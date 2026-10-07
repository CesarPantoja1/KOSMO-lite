from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog
from ulid import ULID

from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    FeatureImplementationRepository,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    WorkspaceManagerPort,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.domain.codegen.parse_validation_output import truncate_error_output
from kosmo.domain.codegen.registry_edit import remove_feature_from_registry

_log = structlog.get_logger(__name__)


def _build_fix_prompt(feature: Feature, error_feedback: str) -> str:
    return (
        f"La aplicación quedó rota tras eliminar la feature '{feature.slug}'. "
        "NO recrees la feature ni ninguno de sus archivos: la feature fue eliminada del producto a propósito. "
        "Corrige solo las referencias colgantes (imports, registros, componentes y tests) para que la "
        "aplicación compile, pase las validaciones y funcione sin esa feature.\n"
        f"## Errores detectados:\n{error_feedback}"
    )


@dataclass(frozen=True)
class DeleteFeatureCodeInput:
    feature: Feature
    max_fix_attempts: int = 2


class DeleteFeatureCodeUseCase:
    """Elimina el código generado de una feature y garantiza que la aplicación siga funcionando.

    Ejecuta en background vía el broker: borra los archivos de la feature, valida la
    aplicación y, si algo se rompe, el agente corrige las referencias sin recrear la
    feature. Si no logra dejarla funcional, revierte el borrado (git revert) para que
    la aplicación nunca quede rota.
    """

    def __init__(
        self,
        workspace_manager: WorkspaceManagerPort,
        code_runner: CodeRunnerPort,
        opencode_client: OpenCodeClientPort,
        implementation_repo: FeatureImplementationRepository,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._code_runner = code_runner
        self._opencode_client = opencode_client
        self._implementation_repo = implementation_repo

    async def execute_stream(self, input_data: DeleteFeatureCodeInput) -> AsyncIterator[OpenCodeEvent]:
        run_id = ULID().hex
        feature = input_data.feature

        await self._workspace_manager.acquire_lock(feature.project_id)
        try:
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.PLAN_PROGRESS,
                session_id="",
                data={"delta": f"Eliminando la funcionalidad '{feature.title}' del código...", "stage": "deleting"},
                run_id=run_id,
            )

            workspace = await self._workspace_manager.get_workspace(feature.project_id)
            if workspace is None or not workspace.workspace_dir:
                await self._implementation_repo.delete(feature.id)
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.DONE,
                    session_id="",
                    data={"status": "deleted", "delta": "La funcionalidad se eliminó correctamente."},
                    run_id=run_id,
                )
                return

            removed = await self._workspace_manager.remove_feature_paths(feature.project_id, feature.slug)
            await self._workspace_manager.update_text_file(
                feature.project_id,
                "src/lib/feature-registry.ts",
                lambda content: remove_feature_from_registry(content, feature.slug),
            )

            commit_hash: str | None = None
            if removed:
                commit_hash = await self._workspace_manager.commit_workspace(
                    feature.project_id,
                    f"feat({feature.slug}): remove feature {feature.display_id} - {feature.title}",
                )

            await self._implementation_repo.delete(feature.id)

            if not removed:
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.DONE,
                    session_id="",
                    data={
                        "status": "deleted",
                        "delta": "La funcionalidad se eliminó y la aplicación sigue funcionando correctamente.",
                    },
                    run_id=run_id,
                )
                return

            session_id: str | None = None
            job_started = False
            try:
                for attempt in range(1, input_data.max_fix_attempts + 2):
                    if attempt == 1:
                        delta = "Validando la aplicación después de la eliminación..."
                    else:
                        delta = (
                            "Corrigiendo la aplicación para que funcione sin la funcionalidad "
                            f"(intento {attempt - 1})..."
                        )
                    yield OpenCodeEvent(
                        event_type=OpenCodeEventType.BUILD_PROGRESS,
                        session_id=session_id or "",
                        data={"delta": delta, "stage": "validating", "attempt": attempt},
                        run_id=run_id,
                    )

                    validation = await self._code_runner.run_pipeline(workspace.workspace_dir, run_id=run_id)
                    if validation.all_passed:
                        yield OpenCodeEvent(
                            event_type=OpenCodeEventType.DONE,
                            session_id=session_id or "",
                            data={
                                "status": "deleted",
                                "delta": "La funcionalidad se eliminó y la aplicación sigue funcionando correctamente.",
                            },
                            run_id=run_id,
                        )
                        return

                    if attempt > input_data.max_fix_attempts:
                        break

                    if not job_started:
                        start_job = getattr(self._opencode_client, "start_job", None)
                        if start_job is not None:
                            await start_job(workspace.workspace_dir)
                            job_started = True

                    if not await self._opencode_client.health_check():
                        _log.warning(
                            "delete_feature_code.opencode_unavailable",
                            feature_id=str(feature.id),
                            run_id=run_id,
                        )
                        break

                    if session_id is None:
                        session = await self._opencode_client.create_session(
                            workspace_dir=workspace.workspace_dir,
                            title=f"Fix app after removing feature: {feature.title}",
                        )
                        session_id = session.session_id

                    error_feedback = truncate_error_output(
                        "\n".join(validation.error_summary),
                        max_chars=2000,
                    )
                    async for ev in self._opencode_client.send_prompt(
                        session_id,
                        _build_fix_prompt(feature, error_feedback),
                        agent="build",
                    ):
                        yield ev

                # Último recurso: la aplicación debe quedar funcional siempre
                if commit_hash is not None:
                    await self._workspace_manager.revert_commit(feature.project_id, commit_hash)
                    _log.warning(
                        "delete_feature_code.reverted",
                        feature_id=str(feature.id),
                        commit=commit_hash,
                        run_id=run_id,
                    )
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id or "",
                    data={
                        "error": "No se pudo eliminar la funcionalidad. La aplicación volvió a su estado anterior.",
                        "status": "delete_reverted",
                    },
                    run_id=run_id,
                )
            except Exception as exc:
                if commit_hash is not None:
                    with contextlib.suppress(Exception):
                        await self._workspace_manager.revert_commit(feature.project_id, commit_hash)
                _log.exception("delete_feature_code.failed", feature_id=str(feature.id), run_id=run_id)
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id or "",
                    data={
                        "error": f"No se pudo reparar la aplicación tras eliminar la funcionalidad: {exc}",
                        "status": "delete_reverted",
                    },
                    run_id=run_id,
                )
            finally:
                if session_id is not None:
                    with contextlib.suppress(Exception):
                        await self._opencode_client.close_session(session_id)
                if job_started:
                    stop_job = getattr(self._opencode_client, "stop_job", None)
                    if stop_job is not None:
                        with contextlib.suppress(Exception):
                            await stop_job()
        finally:
            with contextlib.suppress(Exception):
                await self._workspace_manager.release_lock(feature.project_id)
