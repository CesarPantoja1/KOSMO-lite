from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kosmo.application.codegen.get_implementation_record import (
    GetImplementationRecordUseCase,
    ImplementationRecordOutput,
)
from kosmo.contracts.sdd.codegen import (
    FeatureImplementation,
    FeatureImplementationStatus,
    ValidationRunResult,
    ValidationStep,
    ValidationStepResult,
)
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId
from tests.unit.fakes import (
    InMemoryFeatureImplementationRepository,
    InMemoryRequirementRepository,
)


class _FakeTraceabilityRepo:
    def __init__(self, impact: dict[str, list[dict[str, str]]] | None = None) -> None:
        self.impact = impact or {
            "upstream": [{"type": "requirement", "id": "req_01"}],
            "downstream": [{"type": "code", "id": "src/app/page.tsx"}],
        }

    async def get_impact_batch(self, artifact_ids: list[str]) -> dict[str, dict[str, list[dict[str, str]]]]:
        return dict.fromkeys(artifact_ids, self.impact)

    async def get_impact(self, artifact_id: str) -> dict[str, list[dict[str, str]]]:
        return self.impact


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_returns_none_when_implementation_not_found() -> None:
    impl_repo = InMemoryFeatureImplementationRepository()
    use_case = GetImplementationRecordUseCase(implementation_repo=impl_repo)

    result = await use_case.execute(FeatureId("feat_missing"))

    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_calculates_all_metrics() -> None:
    now = datetime.now(UTC)
    project_id = ProjectId("prj_test")
    feature_id = FeatureId("feat_01")

    impl_repo = InMemoryFeatureImplementationRepository()
    # Save the target implementation
    target_impl = FeatureImplementation(
        id=ImplementationId("impl_01"),
        feature_id=feature_id,
        project_id=project_id,
        status=FeatureImplementationStatus.IMPLEMENTED,
        generated_files=("src/app/page.tsx", "src/components/Header.tsx", "src/lib/utils.ts"),
        last_validation=ValidationRunResult(
            all_passed=True,
            steps=(
                ValidationStepResult(step=ValidationStep.TYPECHECK, success=True),
                ValidationStepResult(step=ValidationStep.LINT, success=True),
                ValidationStepResult(step=ValidationStep.TESTS, success=False),
            ),
        ),
        created_at=now,
        updated_at=now,
    )
    await impl_repo.save(target_impl)

    # Save a second implemented feature in the same project to test features_count
    second_impl = FeatureImplementation(
        id=ImplementationId("impl_02"),
        feature_id=FeatureId("feat_02"),
        project_id=project_id,
        status=FeatureImplementationStatus.IMPLEMENTED,
        generated_files=(),
        created_at=now,
        updated_at=now,
    )
    await impl_repo.save(second_impl)

    req_repo = InMemoryRequirementRepository()
    await req_repo.save(
        feature_id,
        "### Requisitos EARS\n- REQ-01.01: El sistema debe registrar usuarios.\n- REQ-01.02: El sistema debe listar.",
    )

    trace_repo = _FakeTraceabilityRepo()

    use_case = GetImplementationRecordUseCase(
        implementation_repo=impl_repo,
        requirement_repo=req_repo,
        traceability_repo=trace_repo,
    )

    result = await use_case.execute(feature_id)

    assert result is not None
    assert isinstance(result, ImplementationRecordOutput)
    assert result.implementation.id == ImplementationId("impl_01")
    # 2 screens (page.tsx and Header.tsx)
    assert result.screens_count == 2
    # 2 requirements matched
    assert result.requirements_count == 2
    # 2 out of 3 validations passed
    assert result.validations_passed == 2
    assert result.validations_total == 3
    # Traceability edges > 0
    assert result.traceability_edges_count > 0
    # 2 implemented features in project
    assert result.features_count == 2
    assert "Next.js" in result.technologies


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_fallbacks_when_no_page_or_components_match() -> None:
    now = datetime.now(UTC)
    project_id = ProjectId("prj_fallback")
    feature_id = FeatureId("feat_fallback")

    impl_repo = InMemoryFeatureImplementationRepository()
    impl = FeatureImplementation(
        id=ImplementationId("impl_fallback"),
        feature_id=feature_id,
        project_id=project_id,
        status=FeatureImplementationStatus.PENDING,
        generated_files=("src/lib/a.ts", "src/lib/b.ts", "src/lib/c.ts", "src/lib/d.ts"),
        last_validation=None,
        created_at=now,
        updated_at=now,
    )
    await impl_repo.save(impl)

    use_case = GetImplementationRecordUseCase(implementation_repo=impl_repo)

    result = await use_case.execute(feature_id)

    assert result is not None
    # Fallback screens count: max(1, 4 // 2) = 2
    assert result.screens_count == 2
    assert result.requirements_count == 0
    # Default validations: 4 / 4
    assert result.validations_passed == 4
    assert result.validations_total == 4
    # Traceability fallback: max(1, 0 + 4) = 4
    assert result.traceability_edges_count == 4
    assert result.features_count == 1
