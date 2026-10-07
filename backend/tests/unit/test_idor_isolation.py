from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from kosmo.application.chat.chat_sessions import (
    CreateChatSessionInput,
    CreateChatSessionUseCase,
    DeleteChatSessionInput,
    DeleteChatSessionUseCase,
)
from kosmo.application.consistency.manage_consistency import (
    ApplyConsistencyEvaluationUseCase,
    DiscardConsistencyEvaluationUseCase,
)
from kosmo.contracts.ai.consistency import (
    ConsistencyEvaluation,
    ConsistencyEvaluationStatus,
    SpecPhase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.errors import (
    ChatSessionNotFoundError,
    ConsistencyEvaluationNotFoundError,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import (
    ConsistencyEvaluationId,
    FeatureId,
    ProjectId,
    UserId,
)
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.api.dependencies.auth import require_project_owner, verify_feature_owner
from tests.unit.fakes import InMemoryChatRepository, InMemoryConsistencyEvaluationRepository


@pytest.mark.asyncio
@pytest.mark.unit
async def test_chat_session_cross_project_deletion_prevented() -> None:
    # Arrange: Alice crea una sesion de chat legitima en su proyecto
    repo = InMemoryChatRepository()
    create_uc = CreateChatSessionUseCase(repo)
    session_alice = await create_uc.execute(
        CreateChatSessionInput(
            project_id=ProjectId("prj_alice"),
            phase=SpecPhase.DESCUBRIMIENTO,
        )
    )
    delete_uc = DeleteChatSessionUseCase(repo)

    # Act & Assert: Atacante desde prj_bob intenta eliminar la sesion de Alice
    with pytest.raises(ChatSessionNotFoundError) as exc_info:
        await delete_uc.execute(
            DeleteChatSessionInput(
                session_id=session_alice.id,
                project_id=ProjectId("prj_bob"),
            )
        )

    # El error es 404 (no revela si la sesion existe en otro proyecto)
    assert exc_info.value.problem.status == 404

    # La sesion en prj_alice permanece intacta
    assert len(repo.sessions) == 1
    assert repo.sessions[0].id == session_alice.id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consistency_evaluation_cross_project_apply_prevented() -> None:
    # Arrange: Evaluacion completada perteneciente al proyecto de Alice
    eval_repo = InMemoryConsistencyEvaluationRepository()
    eval_alice = ConsistencyEvaluation(
        id=ConsistencyEvaluationId("cev_alice_01"),
        project_id=ProjectId("prj_alice"),
        source_phase=SpecPhase.CARACTERISTICAS,
        target_phase=SpecPhase.REQUISITOS,
        target_artifact_id="feat_01",
        artifact_type="feature",
        status=ConsistencyEvaluationStatus.COMPLETED,
        result={},
        snapshot_hash="hash_123",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await eval_repo.save(eval_alice)

    use_case = ApplyConsistencyEvaluationUseCase(
        evaluation_repo=eval_repo,
        apply_uc=AsyncMock(),
        document_repo=AsyncMock(),
        feature_repo=AsyncMock(),
        requirement_repo=AsyncMock(),
        diagram_repo=AsyncMock(),
    )

    # Act & Assert: Atacante intenta aplicar evaluacion de Alice usando prj_bob
    with pytest.raises(ConsistencyEvaluationNotFoundError) as exc_info:
        await use_case.execute(
            evaluation_id=eval_alice.id,
            project_id=ProjectId("prj_bob"),
        )

    assert exc_info.value.problem.status == 404

    # El estado permanece COMPLETED y nunca pasa a APPLIED
    stored = await eval_repo.by_id(eval_alice.id)
    assert stored is not None
    assert stored.status == ConsistencyEvaluationStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.unit
async def test_consistency_evaluation_cross_project_discard_prevented() -> None:
    # Arrange: Evaluacion completada perteneciente a Alice
    eval_repo = InMemoryConsistencyEvaluationRepository()
    eval_alice = ConsistencyEvaluation(
        id=ConsistencyEvaluationId("cev_alice_02"),
        project_id=ProjectId("prj_alice"),
        source_phase=SpecPhase.CARACTERISTICAS,
        target_phase=SpecPhase.REQUISITOS,
        target_artifact_id="feat_02",
        artifact_type="feature",
        status=ConsistencyEvaluationStatus.COMPLETED,
        result={},
        snapshot_hash="hash_456",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    await eval_repo.save(eval_alice)

    use_case = DiscardConsistencyEvaluationUseCase(evaluation_repo=eval_repo)

    # Act & Assert: Atacante intenta descartar evaluacion de Alice desde prj_bob
    with pytest.raises(ConsistencyEvaluationNotFoundError) as exc_info:
        await use_case.execute(
            evaluation_id=eval_alice.id,
            project_id=ProjectId("prj_bob"),
        )

    assert exc_info.value.problem.status == 404

    # El estado permanece COMPLETED y nunca pasa a DISCARDED
    stored = await eval_repo.by_id(eval_alice.id)
    assert stored is not None
    assert stored.status == ConsistencyEvaluationStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.unit
async def test_require_project_owner_cross_tenant_returns_404() -> None:
    # Arrange: Proyecto perteneciente a Alice
    alice_project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto de Alice",
        slug="proyecto-alice",
        description="Confidencial",
        owner_id=UserId("usr_alice"),
    )
    container = MagicMock()
    container.repos.projects.by_id = AsyncMock(return_value=alice_project)

    # Intruso Bob
    bob_principal = Principal(subject="usr_bob", scopes=frozenset({"*"}))

    # Act & Assert: require_project_owner debe levantar 404 (nunca 403) para no filtrar existencia
    with pytest.raises(HTTPException) as exc_info:
        await require_project_owner(
            container=container,
            project_id=ProjectId("prj_alice"),
            principal=bob_principal,
        )

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail


@pytest.mark.asyncio
@pytest.mark.unit
async def test_verify_feature_owner_cross_tenant_returns_404() -> None:
    # Arrange: Caracteristica perteneciente al proyecto de Alice
    alice_project = Project(
        id=ProjectId("prj_alice"),
        name="Proyecto de Alice",
        slug="proyecto-alice",
        description="Confidencial",
        owner_id=UserId("usr_alice"),
    )
    alice_feature = Feature(
        id=FeatureId("feat_alice_01"),
        number=1,
        title="Feature de Alice",
        slug="feat-alice",
        description="Confidencial",
        project_id=ProjectId("prj_alice"),
    )

    container = MagicMock()
    container.repos.projects.by_id = AsyncMock(return_value=alice_project)
    container.repos.features.by_id = AsyncMock(return_value=alice_feature)

    mock_request = MagicMock(spec=Request)
    mock_request.app.state.container = container
    mock_request.state = MagicMock()

    bob_principal = Principal(subject="usr_bob", scopes=frozenset({"*"}))

    # Act & Assert: Intruso Bob consultando caracteristica de Alice recibe 404
    with pytest.raises(HTTPException) as exc_info:
        await verify_feature_owner(
            feature_id="feat_alice_01",
            principal=bob_principal,
            request=mock_request,
        )

    assert exc_info.value.status_code == 404
    assert "no encontrado" in exc_info.value.detail
