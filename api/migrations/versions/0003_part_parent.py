"""associate a part with a host part (e.g. a disk on a controller card)

Revision ID: 0003_part_parent
Revises: 0002_normalise_specs
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_part_parent"
down_revision = "0002_normalise_specs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("parts", sa.Column("parent_id", sa.String(16), server_default=""))
    op.create_index("ix_parts_parent_id", "parts", ["parent_id"])


def downgrade():
    op.drop_index("ix_parts_parent_id", table_name="parts")
    op.drop_column("parts", "parent_id")
