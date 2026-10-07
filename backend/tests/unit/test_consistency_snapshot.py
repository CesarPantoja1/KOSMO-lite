from __future__ import annotations

import pytest

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.sdd.consistency_snapshot import compute_snapshot_hash
from kosmo.domain.sdd.traceability_tracer import trace_downstream_phases


@pytest.mark.unit
def test_trace_downstream_phases_follows_rightward_chain() -> None:
    # Arrange
    # Act
    discovery_targets = trace_downstream_phases(SpecPhase.DESCUBRIMIENTO)
    features_targets = trace_downstream_phases(SpecPhase.CARACTERISTICAS)
    requirements_targets = trace_downstream_phases(SpecPhase.REQUISITOS)
    model_targets = trace_downstream_phases(SpecPhase.MODELO)

    # Assert
    assert discovery_targets == [
        SpecPhase.CARACTERISTICAS,
        SpecPhase.REQUISITOS,
        SpecPhase.MODELO,
        SpecPhase.IMPLEMENTACION,
    ]
    assert features_targets == [SpecPhase.REQUISITOS, SpecPhase.MODELO, SpecPhase.IMPLEMENTACION]
    assert requirements_targets == [SpecPhase.MODELO, SpecPhase.IMPLEMENTACION]
    assert model_targets == [SpecPhase.IMPLEMENTACION]
    assert trace_downstream_phases(SpecPhase.IMPLEMENTACION) == []


@pytest.mark.unit
def test_compute_snapshot_hash_is_deterministic() -> None:
    # Arrange
    parts = ["descubrimiento", "caracteristicas", "feat_01", "Feature", "contenido fuente", "contenido destino"]

    # Act
    first = compute_snapshot_hash(*parts)
    second = compute_snapshot_hash(*parts)

    # Assert
    assert first == second
    assert len(first) == 64


@pytest.mark.unit
def test_compute_snapshot_hash_changes_with_input() -> None:
    # Arrange
    base = ["a", "b", "c"]

    # Act
    original = compute_snapshot_hash(*base)
    changed = compute_snapshot_hash(*base[:-1], "c modificado")

    # Assert
    assert original != changed
