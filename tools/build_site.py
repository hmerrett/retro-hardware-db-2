#!/usr/bin/env python3
"""Build the static website from the REST API into ./site/.

Every computer and every part gets a page at  site/items/<asset_id>/index.html
so the QR codes (which encode <base_url>/items/<asset_id>/) resolve uniformly,
whatever the item is -- unchanged from the flat-file build, so labels already in
the wild keep working. A computer's page lists its parts; a part's page links
back to the computer it's installed in.

    python tools/build_site.py
    python tools/build_site.py --api http://192.168.1.2:8000
"""
from __future__ import annotations

import argparse
import shutil
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape

from rhdb import (ROOT, TYPE_ORDER, add_api_arg, apply_api_arg, display_name,
                  images_dir, index_by_id, load_computers, load_config,
                  load_parts, parse_specs, parts_for, placeholder_for,
                  type_label, type_sort_key, url_label, validate)

TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

IMAGES_DIR = None


def detect_image(kind, asset_id):
    """Find a photo at <images_dir>/<kind>/<asset_id>.<ext> (kind is 'computers'
    or 'parts')."""
    folder = IMAGES_DIR / kind
    for ext in IMAGE_EXTS:
        f = folder / f"{asset_id}{ext}"
        if f.exists():
            return f"{kind}/{f.name}"
    return ""


def detect_images(kind, asset_id, primary=""):
    """Ordered photo list: the primary first, then any extras dropped in as
    <asset_id>-2.<ext>, -3.<ext>, ... (numeric order first, then alphabetical)."""
    folder = IMAGES_DIR / kind
    imgs = []
    if primary:
        imgs.append(primary)
    else:
        primary = detect_image(kind, asset_id)
        if primary:
            imgs.append(primary)
    extras = []
    if folder.exists():
        for f in folder.iterdir():
            if f.suffix.lower() in IMAGE_EXTS and f.stem.startswith(asset_id + "-"):
                extras.append(f)

    def sort_key(f):
        suffix = f.stem[len(asset_id) + 1:]
        return (0, int(suffix), "") if suffix.isdigit() else (1, 0, suffix.lower())

    for f in sorted(extras, key=sort_key):
        imgs.append(f"{kind}/{f.name}")
    return imgs


def build():
    config = load_config()
    computers = load_computers()
    parts = load_parts()

    warnings = validate(computers, parts)
    for w in warnings:
        print(f"  ! {w}", file=sys.stderr)
    if warnings:
        print(f"  ({len(warnings)} integrity warning(s) above — building anyway)\n",
              file=sys.stderr)

    # Derived fields.
    for c in computers:
        c["display_name"] = display_name(c)
        c["placeholder"] = placeholder_for("computer")
        if not c.get("image"):
            c["image"] = detect_image("computers", c["asset_id"])
        c["images"] = detect_images("computers", c["asset_id"], c.get("image", ""))
        if not c.get("image") and c["images"]:
            c["image"] = c["images"][0]
        c["url_label"] = url_label(c.get("url", ""))
    computers_by_id = index_by_id(computers)

    for p in parts:
        p["display_name"] = display_name(p)
        p["type_label"] = type_label(p.get("type", ""))
        p["spec_pairs"] = parse_specs(p.get("specs", ""))
        p["parent"] = computers_by_id.get(p.get("computer_id", "")) or None
        p["placeholder"] = placeholder_for(p.get("type", ""))
        if p.get("type") == "storage":
            kind = dict(p.get("spec_pairs") or []).get("Kind", "").lower()
            if "optical" in kind:
                p["placeholder"] = placeholder_for("optical")
            elif "floppy" in kind or "gotek" in kind:
                p["placeholder"] = placeholder_for("floppy")
        if not p.get("image"):
            p["image"] = detect_image("parts", p["asset_id"])
        p["images"] = detect_images("parts", p["asset_id"], p.get("image", ""))
        if not p.get("image") and p["images"]:
            p["image"] = p["images"][0]
        p["url_label"] = url_label(p.get("url", ""))
    for c in computers:
        c["parts"] = parts_for(c["asset_id"], parts)
        # Form factor is a motherboard property — derive it from the linked board.
        c["form_factor"] = ""
        for p in c["parts"]:
            if p.get("type") == "motherboard":
                ff = dict(p.get("spec_pairs") or []).get("Form factor", "")
                if ff:
                    c["form_factor"] = ff
                    break

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    # Fresh output.
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True)
    if IMAGES_DIR.exists():
        shutil.copytree(IMAGES_DIR, SITE_DIR / "images",
                        ignore=shutil.ignore_patterns(".gitkeep"))
    placeholders = ROOT / "assets" / "placeholders"
    if placeholders.exists():
        shutil.copytree(placeholders, SITE_DIR / "placeholders")

    # --- index: unified list of computers + parts ---
    assets = []
    for c in computers:
        assets.append({
            "asset_id": c["asset_id"], "cat": "computer", "cat_label": "Computer",
            "display_name": c["display_name"], "image": c.get("image", ""),
            "year": c.get("year", ""), "parent": "", "generic": False,
            "disposed": bool((c.get("disposed") or "").strip()),
            "placeholder": c["placeholder"],
            "search_text": " ".join([c["display_name"], c.get("manufacturer", ""),
                                     c.get("model", ""), c.get("os", ""),
                                     c["asset_id"]]).lower(),
        })
    for p in parts:
        assets.append({
            "asset_id": p["asset_id"], "cat": p.get("type", "other"),
            "cat_label": p["type_label"], "display_name": p["display_name"],
            "image": p.get("image", ""), "year": p.get("year", ""),
            "parent": p.get("computer_id", ""),
            "generic": (p.get("manufacturer", "").strip().lower() == "generic"),
            "disposed": bool((p.get("disposed") or "").strip()),
            "placeholder": p["placeholder"],
            "search_text": " ".join([p["display_name"], p.get("manufacturer", ""),
                                     p.get("model", ""), p.get("specs", ""),
                                     p.get("type", ""), p["asset_id"]]).lower(),
        })
    # Default order: items with a photo first, then most recently added first.
    assets.sort(key=lambda a: a["asset_id"], reverse=True)
    assets.sort(key=lambda a: 0 if a["image"] else 1)

    present_types = {p.get("type", "other") for p in parts}
    categories = [{"key": "computer", "label": "Computers"}]
    for t in sorted(present_types, key=type_sort_key):
        categories.append({"key": t, "label": type_label(t) + "s"})

    (SITE_DIR / "index.html").write_text(
        env.get_template("index.html").render(
            config=config, assets=assets, categories=categories, root=""),
        encoding="utf-8")

    # --- one page per computer and per part ---
    comp_tpl = env.get_template("computer.html")
    for c in computers:
        out = SITE_DIR / "items" / c["asset_id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            comp_tpl.render(config=config, c=c, root="../../"), encoding="utf-8")

    part_tpl = env.get_template("part.html")
    for p in parts:
        out = SITE_DIR / "items" / p["asset_id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            part_tpl.render(config=config, p=p, root="../../"), encoding="utf-8")

    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {len(computers)} computer page(s) + {len(parts)} part page(s) "
          f"-> {SITE_DIR}")
    print("Open site/index.html in a browser to preview.")


def main():
    global IMAGES_DIR
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_api_arg(ap)
    ap.add_argument("--images", default="",
                    help="photo source dir (default: RHDB_IMAGES / config images_dir)")
    args = ap.parse_args()
    apply_api_arg(args)
    if args.images:
        import os
        os.environ["RHDB_IMAGES"] = args.images
    IMAGES_DIR = images_dir()
    build()


if __name__ == "__main__":
    main()
