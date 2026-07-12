"""MCP server for the Retro Hardware Database.

A thin wrapper over the REST API (the single source of truth) that exposes
native tools to list / get / create / update / delete computers and parts over
the Model Context Protocol. It holds no data itself -- every tool call is an HTTP
request to the API, so the MCP server, the GUI and the ported scripts all see
exactly the same data.

Runs over the streamable-HTTP transport so it can live as its own always-on
docker-compose service. Point a client at http://<host>:8001/mcp.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

# If the API requires HTTP Basic auth, forward the same credentials.
_AUTH_USER = os.getenv("RHDB_AUTH_USER", "")
_AUTH_PASS = os.getenv("RHDB_AUTH_PASSWORD", "")
API_AUTH = (_AUTH_USER, _AUTH_PASS) if _AUTH_USER and _AUTH_PASS else None

mcp = FastMCP(
    "retro-hardware",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8001")),
)


def _client():
    return httpx.Client(base_url=API_BASE_URL, timeout=30.0, auth=API_AUTH)


def _request(method, path, *, params=None, json=None):
    """One HTTP call to the API, returning parsed JSON. Raises with the API's
    own error body attached so the caller sees why a call failed (e.g. 404)."""
    with _client() as c:
        resp = c.request(method, path, params=params, json=json)
    if resp.status_code >= 400:
        raise RuntimeError(f"API {method} {path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _clean(fields):
    """Drop unset (None) fields so create/update only send what was supplied --
    this is what makes update a genuine partial (PATCH) of just those columns."""
    return {k: v for k, v in fields.items() if v is not None}


# --- computers -------------------------------------------------------------

@mcp.tool()
def list_computers() -> list[dict]:
    """List every computer (whole machine) in the asset register."""
    return _request("GET", "/api/computers")


@mcp.tool()
def get_computer(asset_id: str) -> dict:
    """Fetch one computer by its asset id, e.g. RH-0001."""
    return _request("GET", f"/api/computers/{asset_id}")


@mcp.tool()
def create_computer(
    name: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    year: str | None = None,
    chassis: str | None = None,
    os: str | None = None,
    cpu: str | None = None,
    installed_ram: str | None = None,
    drives: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: str | None = None,
) -> dict:
    """Create a computer. The server assigns the next asset id across both
    tables. CPU, installed_ram and drives (floppy/optical/CF-SD, ';'-separated)
    are attributes of the computer, not separate parts."""
    return _request("POST", "/api/computers", json=_clean(locals()))


@mcp.tool()
def update_computer(
    asset_id: str,
    name: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    year: str | None = None,
    chassis: str | None = None,
    os: str | None = None,
    cpu: str | None = None,
    installed_ram: str | None = None,
    drives: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: str | None = None,
) -> dict:
    """Partial-update a computer: only the fields you pass are changed. Set
    disposed to a note/date to flag it disposed; pass an empty string to clear."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/computers/{asset_id}", json=fields)


@mcp.tool()
def delete_computer(asset_id: str) -> dict:
    """Delete a computer by asset id. Its parts are not deleted; they keep their
    computer_id (fix or clear those separately)."""
    return _request("DELETE", f"/api/computers/{asset_id}")


# --- parts -----------------------------------------------------------------

@mcp.tool()
def list_parts(computer_id: str | None = None, type: str | None = None) -> list[dict]:
    """List parts, optionally filtered. Pass computer_id (e.g. RH-0001) for one
    machine's parts, or an empty string for standalone parts. Pass type to filter
    by kind: motherboard, cpu, ram, video, sound, network, io, storage, cooler,
    peripheral, other."""
    params = {}
    if computer_id is not None:
        params["computer_id"] = computer_id
    if type is not None:
        params["type"] = type
    return _request("GET", "/api/parts", params=params)


@mcp.tool()
def get_part(asset_id: str) -> dict:
    """Fetch one part by its asset id, e.g. RH-0003."""
    return _request("GET", f"/api/parts/{asset_id}")


@mcp.tool()
def create_part(
    computer_id: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    name: str | None = None,
    year: str | None = None,
    specs: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: str | None = None,
    disk_image: str | None = None,
) -> dict:
    """Create a part. The server assigns the next asset id. computer_id soft-links
    it to a computer (blank = standalone). specs is free text formatted
    'Key: value | Key: value'. Storage parts are mechanical hard disks and tape
    (type 'storage', with a 'Kind' spec); the motherboard carries Chipset, CPU
    family, Form factor, RAM slots, Slots, Cache, BIOS, Onboard video, Ports."""
    return _request("POST", "/api/parts", json=_clean(locals()))


@mcp.tool()
def update_part(
    asset_id: str,
    computer_id: str | None = None,
    type: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    name: str | None = None,
    year: str | None = None,
    specs: str | None = None,
    condition: str | None = None,
    source: str | None = None,
    acquired_date: str | None = None,
    image: str | None = None,
    url: str | None = None,
    summary: str | None = None,
    notes: str | None = None,
    disposed: str | None = None,
    disk_image: str | None = None,
) -> dict:
    """Partial-update a part: only the fields you pass are changed. To move a part
    to another machine set computer_id; to make it standalone set it to ''."""
    fields = _clean(locals())
    fields.pop("asset_id")
    return _request("PATCH", f"/api/parts/{asset_id}", json=fields)


@mcp.tool()
def delete_part(asset_id: str) -> dict:
    """Delete a part by asset id."""
    return _request("DELETE", f"/api/parts/{asset_id}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
