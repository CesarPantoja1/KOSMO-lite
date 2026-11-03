from __future__ import annotations

from dataclasses import dataclass

from kosmo.application.consistency.trigger_downstream import trigger_downstream_evaluation
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.contracts.pipeline.phase_contexts import DiscoveryRefinePhaseContext
from kosmo.contracts.pipeline.phase_outputs import DiscoveryPhaseOutput
from kosmo.contracts.sdd.document import RichTextDocument, SpecPhase
from kosmo.contracts.sdd.errors import LLMInvocationError, ProjectNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.contracts.sdd.repositories import (
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.document_converters import document_to_markdown


@dataclass(frozen=True)
class RegenerateDiscoveryInput:
    project_id: ProjectId


@dataclass(frozen=True)
class RegenerateDiscoveryOutput:
    artifact_id: str
    content: str
    phase: str
    document: RichTextDocument


class RegenerateDiscoveryUseCase:
    def __init__(
        self,
        project_repo: ProjectRepository,
        document_repo: DocumentRepository,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        agent: AgentPort,
        outbox: OutboxPort | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._document_repo = document_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._agent = agent
        self._outbox = outbox

    async def execute(self, input_data: RegenerateDiscoveryInput) -> RegenerateDiscoveryOutput:
        project = await self._project_repo.by_id(input_data.project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(input_data.project_id),
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/regenerate",
            )

        current_doc = await self._document_repo.get_discovery(input_data.project_id)
        if current_doc is None:
            raise LLMInvocationError(
                detail="No existe un documento de descubrimiento previo para regenerar.",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/regenerate",
            )

        current_markdown = document_to_markdown(current_doc)

        features = await self._feature_repo.list_by_project(input_data.project_id)
        ctx_artifacts = await self._build_artifacts_summary(features, input_data.project_id)

        user_instructions = (
            "Regenera completamente el documento de descubrimiento del proyecto "
            "manteniendo las 7 secciones obligatorias (Visión del producto, "
            "Espacio del problema, Actores, Propuesta de valor, Metas del producto, "
            "Reglas de negocio, Alcance).\n\n"
            "El documento actual es el siguiente (úsalo como base estructural):\n\n"
            f"{current_markdown}\n\n"
        )
        if ctx_artifacts:
            user_instructions += (
                "El proyecto ya cuenta con los siguientes artefactos en fases "
                f"posteriores. Asegúrate de que el discovery sea coherente con ellos:\n\n"
                f"{ctx_artifacts}"
            )

        context = DiscoveryRefinePhaseContext(
            current_document=current_doc,
            user_instructions=user_instructions,
        )

        try:
            phase_output = await self._agent.execute_with_skill(
                skill_name="discovery_refine",
                context=context,
                project_id=input_data.project_id,
                user_instructions=user_instructions,
            )
        except Exception as exc:
            raise LLMInvocationError(
                detail=f"Error al regenerar el documento de descubrimiento: {exc}",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/regenerate",
            ) from exc

        if not isinstance(phase_output, DiscoveryPhaseOutput):  # type: ignore[reportUnknownMemberType]
            raise LLMInvocationError(
                detail="El agente no devolvió un DiscoveryPhaseOutput válido.",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/regenerate",
            )

        validation = phase_output.validation_result
        if not validation.is_valid or phase_output.discovery_document.section_count == 0:
            detail = "; ".join(validation.errors) or "El documento regenerado está vacío."
            raise LLMInvocationError(
                detail=f"La regeneración del discovery falló: {detail}",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/regenerate",
            )

        saved_doc = await self._document_repo.save_discovery(
            project_id=input_data.project_id,
            document=phase_output.discovery_document,
        )

        await trigger_downstream_evaluation(
            self._outbox,
            project_id=input_data.project_id,
            source_phase=SpecPhase.DESCUBRIMIENTO,
            changes=[
                {
                    "section": "documento",
                    "description": "Regeneración con IA del documento de Descubrimiento",
                    "before": "",
                    "after": document_to_markdown(saved_doc),
                }
            ],
        )

        return RegenerateDiscoveryOutput(
            artifact_id=str(input_data.project_id),
            content=document_to_markdown(saved_doc),
            phase="discovery",
            document=saved_doc,
        )

    async def _build_artifacts_summary(
        self,
        features: list[Feature],
        project_id: ProjectId,  # noqa: ARG002
    ) -> str:
        parts: list[str] = []

        if features:
            parts.append("## Características\n")
            for f in features:
                parts.append(f"- {f.display_id}: {f.title}")
                if f.description:
                    parts.append(f"  {f.description[:200]}")

        for f in features:
            req_md = await self._requirement_repo.by_feature_id(f.id)
            if req_md is not None:
                if not parts or not parts[-1].startswith("## Requisitos"):
                    parts.append("\n## Requisitos\n")
                parts.append(f"- {f.display_id}: {req_md[:300]}")
        return "\n".join(parts) if len(parts) > 0 else ""
