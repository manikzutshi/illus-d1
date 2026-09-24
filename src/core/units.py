"""Engineering quantity parsing/formatting.

Deterministic, dependency-free helpers used wherever a human- or AI-supplied value
string (``"4.7k"``, ``"10uF"``, ``"3.3V"``, ``"220 Ω"``) must become a number.
Unparseable input returns ``None`` - callers must treat that as *unknown*, never guess.
"""
from __future__ import annotations

import math
import re
from typing import Optional

_PREFIX = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
    "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9,
}
_UNITS = ("ohm", "ohms", "Ω", "Ω", "F", "H", "V", "A", "Hz", "W", "s", "R")

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_RE = re.compile(
    rf"^\s*(?P<num>{_NUM})\s*(?P<prefix>[pnuµμmkKMG]?)\s*(?P<unit>ohms?|Ω|Ω|F|H|V|A|Hz|W|s|R)?\s*$"
)
# RKM code: 4k7, 2R2, 1M5
_RKM = re.compile(r"^\s*(?P<a>\d+)(?P<p>[RkKM])(?P<b>\d+)\s*(?:ohms?|Ω)?\s*$")


def parse_quantity(text: object, expected_unit: Optional[str] = None) -> Optional[float]:
    """Parse an engineering quantity to a float in base SI units.

    ``expected_unit`` (e.g. "V", "F", "ohm") rejects values carrying a *different*
    explicit unit. Returns None when the value cannot be parsed unambiguously.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text) if math.isfinite(float(text)) else None
    s = str(text).strip()
    if not s:
        return None
    m = _RKM.match(s)
    if m:
        mult = 1.0 if m.group("p") == "R" else _PREFIX[m.group("p")]
        return float(f"{float(m.group('a') + '.' + m.group('b')) * mult:.12g}")
    m = _RE.match(s)
    if not m:
        return None
    prefix, unit = m.group("prefix"), m.group("unit")
    # "m" with unit "ohm" is milli; bare "M" is mega. A lone "m"/"M" without unit is ambiguous
    # only for "m" vs "M" which are distinct characters, so it is fine.
    if expected_unit and unit:
        norm = {"ohms": "ohm", "Ω": "ohm", "Ω": "ohm", "R": "ohm"}.get(unit, unit)
        exp = {"ohms": "ohm", "Ω": "ohm", "Ω": "ohm", "R": "ohm"}.get(expected_unit, expected_unit)
        if norm != exp:
            return None
    value = float(f"{float(m.group('num')) * _PREFIX[prefix]:.12g}")
    return value if math.isfinite(value) else None


def parse_range(text: object, expected_unit: Optional[str] = None) -> Optional[tuple[float, float]]:
    """Parse ``"3.3V-5V"`` / ``"2.0V-6.0V"`` / ``"5V"`` into (min, max)."""
    if text is None:
        return None
    s = str(text).strip()
    parts = re.split(r"\s*(?:-|–|to)\s*(?=\d)", s)
    if len(parts) == 2:
        a, b = parse_quantity(parts[0], expected_unit), parse_quantity(parts[1], expected_unit)
        if a is None and b is not None:
            # "3.3-5V": unit only on the second value
            a = parse_quantity(parts[0] + re.sub(r"^[-+\d.eE\s]*", "", parts[1]), expected_unit)
        if a is not None and b is not None:
            return (min(a, b), max(a, b))
        return None
    v = parse_quantity(s, expected_unit)
    return (v, v) if v is not None else None


def format_quantity(value: Optional[float], unit: str = "", digits: int = 3) -> str:
    """Format a value with an SI prefix: 4700 -> '4.7k', 1e-7 -> '100n'."""
    if value is None:
        return "unknown"
    if value == 0:
        return f"0{unit}"
    exp = int(math.floor(math.log10(abs(value)) / 3) * 3)
    exp = max(-12, min(9, exp))
    prefix = {-12: "p", -9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}[exp]
    scaled = value / (10 ** exp)
    text = f"{scaled:.{digits}g}"
    return f"{text}{prefix}{unit}"
