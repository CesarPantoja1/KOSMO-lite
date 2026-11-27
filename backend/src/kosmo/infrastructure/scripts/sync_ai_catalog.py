"""Script CLI para sincronizar el catálogo de modelos de IA con OpenCode y proveedores.

Uso:
    uv run python -m kosmo.infrastructure.scripts.sync_ai_catalog

Puede ser invocado por:
    - Crontab del sistema operativo (Linux host).
    - Kubernetes CronJobs.
    - Pipelines de CI/CD tras actualizar OpenCode.
"""

from __future__ import annotations

import asyncio
import sys

from kosmo.config import settings
from kosmo.infrastructure.api.composition import build_app_components
from kosmo.infrastructure.api.dependencies.ai_config import build_sync_ai_catalog_use_case


async def _run() -> int:
    components = build_app_components(settings)
    try:
        print("[sync_ai_catalog] Iniciando sincronización del catálogo de IA...")  # noqa: T201
        use_case = build_sync_ai_catalog_use_case(components)

        provider_keys: dict[str, str | None] = {}
        if settings.llm_api_key and settings.llm_provider != "noop":
            provider_keys[settings.llm_provider] = settings.llm_api_key.get_secret_value()

        result = await use_case.execute(provider_keys=provider_keys or None)

        upserted = result.get("upserted", 0)
        active = result.get("active", 0)
        print(f"[sync_ai_catalog] Sincronización exitosa: upserted={upserted}, active={active}")  # noqa: T201
        return 0
    except Exception as exc:
        print(f"[sync_ai_catalog] ERROR al sincronizar catálogo: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    finally:
        await components.close()


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
