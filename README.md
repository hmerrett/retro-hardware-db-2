# Retro Hardware Database

A catalogue of retro PCs and the parts they are built from. It runs under Docker
Compose and has four services:

```
docker compose
├── caddy  reverse proxy, auto HTTPS   (:80 and :443, https://db.2600.me)
│          proxies to api, Let's Encrypt certificate
├── db     MariaDB 11                   (volume: dbdata)
├── api    FastAPI + uvicorn            (127.0.0.1:8000, public via caddy)
│          /            web GUI (public read-only, login to edit)
│          /api/...     JSON REST API (login required)
│          /images/...  uploaded photos (volume: images)
│          /docs        OpenAPI docs (login required)
└── mcp    MCP server                   (127.0.0.1:8001/mcp)
           list/get/create/update/delete tools over the REST API
```

Anyone can browse the gallery and item pages at https://db.2600.me without
logging in. Editing, photo upload, the JSON API and the docs need an HTTP Basic
login. Only Caddy is exposed to the internet, on ports 80 and 443; the API and
MCP server listen on localhost and are reached through the proxy or on the host.

## Data model

Two tables share a single asset register (RH-0001, RH-0002, and so on).
`computers` holds each machine and `parts` holds each component. A part's
`computer_id` points at the computer it is installed in, or is blank for a
standalone spare. A computer carries its CPU, installed RAM and
floppy/optical/CF-SD drives as attributes of the machine; mechanical hard disks,
tape and expansion cards are parts.

Part specifications are stored in dedicated tables rather than a single field.
Each part type has a table of typed columns: `motherboard_spec`, `cpu_spec`,
`ram_spec`, `video_spec`, `sound_spec`, `network_spec`, `io_spec` and
`storage_spec`. Fields that are naturally lists have child tables (`part_slot`,
`part_ram_slot`, `part_port`), and free-form types use `part_attribute`
key/value rows. This keeps specifications queryable, for example finding every
board with a VLB slot. The `parts.specs` text column holds a `Key: value | ...`
rendering of the same data, refreshed on every write (see `app/specstruct.py`
and `sync_part_specs`), and drives the search index and label text.

## Quick start

```
cp .env.example .env
docker compose up --build
```

Set the database passwords in `.env`. Optionally set `RHDB_AUTH_USER` and
`RHDB_AUTH_PASSWORD` for the login, and `RHDB_BASE_URL` for the hostname the
labels encode. On the host the GUI is at http://localhost:8000 and the docs at
`/docs`. In production Caddy serves it over HTTPS; see Access and HTTPS below.

## Import from CSV

`tools/migrate_csv.py` loads `computers.csv` and `parts.csv` into the database,
preserving asset ids. It upserts by asset id, so it is safe to run repeatedly.
Run it inside the api container, or against the database with `DATABASE_URL`:

```
DATABASE_URL=mysql+pymysql://retro:PASS@localhost:3306/retro \
    python tools/migrate_csv.py --data /path/to/data
```

## REST API

| Method | Path | |
|---|---|---|
| GET, POST | `/api/computers`, `/api/parts` | list, or create (server assigns the next asset id) |
| GET, PATCH, DELETE | `/api/computers/{id}`, `/api/parts/{id}` | fetch, partial update, delete |

`GET /api/parts?computer_id=RH-0010` and `?type=sound` filter the list. PATCH
changes only the fields you send. The full schema and an interactive console are
at `/docs`.

## MCP server

The `mcp` service wraps the REST API and exposes tools over the Model Context
Protocol:

- `list_computers`, `get_computer`, `create_computer`, `update_computer`, `delete_computer`
- `list_parts` (filter by `computer_id` or `type`), `get_part`, `create_part`, `update_part`, `delete_part`

It stores nothing of its own; every call is an HTTP request to the API, so the
MCP server, the GUI and the command-line tools all work against the same
database. It uses the streamable-HTTP transport on port 8001 and starts with the
stack. Point an MCP client at the endpoint; a project `.mcp.json` is committed at
the repo root, and the URL is:

