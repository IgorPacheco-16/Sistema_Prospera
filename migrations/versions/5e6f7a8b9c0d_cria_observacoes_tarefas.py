"""cria observacoes de tarefas

Revision ID: 5e6f7a8b9c0d
Revises: 2b4c6d8e0f12
Create Date: 2026-06-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5e6f7a8b9c0d"
down_revision = "2b4c6d8e0f12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tarefa_observacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tarefa_id", sa.Integer(), nullable=False),
        sa.Column("autor_id", sa.Integer(), nullable=True),
        sa.Column("texto", sa.String(length=1000), nullable=False),
        sa.Column("criada_em", sa.DateTime(), nullable=False),
        sa.Column("deletada_em", sa.DateTime(), nullable=True),
        sa.Column("deletada_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["autor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["deletada_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tarefa_observacoes_tarefa_ativa",
        "tarefa_observacoes",
        ["tarefa_id", "deletada_em", "criada_em"],
    )
    op.create_index(
        "ix_tarefa_observacoes_autor",
        "tarefa_observacoes",
        ["autor_id"],
    )


def downgrade():
    op.drop_index("ix_tarefa_observacoes_autor", table_name="tarefa_observacoes")
    op.drop_index("ix_tarefa_observacoes_tarefa_ativa", table_name="tarefa_observacoes")
    op.drop_table("tarefa_observacoes")
