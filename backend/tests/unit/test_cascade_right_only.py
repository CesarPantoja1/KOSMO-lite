from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from kosmo.contracts.ai.consistency import DOWNSTREAM_TARGETS
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.infrastructure.api.routers.consistency import (
    evaluate_consistency,
    evaluate_consistency_stream,
)
from kosmo.infrastructure.api.schemas import EvaluateConsistencyRequestView


def _principal() -> Principal:
    return Principal(subject="usr_test123", scopes=frozenset({"*"}))


def test_downstream_targets_are_right_only() -> None:
    # Act
    discovery_targets = DOWNSTREAM_TARGETS[SpecPhase.DESCUBRIMIENTO]
    features_targets = DOWNSTREAM_TARGETS[SpecPhase.CARACTERISTICAS]
    requirements_targets = DOWNSTREAM_TARGETS[SpecPhase.REQUISITOS]
    model_targets = DOWNSTREAM_TARGETS[SpecPhase.MODELO]

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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_consistency_rejects_upstream_destination_with_422() -> None:
    # Arrange
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=MagicMock(report_id="rpt", upstream_impact=[], downstream_impact=[]))
    request_body = EvaluateConsistencyRequestView(
        phase_origin="features",
        phase_destination="discovery",
        changes=[],
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await evaluate_consistency("prj_01", _principal(), request_body, uc)

    assert exc_info.value.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_consistency_rejects_same_phase_destination_with_422() -> None:
    # Arrange
    uc = MagicMock()
    request_body = EvaluateConsistencyRequestView(
        phase_origin="requirements",
        phase_destination="requirements",
        changes=[],
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await evaluate_consistency("prj_01", _principal(), request_body, uc)

    assert exc_info.value.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_consistency_defaults_to_right_phases_of_origin() -> None:
    # Arrange
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=MagicMock(report_id="rpt", upstream_impact=[], downstream_impact=[]))
    request_body = EvaluateConsistencyRequestView(
        phase_origin="requirements",
        changes=[],
    )

    # Act
    await evaluate_consistency("prj_01", _principal(), request_body, uc)

    # Assert
    input_data = uc.execute.await_args.args[0]
    assert input_data.target_phases == [SpecPhase.MODELO, SpecPhase.IMPLEMENTACION]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_consistency_unknown_destination_raises_400() -> None:
    # Arrange
    uc = MagicMock()
    request_body = EvaluateConsistencyRequestView(
        phase_origin="discovery",
        phase_destination="unknown_phase",
        changes=[],
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await evaluate_consistency("prj_01", _principal(), request_body, uc)

    assert exc_info.value.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_consistency_stream_rejects_upstream_destination() -> None:
    # Arrange
    uc = MagicMock()
    uc.execute_stream = AsyncMock(return_value=MagicMock())
    request_body = EvaluateConsistencyRequestView(
        phase_origin="model",
        phase_destination="discovery",
        changes=[],
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await evaluate_consistency_stream("prj_01", _principal(), request_body, uc)

    assert exc_info.value.status_code == 422
    uc.execute_stream.assert_not_awaited()
