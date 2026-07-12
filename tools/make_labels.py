#!/usr/bin/env python3
"""Generate print-ready labels (PDF) for any asset — a whole computer or an
individual part — with a QR code linking to that item's page on your GitHub
Pages site.

Two sizes:
  * full (default, 6x4 in)  — asset number, title and all the details.
  * small (--small, e.g. 19x51 mm) — just the QR, asset number and make/model.

Automatic set (--auto): computers get BOTH sizes, any real (non-generic) part
gets the small one, generic filler gets none. `add.py` calls this on create/update.

All text uses the TTF set in config.yml (label.font_path, e.g. Audiowide); if
that file is missing the label falls back to Helvetica.

Usage (the description sits above each command):
    full labels, everything:
        python scripts/make_labels.py
    one item, written to labels/RH-0002.pdf:
        python scripts/make_labels.py RH-0002
    small tag, written to labels/RH-0002-small.pdf:
        python scripts/make_labels.py --small RH-0002
    auto set for every device:
        python scripts/make_labels.py --auto
    auto set for one device:
        python scripts/make_labels.py --auto RH-0010
    reprint a tag and send it to the printer:
        python scripts/make_labels.py --small --print RH-0002
"""
from __future__ import annotations

import argparse
import io
import subprocess
from pathlib import Path

import segno
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from rhdb import (ROOT, add_api_arg, apply_api_arg, display_name, index_by_id,
                  item_url, load_computers, load_config, load_parts,
                  parse_specs, parts_for, type_label)

LABELS_DIR = ROOT / "labels"

BUILD_ROWS = [
    ("cpu", "CPU"), ("ram", "Memory"), ("video", "Video"), ("sound", "Sound"),
    ("storage", "Storage"), ("network", "Network"), ("optical", "Optical"),
    ("floppy", "Floppy"),
]
SPEC_PICK = {"ram": "Size", "storage": "Capacity", "optical": "Media",
             "floppy": "Media"}


def register_fonts(config, quiet=False):
    rel = (config.get("label", {}) or {}).get("font_path", "")
    if rel:
        path = ROOT / rel
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("LabelFont", str(path)))
                if not quiet:
                    print(f"  using label font: {rel}")
                return "LabelFont", "LabelFont"
            except Exception as exc:
                print(f"  note: could not load {rel} ({exc}) — using Helvetica.")
        elif not quiet:
            print(f"  note: label font {rel} not found — using Helvetica.")
    return "Helvetica-Bold", "Helvetica"


def page_size(lc):
    unit = inch if lc.get("units", "in") == "in" else mm
    return float(lc.get("width", 6)) * unit, float(lc.get("height", 4)) * unit


def label_geom(config, small):
    if small:
        lc = config.get("label_small") or {"width": 51, "height": 19, "units": "mm"}
    else:
        lc = config.get("label") or {}
    w, h = page_size(lc)
    return w, h, lc.get("qr_error", "M")


def label_rotation(config, small):
    lc = (config.get("label_small") if small else config.get("label")) or {}
    try:
        return int(lc.get("rotate", 0)) % 360
    except (TypeError, ValueError):
        return 0


def rotated_page_size(W, H, rot):
    return (H, W) if rot in (90, 270) else (W, H)


def apply_rotation(c, W, H, rot):
    if rot == 90:
        c.translate(H, 0)
        c.rotate(90)
    elif rot == 270:
        c.translate(0, W)
        c.rotate(-90)
    elif rot == 180:
        c.translate(W, H)
        c.rotate(180)


def default_filename(ids, suffix=""):
    if not ids:
        return f"labels{suffix}.pdf"
    if len(ids) == 1:
        return f"{ids[0]}{suffix}.pdf"
    if len(ids) <= 4:
        return "_".join(ids) + f"{suffix}.pdf"
    return f"{ids[0]}_and_{len(ids) - 1}_more{suffix}.pdf"


def qr_reader(data, error="M"):
    buf = io.BytesIO()
    segno.make(data, error=error.lower()).save(buf, kind="png", scale=10, border=1)
    buf.seek(0)
    return ImageReader(buf)


def wrap_to_width(c, text, font, size, max_w):
    words = text.split()
    lines, cur = [], ""
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


def fit_size(c, text, font, start, min_size, max_w):
    size = start
    while size > min_size and c.stringWidth(text, font, size) > max_w:
        size -= 1
    return size


def computer_lines(comp, parts):
    lines = ["Type: Computer"]
    kids = parts_for(comp["asset_id"], parts)
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


