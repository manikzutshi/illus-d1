"""Schematic symbol library.

Symbols are *data*: drawing primitives plus pins (tip positions on the integer grid and an
outward orientation). The same definitions drive the layout engine (pin geometry), the SVG
exporter and the browser renderer, so there is exactly one description of every symbol.

Fixed symbols follow common IEEE/ANSI conventions. Parts without a dedicated symbol get a
generated IC box (``build_box_symbol``) whose pin sides are chosen by the layout engine.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, List, Optional

from core.models import ComponentType
from core.enums import PinDirection
from .models import SymbolDef, SymbolPin, SymbolPrimitive as P

# ── primitive helpers ──────────────────────────────────────────────────────

def _line(x1, y1, x2, y2, w=0.15) -> P:
    return P(kind="line", points=[[x1, y1], [x2, y2]], width=w)


def _poly(points, closed=False, fill="none", w=0.15) -> P:
    return P(kind="polygon" if closed else "polyline", points=[list(p) for p in points], fill=fill, width=w)


def _rect(x0, y0, x1, y1, fill="body", w=0.18) -> P:
    return P(kind="rect", x=x0, y=y0, w=x1 - x0, h=y1 - y0, fill=fill, width=w)


def _circle(cx, cy, r, fill="none", w=0.15) -> P:
    return P(kind="circle", x=cx, y=cy, r=r, fill=fill, width=w)


def _path(d, fill="none", w=0.15) -> P:
    return P(kind="path", d=d, fill=fill, width=w)


def _text(x, y, s, size=0.9, anchor="middle") -> P:
    return P(kind="text", x=x, y=y, text=s, size=size, anchor=anchor)


def _arrow(x1, y1, x2, y2, head=0.35) -> list[P]:
    """Line with a filled arrowhead at (x2, y2)."""
    ang = math.atan2(y2 - y1, x2 - x1)
    a1 = (x2 - head * math.cos(ang - 0.45), y2 - head * math.sin(ang - 0.45))
    a2 = (x2 - head * math.cos(ang + 0.45), y2 - head * math.sin(ang + 0.45))
    r = lambda v: round(v, 3)
    return [_line(x1, y1, x2, y2, 0.1), _poly([(x2, y2), (r(a1[0]), r(a1[1])), (r(a2[0]), r(a2[1]))], closed=True, fill="outline", w=0.08)]


def _pin(name, x, y, orient, length=2.0, number=None, show_name=False) -> SymbolPin:
    return SymbolPin(name=name, x=x, y=y, orientation=orient, length=length, number=number, show_name=show_name)


# ── fixed symbols ──────────────────────────────────────────────────────────

_ZIGZAG = [(-2, 0), (-1.67, -0.7), (-1, 0.7), (-0.33, -0.7), (0.33, 0.7), (1, -0.7), (1.67, 0.7), (2, 0)]


def _resistor() -> SymbolDef:
    return SymbolDef(symbol_id="resistor", graphics=[_poly(_ZIGZAG)],
                     pins=[_pin("1", -3, 0, "left", 1), _pin("2", 3, 0, "right", 1)],
                     body=[-2, -0.8, 2, 0.8], description="Resistor (IEEE zig-zag)")


def _photoresistor() -> SymbolDef:
    g = [_poly(_ZIGZAG), *_arrow(-2.2, -2.6, -1.0, -1.2), *_arrow(-0.9, -2.9, 0.3, -1.5)]
    return SymbolDef(symbol_id="photoresistor", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 1), _pin("2", 3, 0, "right", 1)],
                     body=[-2.3, -2.9, 2, 0.8], description="Light dependent resistor")


def _thermistor() -> SymbolDef:
    g = [_poly(_ZIGZAG), _poly([(-2, 1.4), (-1.3, 1.4), (1.6, -1.4)]), _text(1.4, 1.5, "t°", 0.8)]
    return SymbolDef(symbol_id="thermistor", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 1), _pin("2", 3, 0, "right", 1)],
                     body=[-2, -1.4, 2, 1.6], description="Thermistor")


def _potentiometer() -> SymbolDef:
    g = [_poly(_ZIGZAG), *_arrow(0, 2, 0, 0.8)]
    return SymbolDef(symbol_id="potentiometer", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 1), _pin("3", 3, 0, "right", 1), _pin("2", 0, 3, "down", 1)],
                     body=[-2, -0.8, 2, 2], description="Potentiometer (wiper = pin 2)")


def _capacitor() -> SymbolDef:
    g = [_line(-0.4, -1.3, -0.4, 1.3, 0.2), _line(0.4, -1.3, 0.4, 1.3, 0.2)]
    return SymbolDef(symbol_id="capacitor", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 2.6), _pin("2", 3, 0, "right", 2.6)],
                     body=[-0.4, -1.3, 0.4, 1.3], description="Capacitor")


def _capacitor_polarized() -> SymbolDef:
    g = [_line(-0.4, -1.3, -0.4, 1.3, 0.2), _path("M 0.9 -1.3 Q 0.3 0 0.9 1.3", w=0.2),
         _text(-1.3, -0.9, "+", 0.9)]
    return SymbolDef(symbol_id="capacitor_polarized", graphics=g,
                     pins=[_pin("+", -3, 0, "left", 2.6), _pin("-", 3, 0, "right", 2.4)],
                     body=[-1.6, -1.6, 0.9, 1.3], description="Polarised capacitor")


def _inductor() -> SymbolDef:
    d = "M -2 0 " + " ".join(f"A 0.5 0.5 0 0 1 {x} 0" for x in (-1, 0, 1, 2))
    return SymbolDef(symbol_id="inductor", graphics=[_path(d)],
                     pins=[_pin("1", -3, 0, "left", 1), _pin("2", 3, 0, "right", 1)],
                     body=[-2, -0.6, 2, 0.1], description="Inductor")


def _diode_base(symbol_id: str, bar: list[P], extra: Optional[list[P]] = None, desc: str = "") -> SymbolDef:
    g = [_poly([(-1, -1), (-1, 1), (1, 0)], closed=True, fill="outline"), _line(-1, 0, 1, 0), *bar, *(extra or [])]
    return SymbolDef(symbol_id=symbol_id, graphics=g,
                     pins=[_pin("A", -3, 0, "left", 2), _pin("K", 3, 0, "right", 2)],
                     body=[-1, -1.2, 1, 1.2] if not extra else [-1, -2.6, 2.2, 1.2], description=desc)


def _diode() -> SymbolDef:
    return _diode_base("diode", [_line(1, -1, 1, 1, 0.2)], desc="Diode")


def _zener() -> SymbolDef:
    return _diode_base("zener", [_poly([(0.6, -1.2), (1, -1), (1, 1), (1.4, 1.2)], w=0.2)], desc="Zener diode")


def _schottky() -> SymbolDef:
    return _diode_base("schottky", [_poly([(1.4, -0.7), (1.4, -1), (1, -1), (1, 1), (0.6, 1), (0.6, 0.7)], w=0.2)],
                       desc="Schottky diode")


def _led() -> SymbolDef:
    return _diode_base("led", [_line(1, -1, 1, 1, 0.2)],
                       extra=[*_arrow(0.2, -1.2, 1.1, -2.2), *_arrow(0.9, -0.9, 1.9, -1.9)], desc="Light emitting diode")


def _npn() -> SymbolDef:
    g = [_circle(0.3, 0, 2.0), _line(-0.5, -1.2, -0.5, 1.2, 0.25), _line(-0.5, -0.5, 1, -1.5),
         _line(-0.5, 0.5, 1, 1.5), *_arrow(-0.5, 0.5, 0.85, 1.4)]
    return SymbolDef(symbol_id="npn", graphics=g,
                     pins=[_pin("B", -3, 0, "left", 2.5), _pin("C", 1, -3, "up", 1.5), _pin("E", 1, 3, "down", 1.5)],
                     body=[-1.7, -2, 2.3, 2], description="NPN bipolar transistor")


def _pnp() -> SymbolDef:
    g = [_circle(0.3, 0, 2.0), _line(-0.5, -1.2, -0.5, 1.2, 0.25), _line(-0.5, 0.5, 1, 1.5),
         _line(1, -1.5, -0.5, -0.5), *_arrow(1, -1.5, -0.35, -0.6)]
    return SymbolDef(symbol_id="pnp", graphics=g,
                     pins=[_pin("B", -3, 0, "left", 2.5), _pin("E", 1, -3, "up", 1.5), _pin("C", 1, 3, "down", 1.5)],
                     body=[-1.7, -2, 2.3, 2], description="PNP bipolar transistor")


def _mos(symbol_id: str, p_channel: bool) -> SymbolDef:
    top, bottom = ("S", "D") if p_channel else ("D", "S")
    g = [_circle(0.3, 0, 2.0), _line(-1, -1, -1, 1, 0.2),
         _line(-0.5, -1.2, -0.5, -0.6, 0.25), _line(-0.5, -0.3, -0.5, 0.3, 0.25), _line(-0.5, 0.6, -0.5, 1.2, 0.25),
         _poly([(-0.5, -0.9), (1, -0.9), (1, -1.5)]), _poly([(-0.5, 0.9), (1, 0.9), (1, 1.5)]),
         _line(1, 0, 1, 0.9)]
    g += _arrow(-0.5, 0, 1, 0) if p_channel else _arrow(1, 0, -0.45, 0)
    return SymbolDef(symbol_id=symbol_id, graphics=g,
                     pins=[_pin("G", -3, 0, "left", 2), _pin(top, 1, -3, "up", 1.5), _pin(bottom, 1, 3, "down", 1.5)],
                     body=[-1.7, -2, 2.3, 2],
                     description=("P" if p_channel else "N") + "-channel enhancement MOSFET")


def _opamp() -> SymbolDef:
    g = [_poly([(-2, -3), (-2, 3), (3, 0)], closed=True, fill="body"), _text(-1.3, -0.65, "−", 1.0),
         _text(-1.3, 1.35, "+", 1.0)]
    return SymbolDef(symbol_id="opamp", graphics=g,
                     pins=[_pin("-", -4, -1, "left", 2), _pin("+", -4, 1, "left", 2), _pin("OUT", 4, 0, "right", 1),
                           _pin("V+", 0, -3, "up", 1.8), _pin("V-", 0, 3, "down", 1.8)],
                     body=[-2, -3, 3, 3], description="Operational amplifier / comparator")


def _gate(symbol_id: str, shape: str, invert: bool, inputs: int = 2) -> SymbolDef:
    g: list[P] = []
    tip_x = 2.0
    if shape == "and":
        g.append(_path("M -2 -1.5 L 0.5 -1.5 A 1.5 1.5 0 0 1 0.5 1.5 L -2 1.5 Z", fill="body"))
    elif shape in ("or", "xor"):
        g.append(_path("M -2 -1.5 Q -1 0 -2 1.5 Q 0.8 1.5 2 0 Q 0.8 -1.5 -2 -1.5 Z", fill="body"))
        if shape == "xor":
            g.append(_path("M -2.5 -1.5 Q -1.5 0 -2.5 1.5"))
    elif shape == "buf":
        g.append(_poly([(-1.5, -1.4), (-1.5, 1.4), (1.2, 0)], closed=True, fill="body"))
        tip_x = 1.2
    if invert:
        g.append(_circle(tip_x + 0.3, 0, 0.3))
        tip_x += 0.6
    if inputs == 1:
        pins = [_pin("A", -4, 0, "left", 2.5 if shape == "buf" else 2)]
    else:
        back = -2 if shape == "and" else -1.7
        pins = [_pin("A", -4, -1, "left", 4 + back), _pin("B", -4, 1, "left", 4 + back)]
    pins.append(_pin("Y", 4, 0, "right", round(4 - tip_x, 3)))
    return SymbolDef(symbol_id=symbol_id, graphics=g, pins=pins, body=[-2.5, -1.6, tip_x, 1.6],
                     description=f"{symbol_id.upper()} logic gate")


def _dff() -> SymbolDef:
    g = [_rect(-2.5, -3, 2.5, 3), _poly([(-2.5, 1.5), (-1.8, 2), (-2.5, 2.5)]),
         _text(-2.1, -1.65, "D", 0.8, "start"), _text(2.1, -1.65, "Q", 0.8, "end"), _text(2.1, 2.35, "Q̅", 0.8, "end")]
    return SymbolDef(symbol_id="dff", graphics=g,
                     pins=[_pin("D", -4, -2, "left", 1.5), _pin("CLK", -4, 2, "left", 1.5),
                           _pin("Q", 4, -2, "right", 1.5), _pin("QN", 4, 2, "right", 1.5)],
                     body=[-2.5, -3, 2.5, 3], description="D flip-flop")


def _switch_push() -> SymbolDef:
    g = [_circle(-1.2, 0, 0.25), _circle(1.2, 0, 0.25), _line(-1.5, -0.8, 1.5, -0.8, 0.2),
         _line(0, -0.8, 0, -1.8), _line(-0.6, -1.8, 0.6, -1.8)]
    return SymbolDef(symbol_id="switch_push", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 1.55), _pin("2", 3, 0, "right", 1.55)],
                     body=[-1.5, -1.8, 1.5, 0.3], description="Momentary push button")


def _switch_push_4pin() -> SymbolDef:
    g = [_circle(-1.2, 0, 0.25), _circle(1.2, 0, 0.25), _line(-1.5, -0.8, 1.5, -0.8, 0.2),
         _line(0, -0.8, 0, -1.8), _line(-0.6, -1.8, 0.6, -1.8),
         _line(-2, 0, -2, 2), _line(2, 0, 2, 2), _circle(-2, 0, 0.15, fill="outline"), _circle(2, 0, 0.15, fill="outline")]
    return SymbolDef(symbol_id="switch_push_4pin", graphics=g,
                     pins=[_pin("1A", -3, 0, "left", 1.55), _pin("2A", 3, 0, "right", 1.55),
                           _pin("1B", -3, 2, "left", 1), _pin("2B", 3, 2, "right", 1)],
                     body=[-2, -1.8, 2, 2], description="4-pin tactile switch (1A=1B, 2A=2B internally)")


def _switch_spst() -> SymbolDef:
    g = [_circle(-1.2, 0, 0.25), _circle(1.2, 0, 0.25), _line(-1.0, -0.1, 1.3, -1.2, 0.2)]
    return SymbolDef(symbol_id="switch_spst", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 1.55), _pin("2", 3, 0, "right", 1.55)],
                     body=[-1.5, -1.3, 1.5, 0.3], description="SPST switch")


def _battery() -> SymbolDef:
    g = [_line(-1.5, -1, 1.5, -1, 0.2), _line(-0.8, -0.4, 0.8, -0.4, 0.35),
         _line(-1.5, 0.4, 1.5, 0.4, 0.2), _line(-0.8, 1, 0.8, 1, 0.35), _text(1.6, -1.35, "+", 0.9)]
    return SymbolDef(symbol_id="battery", graphics=g,
                     pins=[_pin("+", 0, -3, "up", 2), _pin("-", 0, 3, "down", 2)],
                     body=[-1.5, -1.8, 2.1, 1.2], description="Battery")


def _dc_source() -> SymbolDef:
    g = [_circle(0, 0, 1.5), _text(0, -0.25, "+", 0.9), _text(0, 1.05, "−", 0.9)]
    return SymbolDef(symbol_id="dc_source", graphics=g,
                     pins=[_pin("+", 0, -3, "up", 1.5), _pin("-", 0, 3, "down", 1.5)],
                     body=[-1.5, -1.5, 1.5, 1.5], description="Ideal DC voltage source")


def _motor() -> SymbolDef:
    return SymbolDef(symbol_id="motor", graphics=[_circle(0, 0, 1.6), _text(0, 0.45, "M", 1.2)],
                     pins=[_pin("1", 0, -3, "up", 1.4), _pin("2", 0, 3, "down", 1.4)],
                     body=[-1.6, -1.6, 1.6, 1.6], description="DC motor")


def _buzzer() -> SymbolDef:
    g = [_rect(-1.4, -1.2, 1.4, 1.2), _path("M -0.8 0.6 A 0.8 0.8 0 0 1 0.8 0.6"), _line(-0.8, 0.6, 0.8, 0.6),
         _text(1.9, -1.4, "+", 0.8)]
    return SymbolDef(symbol_id="buzzer", graphics=g,
                     pins=[_pin("+", 0, -3, "up", 1.8), _pin("-", 0, 3, "down", 1.8)],
                     body=[-1.4, -1.8, 2.2, 1.2], description="Buzzer")


def _regulator() -> SymbolDef:
    g = [_rect(-3, -2, 3, 2), _text(-2.6, 0.35, "IN", 0.8, "start"), _text(2.6, 0.35, "OUT", 0.8, "end"),
         _text(0, 1.6, "GND", 0.8)]
    return SymbolDef(symbol_id="regulator", graphics=g,
                     pins=[_pin("VIN", -5, 0, "left", 2), _pin("VOUT", 5, 0, "right", 2), _pin("GND", 0, 4, "down", 2)],
                     body=[-3, -2, 3, 2], description="Three-terminal voltage regulator")


def _logic_in() -> SymbolDef:
    g = [_poly([(-3, -1), (0.2, -1), (1.2, 0), (0.2, 1), (-3, 1)], closed=True, fill="body")]
    return SymbolDef(symbol_id="logic_in", graphics=g, pins=[_pin("OUT", 3, 0, "right", 1.8)],
                     body=[-3, -1, 1.2, 1], description="Logic input stimulus")


def _logic_out() -> SymbolDef:
    g = [_poly([(-1.2, 0), (-0.2, -1), (3, -1), (3, 1), (-0.2, 1)], closed=True, fill="body")]
    return SymbolDef(symbol_id="logic_out", graphics=g, pins=[_pin("IN", -3, 0, "left", 1.8)],
                     body=[-1.2, -1, 3, 1], description="Logic output probe")


def _jumper() -> SymbolDef:
    g = [_circle(-1.2, 0, 0.3, fill="outline"), _circle(1.2, 0, 0.3, fill="outline"), _path("M -1.2 -0.3 Q 0 -1.3 1.2 -0.3", w=0.18)]
    return SymbolDef(symbol_id="jumper", graphics=g,
                     pins=[_pin("1", -3, 0, "left", 1.5), _pin("2", 3, 0, "right", 1.5)],
                     body=[-1.5, -1.0, 1.5, 0.4], description="Wire jumper / link")


def _power_flag() -> SymbolDef:
    g = [_line(0, 0, 0, -1), _line(-1, -1, 1, -1, 0.2)]
    return SymbolDef(symbol_id="power_flag", kind="power_flag", graphics=g,
                     pins=[_pin("1", 0, 0, "down", 0)], body=[-1, -1.2, 1, 0], description="Supply rail source")


def _ground_flag() -> SymbolDef:
    g = [_line(0, 0, 0, 1), _line(-1.2, 1, 1.2, 1, 0.2), _line(-0.75, 1.45, 0.75, 1.45, 0.2), _line(-0.3, 1.9, 0.3, 1.9, 0.2)]
    return SymbolDef(symbol_id="ground_flag", kind="ground_flag", graphics=g,
                     pins=[_pin("1", 0, 0, "up", 0)], body=[-1.2, 0, 1.2, 2], description="Ground reference")


_FACTORIES: Dict[str, Callable[[], SymbolDef]] = {
    "resistor": _resistor, "photoresistor": _photoresistor, "thermistor": _thermistor,
    "potentiometer": _potentiometer, "capacitor": _capacitor, "capacitor_polarized": _capacitor_polarized,
    "inductor": _inductor, "diode": _diode, "zener": _zener, "schottky": _schottky, "led": _led,
    "npn": _npn, "pnp": _pnp, "nmos": lambda: _mos("nmos", False), "pmos": lambda: _mos("pmos", True),
    "opamp": _opamp,
    "gate_and": lambda: _gate("gate_and", "and", False), "gate_nand": lambda: _gate("gate_nand", "and", True),
    "gate_or": lambda: _gate("gate_or", "or", False), "gate_nor": lambda: _gate("gate_nor", "or", True),
    "gate_xor": lambda: _gate("gate_xor", "xor", False), "gate_xnor": lambda: _gate("gate_xnor", "xor", True),
    "gate_not": lambda: _gate("gate_not", "buf", True, 1), "gate_buf": lambda: _gate("gate_buf", "buf", False, 1),
    "dff": _dff, "switch_push": _switch_push, "switch_push_4pin": _switch_push_4pin, "switch_spst": _switch_spst,
    "battery": _battery, "dc_source": _dc_source, "motor": _motor, "buzzer": _buzzer, "regulator": _regulator,
    "jumper": _jumper, "logic_in": _logic_in, "logic_out": _logic_out, "power_flag": _power_flag, "ground_flag": _ground_flag,
}

_CACHE: Dict[str, SymbolDef] = {}


def fixed_symbol_names() -> list[str]:
    return sorted(_FACTORIES)


def get_fixed_symbol(name: str) -> Optional[SymbolDef]:
    if name not in _FACTORIES:
        return None
    if name not in _CACHE:
        _CACHE[name] = _FACTORIES[name]()
    return _CACHE[name].model_copy(deep=True)


# ── generated IC box ───────────────────────────────────────────────────────

CHAR_W = 0.55   # approximate glyph width (gu) at text size 0.85


def build_box_symbol(symbol_id: str, sides: Dict[str, List[tuple[str, str, Optional[str]]]], title: str = "",
                     hidden_count: int = 0) -> SymbolDef:
    """Build a rectangular IC symbol with the part name printed inside the box.

    ``sides`` maps 'left'/'right'/'top'/'bottom' to ordered lists of (pin_name, label, number).
    Pins are spaced 2 gu apart and every tip lands on an integer grid point.
    """
    left, right = sides.get("left", []), sides.get("right", [])
    top, bottom = sides.get("top", []), sides.get("bottom", [])
    max_l = max((len(p[1]) for p in left), default=0)
    max_r = max((len(p[1]) for p in right), default=0)
    width = max(6, math.ceil(CHAR_W * (max_l + max_r) + 2.5), 2 * max(len(top), len(bottom)) + 2,
                math.ceil(0.6 * len(title) + 2) if title else 0)
    width += width % 2
    hw = width // 2

    # Vertical layout, top to bottom (y0 = 0 here, shifted to centre afterwards).
    cursor = 0.0
    top_label_y = cursor + 1.1 if top else None
    if top:
        cursor += 1.6
    title_y = cursor + 1.25 if title else None
    if title:
        cursor += 1.7
    rows = max(len(left), len(right))
    row0 = math.ceil(cursor + 1.0)
    cursor = row0 + 2 * max(rows - 1, 0) + (1.0 if rows else 0.0)
    note_y = cursor + 0.8 if hidden_count else None
    if hidden_count:
        cursor += 1.3
    bottom_label_y = cursor + 0.8 if bottom else None
    if bottom:
        cursor += 1.2
    height = max(4, math.ceil(cursor))
    shift = -(height // 2)            # integer shift keeps pins on the grid
    y0, y1 = shift, shift + height

    pins: list[SymbolPin] = []
    graphics: list[P] = [_rect(-hw, y0, hw, y1)]

    def spread(n: int) -> list[int]:
        return [-(n - 1) + 2 * i for i in range(n)]

    for i, (name, label, num) in enumerate(left):
        y = shift + row0 + 2 * i
        pins.append(_pin(name, -hw - 2, y, "left", 2, num))
        graphics.append(_text(-hw + 0.4, y + 0.3, label, 0.85, "start"))
    for i, (name, label, num) in enumerate(right):
        y = shift + row0 + 2 * i
        pins.append(_pin(name, hw + 2, y, "right", 2, num))
        graphics.append(_text(hw - 0.4, y + 0.3, label, 0.85, "end"))
    for (name, label, num), x in zip(top, spread(len(top))):
        pins.append(_pin(name, x, y0 - 2, "up", 2, num))
        graphics.append(_text(x, shift + top_label_y, label, 0.75))
    for (name, label, num), x in zip(bottom, spread(len(bottom))):
        pins.append(_pin(name, x, y1 + 2, "down", 2, num))
        graphics.append(_text(x, shift + bottom_label_y, label, 0.75))
    if title:
        graphics.append(P(kind="text", x=0, y=shift + title_y, text=title, size=0.95, anchor="middle"))
        graphics.append(_line(-hw + 0.3, shift + title_y + 0.45, hw - 0.3, shift + title_y + 0.45, 0.06))
    if hidden_count:
        graphics.append(_text(0, shift + note_y, f"+{hidden_count} unused pins", 0.65))
    return SymbolDef(symbol_id=symbol_id, graphics=graphics, pins=pins, body=[-hw, y0, hw, y1],
                     description=title or "IC")


# ── component type → symbol resolution ─────────────────────────────────────

REF_PREFIX_BY_SYMBOL = {
    "resistor": "R", "photoresistor": "R", "thermistor": "TH", "potentiometer": "RV", "capacitor": "C",
    "capacitor_polarized": "C", "inductor": "L", "diode": "D", "zener": "D", "schottky": "D", "led": "D",
    "npn": "Q", "pnp": "Q", "nmos": "Q", "pmos": "Q", "opamp": "U", "dff": "U", "switch_push": "SW",
    "switch_push_4pin": "SW", "switch_spst": "SW", "battery": "BT", "dc_source": "V", "motor": "M",
    "buzzer": "BZ", "regulator": "U", "jumper": "JP", "logic_in": "IN", "logic_out": "OUT", "power_flag": "#PWR", "ground_flag": "#GND",
}


def symbol_name_for(ctype: Optional[ComponentType]) -> str:
    """Symbol library name for a component type ('ic_box' when no fixed symbol applies)."""
    if ctype is None:
        return "ic_box"
    if ctype.symbol and ctype.symbol.name in _FACTORIES:
        return ctype.symbol.name
    if ctype.symbol_name and ctype.symbol_name in _FACTORIES:
        return ctype.symbol_name
    return "ic_box"


def pin_mapping(ctype: ComponentType, symbol: SymbolDef) -> Dict[str, str]:
    """engineering pin_id -> symbol pin name for a fixed symbol.

    Explicit ``symbol.pin_map`` entries win; otherwise identical names are matched. Raises
    ValueError when the mapping is not a bijection between engineering and symbol pins,
    so that a bad registry entry fails loudly instead of drawing a wrong symbol.
    """
    explicit = ctype.symbol.pin_map if ctype.symbol else {}
    sym_names = {p.name for p in symbol.pins}
    mapping: Dict[str, str] = {}
    for pin in ctype.pins:
        target = explicit.get(pin.pin_id, pin.pin_id)
        if target not in sym_names:
            raise ValueError(f"{ctype.component_type_id}: pin {pin.pin_id} has no symbol pin '{target}' in {symbol.symbol_id}")
        mapping[pin.pin_id] = target
    if len(set(mapping.values())) != len(mapping):
        raise ValueError(f"{ctype.component_type_id}: two engineering pins map to one symbol pin in {symbol.symbol_id}")
    unused = sym_names - set(mapping.values())
    optional = {"V+", "V-"}  # op-amp symbol supply pins may be absent for ideal parts
    if unused - optional:
        raise ValueError(f"{ctype.component_type_id}: symbol pins {sorted(unused)} of {symbol.symbol_id} are unmapped")
    return mapping


def ref_prefix(ctype: Optional[ComponentType], symbol_name: str) -> str:
    if ctype and ctype.symbol and ctype.symbol.ref_prefix:
        return ctype.symbol.ref_prefix
    if symbol_name in REF_PREFIX_BY_SYMBOL:
        return REF_PREFIX_BY_SYMBOL[symbol_name]
    if ctype is not None:
        from core.enums import ComponentCategory as C
        return {C.CONNECTOR: "J", C.MICROCONTROLLER: "U", C.SENSOR: "U", C.DISPLAY: "DS", C.SWITCH: "SW",
                C.ACTUATOR: "M"}.get(ctype.category, "U")
    return "U"


def default_box_side(direction: PinDirection) -> str:
    return {PinDirection.POWER: "top", PinDirection.GROUND: "bottom", PinDirection.INPUT: "left",
            PinDirection.OUTPUT: "right"}.get(direction, "right")


def all_library_symbols(extra: Iterable[SymbolDef] = ()) -> Dict[str, SymbolDef]:
    out = {name: get_fixed_symbol(name) for name in fixed_symbol_names()}
    for s in extra:
        out[s.symbol_id] = s
    return out
