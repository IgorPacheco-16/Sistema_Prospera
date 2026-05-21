"""adiciona email_enviado em notificacoes

Revision ID: b13f2a7c9d01
Revises: 4d8a7b2c1f90
Create Date: 2026-05-21 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b13f2a7c9d01"
down_revision = "4d8a7b2c1f90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "notificacoes",
        sa.Column(
            "email_enviado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("notificacoes", "email_enviado")
