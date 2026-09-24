"""Standalone SVG rendering of a SchematicProject (export / documentation / visual checks).

The browser studio renders the same Schematic IR with the same conventions; this module
exists so schematics can be exported and inspected without a browser.
"""
from __future__ import annotations

from html import escape
from typing import List, Optional

from .geometry import VEC, transform_orientation, transform_point
from .models import SchematicProject, SymbolPrimitive

SCALE = 10  # px per grid unit

COL = {
    "bg": "#fbfaf6", "grid": "#e9e6dc", "body": "#fff8e1", "stroke": "#8c2f1b", "pin": "#8c2f1b",
    "wire": "#16794a", "junction": "#16794a", "ref": "#274b8a", "value": "#4a4a4a", "power": "#b3261e",
    "ground": "#3d3d3d", "label": "#6b3fa0", "title": "#222",
}


def _f(v: float) -> str:
    return f"{v * SCALE:.2f}".rstrip("0").rstrip(".")


def _text_anchor(anchor: str, rotation: int, mirror: bool) -> str:
    vx, vy = transform_point(1, 0, 0, 0, rotation, mirror)
    if abs(vy) > 0.5:
        return "middle"
    if vx < 0:
        return {"start": "end", "end": "start"}.get(anchor, anchor)
    return anchor


def _prim(p: SymbolPrimitive, color: str) -> str:
    fill = {"none": "none", "outline": color, "body": COL["body"]}[p.fill]
    sw = f'stroke="{color}" stroke-width="{_f(p.width)}" fill="{fill}" stroke-linejoin="round" stroke-linecap="round"'
    if p.kind == "line":
        (x1, y1), (x2, y2) = p.points
        return f'<line x1="{_f(x1)}" y1="{_f(y1)}" x2="{_f(x2)}" y2="{_f(y2)}" {sw}/>'
    if p.kind in ("polyline", "polygon"):
        pts = " ".join(f"{_f(x)},{_f(y)}" for x, y in p.points)
        return f'<{p.kind} points="{pts}" {sw}/>'
    if p.kind == "rect":
        return f'<rect x="{_f(p.x)}" y="{_f(p.y)}" width="{_f(p.w)}" height="{_f(p.h)}" {sw}/>'
    if p.kind == "circle":
        return f'<circle cx="{_f(p.x)}" cy="{_f(p.y)}" r="{_f(p.r)}" {sw}/>'
    if p.kind == "path":
        # Scale path data by wrapping in a scaled group.
        return f'<path transform="scale({SCALE})" d="{p.d}" stroke="{color}" stroke-width="{p.width}" fill="{fill}" stroke-linejoin="round"/>'
    return ""


def _text(x: float, y: float, s: str, size: float, anchor: str, color: str, weight: str = "normal") -> str:
    return (f'<text x="{_f(x)}" y="{_f(y)}" font-size="{_f(size)}" text-anchor="{anchor}" fill="{color}" '
            f'font-family="Inter, Segoe UI, Arial, sans-serif" font-weight="{weight}">{escape(s)}</text>')


