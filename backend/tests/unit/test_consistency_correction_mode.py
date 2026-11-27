from __future__ import annotations

import pytest

from kosmo.contracts.pipeline.consistency_phase_context import (
    ConsistencyPhaseContext,
    DownstreamArtifact,
)
from kosmo.contracts.pipeline.phase_outputs import ConsistencyCorrection
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.pipeline.phase_modes.consistency_evaluation_mode import (
    ConsistencyCorrectionMode,
)


def _feature_context() -> ConsistencyPhaseContext:
    return ConsistencyPhaseContext(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        downstream_artifacts=[
            DownstreamArtifact(
                artifact_id="feat_01",
                artifact_type="Feature",
                title="Consultar catálogo",
                description="Descripción original.",
            )
        ],
    )


@pytest.mark.unit
def test_correction_accepts_valid_feature_fragment() -> None:
    # Arrange
    mode = ConsistencyCorrectionMode()

    # Act
    result = mode.validate_output(
        ConsistencyCorrection(
            suggested_before="Descripción original.",
            suggested_after="Descripción modificada.",
        ),
        context=_feature_context(),
    )

    # Assert
    assert result.is_valid is True


@pytest.mark.unit
def test_correction_rejects_empty_fragments() -> None:
    # Arrange
    mode = ConsistencyCorrectionMode()

    # Act
    result = mode.validate_output(
        ConsistencyCorrection(suggested_before="", suggested_after=""),
        context=_feature_context(),
    )

    # Assert
    assert result.is_valid is False
