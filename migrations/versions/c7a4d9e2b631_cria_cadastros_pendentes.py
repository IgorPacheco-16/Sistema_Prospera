"""cria cadastros pendentes

Revision ID: c7a4d9e2b631
Revises: b13f2a7c9d01
Create Date: 2026-05-25 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7a4d9e2b631"
down_revision = "b13f2a7c9d01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cadastros_pendentes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("codigo_hash", sa.String(length=255), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verificado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )


def downgrade():
    op.drop_table("cadastros_pendentes")
