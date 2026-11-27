from __future__ import annotations

from typing import Any, cast

import httpx
import structlog

from kosmo.contracts.ai.catalog import ModelDiscoveryAdapter, RawDiscoveredModel
from kosmo.infrastructure.llm.discovery.base import is_excluded_model

_log = structlog.get_logger(__name__)


class AnthropicDiscoveryAdapter(ModelDiscoveryAdapter):
    """Adaptador oficial para listar modelos de Anthropic vía GET /v1/models."""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout_seconds: float = 6.0) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    @property
    def provider(self) -> str:
        return "anthropic"

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
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key.strip(),
                    "anthropic-version": "2023-06-01",
                },
            )
            if not resp.is_success:
                _log.warning("anthropic_discovery.http_error", status_code=resp.status_code)
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
                if not mid.startswith("claude-") or is_excluded_model(mid):
                    continue

                display_name = str(item_dict.get("display_name") or mid.replace("-", " ").title())
                context_window = int(item_dict.get("max_input_tokens") or 200000)
                max_output = int(item_dict.get("max_tokens") or 8192)

                results.append(
                    RawDiscoveredModel(
                        provider="anthropic",
                        model_id=mid,
                        display_name=display_name,
                        context_window=context_window,
                        max_output_tokens=max_output,
                        supports_tools=True,
                        supports_vision=True,
                        raw_metadata=item_dict,
                    )
                )
            return results
        except Exception:
            _log.warning("anthropic_discovery.failed", exc_info=True)
            return []
        finally:
            if should_close:
                await client.aclose()
