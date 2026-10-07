from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId


@dataclass(frozen=True)
class KnowledgePattern:
    pattern_id: str
    phase: SpecPhase
    pattern_text: str
    support_count: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AgentSession:
    session_id: AgentMemoryId
    project_id: ProjectId
    session_type: str  # generation | refinement
    phase: SpecPhase
    skill_name: str | None

    conversation: list[str] = field(default_factory=list[str])
    reasoning_log: list[str] = field(default_factory=list[str])
    tool_results: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    validation_error_messages: list[str] = field(default_factory=list[str])

    current_iteration: int = 0
    max_iterations: int = 8
    is_completed: bool = False

    output_json: str | None = None
    validation_is_valid: bool = False
    validation_errors: int = 0
    total_llm_calls: int = 0

    user_instructions: str | None = None

    embedding: list[float] | None = None
    embedding_model: str | None = None

    reflection: str | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class AgentSessionSummary:
    session_id: AgentMemoryId
    project_id: ProjectId
    session_type: str
    phase: SpecPhase
    skill_name: str | None
    is_completed: bool
    total_llm_calls: int
    validation_errors: int
    user_instructions: str | None
    created_at: datetime
    reflection: str | None = None


@dataclass(frozen=True)
class ProjectMemoryContext:
    project_id: ProjectId
    latest_sessions: dict[str, AgentSessionSummary]
    total_sessions: int
    common_validation_errors: list[str] = field(default_factory=list[str])
    recent_reflections: list[str] = field(default_factory=list[str])


class AgentMemoryPort(Protocol):
    async def save_session(self, session: AgentSession) -> None: ...

    async def update_reflection(self, session_id: AgentMemoryId, reflection: str) -> None: ...

    async def load_session(self, session_id: AgentMemoryId) -> AgentSession | None: ...

    async def list_sessions(
        self,
        project_id: ProjectId,
        *,
        phase: SpecPhase | None = None,
    ) -> list[AgentSessionSummary]: ...

    async def get_latest_session(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
    ) -> AgentSession | None: ...

    async def get_project_context(self, project_id: ProjectId) -> ProjectMemoryContext: ...

    async def get_similar_sessions(
        self,
        embedding: list[float],
        *,
        limit: int = 5,
        exclude_project_id: ProjectId | None = None,
        model: str | None = None,
    ) -> list[AgentSessionSummary]: ...

    async def list_recent_sessions_global(
        self,
        *,
        limit: int = 50,
    ) -> list[AgentSessionSummary]: ...

    async def count_completed_by_phase(
        self,
        *,
        since_session_id: AgentMemoryId | None = None,
        project_id: ProjectId | None = None,
    ) -> dict[str, int]: ...

    async def delete_by_project(self, project_id: ProjectId) -> None: ...

    async def purge_stale_sessions(
        self,
        *,
        older_than_days: int = 7,
        incomplete_only: bool = True,
    ) -> int: ...


class KnowledgePatternStore(Protocol):
    async def replace_patterns(
        self,
        phase: SpecPhase,
        patterns: list[KnowledgePattern],
    ) -> None: ...

    async def list_patterns(
        self,
        phase: SpecPhase | None = None,
        *,
        limit: int = 10,
    ) -> list[KnowledgePattern]: ...


class AgentMemoryError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
