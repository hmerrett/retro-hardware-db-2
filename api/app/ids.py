"""Next free asset id across BOTH tables, e.g. RH-0243 (max numeric + 1)."""
import re

from .models import Computer, Part

PREFIX = "RH-"
PAD = 4


def next_asset_id(db):
    nums = []
    for model in (Computer, Part):
        for (aid,) in db.query(model.asset_id).all():
            m = re.fullmatch(rf"{PREFIX}(\d+)", aid or "")
            if m:
                nums.append(int(m.group(1)))
    nxt = (max(nums) + 1) if nums else 1
    return f"{PREFIX}{nxt:0{PAD}d}"
