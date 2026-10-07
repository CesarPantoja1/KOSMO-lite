from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.ai.consistency import (
    ConsistencyEvaluation,
    ConsistencyEvaluationRepository,
    ConsistencyEvaluationStatus,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ConsistencyEvaluationId, ProjectId
from kosmo.infrastructure.persistence.postgres.models import ConsistencyEvaluationModel

_UNRESOLVED_STATUSES = (
    ConsistencyEvaluationStatus.EVALUATING.value,
    ConsistencyEvaluationStatus.COMPLETED.value,
    ConsistencyEvaluationStatus.FAILED.value,
)

_RESOLVED_STATUSES = (
    ConsistencyEvaluationStatus.APPLIED.value,
    ConsistencyEvaluationStatus.DISCARDED.value,
)


class SqlAlchemyConsistencyEvaluationRepository(ConsistencyEvaluationRepository):
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

    async def save(self, evaluation: ConsistencyEvaluation) -> ConsistencyEvaluation:
        async with self._session_ctx() as session:
            stmt = select(ConsistencyEvaluationModel).where(
                ConsistencyEvaluationModel.project_id == str(evaluation.project_id),
                ConsistencyEvaluationModel.source_phase == evaluation.source_phase.value,
                ConsistencyEvaluationModel.target_phase == evaluation.target_phase.value,
                ConsistencyEvaluationModel.target_artifact_id == evaluation.target_artifact_id,
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            if model is None:
                model = ConsistencyEvaluationModel(id=str(evaluation.id))
                session.add(model)
            else:
                evaluation = _with_id(evaluation, model.id)

            model.project_id = str(evaluation.project_id)
            model.source_phase = evaluation.source_phase.value
            model.target_phase = evaluation.target_phase.value
            model.target_artifact_id = evaluation.target_artifact_id
            model.artifact_type = evaluation.artifact_type
            model.snapshot_hash = evaluation.snapshot_hash
            model.status = evaluation.status.value
            model.result = evaluation.result
            model.source_changes = list(evaluation.source_changes)
            model.operation_id = evaluation.operation_id
            model.failure_reason = evaluation.failure_reason
            model.updated_at = datetime.now(UTC)
            await self._commit(session)

        return evaluation

    async def by_id(self, evaluation_id: ConsistencyEvaluationId) -> ConsistencyEvaluation | None:
        async with self._session_ctx() as session:
            result = await session.execute(
                select(ConsistencyEvaluationModel).where(ConsistencyEvaluationModel.id == str(evaluation_id))
            )
            model = result.scalar_one_or_none()
            return _model_to_evaluation(model) if model is not None else None

    async def list_unresolved(
        self,
        project_id: ProjectId,
        target_phase: SpecPhase,
    ) -> list[ConsistencyEvaluation]:
        async with self._session_ctx() as session:
            stmt = (
                select(ConsistencyEvaluationModel)
                .where(
                    ConsistencyEvaluationModel.project_id == str(project_id),
                    ConsistencyEvaluationModel.target_phase == target_phase.value,
                    ConsistencyEvaluationModel.status.in_(_UNRESOLVED_STATUSES),
                )
                .order_by(ConsistencyEvaluationModel.created_at)
            )
            result = await session.execute(stmt)
            return [_model_to_evaluation(m) for m in result.scalars().all()]

    async def list_for_activity(
        self,
        project_id: ProjectId,
        *,
        limit: int = 50,
    ) -> list[ConsistencyEvaluation]:
        async with self._session_ctx() as session:
            stmt = (
                select(ConsistencyEvaluationModel)
                .where(
                    ConsistencyEvaluationModel.project_id == str(project_id),
                    ConsistencyEvaluationModel.status.in_(_RESOLVED_STATUSES),
                )
                .order_by(ConsistencyEvaluationModel.updated_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [_model_to_evaluation(m) for m in result.scalars().all()]

    async def delete_by_project(self, project_id: ProjectId) -> None:
        from sqlalchemy import delete

        async with self._session_ctx() as session:
            stmt = delete(ConsistencyEvaluationModel).where(ConsistencyEvaluationModel.project_id == str(project_id))
            await session.execute(stmt)
            await self._commit(session)


def _with_id(evaluation: ConsistencyEvaluation, id_value: str) -> ConsistencyEvaluation:
    return ConsistencyEvaluation(
        id=ConsistencyEvaluationId(id_value),
        project_id=evaluation.project_id,
        source_phase=evaluation.source_phase,
        target_phase=evaluation.target_phase,
        target_artifact_id=evaluation.target_artifact_id,
        artifact_type=evaluation.artifact_type,
        snapshot_hash=evaluation.snapshot_hash,
        status=evaluation.status,
        result=evaluation.result,
        source_changes=evaluation.source_changes,
        operation_id=evaluation.operation_id,
        failure_reason=evaluation.failure_reason,
        created_at=evaluation.created_at,
        updated_at=evaluation.updated_at,
    )


def _model_to_evaluation(model: ConsistencyEvaluationModel) -> ConsistencyEvaluation:
    result = model.result if isinstance(model.result, dict) else None
    source_changes: list[dict[str, object]] = [
        cast(dict[str, object], c) if isinstance(c, dict) else {} for c in (model.source_changes or [])
    ]
    return ConsistencyEvaluation(
        id=ConsistencyEvaluationId(model.id),
        project_id=ProjectId(model.project_id),
        source_phase=SpecPhase(model.source_phase),
        target_phase=SpecPhase(model.target_phase),
        target_artifact_id=model.target_artifact_id,
        artifact_type=model.artifact_type,
        snapshot_hash=model.snapshot_hash,
        status=ConsistencyEvaluationStatus(model.status),
        result=result,
        source_changes=source_changes,
        operation_id=model.operation_id,
        failure_reason=model.failure_reason,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
