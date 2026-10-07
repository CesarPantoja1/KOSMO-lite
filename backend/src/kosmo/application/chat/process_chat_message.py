from __future__ import annotations

import dataclasses
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from kosmo.application.consistency.trigger_downstream import trigger_downstream_evaluation
from kosmo.contracts.ai.chat import (
    AppliedChange,
    ChatRepository,
    ChatRole,
    MensajeChat,
    ModificacionChat,
    SugerenciaCambio,
)
from kosmo.contracts.ai.consistency import ConsistencyEvaluator, ConsistencyStatus
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import LLMInvocationError, ProjectNotFoundError
from kosmo.contracts.sdd.ids import ChatMessageId, ChatSessionId, ProjectId
from kosmo.contracts.sdd.repositories import (
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.chat_edit_applier import (
    apply_feature_attribute,
    apply_markdown_suggestion,
    check_fragment_terms,
)
from kosmo.domain.sdd.document_converters import (
    document_to_markdown,
    markdown_to_document,
    slugify_spanish,
)
from kosmo.domain.sdd.id_generator import IdGenerator

if TYPE_CHECKING:
    from kosmo.domain.pipeline.skill_registry import SkillRegistry

_MAX_CONTENT_LENGTH = 4000

_log = structlog.get_logger(__name__)

_FEATURE_ATTRIBUTES: dict[str, str] = {
    "titulo": "title",
    "título": "title",
    "descripcion": "description",
    "descripción": "description",
    "origen": "origin",
}


@dataclass(frozen=True)
class ProcessChatMessageInput:
    project_id: ProjectId
    phase: SpecPhase
    content: str
    context: Any
    context_id: str | None = None
    session_id: ChatSessionId | None = None
    instance: str = ""


@dataclass(frozen=True)
class ProcessChatMessageOutput:
    project_id: ProjectId
    message: MensajeChat


@dataclass(frozen=True)
class ChatStreamChunk:
    content: str


class ProcessChatMessageUseCase:
    """Chat conversacional por fase con aplicacion instantanea de sugerencias.

    El agente responde con el nivel de abstraccion de la fase (chat mode) y
    cada sugerencia de cambio se aplica de inmediato y de forma deterministica.
    Las sugerencias se devuelven como cards de visualizacion con su resultado.
    """

    def __init__(
        self,
        chat_repo: ChatRepository,
        agent: AgentPort,
        *,
        skill_registry: SkillRegistry | None = None,
        project_repo: ProjectRepository | None = None,
        document_repo: DocumentRepository | None = None,
        feature_repo: FeatureRepository | None = None,
        requirement_repo: RequirementRepository | None = None,
        outbox: OutboxPort | None = None,
        consistency_evaluator: ConsistencyEvaluator | None = None,
    ) -> None:
        self._chat_repo = chat_repo
        self._agent = agent
        self._skill_registry = skill_registry
        self._project_repo = project_repo
        self._document_repo = document_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._outbox = outbox
        self._consistency_evaluator = consistency_evaluator

    async def execute(self, input_data: ProcessChatMessageInput) -> ProcessChatMessageOutput:
        total_start = time.monotonic()
        content = self._validate_content(input_data)
        messages, skill_name = await self._prepare(input_data, content)

        llm_start = time.monotonic()
        try:
            assistant_msg = await self._agent.execute_conversation(
                skill_name=skill_name,
                messages=messages,
                context=input_data.context,
                project_id=input_data.project_id,
            )
        except ValueError:
            raise
        except Exception as exc:
            _log.error("chat.llm_error", exc_info=True)
            await self._save_error_message(input_data)
            raise LLMInvocationError(
                detail="Error interno al procesar el mensaje. Reintenta más tarde.",
                instance=input_data.instance,
            ) from exc
        llm_ms = self._elapsed_ms(llm_start)

        apply_start = time.monotonic()
        output = await self._finalize(input_data, assistant_msg)
        apply_ms = self._elapsed_ms(apply_start)

        _log.info(
            "chat.stage_times",
            phase=input_data.phase.value,
            llm_ms=llm_ms,
            apply_ms=apply_ms,
            total_ms=self._elapsed_ms(total_start),
        )
        return output

    async def execute_stream(
        self,
        input_data: ProcessChatMessageInput,
    ) -> AsyncIterator[ChatStreamChunk | ProcessChatMessageOutput]:
        """Streaming real: emite fragmentos conforme el LLM genera y aplica al final.

        Eventos: ChatStreamChunk por delta de texto y ProcessChatMessageOutput al
        terminar (con las cards aplicadas). La persistencia del mensaje ocurre
        despues del ultimo evento, igual que en execute().
        """
        total_start = time.monotonic()
        content = self._validate_content(input_data)
        messages, skill_name = await self._prepare(input_data, content)

        llm_start = time.monotonic()
        final_msg: MensajeChat | None = None
        try:
            async for item in self._agent.execute_conversation_stream(
                skill_name=skill_name,
                messages=messages,
                context=input_data.context,
                project_id=input_data.project_id,
            ):
                if isinstance(item, str):
                    yield ChatStreamChunk(content=item)
                else:
                    final_msg = item
        except ValueError:
            raise
        except Exception as exc:
            _log.error("chat.llm_error", exc_info=True)
            await self._save_error_message(input_data)
            raise LLMInvocationError(
                detail="Error interno al procesar el mensaje. Reintenta más tarde.",
                instance=input_data.instance,
            ) from exc
        llm_ms = self._elapsed_ms(llm_start)

        if final_msg is None:
            final_msg = MensajeChat(
                id=ChatMessageId(IdGenerator.generate("chat_message")),
                role=ChatRole.ASSISTANT,
                content="No se pudo generar una respuesta. Intenta nuevamente.",
            )

        apply_start = time.monotonic()
        output = await self._finalize(input_data, final_msg)
        apply_ms = self._elapsed_ms(apply_start)

        _log.info(
            "chat.stage_times",
            phase=input_data.phase.value,
            llm_ms=llm_ms,
            apply_ms=apply_ms,
            total_ms=self._elapsed_ms(total_start),
        )
        yield output

    async def _prepare(
        self,
        input_data: ProcessChatMessageInput,
        content: str,
    ) -> tuple[list[MensajeChat], str]:
        if self._project_repo is not None:
            project = await self._project_repo.by_id(input_data.project_id)
            if project is None:
                raise ProjectNotFoundError(
                    project_id=str(input_data.project_id),
                    instance=input_data.instance,
                )

        skill_name = self._resolve_chat_skill(input_data.phase)

        history = await self._chat_repo.get_history(
            project_id=input_data.project_id,
            phase=input_data.phase,
            context_id=input_data.context_id,
            session_id=input_data.session_id,
        )
        prior_messages = list(history.messages) if history else []

        user_msg = MensajeChat(
            id=ChatMessageId(IdGenerator.generate("chat_message")),
            role=ChatRole.USER,
            content=content,
        )
        await self._chat_repo.save_message(
            project_id=input_data.project_id,
            phase=input_data.phase,
            message=user_msg,
            context_id=input_data.context_id,
            session_id=input_data.session_id,
        )

        return prior_messages + [user_msg], skill_name

    async def _finalize(
        self,
        input_data: ProcessChatMessageInput,
        assistant_msg: MensajeChat,
    ) -> ProcessChatMessageOutput:
        cards = await self._apply_suggestions(
            phase=input_data.phase,
            project_id=input_data.project_id,
            context=input_data.context,
            suggestions=list(assistant_msg.suggested_changes),
        )
        modification = self._build_modification(cards)

        applied_cards = [c for c in cards if c.applied]
        if applied_cards:
            await self._trigger_downstream_consistency(input_data, applied_cards)

        final_msg = MensajeChat(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            suggested_changes=cards,
            modification=modification,
        )

        await self._chat_repo.save_message(
            project_id=input_data.project_id,
            phase=input_data.phase,
            message=final_msg,
            context_id=input_data.context_id,
            session_id=input_data.session_id,
        )

        return ProcessChatMessageOutput(
            project_id=input_data.project_id,
            message=final_msg,
        )

    async def _save_error_message(self, input_data: ProcessChatMessageInput) -> None:
        error_msg = MensajeChat(
            id=ChatMessageId(IdGenerator.generate("chat_message")),
            role=ChatRole.ASSISTANT,
            content="No se pudo procesar la solicitud. Intenta nuevamente.",
        )
        await self._chat_repo.save_message(
            project_id=input_data.project_id,
            phase=input_data.phase,
            message=error_msg,
            context_id=input_data.context_id,
            session_id=input_data.session_id,
        )

    async def _apply_suggestions(
        self,
        *,
        phase: SpecPhase,
        project_id: ProjectId,
        context: Any,
        suggestions: list[SugerenciaCambio],
    ) -> list[SugerenciaCambio]:
        guard_reason = await self._check_upstream_guard(phase, project_id, suggestions)
        if guard_reason is not None:
            return [
                SugerenciaCambio(
                    id=sc.id,
                    section=sc.section,
                    description=sc.description,
                    diff=sc.diff,
                    rationale=sc.rationale,
                    applied=False,
                    not_applied_reason=guard_reason,
                )
                for sc in suggestions
            ]

        applied: list[SugerenciaCambio] = []
        for sc in suggestions:
            reason = await self._apply_suggestion(phase, project_id, context, sc)
            applied.append(
                SugerenciaCambio(
                    id=sc.id,
                    section=sc.section,
                    description=sc.description,
                    diff=sc.diff,
                    rationale=sc.rationale,
                    applied=reason is None,
                    not_applied_reason=reason,
                )
            )
        return applied

    async def _check_upstream_guard(
        self,
        phase: SpecPhase,
        project_id: ProjectId,
        suggestions: list[SugerenciaCambio],
    ) -> str | None:
        """Guarda de trazabilidad a la izquierda: rechaza cambios de chat que
        contradigan o amplíen lo declarado en los documentos upstream."""
        if self._consistency_evaluator is None or not suggestions:
            return None

        pairs: list[tuple[SpecPhase, SpecPhase, str]] = []
        if phase == SpecPhase.CARACTERISTICAS:
            pairs.append((phase, SpecPhase.DESCUBRIMIENTO, "el documento de Descubrimiento"))
        elif phase == SpecPhase.REQUISITOS:
            pairs.append((phase, SpecPhase.CARACTERISTICAS, "la característica padre"))
            pairs.append((phase, SpecPhase.DESCUBRIMIENTO, "el documento de Descubrimiento"))
        else:
            return None

        changes = [
            AppliedChange(
                id=sc.id,
                section=sc.section,
                description=sc.description,
                diff=sc.diff,
            )
            for sc in suggestions
        ]

        for source_phase, target_phase, doc_label in pairs:
            try:
                result = await self._consistency_evaluator.evaluate(
                    source_phase=source_phase,
                    target_phase=target_phase,
                    project_id=project_id,
                    applied_changes=changes,
                )
            except Exception:
                _log.warning(
                    "chat.upstream_guard_failed",
                    phase=phase.value,
                    target=target_phase.value,
                    exc_info=True,
                )
                continue

            if result.status != ConsistencyStatus.ANALIZADO_CON_IMPACTO:
                continue

            section = result.actions[0].suggested_field if result.actions else ""
            section_note = f" (sección: {section})" if section else ""
            return (
                f"El cambio contradice o amplía lo declarado en {doc_label}{section_note}. "
                f"Modifica primero {doc_label} y vuelve a pedir el cambio aquí."
            )

        return None

    async def _apply_suggestion(
        self,
        phase: SpecPhase,
        project_id: ProjectId,
        context: Any,
        sc: SugerenciaCambio,
    ) -> str | None:
        if phase == SpecPhase.DESCUBRIMIENTO:
            return await self._apply_discovery_suggestion(project_id, context, sc)
        if phase == SpecPhase.CARACTERISTICAS:
            return await self._apply_feature_suggestion(context, sc)
        if phase == SpecPhase.REQUISITOS:
            return await self._apply_requirement_suggestion(context, sc)
        return f"Fase no soportada para cambios: {phase.value}"

    async def _apply_discovery_suggestion(
        self,
        project_id: ProjectId,
        context: Any,  # noqa: ARG002  # el contenido se lee del repo: siempre el estado mas reciente
        sc: SugerenciaCambio,
    ) -> str | None:
        if self._document_repo is None:
            return "Repositorio de documentos no configurado."

        terms = check_fragment_terms(SpecPhase.DESCUBRIMIENTO, sc.diff.after)
        if terms:
            return "El cambio contiene terminología prohibida: " + ", ".join(sorted(set(terms))[:5]) + "."

        document = await self._document_repo.get_discovery(project_id)
        if document is None:
            return "No existe el documento de descubrimiento."

        current_md = document_to_markdown(document)
        new_md = apply_markdown_suggestion(
            current_md,
            section=sc.section or None,
            diff_before=sc.diff.before,
            diff_after=sc.diff.after,
        )
        if new_md is None or new_md == current_md:
            return "No se encontró el fragmento a reemplazar; el documento pudo haber cambiado."

        await self._document_repo.save_discovery(project_id, markdown_to_document(new_md))
        return None

    async def _apply_feature_suggestion(self, context: Any, sc: SugerenciaCambio) -> str | None:
        if self._feature_repo is None:
            return "Repositorio de características no configurado."

        attr = _FEATURE_ATTRIBUTES.get(sc.section.strip().lower())
        if attr is None:
            return f"Atributo desconocido: {sc.section}."

        terms = check_fragment_terms(SpecPhase.CARACTERISTICAS, sc.diff.after)
        if terms:
            return "El cambio contiene terminología prohibida: " + ", ".join(sorted(set(terms))[:5]) + "."

        feature = await self._feature_repo.by_id(context.feature.id)
        if feature is None:
            return "La característica ya no existe."

        current = str(getattr(feature, attr))
        new_value = apply_feature_attribute(current, diff_before=sc.diff.before, diff_after=sc.diff.after)
        if new_value is None:
            return "No se encontró el fragmento a reemplazar en el atributo."

        if attr == "title":
            updated = dataclasses.replace(
                feature,
                title=new_value,
                slug=slugify_spanish(new_value) or feature.slug,
            )
        else:
            updated = dataclasses.replace(feature, **{attr: new_value})
        await self._feature_repo.save(updated)
        return None

    async def _apply_requirement_suggestion(self, context: Any, sc: SugerenciaCambio) -> str | None:
        if self._requirement_repo is None:
            return "Repositorio de requisitos no configurado."

        current_md = await self._requirement_repo.by_feature_id(context.feature.id)
        if not current_md:
            return "No hay markdown de requisitos para aplicar el cambio."

        new_md = apply_markdown_suggestion(
            current_md,
            section=None,
            diff_before=sc.diff.before,
            diff_after=sc.diff.after,
        )
        if new_md is None or new_md == current_md:
            return "No se encontró el fragmento a reemplazar; el requisito pudo haber cambiado."

        await self._requirement_repo.save(context.feature.id, new_md)
        return None

    async def _trigger_downstream_consistency(
        self,
        input_data: ProcessChatMessageInput,
        applied_cards: list[SugerenciaCambio],
    ) -> None:
        await trigger_downstream_evaluation(
            self._outbox,
            project_id=input_data.project_id,
            source_phase=input_data.phase,
            changes=[
                {
                    "section": c.section,
                    "description": c.description,
                    "before": c.diff.before,
                    "after": c.diff.after,
                }
                for c in applied_cards
            ],
        )

    @staticmethod
    def _build_modification(cards: list[SugerenciaCambio]) -> ModificacionChat | None:
        if not cards:
            return None

        applied = [c for c in cards if c.applied]
        if not applied:
            reasons = [c.not_applied_reason for c in cards if c.not_applied_reason]
            return ModificacionChat(applied=False, clarification_message="; ".join(reasons))

        sections = ", ".join(sorted({c.section for c in applied if c.section}))
        return ModificacionChat(
            applied=True,
            modified_section=sections or None,
            change_description="Se aplicaron los cambios sugeridos.",
        )

    @staticmethod
    def _validate_content(input_data: ProcessChatMessageInput) -> str:
        content = input_data.content.strip()
        if not content:
            raise ValueError("El mensaje no puede estar vacío.")
        if len(content) > _MAX_CONTENT_LENGTH:
            raise ValueError(f"El mensaje no puede exceder {_MAX_CONTENT_LENGTH} caracteres.")
        return content

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _resolve_chat_skill(self, phase: SpecPhase) -> str:
        if self._skill_registry is not None:
            return self._skill_registry.resolve_chat_skill(phase)
        raise ValueError(f"No hay SkillRegistry configurado para resolver el skill de chat de la fase {phase.value}")
