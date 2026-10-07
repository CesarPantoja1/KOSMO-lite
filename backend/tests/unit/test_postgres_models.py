"""Tests de verificación de Foreign Keys y Unique Constraints en SQLAlchemy models."""

import pytest
from sqlalchemy import UniqueConstraint

from kosmo.infrastructure.persistence.postgres.models import (
    ActivityDiagramModel,
    AgentSessionModel,
    ChatMessageModel,
    DiscoveryDocumentModel,
    DocumentVersionModel,
    FeatureModel,
    KnowledgePatternModel,
    RequirementModel,
)

pytestmark = pytest.mark.unit


def test_feature_model_has_fk_and_unique_constraint() -> None:
    table = FeatureModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "projects"), None)
    assert fk is not None
    assert fk.parent.name == "project_id"
    assert fk.target_fullname == "projects.id"
    assert fk.ondelete == "CASCADE"

    uq = next((c for c in table.constraints if isinstance(c, UniqueConstraint)), None)
    assert uq is not None
    assert {col.name for col in uq.columns} == {"project_id", "number"}


def test_requirement_model_has_fk_to_features() -> None:
    table = RequirementModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "features"), None)
    assert fk is not None
    assert fk.parent.name == "feature_id"
    assert fk.target_fullname == "features.id"
    assert fk.ondelete == "CASCADE"


def test_discovery_document_model_has_fk_to_projects() -> None:
    table = DiscoveryDocumentModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "projects"), None)
    assert fk is not None
    assert fk.parent.name == "project_id"
    assert fk.target_fullname == "projects.id"
    assert fk.ondelete == "CASCADE"


def test_agent_session_model_has_fk_to_projects() -> None:
    table = AgentSessionModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "projects"), None)
    assert fk is not None
    assert fk.parent.name == "project_id"
    assert fk.target_fullname == "projects.id"
    assert fk.ondelete == "CASCADE"


def test_activity_diagram_model_has_fk_to_features() -> None:
    table = ActivityDiagramModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "features"), None)
    assert fk is not None
    assert fk.parent.name == "feature_id"
    assert fk.target_fullname == "features.id"
    assert fk.ondelete == "CASCADE"


def test_knowledge_pattern_model_has_unique_constraint() -> None:
    table = KnowledgePatternModel.__table__
    uq = next((c for c in table.constraints if isinstance(c, UniqueConstraint)), None)
    assert uq is not None
    assert {col.name for col in uq.columns} == {"phase", "pattern_text"}


def test_chat_message_model_has_fk_to_projects() -> None:
    table = ChatMessageModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "projects"), None)
    assert fk is not None
    assert fk.parent.name == "project_id"
    assert fk.target_fullname == "projects.id"
    assert fk.ondelete == "CASCADE"


def test_document_version_model_has_fk_to_projects() -> None:
    table = DocumentVersionModel.__table__
    fk = next((fk for fk in table.foreign_keys if fk.column.table.name == "projects"), None)
    assert fk is not None
    assert fk.parent.name == "project_id"
    assert fk.target_fullname == "projects.id"
    assert fk.ondelete == "CASCADE"
