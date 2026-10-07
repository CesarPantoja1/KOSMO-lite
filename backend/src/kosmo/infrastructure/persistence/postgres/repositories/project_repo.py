from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.sdd.ids import ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.contracts.sdd.repositories import ProjectRepository
from kosmo.infrastructure.persistence.postgres.models import ProjectModel


class SqlAlchemyProjectRepository(ProjectRepository):
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

    async def by_id(self, project_id: ProjectId) -> Project | None:
        async with self._session_ctx() as session:
            model = await session.get(ProjectModel, project_id)
            if model is None:
                return None
            return self._to_entity(model)

    async def by_slug(self, owner_id: str, slug: str) -> Project | None:
        async with self._session_ctx() as session:
            from sqlalchemy import select

            stmt = select(ProjectModel).where(ProjectModel.owner_id == owner_id).where(ProjectModel.slug == slug)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_entity(model)

    async def find_by_slug(self, slug: str) -> Project | None:
        async with self._session_ctx() as session:
            from sqlalchemy import select

            stmt = select(ProjectModel).where(ProjectModel.slug == slug)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._to_entity(model)

    async def list_by_owner(self, owner_id: str, *, limit: int = 100) -> list[Project]:
        async with self._session_ctx() as session:
            from sqlalchemy import select

            stmt = (
                select(ProjectModel)
                .where(ProjectModel.owner_id == owner_id)
                .order_by(ProjectModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            models = result.scalars().all()
            return [self._to_entity(m) for m in models]

    async def save(self, project: Project) -> Project:
        async with self._session_ctx() as session:
            model = await session.get(ProjectModel, str(project.id))
            if model is None:
                model = ProjectModel(
                    id=str(project.id),
                    name=project.name,
                    slug=project.slug,
                    description=project.description,
                    owner_id=str(project.owner_id),
                )
                session.add(model)
            else:
                model.name = project.name
                model.slug = project.slug
                model.description = project.description
                model.updated_at = datetime.now(UTC)
            await self._commit(session)
            return project

    async def delete(self, project_id: ProjectId) -> None:
        from sqlalchemy import delete

        async with self._session_ctx() as session:
            stmt = delete(ProjectModel).where(ProjectModel.id == str(project_id))
            await session.execute(stmt)
            await self._commit(session)

    def _to_entity(self, model: ProjectModel) -> Project:
        return Project(
            id=ProjectId(model.id),
            name=model.name,
            slug=model.slug,
            description=model.description,
            owner_id=UserId(model.owner_id),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
