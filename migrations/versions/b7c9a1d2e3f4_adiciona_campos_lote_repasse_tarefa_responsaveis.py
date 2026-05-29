"""adiciona campos de lote de repasse em tarefa_responsaveis

Revision ID: b7c9a1d2e3f4
Revises: a6b3d4e5f7c8
Create Date: 2026-05-29 12:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c9a1d2e3f4"
down_revision = "a6b3d4e5f7c8"
branch_labels = None
depends_on = None


COLUMNS = (
    ("repasse_lote_id", sa.String(length=36)),
    ("repasse_papel", sa.String(length=20)),
    ("repasse_status", sa.String(length=20)),
)


def _existing_columns():
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("tarefa_responsaveis")}


def upgrade():
    existing_columns = _existing_columns()
    missing_columns = [
        (name, column_type)
        for name, column_type in COLUMNS
        if name not in existing_columns
    ]

    if not missing_columns:
        return

    with op.batch_alter_table("tarefa_responsaveis") as batch_op:
        for name, column_type in missing_columns:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))


def downgrade():
    existing_columns = _existing_columns()
    columns_to_drop = [
        name
        for name, _column_type in COLUMNS
        if name in existing_columns
    ]

    if not columns_to_drop:
        return

    with op.batch_alter_table("tarefa_responsaveis") as batch_op:
        for name in columns_to_drop:
            batch_op.drop_column(name)
