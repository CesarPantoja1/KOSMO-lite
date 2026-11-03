"""drop_activity_diagrams_table

Revision ID: 0023_drop_activity_diagrams_table
Revises: 0022_add_performance_indexes
Create Date: 2026-11-02 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0023_drop_activity_diagrams_table"
down_revision: str | Sequence[str] | None = "0022_add_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Normalizar proyectos en fase 'modelo'
    op.execute("UPDATE projects SET current_phase = 'requisitos' WHERE current_phase = 'modelo'")

    # 2. Limpiar evaluaciones de consistencia relacionadas
    op.execute(
        "DELETE FROM consistency_evaluations "
        "WHERE target_phase = 'modelo' OR source_phase = 'modelo' OR artifact_type = 'ActivityDiagram'"
    )

    # 3. Eliminar indice y tabla
    op.drop_index(op.f("ix_activity_diagrams_feature_id"), table_name="activity_diagrams")
    op.drop_table("activity_diagrams")


def downgrade() -> None:
    op.create_table(
        "activity_diagrams",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("feature_id", sa.String(length=64), nullable=False),
        sa.Column("diagram_syntax", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["features.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activity_diagrams_feature_id"), "activity_diagrams", ["feature_id"], unique=True)
