"""Visual parameters derived from engineering data (never guessed)."""
from __future__ import annotations

from typing import Dict, Optional

from core.units import parse_quantity

BAND_COLORS = ["black", "brown", "red", "orange", "yellow", "green", "blue", "violet", "grey", "white"]
LED_COLORS = {"red": "#e53935", "green": "#43a047", "blue": "#1e88e5", "yellow": "#fdd835", "amber": "#ffb300",
              "orange": "#fb8c00", "white": "#f5f5f5", "warm white": "#fff3e0", "uv": "#7e57c2", "ir": "#5d4037",
              "pink": "#ec407a", "purple": "#8e24aa"}


def resistor_bands(value: Optional[str]) -> Optional[str]:
    """4-band colour code (two significant digits, multiplier, gold 5 %) for a resistance, or None."""
    ohms = parse_quantity(value, "ohm") if value else None
    if not ohms or ohms <= 0:
        return None
    exp = 0
    v = float(ohms)
    while v >= 100 - 1e-9:
        v /= 10
        exp += 1
    while v < 10 - 1e-9 and exp > -2:
        v *= 10
        exp -= 1
    digits = int(round(v))
    if digits >= 100:
        digits //= 10
        exp += 1
    d1, d2 = digits // 10, digits % 10
    mult = {-2: "silver", -1: "gold"}.get(exp, BAND_COLORS[exp] if 0 <= exp < 10 else None)
    if mult is None:
        return None
    return ",".join([BAND_COLORS[d1], BAND_COLORS[d2], mult, "gold"])


def visual_params(visual_kind: str, parameters: Dict[str, str], ctype_name: str, short_name: Optional[str]) -> Dict[str, str]:
    p: Dict[str, str] = {"text": short_name or ctype_name}
    if visual_kind in ("axial_resistor",):
        bands = resistor_bands(parameters.get("resistance"))
        if bands:
            p["bands"] = bands
    if visual_kind in ("led_5mm",):
        c = (parameters.get("color") or "").strip().lower()
        p["color"] = LED_COLORS.get(c, "#eceff1")
        p["color_known"] = "true" if c in LED_COLORS else "false"
    for k in ("capacitance", "resistance", "inductance"):
        if parameters.get(k):
            p["value"] = parameters[k]
    return p
