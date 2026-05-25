"""adiciona responsaveis em tarefas

Revision ID: e2f6a9c4b8d3
Revises: c7a4d9e2b631
Create Date: 2026-05-25 17:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e2f6a9c4b8d3"
down_revision = "c7a4d9e2b631"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tarefa_responsaveis",
        sa.Column("tarefa_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tarefa_id", "user_id"),
    )


def downgrade():
    op.drop_table("tarefa_responsaveis")
