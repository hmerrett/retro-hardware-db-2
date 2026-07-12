#!/usr/bin/env python3
"""Load the flat-file CSVs (computers.csv, parts.csv) into the database,
preserving the existing asset ids. Idempotent -- re-run to refresh (upsert by
asset_id), so data you keep adding in the CSV world can be re-imported at cutover.

    DATABASE_URL=mysql+pymysql://retro:retro@localhost:3306/retro \\
        python tools/migrate_csv.py --data ../retro-hardware-database/data

    # quick local test with SQLite:
    DATABASE_URL=sqlite:///dev.db python tools/migrate_csv.py --data /path/to/data
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from app.db import Base, SessionLocal, engine
from app.models import Computer, Part


def load(db, path, model):
    cols = {c.name for c in model.__table__.columns}
    n = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data = {k: (v or "") for k, v in row.items() if k in cols}
            if not data.get("asset_id"):
                continue
            db.merge(model(**data))
            n += 1
    db.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="path to the flat-file data/ folder")
    args = ap.parse_args()
    Base.metadata.create_all(bind=engine)
    d = Path(args.data)
    db = SessionLocal()
    try:
        c = load(db, d / "computers.csv", Computer)
        p = load(db, d / "parts.csv", Part)
    finally:
        db.close()
    print(f"loaded {c} computers, {p} parts")


if __name__ == "__main__":
    main()
