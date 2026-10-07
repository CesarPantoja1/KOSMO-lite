from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.infrastructure.persistence.postgres.models import FeatureModel
from kosmo.infrastructure.persistence.postgres.repositories.feature_repo import (
    SqlAlchemyFeatureRepository,
)


def _make_feature(
    feature_id: str = "feat_01",
    project_id: str = "prj_01",
    number: int = 1,
) -> Feature:
    now = datetime.now(UTC)
    return Feature(
        id=FeatureId(feature_id),
        project_id=ProjectId(project_id),
        number=number,
        title=f"Feature {number}",
        slug=f"feature-{number}",
        description=None,
        origin=None,
        created_at=now,
        updated_at=now,
    )


def _make_feature_model(feature_id: str = "feat_01", project_id: str = "prj_01") -> FeatureModel:
    now = datetime.now(UTC)
    return FeatureModel(
        id=feature_id,
        project_id=project_id,
        number=1,
        title="Feature 1",
        slug="feature-1",
        description=None,
        origin=None,
        created_at=now,
        updated_at=now,
    )


def _make_session(existing_models: list) -> MagicMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = existing_models
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=mock_result)
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _make_repo(session: MagicMock) -> SqlAlchemyFeatureRepository:
    factory = MagicMock(spec=async_sessionmaker)
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return SqlAlchemyFeatureRepository(session_factory=factory)


@pytest.mark.unit
async def test_save_many_empty_list_returns_immediately() -> None:
    session = _make_session([])
    repo = _make_repo(session)
    result = await repo.save_many([])
    assert result == []
    session.execute.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.unit
async def test_save_many_issues_exactly_one_query_for_n_features() -> None:
    features = [_make_feature(f"feat_0{i}", number=i) for i in range(1, 6)]
    session = _make_session([])
    repo = _make_repo(session)
    await repo.save_many(features)
    assert session.execute.call_count == 1
    assert session.add.call_count == 5
    session.commit.assert_called_once()


@pytest.mark.unit
async def test_save_many_inserts_new_features() -> None:
    features = [_make_feature("feat_new")]
    session = _make_session([])
    repo = _make_repo(session)
    result = await repo.save_many(features)
    session.add.assert_called_once()
    assert result == features


@pytest.mark.unit
async def test_save_many_updates_existing_features() -> None:
    existing_model = _make_feature_model("feat_01")
    feature_updated = Feature(
        id=FeatureId("feat_01"),
        project_id=ProjectId("prj_01"),
        number=1,
        title="Titulo actualizado",
        slug="feature-1",
        description=None,
        origin=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = _make_session([existing_model])
    repo = _make_repo(session)
    await repo.save_many([feature_updated])
    session.add.assert_not_called()
    assert existing_model.title == "Titulo actualizado"
    session.commit.assert_called_once()


@pytest.mark.unit
async def test_save_many_mixed_insert_and_update() -> None:
    existing_model = _make_feature_model("feat_01")
    features = [_make_feature("feat_01"), _make_feature("feat_02", number=2)]
    session = _make_session([existing_model])
    repo = _make_repo(session)
    await repo.save_many(features)
    assert session.execute.call_count == 1
    assert session.add.call_count == 1
    session.commit.assert_called_once()
