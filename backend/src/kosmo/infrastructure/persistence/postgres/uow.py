from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from kosmo.contracts.ai.chat import ChatRepository
from kosmo.contracts.ai.consistency import TraceabilityRepository
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.sdd.codegen import FeatureImplementationRepository
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from kosmo.infrastructure.persistence.postgres.outbox import OutboxStore
from kosmo.infrastructure.persistence.postgres.repositories.activity_diagram_repo import (
    SqlAlchemyActivityDiagramRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.chat_repo import SqlAlchemyChatRepository
from kosmo.infrastructure.persistence.postgres.repositories.document_repo import (
    SqlAlchemyDocumentRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.feature_implementation_repo import (
    SqlAlchemyFeatureImplementationRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.feature_repo import (
    SqlAlchemyFeatureRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.project_repo import (
    SqlAlchemyProjectRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.requirement_repo import (
    SqlAlchemyRequirementRepository,
)
from kosmo.infrastructure.persistence.postgres.repositories.traceability_repo import (
    SqlAlchemyTraceabilityRepository,
)


@dataclass(slots=True)
class _UowContext:
    session: AsyncSession
    projects: ProjectRepository
    documents: DocumentRepository
    features: FeatureRepository
    requirements: RequirementRepository
    diagrams: ActivityDiagramRepository
    implementations: FeatureImplementationRepository
    chat: ChatRepository
    traceability: TraceabilityRepository
    outbox: OutboxPort


class SqlAlchemyUnitOfWork:
    """Unit of Work sobre SQLAlchemy: una sesion compartida por repos bound.

    Cada ``__aenter__`` crea una sesion fresca y repos bound a ella en un
    contexto aislado por corrutina/tarea (usando contextvars). Ninguna
    operacion de repos comitea por su cuenta: el commit ocurre al salir del
    contexto (salida limpia) o via ``commit()``; ante excepcion, rollback.
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._context_stack: ContextVar[tuple[_UowContext, ...]] = ContextVar(
            f"uow_stack_{id(self)}",
            default=(),
        )

    def _get_context(self) -> _UowContext | None:
        stack = self._context_stack.get()
        return stack[-1] if stack else None

    @property
    def _current(self) -> _UowContext:
        ctx = self._get_context()
        if ctx is None:
            raise ValueError("Unit of Work no activo")
        return ctx

    @property
    def _session(self) -> AsyncSession | None:
        ctx = self._get_context()
        return ctx.session if ctx is not None else None

    @property
    def projects(self) -> ProjectRepository:
        return self._current.projects

    @property
    def documents(self) -> DocumentRepository:
        return self._current.documents

    @property
    def features(self) -> FeatureRepository:
        return self._current.features

    @property
    def requirements(self) -> RequirementRepository:
        return self._current.requirements

    @property
    def diagrams(self) -> ActivityDiagramRepository:
        return self._current.diagrams

    @property
    def implementations(self) -> FeatureImplementationRepository:
        return self._current.implementations

    @property
    def chat(self) -> ChatRepository:
        return self._current.chat

    @property
    def traceability(self) -> TraceabilityRepository:
        return self._current.traceability

    @property
    def outbox(self) -> OutboxPort:
        return self._current.outbox

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        session = self._session_factory()
        ctx = _UowContext(
            session=session,
            projects=SqlAlchemyProjectRepository(session=session),
            documents=SqlAlchemyDocumentRepository(session=session),
            features=SqlAlchemyFeatureRepository(session=session),
            requirements=SqlAlchemyRequirementRepository(session=session),
            diagrams=SqlAlchemyActivityDiagramRepository(session=session),
            implementations=SqlAlchemyFeatureImplementationRepository(session=session),
            chat=SqlAlchemyChatRepository(session=session),
            traceability=SqlAlchemyTraceabilityRepository(session=session),
            outbox=OutboxStore(session=session),
        )
        current = self._context_stack.get()
        self._context_stack.set((*current, ctx))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        current = self._context_stack.get()
        if not current:
            return
        ctx = current[-1]
        self._context_stack.set(current[:-1])
        try:
            if exc_type is None:
                await ctx.session.commit()
            else:
                await ctx.session.rollback()
        finally:
            await ctx.session.close()

    async def commit(self) -> None:
        await self._current.session.commit()

    async def rollback(self) -> None:
        await self._current.session.rollback()
