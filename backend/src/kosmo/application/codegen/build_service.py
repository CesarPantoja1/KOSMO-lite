from __future__ import annotations

import contextlib
import time
from collections.abc import Awaitable, Callable

import structlog

from kosmo.application.codegen.implementation_context_builder import (
    ImplementationContextBuilder,
    collect_workspace_feature_files,
    normalize_generated_file_path,
)
from kosmo.contracts.sdd.codegen import (
    FileSystemReader,
    ImplementationPlan,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    WorkspaceManagerPort,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.product_map import ImplementationDisposition, ProductMap
from kosmo.contracts.telemetry import record_codegen_duration
from kosmo.domain.codegen.structural_validator import validate_workspace_feature_structure
from kosmo.domain.sdd.document_converters import slugify_spanish

_log = structlog.get_logger("kosmo.codegen.build")


class OpenCodeGenerationError(RuntimeError):
    """Un error del stream de OpenCode que debe detener la generación actual."""


def raise_for_opencode_error(event: OpenCodeEvent) -> None:
    """Convierte errores emitidos por OpenCode en una terminación inequívoca."""
    if event.event_type != OpenCodeEventType.ERROR:
        return
    detail = event.data.get("error")
    extra = event.data.get("detail")
    message = str(detail).strip() if detail is not None else "OpenCode devolvió un error sin detalle."
    if extra:
        message = f"{message}: {str(extra).strip()}"
    raise OpenCodeGenerationError(message)


_raise_for_opencode_error = raise_for_opencode_error


class BuildService:
    """Orquesta la fase de construcción de código enviando prompts al Build Agent y recolectando archivos generados."""

    def __init__(
        self,
        opencode_client: OpenCodeClientPort,
        context_builder: ImplementationContextBuilder,
        workspace_manager: WorkspaceManagerPort,
        fs_reader: FileSystemReader,
    ) -> None:
        self._opencode_client = opencode_client
        self._context_builder = context_builder
        self._workspace_manager = workspace_manager
        self._fs_reader = fs_reader

    async def execute_build(
        self,
        *,
        feature: Feature,
        req_markdown: str,
        diagram_syntax: str,
        ux_prompt_block: str,
        project_context: str,
        impl_plan: ImplementationPlan,
        product_map: ProductMap | None,
        workspace_dir: str,
        session_id: str,
        emit_event: Callable[[OpenCodeEvent], Awaitable[None]],
    ) -> set[str]:
        build_start = time.monotonic()
        feature_slug = slugify_spanish(feature.slug) or feature.slug

        plan_lines = "\n".join(
            f"- [{op.action}] {op.path}" + (f" — {op.description}" if op.description else "")
            for op in impl_plan.operations
        )
        build_prompt = self._context_builder.build_build_prompt(
            feature=feature,
            req_markdown=req_markdown,
            diagram_syntax=diagram_syntax,
            ux_prompt_block=ux_prompt_block,
            project_context=project_context,
            plan_lines=plan_lines,
            product_map=product_map,
        )

        generated_files: set[str] = set()
        try:
            async for ev in self._opencode_client.send_prompt(session_id, build_prompt, agent="build"):
                _raise_for_opencode_error(ev)
                await emit_event(ev)
                if ev.event_type == OpenCodeEventType.FILE_EDIT:
                    file_path: object = ev.data.get("path") or ev.data.get("file")
                    if file_path is not None:
                        normalized_p = normalize_generated_file_path(str(file_path), workspace_dir)
                        if normalized_p:
                            generated_files.add(normalized_p)
                elif ev.event_type == OpenCodeEventType.BUILD_COMPLETE:
                    files_obj: object = ev.data.get("files")
                    if isinstance(files_obj, list):
                        files_items: list[object] = list(files_obj)  # type: ignore[reportUnknownVariableType]
                        for f_item in files_items:
                            normalized_p = normalize_generated_file_path(str(f_item), workspace_dir)
                            if normalized_p:
                                generated_files.add(normalized_p)
        except OpenCodeGenerationError as exc:
            disposition = (
                product_map.get_disposition(feature.id).disposition if product_map else ImplementationDisposition.CREATE
            )
            structural_check = validate_workspace_feature_structure(
                workspace_dir=workspace_dir,
                feature_slug=feature_slug,
                fs_reader=self._fs_reader,
                extra_files=generated_files,
                disposition=disposition,
            )
            if structural_check.is_valid:
                _log.warning(
                    "codegen.opencode_build_timeout_recovered",
                    feature_id=str(feature.id),
                    project_id=str(feature.project_id),
                    error=str(exc),
                )
                await emit_event(
                    OpenCodeEvent(
                        event_type=OpenCodeEventType.BUILD_PROGRESS,
                        session_id=session_id,
                        data={
                            "delta": (
                                "La comunicación con OpenCode finalizó por tiempo límite, "
                                "pero se detectó código generado en disco. Procediendo a validación..."
                            ),
                            "stage": "validating",
                        },
                    )
                )
            else:
                with contextlib.suppress(Exception):
                    await self._workspace_manager.rollback_workspace(feature.project_id)
                raise

        generated_files.update(collect_workspace_feature_files(workspace_dir, feature_slug, self._fs_reader))
        record_codegen_duration("build", time.monotonic() - build_start, status="success")
        return generated_files


ExecutionService = BuildService
