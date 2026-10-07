from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.ai.chat import (
    ChatRepository,
    ChatRole,
    ChatSession,
    ChatSessionSummary,
    DiffCambio,
    HistorialChat,
    MensajeChat,
    SugerenciaCambio,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import (
    ChatHistoryId,
    ChatMessageId,
    ChatSessionId,
    ProjectId,
)
from kosmo.domain.sdd.session_title import derive_session_title
from kosmo.infrastructure.persistence.postgres.models import (
    ChatMessageModel,
    ChatSessionModel,
)


class SqlAlchemyChatRepository(ChatRepository):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        if session_factory is None and session is None:
            raise ValueError("Se requiere session_factory o session")
        self._session_factory = session_factory
        self._session = session

    @asynccontextmanager
    async def _session_ctx(self) -> AsyncGenerator[AsyncSession]:
        if self._session is not None:
            yield self._session
            return
        assert self._session_factory is not None
        async with self._session_factory() as session:
            yield session

    async def _commit(self, session: AsyncSession) -> None:
        if self._session is None:
            await session.commit()

    async def save_message(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        message: MensajeChat,
        context_id: str | None = None,
        session_id: ChatSessionId | None = None,
    ) -> MensajeChat:
        suggested_changes: list[dict[str, Any]] | None = None
        if message.suggested_changes:
            suggested_changes = [
                {
                    "id": sc.id,
                    "section": sc.section,
                    "description": sc.description,
                    "diff": {"before": sc.diff.before, "after": sc.diff.after},
                    "rationale": sc.rationale,
                    "applied": sc.applied,
                    "not_applied_reason": sc.not_applied_reason,
                }
                for sc in message.suggested_changes
            ]

        model = ChatMessageModel(
            id=str(message.id),
            project_id=str(project_id),
            phase=phase.value,
            context_id=context_id,
            session_id=str(session_id) if session_id is not None else None,
            role=message.role.value,
            content=message.content,
            suggested_change=suggested_changes,
            error=message.error,
        )
        async with self._session_ctx() as session:
            session.add(model)
            await self._commit(session)
        return message

    async def get_history(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        context_id: str | None = None,
        limit: int = 200,
        before: str | None = None,
        session_id: ChatSessionId | None = None,
    ) -> HistorialChat | None:
        stmt = select(ChatMessageModel).where(
            ChatMessageModel.project_id == str(project_id),
            ChatMessageModel.phase == phase.value,
        )
        if session_id is not None:
            stmt = stmt.where(ChatMessageModel.session_id == str(session_id))
        elif context_id:
            stmt = stmt.where(ChatMessageModel.context_id == context_id)
        else:
            stmt = stmt.where(ChatMessageModel.context_id.is_(None))

        if before:
            from datetime import datetime as _datetime

            cursor_dt = _datetime.fromisoformat(before)
            stmt = stmt.where(ChatMessageModel.created_at < cursor_dt)

        stmt = stmt.order_by(ChatMessageModel.created_at.desc()).limit(limit)

        async with self._session_ctx() as session:
            result = await session.execute(stmt)
            models = list(result.scalars().all())

        if not models:
            return None

        models.reverse()
        messages = tuple(_model_to_message(m) for m in models)

        history_id = self._compose_history_id(project_id, phase, context_id)

        has_more = len(models) == limit
        next_cursor = models[0].created_at.isoformat() if has_more else None

        return HistorialChat(
            id=ChatHistoryId(history_id),
            project_id=project_id,
            phase=phase,
            context_id=context_id,
            session_id=session_id,
            messages=messages,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    async def create_session(self, session: ChatSession) -> ChatSession:
        model = ChatSessionModel(
            id=str(session.id),
            project_id=str(session.project_id),
            phase=session.phase.value,
            context_id=session.context_id,
        )
        async with self._session_ctx() as db:
            db.add(model)
            await self._commit(db)
        return session

    async def list_sessions(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
        *,
        context_id: str | None = None,
        limit: int = 100,
    ) -> list[ChatSessionSummary]:
        stmt = (
            select(
                ChatSessionModel,
                func.count(ChatMessageModel.id),
                func.max(ChatMessageModel.created_at),
            )
            .outerjoin(ChatMessageModel, ChatMessageModel.session_id == ChatSessionModel.id)
            .where(
                ChatSessionModel.project_id == str(project_id),
                ChatSessionModel.phase == phase.value,
            )
            .group_by(ChatSessionModel.id)
            .order_by(ChatSessionModel.created_at.desc())
            .limit(limit)
        )
        if context_id is not None:
            stmt = stmt.where(ChatSessionModel.context_id == context_id)

        async with self._session_ctx() as db:
            result = await db.execute(stmt)
            rows = result.all()

        first_messages = await self._first_user_messages([str(row[0].id) for row in rows])

        return [
            ChatSessionSummary(
                id=ChatSessionId(model.id),
                phase=SpecPhase(model.phase),
                context_id=model.context_id,
                created_at=model.created_at,
                message_count=int(count or 0),
                last_message_at=last_at,
                title=derive_session_title(first_messages.get(str(model.id), "")),
            )
            for model, count, last_at in rows
        ]

    async def _first_user_messages(self, session_ids: list[str]) -> dict[str, str]:
        """Primer mensaje del usuario (más antiguo) por sesión, para derivar el título."""
        if not session_ids:
            return {}
        stmt = (
            select(ChatMessageModel.session_id, ChatMessageModel.content)
            .distinct(ChatMessageModel.session_id)
            .where(
                ChatMessageModel.session_id.in_(session_ids),
                ChatMessageModel.role == ChatRole.USER.value,
            )
            .order_by(ChatMessageModel.session_id, ChatMessageModel.created_at.asc())
        )
        async with self._session_ctx() as db:
            result = await db.execute(stmt)
            rows = result.all()

        return {sid: content or "" for sid, content in rows if sid is not None}

    async def delete_session(self, session_id: ChatSessionId, project_id: ProjectId) -> bool:
        from sqlalchemy import delete

        async with self._session_ctx() as db:
            result = cast(
                CursorResult[Any],
                await db.execute(
                    delete(ChatSessionModel).where(
                        ChatSessionModel.id == str(session_id),
                        ChatSessionModel.project_id == str(project_id),
                    )
                ),
            )
            deleted = bool(result.rowcount > 0)
            if deleted:
                await db.execute(
                    delete(ChatMessageModel).where(
                        ChatMessageModel.session_id == str(session_id),
                        ChatMessageModel.project_id == str(project_id),
                    )
                )
            await self._commit(db)
            return deleted

    async def delete_by_project(self, project_id: ProjectId) -> None:
        from sqlalchemy import delete

        async with self._session_ctx() as db:
            await db.execute(delete(ChatMessageModel).where(ChatMessageModel.project_id == str(project_id)))
            await db.execute(delete(ChatSessionModel).where(ChatSessionModel.project_id == str(project_id)))
            await self._commit(db)

    @staticmethod
    def _compose_history_id(project_id: ProjectId, phase: SpecPhase, context_id: str | None) -> str:
        return f"{project_id}:{phase.value}:{context_id or ''}"


def _model_to_message(model: ChatMessageModel) -> MensajeChat:
    from typing import Any as TypingAny

    suggested_changes: list[SugerenciaCambio] = []
    raw: TypingAny = model.suggested_change
    if raw is not None:
        items: list[TypingAny] = raw if isinstance(raw, list) else [raw]  # type: ignore[reportUnknownVariableType]
        for item in items:
            diff_dict: dict[str, str] = item.get("diff", {})
            suggested_changes.append(
                SugerenciaCambio(
                    id=item["id"],
                    section=item.get("section", ""),
                    description=item.get("description", ""),
                    diff=DiffCambio(
                        before=diff_dict.get("before", ""),
                        after=diff_dict.get("after", ""),
                    ),
                    rationale=item.get("rationale"),
                )
            )

    return MensajeChat(
        id=ChatMessageId(model.id),
        role=ChatRole(model.role),
        content=model.content,
        timestamp=model.created_at if model.created_at else datetime.now(UTC),
        suggested_changes=suggested_changes,
        error=model.error,
    )
