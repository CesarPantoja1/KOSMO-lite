from __future__ import annotations

import base64
import re
from typing import Any, cast

import httpx
import structlog

from kosmo.contracts.ai.catalog import RawDiscoveredModel
from kosmo.contracts.sdd.codegen import OpenCodeCatalogInspector
from kosmo.infrastructure.codegen.opencode_seed_catalog import OPENCODE_SEED_MODELS

_log = structlog.get_logger(__name__)


class HttpOpenCodeCatalogInspector(OpenCodeCatalogInspector):
    """Adaptador de infraestructura para obtener los modelos validados por OpenCode."""

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
        server_username: str = "opencode",
        server_password: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._auth_token = auth_token
        self._server_username = server_username
        self._server_password = server_password
        self._client = client
        self._timeout_seconds = timeout_seconds

    def _get_provider_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._server_password:
            creds = f"{self._server_username}:{self._server_password}"
            encoded = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        elif self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    async def get_supported_models(self) -> dict[str, set[str]]:
        """Consulta OpenCode o el launcher para obtener el catálogo activo.

        Si el servicio no responde, recurre al catálogo semilla verificado.
        """
        if not self._base_url and not self._client:
            return {k: set(v) for k, v in OPENCODE_SEED_MODELS.items()}

        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(
                base_url=self._base_url or "http://localhost:8082", timeout=self._timeout_seconds
            )
            should_close = True

        try:
            # 1. Intentar endpoint /catalog (launcher)
            try:
                resp = await client.get("/catalog", headers=headers)
                if resp.is_success:
                    data = resp.json()
                    if isinstance(data, dict):
                        typed_data = cast("dict[str, Any]", data)
                        result: dict[str, set[str]] = {}
                        for k, v in typed_data.items():
                            if isinstance(v, (list, set, tuple)):
                                v_seq = cast("list[object] | set[object] | tuple[object, ...]", v)
                                result[str(k)] = {str(item) for item in v_seq}
                        return result
            except Exception:
                pass

            # 2. Intentar endpoint /provider (opencode serve directo con basic auth)
            try:
                resp = await client.get("/provider", headers=self._get_provider_headers())
                if resp.is_success:
                    raw_data: object = resp.json()
                    data = cast("dict[str, Any]", raw_data) if isinstance(raw_data, dict) else {}
                    raw_providers: object = data.get("all", [])
                    providers = cast("list[object]", raw_providers) if isinstance(raw_providers, list) else []
                    result: dict[str, set[str]] = {}
                    for entry in providers:
                        if isinstance(entry, dict):
                            entry_dict = cast("dict[str, Any]", entry)
                            p_id = str(entry_dict.get("id", ""))
                            models_map = entry_dict.get("models")
                            if p_id and isinstance(models_map, dict):
                                typed_map = cast("dict[str, Any]", models_map)
                                result[p_id] = {str(k) for k in typed_map}
                    if result:
                        return result
            except Exception:
                pass
        except Exception:
            _log.warning("opencode_catalog.live_query_failed_using_seed", exc_info=True)
        finally:
            if should_close:
                await client.aclose()

        return {k: set(v) for k, v in OPENCODE_SEED_MODELS.items()}

    async def get_raw_models(self) -> list[RawDiscoveredModel]:
        """Consulta OpenCode /provider y extrae los modelos con sus metadatos reales."""
        if not self._base_url and not self._client:
            return []

        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(
                base_url=self._base_url or "http://localhost:4096", timeout=self._timeout_seconds
            )
            should_close = True

        try:
            resp = await client.get("/provider", headers=self._get_provider_headers())
            if not resp.is_success:
                return []
            raw_data: object = resp.json()
            data = cast("dict[str, Any]", raw_data) if isinstance(raw_data, dict) else {}
            raw_providers: object = data.get("all", [])
            providers = cast("list[object]", raw_providers) if isinstance(raw_providers, list) else []
            models: list[RawDiscoveredModel] = []
            allowed_providers = {"anthropic", "openai", "google", "deepseek"}
            for entry in providers:
                if not isinstance(entry, dict):
                    continue
                entry_dict = cast("dict[str, Any]", entry)
                p_id = str(entry_dict.get("id", ""))
                if p_id not in allowed_providers:
                    continue
                models_map = entry_dict.get("models")
                if not isinstance(models_map, dict):
                    continue
                typed_map = cast("dict[str, Any]", models_map)
                for m_id, m_data in typed_map.items():
                    if not isinstance(m_data, dict):
                        continue
                    m_str_id = str(m_id)
                    if bool(re.search(r"-\d{8}$", m_str_id)):
                        continue
                    m_dict = cast("dict[str, Any]", m_data)
                    limit_raw = m_dict.get("limit")
                    limit_dict = cast("dict[str, Any]", limit_raw) if isinstance(limit_raw, dict) else {}
                    cap_raw = m_dict.get("capabilities")
                    cap_dict = cast("dict[str, Any]", cap_raw) if isinstance(cap_raw, dict) else {}
                    inp_raw = cap_dict.get("input")
                    inp_dict = cast("dict[str, Any]", inp_raw) if isinstance(inp_raw, dict) else {}

                    display_name = str(m_dict.get("name") or m_id)
                    status_str = str(m_dict.get("status", "active"))
                    is_deprecated = status_str == "deprecated"
                    context_win = int(limit_dict.get("context") or 128000)
                    max_out = int(limit_dict.get("output") or 8192)
                    supports_tools = bool(cap_dict.get("toolcall", True))
                    supports_vision = bool(inp_dict.get("image", False))

                    models.append(
                        RawDiscoveredModel(
                            provider=p_id,
                            model_id=str(m_id),
                            display_name=display_name,
                            context_window=context_win,
                            max_output_tokens=max_out,
                            supports_tools=supports_tools,
                            supports_vision=supports_vision,
                            is_deprecated=is_deprecated,
                            raw_metadata=m_dict,
                        )
                    )
            return models
        except Exception:
            _log.warning("opencode_catalog.raw_models_query_failed", exc_info=True)
            return []
        finally:
            if should_close:
                await client.aclose()
