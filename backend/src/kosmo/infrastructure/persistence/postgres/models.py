from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects import postgresql as pg
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(pg.CITEXT(), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    disabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class AuditEventModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(pg.INET(), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text(), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        pg.JSONB(),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    current_phase: Mapped[str] = mapped_column(String(32), nullable=False, default="descubrimiento")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="en_proceso")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FeatureModel(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_features_project_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    origin: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RequirementModel(Base):
    __tablename__ = "requirements"

    feature_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("features.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    markdown: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TraceabilityEdgeModel(Base):
    __tablename__ = "traceability_edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="llm")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DiscoveryDocumentModel(Base):
    __tablename__ = "discovery"

    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    markdown: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AgentSessionModel(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_type: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    skill_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    conversation: Mapped[list[Any]] = mapped_column(pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb"))
    reasoning_log: Mapped[list[Any]] = mapped_column(pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb"))
    tool_results: Mapped[list[Any]] = mapped_column(pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb"))

    current_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    is_completed: Mapped[bool] = mapped_column(default=False, nullable=False)

    output_json: Mapped[dict[str, Any] | None] = mapped_column(pg.JSONB(), nullable=True)
    validation_is_valid: Mapped[bool] = mapped_column(default=False, nullable=False)
    validation_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_error_messages: Mapped[list[Any]] = mapped_column(
        pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb")
    )
    total_llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user_instructions: Mapped[str | None] = mapped_column(Text(), nullable=True)

    embedding: Mapped[list[float] | None] = mapped_column(Vector, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reflection: Mapped[str | None] = mapped_column(Text(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ActivityDiagramModel(Base):
    __tablename__ = "activity_diagrams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    diagram_syntax: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class KnowledgePatternModel(Base):
    __tablename__ = "knowledge_patterns"
    __table_args__ = (UniqueConstraint("phase", "pattern_text", name="uq_knowledge_patterns_phase_pattern"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    pattern_text: Mapped[str] = mapped_column(Text(), nullable=False)
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    context_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    suggested_change: Mapped[dict[str, Any] | None] = mapped_column(pg.JSONB(), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    context_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocumentVersionModel(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    markdown: Mapped[str] = mapped_column(Text(), nullable=False)
    change_ids: Mapped[list[Any]] = mapped_column(pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OutboxJobModel(Base):
    __tablename__ = "outbox_jobs"
    __table_args__ = (Index("ix_outbox_pending", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(pg.JSONB(), nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ConsistencyEvaluationModel(Base):
    __tablename__ = "consistency_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_phase",
            "target_phase",
            "target_artifact_id",
            name="uq_consistency_evaluations_natural",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    target_phase: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_artifact_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="evaluating")
    result: Mapped[dict[str, Any] | None] = mapped_column(pg.JSONB(), nullable=True)
    source_changes: Mapped[list[Any]] = mapped_column(
        pg.JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    operation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class UserPreferenceModel(Base):
    __tablename__ = "user_preferences"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_text: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkspaceModel(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    current_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    path: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FeatureImplementationModel(Base):
    __tablename__ = "feature_implementations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(pg.JSONB(), nullable=True)
    last_validation: Mapped[dict[str, Any] | None] = mapped_column(pg.JSONB(), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    generated_files: Mapped[list[str]] = mapped_column(pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb"))
    retry_history: Mapped[list[Any]] = mapped_column(pg.JSONB(), nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserAiConfigModel(Base):
    __tablename__ = "user_ai_configs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserIntegrationModel(Base):
    __tablename__ = "user_integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_integrations_user_provider"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_enc: Mapped[str] = mapped_column(Text(), nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text(), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(
        pg.JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProjectIntegrationModel(Base):
    __tablename__ = "project_integrations"
    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_project_integrations_project_provider"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="github")
    repo_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_branch: Mapped[str] = mapped_column(String(100), nullable=False, default="main")
    last_push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_commit_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_created")
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Campos de despliegue en la nube (HU-24)
    service_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    deploy_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_created",
        server_default="not_created",
    )
    build_logs_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    volumes: Mapped[list[dict[str, Any]]] = mapped_column(
        pg.JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    ports: Mapped[list[dict[str, Any]]] = mapped_column(
        pg.JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    env_vars: Mapped[list[dict[str, Any]]] = mapped_column(
        pg.JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CodeSyncLogModel(Base):
    __tablename__ = "code_sync_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="failed")
    message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
