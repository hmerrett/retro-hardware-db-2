"""Convert between the free-text specs string ('Key: value | Key: value') and a
normalised structure, so the relational spec tables and the legacy specs string
stay in agreement.

- parse(ptype, specs) -> Struct: scalars (mapped to DB columns), the count-list
  fields (slots / RAM slots / ports), storage CHS split into ints, and a
  key/value fallback for free-form types.
- format(ptype, struct) -> specs string: the canonical rendering, used to keep
  parts.specs as a denormalised cache and to render spec tables.

Everything here is pure (no DB); models.py owns the tables and main.py maps a
Struct onto them.
"""
from __future__ import annotations

import re

from .entry import parse_specs

# Spec-key -> column name, per typed table. Aliases (Chipset->chip) collapse on
# the way in; format() uses the display order below on the way out.
SCALARS = {
    "motherboard": {"Chipset": "chipset", "CPU family": "cpu_family",
                    "Form factor": "form_factor", "Cache": "cache",
                    "BIOS": "bios", "Onboard video": "onboard_video"},
    "cpu": {"Socket": "socket", "Speed": "speed", "FSB": "fsb", "Cores": "cores",
            "Cache": "cache", "L2 cache": "cache", "L1/L2 cache": "cache"},
    "ram": {"Type": "ram_type", "Size": "size_kb", "Speed": "speed"},
    "video": {"Chip": "chip", "Chipset": "chip", "Interface": "interface",
              "Connector": "connector", "Memory": "memory_kb", "Type": "video_type"},
    "sound": {"Chip": "chip", "Chipset": "chip", "Interface": "interface",
              "FM": "fm", "Ports": "ports"},
    "network": {"Chip": "chip", "Chipset": "chip", "Interface": "interface",
                "Connector": "connector"},
    "io": {"Chip": "chip", "Chipset": "chip", "Interface": "interface"},
    "storage": {"Kind": "kind", "Interface": "interface", "Protocol": "protocol",
                "Capacity": "capacity", "Media": "media", "Speed": "speed",
                "Role": "role"},
}

# Columns holding an integer count of KB (parsed from 'N KB' / 'N MB' / bare).
KB_COLS = {"size_kb", "memory_kb"}
INT_COLS = {"cores"}

# Count-list spec keys, per type -> which Struct list they populate.
LIST_KEYS = {
    "motherboard": {"Slots": "slots", "RAM slots": "ram_slots", "Ports": "ports"},
    "io": {"Ports": "ports"},
}

# Display order per type for format() (includes list + CHS keys).
ORDER = {
    "motherboard": ["Chipset", "CPU family", "Form factor", "RAM slots", "Slots",
                    "Cache", "BIOS", "Onboard video", "Ports"],
    "cpu": ["Socket", "Speed", "FSB", "Cores", "Cache"],
    "ram": ["Type", "Size", "Speed"],
    "video": ["Chip", "Interface", "Connector", "Memory", "Type"],
    "sound": ["Chip", "Interface", "FM", "Ports"],
    "network": ["Chip", "Interface", "Connector"],
    "io": ["Chip", "Interface", "Ports"],
    "storage": ["Kind", "Interface", "Protocol", "Capacity", "CHS", "Media",
                "Speed", "Role"],
}
# Which column a display key reads from in format() (first alias wins).
DISPLAY_COL = {t: {} for t in SCALARS}
for _t, _m in SCALARS.items():
    for _key, _col in _m.items():
        DISPLAY_COL[_t].setdefault(_col, _key)

TYPED = set(SCALARS)

_COUNT_RE = re.compile(r"^\s*(\d+)\s*[×x]\s*(.+?)\s*$")
_KB_RE = re.compile(r"^\s*([\d.]+)\s*([kKmMgG]?)[bB]?\s*$")
_CHS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*$")


class Struct:
    __slots__ = ("scalars", "slots", "ram_slots", "ports", "chs", "attributes")

    def __init__(self):
        self.scalars = {}
        self.slots = []
        self.ram_slots = []
        self.ports = []
        self.chs = None
        self.attributes = []


def _to_kb(text):
    m = _KB_RE.match(text or "")
    if not m:
        return None
    unit = m.group(2).lower()
    mult = {"": 1, "k": 1, "m": 1024, "g": 1024 * 1024}.get(unit, 1)
    try:
        return int(round(float(m.group(1)) * mult))
    except ValueError:
        return None


def _parse_counts(value):
    """'2× 8-bit ISA, 6× 16-bit ISA, VLB' -> [('8-bit ISA', 2), ('16-bit ISA', 6),
    ('VLB', 1)]."""
    out = []
    for tok in (value or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = _COUNT_RE.match(tok)
        if m:
            out.append((m.group(2).strip(), int(m.group(1))))
        else:
            out.append((tok, 1))
    return out


def _fmt_counts(items):
    return ", ".join(f"{n}× {name}" if n and n > 1 else name for name, n in items)


def parse(ptype, specs) -> Struct:
    s = Struct()
    pairs = parse_specs(specs)
    if ptype not in TYPED:
        s.attributes = list(pairs)
        return s
    scalar_map = SCALARS[ptype]
    list_map = LIST_KEYS.get(ptype, {})
    for k, v in pairs:
        if not k:
            # A bare value with no key (messy legacy entry) -- keep it verbatim.
            s.attributes.append((k, v))
            continue
        if k in list_map:
            getattr(s, list_map[k]).extend(_parse_counts(v))
        elif ptype == "storage" and k == "CHS":
            m = _CHS_RE.match(v)
            s.chs = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
            if not m:
                s.attributes.append((k, v))
        elif k in scalar_map:
            col = scalar_map[k]
            if col in KB_COLS:
                kb = _to_kb(v)
                s.scalars[col] = kb if kb is not None else None
                if kb is None:
                    s.attributes.append((k, v))
            elif col in INT_COLS:
                m = re.match(r"^\s*(\d+)", v)
                s.scalars[col] = int(m.group(1)) if m else None
                if not m:
                    s.attributes.append((k, v))
            else:
                s.scalars[col] = v
        else:
            s.attributes.append((k, v))
    return s


def format(ptype, s) -> str:
    """Canonical specs string from a Struct (or a mapping produced by main.py)."""
    pairs = []
    if ptype in ORDER:
        for key in ORDER[ptype]:
            if key in ("Slots", "RAM slots", "Ports") and key in LIST_KEYS.get(ptype, {}):
                items = getattr(s, LIST_KEYS[ptype][key])
                if items:
                    pairs.append((key, _fmt_counts(items)))
            elif key == "CHS" and ptype == "storage":
                if s.chs:
                    pairs.append(("CHS", "{}/{}/{}".format(*s.chs)))
            else:
                col = SCALARS[ptype].get(key)
                if col and s.scalars.get(col) not in (None, ""):
                    val = s.scalars[col]
                    if col in KB_COLS:
                        val = f"{val} KB"
                    pairs.append((key, str(val)))
    pairs.extend(s.attributes)
    return " | ".join(f"{k}: {v}" if k else str(v) for k, v in pairs)
