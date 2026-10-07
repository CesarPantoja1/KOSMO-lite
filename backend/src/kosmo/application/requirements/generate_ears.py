from __future__ import annotations

from dataclasses import dataclass

from kosmo.contracts.persistence.persistence import UnitOfWork
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.contracts.pipeline.phase_contexts import EARSPhaseContext
from kosmo.contracts.pipeline.phase_outputs import (
    EARSPhaseOutput,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ears import EARSRequirement
from kosmo.contracts.sdd.errors import LLMInvocationError
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import (
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)


async def _advance_phase(project_repo: ProjectRepository, project_id: ProjectId, phase: SpecPhase) -> None:
    project = await project_repo.by_id(project_id)
    if project is not None and project.current_phase != phase.value:
        import dataclasses

        updated = dataclasses.replace(project, current_phase=phase.value)
        await project_repo.save(updated)


@dataclass(frozen=True)
class GenerateEARSInput:
    project_id: ProjectId
    feature_id: FeatureId


@dataclass(frozen=True)
class GenerateEARSOutput:
    project_id: ProjectId
    feature_id: FeatureId
    requirements: list[EARSRequirement]
    phase_output: EARSPhaseOutput


@dataclass(frozen=True)
class GetRequirementsOutput:
    markdown: str | None
    total: int
    feature_id: FeatureId | None = None
    feature_number: int | None = None


class GenerateEARSUseCase:
    def __init__(self, uow: UnitOfWork, agent: AgentPort) -> None:
        self._uow = uow
        self._agent = agent

    async def execute(self, input_data: GenerateEARSInput) -> GenerateEARSOutput:
        from kosmo.contracts.sdd.errors import (
            DocumentNotFoundError,
            FeatureNotFoundError,
            ProjectNotFoundError,
        )

        async with self._uow as uow:
            project = await uow.projects.by_id(input_data.project_id)
            if project is None:
                raise ProjectNotFoundError(
                    project_id=str(input_data.project_id),
                    instance=f"/api/v1/projects/{input_data.project_id}/features/{input_data.feature_id}/requirements",
                )

            feature = await uow.features.by_id(input_data.feature_id)
            if feature is None or feature.project_id != input_data.project_id:
                raise FeatureNotFoundError(
                    feature_id=str(input_data.feature_id),
                    instance=f"/api/v1/projects/{input_data.project_id}/features/{input_data.feature_id}/requirements",
                )

            discovery_doc = await uow.documents.get_discovery(input_data.project_id)
            if discovery_doc is None:
                raise DocumentNotFoundError(
                    document_type="discovery",
                    instance=f"/api/v1/projects/{input_data.project_id}/features/{input_data.feature_id}/requirements",
                )

            context = EARSPhaseContext(
                discovery_document=discovery_doc,
                feature=feature,
                feature_number=feature.number,
            )

        # La llamada LLM ocurre fuera de transaccion para no retener una conexion del pool
        try:
            phase_output = await self._agent.execute_with_skill(
                skill_name="ears_generate",
                context=context,
                project_id=input_data.project_id,
            )
        except Exception as exc:
            raise LLMInvocationError(
                detail=f"Error al generar requisitos EARS: {exc}",
                instance=f"/api/v1/projects/{input_data.project_id}/features/{input_data.feature_id}/requirements",
            ) from exc

        if not isinstance(phase_output, EARSPhaseOutput):
            raise LLMInvocationError(
                detail="El agente no devolvió un EARSPhaseOutput válido.",
                instance=f"/api/v1/projects/{input_data.project_id}/features/{input_data.feature_id}/requirements",
            )

        # Escritura atomica: requisitos + edges de trazabilidad + avance de fase
        async with self._uow as uow:
            await uow.requirements.save(input_data.feature_id, phase_output.requirements_markdown)

            for r in phase_output.requirements:
                await uow.traceability.add_edge(
                    source_type="feature",
                    source_id=str(input_data.feature_id),
                    target_type="requirement",
                    target_id=str(r.id),
                )

            await _advance_phase(uow.projects, input_data.project_id, SpecPhase.REQUISITOS)

        return GenerateEARSOutput(
            project_id=input_data.project_id,
            feature_id=input_data.feature_id,
            requirements=phase_output.requirements,
            phase_output=phase_output,
        )


class GetRequirementsUseCase:
    def __init__(
        self,
        project_repo: ProjectRepository,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
    ) -> None:
        self._project_repo = project_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo

    async def execute(self, project_id: ProjectId, feature_id: FeatureId) -> GetRequirementsOutput:
        from kosmo.contracts.sdd.errors import FeatureNotFoundError, ProjectNotFoundError, RequirementsNotFoundError

        project = await self._project_repo.by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(project_id),
                instance=f"/api/v1/projects/{project_id}/features/{feature_id}/requirements",
            )

        feature = await self._feature_repo.by_id(feature_id)
        if feature is None or feature.project_id != project_id:
            raise FeatureNotFoundError(
                feature_id=str(feature_id),
                instance=f"/api/v1/projects/{project_id}/features/{feature_id}/requirements",
            )

        markdown = await self._requirement_repo.by_feature_id(feature_id)
        if not markdown or not markdown.strip():
            raise RequirementsNotFoundError(
                feature_id=str(feature_id),
                instance=f"/api/v1/projects/{project_id}/features/{feature_id}/requirements",
            )

        from kosmo.domain.sdd.requirements_markdown import count_requirements

        total = count_requirements(markdown)
        return GetRequirementsOutput(
            markdown=markdown,
            total=total,
            feature_id=feature.id,
            feature_number=feature.number,
        )
