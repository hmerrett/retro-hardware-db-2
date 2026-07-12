"""Retro Hardware Database — FastAPI backend.

Two surfaces over the same MariaDB:
  * JSON API under /api  (used by scripts, the MCP wrapper, and the GUI)
  * a bespoke server-rendered GUI that mirrors the flat-file add.py workflow:
    the guided build walk (computer -> link/create motherboard -> parts by
    category), storage-kind routing, CPU/RAM as computer fields, photo upload,
    a disposed toggle, print-label PDFs, and a searchable/filterable index.

Interactive API docs live at /docs (OpenAPI).
"""
import base64
import os
import secrets
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import entry, labels
from .db import get_db
from .ids import next_asset_id
from .models import Computer, Part
from .schemas import ComputerIn, ComputerOut, PartIn, PartOut

# Schema is owned by Alembic now (entrypoint.sh runs `alembic upgrade head` on
# start); no create_all here.

app = FastAPI(title="Retro Hardware Database API", version="0.3.0")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
templates.env.globals.update(
    display_name=entry.display_name, type_label=entry.type_label,
    parse_specs=entry.parse_specs, TYPE_ORDER=entry.TYPE_ORDER)

AUTH_USER = os.getenv("RHDB_AUTH_USER", "")
AUTH_PASS = os.getenv("RHDB_AUTH_PASSWORD", "")


def _valid_creds(request: Request) -> bool:
    """True if the request carries the right HTTP Basic credentials -- or if auth
    is disabled (no env creds), in which case everything is treated as allowed."""
    if not (AUTH_USER and AUTH_PASS):
        return True
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            u, _, p = base64.b64decode(header[6:]).decode("utf-8").partition(":")
            return (secrets.compare_digest(u, AUTH_USER)
                    and secrets.compare_digest(p, AUTH_PASS))
        except Exception:
            return False
    return False


