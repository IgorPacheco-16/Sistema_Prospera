"""adiciona observacao de entrega em tarefas

Revision ID: f4a8c1d2e9b0
Revises: e2f6a9c4b8d3
Create Date: 2026-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4a8c1d2e9b0"
down_revision = "e2f6a9c4b8d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tarefas",
        sa.Column("observacao_entrega", sa.String(length=1000), nullable=True),
    )


def downgrade():
    op.drop_column("tarefas", "observacao_entrega")
