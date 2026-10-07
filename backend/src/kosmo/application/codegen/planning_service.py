from __future__ import annotations

import contextlib
import dataclasses
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from kosmo.application.codegen.analyze_feature_integration import (
    AnalyzeFeatureIntegrationInput,
    AnalyzeFeatureIntegrationUseCase,
)
from kosmo.application.codegen.analyze_ux_context import (
    UXAnalysisInput,
    UXAnalyzerUseCase,
)
from kosmo.application.codegen.build_service import raise_for_opencode_error
from kosmo.application.codegen.implementation_context_builder import (
    ImplementationContextBuilder,
    normalize_generated_file_path,
)
from kosmo.contracts.sdd.codegen import (
    FeatureImplementation,
    FeatureImplementationRepository,
    FileAction,
    FileOperation,
    ImplementationPlan,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.product_map import ImplementationDisposition, ProductMap
from kosmo.contracts.sdd.ux_context import UXAnalysisOutput
from kosmo.contracts.telemetry import record_codegen_duration
from kosmo.domain.codegen.plan_rules import validate_plan
from kosmo.domain.sdd.document_converters import slugify_spanish

_log = structlog.get_logger("kosmo.codegen.planning")


@dataclass(frozen=True, slots=True)
class PlanningResult:
    impl_plan: ImplementationPlan
    product_map: ProductMap | None
    project_context: str
    ux_analysis: UXAnalysisOutput
    impl: FeatureImplementation


class PlanningService:
    """Orquesta la fase de planificación: análisis de integración, UX, generación del plan y validación determinista."""

    def __init__(
        self,
        opencode_client: OpenCodeClientPort,
        context_builder: ImplementationContextBuilder,
        integration_analyzer: AnalyzeFeatureIntegrationUseCase,
        ux_analyzer: UXAnalyzerUseCase,
        implementation_repo: FeatureImplementationRepository,
    ) -> None:
        self._opencode_client = opencode_client
        self._context_builder = context_builder
        self._integration_analyzer = integration_analyzer
        self._ux_analyzer = ux_analyzer
        self._implementation_repo = implementation_repo

    async def execute_plan(
        self,
        *,
        feature: Feature,
        req_markdown: str,
        diagram_syntax: str,
        workspace_dir: str,
        manifest_files: tuple[str, ...],
        session_id: str,
        impl: FeatureImplementation,
        emit_event: Callable[[OpenCodeEvent], Awaitable[None]],
    ) -> PlanningResult:
        plan_start = time.monotonic()
        feature_slug = slugify_spanish(feature.slug) or feature.slug

        product_map: ProductMap | None = None
        with contextlib.suppress(Exception):
            product_map = await self._integration_analyzer.execute(
                AnalyzeFeatureIntegrationInput(
                    project_id=feature.project_id,
                    current_feature_id=feature.id,
                )
            )

        project_context = await self._context_builder.build_project_context(
            project_id=feature.project_id,
            current_feature_id=feature.id,
            workspace_dir=workspace_dir,
            product_map=product_map,
        )
        ux_analysis = await self._ux_analyzer.execute(
            UXAnalysisInput(feature_id=feature.id, project_id=feature.project_id)
        )

        # Sincronizar site.ts con el arquetipo y tokens reales del análisis UX
        await self._context_builder.sync_site_config(workspace_dir, feature.project_id, ux_analysis)

        await emit_event(
            OpenCodeEvent(
                event_type=OpenCodeEventType.PLAN_PROGRESS,
                session_id=session_id,
                data={
                    "delta": f"Analizando requisitos, UX, integración y diagrama de '{feature.title}'...",
                    "stage": "planning",
                },
            )
        )

        plan_prompt = self._context_builder.build_plan_prompt(
            feature=feature,
            req_markdown=req_markdown,
            diagram_syntax=diagram_syntax,
            ux_prompt_block=ux_analysis.prompt_block,
            project_context=project_context,
            product_map=product_map,
        )

        plan_operations: list[FileOperation] = []
        async for ev in self._opencode_client.send_prompt(session_id, plan_prompt, agent="plan"):
            raise_for_opencode_error(ev)
            await emit_event(ev)
            if ev.event_type == OpenCodeEventType.PLAN_COMPLETE:
                ops_raw: object = ev.data.get("operations")
                if isinstance(ops_raw, list):
                    ops_items: list[object] = list(ops_raw)  # type: ignore[reportUnknownVariableType]
                    for op_item in ops_items:
                        if isinstance(op_item, dict):
                            op_dict: dict[object, object] = dict(op_item)  # type: ignore[reportUnknownVariableType]
                            action_raw = op_dict.get("action", "create")
                            path_raw = str(op_dict.get("path", "")).strip()
                            desc_raw = str(op_dict.get("description", "")).strip()
                            norm_path = normalize_generated_file_path(path_raw, workspace_dir)
                            if norm_path:
                                try:
                                    action = FileAction(str(action_raw).lower())
                                except ValueError:
                                    action = FileAction.CREATE
                                plan_operations.append(
                                    FileOperation(action=action, path=norm_path, description=desc_raw)
                                )

        # Fallback canónico con arquitectura de feature slices si el Plan Agent no produjo operaciones
        if not plan_operations:
            disposition = (
                product_map.get_disposition(feature.id).disposition if product_map else ImplementationDisposition.CREATE
            )
            plan_operations = self._context_builder.build_fallback_plan_operations(
                feature=feature,
                feature_slug=feature_slug,
                manifest_files=manifest_files,
                disposition=disposition,
            )
            _log.info(
                "codegen.fallback_plan_used",
                feature_id=str(feature.id),
                slug=feature_slug,
                operations_count=len(plan_operations),
            )

        impl_plan = ImplementationPlan(
            feature_id=feature.id,
            operations=tuple(plan_operations),
            summary=f"Plan para {feature.title}",
            created_at=datetime.now(UTC),
        )
        # Validar plan determinísticamente
        validate_plan(impl_plan, manifest_files, workspace_dir)
        updated_impl = dataclasses.replace(impl, plan=impl_plan)
        await self._implementation_repo.save(updated_impl)
        record_codegen_duration("plan", time.monotonic() - plan_start, status="success")

        return PlanningResult(
            impl_plan=impl_plan,
            product_map=product_map,
            project_context=project_context,
            ux_analysis=ux_analysis,
            impl=updated_impl,
        )
