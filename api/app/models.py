"""ORM tables. Mirrors the CSV schema of the flat-file system: one shared asset
register across computers + parts. A part's computer_id is a soft link to a
computer's asset_id (blank = standalone / uninstalled)."""
from sqlalchemy import Column, String, Text

from .db import Base


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
