from __future__ import annotations

import asyncio
import logging

from kosmo.application.integrations.handle_deployment_failure import (
    HandleDeploymentFailureCommand,
    HandleDeploymentFailureUseCase,
)
from kosmo.application.integrations.monitor_deployment_status import (
    MonitorDeploymentStatusCommand,
    MonitorDeploymentStatusUseCase,
)
from kosmo.contracts.integrations.deployment import (
    DeploymentProvider,
    DeploymentWorkerPort,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId

logger = logging.getLogger(__name__)


class DeploymentPollingWorker(DeploymentWorkerPort):
    """Worker en segundo plano en la capa de infraestructura para sondeo asíncrono de despliegues.

    Gestiona el ciclo de vida de tareas no bloqueantes de sondeo de despliegues en curso,
    evita la concurrencia duplicada sobre el mismo proyecto y asegura la persistencia
    continua del estado en base de datos para resistir recargas de página.
    """

    def __init__(
        self,
        monitor_use_case: MonitorDeploymentStatusUseCase,
        failure_handler: HandleDeploymentFailureUseCase | None = None,
    ) -> None:
        self._monitor_use_case = monitor_use_case
        self._failure_handler = failure_handler
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

    def start_monitoring(
        self,
        project_id: ProjectId,
        user_id: UserId,
        *,
        max_attempts: int = 60,
        delay_seconds: int = 10,
        provider: DeploymentProvider = DeploymentProvider.RAILWAY,
    ) -> asyncio.Task[None]:
        """Inicia una tarea de sondeo en segundo plano para el proyecto o retorna la activa si ya existe."""
        project_id_str = str(project_id)

        # Si ya existe una tarea activa en ejecución, retornarla sin duplicar
        existing = self._active_tasks.get(project_id_str)
        if existing and not existing.done():
            logger.info("El sondeo para el proyecto %s ya está en ejecución.", project_id_str)
            return existing

        async def _run() -> None:
            cmd = MonitorDeploymentStatusCommand(
                project_id=project_id,
                user_id=user_id,
                max_attempts=max_attempts,
                delay_seconds=delay_seconds,
            )
            try:
                await self._monitor_use_case.execute(cmd)
            except asyncio.CancelledError:
                logger.info("Monitoreo de despliegue cancelado para el proyecto %s.", project_id_str)
                raise
            except Exception as exc:
                logger.exception(
                    "Error no controlado en el sondeo de despliegue para el proyecto %s: %s",
                    project_id_str,
                    exc,
                )
                if self._failure_handler is not None:
                    try:
                        await self._failure_handler.execute(
                            HandleDeploymentFailureCommand(
                                project_id=project_id,
                                error_message=f"Fallo durante el monitoreo del despliegue: {exc}",
                                provider=provider,
                            )
                        )
                    except Exception as handler_exc:
                        logger.exception("Error al registrar fallo de despliegue en DB: %s", handler_exc)

        task = asyncio.create_task(_run(), name=f"deploy_monitor_{project_id_str}")
        self._active_tasks[project_id_str] = task

        def _cleanup(_: asyncio.Task[None]) -> None:
            self._active_tasks.pop(project_id_str, None)

        task.add_done_callback(_cleanup)
        return task

    def is_monitoring(self, project_id: ProjectId) -> bool:
        """Determina si hay una tarea de sondeo activa para el proyecto."""
        task = self._active_tasks.get(str(project_id))
        return task is not None and not task.done()

    def cancel_monitoring(self, project_id: ProjectId) -> bool:
        """Cancela la tarea de sondeo activa para el proyecto si existe."""
        task = self._active_tasks.get(str(project_id))
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def shutdown(self) -> None:
        """Cancela y espera la finalización de todas las tareas activas de sondeo."""
        tasks_to_cancel = [t for t in self._active_tasks.values() if not t.done()]
        for task in tasks_to_cancel:
            task.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self._active_tasks.clear()
