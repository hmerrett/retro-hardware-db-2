"""Retro Hardware Database — FastAPI backend.

Two surfaces over the same MariaDB:
  * JSON API under /api  (used by scripts, an MCP wrapper, and the GUI)
  * a minimal server-rendered GUI for day-to-day editing

Interactive API docs live at /docs (OpenAPI) — handy for humans and AI alike.
"""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .ids import next_asset_id
from .models import Computer, Part
from .schemas import ComputerIn, ComputerOut, PartIn, PartOut

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Retro Hardware Database API", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

COMPUTER_FIELDS = [c.name for c in Computer.__table__.columns if c.name != "asset_id"]
PART_FIELDS = [c.name for c in Part.__table__.columns if c.name != "asset_id"]


def get_or_404(db, model, aid):
    obj = db.get(model, aid)
    if not obj:
        raise HTTPException(404, f"{model.__tablename__} {aid} not found")
    return obj


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


# --- minimal GUI -----------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def gui_index(request: Request, db: Session = Depends(get_db)):
    computers = db.query(Computer).order_by(Computer.asset_id).all()
    parts = db.query(Part).order_by(Part.asset_id).all()
    counts = {}
    for p in parts:
        if p.computer_id:
            counts[p.computer_id] = counts.get(p.computer_id, 0) + 1
    standalone = [p for p in parts if not p.computer_id]
    return templates.TemplateResponse(request, "index.html", {
        "computers": computers, "counts": counts,
        "standalone": standalone, "part_total": len(parts)})


@app.get("/computers/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_computer(request: Request):
    return templates.TemplateResponse(request, "form.html", {
        "obj": None, "fields": COMPUTER_FIELDS,
        "action": "/computers/new", "title": "New computer"})


@app.post("/computers/new", include_in_schema=False)
async def gui_create_computer(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    obj = Computer(asset_id=next_asset_id(db),
                   **{k: form.get(k, "") for k in COMPUTER_FIELDS})
    db.add(obj)
    db.commit()
    return RedirectResponse(f"/computers/{obj.asset_id}", status_code=303)


@app.get("/computers/{aid}", response_class=HTMLResponse, include_in_schema=False)
def gui_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    parts = db.query(Part).filter(Part.computer_id == aid).order_by(Part.type).all()
    return templates.TemplateResponse(request, "computer.html",
                                      {"c": c, "parts": parts})


@app.get("/computers/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    return templates.TemplateResponse(request, "form.html", {
        "obj": c, "fields": COMPUTER_FIELDS,
        "action": f"/computers/{aid}/edit", "title": f"Edit {aid}"})


@app.post("/computers/{aid}/edit", include_in_schema=False)
async def gui_save_computer(aid: str, request: Request, db: Session = Depends(get_db)):
    c = get_or_404(db, Computer, aid)
    form = await request.form()
    for k in COMPUTER_FIELDS:
        if k in form:
            setattr(c, k, form[k])
    db.commit()
    return RedirectResponse(f"/computers/{aid}", status_code=303)


@app.get("/parts/new", response_class=HTMLResponse, include_in_schema=False)
def gui_new_part(request: Request, computer_id: str = ""):
    obj = Part(computer_id=computer_id)
    return templates.TemplateResponse(request, "form.html", {
        "obj": obj, "fields": PART_FIELDS,
        "action": "/parts/new", "title": "New part"})


@app.post("/parts/new", include_in_schema=False)
async def gui_create_part(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    obj = Part(asset_id=next_asset_id(db),
               **{k: form.get(k, "") for k in PART_FIELDS})
    db.add(obj)
    db.commit()
    dest = f"/computers/{obj.computer_id}" if obj.computer_id else "/"
    return RedirectResponse(dest, status_code=303)


@app.get("/parts/{aid}/edit", response_class=HTMLResponse, include_in_schema=False)
def gui_edit_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    return templates.TemplateResponse(request, "form.html", {
        "obj": p, "fields": PART_FIELDS,
        "action": f"/parts/{aid}/edit", "title": f"Edit {aid}"})


@app.post("/parts/{aid}/edit", include_in_schema=False)
async def gui_save_part(aid: str, request: Request, db: Session = Depends(get_db)):
    p = get_or_404(db, Part, aid)
    form = await request.form()
    for k in PART_FIELDS:
        if k in form:
            setattr(p, k, form[k])
    db.commit()
    dest = f"/computers/{p.computer_id}" if p.computer_id else "/"
    return RedirectResponse(dest, status_code=303)
