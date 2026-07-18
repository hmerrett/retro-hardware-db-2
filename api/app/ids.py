"""Allocate an asset id, unique across BOTH tables (computers + parts).

Historic ids are sequential (RH-0001); newly created ones are RH- followed by
four random uppercase hex characters, e.g. RH-3F9A. A random id keeps the shared
register simple and avoids leaking how many items exist.
"""
import secrets

from .models import Computer, Part

PREFIX = "RH-"


def _random_id():
    return PREFIX + secrets.token_hex(2).upper()


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
