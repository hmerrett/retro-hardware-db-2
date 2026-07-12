"""Print-ready label PDFs, rendered in the api so the GUI's "print label" action
can hand back a file to download. A focused port of the flat-file make_labels.py:
same 6x4in full label and 51x19mm small label, same QR encoding
<base_url>/items/<asset_id>/ so the codes match every label already printed.

Physical printing stays on the DYMO box; here we only generate the PDF.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import segno
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .entry import display_name, parse_specs, type_label

FONT_PATH = Path(__file__).resolve().parent / "label_font.ttf"

# Label geometry, mirroring the flat-file config.yml defaults.
FULL = {"w": 6 * inch, "h": 4 * inch, "qr": "M", "rotate": 90}
SMALL = {"w": 51 * mm, "h": 19 * mm, "qr": "M", "rotate": 90, "safe_mm": 3}

BUILD_ROWS = [("cpu", "CPU"), ("ram", "Memory"), ("video", "Video"),
              ("sound", "Sound"), ("storage", "Storage"), ("network", "Network")]
SPEC_PICK = {"ram": "Size", "storage": "Capacity"}

_font_ready = False


def base_url() -> str:
    return (os.getenv("RHDB_BASE_URL")
            or "https://hmerrett.github.io/retro-hardware-database").rstrip("/")


def item_url(asset_id: str) -> str:
    return f"{base_url()}/items/{asset_id}/"


def _fonts():
    """Register the display TTF once; fall back to Helvetica if it's missing."""
    global _font_ready
    if _font_ready:
        return ("LabelFont", "LabelFont")
    if FONT_PATH.exists():
        try:
            pdfmetrics.registerFont(TTFont("LabelFont", str(FONT_PATH)))
            _font_ready = True
            return ("LabelFont", "LabelFont")
        except Exception:
            pass
    return ("Helvetica-Bold", "Helvetica")


def _qr(data, error="M"):
    buf = io.BytesIO()
    segno.make(data, error=error.lower()).save(buf, kind="png", scale=10, border=1)
    buf.seek(0)
    return ImageReader(buf)


