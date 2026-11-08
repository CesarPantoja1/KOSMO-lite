from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from kosmo.infrastructure.api.dependencies.ai_config import build_sync_ai_catalog_use_case

if TYPE_CHECKING:
    from kosmo.config import Settings
    from kosmo.infrastructure.api.composition import AppContainer

_log = structlog.get_logger("kosmo.ai.catalog_sync")


async def run_catalog_sync_worker(components: AppContainer, settings: Settings) -> None:
    """Worker asíncrono periódico para sincronizar el catálogo de modelos de IA.

    Se ejecuta en el lifespan de FastAPI y sondea OpenCode y los proveedores configurados
    según el intervalo configurado (por defecto 24 horas).
    """
    if not settings.ai_catalog_sync_enabled:
        _log.info("catalog_sync.disabled")
        return

    # Espera inicial para que la BD y OpenCode completen su inicialización
    initial_delay = max(0.0, float(settings.ai_catalog_sync_initial_delay_seconds))
    if initial_delay > 0:
        _log.info("catalog_sync.waiting_initial_delay", delay_seconds=initial_delay)
        await asyncio.sleep(initial_delay)

    retry_delay = 60.0
    while True:
        try:
            _log.info("catalog_sync.start")
            use_case = build_sync_ai_catalog_use_case(components)

            provider_keys: dict[str, str | None] = {}
            if settings.llm_api_key and settings.llm_provider != "noop":
                provider_keys[settings.llm_provider] = settings.llm_api_key.get_secret_value()

            result = await use_case.execute(provider_keys=provider_keys or None)
            _log.info(
                "catalog_sync.success",
                upserted=result.get("upserted", 0),
                active=result.get("active", 0),
            )

            # Restablecer el delay de reintento tras un ciclo exitoso
            retry_delay = 60.0
            normal_interval = max(60.0, float(settings.ai_catalog_sync_interval_hours) * 3600.0)
            await asyncio.sleep(normal_interval)
        except asyncio.CancelledError:
            _log.info("catalog_sync.cancelled")
            raise
        except Exception as exc:
            _log.warning(
                "catalog_sync.failed",
                error=str(exc),
                retry_in_seconds=retry_delay,
                exc_info=True,
            )
            await asyncio.sleep(retry_delay)
            # Backoff exponencial acotado hasta un máximo de 10 minutos
            retry_delay = min(retry_delay * 2, 600.0)
