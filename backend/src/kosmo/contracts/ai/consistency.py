from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from kosmo.contracts.ai.chat import AppliedChange, DiffCambio
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ConsistencyEvaluationId, FeatureId, ProjectId, RequirementId


class TraceabilityRepository(Protocol):
    async def get_impact(self, artifact_id: str) -> dict[str, list[dict[str, str]]]: ...
    async def get_impact_batch(self, artifact_ids: list[str]) -> dict[str, dict[str, list[dict[str, str]]]]: ...
    async def add_edge(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        origin: str = "llm",
    ) -> None: ...
    async def add_feature_requirement_edges(
        self, feature_id: FeatureId, requirement_ids: list[RequirementId]
    ) -> None: ...
    async def delete_by_entity_id(self, entity_id: str) -> None: ...


class ConsistencyStatus(StrEnum):
    ANALIZADO_SIN_IMPACTO = "analizado_sin_impacto"
    ANALIZADO_CON_IMPACTO = "analizado_con_impacto"
    ANALISIS_FALLIDO = "analisis_fallido"


class ConsistencyEvaluationStatus(StrEnum):
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    APPLIED = "applied"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class ConsistencyEvaluation:
    """Sugerencia de impacto fresca: solo es valida si su snapshot_hash coincide con el estado actual."""

    id: ConsistencyEvaluationId
    project_id: ProjectId
    source_phase: SpecPhase
    target_phase: SpecPhase
    target_artifact_id: str
    artifact_type: str
    snapshot_hash: str
    status: ConsistencyEvaluationStatus = ConsistencyEvaluationStatus.COMPLETED
    result: dict[str, object] | None = None
    source_changes: list[dict[str, object]] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    operation_id: str | None = None
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ConsistencyEvaluationRepository(Protocol):
    async def save(self, evaluation: ConsistencyEvaluation) -> ConsistencyEvaluation: ...

    async def by_id(self, evaluation_id: ConsistencyEvaluationId) -> ConsistencyEvaluation | None: ...

    async def list_unresolved(
        self,
        project_id: ProjectId,
        target_phase: SpecPhase,
    ) -> list[ConsistencyEvaluation]: ...

    async def list_for_activity(
        self,
        project_id: ProjectId,
        *,
        limit: int = 50,
    ) -> list[ConsistencyEvaluation]: ...

    async def delete_by_project(self, project_id: ProjectId) -> None: ...


# Trazabilidad solo hacia la derecha: Descubrimiento -> Caracteristicas -> Requisitos -> Modelo -> Implementacion
DOWNSTREAM_TARGETS: dict[SpecPhase, list[SpecPhase]] = {
    SpecPhase.DESCUBRIMIENTO: [
        SpecPhase.CARACTERISTICAS,
        SpecPhase.REQUISITOS,
        SpecPhase.MODELO,
        SpecPhase.IMPLEMENTACION,
    ],
    SpecPhase.CARACTERISTICAS: [
        SpecPhase.REQUISITOS,
        SpecPhase.MODELO,
        SpecPhase.IMPLEMENTACION,
    ],
    SpecPhase.REQUISITOS: [
        SpecPhase.MODELO,
        SpecPhase.IMPLEMENTACION,
    ],
    SpecPhase.MODELO: [
        SpecPhase.IMPLEMENTACION,
    ],
    SpecPhase.IMPLEMENTACION: [],
}

PHASE_ORDER: dict[SpecPhase, int] = {
    SpecPhase.DESCUBRIMIENTO: 0,
    SpecPhase.CARACTERISTICAS: 1,
    SpecPhase.REQUISITOS: 2,
    SpecPhase.MODELO: 3,
    SpecPhase.IMPLEMENTACION: 4,
}


@dataclass(frozen=True)
class ArtefactoAfectado:
    artifact_id: str
    artifact_type: str
    title: str
    traceability_description: str
    suggested_diff: DiffCambio
    rationale: str | None = None


@dataclass(frozen=True)
class ReporteConsistencia:
    id: str
    source_phase: SpecPhase
    target_phase: SpecPhase
    user_changes: list[AppliedChange] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    affected_artifacts: list[ArtefactoAfectado] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class ArtifactAction:
    artifact_id: str
    action: str  # "update", "delete", "keep"
    rationale: str
    suggested_field: str = ""
    suggested_before: str = ""
    suggested_after: str = ""


@dataclass(frozen=True)
class ImpactItem:
    id: str
    phase: str
    target_id: str
    artifact_type: str
    target_display_id: str
    target_title: str
    section: str
    rationale: str
    diff: dict[str, object] | None = None
    action: str = "update"


@dataclass(frozen=True)
class ConsistencyEvaluationOutput:
    report_id: str
    status: ConsistencyStatus = ConsistencyStatus.ANALIZADO_SIN_IMPACTO
    affected_artifact_ids: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    rationale: str = ""
    failure_reason: str = ""
    actions: list[ArtifactAction] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    upstream_impact: list[ImpactItem] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    downstream_impact: list[ImpactItem] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class ConsistencyEvaluator(Protocol):
    async def evaluate(
        self,
        *,
        source_phase: SpecPhase,
        target_phase: SpecPhase,
        project_id: ProjectId,
        applied_changes: list[AppliedChange],
    ) -> ConsistencyEvaluationOutput: ...


@dataclass(frozen=True)
class PhasePropagationInfo:
    phase: str
    affected_count: int
    affected_ids: list[str]
