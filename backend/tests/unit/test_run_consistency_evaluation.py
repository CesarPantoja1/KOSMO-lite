from __future__ import annotations

from typing import Any

import pytest

from kosmo.application.consistency.run_consistency_evaluation import run_consistency_evaluation
from kosmo.contracts.ai.consistency import (
    ArtifactAction,
    ConsistencyEvaluationOutput,
    ConsistencyEvaluationStatus,
    ConsistencyStatus,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.domain.sdd.document_converters import markdown_to_document
from tests.unit.conftest import DISCOVERY_VALID
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryConsistencyEvaluationRepository,
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
)


class _ActionEvaluator:
    def __init__(self, actions: list[ArtifactAction] | None = None, *, should_fail: bool = False) -> None:
        self._actions = actions or []
        self._should_fail = should_fail
        self.calls: list[tuple[str, str]] = []

    async def evaluate(
        self,
        *,
        source_phase: SpecPhase,
        target_phase: SpecPhase,
        project_id: ProjectId,  # noqa: ARG002
        applied_changes: list[Any],  # noqa: ARG002
    ) -> ConsistencyEvaluationOutput:
        self.calls.append((source_phase.value, target_phase.value))
        if self._should_fail:
            raise RuntimeError("Falla simulada del evaluador")
        affected = [a.artifact_id for a in self._actions]
        return ConsistencyEvaluationOutput(
            report_id="rpt_1",
            status=ConsistencyStatus.ANALIZADO_CON_IMPACTO if affected else ConsistencyStatus.ANALIZADO_SIN_IMPACTO,
            affected_artifact_ids=affected,
            actions=self._actions,
        )


def _a_feature(project_id: str = "prj_01") -> Feature:
    return Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Registrar gastos compartidos",
        slug="registrar-gastos-compartidos",
        description="El usuario ingresa un gasto para dividirlo.",
        project_id=ProjectId(project_id),
        origin="Deriva de Metas del producto.",
    )


def _make_repos(with_feature: bool = True) -> tuple[Any, ...]:
    projects = InMemoryProjectRepository()
    features = InMemoryFeatureRepository()
    requirements = InMemoryRequirementRepository()
    diagrams = InMemoryActivityDiagramRepository()
    documents = InMemoryDocumentRepository()
    evaluations = InMemoryConsistencyEvaluationRepository()
    from kosmo.contracts.sdd.ids import UserId
    from kosmo.contracts.sdd.project import Project

    projects.projects["prj_01"] = Project(
        id=ProjectId("prj_01"),
        name="GastoJusto",
        slug="gastojusto",
        description="Reparto de gastos compartidos",
        owner_id=UserId("usr_01"),
    )
    documents.discovery_docs["prj_01"] = markdown_to_document(DISCOVERY_VALID)
    if with_feature:
        features.features["feat_01"] = _a_feature()
    return projects, features, requirements, diagrams, documents, evaluations


