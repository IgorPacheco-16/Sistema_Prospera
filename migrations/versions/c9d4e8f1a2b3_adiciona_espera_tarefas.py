"""adiciona solicitacoes de espera em tarefas

Revision ID: c9d4e8f1a2b3
Revises: b7c9a1d2e3f4
Create Date: 2026-05-29 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9d4e8f1a2b3"
down_revision = "b7c9a1d2e3f4"
branch_labels = None
depends_on = None


TAREFA_COLUMNS = (
    ("em_espera", sa.Boolean(), False),
    ("espera_motivo_atual", sa.String(length=1000), True),
    ("espera_aprovada_em", sa.DateTime(), True),
    ("espera_aprovada_por_id", sa.Integer(), True),
    ("espera_solicitacao_atual_id", sa.Integer(), True),
)


def _table_exists(table_name):
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _columns(table_name):
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    if not _table_exists("tarefa_espera_solicitacoes"):
        op.create_table(
            "tarefa_espera_solicitacoes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tarefa_id", sa.Integer(), nullable=False),
            sa.Column("solicitado_por_id", sa.Integer(), nullable=False),
            sa.Column("motivo", sa.String(length=1000), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="PENDENTE", nullable=False),
            sa.Column("respondido_por_id", sa.Integer(), nullable=True),
            sa.Column("solicitado_em", sa.DateTime(), nullable=False),
            sa.Column("respondido_em", sa.DateTime(), nullable=True),
            sa.Column("justificativa_resposta", sa.String(length=1000), nullable=True),
            sa.Column("status_anterior_tarefa", sa.String(length=30), nullable=True),
            sa.Column("ativo", sa.Boolean(), server_default="1", nullable=False),
            sa.ForeignKeyConstraint(["respondido_por_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["solicitado_por_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["tarefa_id"], ["tarefas.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_tarefa_espera_solicitacoes_tarefa_status",
            "tarefa_espera_solicitacoes",
            ["tarefa_id", "status", "ativo"],
        )

    existing = _columns("tarefas")
    missing = [column for column in TAREFA_COLUMNS if column[0] not in existing]
    if missing:
        with op.batch_alter_table("tarefas") as batch_op:
            for name, column_type, nullable in missing:
                if name == "em_espera":
                    batch_op.add_column(
                        sa.Column(
                            name,
                            column_type,
                            nullable=False,
                            server_default="0",
                        )
                    )
                else:
                    batch_op.add_column(sa.Column(name, column_type, nullable=nullable))

    # SQLite batch mode keeps these nullable columns simple; ORM relationships
    # still enforce the intended links when the app writes them.


def downgrade():
    existing = _columns("tarefas")
    columns_to_drop = [name for name, _column_type, _nullable in TAREFA_COLUMNS if name in existing]
    if columns_to_drop:
        with op.batch_alter_table("tarefas") as batch_op:
            for name in columns_to_drop:
                batch_op.drop_column(name)

    if _table_exists("tarefa_espera_solicitacoes"):
        op.drop_index(
            "ix_tarefa_espera_solicitacoes_tarefa_status",
            table_name="tarefa_espera_solicitacoes",
        )
        op.drop_table("tarefa_espera_solicitacoes")
