from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kosmo.application.codegen.recover_zombie_implementations import recover_zombie_implementations
from kosmo.contracts.sdd.codegen import (
    FeatureImplementation,
    FeatureImplementationStatus,
)
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId


class InMemoryImplementationRepo:
    def __init__(self, implementations: list[FeatureImplementation]) -> None:
        self.implementations = implementations
        self.saved: list[FeatureImplementation] = []

    async def list_by_status(self, status: FeatureImplementationStatus) -> list[FeatureImplementation]:
        return [impl for impl in self.implementations if impl.status == status]

    async def save(self, implementation: FeatureImplementation) -> FeatureImplementation:
        self.saved.append(implementation)
        return implementation


class FakeOpenCodeClient:
    def __init__(self, fail_on_close: bool = False) -> None:
        self.fail_on_close = fail_on_close
        self.closed: list[str] = []

    async def close_session(self, session_id: str) -> None:
        if self.fail_on_close:
            raise RuntimeError("OpenCode server down")
        self.closed.append(session_id)


class FakeWorkspaceManager:
    def __init__(self) -> None:
        self.released: list[str] = []

    async def release_lock(self, project_id: ProjectId) -> None:
        self.released.append(str(project_id))


def _an_implementation(
    *,
    status: FeatureImplementationStatus = FeatureImplementationStatus.IN_PROGRESS,
    session_id: str | None = "oc_sess_1",
) -> FeatureImplementation:
    now = datetime.now(UTC)
    return FeatureImplementation(
        id=ImplementationId("impl_feat_01"),
        feature_id=FeatureId("feat_01"),
        project_id=ProjectId("prj_01"),
        status=status,
        session_id=session_id,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_recover_zombie_implementations_marks_failed_and_releases_resources() -> None:
    # Arrange
    impl = _an_implementation(session_id="oc_sess_zombie")
    repo = InMemoryImplementationRepo([impl])
    opencode_client = FakeOpenCodeClient()
    workspace_manager = FakeWorkspaceManager()

    # Act
    recovered = await recover_zombie_implementations(repo, opencode_client, workspace_manager)

    # Assert
    assert recovered == 1
    assert len(repo.saved) == 1
    assert repo.saved[0].status == FeatureImplementationStatus.FAILED
    assert "oc_sess_zombie" in opencode_client.closed
    assert "prj_01" in workspace_manager.released


@pytest.mark.asyncio
@pytest.mark.unit
async def test_recover_zombie_implementations_returns_zero_when_none_in_progress() -> None:
    # Arrange
    repo = InMemoryImplementationRepo(
        [
            _an_implementation(status=FeatureImplementationStatus.IMPLEMENTED),
            _an_implementation(status=FeatureImplementationStatus.REQUIRES_REVIEW),
        ]
    )
    opencode_client = FakeOpenCodeClient()
    workspace_manager = FakeWorkspaceManager()

    # Act
    recovered = await recover_zombie_implementations(repo, opencode_client, workspace_manager)

    # Assert
    assert recovered == 0
    assert repo.saved == []
    assert opencode_client.closed == []
    assert workspace_manager.released == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_recover_zombie_implementations_best_effort_when_close_session_fails() -> None:
    # Arrange
    impl = _an_implementation(session_id="oc_sess_down")
    repo = InMemoryImplementationRepo([impl])
    opencode_client = FakeOpenCodeClient(fail_on_close=True)
    workspace_manager = FakeWorkspaceManager()

    # Act
    recovered = await recover_zombie_implementations(repo, opencode_client, workspace_manager)

    # Assert — el fallo de OpenCode no impide marcar FAILED ni liberar el lock
    assert recovered == 1
    assert repo.saved[0].status == FeatureImplementationStatus.FAILED
    assert "prj_01" in workspace_manager.released


@pytest.mark.asyncio
@pytest.mark.unit
async def test_recover_zombie_implementations_skips_close_when_no_session() -> None:
    # Arrange
    impl = _an_implementation(session_id=None)
    repo = InMemoryImplementationRepo([impl])
    opencode_client = FakeOpenCodeClient()
    workspace_manager = FakeWorkspaceManager()

    # Act
    recovered = await recover_zombie_implementations(repo, opencode_client, workspace_manager)

    # Assert
    assert recovered == 1
    assert repo.saved[0].status == FeatureImplementationStatus.FAILED
    assert opencode_client.closed == []
    assert "prj_01" in workspace_manager.released


@pytest.mark.asyncio
@pytest.mark.unit
async def test_recovery_does_not_interrupt_job_running_on_another_worker() -> None:
    impl = _an_implementation(session_id="oc_sess_active")
    repo = InMemoryImplementationRepo([impl])
    opencode_client = FakeOpenCodeClient()
    workspace_manager = FakeWorkspaceManager()
    checked: list[str] = []

    async def is_active(implementation_id: str) -> bool:
        checked.append(implementation_id)
        return True

    recovered = await recover_zombie_implementations(repo, opencode_client, workspace_manager, is_active=is_active)

    assert recovered == 0
    assert checked == ["impl_feat_01"]
    assert repo.saved == []
    assert opencode_client.closed == []
    assert workspace_manager.released == []
