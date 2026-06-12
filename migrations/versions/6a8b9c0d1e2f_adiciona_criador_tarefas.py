"""adiciona criador das tarefas

Revision ID: 6a8b9c0d1e2f
Revises: 5e6f7a8b9c0d
Create Date: 2026-06-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "6a8b9c0d1e2f"
down_revision = "5e6f7a8b9c0d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tarefas") as batch_op:
        batch_op.add_column(sa.Column("criado_por_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tarefas_criado_por_id_users",
            "users",
            ["criado_por_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("tarefas") as batch_op:
        batch_op.drop_constraint("fk_tarefas_criado_por_id_users", type_="foreignkey")
        batch_op.drop_column("criado_por_id")
