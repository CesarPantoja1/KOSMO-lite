"""add performance indexes for concurrent users

Revision ID: 0022_add_performance_indexes
Revises: 0021_add_missing_fk_constraints
Create Date: 2026-09-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_add_performance_indexes"
down_revision: str | None = "0021_add_missing_fk_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # feature_implementations.status — usado por recover_zombie_implementations cada 100s
    op.create_index(
        "ix_feature_implementations_status",
        "feature_implementations",
        ["status"],
        if_not_exists=True,
    )
    # chat_messages (session_id, role, created_at) — usado por _first_user_messages
    op.create_index(
        "ix_chat_messages_session_role_created",
        "chat_messages",
        ["session_id", "role", "created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session_role_created", table_name="chat_messages")
    op.drop_index("ix_feature_implementations_status", table_name="feature_implementations")