def _wrap(c, text, font, size, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if not cur or c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _fit(c, text, font, start, min_size, max_w):
    size = start
    while size > min_size and c.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def _fit_lines(c, text, font, start, min_size, width, max_lines):
    size = start
    while size > min_size and len(_wrap(c, text, font, size, width)) > max_lines:
        size -= 0.5
    return size


def rotated_page(spec):
    return (spec["h"], spec["w"]) if spec["rotate"] in (90, 270) else (spec["w"], spec["h"])


def _apply_rotation(c, W, H, rot):
    if rot == 90:
        c.translate(H, 0)
        c.rotate(90)
    elif rot == 270:
        c.translate(0, W)
        c.rotate(-90)
    elif rot == 180:
        c.translate(W, H)
        c.rotate(180)


# --- content ---------------------------------------------------------------

def computer_lines(comp, parts):
    kids = sorted((p for p in parts if p.get("computer_id") == comp["asset_id"]),
                  key=lambda p: p.get("type", ""))
    lines = ["Type: Computer"]
    form_factor = ""
    for p in kids:
        if p.get("type") == "motherboard":
            form_factor = dict(parse_specs(p.get("specs", ""))).get("Form factor", "")
            if form_factor:
                break
    if comp.get("manufacturer"):
        lines.append(f"Manufacturer: {comp['manufacturer']}")
    if comp.get("year"):
        lines.append(f"Year: {comp['year']}")
    if form_factor:
        lines.append(f"Form factor: {form_factor}")
    for label, key in (("CPU", "cpu"), ("RAM", "installed_ram"),
                       ("Drives", "drives"), ("Chassis", "chassis"), ("OS", "os")):
        if comp.get(key):
            lines.append(f"{label}: {comp[key]}")
    by_type = {}
    for p in kids:
        by_type.setdefault(p.get("type", ""), []).append(p)
    for ptype, label in BUILD_ROWS:
        if ptype not in by_type:
            continue
        members = by_type[ptype]
        if ptype in SPEC_PICK:
            specs = dict(parse_specs(members[0].get("specs", "")))
            value = specs.get(SPEC_PICK[ptype]) or display_name(members[0])
        else:
            value = " + ".join(display_name(m) for m in members)
        lines.append(f"{label}: {value}")
    if comp.get("condition"):
        lines.append(f"Condition: {comp['condition']}")
    return lines


def part_lines(part):
    lines = [f"Type: {type_label(part.get('type', ''))}"]
    for label, key in (("Manufacturer", "manufacturer"), ("Year", "year")):
        if part.get(key):
            lines.append(f"{label}: {part[key]}")
    lines += [f"{k}: {v}" if k else v for k, v in parse_specs(part.get("specs", ""))]
    if part.get("computer_id"):
        lines.append(f"Installed in: {part['computer_id']}")
    if part.get("condition"):
        lines.append(f"Condition: {part['condition']}")
    return lines


# --- drawing ---------------------------------------------------------------

def _render_full(c, W, H, asset_id, title, lines, url, hfont, bfont):
    margin = 0.22 * inch
    qr_size = min(H - 2 * margin, 2.1 * inch)
    qr_x = W - margin - qr_size
    text_w = qr_x - margin - 0.10 * inch
    bottom = margin + 0.16 * inch
    c.setLineWidth(1)
    c.setStrokeColorRGB(0.65, 0.65, 0.65)
    c.roundRect(0.10 * inch, 0.10 * inch, W - 0.20 * inch, H - 0.20 * inch, 8,
                stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)
    aid_size = _fit(c, asset_id, hfont, 24, 12, text_w)
    y = H - margin - aid_size + 4
    c.setFont(hfont, aid_size)
    c.drawString(margin, y, asset_id)
    c.setFont(hfont, 12)
    for line in _wrap(c, title, hfont, 12, text_w)[:2]:
        y -= 16
        c.drawString(margin, y, line)
    y -= 5
    for raw in lines:
        for i, line in enumerate(_wrap(c, "• " + raw, bfont, 9, text_w)[:2]):
            if y - 12 < bottom:
                break
            y -= 12
            c.setFont(bfont, 9)
            c.drawString(margin if i == 0 else margin + 8, y,
                         line if i == 0 else "  " + line)
        if y - 12 < bottom:
            break
    qr_y = (H - qr_size) / 2 + 0.10 * inch
    c.drawImage(_qr(url), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")
    c.setFont(bfont, 7.5)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 11, "scan for details")


def _render_small(c, W, H, asset_id, title, url, hfont, bfont, safe=0.0):
    my = 1.2 * mm
    mx = my + safe * mm
    c.setFillColorRGB(0, 0, 0)
    qr = H - 2 * my
    c.drawImage(_qr(url), mx, my, width=qr, height=qr, preserveAspectRatio=True,
                mask="auto")
    tx = mx + qr + 1.5 * mm
    tw = W - tx - mx
    aid_size = _fit(c, asset_id, hfont, 11, 5, tw)
    y = H - my - aid_size
    c.setFont(hfont, aid_size)
    c.drawString(tx, y, asset_id)
    bsize = _fit_lines(c, title, bfont, 6.5, 4.5, tw, 3)
    for line in _wrap(c, title, bfont, bsize, tw)[:3]:
        if y - (bsize + 1.5) < my:
            break
        y -= bsize + 1.5
        c.setFont(bfont, bsize)
        c.drawString(tx, y, line)


def render_pdf(asset, parts, is_computer, small=False) -> bytes:
    """Render one label PDF and return its bytes. `asset` is the computer/part
    row (dict); `parts` is the full parts list (used for a computer's build)."""
    hfont, bfont = _fonts()
    spec = SMALL if small else FULL
    title = display_name(asset)
    url = item_url(asset["asset_id"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=rotated_page(spec))
    c.saveState()
    _apply_rotation(c, spec["w"], spec["h"], spec["rotate"])
    if small:
        _render_small(c, spec["w"], spec["h"], asset["asset_id"], title, url,
                      hfont, bfont, spec.get("safe_mm", 0))
    else:
        lines = (computer_lines(asset, parts) if is_computer
                 else part_lines(asset))
        _render_full(c, spec["w"], spec["h"], asset["asset_id"], title, lines,
                     url, hfont, bfont)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()