def _is_public_read(request: Request) -> bool:
    """Anonymous visitors get read-only GETs: the gallery, item pages, photos and
    static assets. Editing GETs (new/edit forms, labels), the JSON API and /docs
    stay private, and every write (POST/PATCH/DELETE) requires login."""
    if request.method != "GET":
        return False
    path = request.url.path
    if path == "/" or path.startswith("/images/") or path.startswith("/static/"):
        return True
    if path.startswith("/computers/") or path.startswith("/parts/"):
        if path.endswith("/new") or "/edit" in path or "/label.pdf" in path:
            return False
        return True
    return False


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Public read-only browsing; login required to edit. request.state.authed
    tells templates whether to show the editing controls."""
    authed = _valid_creds(request)
    request.state.authed = authed
    if not authed and not _is_public_read(request):
        return Response("Authentication required", status_code=401, headers={
            "WWW-Authenticate": 'Basic realm="Retro Hardware Database"'})
    return await call_next(request)


COMPUTER_FIELDS = [c.name for c in Computer.__table__.columns if c.name != "asset_id"]
PART_FIELDS = [c.name for c in Part.__table__.columns if c.name != "asset_id"]

IMAGES_DIR = Path("/app/images")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
for sub in ("computers", "parts"):
    (IMAGES_DIR / sub).mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
          name="static")


def get_or_404(db, model, aid):
    obj = db.get(model, aid)
    if not obj:
        raise HTTPException(404, f"{model.__tablename__} {aid} not found")
    return obj


def to_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


# --- JSON API: computers ---------------------------------------------------

@app.get("/api/computers", response_model=list[ComputerOut], tags=["computers"])
def api_list_computers(db: Session = Depends(get_db)):
    return db.query(Computer).order_by(Computer.asset_id).all()


@app.post("/api/computers", response_model=ComputerOut, tags=["computers"])
def api_create_computer(data: ComputerIn, db: Session = Depends(get_db)):
    obj = Computer(asset_id=next_asset_id(db), **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_get_computer(aid: str, db: Session = Depends(get_db)):
    return get_or_404(db, Computer, aid)


@app.patch("/api/computers/{aid}", response_model=ComputerOut, tags=["computers"])
def api_update_computer(aid: str, data: ComputerIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Computer, aid)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/computers/{aid}", tags=["computers"])
def api_delete_computer(aid: str, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Computer, aid))
    db.commit()
    return {"deleted": aid}


# --- JSON API: parts -------------------------------------------------------

@app.get("/api/parts", response_model=list[PartOut], tags=["parts"])
def api_list_parts(computer_id: str | None = None, type: str | None = None,
                   db: Session = Depends(get_db)):
    q = db.query(Part)
    if computer_id is not None:
        q = q.filter(Part.computer_id == computer_id)
    if type is not None:
        q = q.filter(Part.type == type)
    return q.order_by(Part.asset_id).all()


@app.post("/api/parts", response_model=PartOut, tags=["parts"])
def api_create_part(data: PartIn, db: Session = Depends(get_db)):
    obj = Part(asset_id=next_asset_id(db), **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@app.get("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_get_part(aid: str, db: Session = Depends(get_db)):
    return get_or_404(db, Part, aid)


@app.patch("/api/parts/{aid}", response_model=PartOut, tags=["parts"])
def api_update_part(aid: str, data: PartIn, db: Session = Depends(get_db)):
    obj = get_or_404(db, Part, aid)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@app.delete("/api/parts/{aid}", tags=["parts"])
def api_delete_part(aid: str, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Part, aid))
    db.commit()
    return {"deleted": aid}


# --- images: manifest (for build_site over the network) --------------------

@app.get("/api/images", tags=["images"])
def api_images():
    """Every image file in the store, as relative paths like
    'computers/RH-0001.jpg' -- so build_site can fetch photos over the network."""
    out = []
    for sub in ("computers", "parts"):
        folder = IMAGES_DIR / sub
        if folder.exists():
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                    out.append(f"{sub}/{f.name}")
    return out


def detect_images(kind, asset_id):
    """Ordered photos for an asset: <asset_id>.<ext> first, then -2, -3, ..."""
    folder = IMAGES_DIR / kind
    if not folder.exists():
        return []
    primary, extras = [], []
    for f in folder.iterdir():
        if f.suffix.lower() not in IMAGE_EXTS:
            continue
        if f.stem == asset_id:
            primary.append(f"{kind}/{f.name}")
        elif f.stem.startswith(asset_id + "-"):
            extras.append(f)

    def sort_key(f):
        suffix = f.stem[len(asset_id) + 1:]
        return (0, int(suffix), "") if suffix.isdigit() else (1, 0, suffix.lower())

    return primary + [f"{kind}/{f.name}" for f in sorted(extras, key=sort_key)]


def _save_photo(kind, asset_id, upload: UploadFile):
    """Store an uploaded photo. The first becomes <asset_id>.<ext> (the primary);
    later ones get the next free -N suffix so an item can carry several."""
    ext = Path(upload.filename or "").suffix.lower() or ".jpg"
    if ext not in IMAGE_EXTS:
        raise HTTPException(400, f"unsupported image type: {ext}")
    folder = IMAGES_DIR / kind
    folder.mkdir(parents=True, exist_ok=True)
    existing = detect_images(kind, asset_id)
    if not any(Path(p).stem == asset_id for p in existing):
        name = f"{asset_id}{ext}"
    else:
        n = 2
        while any(Path(p).stem == f"{asset_id}-{n}" for p in existing):
            n += 1
        name = f"{asset_id}-{n}{ext}"
    with open(folder / name, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return f"{kind}/{name}"


# --- GUI: index ------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def gui_index(request: Request, db: Session = Depends(get_db)):
    computers = db.query(Computer).order_by(Computer.asset_id).all()
    parts = db.query(Part).order_by(Part.asset_id).all()
    counts = {}
    for p in parts:
        if p.computer_id:
            counts[p.computer_id] = counts.get(p.computer_id, 0) + 1
    comp_ids = {c.asset_id for c in computers}

    def primary_image(kind, aid):
        imgs = detect_images(kind, aid)
        return imgs[0] if imgs else ""

    def storage_placeholder(p):
        kind = dict(entry.parse_specs(p.specs or "")).get("Kind", "").lower()
        if "optical" in kind:
            return entry.placeholder_for("optical")
        if "floppy" in kind or "gotek" in kind:
            return entry.placeholder_for("floppy")
        return entry.placeholder_for("storage")

    rows = []
    for c in computers:
        rows.append({
            "obj": c, "kind": "computer", "cat": "computer",
            "cat_label": "Computer", "parent": "", "year": c.year or "",
            "name": entry.display_name(to_dict(c)),
            "image": primary_image("computers", c.asset_id),
            "placeholder": entry.placeholder_for("computer"),
            "sub": f"{counts.get(c.asset_id, 0)} part(s)",
            "search": " ".join([c.asset_id, c.name or "", c.manufacturer or "",
                                 c.model or "", c.os or "", c.cpu or ""]).lower(),
        })
    for p in parts:
        ptype = p.type or "other"
        rows.append({
            "obj": p, "kind": "part", "cat": ptype,
            "cat_label": entry.type_label(ptype), "year": p.year or "",
            "parent": p.computer_id if p.computer_id in comp_ids else "",
            "name": entry.display_name(to_dict(p)),
            "image": primary_image("parts", p.asset_id),
            "placeholder": (storage_placeholder(p) if ptype == "storage"
                            else entry.placeholder_for(ptype)),
            "sub": (p.computer_id if p.computer_id else "standalone"),
            "search": " ".join([p.asset_id, p.name or "", p.manufacturer or "",
                                 p.model or "", p.specs or "", p.type or ""]).lower(),
        })
    cats = [("computer", "Computers")]
    present = {p.type or "other" for p in parts}
    for t in sorted(present, key=entry.type_sort_key):
        cats.append((t, entry.type_label(t)))
    return templates.TemplateResponse(request, "index.html", {
        "rows": rows, "cats": cats,
        "n_computers": len(computers), "n_parts": len(parts)})


# --- GUI: computers --------------------------------------------------------

@app.get("/computers/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_computer(request: Request):
    return templates.TemplateResponse(request, "computer_form.html", {
        "c": None, "conditions": entry.CONDITIONS, "title": "New computer"})


@app.post("/computers/new", include_in_schema=False)
async def gui_create_computer(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = {k: (form.get(k, "") or "") for k in COMPUTER_FIELDS}
    data["installed_ram"] = entry.parse_installed_ram(data.get("installed_ram", ""))
    for f in ("manufacturer", "model"):
        data[f] = entry.deshout(data[f])
    obj = Computer(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.commit()
    # Land on the build walk so the next step (motherboard) is front and centre.
    return RedirectResponse(f"/computers/{obj.asset_id}?build=1", status_code=303)


@app.get("/computers/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_computer(aid: str, request: Request, build: int = 0,
                 db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    parts = db.query(Part).filter(Part.computer_id == aid).all()
    parts.sort(key=lambda p: (entry.type_sort_key(p.type or ""),
                              entry.display_name(to_dict(p))))
    motherboard = next((p for p in parts if p.type == "motherboard"), None)
    # Unlinked boards that could be linked to this machine.
    free_boards = (db.query(Part)
                   .filter(Part.type == "motherboard",
                           (Part.computer_id == "") | (Part.computer_id.is_(None)))
                   .order_by(Part.asset_id).all())
    return templates.TemplateResponse(request, "computer.html", {
        "c": c, "parts": parts, "motherboard": motherboard,
        "free_boards": free_boards, "images": detect_images("computers", aid),
        "card_steps": entry.CARD_STEPS, "build": bool(build)})


@app.get("/computers/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    return templates.TemplateResponse(request, "computer_form.html", {
        "c": c, "conditions": entry.CONDITIONS, "title": f"Edit {aid}"})


@app.post("/computers/{aid}/edit", include_in_schema=False)
async def gui_save_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    for k in COMPUTER_FIELDS:
        if k not in form:
            continue
        v = form[k] or ""
        if k == "installed_ram":
            v = entry.parse_installed_ram(v)
        elif k in ("manufacturer", "model"):
            v = entry.deshout(v)
        setattr(c, k, v)
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/link-motherboard", include_in_schema=False)
async def gui_link_motherboard(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    get_or_404(db, Computer, aid)
    form = await request.form()
    pid = form.get("part_id", "")
    board = get_or_404(db, Part, pid)
    if board.type != "motherboard":
        raise HTTPException(400, f"{pid} is not a motherboard")
    board.computer_id = aid
    db.commit()
    return RedirectResponse(f"/computers/{aid}?build=1", status_code=303)


@app.post("/computers/{aid}/dispose", include_in_schema=False)
async def gui_dispose_computer(aid: str, request: Request,
                               db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    c.disposed = form.get("note", "") or "disposed"
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/restore", include_in_schema=False)
def gui_restore_computer(aid: str, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    c.disposed = ""
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.post("/computers/{aid}/photo", include_in_schema=False)
async def gui_computer_photo(aid: str, photo: UploadFile = File(...),
                             db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    rel = _save_photo("computers", aid, photo)
    if not c.image:
        c.image = rel
        db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.get("/computers/{aid}/label.pdf", include_in_schema=False)
def gui_computer_label(aid: str, small: int = 0, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    parts = [to_dict(p) for p in db.query(Part).filter(Part.computer_id == aid).all()]
    pdf = labels.render_pdf(to_dict(c), parts, is_computer=True, small=bool(small))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'})


# --- GUI: parts (guided, typed entry) --------------------------------------

def _part_form_ctx(obj, ptype, computer_id):
    return {
        "p": obj, "ptype": ptype, "computer_id": computer_id,
        "spec_keys": dict(entry.parse_specs(obj.specs)) if obj else {},
        "conditions": entry.CONDITIONS,
        "vocab": {
            "form_factors": entry.MOBO_FORM_FACTORS, "cpu_families": entry.CPU_FAMILIES,
            "ram_slots": entry.RAM_SLOT_TYPES, "card_interfaces": entry.CARD_INTERFACES,
            "video_connectors": entry.VIDEO_CONNECTORS,
            "storage_interfaces": entry.STORAGE_INTERFACES,
            "storage_kinds": entry.STORAGE_KINDS, "storage_protocols": entry.STORAGE_PROTOCOLS,
            "peripheral_interfaces": entry.PERIPHERAL_INTERFACES,
        },
        "port_legend": entry.PORT_LEGEND,
        "type_labels": entry.TYPE_LABELS, "type_order": entry.TYPE_ORDER,
    }


@app.get("/parts/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_part(request: Request, type: str = "other", computer_id: str = ""):
    ctx = _part_form_ctx(None, type, computer_id)
    ctx["title"] = f"New {entry.type_label(type)}"
    return templates.TemplateResponse(request, "part_form.html", ctx)


def _assemble_specs(ptype, form, existing=""):
    """Build a part's specs string from the typed form fields, running the same
    quick-entry expanders as add.py. Spec keys the form doesn't manage (rare, on
    edit) are preserved."""
    managed = {
        "motherboard": ["Chipset", "CPU family", "Form factor", "RAM slots",
                        "Slots", "Cache", "BIOS", "Onboard video", "Ports"],
        "cpu": ["Socket", "Speed", "FSB", "Cores", "Cache"],
        "ram": ["Type", "Size", "Speed"],
        "video": ["Chip", "Interface", "Connector", "Memory", "Type"],
        "sound": ["Chip", "Interface", "FM", "Ports"],
        "network": ["Chip", "Interface", "Connector"],
        "io": ["Chip", "Interface", "Ports"],
        "storage": ["Kind", "Interface", "Protocol", "Capacity", "CHS", "Media",
                    "Speed", "Role"],
    }.get(ptype)
    # 'other' / 'peripheral' keep a free-text specs box (no data loss).
    if managed is None:
        return " ".join((form.get("specs", "") or "").split())
    # Preserve any non-managed keys already on the row.
    specs = ""
    for k, v in entry.parse_specs(existing):
        if k and k not in managed:
            specs = entry.merge_spec(specs, k, v)
    for key in managed:
        # spec_ prefix keeps these clear of the part's own columns (a RAM
        # 'Type' spec vs the part type, etc.).
        field = "spec_" + key.lower().replace(" ", "_").replace("/", "_")
        raw = (form.get(field, "") or "").strip()
        if not raw:
            continue
        if key == "Ports":
            raw = entry.expand_ports(raw)
        elif key == "Slots":
            raw = entry.expand_slots(raw)
        elif key in ("Size", "Memory"):
            raw = entry.normalise_amount(key, raw)
        specs = entry.merge_spec(specs, key, raw)
    return specs


async def _part_from_form(form, ptype):
    data = {"type": ptype, "computer_id": form.get("computer_id", "") or ""}
    for f in ("manufacturer", "model", "name", "year", "condition", "source",
              "acquired_date", "url", "notes", "disk_image"):
        data[f] = form.get(f, "") or ""
    for f in ("manufacturer", "model"):
        data[f] = entry.deshout(data[f])
    data["specs"] = _assemble_specs(ptype, form, form.get("_existing_specs", ""))
    return data


@app.post("/parts/new", include_in_schema=False)
async def gui_create_part(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    ptype = form.get("type", "other") or "other"
    computer_id = form.get("computer_id", "") or ""
    # Storage routing: floppy / optical / SD-CF live on the computer's drives
    # field; only hard disks and tape become their own tagged parts.
    if ptype == "storage":
        kind = form.get("kind", "") or ""
        if kind and kind not in entry.PART_STORAGE_KINDS:
            desc = (form.get("drive_desc", "") or "").strip() or kind
            if computer_id:
                c = get_or_404(db, Computer, computer_id)
                cur = (c.drives or "").strip()
                c.drives = f"{cur}; {desc}" if cur else desc
                db.commit()
                return RedirectResponse(f"/computers/{computer_id}?build=1",
                                        status_code=303)
    data = await _part_from_form(form, ptype)
    if ptype == "storage":
        data["specs"] = entry.merge_spec(data["specs"], "Kind",
                                         form.get("kind", "") or "")
    obj = Part(asset_id=next_asset_id(db), **data)
    db.add(obj)
    db.commit()
    dest = f"/computers/{computer_id}?build=1" if computer_id else f"/parts/{obj.asset_id}"
    return RedirectResponse(dest, status_code=303)


@app.get("/parts/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    parent = db.get(Computer, p.computer_id) if p.computer_id else None
    return templates.TemplateResponse(request, "part.html", {
        "p": p, "parent": parent, "images": detect_images("parts", aid),
        "spec_pairs": entry.parse_specs(p.specs)})


@app.get("/parts/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    ctx = _part_form_ctx(p, p.type or "other", p.computer_id or "")
    ctx["title"] = f"Edit {aid}"
    return templates.TemplateResponse(request, "part_form.html", ctx)


@app.post("/parts/{aid}/edit", include_in_schema=False)
async def gui_save_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    ptype = form.get("type", p.type) or "other"
    data = await _part_from_form(form, ptype)
    if ptype == "storage" and (form.get("kind", "") or ""):
        data["specs"] = entry.merge_spec(data["specs"], "Kind", form.get("kind"))
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/dispose", include_in_schema=False)
async def gui_dispose_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    p.disposed = form.get("note", "") or "disposed"
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/restore", include_in_schema=False)
def gui_restore_part(aid: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    p.disposed = ""
    db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.post("/parts/{aid}/photo", include_in_schema=False)
async def gui_part_photo(aid: str, photo: UploadFile = File(...),
                         db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    rel = _save_photo("parts", aid, photo)
    if not p.image:
        p.image = rel
        db.commit()
    return RedirectResponse(f"/parts/{aid}", status_code=303)


@app.get("/parts/{aid}/label.pdf", include_in_schema=False)
def gui_part_label(aid: str, small: int = 1, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    pdf = labels.render_pdf(to_dict(p), [], is_computer=False, small=bool(small))
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="{aid}{"-small" if small else ""}.pdf"'})
