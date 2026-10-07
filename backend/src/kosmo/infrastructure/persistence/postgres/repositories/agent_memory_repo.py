from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.memory.agent_memory import (
    AgentMemoryPort,
    AgentSession,
    AgentSessionSummary,
    KnowledgePattern,
    ProjectMemoryContext,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId
from kosmo.infrastructure.persistence.postgres.models import AgentSessionModel, KnowledgePatternModel


class SqlAlchemyAgentSessionStore(AgentMemoryPort):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_session(self, session: AgentSession) -> None:
        async with self._session_factory() as db:
            stmt = (
                pg_insert(AgentSessionModel)
                .values(
                    id=session.session_id,
                    project_id=session.project_id,
                    session_type=session.session_type,
                    phase=session.phase.value,
                    skill_name=session.skill_name,
                    conversation=list(session.conversation),
                    reasoning_log=list(session.reasoning_log),
                    tool_results=list(session.tool_results),
                    current_iteration=session.current_iteration,
                    max_iterations=session.max_iterations,
                    is_completed=session.is_completed,
                    output_json=_json_to_dict(session.output_json),
                    validation_is_valid=session.validation_is_valid,
                    validation_errors=session.validation_errors,
                    validation_error_messages=list(session.validation_error_messages),
                    total_llm_calls=session.total_llm_calls,
                    user_instructions=session.user_instructions,
                    embedding=list(session.embedding) if session.embedding else None,
                    embedding_model=session.embedding_model,
                    reflection=session.reflection,
                    updated_at=datetime.now(UTC),
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "project_id": session.project_id,
                        "session_type": session.session_type,
                        "phase": session.phase.value,
                        "skill_name": session.skill_name,
                        "conversation": list(session.conversation),
                        "reasoning_log": list(session.reasoning_log),
                        "tool_results": list(session.tool_results),
                        "current_iteration": session.current_iteration,
                        "max_iterations": session.max_iterations,
                        "is_completed": session.is_completed,
                        "output_json": _json_to_dict(session.output_json),
                        "validation_is_valid": session.validation_is_valid,
                        "validation_errors": session.validation_errors,
                        "validation_error_messages": list(session.validation_error_messages),
                        "total_llm_calls": session.total_llm_calls,
                        "user_instructions": session.user_instructions,
                        "embedding": list(session.embedding) if session.embedding else None,
                        "embedding_model": session.embedding_model,
                        "reflection": session.reflection,
                        "updated_at": datetime.now(UTC),
                    },
                )
            )
            await db.execute(stmt)
            await db.commit()

    async def update_reflection(self, session_id: AgentMemoryId, reflection: str) -> None:
        async with self._session_factory() as db:
            stmt = select(AgentSessionModel).where(AgentSessionModel.id == session_id)
            result = await db.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return
            model.reflection = reflection
            model.updated_at = datetime.now(UTC)
            await db.commit()

    async def load_session(self, session_id: AgentMemoryId) -> AgentSession | None:
        async with self._session_factory() as db:
            stmt = select(AgentSessionModel).where(AgentSessionModel.id == session_id)
            result = await db.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return _model_to_session(model)

    async def list_sessions(
        self,
        project_id: ProjectId,
        *,
        phase: SpecPhase | None = None,
    ) -> list[AgentSessionSummary]:
        cols = (
            AgentSessionModel.id,
            AgentSessionModel.project_id,
            AgentSessionModel.session_type,
            AgentSessionModel.phase,
            AgentSessionModel.skill_name,
            AgentSessionModel.is_completed,
            AgentSessionModel.total_llm_calls,
            AgentSessionModel.validation_errors,
            AgentSessionModel.user_instructions,
            AgentSessionModel.created_at,
            AgentSessionModel.reflection,
        )
        async with self._session_factory() as db:
            stmt = select(*cols).where(AgentSessionModel.project_id == str(project_id))
            if phase is not None:
                stmt = stmt.where(AgentSessionModel.phase == phase.value)
            stmt = stmt.order_by(AgentSessionModel.created_at.desc()).limit(50)
            result = await db.execute(stmt)
            rows = result.all()
            return [_row_to_summary(r) for r in rows]

    async def get_latest_session(
        self,
        project_id: ProjectId,
        phase: SpecPhase,
    ) -> AgentSession | None:
        async with self._session_factory() as db:
            stmt = (
                select(AgentSessionModel)
                .where(AgentSessionModel.project_id == str(project_id))
                .where(AgentSessionModel.phase == phase.value)
                .order_by(AgentSessionModel.created_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return _model_to_session(model)

    async def get_project_context(self, project_id: ProjectId) -> ProjectMemoryContext:
        summaries = await self.list_sessions(project_id)
        latest: dict[str, AgentSessionSummary] = {}
        for s in summaries:
            key = f"{s.session_type}:{s.phase.value}"
            if key not in latest or s.created_at > latest[key].created_at:
                latest[key] = s

        reflections: list[str] = []
        error_counter: dict[str, int] = {}
        async with self._session_factory() as db:
            stmt = (
                select(AgentSessionModel.reflection)
                .where(AgentSessionModel.project_id == str(project_id))
                .where(AgentSessionModel.reflection.isnot(None))
                .order_by(AgentSessionModel.created_at.desc())
                .limit(5)
            )
            result = await db.execute(stmt)
            for row in result.fetchall():
                if row[0]:
                    reflections.append(str(row[0]))

            errors_stmt = (
                select(AgentSessionModel.validation_error_messages)
                .where(AgentSessionModel.project_id == str(project_id))
                .where(AgentSessionModel.is_completed == False)  # noqa: E712
                .where(AgentSessionModel.validation_error_messages.isnot(None))
                .order_by(AgentSessionModel.created_at.desc())
                .limit(20)
            )
            errors_result = await db.execute(errors_stmt)
            for (msgs,) in errors_result.fetchall():
                for msg in msgs or []:  # type: ignore[reportUnknownVariableType]
                    error_counter[str(msg)] = error_counter.get(str(msg), 0) + 1  # type: ignore[reportUnknownArgumentType]

        common_errors = [f"{msg} (x{count})" for msg, count in sorted(error_counter.items(), key=lambda x: -x[1])[:5]]

        return ProjectMemoryContext(
            project_id=project_id,
            latest_sessions=latest,
            total_sessions=len(summaries),
            common_validation_errors=common_errors,
            recent_reflections=reflections,
        )

    async def get_similar_sessions(
        self,
        embedding: list[float],
        *,
        limit: int = 5,
        exclude_project_id: ProjectId | None = None,
        model: str | None = None,
    ) -> list[AgentSessionSummary]:
        async with self._session_factory() as db:
            stmt = select(
                AgentSessionModel.id,
                AgentSessionModel.project_id,
                AgentSessionModel.session_type,
                AgentSessionModel.phase,
                AgentSessionModel.skill_name,
                AgentSessionModel.is_completed,
                AgentSessionModel.total_llm_calls,
                AgentSessionModel.validation_errors,
                AgentSessionModel.user_instructions,
                AgentSessionModel.created_at,
                AgentSessionModel.reflection,
            ).where(AgentSessionModel.embedding.isnot(None))
            if exclude_project_id:
                stmt = stmt.where(AgentSessionModel.project_id != str(exclude_project_id))
            if model:
                stmt = stmt.where(AgentSessionModel.embedding_model == model)

            stmt = stmt.order_by(AgentSessionModel.embedding.op("<=>")(embedding)).limit(limit)

            result = await db.execute(stmt)
            rows = result.all()

            return [
                AgentSessionSummary(
                    session_id=AgentMemoryId(row[0]),
                    project_id=ProjectId(row[1]),
                    session_type=row[2],
                    phase=SpecPhase(row[3]),
                    skill_name=row[4],
                    is_completed=row[5],
                    total_llm_calls=row[6],
                    validation_errors=row[7],
                    user_instructions=row[8],
                    created_at=row[9],
                    reflection=row[10],
                )
                for row in rows
            ]

    async def list_recent_sessions_global(
        self,
        *,
        limit: int = 50,
    ) -> list[AgentSessionSummary]:
        cols = (
            AgentSessionModel.id,
            AgentSessionModel.project_id,
            AgentSessionModel.session_type,
            AgentSessionModel.phase,
            AgentSessionModel.skill_name,
            AgentSessionModel.is_completed,
            AgentSessionModel.total_llm_calls,
            AgentSessionModel.validation_errors,
            AgentSessionModel.user_instructions,
            AgentSessionModel.created_at,
            AgentSessionModel.reflection,
        )
        async with self._session_factory() as db:
            stmt = select(*cols).order_by(AgentSessionModel.created_at.desc()).limit(limit)
            result = await db.execute(stmt)
            rows = result.all()
            return [_row_to_summary(r) for r in rows]

    async def count_completed_by_phase(
        self,
        *,
        since_session_id: AgentMemoryId | None = None,
        project_id: ProjectId | None = None,
    ) -> dict[str, int]:
        from sqlalchemy import func

        async with self._session_factory() as db:
            conditions = [AgentSessionModel.is_completed == True]  # noqa: E712
            if since_session_id is not None:
                subq = (
                    select(AgentSessionModel.created_at)
                    .where(AgentSessionModel.id == since_session_id)
                    .scalar_subquery()
                )
                conditions.append(AgentSessionModel.created_at > subq)
            if project_id is not None:
                conditions.append(AgentSessionModel.project_id == str(project_id))
            stmt = select(AgentSessionModel.phase, func.count()).where(*conditions).group_by(AgentSessionModel.phase)
            result = await db.execute(stmt)
            return {str(row[0]): int(row[1]) for row in result.fetchall()}

    async def delete_by_project(self, project_id: ProjectId) -> None:
        from sqlalchemy import delete

        async with self._session_factory() as db:
            stmt = delete(AgentSessionModel).where(AgentSessionModel.project_id == str(project_id))
            await db.execute(stmt)
            await db.commit()

    async def purge_stale_sessions(
        self,
        *,
        older_than_days: int = 7,
        incomplete_only: bool = True,
    ) -> int:
        from datetime import UTC, datetime, timedelta
        from typing import cast

        from sqlalchemy import and_, delete
        from sqlalchemy.engine import CursorResult

        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        async with self._session_factory() as db:
            conditions = [AgentSessionModel.updated_at < cutoff]
            if incomplete_only:
                conditions.append(AgentSessionModel.is_completed == False)  # noqa: E712
            stmt = delete(AgentSessionModel).where(and_(*conditions))
            result = cast(CursorResult[Any], await db.execute(stmt))
            await db.commit()
            return int(result.rowcount)


class SqlAlchemyKnowledgePatternStore:  # type: ignore[reportUnusedClass]
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def replace_patterns(
        self,
        phase: SpecPhase,
        patterns: list[KnowledgePattern],
    ) -> None:
        from sqlalchemy import delete as sqla_delete

        async with self._session_factory() as db:
            del_stmt = sqla_delete(KnowledgePatternModel).where(KnowledgePatternModel.phase == phase.value)
            await db.execute(del_stmt)
            for p in patterns:
                db.add(
                    KnowledgePatternModel(
                        id=p.pattern_id,
                        phase=p.phase.value,
                        pattern_text=p.pattern_text,
                        support_count=p.support_count,
                    )
                )
            await db.commit()

    async def list_patterns(
        self,
        phase: SpecPhase | None = None,
        *,
        limit: int = 10,
    ) -> list[KnowledgePattern]:
        async with self._session_factory() as db:
            stmt = select(KnowledgePatternModel)
            if phase is not None:
                stmt = stmt.where(KnowledgePatternModel.phase == phase.value)
            stmt = stmt.order_by(KnowledgePatternModel.support_count.desc()).limit(limit)
            result = await db.execute(stmt)
            models = result.scalars().all()
            return [
                KnowledgePattern(
                    pattern_id=m.id,
                    phase=SpecPhase(m.phase),
                    pattern_text=m.pattern_text,
                    support_count=m.support_count,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
                for m in models
            ]


def _model_to_session(model: AgentSessionModel) -> AgentSession:
    return AgentSession(
        session_id=AgentMemoryId(model.id),
        project_id=ProjectId(model.project_id),
        session_type=model.session_type,
        phase=SpecPhase(model.phase),
        skill_name=model.skill_name,
        conversation=[str(c) for c in (model.conversation or [])],
        reasoning_log=[str(r) for r in (model.reasoning_log or [])],
        tool_results=[
            dict(t) if isinstance(t, dict) else {}  # type: ignore[reportUnknownArgumentType]
            for t in (model.tool_results or [])
        ],
        current_iteration=model.current_iteration,
        max_iterations=model.max_iterations,
        is_completed=model.is_completed,
        output_json=_safe_json_dump(model.output_json),
        validation_is_valid=model.validation_is_valid,
        validation_errors=model.validation_errors,
        validation_error_messages=[str(m) for m in (model.validation_error_messages or [])],
        total_llm_calls=model.total_llm_calls,
        user_instructions=model.user_instructions,
        embedding=list(model.embedding) if model.embedding else None,
        embedding_model=model.embedding_model,
        reflection=model.reflection,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _row_to_summary(row: Row[Any]) -> AgentSessionSummary:
    return AgentSessionSummary(
        session_id=AgentMemoryId(row[0]),
        project_id=ProjectId(row[1]),
        session_type=row[2],
        phase=SpecPhase(row[3]),
        skill_name=row[4],
        is_completed=row[5],
        total_llm_calls=row[6],
        validation_errors=row[7],
        user_instructions=row[8],
        created_at=row[9],
        reflection=row[10],
    )


def _json_to_dict(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {"raw": str(result)}  # type: ignore[reportUnknownVariableType]
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _safe_json_dump(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


__all__ = [
    "SqlAlchemyAgentSessionStore",
    "SqlAlchemyKnowledgePatternStore",
]
