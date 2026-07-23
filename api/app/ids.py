"""Allocate an asset id, unique across BOTH tables (computers + parts).

Historic ids are sequential (RH-0001); newly created ones are RH- followed by
four random uppercase alphanumeric characters, e.g. RH-K7Q2. Ids are treated
case-insensitively (lookups uppercase the id), so RH-k7q2 finds RH-K7Q2.
"""
import secrets
import string

from .models import Computer, Part

PREFIX = "RH-"
ALPHABET = string.ascii_uppercase + string.digits


def _random_id():
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(4))


def next_asset_id(db):
    taken = set()
    for model in (Computer, Part):
        for (aid,) in db.query(model.asset_id).all():
            taken.add(aid)
    for _ in range(10000):
        candidate = _random_id()
        if candidate not in taken:
            return candidate
    raise RuntimeError("could not allocate a free asset id")