def render_svg(s: SchematicProject, show_grid: bool = True, highlight: Optional[set] = None) -> str:
    x0, y0, x1, y1 = s.bounds
    w, h = (x1 - x0), (y1 - y0)
    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_f(x0)} {_f(y0)} {_f(w)} {_f(h)}" '
        f'width="{int(w * SCALE)}" height="{int(h * SCALE)}">',
        f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(w)}" height="{_f(h)}" fill="{COL["bg"]}"/>',
    ]
    if show_grid:
        out.append(f'<defs><pattern id="g" width="{SCALE * 2}" height="{SCALE * 2}" patternUnits="userSpaceOnUse">'
                   f'<circle cx="0" cy="0" r="0.9" fill="{COL["grid"]}"/></pattern></defs>'
                   f'<rect x="{_f(x0)}" y="{_f(y0)}" width="{_f(w)}" height="{_f(h)}" fill="url(#g)"/>')

    # wires
    for wire in s.wires:
        out.append(f'<line x1="{_f(wire.x1)}" y1="{_f(wire.y1)}" x2="{_f(wire.x2)}" y2="{_f(wire.y2)}" '
                   f'stroke="{COL["wire"]}" stroke-width="{_f(0.18)}" stroke-linecap="round"/>')
    for j in s.junctions:
        out.append(f'<circle cx="{_f(j.x)}" cy="{_f(j.y)}" r="{_f(0.38)}" fill="{COL["junction"]}"/>')

    # components
    for c in s.components:
        sym = s.symbols[c.symbol_id]
        sx = -1 if c.mirror else 1
        g = [f'<g transform="translate({_f(c.x)} {_f(c.y)}) rotate({c.rotation}) scale({sx} 1)">']
        texts = []
        for prim in sym.graphics:
            if prim.kind == "text":
                tx, ty = transform_point(prim.x, prim.y, c.x, c.y, c.rotation, c.mirror)
                texts.append(_text(tx, ty, prim.text, prim.size, _text_anchor(prim.anchor, c.rotation, c.mirror), COL["stroke"]))
            else:
                g.append(_prim(prim, COL["stroke"]))
        g.append("</g>")
        out += g
        for p in c.pins:
            if p.hidden:
                continue
            sp = next((q for q in sym.pins if q.name == p.symbol_pin), None)
            vx, vy = VEC[p.orientation]
            L = sp.length if sp else 2
            if L > 0:
                out.append(f'<line x1="{_f(p.x)}" y1="{_f(p.y)}" x2="{_f(p.x - vx * L)}" y2="{_f(p.y - vy * L)}" '
                           f'stroke="{COL["pin"]}" stroke-width="{_f(0.15)}"/>')
        out += texts
        if c.ref_label:
            t = c.ref_label
            out.append(_text(t.x, t.y, t.text, t.size, t.anchor, COL["ref"], "600"))
        if c.value_label:
            t = c.value_label
            color = COL["power"] if c.port_text and sym.kind == "power_flag" else COL["value"]
            out.append(_text(t.x, t.y, t.text, t.size, t.anchor, color))

    # power ports
    for p in s.power_ports:
        vx, vy = VEC[p.direction]
        ux, uy = abs(vy), abs(vx)
        color = COL["power"] if p.kind == "power" else COL["ground"]
        ax, ay = p.x + vx * 1.0, p.y + vy * 1.0
        out.append(f'<line x1="{_f(p.x)}" y1="{_f(p.y)}" x2="{_f(ax)}" y2="{_f(ay)}" stroke="{color}" stroke-width="{_f(0.15)}"/>')
        if p.kind == "power":
            out.append(f'<line x1="{_f(ax - ux)}" y1="{_f(ay - uy)}" x2="{_f(ax + ux)}" y2="{_f(ay + uy)}" stroke="{color}" stroke-width="{_f(0.22)}"/>')
            tx, ty = p.x + vx * 2.9, p.y + vy * 2.9
        else:
            for k, half in ((0.0, 1.2), (0.45, 0.75), (0.9, 0.3)):
                bx, by = ax + vx * k, ay + vy * k
                out.append(f'<line x1="{_f(bx - ux * half)}" y1="{_f(by - uy * half)}" x2="{_f(bx + ux * half)}" '
                           f'y2="{_f(by + uy * half)}" stroke="{color}" stroke-width="{_f(0.2)}"/>')
            tx, ty = p.x + vx * 3.2, p.y + vy * 3.2
        if p.kind == "power" or p.text != "GND":
            anchor = "middle" if vx == 0 else ("start" if vx > 0 else "end")
            out.append(_text(tx, ty + (0.35 if vy >= 0 else 0) + (0.4 if vx else 0), p.text, 0.95, anchor, color, "600"))

    # net labels
    for l in s.net_labels:
        vx, vy = VEC[l.direction]
        length = 0.62 * max(len(l.text), 1) + 1.2
        if vx:
            xa, xb = l.x, l.x + vx * length
            pts = [(xa, l.y), (xa + vx * 0.6, l.y - 0.6), (xb, l.y - 0.6), (xb, l.y + 0.6), (xa + vx * 0.6, l.y + 0.6)]
            out.append('<polygon points="' + " ".join(f"{_f(x)},{_f(y)}" for x, y in pts) +
                       f'" fill="#f4eefb" stroke="{COL["label"]}" stroke-width="{_f(0.1)}"/>')
            out.append(_text((xa + xb) / 2 + vx * 0.3, l.y + 0.35, l.text, 0.9, "middle", COL["label"]))
        else:
            ya, yb = l.y, l.y + vy * 1.2
            out.append(f'<line x1="{_f(l.x)}" y1="{_f(ya)}" x2="{_f(l.x)}" y2="{_f(yb)}" stroke="{COL["label"]}" stroke-width="{_f(0.12)}"/>')
            out.append(_text(l.x, yb + (0.9 if vy > 0 else -0.3), l.text, 0.9, "middle", COL["label"]))

    for a in s.text_annotations:
        out.append(_text(a.x, a.y, a.text, a.size, a.anchor, COL["title"], "700"))
    out.append("</svg>")
    return "\n".join(out)
