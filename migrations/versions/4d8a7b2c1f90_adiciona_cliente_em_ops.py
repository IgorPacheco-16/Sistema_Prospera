"""adiciona cliente em ops

Revision ID: 4d8a7b2c1f90
Revises: 9f3c2a1b7e4d
Create Date: 2026-05-20 11:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d8a7b2c1f90"
down_revision = "9f3c2a1b7e4d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ops", sa.Column("cliente", sa.String(length=200), nullable=True))


def downgrade():
    op.drop_column("ops", "cliente")
