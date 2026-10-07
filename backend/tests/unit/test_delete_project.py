from __future__ import annotations

import base64
from typing import Any

import pytest

from kosmo.application.projects.delete_project import (
    DeleteProjectInput,
    DeleteProjectUseCase,
)
from kosmo.contracts.ai.chat import ChatRole, ChatSession, MensajeChat
from kosmo.contracts.ai.consistency import ConsistencyEvaluation, ConsistencyEvaluationStatus
from kosmo.contracts.integrations.deployment import (
    DeploymentProvider,
    ProjectDeployment,
    UserDeploymentIntegration,
)
from kosmo.contracts.integrations.github import (
    GitHubSyncStatus,
    ProjectGitHubIntegration,
    UserGitHubIntegration,
)
from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
from kosmo.contracts.sdd.document import RichTextDocument, SpecPhase
from kosmo.contracts.sdd.errors import ProjectNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import (
    ActivityDiagramId,
    ChatMessageId,
    ChatSessionId,
    ConsistencyEvaluationId,
    FeatureId,
    ProjectId,
    UserId,
)
from kosmo.contracts.sdd.project import Project
from kosmo.infrastructure.security.fernet_vault import FernetSecretCipher
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryChatRepository,
    InMemoryConsistencyEvaluationRepository,
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectDeploymentRepository,
    InMemoryProjectGitHubIntegrationRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
    InMemoryTraceabilityRepository,
    InMemoryUserDeploymentIntegrationRepository,
    InMemoryUserGitHubIntegrationRepository,
)

_OWNER = UserId("usr_owner")


class _AgentMemorySpy:
    def __init__(self) -> None:
        self.deleted_projects: list[str] = []

    async def delete_by_project(self, project_id: ProjectId) -> None:
        self.deleted_projects.append(str(project_id))


class _DeploymentWorkerSpy:
    def __init__(self) -> None:
        self.cancelled_projects: list[str] = []

    def is_monitoring(self, project_id: ProjectId) -> bool:
        return True

    def cancel_monitoring(self, project_id: ProjectId) -> bool:
        self.cancelled_projects.append(str(project_id))
        return True


class _GitHubClientSpy:
    def __init__(self, should_fail: bool = False) -> None:
        self.deleted_repos: list[tuple[str, str, str]] = []
        self.should_fail = should_fail

    async def delete_repository(self, token: str, owner: str, repo_name: str) -> bool:
        if self.should_fail:
            raise RuntimeError("GitHub API connection error")
        self.deleted_repos.append((token, owner, repo_name))
        return True


class _DeploymentClientSpy:
    def __init__(self, should_fail: bool = False) -> None:
        self.deleted_services: list[tuple[str, str]] = []
        self.should_fail = should_fail

    async def delete_service(self, token: str, service_id: str) -> bool:
        if self.should_fail:
            raise RuntimeError("Railway API connection error")
        self.deleted_services.append((token, service_id))
        return True


class _WorkspaceManagerSpy:
    def __init__(self, should_fail: bool = False) -> None:
        self.deleted_projects: list[str] = []
        self.should_fail = should_fail

    async def delete_workspace(self, project_id: ProjectId) -> None:
        if self.should_fail:
            raise OSError(39, "Directory not empty")
        self.deleted_projects.append(str(project_id))


def _a_project(project_id: str = "prj_cascade") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=_OWNER,
    )


def _a_feature(project: Project, feature_id: str, number: int = 1) -> Feature:
    return Feature(
        id=FeatureId(feature_id),
        project_id=project.id,
        number=number,
        title="Test Feature",
        slug="test-feature",
        description="Descripción",
    )


def _a_diagram(feature: Feature) -> DiagramaActividad:
    return DiagramaActividad(
        id=ActivityDiagramId(f"adg_{str(feature.id)[-4:]}"),
        feature_id=feature.id,
        diagram_syntax="@startuml\nstart\n:accion;\nstop\n@enduml",
    )


