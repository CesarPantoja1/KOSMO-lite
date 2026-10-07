from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.llm.ports import LLMClient, PromptTemplate
from kosmo.contracts.memory.agent_memory import AgentMemoryPort, KnowledgePatternStore
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.pipeline.phase_outputs import ValidationResult
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId
from kosmo.domain.agent_memory.session_factory import create_session

_log = structlog.get_logger(__name__)


class SessionRecorder:
    """Persiste sesiones del agente y encola la reflexion post-sesion via outbox."""

    def __init__(
        self,
        *,
        memory: AgentMemoryPort | None = None,
        pattern_store: KnowledgePatternStore | None = None,
        embedder: Any = None,
        llm_client: LLMClient | None = None,
        outbox: OutboxPort | None = None,
        max_iterations: int = 8,
        consolidation_threshold: int = 5,
    ) -> None:
        self._memory = memory
        self._pattern_store = pattern_store
        self._embedder: Any = embedder
        self._llm_client = llm_client
        self._outbox = outbox
        self._max_iterations = max_iterations
        self._consolidation_threshold = consolidation_threshold

    async def record(
        self,
        *,
        project_id: ProjectId,
        phase: SpecPhase,
        session_type: str,
        skill_name: str | None,
        current_iteration: int,
        output: Any,
        validation: ValidationResult,
        user_instructions: str | None,
        conversation: list[str] | None = None,
        reasoning_log: list[str] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        is_completed: bool = True,
    ) -> None:
        if self._memory is None:
            return

        _log.info("agent.saving_session", project_id=str(project_id), phase=phase.value)

        output_json = _serialize_output(output)

        embedding: list[float] | None = None
        if self._embedder is not None and output is not None:
            text = self._embedder.text_for_embedding(output, validation.errors)
            embedding = await self._embedder.embed(text)

        session = create_session(
            project_id=project_id,
            session_type=session_type,
            phase=phase,
            skill_name=skill_name,
            max_iterations=self._max_iterations,
            conversation=conversation or [],
            reasoning_log=reasoning_log or [],
            tool_results=tool_results or [],
            current_iteration=current_iteration,
            is_completed=is_completed,
            output_json=output_json,
            validation_is_valid=validation.is_valid,
            validation_errors=len(validation.errors),
            validation_error_messages=validation.errors[:10],
            total_llm_calls=current_iteration,
            user_instructions=user_instructions,
            embedding=embedding,
            embedding_model=self._embedder.model_name if self._embedder else None,
            reflection=None,
        )

        await self._memory.save_session(session)
        _log.info("agent.session_saved")

        if self._outbox is not None:
            user_id = current_user_id.get()
            payload: dict[str, Any] = {
                "session_id": str(session.session_id),
                "phase": phase.value,
                "session_type": session_type,
                "is_completed": is_completed,
                "current_iteration": current_iteration,
                "validation_is_valid": validation.is_valid,
                "validation_errors": "; ".join(validation.errors[:5]),
            }
            if user_id:
                payload["user_id"] = str(user_id)
            await self._outbox.enqueue(
                "reflect_and_consolidate",
                payload,
            )
        else:
            asyncio.create_task(
                self._supervised_reflect(
                    session_id=session.session_id,
                    phase=phase,
                    session_type=session_type,
                    is_completed=is_completed,
                    current_iteration=current_iteration,
                    validation=validation,
                )
            )

    async def _supervised_reflect(
        self,
        *,
        session_id: AgentMemoryId,
        phase: SpecPhase,
        session_type: str,
        is_completed: bool,
        current_iteration: int,
        validation: ValidationResult,
    ) -> None:
        """Fallback sin outbox: la reflexion fallida se registra, nunca se pierde en silencio."""
        try:
            await self.reflect_and_consolidate(
                session_id=session_id,
                phase=phase,
                session_type=session_type,
                is_completed=is_completed,
                current_iteration=current_iteration,
                validation=validation,
            )
        except Exception:
            _log.warning(
                "agent.reflection_fallback_failed",
                session_id=str(session_id),
                phase=phase.value,
                exc_info=True,
            )

    async def reflect_and_consolidate(
        self,
        *,
        session_id: AgentMemoryId,
        phase: SpecPhase,
        session_type: str,
        is_completed: bool,
        current_iteration: int,
        validation: ValidationResult,
    ) -> None:
        if self._memory is None:
            return

        clean_session = is_completed and validation.is_valid and current_iteration <= 1
        if clean_session:
            reflection: str | None = None
        else:
            reflection = await self._generate_reflection(
                phase=phase,
                session_type=session_type,
                is_completed=is_completed,
                current_iteration=current_iteration,
                validation=validation,
            )

        if reflection:
            await self._memory.update_reflection(session_id, reflection)

        if is_completed and self._pattern_store is not None:
            counts = await self._memory.count_completed_by_phase()
            for _phase, count in counts.items():
                if count > 0 and count % self._consolidation_threshold == 0:
                    from kosmo.application.knowledge import ConsolidateInput, ConsolidateKnowledgePatterns

                    uc = ConsolidateKnowledgePatterns(
                        memory=self._memory,
                        pattern_store=self._pattern_store,
                        llm_client=self._llm_client,  # type: ignore[arg-type]
                    )
                    await uc.execute(ConsolidateInput(sessions_limit=min(count * 2, 100)))

    async def _generate_reflection(
        self,
        *,
        phase: SpecPhase,
        session_type: str,
        is_completed: bool,
        current_iteration: int,
        validation: ValidationResult,
    ) -> str | None:
        if self._llm_client is None:
            return None

        status = "completada exitosamente" if is_completed else "fallida"
        errors_text = "; ".join(validation.errors[:5]) if validation.errors else "ninguno"

        prompt = PromptTemplate(
            system_prompt=(
                "Eres un analista de calidad que revisa sesiones de un agente de IA. "
                "Genera UNA sola leccion aprendida en espanol, en maximo 2 oraciones, "
                "que ayude al agente a mejorar en futuras sesiones. "
                "Se especifico: menciona que patron evitar o que enfoque usar. "
                "Responde solo con el texto de la leccion, sin prefijos ni markdown."
            ),
            user_prompt=(
                f"Fase: {phase.value}\n"
                f"Tipo: {session_type}\n"
                f"Estado: {status}\n"
                f"Iteraciones usadas: {current_iteration} de {self._max_iterations}\n"
                f"Errores de validacion: {errors_text}\n\n"
                "Genera una leccion aprendida:"
            ),
        )

        try:
            result = await self._llm_client.complete(
                prompt=prompt,
                temperature=0.3,
                max_tokens=150,
            )
            text = result.text.strip()
            if text and len(text) > 10:
                return text
        except Exception:
            _log.warning("agent.reflection_generation_failed", phase=phase.value, exc_info=True)

        return None


def _serialize_output(output: object) -> str | None:
    if output is None:
        return None
    try:
        return output.model_dump_json()  # type: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
    except AttributeError:
        return json.dumps(output, default=str)
