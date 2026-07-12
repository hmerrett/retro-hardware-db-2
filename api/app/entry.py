"""Guided-entry vocabularies and quick-entry helpers, ported from the flat-file
system's scripts/add.py and common.py so the web GUI matches the established
data-entry model exactly.

Everything here is pure (no DB, no HTTP): the GUI endpoints in main.py call these
to turn friendly input (port letters, slot codes, 'N x size' RAM) into the stored
'Key: value | Key: value' specs and computer fields.
"""
from __future__ import annotations

import re
from collections import Counter

# --- type vocabulary -------------------------------------------------------

TYPE_ORDER = [
    "motherboard", "cpu", "ram", "video", "sound", "network", "io",
    "storage", "cooler", "peripheral", "other",
]

TYPE_LABELS = {
    "motherboard": "Motherboard", "cpu": "CPU", "ram": "Memory", "video": "Video",
    "sound": "Sound", "network": "Network", "io": "I/O", "storage": "Storage",
    "cooler": "Cooling", "peripheral": "Peripheral", "other": "Other",
}

# Expansion-card categories walked through when building out a machine.
CARD_STEPS = [
    ("video", "video card"),
    ("sound", "sound card"),
    ("network", "network card"),
    ("io", "I/O card"),
    ("other", "other expansion card"),
]

# Storage kinds that are their own tagged parts; the rest live on the computer's
# drives field.
PART_STORAGE_KINDS = ("Hard disk", "Tape")

# --- pick-list vocabularies ------------------------------------------------

CONDITIONS = ["Working", "Untested", "Partially working", "Faulty",
              "For parts/repair", "Restored"]
MOBO_FORM_FACTORS = ["AT", "Baby-AT", "ATX", "LPX", "NLX", "proprietary"]
CPU_FAMILIES = ["8088-class", "286-class", "386-class", "486-class",
                "Pentium-class", "Pentium Pro-class", "Pentium II/III-class",
                "Pentium 4-class", "Athlon-class", "Z80"]
RAM_SLOT_TYPES = ["30-pin SIMM", "72-pin SIMM", "168-pin DIMM", "184-pin DIMM"]
CARD_INTERFACES = ["8-bit ISA", "16-bit ISA", "EISA", "MCA", "VLB",
                   "PCI", "AGP", "PCIe x16", "USB"]
VIDEO_CONNECTORS = ["VGA", "DVI", "HDMI", "DisplayPort", "S-Video", "Composite",
                    "Component", "MDA", "CGA", "EGA"]
STORAGE_INTERFACES = ["IDE", "SCSI", "SATA", "MFM", "RLL", "ESDI", "CF", "SD",
                      "USB", "34-pin floppy"]
STORAGE_KINDS = ["Hard disk", "SD/CF card", "Tape", "Optical", "Floppy/Gotek"]
STORAGE_PROTOCOLS = ["ATA", "ATAPI", "SATA", "XTA", "RLL", "MFM", "ESDI", "SCSI"]
PERIPHERAL_INTERFACES = ["USB", "PS/2", "Serial", "Parallel", "VGA", "DIN"]

# Which spec keys each type suggests (drives the guided form fields).
SPEC_HINTS = {
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
    "peripheral": ["Interface", "Size", "Resolution"],
}


# --- specs parsing / merging -----------------------------------------------

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


def merge_spec(specs: str, key: str, value: str) -> str:
    """Set/replace 'key: value' inside a 'a: b | c: d' specs string."""
    pairs, replaced, out = parse_specs(specs), False, []
    for k, v in pairs:
        if k.lower() == key.lower():
            out.append((key, value))
            replaced = True
        else:
            out.append((k, v))
    if not replaced:
        out.append((key, value))
    return " | ".join(f"{k}: {v}" if k else v for k, v in out)


def build_specs(pairs) -> str:
    """Assemble ordered (key, value) pairs into a specs string, dropping blanks."""
    specs = ""
    for key, value in pairs:
        value = (value or "").strip()
        if value:
            specs = merge_spec(specs, key, value)
    return specs


# --- amounts / RAM ---------------------------------------------------------

_KB_UNITS = {"": 1024, "k": 1, "kb": 1, "m": 1024, "mb": 1024,
             "g": 1024 * 1024, "gb": 1024 * 1024,
             "t": 1024 * 1024 * 1024, "tb": 1024 * 1024 * 1024}


def to_kb(text: str):
    """'2MB'->2048, '512KB'->512, '2'->2048 (bare number assumed MB). None if
    unparseable."""
    m = re.match(r"^\s*([\d.]+)\s*([a-zA-Z]*)\s*$", text or "")
    if not m:
        return None
    unit = m.group(2).lower()
    if unit not in _KB_UNITS:
        return None
    try:
        return int(round(float(m.group(1)) * _KB_UNITS[unit]))
    except ValueError:
        return None


def normalise_amount(spec_key: str, amt: str) -> str:
    """Memory amounts (Size/Memory) normalise to KB; others kept as typed."""
    if spec_key in ("Size", "Memory"):
        kb = to_kb(amt)
        if kb is not None:
            return f"{kb} KB"
    return amt


