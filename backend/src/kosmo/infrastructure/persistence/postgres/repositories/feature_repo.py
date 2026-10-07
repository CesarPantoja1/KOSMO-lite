from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import FeatureRepository
from kosmo.infrastructure.persistence.postgres.models import FeatureModel


class SqlAlchemyFeatureRepository(FeatureRepository):
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

    async def by_id(self, feature_id: FeatureId, *, for_update: bool = False) -> Feature | None:
        async with self._session_ctx() as session:
            model = await session.get(FeatureModel, str(feature_id), with_for_update=for_update)
            if model is None:
                return None
            return self._to_entity(model)

    async def list_by_project(self, project_id: ProjectId) -> list[Feature]:
        async with self._session_ctx() as session:
            stmt = (
                select(FeatureModel)
                .where(FeatureModel.project_id == str(project_id))
                .order_by(FeatureModel.number.asc())
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [self._to_entity(m) for m in models]

    async def save(self, feature: Feature) -> Feature:
        async with self._session_ctx() as session:
            model = await session.get(FeatureModel, str(feature.id))
            if model is None:
                model = self._to_model(feature)
                session.add(model)
            else:
                self._update_model(model, feature)
            await self._commit(session)
            return feature

    async def save_many(self, features: list[Feature]) -> list[Feature]:
        if not features:
            return features
        async with self._session_ctx() as session:
            ids = [str(f.id) for f in features]
            result = await session.execute(select(FeatureModel).where(FeatureModel.id.in_(ids)))
            existing: dict[str, FeatureModel] = {m.id: m for m in result.scalars().all()}
            for feature in features:
                model = existing.get(str(feature.id))
                if model is None:
                    session.add(self._to_model(feature))
                else:
                    self._update_model(model, feature)
            await self._commit(session)
            return features

    async def next_number(self, project_id: ProjectId) -> int:
        async with self._session_ctx() as session:
            stmt = (
                select(FeatureModel.number)
                .where(FeatureModel.project_id == str(project_id))
                .order_by(FeatureModel.number.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            max_number = result.scalar_one_or_none()
            return (max_number or 0) + 1

    async def delete(self, feature_id: FeatureId) -> None:
        async with self._session_ctx() as session:
            model = await session.get(FeatureModel, str(feature_id))
            if model is not None:
                await session.delete(model)
                await self._commit(session)

    @staticmethod
    def _to_entity(model: FeatureModel) -> Feature:
        return Feature(
            id=FeatureId(model.id),
            project_id=ProjectId(model.project_id),
            number=model.number,
            title=model.title,
            slug=model.slug,
            description=model.description,
            origin=model.origin,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, feature: Feature) -> FeatureModel:
        return FeatureModel(
            id=str(feature.id),
            project_id=str(feature.project_id),
            number=feature.number,
            title=feature.title,
            slug=feature.slug,
            description=feature.description,
            origin=feature.origin,
        )

    def _update_model(self, model: FeatureModel, feature: Feature) -> None:
        model.number = feature.number
        model.title = feature.title
        model.slug = feature.slug
        model.description = feature.description
        model.origin = feature.origin
        model.updated_at = datetime.now(UTC)
