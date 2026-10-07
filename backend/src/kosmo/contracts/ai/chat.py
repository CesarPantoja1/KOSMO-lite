from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, cast

from pydantic import BaseModel, model_validator

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ChatHistoryId, ChatMessageId, ChatSessionId, ProjectId


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class DiffCambio:
    before: str
    after: str


@dataclass(frozen=True)
class AppliedChange:
    """Cambio aplicado sobre un artefacto, usado como entrada de las evaluaciones de consistencia."""

    id: str
    section: str
    description: str = ""
    diff: DiffCambio = field(default_factory=lambda: DiffCambio(before="", after=""))
    rationale: str | None = None
    change_class: str = ""


@dataclass(frozen=True)
class SugerenciaCambio:
    id: str
    section: str
    description: str
    diff: DiffCambio
    rationale: str | None = None
    applied: bool = True
    not_applied_reason: str | None = None


@dataclass(frozen=True)
class ModificacionChat:
    applied: bool
    modified_section: str | None = None
    change_description: str | None = None
    modified_document: str | None = None
    before: str | None = None
    after: str | None = None
    clarification_message: str | None = None


@dataclass(frozen=True, init=False)
class MensajeChat:
    id: ChatMessageId
    role: ChatRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    suggested_changes: list[SugerenciaCambio] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    modification: ModificacionChat | None = None
    error: str | None = None

    def __init__(
        self,
        id: ChatMessageId,  # noqa: A002
        role: ChatRole,
        content: str,
        timestamp: datetime | None = None,
        suggested_changes: list[SugerenciaCambio] | None = None,
        modification: ModificacionChat | None = None,
        error: str | None = None,
        *,
        suggested_change: SugerenciaCambio | None = None,
    ) -> None:
        normalized_changes = list(suggested_changes or [])
        if suggested_change is not None and not normalized_changes:
            normalized_changes.append(suggested_change)

        object.__setattr__(self, "id", id)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "timestamp", timestamp or datetime.now(UTC))
        object.__setattr__(self, "suggested_changes", normalized_changes)
        object.__setattr__(self, "modification", modification)
        object.__setattr__(self, "error", error)

    @property
    def suggested_change(self) -> SugerenciaCambio | None:
        """Compatibilidad con consumidores que aún esperan una sola sugerencia."""
        return self.suggested_changes[0] if self.suggested_changes else None


@dataclass(frozen=True)
class HistorialChat:
    id: ChatHistoryId
    project_id: ProjectId
    phase: SpecPhase
    context_id: str | None = None
    session_id: ChatSessionId | None = None
    messages: tuple[MensajeChat, ...] = field(default_factory=tuple)
    has_more: bool = False
    next_cursor: str | None = None

    def add_message(self, message: MensajeChat) -> HistorialChat:
        return HistorialChat(
            id=self.id,
            project_id=self.project_id,
            phase=self.phase,
            context_id=self.context_id,
            session_id=self.session_id,
            messages=(*self.messages, message),
        )

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def last_message(self) -> MensajeChat | None:
        return self.messages[-1] if self.messages else None

    @property
    def composite_key(self) -> str:
        return f"{self.project_id}:{self.phase.value}:{self.context_id or ''}"


@dataclass(frozen=True)
class ChatSession:
    id: ChatSessionId
    project_id: ProjectId
    phase: SpecPhase
    context_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ChatSessionSummary:
    id: ChatSessionId
    phase: SpecPhase
    context_id: str | None
    created_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None
    title: str = ""


class ChatRepository(Protocol):
    async def save_message(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        message: MensajeChat,
        context_id: str | None = None,
        session_id: ChatSessionId | None = None,
    ) -> MensajeChat: ...

    async def get_history(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        context_id: str | None = None,
        limit: int = 200,
        before: str | None = None,
        session_id: ChatSessionId | None = None,
    ) -> HistorialChat | None: ...

    async def create_session(self, session: ChatSession) -> ChatSession: ...

    async def delete_session(self, session_id: ChatSessionId, project_id: ProjectId) -> bool: ...

    async def delete_by_project(self, project_id: ProjectId) -> None: ...

    async def list_sessions(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        *,
        context_id: str | None = None,
        limit: int = 100,
    ) -> list[ChatSessionSummary]: ...


class SugerenciaCambioLLM(BaseModel):
    section: str
    description: str
    diff_before: str
    diff_after: str
    rationale: str | None = None


class RespuestaChatLLM(BaseModel):
    content: str
    change_suggestions: list[SugerenciaCambioLLM] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_suggestion(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        raw_data = cast(dict[str, Any], data)
        if "change_suggestion" not in raw_data:
            return raw_data

        normalized = dict(raw_data)
        legacy = normalized.pop("change_suggestion")
        if "change_suggestions" not in normalized:
            normalized["change_suggestions"] = None if legacy is None else [legacy]
        return normalized

    @property
    def change_suggestion(self) -> SugerenciaCambioLLM | None:
        """Compatibilidad con el contrato singular anterior."""
        return self.change_suggestions[0] if self.change_suggestions else None
