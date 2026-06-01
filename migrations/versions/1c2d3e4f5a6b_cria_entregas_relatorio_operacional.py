"""cria entregas relatorio operacional

Revision ID: 1c2d3e4f5a6b
Revises: cff4935c0be5
Create Date: 2026-06-01 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1c2d3e4f5a6b"
down_revision = "cff4935c0be5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_email_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "report_type",
            sa.String(length=50),
            nullable=False,
            server_default="relatorio_operacional",
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("recipient_email", sa.String(length=100), nullable=False),
        sa.Column("janela", sa.String(length=10), nullable=False),
        sa.Column("data_operacional", sa.Date(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("content_summary", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("erro", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_email_deliveries_lookup",
        "notification_email_deliveries",
        ["report_type", "user_id", "janela", "data_operacional", "status"],
    )
    op.create_index(
        "ix_notification_email_deliveries_recipient",
        "notification_email_deliveries",
        ["recipient_email", "janela", "data_operacional"],
    )


def downgrade():
    op.drop_index(
        "ix_notification_email_deliveries_recipient",
        table_name="notification_email_deliveries",
    )
    op.drop_index(
        "ix_notification_email_deliveries_lookup",
        table_name="notification_email_deliveries",
    )
    op.drop_table("notification_email_deliveries")
