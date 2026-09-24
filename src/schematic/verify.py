"""Schematic verification ("schematic LVS").

``extract_connectivity`` rebuilds connectivity from the *drawing alone* — wire geometry,
pin tip positions, port and label texts — exactly as a person reading the sheet would:

  * wire segments connect where an endpoint of one lies on another (T or end-to-end);
  * wires that merely cross do **not** connect;
  * a pin connects to any wire passing through / ending at its tip;
  * power/ground ports and supply flags with the same text are one net;
  * net labels with the same text are one net.

``verify_schematic`` compares the extracted connectivity with the engineering nets and also
checks drawing hygiene (overlapping symbols, wires through bodies, dangling references).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from core.models import EngineeringDesignProject
from .geometry import bbox_intersects, point_on_segment, transform_bbox
from .models import SchematicProject

Point = Tuple[int, int]


class _DSU:
    def __init__(self):
        self.parent: Dict[object, object] = {}

    def find(self, a):
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb, key=str)] = min(ra, rb, key=str)


def extract_connectivity(schematic: SchematicProject) -> List[Set[str]]:
    """Groups of pin refs ("instance.pin") that the drawing shows as connected (groups of >= 1)."""
    dsu = _DSU()
    pin_tips: Dict[str, Point] = {}
    for comp in schematic.components:
        for p in comp.pins:
            if not p.hidden:
                ref = f"{comp.instance_id}.{p.pin_id}"
                pin_tips[ref] = (p.x, p.y)
                dsu.find(("pin", ref))

    # Every "terminal point" a wire could attach to.
    terminal_points: Set[Point] = set(pin_tips.values())
    for w in schematic.wires:
        terminal_points.add((w.x1, w.y1))
        terminal_points.add((w.x2, w.y2))
    for p in schematic.power_ports:
        terminal_points.add((p.x, p.y))
    for l in schematic.net_labels:
        terminal_points.add((l.x, l.y))

    for w in schematic.wires:
        a, b = (w.x1, w.y1), (w.x2, w.y2)
        for tp in terminal_points:
            if point_on_segment(tp, a, b):
                dsu.union(("pt", tp), ("wire", w.wire_id))
    for ref, tip in pin_tips.items():
        dsu.union(("pin", ref), ("pt", tip))
    for p in schematic.power_ports:
        dsu.union(("pt", (p.x, p.y)), ("port", p.text))
    for comp in schematic.components:
        if comp.port_text:
            for p in comp.pins:
                dsu.union(("pin", f"{comp.instance_id}.{p.pin_id}"), ("port", comp.port_text))
    for l in schematic.net_labels:
        dsu.union(("pt", (l.x, l.y)), ("label", l.text))

    groups: Dict[object, Set[str]] = {}
    for ref in pin_tips:
        groups.setdefault(dsu.find(("pin", ref)), set()).add(ref)
    return sorted(groups.values(), key=lambda g: sorted(g))


@dataclass
class VerificationReport:
    ok: bool = True
    opens: List[str] = field(default_factory=list)       # engineering connections missing from drawing
    shorts: List[str] = field(default_factory=list)      # drawing connects different nets / stray pins
    hygiene: List[str] = field(default_factory=list)     # overlaps, wires through bodies, bad references

    def as_dict(self) -> dict:
        return {"ok": self.ok, "opens": self.opens, "shorts": self.shorts, "hygiene": self.hygiene}


def verify_schematic(schematic: SchematicProject, design: EngineeringDesignProject) -> VerificationReport:
    rep = VerificationReport()
    groups = extract_connectivity(schematic)
    group_of: Dict[str, int] = {}
    for i, g in enumerate(groups):
        for ref in g:
            group_of[ref] = i
    drawn = set(group_of)

    net_of: Dict[str, str] = {}
    for net in design.nets:
        refs = [pr.ref for pr in net.connections if pr.ref in drawn]
        for r in refs:
            net_of[r] = net.net_id
        if len({group_of[r] for r in refs}) > 1:
            rep.opens.append(f"net {net.net_id}: pins split across {len({group_of[r] for r in refs})} drawn groups")
    for g in groups:
        nets = {net_of.get(r) for r in g}
        if len(g) > 1 and (len(nets) > 1 or None in nets):
            rep.shorts.append(f"drawing connects {sorted(g)} spanning nets {sorted(str(n) for n in nets)}")

    # Traceability: every drawn object must point at a real engineering object.
    inst_ids = {c.instance_id for c in design.components}
    net_ids = {n.net_id for n in design.nets}
    for c in schematic.components:
        if c.instance_id not in inst_ids:
            rep.hygiene.append(f"component {c.instance_id} has no engineering instance")
        if c.symbol_id not in schematic.symbols:
            rep.hygiene.append(f"component {c.instance_id} references missing symbol {c.symbol_id}")
    for item in [*schematic.wires, *schematic.junctions, *schematic.power_ports, *schematic.net_labels]:
        if item.net_id not in net_ids:
            rep.hygiene.append(f"{type(item).__name__} references unknown net {item.net_id}")

    # Geometry hygiene: symbol bodies must not overlap, wires must not cross bodies.
    bodies = []
    for c in schematic.components:
        sym = schematic.symbols.get(c.symbol_id)
        if sym is None:
            continue
        bodies.append((c.instance_id, transform_bbox(tuple(sym.body), c.x, c.y, c.rotation, c.mirror)))
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            if bbox_intersects(bodies[i][1], bodies[j][1]):
                rep.hygiene.append(f"symbols {bodies[i][0]} and {bodies[j][0]} overlap")
    for w in schematic.wires:
        pts = [(x, y) for x in range(min(w.x1, w.x2), max(w.x1, w.x2) + 1)
               for y in range(min(w.y1, w.y2), max(w.y1, w.y2) + 1)]
        for iid, b in bodies:
            if any(b[0] < x < b[2] and b[1] < y < b[3] for x, y in pts):
                rep.hygiene.append(f"wire {w.wire_id} passes through {iid}")
    rep.ok = not (rep.opens or rep.shorts or rep.hygiene)
    return rep


def count_crossings(schematic: SchematicProject) -> int:
    """Perpendicular crossings between wires of different nets (no shared endpoint)."""
    n = 0
    ws = schematic.wires
    for i in range(len(ws)):
        a = ws[i]
        for j in range(i + 1, len(ws)):
            b = ws[j]
            if a.net_id == b.net_id:
                continue
            ah, bh = a.y1 == a.y2, b.y1 == b.y2
            if ah == bh:
                continue
            h, v = (a, b) if ah else (b, a)
            if min(h.x1, h.x2) < v.x1 < max(h.x1, h.x2) and min(v.y1, v.y2) < h.y1 < max(v.y1, v.y2):
                n += 1
    return n
