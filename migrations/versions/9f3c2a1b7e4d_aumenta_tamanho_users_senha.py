"""aumenta tamanho users senha

Revision ID: 9f3c2a1b7e4d
Revises: 0a9551ba0ccd
Create Date: 2026-05-19 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f3c2a1b7e4d"
down_revision = "0a9551ba0ccd"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "senha",
            existing_type=sa.String(length=100),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "senha",
            existing_type=sa.String(length=255),
            type_=sa.String(length=100),
            existing_nullable=True,
        )
