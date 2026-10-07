from datetime import UTC, datetime

import pytest

from kosmo.contracts.integrations.github import (
    CodeSyncLog,
    CodeSyncStatus,
    GitHubApiError,
    GitHubAuthenticationError,
    GitHubOAuthToken,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubRepository,
    GitHubRepositoryAlreadyExistsError,
    GitHubResourceNotFoundError,
    GitHubSyncStatus,
    GitHubUser,
    ProjectGitHubIntegration,
    UserGitHubIntegration,
)
from kosmo.contracts.sdd.ids import ProjectId, UserId


@pytest.mark.unit
def test_user_github_integration_defaults() -> None:
    # Arrange & Act
    integration = UserGitHubIntegration(
        user_id=UserId("user-1"), github_username="testuser", encrypted_token="encrypted-pat"
    )

    # Assert
    assert integration.user_id == "user-1"
    assert integration.github_username == "testuser"
    assert integration.encrypted_token == "encrypted-pat"
    assert isinstance(integration.updated_at, datetime)
    assert integration.updated_at.tzinfo is not None


@pytest.mark.unit
def test_project_github_integration_defaults() -> None:
    # Arrange & Act
    integration = ProjectGitHubIntegration(
        project_id=ProjectId("proj-1"), repo_url="https://github.com/testuser/testrepo"
    )

    # Assert
    assert integration.project_id == "proj-1"
    assert integration.repo_url == "https://github.com/testuser/testrepo"
    assert integration.repo_name is None
    assert integration.is_public is True
    assert integration.default_branch == "main"
    assert integration.last_push_at is None
    assert integration.last_commit_hash is None
    assert integration.sync_status == GitHubSyncStatus.NOT_CREATED
    assert integration.error_message is None
    assert integration.last_synced_at is None
    assert isinstance(integration.created_at, datetime)
    assert isinstance(integration.updated_at, datetime)


@pytest.mark.unit
def test_project_github_integration_full_fields() -> None:
    # Arrange
    now = datetime.now(UTC)
    # Act
    integration = ProjectGitHubIntegration(
        project_id=ProjectId("prj_01"),
        repo_name="my-cool-repo",
        repo_url="https://github.com/octocat/my-cool-repo",
        is_public=True,
        default_branch="master",
        last_push_at=now,
        last_commit_hash="abc12345",
        sync_status=GitHubSyncStatus.SYNCED,
        error_message=None,
    )

    # Assert
    assert integration.repo_name == "my-cool-repo"
    assert integration.is_public is True
    assert integration.default_branch == "master"
    assert integration.last_push_at == now
    assert integration.last_commit_hash == "abc12345"
    assert integration.sync_status == GitHubSyncStatus.SYNCED


@pytest.mark.unit
def test_github_sync_status_values() -> None:
    # Arrange & Act & Assert
    assert GitHubSyncStatus.NOT_CREATED.value == "not_created"
    assert GitHubSyncStatus.CREATED.value == "created"
    assert GitHubSyncStatus.SYNCING.value == "syncing"
    assert GitHubSyncStatus.SYNCED.value == "synced"
    assert GitHubSyncStatus.FAILED.value == "failed"


@pytest.mark.unit
def test_code_sync_log_defaults() -> None:
    # Arrange & Act
    log = CodeSyncLog()

    # Assert
    assert log.id is not None
    assert log.project_id == ""
    assert log.commit_sha is None
    assert log.status == CodeSyncStatus.FAILED
    assert log.message is None
    assert isinstance(log.synced_at, datetime)


@pytest.mark.unit
def test_github_user_model() -> None:
    # Arrange & Act
    user = GitHubUser(
        login="octocat",
        id=1,
        name="The Octocat",
        email="octocat@github.com",
        avatar_url="https://github.com/images/error/octocat_happy.gif",
        html_url="https://github.com/octocat",
    )

    # Assert
    assert user.login == "octocat"
    assert user.id == 1
    assert user.name == "The Octocat"
    assert user.email == "octocat@github.com"
    assert user.avatar_url == "https://github.com/images/error/octocat_happy.gif"
    assert user.html_url == "https://github.com/octocat"


@pytest.mark.unit
def test_github_repository_model_defaults() -> None:
    # Arrange & Act
    repo = GitHubRepository(
        id=1296269,
        name="Hello-World",
        full_name="octocat/Hello-World",
        owner="octocat",
        html_url="https://github.com/octocat/Hello-World",
        clone_url="https://github.com/octocat/Hello-World.git",
        is_private=True,
    )

    # Assert
    assert repo.id == 1296269
    assert repo.name == "Hello-World"
    assert repo.full_name == "octocat/Hello-World"
    assert repo.owner == "octocat"
    assert repo.is_private is True
    assert repo.default_branch == "main"
    assert repo.description is None


@pytest.mark.unit
def test_github_oauth_token_model() -> None:
    # Arrange & Act
    token = GitHubOAuthToken(
        access_token="gho_16C7e42F292c6912E7710c838347Ae178B4a",
        token_type="bearer",
        scope="repo,user",
    )

    # Assert
    assert token.access_token == "gho_16C7e42F292c6912E7710c838347Ae178B4a"
    assert token.token_type == "bearer"
    assert token.scope == "repo,user"


@pytest.mark.unit
def test_github_exceptions_hierarchy() -> None:
    # Arrange & Act & Assert
    assert issubclass(GitHubAuthenticationError, GitHubApiError)
    assert issubclass(GitHubPermissionError, GitHubApiError)
    assert issubclass(GitHubResourceNotFoundError, GitHubApiError)
    assert issubclass(GitHubRepositoryAlreadyExistsError, GitHubApiError)
    assert issubclass(GitHubRateLimitError, GitHubApiError)
