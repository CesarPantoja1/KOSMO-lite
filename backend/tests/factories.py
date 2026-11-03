from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from kosmo.contracts.ai.ai_config import (
    DEFAULT_AI_MODEL,
    DEFAULT_AI_PROVIDER,
    AIProvider,
    UserAiConfig,
)
from kosmo.contracts.auth.secrets import EncryptedSecret
from kosmo.contracts.memory.agent_memory import AgentSession, AgentSessionSummary
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, FeatureId, ProjectId, RequirementId


def a_session_id() -> AgentMemoryId:
    return AgentMemoryId("agm_01KT01FABRICATED01")


def a_project_id() -> ProjectId:
    return ProjectId("prj_01KT01FABRICATED01")


def _a_different_session_id() -> AgentMemoryId:
    from kosmo.domain.agent_memory.session_factory import generate_session_id

    return generate_session_id()


def a_session(
    *,
    session_id: AgentMemoryId | None = None,
    project_id: ProjectId | None = None,
    session_type: str = "generation",
    phase: SpecPhase = SpecPhase.DESCUBRIMIENTO,
    skill_name: str | None = None,
    conversation: list[str] | None = None,
    reasoning_log: list[str] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    current_iteration: int = 0,
    max_iterations: int = 8,
    is_completed: bool = False,
    output_json: str | None = None,
    validation_is_valid: bool = False,
    validation_errors: int = 0,
    validation_error_messages: list[str] | None = None,
    embedding: list[float] | None = None,
    embedding_model: str | None = None,
    total_llm_calls: int = 0,
    user_instructions: str | None = None,
    reflection: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> AgentSession:
    now = datetime.now(UTC)
    return AgentSession(
        session_id=session_id or _a_different_session_id(),
        project_id=project_id or a_project_id(),
        session_type=session_type,
        phase=phase,
        skill_name=skill_name,
        conversation=conversation or [],
        reasoning_log=reasoning_log or [],
        tool_results=tool_results or [],
        current_iteration=current_iteration,
        max_iterations=max_iterations,
        is_completed=is_completed,
        output_json=output_json,
        validation_is_valid=validation_is_valid,
        validation_errors=validation_errors,
        validation_error_messages=validation_error_messages or [],
        embedding=embedding,
        embedding_model=embedding_model,
        total_llm_calls=total_llm_calls,
        user_instructions=user_instructions,
        reflection=reflection,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


def a_session_summary(
    *,
    session_id: AgentMemoryId | None = None,
    project_id: ProjectId | None = None,
    session_type: str = "generation",
    phase: SpecPhase = SpecPhase.DESCUBRIMIENTO,
    skill_name: str | None = None,
    is_completed: bool = False,
    total_llm_calls: int = 0,
    validation_errors: int = 0,
    user_instructions: str | None = None,
    reflection: str | None = None,
    created_at: datetime | None = None,
) -> AgentSessionSummary:
    return AgentSessionSummary(
        session_id=session_id or a_session_id(),
        project_id=project_id or a_project_id(),
        session_type=session_type,
        phase=phase,
        skill_name=skill_name,
        is_completed=is_completed,
        total_llm_calls=total_llm_calls,
        validation_errors=validation_errors,
        user_instructions=user_instructions,
        created_at=created_at or datetime.now(UTC),
        reflection=reflection,
    )


def a_feature_id() -> FeatureId:
    return FeatureId("feat_01KT01FABRICATED01")


def a_requirement_id() -> RequirementId:
    return RequirementId("req_01KT01FABRICATED01")


def a_user_ai_config(
    *,
    user_id: str = "usr_01TEST",
    provider: AIProvider = DEFAULT_AI_PROVIDER,
    model: str = DEFAULT_AI_MODEL,
    encrypted_api_key: EncryptedSecret | bytes | None = None,
    is_custom: bool = False,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> UserAiConfig:
    now = datetime.now(UTC)
    return UserAiConfig(
        user_id=user_id,
        provider=provider,
        model=model,
        encrypted_api_key=encrypted_api_key,
        is_custom=is_custom,
        created_at=created_at or now,
        updated_at=updated_at or now,
    )
