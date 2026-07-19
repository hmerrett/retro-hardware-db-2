"""per-item change log / notes

Revision ID: 0004_log_entry
Revises: 0003_part_parent
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_log_entry"
down_revision = "0003_part_parent"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "log_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("asset_id", sa.String(16), index=True),
        sa.Column("created_at", sa.DateTime(), index=True),
        sa.Column("kind", sa.String(16)),
        sa.Column("message", sa.Text()),
    )


def downgrade():
    op.drop_table("log_entry")