def render_label(c, W, H, asset_id, title, lines, url, qr_error, hfont, bfont):
    margin = 0.22 * inch
    qr_size = min(H - 2 * margin, 2.1 * inch)
    qr_x = W - margin - qr_size
    text_w = qr_x - margin - 0.10 * inch
    bottom = margin + 0.16 * inch

    c.setLineWidth(1)
    c.setStrokeColorRGB(0.65, 0.65, 0.65)
    c.roundRect(0.10 * inch, 0.10 * inch, W - 0.20 * inch, H - 0.20 * inch,
                8, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)

    aid_size = fit_size(c, asset_id, hfont, 24, 12, text_w)
    y = H - margin - aid_size + 4
    c.setFont(hfont, aid_size)
    c.drawString(margin, y, asset_id)

    c.setFont(hfont, 12)
    for line in wrap_to_width(c, title, hfont, 12, text_w)[:2]:
        y -= 16
        c.drawString(margin, y, line)

    y -= 5
    bsize = 9
    for raw in lines:
        for i, line in enumerate(wrap_to_width(c, "• " + raw, bfont, bsize, text_w)[:2]):
            if y - 12 < bottom:
                break
            y -= 12
            c.setFont(bfont, bsize)
            c.drawString(margin if i == 0 else margin + 8, y,
                         line if i == 0 else "  " + line)
        if y - 12 < bottom:
            break

    qr_y = (H - qr_size) / 2 + 0.10 * inch
    c.drawImage(qr_reader(url, qr_error), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")
    c.setFont(bfont, 7.5)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 11, "scan for details")


def fit_to_lines(c, text, font, start, min_size, width, max_lines):
    """Largest size (down to min_size) at which the wrapped text fits max_lines."""
    size = start
    while size > min_size and len(wrap_to_width(c, text, font, size, width)) > max_lines:
        size -= 0.5
    return size


def render_small_label(c, W, H, asset_id, title, url, qr_error, hfont, bfont, safe=0.0):
    my = 1.2 * mm
    mx = my + safe * mm
    c.setFillColorRGB(0, 0, 0)

    # landscape: QR left, text right
    if W >= H:
        qr = H - 2 * my
        c.drawImage(qr_reader(url, qr_error), mx, my, width=qr, height=qr,
                    preserveAspectRatio=True, mask="auto")
        tx = mx + qr + 1.5 * mm
        tw = W - tx - mx
        aid_size = fit_size(c, asset_id, hfont, 11, 5, tw)
        y = H - my - aid_size
        c.setFont(hfont, aid_size)
        c.drawString(tx, y, asset_id)
        bsize = fit_to_lines(c, title, bfont, 6.5, 4.5, tw, 3)
        for line in wrap_to_width(c, title, bfont, bsize, tw)[:3]:
            if y - (bsize + 1.5) < my:
                break
            y -= bsize + 1.5
            c.setFont(bfont, bsize)
            c.drawString(tx, y, line)
    # portrait: QR top, text below
    else:
        qr = W - 2 * my
        c.drawImage(qr_reader(url, qr_error), my, H - mx - qr, width=qr, height=qr,
                    preserveAspectRatio=True, mask="auto")
        tw = W - 2 * my
        y = H - mx - qr - 1.5 * mm
        aid_size = fit_size(c, asset_id, hfont, 10, 5, tw)
        y -= aid_size
        c.setFont(hfont, aid_size)
        c.drawCentredString(W / 2, y, asset_id)
        bsize = fit_to_lines(c, title, bfont, 6, 4.5, tw, 3)
        for line in wrap_to_width(c, title, bfont, bsize, tw)[:3]:
            if y - (bsize + 1.5) < mx:
                break
            y -= bsize + 1.5
            c.setFont(bfont, bsize)
            c.drawCentredString(W / 2, y, line)


# --- shared content + drawing ----------------------------------------------

def asset_content(aid, comp_by_id, part_by_id, parts):
    """(title, lines) for an asset, or None if the id is unknown."""
    if aid in comp_by_id:
        c = comp_by_id[aid]
        return display_name(c), computer_lines(c, parts)
    if aid in part_by_id:
        p = part_by_id[aid]
        return display_name(p), part_lines(p)
    return None


def draw_one(c, W, H, aid, small, config, title, lines, qr_error, hfont, bfont):
    url = item_url(config, aid)
    c.saveState()
    apply_rotation(c, W, H, label_rotation(config, small))
    if small:
        safe = float((config.get("label_small") or {}).get("safe_mm", 0) or 0)
        render_small_label(c, W, H, aid, title, url, qr_error, hfont, bfont, safe)
    else:
        render_label(c, W, H, aid, title, lines, url, qr_error, hfont, bfont)
    c.restoreState()
    c.showPage()


# --- automatic labels ------------------------------------------------------

def auto_plan(aid, comp_by_id, part_by_id):
    """Which labels a device gets: computers -> full + small; any real (non-
    generic) part -> small; generic filler -> none. Returns (suffix, small) list."""
    if aid in comp_by_id:
        return [("", False), ("-small", True)]
    p = part_by_id.get(aid)
    if p and p.get("manufacturer", "").strip().lower() != "generic":
        return [("-small", True)]
    return []


