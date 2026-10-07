from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from kosmo.contracts.memory.agent_memory import AgentSession
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId
from kosmo.domain.sdd.id_generator import IdGenerator


def generate_session_id() -> AgentMemoryId:
    return AgentMemoryId(IdGenerator.generate("agent_memory"))


def create_session(
    project_id: ProjectId,
    session_type: str,
    phase: SpecPhase,
    *,
    skill_name: str | None = None,
    max_iterations: int = 8,
    conversation: list[str] | None = None,
    reasoning_log: list[str] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    current_iteration: int = 0,
    is_completed: bool = False,
    output_json: str | None = None,
    validation_is_valid: bool = False,
    validation_errors: int = 0,
    total_llm_calls: int = 0,
    user_instructions: str | None = None,
    embedding: list[float] | None = None,
    reflection: str | None = None,
    validation_error_messages: list[str] | None = None,
    embedding_model: str | None = None,
    now: datetime | None = None,
) -> AgentSession:
    timestamp = now if now is not None else datetime.now(UTC)
    return AgentSession(
        session_id=generate_session_id(),
        project_id=project_id,
        session_type=session_type,
        phase=phase,
        skill_name=skill_name,
        conversation=conversation or [],
        reasoning_log=reasoning_log or [],
        tool_results=tool_results or [],
        validation_error_messages=validation_error_messages or [],
        current_iteration=current_iteration,
        max_iterations=max_iterations,
        is_completed=is_completed,
        output_json=output_json,
        validation_is_valid=validation_is_valid,
        validation_errors=validation_errors,
        total_llm_calls=total_llm_calls,
        user_instructions=user_instructions,
        embedding=embedding,
        embedding_model=embedding_model,
        reflection=reflection,
        created_at=timestamp,
        updated_at=timestamp,
    )
