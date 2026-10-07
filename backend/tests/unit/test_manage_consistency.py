from __future__ import annotations

import pytest

from kosmo.application.consistency.apply_consistency_impacts import ApplyConsistencyImpactsUseCase
from kosmo.application.consistency.consistency_snapshot import fetch_snapshot_parts
from kosmo.application.consistency.manage_consistency import (
    ApplyConsistencyEvaluationUseCase,
    BulkResolveConsistencyUseCase,
    DiscardConsistencyEvaluationUseCase,
    GetConsistencyActivityUseCase,
    GetConsistencyReviewUseCase,
    GetConsistencyStatusUseCase,
)
from kosmo.contracts.ai.consistency import (
    ConsistencyEvaluation,
    ConsistencyEvaluationStatus,
)
from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import (
    ConsistencyEvaluationNotFoundError,
    ConsistencyStaleError,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import (
    ActivityDiagramId,
    ConsistencyEvaluationId,
    FeatureId,
    ProjectId,
    UserId,
)
from kosmo.contracts.sdd.project import Project
from kosmo.domain.sdd.consistency_snapshot import compute_snapshot_hash
from kosmo.domain.sdd.document_converters import markdown_to_document
from tests.unit.conftest import DISCOVERY_VALID
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryChatRepository,
    InMemoryConsistencyEvaluationRepository,
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryOutbox,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
    InMemoryTraceabilityRepository,
    InMemoryUnitOfWork,
)

_FEATURE_DESCRIPTION = "El usuario ingresa un gasto para dividirlo."


def _a_feature() -> Feature:
    return Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Registrar gastos compartidos",
        slug="registrar-gastos-compartidos",
        description=_FEATURE_DESCRIPTION,
        project_id=ProjectId("prj_01"),
        origin="Deriva de Metas del producto.",
    )


def _a_project() -> Project:
    return Project(
        id=ProjectId("prj_01"),
        name="GastoJusto",
        slug="gastojusto",
        description="Reparto de gastos compartidos",
        owner_id=UserId("usr_01"),
    )


