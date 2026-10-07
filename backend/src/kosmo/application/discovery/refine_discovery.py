from __future__ import annotations

from dataclasses import dataclass

from kosmo.application.consistency.trigger_downstream import trigger_downstream_evaluation
from kosmo.application.pipeline.context_builder import ContextBuilder
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.contracts.pipeline.phase_outputs import DiscoveryPhaseOutput
from kosmo.contracts.sdd.document import RichTextDocument, SpecPhase
from kosmo.contracts.sdd.errors import LLMInvocationError
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.contracts.sdd.repositories import DocumentRepository, ProjectRepository
from kosmo.domain.sdd.document_converters import document_to_markdown


@dataclass(frozen=True)
class RefineDiscoveryInput:
    project_id: ProjectId
    instructions: str


@dataclass(frozen=True)
class RefineDiscoveryOutput:
    project_id: ProjectId
    document: RichTextDocument
    phase_output: DiscoveryPhaseOutput


class RefineDiscoveryUseCase:
    """Caso de uso: refina un documento de descubrimiento existente mediante IA.

    Orquesta el refinamiento:
    1. Valida que las instrucciones no superen los 500 caracteres.
    2. Construye el contexto de fase mediante el ContextBuilder (incluye el documento actual).
    3. Delega al KOSMOAgent el refinamiento usando la fase DESCUBRIMIENTO.
       El pipeline debe estar configurado para inyectar DiscoveryRefineMode en esta fase.
    4. Persiste el documento refinado en el DocumentRepository.
    5. Gestiona los fallos del servicio de IA, conservando el original.
    """

    def __init__(
        self,
        project_repo: ProjectRepository,
        document_repo: DocumentRepository,
        context_builder: ContextBuilder,
        agent: AgentPort,
        outbox: OutboxPort | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._document_repo = document_repo
        self._context_builder = context_builder
        self._agent = agent
        self._outbox = outbox

    async def execute(self, input_data: RefineDiscoveryInput) -> RefineDiscoveryOutput:
        from kosmo.contracts.sdd.errors import ProjectNotFoundError

        if len(input_data.instructions) > 500:
            raise ValueError("Las instrucciones de refinamiento no pueden exceder los 500 caracteres.")

        project = await self._project_repo.by_id(input_data.project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(input_data.project_id),
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/refine",
            )

        context = await self._context_builder.build_discovery_refine_context(
            project_id=input_data.project_id,
            user_instructions=input_data.instructions,
        )

        try:
            phase_output = await self._agent.execute_with_skill(
                skill_name="discovery_refine",
                context=context,
                project_id=input_data.project_id,
                user_instructions=input_data.instructions,
            )
        except Exception as exc:
            raise LLMInvocationError(
                detail=f"Error al refinar el documento de descubrimiento: {exc}",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/refine",
            ) from exc

        if not isinstance(phase_output, DiscoveryPhaseOutput):  # type: ignore[reportUnknownMemberType]
            raise LLMInvocationError(
                detail="El agente no devolvió un DiscoveryPhaseOutput válido.",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/refine",
            )

        # En refinamiento el usuario decide la estructura: solo exigimos nivel de
        # negocio y que el documento no quede vacío (no se persiste basura).
        validation = phase_output.validation_result
        if not validation.is_valid or phase_output.discovery_document.section_count == 0:
            detail = "; ".join(validation.errors) or "El documento refinado está vacío."
            raise LLMInvocationError(
                detail=f"El descubrimiento refinado no se mantiene a nivel de negocio: {detail}",
                instance=f"/api/v1/projects/{input_data.project_id}/discovery/refine",
            )

        document = await self._document_repo.save_discovery(
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
                    "description": "Refinamiento con IA del documento de Descubrimiento",
                    "before": "",
                    "after": document_to_markdown(document),
                }
            ],
        )

        return RefineDiscoveryOutput(
            project_id=input_data.project_id,
            document=document,
            phase_output=phase_output,
        )
