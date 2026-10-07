from __future__ import annotations

from typing import Any, Protocol, Self

from kosmo.contracts.ai.chat import ChatRepository
from kosmo.contracts.ai.consistency import TraceabilityRepository
from kosmo.contracts.sdd.codegen import FeatureImplementationRepository
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)


class OutboxPort(Protocol):
    async def enqueue(self, job_type: str, payload: dict[str, Any]) -> None: ...


class UnitOfWork(Protocol):
    """Gobierna el boundary transaccional de un use case.

    Los repositorios expuestos comparten la sesion del UoW: ninguna operacion
    comitea por su cuenta. El commit ocurre en ``__aexit__`` (salida limpia) o
    explicitamente via ``commit()``. Ante una excepcion se hace rollback.
    """

    @property
    def projects(self) -> ProjectRepository: ...

    @property
    def documents(self) -> DocumentRepository: ...

    @property
    def features(self) -> FeatureRepository: ...

    @property
    def requirements(self) -> RequirementRepository: ...

    @property
    def diagrams(self) -> ActivityDiagramRepository: ...

    @property
    def implementations(self) -> FeatureImplementationRepository: ...

    @property
    def chat(self) -> ChatRepository: ...

    @property
    def traceability(self) -> TraceabilityRepository: ...

    @property
    def outbox(self) -> OutboxPort: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
