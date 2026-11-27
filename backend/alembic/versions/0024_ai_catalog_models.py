"""create ai_catalog_models table

Revision ID: 0024_ai_catalog_models
Revises: 0023_drop_activity_diagrams
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0024_ai_catalog_models"
down_revision: str | Sequence[str] | None = "0023_drop_activity_diagrams"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_catalog_models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("opencode_model_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False, server_default=sa.text("128000")),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default=sa.text("8192")),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("opencode_compatible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_deprecated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("shutdown_date", sa.Date(), nullable=True),
        sa.Column("metadata_json", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_id", name="uq_ai_catalog_provider_model"),
    )
    op.create_index(
        "ix_ai_catalog_active_models",
        "ai_catalog_models",
        ["provider", "is_active", "opencode_compatible"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_catalog_active_models", table_name="ai_catalog_models")
    op.drop_table("ai_catalog_models")
