"""ORM tables. Mirrors the CSV schema of the flat-file system: one shared asset
register across computers + parts. A part's computer_id is a soft link to a
computer's asset_id (blank = standalone / uninstalled)."""
from sqlalchemy import Column, ForeignKey, Integer, String, Text

from .db import Base


def _part_fk():
    """part_id column referencing a part, cascading on delete."""
    return Column(String(16), ForeignKey("parts.asset_id", ondelete="CASCADE"),
                  primary_key=True)


def _part_fk_indexed():
    return Column(String(16), ForeignKey("parts.asset_id", ondelete="CASCADE"),
                  index=True, nullable=False)


class Computer(Base):
    __tablename__ = "computers"
    asset_id = Column(String(16), primary_key=True)
    name = Column(String(255), default="")
    manufacturer = Column(String(255), default="")
    model = Column(String(255), default="")
    year = Column(String(16), default="")
    chassis = Column(String(64), default="")
    os = Column(String(255), default="")
    cpu = Column(String(255), default="")
    installed_ram = Column(String(255), default="")
    drives = Column(Text, default="")
    condition = Column(String(64), default="")
    source = Column(String(255), default="")
    acquired_date = Column(String(32), default="")
    image = Column(String(255), default="")
    url = Column(Text, default="")
    summary = Column(Text, default="")
    notes = Column(Text, default="")
    disposed = Column(String(255), default="")


class Part(Base):
    __tablename__ = "parts"
    asset_id = Column(String(16), primary_key=True)
    computer_id = Column(String(16), index=True, default="")
    type = Column(String(32), default="")
    manufacturer = Column(String(255), default="")
    model = Column(String(255), default="")
    name = Column(String(255), default="")
    year = Column(String(16), default="")
    specs = Column(Text, default="")
    condition = Column(String(64), default="")
    source = Column(String(255), default="")
    acquired_date = Column(String(32), default="")
    image = Column(String(255), default="")
    url = Column(Text, default="")
    summary = Column(Text, default="")
    notes = Column(Text, default="")
    disposed = Column(String(255), default="")
    disk_image = Column(String(255), default="")


# --- normalised spec tables ------------------------------------------------
# One typed row per part for each type that has a fixed set of attributes, plus
# child tables for the genuinely list-shaped motherboard/io fields. These are a
# normalised projection of parts.specs, kept in sync on every write (see
# main.sync_part_specs); parts.specs remains the denormalised cache.


class MotherboardSpec(Base):
    __tablename__ = "motherboard_spec"
    part_id = _part_fk()
    chipset = Column(String(255))
    cpu_family = Column(String(255))
    form_factor = Column(String(64))
    cache = Column(String(64))
    bios = Column(String(255))
    onboard_video = Column(String(255))


class CpuSpec(Base):
    __tablename__ = "cpu_spec"
    part_id = _part_fk()
    socket = Column(String(64))
    speed = Column(String(64))
    fsb = Column(String(64))
    cores = Column(Integer)
    cache = Column(String(64))


class RamSpec(Base):
    __tablename__ = "ram_spec"
    part_id = _part_fk()
    ram_type = Column(String(64))
    size_kb = Column(Integer)
    speed = Column(String(64))


class VideoSpec(Base):
    __tablename__ = "video_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))
    connector = Column(String(255))
    memory_kb = Column(Integer)
    video_type = Column(String(64))


class SoundSpec(Base):
    __tablename__ = "sound_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))
    fm = Column(String(255))
    ports = Column(String(255))


class NetworkSpec(Base):
    __tablename__ = "network_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))
    connector = Column(String(255))


class IoSpec(Base):
    __tablename__ = "io_spec"
    part_id = _part_fk()
    chip = Column(String(255))
    interface = Column(String(64))


class StorageSpec(Base):
    __tablename__ = "storage_spec"
    part_id = _part_fk()
    kind = Column(String(64))
    interface = Column(String(64))
    protocol = Column(String(64))
    capacity = Column(String(64))
    chs_c = Column(Integer)
    chs_h = Column(Integer)
    chs_s = Column(Integer)
    media = Column(String(255))
    speed = Column(String(64))
    role = Column(String(255))


class PartSlot(Base):
    __tablename__ = "part_slot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    bus = Column(String(64))
    count = Column(Integer, default=1)


class PartRamSlot(Base):
    __tablename__ = "part_ram_slot"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    slot_type = Column(String(64))
    count = Column(Integer, default=1)


class PartPort(Base):
    __tablename__ = "part_port"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    port = Column(String(64))
    count = Column(Integer, default=1)


class PartAttribute(Base):
    __tablename__ = "part_attribute"
    id = Column(Integer, primary_key=True, autoincrement=True)
    part_id = _part_fk_indexed()
    akey = Column(String(128), default="")
    avalue = Column(Text, default="")
