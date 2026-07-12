"""normalise part specs into typed + list tables

Revision ID: 0002_normalise_specs
Revises: 0001_initial
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

revision = "0002_normalise_specs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _fk():
    return sa.ForeignKey("parts.asset_id", ondelete="CASCADE")


def upgrade():
    op.create_table(
        "motherboard_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chipset", sa.String(255)),
        sa.Column("cpu_family", sa.String(255)),
        sa.Column("form_factor", sa.String(64)),
        sa.Column("cache", sa.String(64)),
        sa.Column("bios", sa.String(255)),
        sa.Column("onboard_video", sa.String(255)),
    )
    op.create_table(
        "cpu_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("socket", sa.String(64)),
        sa.Column("speed", sa.String(64)),
        sa.Column("fsb", sa.String(64)),
        sa.Column("cores", sa.Integer()),
        sa.Column("cache", sa.String(64)),
    )
    op.create_table(
        "ram_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("ram_type", sa.String(64)),
        sa.Column("size_kb", sa.Integer()),
        sa.Column("speed", sa.String(64)),
    )
    op.create_table(
        "video_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
        sa.Column("connector", sa.String(255)),
        sa.Column("memory_kb", sa.Integer()),
        sa.Column("video_type", sa.String(64)),
    )
    op.create_table(
        "sound_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
        sa.Column("fm", sa.String(255)),
        sa.Column("ports", sa.String(255)),
    )
    op.create_table(
        "network_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
        sa.Column("connector", sa.String(255)),
    )
    op.create_table(
        "io_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("chip", sa.String(255)),
        sa.Column("interface", sa.String(64)),
    )
    op.create_table(
        "storage_spec",
        sa.Column("part_id", sa.String(16), _fk(), primary_key=True),
        sa.Column("kind", sa.String(64)),
        sa.Column("interface", sa.String(64)),
        sa.Column("protocol", sa.String(64)),
        sa.Column("capacity", sa.String(64)),
        sa.Column("chs_c", sa.Integer()),
        sa.Column("chs_h", sa.Integer()),
        sa.Column("chs_s", sa.Integer()),
        sa.Column("media", sa.String(255)),
        sa.Column("speed", sa.String(64)),
        sa.Column("role", sa.String(255)),
    )
    for name, cols in (
        ("part_slot", [sa.Column("bus", sa.String(64)), sa.Column("count", sa.Integer())]),
        ("part_ram_slot", [sa.Column("slot_type", sa.String(64)), sa.Column("count", sa.Integer())]),
        ("part_port", [sa.Column("port", sa.String(64)), sa.Column("count", sa.Integer())]),
        ("part_attribute", [sa.Column("akey", sa.String(128)), sa.Column("avalue", sa.Text())]),
    ):
        op.create_table(
            name,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("part_id", sa.String(16), _fk(), nullable=False, index=True),
            *cols,
        )

    _backfill(op.get_bind())


def _backfill(bind):
    """Populate the new tables from each part's existing specs string."""
    from app import specstruct
    from app.models import (Part, MotherboardSpec, CpuSpec, RamSpec, VideoSpec,
                            SoundSpec, NetworkSpec, IoSpec, StorageSpec,
                            PartSlot, PartRamSlot, PartPort, PartAttribute)
    spec_model = {"motherboard": MotherboardSpec, "cpu": CpuSpec, "ram": RamSpec,
                  "video": VideoSpec, "sound": SoundSpec, "network": NetworkSpec,
                  "io": IoSpec, "storage": StorageSpec}
    sess = Session(bind=bind)
    for p in sess.query(Part).all():
        ptype = p.type or "other"
        st = specstruct.parse(ptype, p.specs or "")
        model = spec_model.get(ptype)
        if model:
            cols = dict(st.scalars)
            if ptype == "storage" and st.chs:
                cols["chs_c"], cols["chs_h"], cols["chs_s"] = st.chs
            sess.add(model(part_id=p.asset_id, **cols))
        for bus, n in st.slots:
            sess.add(PartSlot(part_id=p.asset_id, bus=bus, count=n))
        for slot_type, n in st.ram_slots:
            sess.add(PartRamSlot(part_id=p.asset_id, slot_type=slot_type, count=n))
        for port, n in st.ports:
            sess.add(PartPort(part_id=p.asset_id, port=port, count=n))
        for k, v in st.attributes:
            sess.add(PartAttribute(part_id=p.asset_id, akey=k or "", avalue=v))
    sess.commit()


def downgrade():
    for name in ("part_attribute", "part_port", "part_ram_slot", "part_slot",
                 "storage_spec", "io_spec", "network_spec", "sound_spec",
                 "video_spec", "ram_spec", "cpu_spec", "motherboard_spec"):
        op.drop_table(name)
