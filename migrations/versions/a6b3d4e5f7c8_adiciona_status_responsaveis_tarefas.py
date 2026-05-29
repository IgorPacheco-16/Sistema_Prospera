"""adiciona status aos responsaveis de tarefas

Revision ID: a6b3d4e5f7c8
Revises: f4a8c1d2e9b0
Create Date: 2026-05-29 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a6b3d4e5f7c8"
down_revision = "f4a8c1d2e9b0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tarefa_responsaveis_nova",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tarefa_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACEITO"),
        sa.Column("tipo", sa.String(length=20), nullable=False, server_default="ATRIBUICAO"),
        sa.Column("solicitado_por_id", sa.Integer(), nullable=True),
        sa.Column("solicitado_em", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("respondido_em", sa.DateTime(), nullable=True),
        sa.Column("observacao", sa.String(length=1000), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("repasse_lote_id", sa.String(length=36), nullable=True),
        sa.Column("repasse_papel", sa.String(length=20), nullable=True),
        sa.Column("repasse_status", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["solicitado_por_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        INSERT INTO tarefa_responsaveis_nova
            (tarefa_id, usuario_id, status, tipo, solicitado_em, ativo)
        SELECT tarefa_id, user_id, 'ACEITO', 'ATRIBUICAO', CURRENT_TIMESTAMP, 1
        FROM tarefa_responsaveis
        """
    )

    op.drop_table("tarefa_responsaveis")
    op.rename_table("tarefa_responsaveis_nova", "tarefa_responsaveis")


def downgrade():
    op.create_table(
        "tarefa_responsaveis_antiga",
        sa.Column("tarefa_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tarefa_id", "user_id"),
    )

    op.execute(
        """
        INSERT OR IGNORE INTO tarefa_responsaveis_antiga (tarefa_id, user_id)
        SELECT tarefa_id, usuario_id
        FROM tarefa_responsaveis
        WHERE status = 'ACEITO' AND ativo = 1
        """
    )

    op.drop_table("tarefa_responsaveis")
    op.rename_table("tarefa_responsaveis_antiga", "tarefa_responsaveis")
