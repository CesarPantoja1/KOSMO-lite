from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.sdd.ids import FeatureId, RequirementId
from kosmo.domain.sdd.id_generator import IdGenerator
from kosmo.infrastructure.persistence.postgres.models import TraceabilityEdgeModel


class SqlAlchemyTraceabilityRepository:
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

    async def add_edge(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        origin: str = "llm",
    ) -> None:
        async with self._session_ctx() as session:
            model = TraceabilityEdgeModel(
                id=IdGenerator.generate("trace_edge"),
                source_type=source_type,
                source_id=source_id,
                target_type=target_type,
                target_id=target_id,
                origin=origin,
            )
            session.add(model)
            await self._commit(session)

    async def get_impact_batch(self, artifact_ids: list[str]) -> dict[str, dict[str, list[dict[str, str]]]]:
        if not artifact_ids:
            return {}

        results: dict[str, dict[str, list[dict[str, str]]]] = {
            aid: {"upstream": [], "downstream": []} for aid in artifact_ids
        }
        artifact_set = set(artifact_ids)

        async with self._session_ctx() as session:
            stmt = select(TraceabilityEdgeModel).where(
                or_(
                    TraceabilityEdgeModel.target_id.in_(artifact_ids),
                    TraceabilityEdgeModel.source_id.in_(artifact_ids),
                )
            )
            result = await session.execute(stmt)
            for edge in result.scalars().all():
                if edge.target_id in artifact_set:
                    results[edge.target_id]["upstream"].append(
                        {
                            "type": edge.source_type,
                            "id": edge.source_id,
                            "origin": edge.origin,
                        }
                    )
                if edge.source_id in artifact_set:
                    results[edge.source_id]["downstream"].append(
                        {
                            "type": edge.target_type,
                            "id": edge.target_id,
                            "origin": edge.origin,
                        }
                    )

        return results

    async def get_impact(self, artifact_id: str) -> dict[str, list[dict[str, str]]]:
        batch = await self.get_impact_batch([artifact_id])
        return batch.get(artifact_id, {"upstream": [], "downstream": []})

    async def add_feature_requirement_edges(self, feature_id: FeatureId, requirement_ids: list[RequirementId]) -> None:
        async with self._session_ctx() as session:
            for req_id in requirement_ids:
                session.add(
                    TraceabilityEdgeModel(
                        id=IdGenerator.generate("trace_edge"),
                        source_type="feature",
                        source_id=str(feature_id),
                        target_type="requirement",
                        target_id=str(req_id),
                        origin="llm",
                    )
                )
            await self._commit(session)

    async def delete_by_entity_id(self, entity_id: str) -> None:
        async with self._session_ctx() as session:
            stmt = delete(TraceabilityEdgeModel).where(
                or_(
                    TraceabilityEdgeModel.source_id == entity_id,
                    TraceabilityEdgeModel.target_id == entity_id,
                )
            )
            await session.execute(stmt)
            await self._commit(session)
