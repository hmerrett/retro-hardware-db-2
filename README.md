# Retro Hardware Database — web stack

The online successor to the flat-file (CSV + `add.py`) system: a MariaDB backend,
a FastAPI REST API (single source of truth for scripts, an MCP wrapper, and the
GUI), and a small server-rendered web GUI for day-to-day editing. Runs under
`docker-compose`.

```
docker-compose
├── db    MariaDB 11            (data volume: dbdata)
└── api   FastAPI + uvicorn     (http://localhost:8000)
          ├── /            web GUI (list / view / edit computers + parts)
          ├── /api/...     JSON REST API  (computers, parts)
          └── /docs        interactive OpenAPI docs
```

Data model mirrors the CSV world: one shared asset register (`RH-0001`…) across
two tables — `computers` and `parts` — where a part's `computer_id` softly links
it to a computer (blank = standalone). CPU, RAM and floppy/optical/CF-SD drives
are computer attributes; mechanical hard disks, tape and expansion cards are parts.

## Quick start

```
cp .env.example .env          # set DB_PASSWORD / DB_ROOT_PASSWORD
docker compose up --build     # api on :8000, db on its volume
```

Open http://localhost:8000 (GUI) and http://localhost:8000/docs (API).

## Seed from the existing CSVs

One-off (re-runnable) import that preserves asset ids. Point it at the flat-file
repo's `data/` folder. Run it against the running DB:

```
docker compose exec api python -c "import sys"   # (api is up)
DATABASE_URL=mysql+pymysql://retro:PASS@localhost:3306/retro \
    python tools/migrate_csv.py --data ../retro-hardware-database/data
```

or run the migration inside the container after copying the CSVs in. Because it
upserts by asset id, you can keep adding data in the CSV system and re-import at
cutover without duplicates.

## API sketch

| Method | Path | |
|---|---|---|
| GET/POST | `/api/computers`, `/api/parts` | list / create (server assigns the next asset id) |
| GET/PATCH/DELETE | `/api/computers/{id}`, `/api/parts/{id}` | fetch / partial-update / delete |

`GET /api/parts?computer_id=RH-0010` and `?type=sound` filter. PATCH only changes
the fields you send. Full schema + try-it-out at `/docs`.

## Local dev without Docker/MariaDB

The app falls back to SQLite if you set `DATABASE_URL`:

```
cd api && pip install -r requirements.txt
DATABASE_URL=sqlite:///dev.db uvicorn app.main:app --reload
```

## Status (v0) and what's next

v0 covers the DB, the REST API + OpenAPI, CSV migration, and a minimal editing
GUI. Planned next:

- **MCP server** wrapping the REST API so Claude gets first-class tools.
- Port the utilities to the API: `build_site.py` (public static site + QR
  labels), `make_labels.py` (DYMO), `import_report.py` (boot-disk HWiNFO/MSD).
- Richer bespoke GUI: the guided build walk, storage-kind routing (hard disk →
  part vs floppy/optical/CF-SD → the computer's `drives` field), label buttons,
  photo upload, disposed toggle.
- Alembic migrations; auth if it's exposed beyond the LAN.
