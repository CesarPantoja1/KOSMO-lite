from __future__ import annotations

import contextlib
from datetime import date
from typing import Any, cast

import httpx
import structlog

from kosmo.contracts.ai.catalog import ModelDiscoveryAdapter, RawDiscoveredModel
from kosmo.infrastructure.llm.discovery.base import is_excluded_model

_log = structlog.get_logger(__name__)


class OpenAIDiscoveryAdapter(ModelDiscoveryAdapter):
    """Adaptador oficial para listar modelos de OpenAI vía GET /v1/models."""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout_seconds: float = 6.0) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    @property
    def provider(self) -> str:
        return "openai"

    async def discover_models(self, api_key: str | None = None) -> list[RawDiscoveredModel]:
        if not api_key or not api_key.strip():
            return []

        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            should_close = True

        try:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key.strip()}"},
            )
            if not resp.is_success:
                _log.warning("openai_discovery.http_error", status_code=resp.status_code)
                return []

            raw_json: object = resp.json()
            data_dict = cast("dict[str, Any]", raw_json) if isinstance(raw_json, dict) else {}
            raw_list = data_dict.get("data", [])
            data_list: list[object] = cast("list[object]", raw_list) if isinstance(raw_list, list) else []

            results: list[RawDiscoveredModel] = []
            for item in data_list:
                if not isinstance(item, dict):
                    continue
                item_dict = cast("dict[str, Any]", item)
                mid = str(item_dict.get("id", ""))
                if not mid or is_excluded_model(mid):
                    continue

                # OpenAI solo modelos de la familia gpt-4, o1, o3, gpt-5, gpt-6, etc.
                if not mid.startswith(("gpt-4", "o1", "o3", "o4", "gpt-5", "gpt-6")):
                    continue

                shutdown_date_val: date | None = None
                raw_sd = item_dict.get("shutdown_date")
                if isinstance(raw_sd, str) and len(raw_sd) == 10:
                    with contextlib.suppress(ValueError):
                        shutdown_date_val = date.fromisoformat(raw_sd)

                context_window = 128000
                max_output = 16384
                if mid.startswith(("o1", "o3", "o4", "gpt-6", "gpt-5.4", "gpt-5.5", "gpt-5.6")):
                    context_window = 1050000
                    max_output = 128000

                display_name = mid.replace("-", " ").title()
                if "Gpt" in display_name:
                    display_name = display_name.replace("Gpt", "GPT")

                results.append(
                    RawDiscoveredModel(
                        provider="openai",
                        model_id=mid,
                        display_name=display_name,
                        context_window=context_window,
                        max_output_tokens=max_output,
                        supports_tools=True,
                        supports_vision=True,
                        is_deprecated=shutdown_date_val is not None,
                        shutdown_date=shutdown_date_val,
                        raw_metadata=item_dict,
                    )
                )
            return results
        except Exception:
            _log.warning("openai_discovery.failed", exc_info=True)
            return []
        finally:
            if should_close:
                await client.aclose()
