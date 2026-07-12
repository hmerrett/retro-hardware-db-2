# Retro Hardware Database — web stack

The online successor to the flat-file (CSV + `add.py`) system: a MariaDB backend,
a FastAPI REST API (single source of truth for scripts, an MCP wrapper, and the
GUI), and a small server-rendered web GUI for day-to-day editing. Runs under
`docker-compose`.

```
docker-compose
├── db    MariaDB 11            (data volume: dbdata)
├── api   FastAPI + uvicorn     (http://localhost:8000)
│         ├── /            web GUI (list / view / edit computers + parts)
│         ├── /api/...     JSON REST API  (computers, parts)
│         └── /docs        interactive OpenAPI docs
└── mcp   MCP server            (http://localhost:8001/mcp)
          └── native list/get/create/update/delete tools over the REST API
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

## MCP server (AI access)

The `mcp` service (in `mcp/`) is a thin wrapper over the REST API that gives an
AI client native tools:

- `list_computers`, `get_computer`, `create_computer`, `update_computer`, `delete_computer`
- `list_parts` (filter by `computer_id` / `type`), `get_part`, `create_part`, `update_part`, `delete_part`

It holds no data of its own — every call is an HTTP request to `api`, so the MCP
server, the GUI and the ported scripts all read/write the same database. It
speaks the streamable-HTTP transport on `:8001` and comes up with the stack.

**Point Claude Code at it.** A project-scoped `.mcp.json` is committed at the
repo root, so running `claude` in this directory offers the server for approval —
accept it once and the tools are available. Equivalent CLI:

```
claude mcp add --transport http retro-hardware http://localhost:8001/mcp
```

From another machine on the LAN, swap `localhost` for the host (e.g.
`http://192.168.1.2:8001/mcp`). `create_*` assigns the next asset id; `update_*`
only changes the fields you pass.

## Ported utilities (`tools/`)

The flat-file scripts, re-pointed at the REST API instead of the CSVs. They read
(and, for the importer, write) over the network, so they can run on whichever
box has the hardware — e.g. the machine with the DYMO printers and the floppy
reader — against the API on the LAN. Shared data access + config live in
`tools/rhdb.py`; `tools/config.yml` carries the (non-secret) base URL, label and
printer settings.

```
cd tools
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export RHDB_API=http://192.168.1.2:8000        # or pass --api / edit config.yml
```

- **`build_site.py`** — renders the public static site into `tools/site/` (one
  `items/<asset_id>/` page each, so QR codes already printed keep resolving).
  Photos are read from `images_dir` (defaults to the old flat-file repo's
  `images/` until the GUI owns photo storage — step 5).
- **`make_labels.py`** — print-ready label PDFs with a QR to the item's page;
  `--small`, `--auto` (computers → full+small, real parts → small), `--print`
  (macOS/CUPS `lp`). QR encodes `<base_url>/items/<asset_id>/`.
- **`import_report.py`** — reads an HWiNFO/MSD boot-disk report from
  `tools/imports/<asset_id>.txt` and proposes CPU/OS (computer), BIOS/chipset/
  onboard-video/ports (its motherboard) and one storage part per detected drive.
  Nothing is written until you confirm; on confirm it PATCHes/POSTs the API.

### Publishing to GitHub Pages

`tools/publish.sh` builds the site from the API and pushes it into the old
`retro-hardware-database` repo (checked out alongside this one), whose Action now
just **deploys the committed `site/`** — its CSV build step is retired. The API
is LAN-only, so the build has to run on a LAN box rather than in GitHub's CI. The
Pages URL and `/items/<asset_id>/` paths are unchanged, so QR labels already in
the wild keep resolving.

```
cd tools
RHDB_API=http://192.168.1.2:8000 ./publish.sh            # build + push + deploy
RHDB_SITE_REPO=/path/to/retro-hardware-database ./publish.sh   # if not adjacent
```

## Local dev without Docker/MariaDB

## Local dev without Docker/MariaDB

The app falls back to SQLite if you set `DATABASE_URL`:

```
cd api && pip install -r requirements.txt
DATABASE_URL=sqlite:///dev.db uvicorn app.main:app --reload
```

## Status (v0) and what's next

v0 covers the DB, the REST API + OpenAPI, CSV migration, a minimal editing GUI,
and an **MCP server** wrapping the REST API so Claude gets first-class tools.
Planned next:

- Port the utilities to the API: `build_site.py` (public static site + QR
  labels), `make_labels.py` (DYMO), `import_report.py` (boot-disk HWiNFO/MSD).
- Richer bespoke GUI: the guided build walk, storage-kind routing (hard disk →
  part vs floppy/optical/CF-SD → the computer's `drives` field), label buttons,
  photo upload, disposed toggle.
- Alembic migrations; auth if it's exposed beyond the LAN.