```
http://localhost:8001/mcp
```

`create_*` assigns the next asset id; `update_*` changes only the fields you pass.

## Command-line tools (`tools/`)

These talk to the REST API over the network, so they can run on whichever
machine has the hardware attached (for example the one with the DYMO printers
and the floppy reader). Shared access and configuration live in `tools/rhdb.py`
and `tools/config.yml` (base URL, label sizes, printer names; nothing secret).

```
cd tools
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export RHDB_API=http://localhost:8000
```

- `build_site.py` builds a static copy of the catalogue into `tools/site/`, one
  page per item at `items/<asset_id>/`. Photos come from the API over HTTP by
  default; point it at a local directory with `RHDB_IMAGES` or `--images` to
  build from files.
- `make_labels.py` produces label PDFs with a QR code for each item. Options:
  `--small`, `--auto` (a full and small label for a computer, a small label for a
  real part), and `--print` (macOS/CUPS `lp`). The QR encodes
  `<base_url>/items/<asset_id>/`, which the app resolves to the right computer or
  part page; `base_url` defaults to https://db.2600.me. The GUI also renders
  labels for download.
- `import_report.py` reads an HWiNFO or MSD boot-disk report from
  `tools/imports/<asset_id>.txt` and proposes updates: CPU and OS on the
  computer, BIOS, chipset, onboard video and ports on its motherboard, and a
  storage part per detected drive. It writes nothing until you confirm.

### Publishing a static site

`tools/publish.sh` builds the catalogue from the API and pushes it to a GitHub
Pages repository checked out alongside this one, whose workflow deploys the
committed `site/` folder. The build runs locally because the API is not
reachable from GitHub's runners.

```
RHDB_API=http://localhost:8000 ./publish.sh
RHDB_SITE_REPO=/path/to/pages-repo ./publish.sh   (if not adjacent)
```

## Access and HTTPS

Reads are public; writes need a login. Anonymous requests may GET the gallery,
item pages, photos and static assets. The new and edit forms, label PDFs, all
writes (POST, PATCH, DELETE), the JSON API and `/docs` require authentication,
configured with `RHDB_AUTH_USER` and `RHDB_AUTH_PASSWORD` in `.env` (leave both
blank to run without auth for local development). The browser signs in through a
login page and gets a signed session cookie, with a log out button in the
header. The JSON API and `/docs` also accept HTTP Basic, which is how the MCP
server and command-line tools authenticate (the tools also accept `auth_user`
and `auth_password` in `tools/config.yml`). The cookie is signed with
`RHDB_SECRET_KEY`. Editing controls appear only when logged in.

The `caddy` service terminates HTTPS. It obtains and renews a Let's Encrypt
certificate for the hostname in `caddy/Caddyfile` (`db.2600.me`) and proxies to
the app. To use a different hostname, edit the Caddyfile and restart Caddy; DNS
must point at the host and ports 80 and 443 must be reachable for the ACME
challenge.

## Migrations

Alembic manages the schema, and the api runs `alembic upgrade head` on start
(see `api/entrypoint.sh`). To change the schema, edit `api/app/models.py` and
then:

```
docker compose exec api alembic revision --autogenerate -m "describe change"
docker compose exec api alembic upgrade head
```

## Backups

The data lives in two Docker volumes: `dbdata` (the database) and `images` (the
photos). `tools/backup.sh` writes a timestamped database dump and photo archive
to `./backups` (override with `RHDB_BACKUP_DIR`):

```
tools/backup.sh
```

It dumps the database with `mariadb-dump` and tars the photos; restore
instructions are in the script header. Copy `backups/` off the host for an
off-site copy.

## Local development

The app falls back to SQLite if you set `DATABASE_URL`:

```
cd api && pip install -r requirements.txt
DATABASE_URL=sqlite:///dev.db uvicorn app.main:app --reload
```