def parse_installed_ram(text: str) -> str:
    """A computer's installed RAM, tidied. A leading 'N x size' becomes a module
    count plus a computed total: '8x1MB 30-pin' -> '8x 1MB 30-pin (8 MB)'. Text
    without an 'N x' (e.g. '16MB') is kept as typed. Idempotent."""
    t = " ".join((text or "").split())
    if not t:
        return ""
    m = re.match(r"(?i)^(\d+)\s*[x×]\s*([\d.]+\s*[kmg]?b?)\s*(.*)$", t)
    if not m:
        return t
    count, size_txt, rest = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
    rest = re.sub(r"(\s*\(\s*[\d.]+\s*[KMG]?B\s*\))+\s*$", "", rest, flags=re.I).strip()
    label = f"{count}× {size_txt}" + (f" {rest}" if rest else "")
    kb = to_kb(size_txt)
    if kb:
        total = count * kb
        label += f" ({total // 1024} MB)" if total % 1024 == 0 else f" ({total} KB)"
    return label


# --- quick-entry: ports (io cards + motherboard onboard I/O) ---------------

PORT_CODES = [("I", "IDE"), ("C", "SCSI"), ("A", "SATA"), ("M", "MFM"),
              ("R", "RLL"), ("F", "Floppy"), ("S", "Serial"), ("P", "Parallel"),
              ("G", "Game"), ("K", "PS/2 keyboard"), ("O", "PS/2 mouse"),
              ("D", "DIN keyboard"), ("U", "USB")]

PORT_LEGEND = " ".join(f"{ltr}={name}" for ltr, name in PORT_CODES)


def expand_ports(code: str) -> str:
    """'IFSSP' -> 'IDE, Floppy, 2x Serial, Parallel'. Order-independent; repeated
    letters become a count; unknown letters are ignored."""
    counts = Counter(c for c in (code or "").upper() if c.isalpha())
    out = []
    for letter, name in PORT_CODES:
        n = counts.get(letter, 0)
        if n:
            out.append(f"{n}× {name}" if n > 1 else name)
    return ", ".join(out)


# --- quick-entry: expansion slots (motherboard) ----------------------------

SLOT_TYPES = [
    ("8-bit ISA", ("8I", "I8", "8ISA", "8")),
    ("16-bit ISA", ("16I", "I16", "16ISA", "16")),
    ("EISA", ("E", "EISA")),
    ("MCA", ("M", "MCA")),
    ("VLB", ("V", "VL", "VLB")),
    ("PCI", ("P", "PCI")),
    ("AGP", ("A", "AGP")),
    ("PCIe x16", ("PCIE16", "X16")),
]
SLOT_NAMES = [name for name, _ in SLOT_TYPES]


def expand_slots(raw: str) -> str:
    """'8I:2 16I:6 VLB' -> '2x 8-bit ISA, 6x 16-bit ISA, VLB'. Tokens are 'key',
    'key:n', 'key*n' or 'keyxn'; order-independent; unknown tokens ignored."""
    alias = {c.upper(): name for name, codes in SLOT_TYPES for c in codes}
    counts = Counter()
    for tok in re.split(r"[\s,]+", (raw or "").strip()):
        if not tok:
            continue
        m = re.match(r"^(.+?)\s*[:*xX]\s*(\d+)$", tok)
        key, n = (m.group(1), int(m.group(2))) if m else (tok, 1)
        name = alias.get(key.upper())
        if name:
            counts[name] += n
    return ", ".join(f"{counts[name]}× {name}" if counts[name] > 1 else name
                     for name in SLOT_NAMES if counts.get(name))


# --- shared display helpers ------------------------------------------------

SHOUT_ACRONYMS = {
    "SCSI", "SATA", "PATA", "EISA", "ESDI", "VESA", "SVGA", "WXGA", "ATAPI",
    "BIOS", "UEFI", "DRAM", "SRAM", "SDRAM", "VRAM", "SIMM", "DIMM", "RIMM",
    "SIPP", "COAST", "CMOS", "MIDI", "EPROM", "EEPROM", "PROM", "MCGA",
    "PLCC", "NTSC", "SECAM", "WLAN", "ASIC",
}


def deshout(text: str) -> str:
    """De-shout a value word by word: a purely-uppercase token 5+ long that isn't
    a known acronym becomes Capitalised; short tokens, acronyms and part numbers
    are left alone."""
    out = []
    for tok in re.split(r"(\s+)", text or ""):
        core = tok.strip(".,:;()[]{}/\\\"'")
        if (core.isalpha() and core.isupper() and len(core) >= 5
                and core not in SHOUT_ACRONYMS):
            i = tok.find(core)
            tok = tok[:i] + core[0] + core[1:].lower() + tok[i + len(core):]
        out.append(tok)
    return "".join(out)


def display_name(row) -> str:
    if row.get("name"):
        return row["name"]
    joined = " ".join(p for p in (row.get("manufacturer", ""),
                                  row.get("model", "")) if p).strip()
    return joined or row.get("asset_id", "")


def type_label(t: str) -> str:
    return TYPE_LABELS.get(t, (t or "other").title())


def type_sort_key(t: str) -> int:
    try:
        return TYPE_ORDER.index(t)
    except ValueError:
        return len(TYPE_ORDER)