class _Seed:
    def __init__(self) -> None:
        self.projects = InMemoryProjectRepository()
        self.projects.projects["prj_01"] = _a_project()
        self.features = InMemoryFeatureRepository()
        self.features.features["feat_01"] = _a_feature()
        self.features.features["feat_02"] = Feature(
            id=FeatureId("feat_02"),
            number=2,
            title="Editar gastos compartidos",
            slug="editar-gastos-compartidos",
            description=_FEATURE_DESCRIPTION,
            project_id=ProjectId("prj_01"),
            origin="Deriva de Metas del producto.",
        )
        self.requirements = InMemoryRequirementRepository()
        self.diagrams = InMemoryActivityDiagramRepository()
        self.documents = InMemoryDocumentRepository()
        self.documents.discovery_docs["prj_01"] = markdown_to_document(DISCOVERY_VALID)
        self.evaluations = InMemoryConsistencyEvaluationRepository()
        self.outbox = InMemoryOutbox()

    def uow(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(
            projects=self.projects,
            documents=self.documents,
            features=self.features,
            requirements=self.requirements,
            diagrams=self.diagrams,
            chat=InMemoryChatRepository(),
            traceability=InMemoryTraceabilityRepository(),
            outbox=self.outbox,
        )

    async def snapshot_parts(
        self,
        source_phase: SpecPhase,
        target_phase: SpecPhase,
        *,
        target_artifact_id: str = "feat_01",
    ) -> list[str]:
        return await fetch_snapshot_parts(
            project_id=ProjectId("prj_01"),
            source_phase=source_phase,
            target_phase=target_phase,
            target_artifact_id=target_artifact_id,
            artifact_type="Feature",
            document_repo=self.documents,
            feature_repo=self.features,
            requirement_repo=self.requirements,
            diagram_repo=self.diagrams,
        )

    async def seed_completed(
        self,
        *,
        source_phase: SpecPhase = SpecPhase.DESCUBRIMIENTO,
        target_phase: SpecPhase = SpecPhase.CARACTERISTICAS,
        evaluation_id: str = "cev_01",
        target_artifact_id: str = "feat_01",
        operation_id: str | None = None,
    ) -> ConsistencyEvaluation:
        parts = await self.snapshot_parts(
            source_phase,
            target_phase,
            target_artifact_id=target_artifact_id,
        )
        row = ConsistencyEvaluation(
            id=ConsistencyEvaluationId(evaluation_id),
            project_id=ProjectId("prj_01"),
            source_phase=source_phase,
            target_phase=target_phase,
            target_artifact_id=target_artifact_id,
            artifact_type="Feature",
            snapshot_hash=compute_snapshot_hash(*parts),
            status=ConsistencyEvaluationStatus.COMPLETED,
            result={
                "targetId": target_artifact_id,
                "artifact_type": "Feature",
                "targetDisplayId": "C01" if target_artifact_id == "feat_01" else "C02",
                "targetTitle": "Registrar gastos compartidos",
                "section": "description",
                "rationale": "El cambio en Descubrimiento afecta esta característica.",
                "action": "update",
                "diff": {
                    "field": "description",
                    "before": _FEATURE_DESCRIPTION,
                    "after": "El usuario registra y edita un gasto para dividirlo.",
                },
            },
            source_changes=[{"section": "Alcance", "description": "Ampliar", "before": "a", "after": "b"}],
            operation_id=operation_id,
        )
        return await self.evaluations.save(row)


def _apply_uc(seed: _Seed) -> ApplyConsistencyEvaluationUseCase:
    return ApplyConsistencyEvaluationUseCase(
        evaluation_repo=seed.evaluations,
        apply_uc=ApplyConsistencyImpactsUseCase(uow=seed.uow()),
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_status_counts_unresolved_by_phase() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()

    # Act
    output = await GetConsistencyStatusUseCase(seed.evaluations).execute(ProjectId("prj_01"))

    # Assert
    phases = output["phases"]
    assert phases["features"]["pending"] == 1
    assert phases["requirements"]["pending"] == 0
    assert phases["model"]["pending"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_returns_fresh_card() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()

    # Act
    cards = await GetConsistencyReviewUseCase(
        seed.evaluations,
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    ).execute(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)

    # Assert
    assert len(cards) == 1
    assert cards[0].evaluation_id == "cev_01"
    assert cards[0].diff is not None
    assert cards[0].status == "completed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_card_includes_operation_id() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed(operation_id="ope_01")

    # Act
    cards = await GetConsistencyReviewUseCase(
        seed.evaluations,
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    ).execute(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)

    # Assert
    assert len(cards) == 1
    assert cards[0].operation_id == "ope_01"


async def _seed_diagram_row(seed: _Seed, diagram_syntax: str, *, before: str, after: str) -> None:
    await seed.diagrams.save(
        DiagramaActividad(
            id=ActivityDiagramId("feat_01"),
            feature_id=FeatureId("feat_01"),
            diagram_syntax=diagram_syntax,
        )
    )
    parts = await fetch_snapshot_parts(
        project_id=ProjectId("prj_01"),
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.MODELO,
        target_artifact_id="feat_01",
        artifact_type="ActivityDiagram",
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    )
    row = ConsistencyEvaluation(
        id=ConsistencyEvaluationId("cev_dia"),
        project_id=ProjectId("prj_01"),
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.MODELO,
        target_artifact_id="feat_01",
        artifact_type="ActivityDiagram",
        snapshot_hash=compute_snapshot_hash(*parts),
        status=ConsistencyEvaluationStatus.COMPLETED,
        result={
            "targetId": "feat_01",
            "artifact_type": "ActivityDiagram",
            "targetDisplayId": "C01",
            "targetTitle": "Diagrama de Registrar gastos compartidos",
            "section": "estructura UML",
            "rationale": "Renombrar actor.",
            "action": "update",
            "diff": {"field": "estructura UML", "before": before, "after": after},
        },
        source_changes=[{"section": "Actores", "description": "Renombrar", "before": "a", "after": "b"}],
    )
    await seed.evaluations.save(row)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_card_includes_full_diagrams_for_activity() -> None:
    """El card de diagrama expone el diagrama completo anterior y propuesto."""
    # Arrange
    seed = _Seed()
    diagram_syntax = "@startuml\nstart\n|#pink|Colaborador_de_tienda|\n:Recibir pedido;\nstop\n@enduml"
    await _seed_diagram_row(
        seed,
        diagram_syntax,
        before="|#pink|Colaborador_de_tienda|",
        after="|#pink|Dueno_o_colaborador|",
    )

    # Act
    cards = await GetConsistencyReviewUseCase(
        seed.evaluations,
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    ).execute(ProjectId("prj_01"), SpecPhase.MODELO)

    # Assert
    assert len(cards) == 1
    assert cards[0].diff is not None
    assert cards[0].diff["before_diagram"] == diagram_syntax
    after_diagram = str(cards[0].diff["after_diagram"])
    assert "Dueno_o_colaborador" in after_diagram
    assert "Colaborador_de_tienda" not in after_diagram


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_card_keeps_fragments_when_full_result_invalid() -> None:
    """Si el cambio rompe la sintaxis del diagrama completo, el diff queda solo con fragmentos."""
    # Arrange
    seed = _Seed()
    diagram_syntax = "@startuml\nstart\nif (¿ok?) then (sí)\n:Paso;\nendif\nstop\n@enduml"
    await _seed_diagram_row(
        seed,
        diagram_syntax,
        before="endif\nstop",
        after="stop",
    )

    # Act
    cards = await GetConsistencyReviewUseCase(
        seed.evaluations,
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    ).execute(ProjectId("prj_01"), SpecPhase.MODELO)

    # Assert
    assert len(cards) == 1
    assert cards[0].diff is not None
    assert "before_diagram" not in cards[0].diff
    assert cards[0].diff["before"] == "endif\nstop"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_discards_stale_card_automatically() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()
    seed.documents.discovery_docs["prj_01"] = markdown_to_document(
        DISCOVERY_VALID.replace("organizar y repartir gastos compartidos", "organizar gastos corporativos")
    )
    review = GetConsistencyReviewUseCase(
        seed.evaluations,
        document_repo=seed.documents,
        feature_repo=seed.features,
        requirement_repo=seed.requirements,
        diagram_repo=seed.diagrams,
    )

    # Act
    cards = await review.execute(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS)

    # Assert
    assert cards == []
    row = await seed.evaluations.by_id(ConsistencyEvaluationId("cev_01"))
    assert row is not None
    assert row.status == ConsistencyEvaluationStatus.DISCARDED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_updates_target_and_marks_applied() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()

    # Act
    result = await _apply_uc(seed).execute(ConsistencyEvaluationId("cev_01"))

    # Assert
    assert result["applied"] is True
    assert seed.features.features["feat_01"].description == "El usuario registra y edita un gasto para dividirlo."
    row = await seed.evaluations.by_id(ConsistencyEvaluationId("cev_01"))
    assert row is not None
    assert row.status == ConsistencyEvaluationStatus.APPLIED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_blocks_and_discards_when_source_changed() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()
    seed.documents.discovery_docs["prj_01"] = markdown_to_document(
        DISCOVERY_VALID.replace("organizar y repartir gastos compartidos", "organizar gastos corporativos")
    )

    # Act & Assert — invariante D2: no hay escritura sobre el target y no se re-encola
    with pytest.raises(ConsistencyStaleError):
        await _apply_uc(seed).execute(ConsistencyEvaluationId("cev_01"))

    assert seed.features.features["feat_01"].description == _FEATURE_DESCRIPTION
    row = await seed.evaluations.by_id(ConsistencyEvaluationId("cev_01"))
    assert row is not None
    assert row.status == ConsistencyEvaluationStatus.DISCARDED
    assert not any(job[0] == "consistency_evaluate" for job in seed.outbox.jobs)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_does_not_chain_evaluation_downstream() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()

    # Act
    await _apply_uc(seed).execute(ConsistencyEvaluationId("cev_01"))

    # Assert — no se encolan jobs en outbox al aplicar
    chain_jobs = [job for job in seed.outbox.jobs if job[0] == "consistency_evaluate"]
    assert len(chain_jobs) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discard_marks_row_for_snapshot() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()

    # Act
    result = await DiscardConsistencyEvaluationUseCase(seed.evaluations).execute(ConsistencyEvaluationId("cev_01"))

    # Assert
    assert result["discarded"] is True
    row = await seed.evaluations.by_id(ConsistencyEvaluationId("cev_01"))
    assert row is not None
    assert row.status == ConsistencyEvaluationStatus.DISCARDED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bulk_resolve_applies_all_fresh_rows() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed(evaluation_id="cev_01", target_artifact_id="feat_01")
    await seed.seed_completed(evaluation_id="cev_02", target_artifact_id="feat_02")

    apply_eval = _apply_uc(seed)
    discard_uc = DiscardConsistencyEvaluationUseCase(seed.evaluations)
    bulk = BulkResolveConsistencyUseCase(
        evaluation_repo=seed.evaluations,
        apply_uc=apply_eval,
        discard_uc=discard_uc,
    )

    # Act
    result = await bulk.execute(ProjectId("prj_01"), SpecPhase.CARACTERISTICAS, action="apply")

    # Assert
    assert result == {"resolved": 2, "skipped": 0}
    rows = await seed.evaluations.list_for_activity(ProjectId("prj_01"))
    assert sum(1 for r in rows if r.status == ConsistencyEvaluationStatus.APPLIED) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activity_lists_resolved_rows() -> None:
    # Arrange
    seed = _Seed()
    await seed.seed_completed()
    await _apply_uc(seed).execute(ConsistencyEvaluationId("cev_01"))

    # Act
    items = await GetConsistencyActivityUseCase(seed.evaluations).execute(ProjectId("prj_01"))

    # Assert
    assert len(items) == 1
    assert items[0]["status"] == "applied"
    assert items[0]["target_artifact_id"] == "feat_01"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_apply_evaluation_rejects_cross_project_idor() -> None:
    # Arrange — Proyecto legítimo prj_01 tiene una evaluación completada
    seed = _Seed()
    await seed.seed_completed(evaluation_id="cev_01")
    apply_uc = _apply_uc(seed)

    # Act & Assert — Atacante en prj_attacker intenta aplicar la evaluación ajena
    with pytest.raises(ConsistencyEvaluationNotFoundError):
        await apply_uc.execute(
            ConsistencyEvaluationId("cev_01"),
            project_id=ProjectId("prj_attacker"),
        )

    # Assert — La evaluación de la víctima NO fue modificada ni aplicada
    row = await seed.evaluations.by_id(ConsistencyEvaluationId("cev_01"))
    assert row is not None
    assert row.status == ConsistencyEvaluationStatus.COMPLETED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discard_evaluation_rejects_cross_project_idor() -> None:
    # Arrange — Proyecto legítimo prj_01 tiene una evaluación completada
    seed = _Seed()
    await seed.seed_completed(evaluation_id="cev_01")
    discard_uc = DiscardConsistencyEvaluationUseCase(seed.evaluations)

    # Act & Assert — Atacante en prj_attacker intenta descartar la evaluación ajena
    with pytest.raises(ConsistencyEvaluationNotFoundError):
        await discard_uc.execute(
            ConsistencyEvaluationId("cev_01"),
            project_id=ProjectId("prj_attacker"),
        )

    # Assert — La evaluación de la víctima NO fue descartada
    row = await seed.evaluations.by_id(ConsistencyEvaluationId("cev_01"))
    assert row is not None
    assert row.status == ConsistencyEvaluationStatus.COMPLETED