def _payload() -> dict[str, Any]:
    return {
        "project_id": "prj_01",
        "source_phase": "descubrimiento",
        "changes": [{"section": "Alcance", "description": "Ampliar alcance", "before": "antes", "after": "después"}],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_stores_fresh_rows() -> None:
    # Arrange
    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    evaluator = _ActionEvaluator(
        [
            ArtifactAction(
                artifact_id="feat_01",
                action="update",
                rationale="El cambio en Descubrimiento afecta esta característica.",
                suggested_field="description",
                suggested_before="El usuario ingresa un gasto para dividirlo.",
                suggested_after="El usuario registra y edita un gasto para dividirlo.",
            )
        ]
    )

    # Act
    await run_consistency_evaluation(
        _payload(),
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=evaluator,  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    # Assert
    rows = await evaluations.list_unresolved(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == ConsistencyEvaluationStatus.COMPLETED
    assert row.target_artifact_id == "feat_01"
    assert row.artifact_type == "Feature"
    assert row.snapshot_hash
    assert row.result is not None
    assert row.result["action"] == "update"
    assert row.source_changes


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_supersedes_stale_rows() -> None:
    # Arrange
    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    evaluator = _ActionEvaluator(
        [
            ArtifactAction(
                artifact_id="feat_01",
                action="update",
                rationale="afecta",
                suggested_field="description",
                suggested_before="El usuario ingresa un gasto para dividirlo.",
                suggested_after="El usuario registra y edita un gasto para dividirlo.",
            )
        ]
    )
    await run_consistency_evaluation(
        _payload(),
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=evaluator,  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    # Act — segunda evaluación sin artefactos afectados
    evaluator._actions = []
    await run_consistency_evaluation(
        _payload(),
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=evaluator,  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    # Assert — la fila vieja queda descartada
    rows = await evaluations.list_unresolved(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)
    assert rows == []
    activity = await evaluations.list_for_activity(ProjectId("prj_01"))
    assert any(r.status == ConsistencyEvaluationStatus.DISCARDED for r in activity)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_contains_failure_in_failed_row() -> None:
    # Arrange
    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    evaluator = _ActionEvaluator(should_fail=True)

    # Act
    await run_consistency_evaluation(
        _payload(),
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=evaluator,  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    # Assert — la excepción no propaga; queda una fila failed con razón
    rows = await evaluations.list_unresolved(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)
    assert len(rows) == 1
    assert rows[0].status == ConsistencyEvaluationStatus.FAILED
    assert rows[0].failure_reason


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_stores_operation_id() -> None:
    # Arrange
    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    evaluator = _ActionEvaluator(
        [
            ArtifactAction(
                artifact_id="feat_01",
                action="update",
                rationale="afecta",
                suggested_field="description",
                suggested_before="El usuario ingresa un gasto para dividirlo.",
                suggested_after="El usuario registra y edita un gasto para dividirlo.",
            )
        ]
    )
    payload = _payload()
    payload["operation_id"] = "ope_test"

    # Act
    await run_consistency_evaluation(
        payload,
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=evaluator,  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    # Assert
    rows = await evaluations.list_unresolved(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)
    assert len(rows) == 1
    assert rows[0].operation_id == "ope_test"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_skips_when_no_target_artifacts() -> None:
    # Arrange
    projects, features, requirements, diagrams, documents, evaluations = _make_repos(with_feature=False)
    evaluator = _ActionEvaluator()

    # Act
    await run_consistency_evaluation(
        _payload(),
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=evaluator,  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    # Assert
    assert evaluator.calls == []
    assert await evaluations.list_unresolved(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_propagates_user_context_from_payload() -> None:
    from kosmo.contracts.auth.context import current_user_id

    captured_user_ids: list[str | None] = []

    class _ContextSpyEvaluator:
        async def evaluate(self, **_kwargs: Any) -> ConsistencyEvaluationOutput:
            captured_user_ids.append(current_user_id.get())
            return ConsistencyEvaluationOutput(report_id="rpt_ctx", status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO)

    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    payload = _payload()
    payload["user_id"] = "usr_explicit_123"

    assert current_user_id.get() is None
    await run_consistency_evaluation(
        payload,
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=_ContextSpyEvaluator(),  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    assert captured_user_ids == ["usr_explicit_123"]
    assert current_user_id.get() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_falls_back_to_project_owner_id() -> None:
    from kosmo.contracts.auth.context import current_user_id

    captured_user_ids: list[str | None] = []

    class _ContextSpyEvaluator:
        async def evaluate(self, **_kwargs: Any) -> ConsistencyEvaluationOutput:
            captured_user_ids.append(current_user_id.get())
            return ConsistencyEvaluationOutput(report_id="rpt_ctx", status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO)

    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    payload = _payload()
    # No user_id in payload, project.owner_id is usr_01
    assert current_user_id.get() is None

    await run_consistency_evaluation(
        payload,
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=_ContextSpyEvaluator(),  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    assert captured_user_ids == ["usr_01"]
    assert current_user_id.get() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_evaluation_handles_analisis_fallido_status() -> None:
    class _FailedStatusEvaluator:
        async def evaluate(self, **_kwargs: Any) -> ConsistencyEvaluationOutput:
            return ConsistencyEvaluationOutput(
                report_id="rpt_fail",
                status=ConsistencyStatus.ANALISIS_FALLIDO,
                failure_reason="API key inválida o cuota agotada",
            )

    projects, features, requirements, diagrams, documents, evaluations = _make_repos()
    payload = _payload()

    await run_consistency_evaluation(
        payload,
        project_repo=projects,
        feature_repo=features,
        requirement_repo=requirements,
        diagram_repo=diagrams,
        document_repo=documents,
        evaluator=_FailedStatusEvaluator(),  # type: ignore[reportArgumentType]
        evaluation_repo=evaluations,
    )

    rows = await evaluations.list_unresolved(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)
    assert len(rows) == 1
    assert rows[0].status == ConsistencyEvaluationStatus.FAILED
    assert "API key inválida" in (rows[0].failure_reason or "")