def _make_uc(
    project_repo: InMemoryProjectRepository,
    feature_repo: InMemoryFeatureRepository,
    requirement_repo: InMemoryRequirementRepository,
    diagram_repo: InMemoryActivityDiagramRepository,
    document_repo: InMemoryDocumentRepository,
    chat_repo: InMemoryChatRepository,
    evaluation_repo: InMemoryConsistencyEvaluationRepository,
    traceability_repo: InMemoryTraceabilityRepository,
    agent_memory: _AgentMemorySpy | None = None,
    workspace_manager: _WorkspaceManagerSpy | None = None,
    project_github_repo: InMemoryProjectGitHubIntegrationRepository | None = None,
    user_github_repo: InMemoryUserGitHubIntegrationRepository | None = None,
    github_client: Any | None = None,
    project_deployment_repo: InMemoryProjectDeploymentRepository | None = None,
    user_deployment_repo: InMemoryUserDeploymentIntegrationRepository | None = None,
    deployment_client: Any | None = None,
    deployment_worker: Any | None = None,
    cipher: Any | None = None,
    delete_deployment: Any | None = None,
    delete_github_repo: Any | None = None,
) -> DeleteProjectUseCase:
    return DeleteProjectUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
        document_repo=document_repo,
        chat_repo=chat_repo,
        consistency_evaluation_repo=evaluation_repo,
        traceability_repo=traceability_repo,
        agent_memory=agent_memory,
        workspace_manager=workspace_manager,
        project_github_repo=project_github_repo,
        user_github_repo=user_github_repo,
        github_client=github_client,
        project_deployment_repo=project_deployment_repo,
        user_deployment_repo=user_deployment_repo,
        deployment_client=deployment_client,
        deployment_worker=deployment_worker,
        cipher=cipher,
        delete_deployment=delete_deployment,
        delete_github_repo=delete_github_repo,
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_removes_all_artifacts_in_cascade() -> None:
    # Arrange — sembrar todos los artefactos del proyecto
    project = _a_project()
    feature_1 = _a_feature(project, "feat_cascade1", number=1)
    feature_2 = _a_feature(project, "feat_cascade2", number=2)

    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(feature_1)
    await feature_repo.save(feature_2)

    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(feature_1.id, "### REQ-1.1\n\nRequisito uno.")
    await requirement_repo.save(feature_2.id, "### REQ-2.1\n\nRequisito dos.")

    diagram_repo = InMemoryActivityDiagramRepository()
    await diagram_repo.save(_a_diagram(feature_1))

    document_repo = InMemoryDocumentRepository()
    await document_repo.save_discovery(project.id, RichTextDocument(nodes=[]))
    await document_repo.save_version(project.id, SpecPhase.DESCUBRIMIENTO, "v1", [])

    chat_repo = InMemoryChatRepository()
    session = ChatSession(id=ChatSessionId("chs_cascade"), project_id=project.id, phase=SpecPhase.DESCUBRIMIENTO)
    await chat_repo.create_session(session)
    await chat_repo.save_message(
        project.id,
        SpecPhase.DESCUBRIMIENTO,
        MensajeChat(id=ChatMessageId("chm_cascade"), role=ChatRole.USER, content="hola"),
        session_id=session.id,
    )

    evaluation_repo = InMemoryConsistencyEvaluationRepository()
    await evaluation_repo.save(
        ConsistencyEvaluation(
            id=ConsistencyEvaluationId("cev_cascade"),
            project_id=project.id,
            source_phase=SpecPhase.DESCUBRIMIENTO,
            target_phase=SpecPhase.CARACTERISTICAS,
            target_artifact_id=str(feature_1.id),
            artifact_type="Feature",
            snapshot_hash="h",
            status=ConsistencyEvaluationStatus.COMPLETED,
        )
    )

    traceability_repo = InMemoryTraceabilityRepository()
    await traceability_repo.add_edge("discovery", str(project.id), "feature", str(feature_1.id))
    await traceability_repo.add_edge("feature", str(feature_1.id), "requirement", "req_1")

    agent_memory = _AgentMemorySpy()
    use_case = _make_uc(
        project_repo,
        feature_repo,
        requirement_repo,
        diagram_repo,
        document_repo,
        chat_repo,
        evaluation_repo,
        traceability_repo,
        agent_memory,
    )

    # Act
    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    # Assert — nada queda
    assert await project_repo.by_id(project.id) is None
    assert await feature_repo.by_id(feature_1.id) is None
    assert await feature_repo.by_id(feature_2.id) is None
    assert await requirement_repo.by_feature_id(feature_1.id) is None
    assert await requirement_repo.by_feature_id(feature_2.id) is None
    assert await diagram_repo.by_feature_id(feature_1.id) is None
    assert await document_repo.get_discovery(project.id) is None
    assert document_repo.versions == {}
    assert chat_repo.sessions == []
    assert chat_repo.messages == []
    assert await evaluation_repo.list_unresolved(project.id, SpecPhase.CARACTERISTICAS) == []
    assert traceability_repo.edges == []
    assert agent_memory.deleted_projects == [str(project.id)]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_raises_when_project_not_found() -> None:
    # Arrange
    use_case = _make_uc(
        InMemoryProjectRepository(),
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
    )

    # Act & Assert
    with pytest.raises(ProjectNotFoundError) as exc_info:
        await use_case.execute(DeleteProjectInput(project_id=ProjectId("prj_missing"), owner_id=_OWNER))

    assert exc_info.value.problem.status == 404


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_raises_when_owner_does_not_match() -> None:
    # Arrange
    project = _a_project()
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
    )

    # Act & Assert — un owner ajeno no puede borrar ni conoce la existencia del proyecto
    with pytest.raises(ProjectNotFoundError) as exc_info:
        await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=UserId("usr_intruso")))

    assert exc_info.value.problem.status == 404
    assert await project_repo.by_id(project.id) is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_without_artifacts_keeps_working() -> None:
    # Arrange — proyecto sin descubrimiento, features ni artefactos secundarios
    project = _a_project("prj_empty")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
    )

    # Act & Assert — el borrado solo elimina lo que exista
    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))
    assert await project_repo.by_id(project.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_removes_persisted_workspace() -> None:
    project = _a_project("prj_workspace")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)
    workspace_manager = _WorkspaceManagerSpy()

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        workspace_manager=workspace_manager,
    )

    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    assert workspace_manager.deleted_projects == [str(project.id)]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_global_cascade_removes_github_and_railway_and_workspace() -> None:
    # Arrange — Proyecto con integración de GitHub, despliegue en Railway y workspace
    project = _a_project("prj_global_del")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    workspace_manager = _WorkspaceManagerSpy()
    cipher = FernetSecretCipher(FernetSecretCipher.generate_master_key())

    # GitHub integration & credentials
    user_gh_repo = InMemoryUserGitHubIntegrationRepository()
    enc_gh_token = base64.b64encode(cipher.encrypt(b"gho_valid_token_123").ciphertext).decode("utf-8")
    await user_gh_repo.save(
        UserGitHubIntegration(
            user_id=_OWNER,
            github_username="octocat",
            encrypted_token=enc_gh_token,
        )
    )

    proj_gh_repo = InMemoryProjectGitHubIntegrationRepository()
    await proj_gh_repo.save(
        ProjectGitHubIntegration(
            project_id=project.id,
            repo_name="my-global-app",
            repo_url="https://github.com/octocat/my-global-app.git",
            sync_status=GitHubSyncStatus.SYNCED,
        )
    )

    # Railway integration & credentials
    user_dep_repo = InMemoryUserDeploymentIntegrationRepository()
    enc_rw_token = base64.b64encode(cipher.encrypt(b"rw_valid_token_456").ciphertext).decode("utf-8")
    await user_dep_repo.save(
        UserDeploymentIntegration(
            user_id=_OWNER,
            provider=DeploymentProvider.RAILWAY,
            encrypted_token=enc_rw_token,
        )
    )

    proj_dep_repo = InMemoryProjectDeploymentRepository()
    await proj_dep_repo.save(
        ProjectDeployment(
            project_id=project.id,
            provider=DeploymentProvider.RAILWAY,
            service_id="srv_railway_999",
        )
    )

    github_client = _GitHubClientSpy()
    deployment_client = _DeploymentClientSpy()
    deployment_worker = _DeploymentWorkerSpy()

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        workspace_manager=workspace_manager,
        project_github_repo=proj_gh_repo,
        user_github_repo=user_gh_repo,
        github_client=github_client,
        project_deployment_repo=proj_dep_repo,
        user_deployment_repo=user_dep_repo,
        deployment_client=deployment_client,
        deployment_worker=deployment_worker,
        cipher=cipher,
    )

    # Act
    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    # Assert:
    # 1. Monitoreo en segundo plano cancelado
    assert deployment_worker.cancelled_projects == [str(project.id)]

    # 2. Despliegue de Railway eliminado con token descifrado y service_id
    assert deployment_client.deleted_services == [("rw_valid_token_456", "srv_railway_999")]
    assert await proj_dep_repo.get_by_project_id(project.id) is None

    # 3. Repositorio de GitHub eliminado con token descifrado, owner y repo_name
    assert github_client.deleted_repos == [("gho_valid_token_123", "octocat", "my-global-app")]
    assert await proj_gh_repo.get_by_project_id(project.id) is None

    # 4. Workspace local eliminado
    assert workspace_manager.deleted_projects == [str(project.id)]

    # 5. Proyecto en BD eliminado
    assert await project_repo.by_id(project.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_resilient_when_github_cleanup_fails() -> None:
    # Arrange — Si GitHub falla (e.g. error de API), Railway y el proyecto igual se eliminan
    project = _a_project("prj_resilient_gh")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    cipher = FernetSecretCipher(FernetSecretCipher.generate_master_key())
    user_gh_repo = InMemoryUserGitHubIntegrationRepository()
    enc_gh = base64.b64encode(cipher.encrypt(b"token_gh").ciphertext).decode("utf-8")
    await user_gh_repo.save(UserGitHubIntegration(user_id=_OWNER, github_username="octocat", encrypted_token=enc_gh))

    proj_gh_repo = InMemoryProjectGitHubIntegrationRepository()
    await proj_gh_repo.save(
        ProjectGitHubIntegration(
            project_id=project.id,
            repo_name="fail-repo",
            repo_url="https://github.com/octocat/fail-repo",
        )
    )

    user_dep_repo = InMemoryUserDeploymentIntegrationRepository()
    enc_rw = base64.b64encode(cipher.encrypt(b"token_rw").ciphertext).decode("utf-8")
    await user_dep_repo.save(
        UserDeploymentIntegration(user_id=_OWNER, provider=DeploymentProvider.RAILWAY, encrypted_token=enc_rw)
    )

    proj_dep_repo = InMemoryProjectDeploymentRepository()
    await proj_dep_repo.save(
        ProjectDeployment(project_id=project.id, provider=DeploymentProvider.RAILWAY, service_id="srv_ok")
    )

    github_client = _GitHubClientSpy(should_fail=True)
    deployment_client = _DeploymentClientSpy(should_fail=False)

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        project_github_repo=proj_gh_repo,
        user_github_repo=user_gh_repo,
        github_client=github_client,
        project_deployment_repo=proj_dep_repo,
        user_deployment_repo=user_dep_repo,
        deployment_client=deployment_client,
        cipher=cipher,
    )

    # Act — No debe lanzar excepción
    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    # Assert — Railway y el proyecto sí se eliminaron
    assert deployment_client.deleted_services == [("token_rw", "srv_ok")]
    assert await project_repo.by_id(project.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_resilient_when_railway_cleanup_fails() -> None:
    # Arrange — Si Railway falla (e.g. timeout o 500), GitHub y el proyecto igual se eliminan
    project = _a_project("prj_resilient_rw")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    cipher = FernetSecretCipher(FernetSecretCipher.generate_master_key())
    user_gh_repo = InMemoryUserGitHubIntegrationRepository()
    enc_gh = base64.b64encode(cipher.encrypt(b"token_gh").ciphertext).decode("utf-8")
    await user_gh_repo.save(UserGitHubIntegration(user_id=_OWNER, github_username="octocat", encrypted_token=enc_gh))

    proj_gh_repo = InMemoryProjectGitHubIntegrationRepository()
    await proj_gh_repo.save(
        ProjectGitHubIntegration(
            project_id=project.id,
            repo_name="success-repo",
            repo_url="https://github.com/octocat/success-repo",
        )
    )

    user_dep_repo = InMemoryUserDeploymentIntegrationRepository()
    enc_rw = base64.b64encode(cipher.encrypt(b"token_rw").ciphertext).decode("utf-8")
    await user_dep_repo.save(
        UserDeploymentIntegration(user_id=_OWNER, provider=DeploymentProvider.RAILWAY, encrypted_token=enc_rw)
    )

    proj_dep_repo = InMemoryProjectDeploymentRepository()
    await proj_dep_repo.save(
        ProjectDeployment(project_id=project.id, provider=DeploymentProvider.RAILWAY, service_id="srv_fail")
    )

    github_client = _GitHubClientSpy(should_fail=False)
    deployment_client = _DeploymentClientSpy(should_fail=True)

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        project_github_repo=proj_gh_repo,
        user_github_repo=user_gh_repo,
        github_client=github_client,
        project_deployment_repo=proj_dep_repo,
        user_deployment_repo=user_dep_repo,
        deployment_client=deployment_client,
        cipher=cipher,
    )

    # Act — No debe lanzar excepción
    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    # Assert — GitHub y el proyecto sí se eliminaron
    assert github_client.deleted_repos == [("token_gh", "octocat", "success-repo")]
    assert await project_repo.by_id(project.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_resilient_when_workspace_cleanup_fails() -> None:
    # Arrange — Si la limpieza del directorio local en disco falla con OSError, el proyecto en DB se elimina igual
    project = _a_project("prj_resilient_ws")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    workspace_manager = _WorkspaceManagerSpy(should_fail=True)

    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        workspace_manager=workspace_manager,
    )

    # Act — No debe lanzar excepción
    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    # Assert — El proyecto sí se eliminó de la base de datos
    assert await project_repo.by_id(project.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_delegates_to_injected_delete_deployment() -> None:
    project = _a_project("prj_delegation")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    class _DeleteDeploymentSpy:
        def __init__(self) -> None:
            self.executed_commands: list[tuple[Any, Any]] = []

        async def execute(self, principal: Any, cmd: Any) -> bool:
            self.executed_commands.append((principal, cmd))
            return True

    delete_deployment_spy = _DeleteDeploymentSpy()
    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        delete_deployment=delete_deployment_spy,
    )

    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    assert len(delete_deployment_spy.executed_commands) == 1
    principal, cmd = delete_deployment_spy.executed_commands[0]
    assert principal.subject == str(_OWNER)
    assert cmd.project_id == project.id
    assert await project_repo.by_id(project.id) is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_delete_project_delegates_to_injected_delete_github_repo() -> None:
    project = _a_project("prj_delegation_gh")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    class _DeleteGitHubRepoSpy:
        def __init__(self) -> None:
            self.executed_commands: list[Any] = []

        async def execute(self, cmd: Any) -> bool:
            self.executed_commands.append(cmd)
            return True

    delete_github_spy = _DeleteGitHubRepoSpy()
    use_case = _make_uc(
        project_repo,
        InMemoryFeatureRepository(),
        InMemoryRequirementRepository(),
        InMemoryActivityDiagramRepository(),
        InMemoryDocumentRepository(),
        InMemoryChatRepository(),
        InMemoryConsistencyEvaluationRepository(),
        InMemoryTraceabilityRepository(),
        delete_github_repo=delete_github_spy,
    )

    await use_case.execute(DeleteProjectInput(project_id=project.id, owner_id=_OWNER))

    assert len(delete_github_spy.executed_commands) == 1
    cmd = delete_github_spy.executed_commands[0]
    assert cmd.project_id == project.id
    assert cmd.owner_id == _OWNER
    assert await project_repo.by_id(project.id) is None
