"""cria solicitacoes tarefa

Revision ID: 2b4c6d8e0f12
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2b4c6d8e0f12"
down_revision = "1c2d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tarefa_solicitacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("op_id", sa.Integer(), nullable=False),
        sa.Column("setor_solicitante_id", sa.Integer(), nullable=False),
        sa.Column("setor_destino_id", sa.Integer(), nullable=False),
        sa.Column("solicitado_por_id", sa.Integer(), nullable=False),
        sa.Column("tarefa_id", sa.Integer(), nullable=True),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("justificativa", sa.String(length=1000), nullable=False),
        sa.Column("prazo_sugerido", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="PENDENTE", nullable=False),
        sa.Column("solicitado_em", sa.DateTime(), nullable=False),
        sa.Column("respondido_por_id", sa.Integer(), nullable=True),
        sa.Column("respondido_em", sa.DateTime(), nullable=True),
        sa.Column("justificativa_resposta", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["op_id"], ["ops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["respondido_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["setor_destino_id"], ["setor.id"]),
        sa.ForeignKeyConstraint(["setor_solicitante_id"], ["setor.id"]),
        sa.ForeignKeyConstraint(["solicitado_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tarefa_solicitacoes_op_status",
        "tarefa_solicitacoes",
        ["op_id", "status"],
    )
    op.create_index(
        "ix_tarefa_solicitacoes_setor_destino_status",
        "tarefa_solicitacoes",
        ["setor_destino_id", "status"],
    )


def downgrade():
    op.drop_index("ix_tarefa_solicitacoes_setor_destino_status", table_name="tarefa_solicitacoes")
    op.drop_index("ix_tarefa_solicitacoes_op_status", table_name="tarefa_solicitacoes")
    op.drop_table("tarefa_solicitacoes")
