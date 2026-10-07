"""add missing fk constraints for chat_sessions, consistency_evaluations, user_preferences

Revision ID: 0021_add_missing_fk_constraints
Revises: 0020_add_deployment_service_name
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_add_missing_fk_constraints"
down_revision: str | None = "0020_add_deployment_service_name"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_chat_sessions_project",
        "chat_sessions",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_consistency_evaluations_project",
        "consistency_evaluations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_user_preferences_user",
        "user_preferences",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_preferences_user", "user_preferences", type_="foreignkey")
    op.drop_constraint("fk_consistency_evaluations_project", "consistency_evaluations", type_="foreignkey")
    op.drop_constraint("fk_chat_sessions_project", "chat_sessions", type_="foreignkey")