def auto_labels(asset_ids, config=None, announce=True):
    """Write the automatic label set for the given assets (overwriting). Returns
    the list of files written."""
    config = config or load_config()
    computers, parts = load_computers(), load_parts()
    comp_by_id, part_by_id = index_by_id(computers), index_by_id(parts)
    hfont, bfont = register_fonts(config, quiet=True)
    LABELS_DIR.mkdir(parents=True, exist_ok=True)

    written = []
    for aid in asset_ids:
        plan = auto_plan(aid, comp_by_id, part_by_id)
        if not plan:
            continue
        content = asset_content(aid, comp_by_id, part_by_id, parts)
        if not content:
            continue
        title, lines = content
        for suffix, small in plan:
            out = LABELS_DIR / f"{aid}{suffix}.pdf"
            W, H, qr = label_geom(config, small)
            rot = label_rotation(config, small)
            c = canvas.Canvas(str(out), pagesize=rotated_page_size(W, H, rot))
            draw_one(c, W, H, aid, small, config, title, lines, qr, hfont, bfont)
            c.save()
            written.append(out)
    if announce and written:
        print("  labels: " + ", ".join(p.name for p in written))
    return written


def regenerate(asset_ids, config=None):
    """Auto-label the given assets, and any parent computers of changed parts
    (whose build summary may have changed). Returns files written."""
    pbi = index_by_id(load_parts())
    targets = set()
    for aid in asset_ids:
        targets.add(aid)
        p = pbi.get(aid)
        if p and p.get("computer_id"):
            targets.add(p["computer_id"])
    return auto_labels(sorted(targets), config)


def all_auto_ids():
    computers, parts = load_computers(), load_parts()
    return ([c["asset_id"] for c in computers]
            + [p["asset_id"] for p in parts
               if p.get("manufacturer", "").strip().lower() != "generic"])


def print_pdf(path, printer="", copies=1):
    """Send a PDF to a printer via macOS/CUPS `lp`. Returns (ok, message)."""
    cmd = ["lp"]
    if printer:
        cmd += ["-d", printer]
    try:
        copies = int(copies)
    except (TypeError, ValueError):
        copies = 1
    if copies > 1:
        cmd += ["-n", str(copies)]
    cmd.append(str(path))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        return False, "no 'lp' command (printing needs macOS/CUPS)"
    except Exception as exc:
        return False, str(exc)
    if res.returncode == 0:
        return True, (res.stdout.strip() or "queued")
    return False, (res.stderr.strip() or f"lp exited {res.returncode}")


def printer_for(config, small):
    pc = config.get("print") or {}
    return pc.get("small_printer" if small else "full_printer") or ""


def print_label_file(path, config):
    """Print one label PDF, choosing the printer by size (small vs full)."""
    small = str(path).endswith("-small.pdf")
    printer = printer_for(config, small)
    copies = (config.get("print") or {}).get("copies", 1)
    ok, msg = print_pdf(path, printer, copies)
    if ok:
        print(f"  printed {Path(path).name} -> {printer or 'default printer'}")
    else:
        print(f"  ! print failed for {Path(path).name}: {msg}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_api_arg(ap)
    ap.add_argument("ids", nargs="*", help="asset_ids to print (default: all)")
    ap.add_argument("--small", action="store_true",
                    help="compact QR + number + make/model label (config: label_small)")
    ap.add_argument("--auto", action="store_true",
                    help="auto set: computers full+small, real (non-generic) parts small")
    ap.add_argument("--print", dest="do_print", action="store_true",
                    help="also send the generated label(s) to the printer (macOS lp)")
    ap.add_argument("-o", "--out", default=None,
                    help="output PDF path (default: named after the asset id(s))")
    args = ap.parse_args()
    apply_api_arg(args)

    config = load_config()

    if args.auto:
        ids = args.ids if args.ids else all_auto_ids()
        written = auto_labels(ids, config, announce=False)
        print(f"Wrote {len(written)} label file(s) -> {LABELS_DIR}")
        if args.do_print:
            for p in written:
                print_label_file(p, config)
        return

    computers, parts = load_computers(), load_parts()
    comp_by_id, part_by_id = index_by_id(computers), index_by_id(parts)
    hfont, bfont = register_fonts(config)

    all_ids = sorted([c["asset_id"] for c in computers] + [p["asset_id"] for p in parts])
    ids = args.ids if args.ids else all_ids

    base_url = config.get("base_url") or ""
    if not base_url or "USERNAME" in base_url:
        print("WARNING: config.yml base_url still has a placeholder.")
        print("         QR codes will not resolve until you set it to your "
              "GitHub Pages URL.\n")

    small = args.small
    W, H, qr_error = label_geom(config, small)
    suffix = "-small" if small else ""
    out_path = Path(args.out) if args.out else LABELS_DIR / default_filename(args.ids, suffix)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=rotated_page_size(W, H, label_rotation(config, small)))

    printed = 0
    for aid in ids:
        content = asset_content(aid, comp_by_id, part_by_id, parts)
        if not content:
            print(f"  ! unknown asset_id: {aid}")
            continue
        title, lines = content
        draw_one(c, W, H, aid, small, config, title, lines, qr_error, hfont, bfont)
        printed += 1

    if printed == 0:
        print("No matching items — nothing written.")
        return
    c.save()
    print(f"Wrote {printed} {'small ' if small else ''}label(s) -> {out_path}")
    if args.do_print:
        print_label_file(out_path, config)


if __name__ == "__main__":
    main()
