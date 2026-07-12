"""Request/response shapes. Fields default to "" so a POST can omit them; PATCH
handlers use model_dump(exclude_unset=True) so only supplied fields change."""
from pydantic import BaseModel, ConfigDict


class ComputerIn(BaseModel):
    name: str = ""
    manufacturer: str = ""
    model: str = ""
    year: str = ""
    chassis: str = ""
    os: str = ""
    cpu: str = ""
    installed_ram: str = ""
    drives: str = ""
    condition: str = ""
    source: str = ""
    acquired_date: str = ""
    image: str = ""
    url: str = ""
    summary: str = ""
    notes: str = ""
    disposed: str = ""


class ComputerOut(ComputerIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str


class PartIn(BaseModel):
    computer_id: str = ""
    type: str = ""
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    year: str = ""
    specs: str = ""
    condition: str = ""
    source: str = ""
    acquired_date: str = ""
    image: str = ""
    url: str = ""
    summary: str = ""
    notes: str = ""
    disposed: str = ""
    disk_image: str = ""


class PartOut(PartIn):
    model_config = ConfigDict(from_attributes=True)
    asset_id: str
