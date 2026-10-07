from __future__ import annotations

import pytest

from kosmo.contracts import (
    AppliedChange,
    ArtefactoAfectado,
    ConsistencyEvaluationOutput,
    ConsistencyStatus,
    DiffCambio,
    ImpactItem,
    ReporteConsistencia,
)
from kosmo.contracts.sdd.document import SpecPhase


@pytest.mark.unit
def test_artefacto_afectado_creation() -> None:
    # Arrange & Act
    artefacto = ArtefactoAfectado(
        artifact_id="feat_01",
        artifact_type="Feature",
        title="Gestión de usuarios",
        traceability_description="Derivado de la sección Alcance del Descubrimiento",
        suggested_diff=DiffCambio(before="Título viejo", after="Título nuevo"),
        rationale="Ajuste por modificación en Descubrimiento",
    )

    # Assert
    assert artefacto.artifact_id == "feat_01"
    assert artefacto.artifact_type == "Feature"
    assert artefacto.title == "Gestión de usuarios"
    assert artefacto.traceability_description == "Derivado de la sección Alcance del Descubrimiento"
    assert artefacto.suggested_diff.before == "Título viejo"
    assert artefacto.suggested_diff.after == "Título nuevo"
    assert artefacto.rationale == "Ajuste por modificación en Descubrimiento"


@pytest.mark.unit
def test_reporte_consistencia_creation_with_multiple_affected_artifacts() -> None:
    # Arrange
    user_change = AppliedChange(
        id="chg_01",
        section="Alcance",
        description="Modificación del alcance del sistema",
        diff=DiffCambio(before="Alcance 1", after="Alcance 2"),
    )
    feature_artifact = ArtefactoAfectado(
        artifact_id="feat_01",
        artifact_type="Feature",
        title="Gestión de catálogo",
        traceability_description="Derivada de Alcance",
        suggested_diff=DiffCambio(before="Catálogo básico", after="Catálogo avanzado"),
    )
    requirement_artifact = ArtefactoAfectado(
        artifact_id="req_01",
        artifact_type="EARSRequirement",
        title="Validación de timeout",
        traceability_description="Derivado de la Feature 1",
        suggested_diff=DiffCambio(before="30s timeout", after="15s timeout"),
    )

    # Act
    reporte = ReporteConsistencia(
        id="rep_01",
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        user_changes=[user_change],
        affected_artifacts=[feature_artifact, requirement_artifact],
    )

    # Assert
    assert reporte.id == "rep_01"
    assert reporte.source_phase == SpecPhase.DESCUBRIMIENTO
    assert reporte.target_phase == SpecPhase.CARACTERISTICAS
    assert len(reporte.user_changes) == 1
    assert reporte.user_changes[0].section == "Alcance"
    assert len(reporte.affected_artifacts) == 2
    assert reporte.affected_artifacts[0].artifact_type == "Feature"
    assert reporte.affected_artifacts[1].artifact_type == "EARSRequirement"
    assert reporte.created_at is not None


@pytest.mark.unit
def test_impact_item_creation() -> None:
    # Arrange & Act
    item = ImpactItem(
        id="imp_01",
        phase="features",
        target_id="feat_01",
        artifact_type="Feature",
        target_display_id="C01",
        target_title="Gestión de usuarios",
        section="title",
        rationale="El cambio en Descubrimiento afecta esta característica.",
        diff={"field": "title", "before": "Gestión básica", "after": "Gestión avanzada"},
        action="update",
    )

    # Assert
    assert item.id == "imp_01"
    assert item.phase == "features"
    assert item.target_id == "feat_01"
    assert item.artifact_type == "Feature"
    assert item.target_display_id == "C01"
    assert item.target_title == "Gestión de usuarios"
    assert item.section == "title"
    assert item.rationale == "El cambio en Descubrimiento afecta esta característica."
    assert item.diff == {"field": "title", "before": "Gestión básica", "after": "Gestión avanzada"}
    assert item.action == "update"


@pytest.mark.unit
def test_impact_item_minimal_creation() -> None:
    # Arrange & Act
    item = ImpactItem(
        id="imp_min",
        phase="model",
        target_id="feat_02",
        artifact_type="ActivityDiagram",
        target_display_id="C02",
        target_title="Diagrama de inventario",
        section="estructura UML",
        rationale="El cambio podría requerir actualizar el diagrama.",
    )

    # Assert
    assert item.diff is None
    assert item.action == "update"  # default


@pytest.mark.unit
def test_consistency_output_default_impacts_are_empty() -> None:
    # Arrange & Act
    output = ConsistencyEvaluationOutput(report_id="rep_01")

    # Assert
    assert output.upstream_impact == []
    assert output.downstream_impact == []


@pytest.mark.unit
def test_consistency_output_with_impact_items() -> None:
    # Arrange
    upstream_item = ImpactItem(
        id="imp_up",
        phase="discovery",
        target_id="doc_01",
        artifact_type="Document",
        target_display_id="D01",
        target_title="Visión del producto",
        section="Visión",
        rationale="La característica contradice la Visión del Descubrimiento.",
    )
    downstream_item = ImpactItem(
        id="imp_down",
        phase="requirements",
        target_id="feat_01",
        artifact_type="EARSRequirement",
        target_display_id="REQ-1.1",
        target_title="Validación de timeout",
        section="statement",
        rationale="El cambio en características afecta este requisito.",
    )

    # Act
    output = ConsistencyEvaluationOutput(
        report_id="rep_01",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["doc_01", "feat_01"],
        upstream_impact=[upstream_item],
        downstream_impact=[downstream_item],
    )

    # Assert
    assert output.status == ConsistencyStatus.ANALIZADO_CON_IMPACTO
    assert output.affected_artifact_ids == ["doc_01", "feat_01"]
    assert len(output.upstream_impact) == 1
    assert output.upstream_impact[0].phase == "discovery"
    assert output.upstream_impact[0].target_id == "doc_01"
    assert len(output.downstream_impact) == 1
    assert output.downstream_impact[0].phase == "requirements"
    assert output.downstream_impact[0].target_title == "Validación de timeout"


@pytest.mark.unit
def test_downstream_targets_includes_implementation_and_enforces_right_only() -> None:
    from kosmo.contracts.ai.consistency import DOWNSTREAM_TARGETS, PHASE_ORDER

    # Descubrimiento llega hasta IMPLEMENTACION
    assert SpecPhase.IMPLEMENTACION in DOWNSTREAM_TARGETS[SpecPhase.DESCUBRIMIENTO]
    # Características llega hasta IMPLEMENTACION
    assert SpecPhase.IMPLEMENTACION in DOWNSTREAM_TARGETS[SpecPhase.CARACTERISTICAS]
    # Requisitos llega hasta IMPLEMENTACION
    assert SpecPhase.IMPLEMENTACION in DOWNSTREAM_TARGETS[SpecPhase.REQUISITOS]
    # Modelo llega a IMPLEMENTACION
    assert SpecPhase.IMPLEMENTACION in DOWNSTREAM_TARGETS[SpecPhase.MODELO]
    # IMPLEMENTACION no tiene targets downstream (es hoja)
    assert DOWNSTREAM_TARGETS[SpecPhase.IMPLEMENTACION] == []

    # Verificar orden estricto hacia la derecha
    for source, targets in DOWNSTREAM_TARGETS.items():
        source_order = PHASE_ORDER[source]
        for target in targets:
            assert PHASE_ORDER[target] > source_order, f"{target} no está a la derecha de {source}"
