#!/usr/bin/env python3
"""Import a detector report (HWiNFO on 386+, or MSD on XT/286 machines) and
PROPOSE updates to its computer, its motherboard and its parts. Nothing is
written until you confirm. See bootdisk/README.md for the disk side.

Reports live in imports/ named after the asset id, e.g. imports/RH-0005.txt (or
.TXT). The report maps onto the model as:
  * computer    — cpu (Main Processor), os (if the report has it)
  * motherboard — Onboard video, BIOS, Chipset, Ports (onboard I/O), for the
                  board linked to that computer
  * storage     — one part per detected, non-empty drive

    python scripts/import_report.py            # every report in imports/
    python scripts/import_report.py RH-0005     # just one

HWiNFO's memory total is unreliable on pre-Pentium machines, so RAM is left to
the computer's installed_ram field (entered by hand).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rhdb import (PART_COLUMNS, ROOT, add_api_arg, apply_api_arg, create_part,
                  display_name, index_by_id, load_computers, load_parts,
                  parse_specs, update_computer, update_part)

IMPORTS_DIR = ROOT / "imports"

CHS_RE = re.compile(r"(\d{2,5})\s*[/xX]\s*(\d{1,3})\s*[/xX]\s*(\d{1,4})")
_EMPTY = {"", "n/a", "none", "not present", "unknown", "<empty>", "not found",
          "<skipped>", "0", "unknown or standard vga"}


def clean(v):
    return re.sub(r"\s+", " ", v or "").strip()


def has(v):
    return clean(v).lower() not in _EMPTY


def parse_pairs(text):
    """HWiNFO frames each line in CP437 box characters, which arrive as noise
    once decoded. Strip anything non-ASCII, then read 'Label: value'."""
    pairs = []
    for line in text.splitlines():
        s = clean("".join(c if 32 <= ord(c) < 127 else " " for c in line))
        if ":" not in s:
            continue
        k, v = s.split(":", 1)
        k = clean(k).lower()
        if k:
            pairs.append((k, clean(v)))
    return pairs


def set_spec(specs, key, value):
    """Set/replace 'key: value' inside a specs string."""
    out, replaced = [], False
    for k, v in parse_specs(specs):
        if k.lower() == key.lower():
            out.append((key, value))
            replaced = True
        else:
            out.append((k, v))
    if not replaced:
        out.append((key, value))
    return " | ".join(f"{k}: {v}" if k else v for k, v in out)


def detect_hwinfo(text):
    pairs = parse_pairs(text)

    def find(*keys):
        for want in keys:
            for k, v in pairs:
                if want in k:
                    return v
        return ""

    d = {}
    if has(find("main processor")):
        d["cpu"] = clean(find("main processor"))
    for field, keys in (("os", ("operating system", "dos version")),
                        ("bios", ("bios manufacturer",)),
                        ("chipset", ("mainboard chipset",))):
        if has(find(*keys)):
            d[field] = clean(find(*keys))
    if has(find("video chipset")):
        vmem = find("video memory size")
        d["onboard_video"] = (clean(find("video chipset"))
                              + (f" ({clean(vmem)})" if has(vmem) else ""))

    ports = []
    tl = text.lower()
    if "ide" in tl and ("primary" in tl or "ide channel" in tl):
        ports.append("IDE")
    if has(find("floppy drive")):
        ports.append("Floppy")
    ncom = sum(1 for k, v in pairs if k.startswith("serial port (com") and has(v))
    if ncom:
        ports.append(f"{ncom}× Serial" if ncom > 1 else "Serial")
    nlpt = sum(1 for k, v in pairs if k.startswith("parallel port (lpt") and has(v))
    if nlpt:
        ports.append(f"{nlpt}× Parallel" if nlpt > 1 else "Parallel")
    if ports:
        d["ports"] = ", ".join(ports)

    drives = [clean(v) for k, v in pairs
              if ("model" in k or "drive" in k) and CHS_RE.search(v)]
    d["drives"] = drives
    return d


def _is_msd(text):
    """MSD reports are plain ASCII with these section labels; HWiNFO reports
    are CP437 box-framed and say 'HWiNFO'."""
    t = text.lower()
    if "microsoft diagnostic" in t:
        return True
    hits = sum(m in t for m in ("os version", "lpt ports", "com ports",
                                "disk drives"))
    return hits >= 2 and "hwinfo" not in t


def detect_msd(text):
    """Parse a Microsoft Diagnostics (MSD /P) report into the same shape as
    detect_hwinfo. Tolerant of label/spacing differences across MSD versions;
    calibrate against a real MSD report if a field looks off."""
    pairs = parse_pairs(text)

    def find(*keys):
        for want in keys:
            for k, v in pairs:
                if want in k:
                    return v
        return ""

    def as_int(s):
        m = re.search(r"\d+", s or "")
        return int(m.group()) if m else 0

    d = {}
    for k, v in pairs:            # "Processor:" but not "Math Coprocessor:"
        if "processor" in k and "co" not in k and has(v):
            d["cpu"] = clean(v)
            break
    if has(find("os version", "operating system", "dos version")):
        d["os"] = clean(find("os version", "operating system", "dos version"))
    bios = find("bios manufacturer", "bios name")
    bdate = find("bios date")
    if has(bios):
        d["bios"] = clean(bios + (f" ({clean(bdate)})" if has(bdate) else ""))
    vtype = find("video adapter type", "video adapter", "adapter type")
    if has(vtype):
        d["onboard_video"] = clean(vtype)

    ports = []
    nlpt = as_int(find("lpt ports")) or sum(
        1 for k, v in pairs if k in ("lpt1", "lpt2", "lpt3") and has(v))
    ncom = as_int(find("com ports")) or sum(
        1 for k, v in pairs if k in ("com1", "com2", "com3", "com4") and has(v))
    if nlpt:
        ports.append(f"{nlpt}× Parallel" if nlpt > 1 else "Parallel")
    if ncom:
        ports.append(f"{ncom}× Serial" if ncom > 1 else "Serial")
    if ports:
        d["ports"] = ", ".join(ports)

    d["drives"] = [clean(v) for k, v in pairs
                   if ("drive" in k or "disk" in k or "model" in k)
                   and CHS_RE.search(v)]
    return d


def detect(text):
    """Dispatch on report format: MSD from the XT/286 disk, else HWiNFO."""
    return detect_msd(text) if _is_msd(text) else detect_hwinfo(text)


def blank_part(computer_id):
    row = {c: "" for c in PART_COLUMNS}
    row["computer_id"] = computer_id
    row["condition"] = "Working"
    return row


def propose(comp, mobo, det):
    """Return (computer updates, motherboard spec updates, [new part rows])."""
    cupd = {}
    if det.get("cpu") and not comp.get("cpu"):
        cupd["cpu"] = det["cpu"]
    if det.get("os") and not comp.get("os"):
        cupd["os"] = det["os"]

    mupd = {}
    if mobo is not None:
        ms = {k: v for k, v in parse_specs(mobo.get("specs", ""))}
        for spec, key in (("Onboard video", "onboard_video"), ("BIOS", "bios"),
                          ("Chipset", "chipset"), ("Ports", "ports")):
            if det.get(key) and not ms.get(spec):
                mupd[spec] = det[key]

    parts_out = []
    for drv in det.get("drives", []):
        r = blank_part(comp["asset_id"])
        chs = CHS_RE.search(drv)
        specs = "Kind: Hard disk | Interface: IDE"
        if chs:
            specs += f" | CHS: {chs.group(1)}/{chs.group(2)}/{chs.group(3)}"
        r.update(type="storage", name="Detected drive", specs=specs,
                 notes=f"detected via boot report: {drv}")
        parts_out.append(r)
    return cupd, mupd, parts_out


def ask(q):
    try:
        return input(q).strip().lower().startswith("y")
    except EOFError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    add_api_arg(ap)
    ap.add_argument("only", nargs="?", default=None,
                    help="import just this asset id (default: every report in imports/)")
    args = ap.parse_args()
    apply_api_arg(args)
    only = args.only
    if not IMPORTS_DIR.exists():
        print(f"No imports/ folder yet — drop reports in {IMPORTS_DIR}")
        return

    computers = load_computers()
    parts = load_parts()
    comp_by_id = index_by_id(computers)
    mobo_by_comp = {}
    for p in parts:
        if p.get("type") == "motherboard" and p.get("computer_id"):
            mobo_by_comp.setdefault(p["computer_id"], p)

    reports = sorted(p for p in IMPORTS_DIR.iterdir()
                     if p.is_file() and p.suffix.lower() == ".txt")
    if only:
        reports = [r for r in reports if r.stem.lower() == only.lower()]
        if not reports:
            print(f"No report imports/{only}.txt")
            return

    wrote_c = wrote_p = 0
    for rpt in reports:
        det = detect(rpt.read_text(encoding="utf-8", errors="replace"))
        asset_id = rpt.stem
        comp = comp_by_id.get(asset_id) or comp_by_id.get(asset_id.upper())
        if not comp:
            # Auto-named report (e.g. SCAN03 from the boot disk's non-interactive
            # scan) — show what it detected, then attach it to a machine by hand.
            ident = ", ".join(f"{k.replace('_', ' ')}={det[k]}"
                              for k in ("cpu", "bios", "os", "onboard_video")
                              if det.get(k))
            print(f"\n{rpt.name}: not an asset id — detected {ident or '(nothing)'}")
            try:
                ans = input("  attach to which asset id? (RH-xxxx, blank=skip): ").strip()
            except EOFError:
                ans = ""
            comp = comp_by_id.get(ans) or comp_by_id.get(ans.upper())
            if not comp:
                print("  skipped.")
                continue
            asset_id = comp["asset_id"]
        mobo = mobo_by_comp.get(asset_id)
        cupd, mupd, new_parts = propose(comp, mobo, det)

        print(f"\n=== {asset_id}  {display_name(comp)} ===")
        for k in ("cpu", "os", "onboard_video", "bios", "chipset", "ports"):
            if det.get(k):
                print(f"  detected {k.replace('_', ' ')}: {det[k]}")
        for drv in det.get("drives", []):
            print(f"  detected drive: {drv}")
        if not (cupd or mupd or new_parts):
            print("  (already recorded, or nothing new detected)")
            continue
        if cupd:
            print("  would set on the computer: "
                  + ", ".join(f"{k}={v}" for k, v in cupd.items()))
        if mupd and mobo is not None:
            print(f"  would set on motherboard {mobo['asset_id']}: "
                  + ", ".join(f"{k}={v}" for k, v in mupd.items()))
        for r in new_parts:
            print(f"  would add part: {r['type']}  [{r['specs']}]")

        if not ask("  apply these? (y/N) "):
            print("  skipped.")
            continue

        if cupd:
            update_computer(comp["asset_id"], cupd)
            comp.update(cupd)
            wrote_c += 1
        if mupd and mobo is not None:
            specs = mobo.get("specs", "")
            for k, v in mupd.items():
                specs = set_spec(specs, k, v)
            update_part(mobo["asset_id"], {"specs": specs})
            mobo["specs"] = specs
        for r in new_parts:
            # The API assigns the asset id; send only the meaningful fields.
            payload = {k: v for k, v in r.items() if k != "asset_id" and v}
            create_part(payload)
        if mupd or new_parts:
            wrote_p += 1
        print("  applied.")

    if wrote_c or wrote_p:
        print(f"\nApplied to the API: {wrote_c} computer(s) updated, {wrote_p} "
              "with motherboard/parts changes. Rebuild with build_site.py.")
    else:
        print("\nNothing written.")


if __name__ == "__main__":
    main()
