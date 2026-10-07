from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

from kosmo.contracts.persistence.persistence import UnitOfWork
from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
from kosmo.contracts.sdd.codegen import FeatureImplementationStatus
from kosmo.contracts.sdd.errors import ProjectNotFoundError
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.domain.sdd.document_converters import document_to_markdown, markdown_to_document
from kosmo.domain.sdd.plan_diffs import apply_change_diff
from kosmo.domain.sdd.requirements_markdown import parse_requirements_markdown
from kosmo.domain.sdd.text_normalizer import strip_origin_line
from kosmo.domain.sdd.validators.activity_diagram_validator import validate_activity_diagram_syntax

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AppliedImpact:
    target_id: str
    artifact_type: str


@dataclass(frozen=True)
class FailedImpact:
    target_id: str
    artifact_type: str
    reason: str


@dataclass(frozen=True)
class ApplyConsistencyImpactsOutput:
    applied: list[AppliedImpact] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    failed: list[FailedImpact] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class ApplyConsistencyImpactsUseCase:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self,
        project_id: ProjectId,
        impacts: list[dict[str, object]],
    ) -> ApplyConsistencyImpactsOutput:
        async with self._uow as uow:
            project = await uow.projects.by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(project_id),
                instance=f"/api/v1/projects/{project_id}/consistency/apply",
            )

        applied: list[AppliedImpact] = []
        failed: list[FailedImpact] = []

        for impact in impacts:
            artifact_type = str(impact.get("artifact_type", ""))
            target_id = str(impact.get("target_id", ""))
            action = str(impact.get("action", "update"))
            field = str(impact.get("field", "description"))
            before = str(impact.get("before", ""))
            after = str(impact.get("after", ""))

            if not artifact_type or not target_id:
                failed.append(
                    FailedImpact(target_id=target_id, artifact_type=artifact_type, reason="Datos incompletos")
                )
                continue

            if action == "update" and not before and not after and artifact_type != "FeatureImplementation":
                failed.append(
                    FailedImpact(target_id=target_id, artifact_type=artifact_type, reason="Sin sugerencia de cambio")
                )
                continue

            # Transaccion por impacto: un fallo no envenena los impactos siguientes
            try:
                async with self._uow as uow:
                    result = await self._apply_impact(
                        uow, project_id, artifact_type, target_id, action, field, before, after
                    )
            except Exception as exc:
                _log.warning(
                    "consistency.apply_impact_failed",
                    target_id=target_id,
                    artifact_type=artifact_type,
                    exc_info=True,
                )
                failed.append(FailedImpact(target_id=target_id, artifact_type=artifact_type, reason=str(exc)))
                continue

            if result is None:
                applied.append(AppliedImpact(target_id=target_id, artifact_type=artifact_type))
            else:
                failed.append(FailedImpact(target_id=target_id, artifact_type=artifact_type, reason=result))

        return ApplyConsistencyImpactsOutput(applied=applied, failed=failed)

    async def _apply_impact(
        self,
        uow: UnitOfWork,
        project_id: ProjectId,
        artifact_type: str,
        target_id: str,
        action: str,
        field: str,
        before: str,
        after: str,
    ) -> str | None:
        # Row-lock del artefacto destino: el diff se computa contra el contenido
        # leido bajo lock, por lo que dos applies concurrentes se serializan y
        # el segundo falla deterministamente si el contenido ya cambio (D2).
        feature_id = FeatureId(target_id)

        if artifact_type == "EARSRequirement":
            if action == "delete":
                return None  # cascada BD: la feature padre ya se eliminó
            return await self._apply_requirement(uow, project_id, feature_id, before, after)

        if artifact_type == "Feature":
            if action == "delete":
                return await self._delete_feature(uow, feature_id)
            return await self._update_feature(uow, feature_id, field, before, after)

        if artifact_type == "ActivityDiagram":
            if action == "delete":
                return None  # cascada BD: la feature padre ya se eliminó
            return await self._update_diagram(uow, feature_id, before, after)

        if artifact_type == "FeatureImplementation":
            if action == "delete":
                return await self._delete_implementation(uow, feature_id)
            return await self._mark_implementation_for_review(uow, feature_id)

        if artifact_type == "DiscoveryDocument":
            if action == "delete":
                return "El documento de Descubrimiento no puede eliminarse"
            return await self._update_discovery(uow, project_id, before, after)

        return f"Tipo de artefacto desconocido: {artifact_type}"

    async def _mark_implementation_for_review(self, uow: UnitOfWork, feature_id: FeatureId) -> str | None:
        import dataclasses

        impl = await uow.implementations.by_feature_id(feature_id)
        if impl is None:
            return "La implementación no existe"
        updated = dataclasses.replace(
            impl,
            status=FeatureImplementationStatus.REQUIRES_REVIEW,
            updated_at=datetime.now(UTC),
        )
        await uow.implementations.save(updated)
        return None

    async def _delete_implementation(self, uow: UnitOfWork, feature_id: FeatureId) -> str | None:
        impl = await uow.implementations.by_feature_id(feature_id)
        if impl is None:
            return None
        await uow.implementations.delete(feature_id)
        return None

    async def _update_discovery(self, uow: UnitOfWork, project_id: ProjectId, before: str, after: str) -> str | None:
        document = await uow.documents.get_discovery(project_id, for_update=True)
        if document is None:
            return "El documento de Descubrimiento no existe"

        markdown = document_to_markdown(document)
        result = apply_change_diff(markdown, before=before, after=after)
        if result is None:
            return "El texto original no se encontro en el documento de Descubrimiento"

        await uow.documents.save_discovery(
            project_id=project_id,
            document=markdown_to_document(result),
        )
        return None

    async def _apply_requirement(
        self,
        uow: UnitOfWork,
        project_id: ProjectId,  # noqa: ARG002
        feature_id: FeatureId,
        before: str,
        after: str,
    ) -> str | None:
        markdown = await uow.requirements.by_feature_id(feature_id, for_update=True)
        if markdown is None:
            return "El documento de requisitos no existe"

        result = apply_change_diff(markdown, before=before, after=after)
        if result is None:
            return "El texto original no se encontro en los requisitos"

        await uow.requirements.save(feature_id, result)

        feature = await uow.features.by_id(feature_id)
        if feature is not None:
            try:
                parsed = parse_requirements_markdown(result, feature_id, feature.number)

                await uow.traceability.delete_by_entity_id(str(feature_id))
                for r in parsed:
                    await uow.traceability.add_edge(
                        source_type="feature",
                        source_id=str(feature_id),
                        target_type="requirement",
                        target_id=str(r.id),
                    )
            except Exception:
                _log.warning(
                    "consistency.reparse_failed",
                    feature_id=str(feature_id),
                    exc_info=True,
                )

        return None

    async def _update_feature(
        self, uow: UnitOfWork, feature_id: FeatureId, field: str, before: str, after: str
    ) -> str | None:
        feature = await uow.features.by_id(feature_id, for_update=True)
        if feature is None:
            return "La caracteristica no existe"

        valid_fields = {"title", "description", "origin"}
        if field not in valid_fields:
            return f"Campo no modificable: {field}"

        current: str = str(getattr(feature, field, ""))
        # El LLM incluye el origen interno en la descripción sugerida; se elimina
        # para no contaminar la descripción guardada ni romper el match del diff.
        if field == "description":
            current = strip_origin_line(current)
            before = strip_origin_line(before)
            after = strip_origin_line(after)
        result = apply_change_diff(current, before=before, after=after)
        if result is None:
            return f"El texto original no se encontro en {field} de la caracteristica"

        setattr(feature, field, result)
        if field == "title":
            feature.slug = result.lower().replace(" ", "-")
        feature.updated_at = datetime.now(UTC)
        await uow.features.save(feature)
        return None

    async def _delete_feature(self, uow: UnitOfWork, feature_id: FeatureId) -> str | None:
        feature = await uow.features.by_id(feature_id, for_update=True)
        if feature is None:
            return "La caracteristica no existe"

        await uow.requirements.delete(feature_id)
        await uow.diagrams.delete(feature_id)
        await uow.features.delete(feature_id)

        try:
            await uow.traceability.delete_by_entity_id(str(feature_id))
        except Exception:
            _log.warning(
                "consistency.delete_feature.traceability_cleanup_failed",
                feature_id=str(feature_id),
                exc_info=True,
            )

        _log.info(
            "consistency.delete_feature.success",
            feature_id=str(feature_id),
            display_id=feature.display_id,
        )
        return None

    async def _update_diagram(self, uow: UnitOfWork, feature_id: FeatureId, before: str, after: str) -> str | None:
        diagram = await uow.diagrams.by_feature_id(feature_id, for_update=True)
        if diagram is None:
            return "El diagrama no existe"

        result = apply_change_diff(diagram.diagram_syntax, before=before, after=after)
        if result is None:
            return "El texto original no se encontro en el diagrama"

        validation = validate_activity_diagram_syntax(result)
        if not validation.is_valid:
            _log.warning(
                "consistency.diagram_validation_failed",
                feature_id=str(feature_id),
                errors=validation.errors,
            )
            return f"El cambio dejaría el diagrama con sintaxis inválida: {'; '.join(validation.errors)}"

        updated = DiagramaActividad(
            id=diagram.id,
            feature_id=diagram.feature_id,
            diagram_syntax=result,
            created_at=diagram.created_at,
            updated_at=datetime.now(UTC),
        )
        await uow.diagrams.save(updated)
        return None
