"""initial schema: computers + parts

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "computers",
        sa.Column("asset_id", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(255)),
        sa.Column("manufacturer", sa.String(255)),
        sa.Column("model", sa.String(255)),
        sa.Column("year", sa.String(16)),
        sa.Column("chassis", sa.String(64)),
        sa.Column("os", sa.String(255)),
        sa.Column("cpu", sa.String(255)),
        sa.Column("installed_ram", sa.String(255)),
        sa.Column("drives", sa.Text()),
        sa.Column("condition", sa.String(64)),
        sa.Column("source", sa.String(255)),
        sa.Column("acquired_date", sa.String(32)),
        sa.Column("image", sa.String(255)),
        sa.Column("url", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("disposed", sa.String(255)),
    )
    op.create_table(
        "parts",
        sa.Column("asset_id", sa.String(16), primary_key=True),
        sa.Column("computer_id", sa.String(16)),
        sa.Column("type", sa.String(32)),
        sa.Column("manufacturer", sa.String(255)),
        sa.Column("model", sa.String(255)),
        sa.Column("name", sa.String(255)),
        sa.Column("year", sa.String(16)),
        sa.Column("specs", sa.Text()),
        sa.Column("condition", sa.String(64)),
        sa.Column("source", sa.String(255)),
        sa.Column("acquired_date", sa.String(32)),
        sa.Column("image", sa.String(255)),
        sa.Column("url", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("disposed", sa.String(255)),
        sa.Column("disk_image", sa.String(255)),
    )
    op.create_index("ix_parts_computer_id", "parts", ["computer_id"])


def downgrade():
    op.drop_index("ix_parts_computer_id", table_name="parts")
    op.drop_table("parts")
    op.drop_table("computers")
