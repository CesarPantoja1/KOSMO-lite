from __future__ import annotations

import dataclasses
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from kosmo.application.codegen.implementation_context_builder import (
    ImplementationContextBuilder,
    collect_workspace_feature_files,
    normalize_generated_file_path,
)
from kosmo.contracts.sdd.codegen import (
    CodeRunnerPort,
    FeatureImplementation,
    FeatureImplementationRepository,
    FileSystemReader,
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    ValidationErrorDetail,
    ValidationRunResult,
    ValidationSeverity,
    ValidationStep,
    ValidationStepResult,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.product_map import ImplementationDisposition, ProductMap
from kosmo.domain.codegen.structural_validator import validate_workspace_feature_structure
from kosmo.domain.sdd.document_converters import slugify_spanish

_log = structlog.get_logger("kosmo.codegen.validation")


@dataclass(frozen=True, slots=True)
class ValidationCycleResult:
    validation_result: ValidationRunResult | None
    retry_history: tuple[tuple[str, ...], ...]
    attempt: int
    generated_files: set[str]
    impl: FeatureImplementation
    duration_seconds: float


class ValidationService:
    """Orquesta la fase de validación técnica y estructural del código, con reintentos guiados."""

    def __init__(
        self,
        code_runner: CodeRunnerPort,
        opencode_client: OpenCodeClientPort,
        context_builder: ImplementationContextBuilder,
        implementation_repo: FeatureImplementationRepository,
        fs_reader: FileSystemReader,
    ) -> None:
        self._code_runner = code_runner
        self._opencode_client = opencode_client
        self._context_builder = context_builder
        self._implementation_repo = implementation_repo
        self._fs_reader = fs_reader

    async def execute_validation(
        self,
        *,
        feature: Feature,
        workspace_dir: str,
        session_id: str,
        product_map: ProductMap | None,
        generated_files: set[str],
        impl: FeatureImplementation,
        max_retries: int,
        run_id: str,
        emit_event: Callable[[OpenCodeEvent], Awaitable[None]],
    ) -> ValidationCycleResult:
        val_start = time.monotonic()
        feature_slug = slugify_spanish(feature.slug) or feature.slug
        attempt = 0

        validation_result: ValidationRunResult | None = None
        retry_history: list[tuple[str, ...]] = []

        while attempt < max_retries:
            attempt += 1
            await emit_event(
                OpenCodeEvent(
                    event_type=OpenCodeEventType.BUILD_PROGRESS,
                    session_id=session_id,
                    data={
                        "delta": f"Validando código (intento {attempt}/{max_retries})...",
                        "stage": "validating",
                        "attempt": attempt,
                    },
                )
            )
            # 1. Validación estructural post-build (page.tsx, slice, feature-registry.ts, domain)
            disposition = (
                product_map.get_disposition(feature.id).disposition if product_map else ImplementationDisposition.CREATE
            )
            structural_result = validate_workspace_feature_structure(
                workspace_dir=workspace_dir,
                feature_slug=feature_slug,
                fs_reader=self._fs_reader,
                extra_files=generated_files,
                disposition=disposition,
            )

            # 2. Validación técnica (tsc, eslint, vitest, build)
            tech_result = await self._code_runner.run_pipeline(workspace_dir, run_id=run_id)

            # 3. Consolidación de resultados
            if not structural_result.is_valid:
                structural_step = ValidationStepResult(
                    step=ValidationStep.STRUCTURE,
                    success=False,
                    error_messages=structural_result.errors,
                    errors=tuple(
                        ValidationErrorDetail(
                            file=err.split(":")[-1].strip() if ":" in err else "workspace",
                            message=err,
                            severity=ValidationSeverity.ERROR,
                        )
                        for err in structural_result.errors
                    ),
                )
                combined_steps = (structural_step,) + tech_result.steps
                combined_errors = structural_result.errors + tech_result.error_summary
                validation_result = dataclasses.replace(
                    tech_result,
                    steps=combined_steps,
                    all_passed=False,
                    error_summary=combined_errors,
                )
            else:
                structural_step = ValidationStepResult(
                    step=ValidationStep.STRUCTURE,
                    success=True,
                )
                combined_steps = (structural_step,) + tech_result.steps
                validation_result = dataclasses.replace(
                    tech_result,
                    steps=combined_steps,
                )

            impl = dataclasses.replace(
                impl,
                attempt_count=attempt,
                last_validation=validation_result,
                generated_files=tuple(sorted(generated_files)),
                updated_at=datetime.now(UTC),
            )
            await self._implementation_repo.save(impl)

            if validation_result.all_passed:
                await emit_event(
                    OpenCodeEvent(
                        event_type=OpenCodeEventType.BUILD_PROGRESS,
                        session_id=session_id,
                        data={
                            "delta": "Validaciones completadas con éxito en el workspace.",
                            "stage": "validation_passed",
                        },
                    )
                )
                break

            # Acumular historial de errores del intento actual
            retry_history.append(validation_result.error_summary)

            if attempt < max_retries:
                # Emitir evento RETRY para notificar al frontend
                await emit_event(
                    OpenCodeEvent(
                        event_type=OpenCodeEventType.RETRY,
                        session_id=session_id,
                        data={
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "error_summary": list(validation_result.error_summary),
                        },
                    )
                )

                fix_prompt = self._context_builder.build_fix_prompt(
                    attempt=attempt,
                    max_retries=max_retries,
                    validation_result=validation_result,
                )
                async for ev in self._opencode_client.send_prompt(session_id, fix_prompt, agent="build"):
                    if ev.event_type == OpenCodeEventType.ERROR:
                        _log.warning(
                            "codegen.fix_prompt_opencode_error",
                            attempt=attempt,
                            error=ev.data.get("error"),
                        )
                        continue
                    await emit_event(ev)
                    if ev.event_type == OpenCodeEventType.FILE_EDIT:
                        file_path_fix: object = ev.data.get("path")
                        if file_path_fix is not None:
                            normalized_p = normalize_generated_file_path(str(file_path_fix), workspace_dir)
                            if normalized_p:
                                generated_files.add(normalized_p)

        generated_files.update(collect_workspace_feature_files(workspace_dir, feature_slug, self._fs_reader))
        val_duration = time.monotonic() - val_start

        return ValidationCycleResult(
            validation_result=validation_result,
            retry_history=tuple(retry_history),
            attempt=attempt,
            generated_files=generated_files,
            impl=impl,
            duration_seconds=val_duration,
        )


VerificationService = ValidationService
