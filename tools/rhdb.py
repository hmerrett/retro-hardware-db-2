"""API-backed data access + shared helpers for the ported utilities.

A drop-in successor to the flat-file system's scripts/common.py: it exposes the
same helper names, but instead of reading/writing CSVs it talks to the REST API
(the single source of truth). The site builder, label maker and report importer
all import from here, so they read/write exactly what the GUI and MCP server do.

Point it at the API with, in order of precedence: --api on the command line
(scripts set RHDB_API before importing), the RHDB_API env var, config.yml's
api_url, else http://localhost:8000.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR
CONFIG_PATH = BASE_DIR / "config.yml"

TIMEOUT = 30

COMPUTER_COLUMNS = [
    "asset_id", "name", "manufacturer", "model", "year",
    "chassis", "os", "cpu", "installed_ram", "drives", "condition", "source",
    "acquired_date", "image", "url", "summary", "notes", "disposed",
]

PART_COLUMNS = [
    "asset_id", "computer_id", "type", "manufacturer", "model", "name",
    "year", "specs", "condition", "source", "acquired_date",
    "image", "url", "summary", "notes", "disposed", "disk_image",
]

TYPE_ORDER = [
    "motherboard", "cpu", "ram", "video", "sound", "network", "io",
    "storage", "cooler", "peripheral", "other",
]

TYPE_LABELS = {
    "motherboard": "Motherboard", "cpu": "CPU", "ram": "Memory", "video": "Video",
    "sound": "Sound", "network": "Network", "io": "I/O", "storage": "Storage",
    "optical": "Optical drive", "floppy": "Floppy drive", "psu": "Power supply",
    "cooler": "Cooling", "peripheral": "Peripheral", "other": "Other",
}


# --- config ----------------------------------------------------------------

_config_cache = None


def load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    return _config_cache


def api_base() -> str:
    url = (os.getenv("RHDB_API") or load_config().get("api_url")
           or "http://localhost:8000")
    return url.rstrip("/")


def images_dir() -> Path:
    """Photo source dir. A relative path is resolved against the repo root (the
    parent of tools/), so the default '../retro-hardware-database/images' lands
    on the old flat-file repo cloned next to this one."""
    raw = os.getenv("RHDB_IMAGES") or load_config().get("images_dir") or "images"
    p = Path(raw)
    return p if p.is_absolute() else (BASE_DIR.parent / p).resolve()


# --- HTTP / data access ----------------------------------------------------

def _request(method, path, **kwargs):
    resp = requests.request(method, f"{api_base()}{path}", timeout=TIMEOUT, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"API {method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def load_computers() -> list[dict]:
    return _request("GET", "/api/computers")


def load_parts() -> list[dict]:
    return _request("GET", "/api/parts")


def update_computer(asset_id: str, fields: dict) -> dict:
    return _request("PATCH", f"/api/computers/{asset_id}", json=fields)


def update_part(asset_id: str, fields: dict) -> dict:
    return _request("PATCH", f"/api/parts/{asset_id}", json=fields)


def create_part(fields: dict) -> dict:
    return _request("POST", "/api/parts", json=fields)


# --- pure helpers (verbatim from the flat-file common.py) ------------------

def display_name(row: dict) -> str:
    """Best human label: explicit name, else manufacturer + model, else id."""
    if row.get("name"):
        return row["name"]
    joined = " ".join(p for p in (row.get("manufacturer", ""),
                                  row.get("model", "")) if p).strip()
    return joined or row.get("asset_id", "")


def parse_specs(specs: str) -> list[tuple[str, str]]:
    """Turn 'CPU: x | RAM: y' into [('CPU','x'), ('RAM','y')]."""
    out = []
    for chunk in (specs or "").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            out.append((k.strip(), v.strip()))
        else:
            out.append(("", chunk))
    return out


def type_label(t: str) -> str:
    return TYPE_LABELS.get(t, (t or "other").title())


def type_sort_key(t: str) -> int:
    try:
        return TYPE_ORDER.index(t)
    except ValueError:
        return len(TYPE_ORDER)


def url_source(url: str) -> str:
    u = (url or "").lower()
    if not u:
        return ""
    if "wikipedia.org" in u:
        return "wikipedia"
    if "theretroweb.com" in u:
        return "theretroweb"
    return "other"


def url_label(url: str) -> str:
    return {"wikipedia": "Wikipedia",
            "theretroweb": "The Retro Web"}.get(url_source(url), "Reference")


def is_disposed(row) -> bool:
    return bool((row.get("disposed") or "").strip())


def index_by_id(rows: list[dict]) -> dict:
    return {r["asset_id"]: r for r in rows}


def parts_for(computer_id: str, parts: list[dict]) -> list[dict]:
    """Parts installed in / paired with a computer, sorted by type then name."""
    kids = [p for p in parts if p.get("computer_id") == computer_id]
    kids.sort(key=lambda p: (type_sort_key(p.get("type", "")), display_name(p)))
    return kids


def item_url(config: dict, asset_id: str) -> str:
    base = (config.get("base_url") or "").rstrip("/")
    return f"{base}/items/{asset_id}/"


PLACEHOLDER = {
    "computer": "computer", "motherboard": "board", "cpu": "chip", "ram": "ram",
    "video": "card", "sound": "card", "network": "card", "io": "card",
    "storage": "drive", "optical": "disc", "floppy": "floppy", "psu": "psu",
    "cooler": "fan", "peripheral": "keyboard", "other": "box",
}


def placeholder_for(kind_or_type: str) -> str:
    return "placeholders/" + PLACEHOLDER.get(kind_or_type, "box") + ".svg"


KNOWN_SPEC_KEYS = {
    "motherboard": {"Chipset", "Socket", "CPU family", "Form factor",
                    "RAM slots", "Slots", "Cache", "BIOS", "Ports",
                    "Onboard video"},
    "cpu": {"Socket", "Speed", "FSB", "Cores", "Cache", "L1/L2 cache", "L2 cache"},
    "ram": {"Type", "Size", "Speed"},
    "video": {"Interface", "Memory", "Chip", "Chipset", "Type", "Connector"},
    "sound": {"Interface", "Chip", "Chipset", "FM", "Ports"},
    "network": {"Interface", "Connector", "Chip", "Chipset"},
    "io": {"Interface", "Ports", "Chip", "Chipset"},
    "storage": {"Kind", "Interface", "Protocol", "Capacity", "CHS", "Role",
                "Media", "Speed"},
    "optical": {"Media", "Interface", "Speed"},
    "floppy": {"Media", "Interface", "Speed"},
    "psu": {"Form factor", "Wattage", "Connectors"},
    "cooler": {"Type", "Socket"},
}


def validate(computers: list[dict], parts: list[dict]) -> list[str]:
    """Human-readable integrity warnings (empty = all good). Duplicate ids can't
    occur with the DB primary key, but dangling computer_id and stray spec keys
    still can, so the same checks run at build time."""
    warnings = []
    comp_ids = {c["asset_id"] for c in computers}
    for p in parts:
        aid = p.get("asset_id", "")
        cid = p.get("computer_id", "")
        if cid and cid not in comp_ids:
            warnings.append(
                f"part {aid} references unknown computer_id {cid}")
        ptype = p.get("type", "")
        allowed = KNOWN_SPEC_KEYS.get(ptype)
        seen_keys = set()
        for k, v in parse_specs(p.get("specs", "")):
            if v.strip().lower().startswith("http"):
                warnings.append(
                    f"part {aid} has a link in a spec value — put URLs in the "
                    "url column")
            if not k:
                continue
            if k in seen_keys:
                warnings.append(f"part {aid} has duplicate spec key '{k}'")
            seen_keys.add(k)
            if allowed is not None and k not in allowed:
                warnings.append(
                    f"part {aid} unexpected spec key '{k}' for type '{ptype}'")
    return warnings


SHOUT_ACRONYMS = {
    "SCSI", "SATA", "PATA", "EISA", "ESDI", "VESA", "SVGA", "WXGA", "ATAPI",
    "BIOS", "UEFI", "DRAM", "SRAM", "SDRAM", "VRAM", "SIMM", "DIMM", "RIMM",
    "SIPP", "COAST", "CMOS", "MIDI", "EPROM", "EEPROM", "PROM", "MCGA",
    "PLCC", "NTSC", "SECAM", "WLAN", "ASIC",
}


def deshout(text: str) -> str:
    out = []
    for tok in re.split(r"(\s+)", text or ""):
        core = tok.strip(".,:;()[]{}/\\\"'")
        if (core.isalpha() and core.isupper() and len(core) >= 5
                and core not in SHOUT_ACRONYMS):
            i = tok.find(core)
            tok = tok[:i] + core[0] + core[1:].lower() + tok[i + len(core):]
        out.append(tok)
    return "".join(out)


def add_api_arg(parser):
    """Give a script a --api flag; when passed, it wins over env/config by
    setting RHDB_API before any request is made."""
    parser.add_argument("--api", default="",
                        help="REST API base URL (default: RHDB_API / config api_url)")


def apply_api_arg(args):
    if getattr(args, "api", ""):
        os.environ["RHDB_API"] = args.api
