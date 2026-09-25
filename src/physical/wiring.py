"""Physical wiring: flying leads and jumper wires that complete each engineering net.

After placement, a net is already partly connected by the board itself (pins that share a strip or
a rail). What remains:

1. **Leads** - off-board items with flying leads (batteries, supplies, motors) push their lead end
   into a hole of the net's rail if it has one, else a strip already carrying the net, else a fresh
   strip reserved for the net.
2. **Jumpers** - the net's distinct nodes (strips, rails, off-board header pins) are joined by a
   minimum spanning tree (Prim, deterministic tie-breaks); each tree edge becomes one jumper wire
   between the nearest pair of free holes / terminals. A jumper between two rails of the same net is
   a rail bridge.

Wire paths are plan-view L routes lifted above the board, raised over any part body they cross.
Colours follow common practice: black ground, red supply, then a fixed palette per net.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .breadboard import Breadboard
from .models import PhysicalWire, WireEnd
from .placement import BoardState, Rect

GROUND_COLOR = "#212121"
SUPPLY_COLORS = ["#d32f2f", "#ef6c00", "#c2185b"]
SIGNAL_COLORS = ["#fbc02d", "#388e3c", "#1e88e5", "#8e24aa", "#00acc1", "#eeeeee", "#6d4c41", "#546e7a"]


@dataclass
class Terminal3D:
    pin_ref: str                      # "instance.pin"
    net: Optional[str]
    style: str                        # lead | header | screw | pad
    pos: Tuple[float, float, float]
    color: Optional[str] = None


@dataclass
class BodyBox:
    instance_id: str
    rect: Rect
    top: float


def net_colors(net_info: Dict[str, object], supply_order: Sequence[str]) -> Dict[str, str]:
    colors: Dict[str, str] = {}
    signals = sorted(n for n, i in net_info.items() if getattr(i, "net_class", "signal") == "signal")
    for k, n in enumerate(signals):
        colors[n] = SIGNAL_COLORS[k % len(SIGNAL_COLORS)]
    for n, i in net_info.items():
        cls = getattr(i, "net_class", "signal")
        if cls == "ground":
            colors[n] = GROUND_COLOR
        elif cls == "power":
            k = list(supply_order).index(n) if n in supply_order else len(supply_order)
            colors[n] = SUPPLY_COLORS[min(k, len(SUPPLY_COLORS) - 1)]
    return colors


def _dist(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seg_hits(rect: Rect, p: Tuple[float, float], q: Tuple[float, float]) -> bool:
    """Axis-aligned segment p-q intersects rect (shrunk slightly)."""
    x0, y0, x1, y1 = rect[0] + 0.2, rect[1] + 0.2, rect[2] - 0.2, rect[3] - 0.2
    if abs(p[0] - q[0]) < 1e-9:
        x = p[0]
        lo, hi = sorted((p[1], q[1]))
        return x0 < x < x1 and lo < y1 and hi > y0
    y = p[1]
    lo, hi = sorted((p[0], q[0]))
    return y0 < y < y1 and lo < x1 and hi > x0


class Wirer:
    def __init__(self, state: BoardState, bodies: List[BodyBox], colors: Dict[str, str], board_height: float):
        self.st = state
        self.bb: Breadboard = state.bb
        self.bodies = bodies
        self.colors = colors
        self.board_h = board_height
        self.wires: List[PhysicalWire] = []
        self._k = 0

    # ── helpers ─────────────────────────────────────────────────────────
    def _hole_pos(self, hid: str) -> Tuple[float, float, float]:
        h = self.bb.holes[hid]
        return (h.x, h.y, 0.0)

    def _free(self, node: str) -> List[str]:
        return self.st.free_holes(node)

    def _new_id(self) -> str:
        self._k += 1
        return f"w{self._k}"

    def _occupy(self, hid: str, who: str) -> None:
        self.st.occupied[hid] = who

    def _route(self, a: Tuple[float, float, float], b: Tuple[float, float, float], lane: int,
               a_is_hole: bool, b_is_hole: bool) -> List[List[float]]:
        """L-shaped plan route lifted above the board and over any body it crosses."""
        pa, pb = (a[0], a[1]), (b[0], b[1])
        options = [[pa, (pb[0], pa[1]), pb], [pa, (pa[0], pb[1]), pb]]

        def cost(pts):
            hits = [bx for bx in self.bodies for s in range(len(pts) - 1) if _seg_hits(bx.rect, pts[s], pts[s + 1])]
            return (len(hits), max((bx.top for bx in hits), default=0.0))

        pts = min(options, key=lambda o: (cost(o), o[1]))
        n_hits, top = cost(pts)
        h = max(2.0 + 0.5 * (lane % 4), top + 1.5 if n_hits else 0.0)
        path: List[List[float]] = [[a[0], a[1], a[2]]]
        if a_is_hole or a[2] < h:
            path.append([a[0], a[1], max(h, a[2])])
        for x, y in pts[1:-1]:
            if (abs(x - pa[0]) > 1e-6 or abs(y - pa[1]) > 1e-6) and (abs(x - pb[0]) > 1e-6 or abs(y - pb[1]) > 1e-6):
                path.append([x, y, h])
        if b_is_hole or b[2] < h:
            path.append([b[0], b[1], max(h, b[2])])
        path.append([b[0], b[1], b[2]])
        out: List[List[float]] = []
        for p in path:
            q = [round(v, 3) for v in p]
            if not out or out[-1] != q:
                out.append(q)
        return out

    @staticmethod
    def _length(path: List[List[float]]) -> float:
        return round(sum(math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)), 2)

    def _add(self, net: str, kind: str, a: WireEnd, b: WireEnd, color: Optional[str], purpose: str) -> PhysicalWire:
        wid = self._new_id()
        path = self._route(tuple(a.position), tuple(b.position), len(self.wires),
                           a.kind == "hole", b.kind == "hole")
        w = PhysicalWire(wire_id=wid, net_id=net, kind=kind, a=a, b=b, path=path,
                         color=color or self.colors.get(net, SIGNAL_COLORS[0]), length_mm=self._length(path),
                         purpose=purpose)
        for end, tag in ((a, "a"), (b, "b")):
            if end.kind == "hole" and end.hole:
                self._occupy(end.hole, f"wire:{wid}.{tag}")
        self.wires.append(w)
        return w

    def _best_hole(self, node: str, near: Tuple[float, float, float]) -> Optional[str]:
        free = self._free(node)
        if not free:
            return None
        return min(free, key=lambda h: (round(_dist(self._hole_pos(h), near), 6), h))

    def _fresh_strip(self, net: str, near: Tuple[float, float, float]) -> Optional[str]:
        cands = []
        for node, holes in self.bb.node_holes.items():
            if node.startswith("rail:") or node in self.st.node_net:
                continue
            free = [h for h in holes if h not in self.st.occupied and h not in self.st.covered]
            if len(free) < 2:
                continue
            d = min(_dist(self._hole_pos(h), near) for h in free)
            cands.append((round(d, 6), node))
        if not cands:
            return None
        node = min(cands)[1]
        self.st.assign(node, net)
        return node

    # ── leads ───────────────────────────────────────────────────────────
    def plug_leads(self, terminals: List[Terminal3D], rail_nets: Dict[str, Optional[str]]) -> Dict[str, str]:
        """Insert flying leads into the board. Returns pin_ref -> hole."""
        done: Dict[str, str] = {}
        for t in sorted(terminals, key=lambda t: t.pin_ref):
            if t.style != "lead" or not t.net:
                continue
            nodes = [f"rail:{r}" for r, n in sorted(rail_nets.items()) if n == t.net]
            nodes += [n for n in self.st.net_nodes.get(t.net, []) if not n.startswith("rail:") and n not in nodes]
            hole = None
            for node in sorted(nodes, key=lambda n: (min((_dist(self._hole_pos(h), t.pos) for h in self._free(n)), default=1e9), n)):
                hole = self._best_hole(node, t.pos)
                if hole:
                    self.st.assign(node, t.net)
                    break
            if hole is None:
                node = self._fresh_strip(t.net, t.pos)
                hole = self._best_hole(node, t.pos) if node else None
            if hole is None:
                continue
            a = WireEnd(kind="pin", pin_ref=t.pin_ref, position=list(t.pos))
            b = WireEnd(kind="hole", hole=hole, position=list(self._hole_pos(hole)))
            self._add(t.net, "lead", a, b, t.color, f"{t.pin_ref} lead into {hole}")
            done[t.pin_ref] = hole
        return done

    # ── jumpers ─────────────────────────────────────────────────────────
    def connect_nets(self, nets: Sequence[str], terminals: List[Terminal3D],
                     rail_nets: Optional[Dict[str, Optional[str]]] = None) -> List[str]:
        """Join the nodes of each net with a spanning tree of jumpers. Returns nets left open.

        The tree is planned as a dry run that respects hole capacity (a strip has five holes); if
        it cannot be completed, it is planned again with the net's rails added as hubs."""
        open_nets = []
        header_terms: Dict[str, List[Terminal3D]] = {}
        for t in terminals:
            if t.style != "lead" and t.net:
                header_terms.setdefault(t.net, []).append(t)
        for net in nets:
            nodes: List[Tuple[str, object]] = []
            for node in sorted(self.st.net_nodes.get(net, [])):
                if any(h in self.st.occupied for h in self.bb.node_holes.get(node, [])):
                    nodes.append(("node", node))
            for t in sorted(header_terms.get(net, []), key=lambda t: t.pin_ref):
                nodes.append(("term", t))
            if len(nodes) < 2:
                continue
            plan = self._plan(nodes)
            if plan is None and rail_nets:
                hubs = [("node", f"rail:{r}") for r, n in sorted(rail_nets.items())
                        if n == net and ("node", f"rail:{r}") not in nodes]
                if hubs:
                    plan = self._plan(hubs + nodes)
            if plan is None:
                open_nets.append(net)
                continue
            for u, v, ea, eb in plan:
                kind = "rail_bridge" if (u[0] == "node" and v[0] == "node" and str(u[1]).startswith("rail:")
                                         and str(v[1]).startswith("rail:")) else "jumper"
                self._add(net, kind, ea, eb, None, self._purpose(net, u, v))
        return open_nets

    def _plan(self, nodes) -> Optional[List[tuple]]:
        """Prim's tree over the nodes with hole reservations; None if it cannot be completed."""
        reserved: set = set()
        in_tree = [nodes[0]]
        rest = list(nodes[1:])
        edges = []
        while rest:
            best = None
            for u in in_tree:
                for v in rest:
                    link = self._link(u, v, reserved)
                    if link is None:
                        continue
                    key = (round(link[0], 6), self._key(u), self._key(v))
                    if best is None or key < best[0]:
                        best = (key, u, v, link)
            if best is None:
                return None
            _, u, v, (_, ea, eb) = best
            for end in (ea, eb):
                if end.kind == "hole":
                    reserved.add(end.hole)
            edges.append((u, v, ea, eb))
            in_tree.append(v)
            rest.remove(v)
        return edges

    @staticmethod
    def _key(n) -> str:
        return n[1] if n[0] == "node" else f"term:{n[1].pin_ref}"

    @staticmethod
    def _purpose(net: str, u, v) -> str:
        def name(n):
            return n[1] if n[0] == "node" else n[1].pin_ref
        return f"{net}: {name(u)} to {name(v)}"

    def _link(self, u, v, reserved: Optional[set] = None) -> Optional[Tuple[float, WireEnd, WireEnd]]:
        reserved = reserved or set()

        def ends(n) -> List[Tuple[Tuple[float, float, float], WireEnd]]:
            if n[0] == "term":
                t: Terminal3D = n[1]
                return [(t.pos, WireEnd(kind="pin", pin_ref=t.pin_ref, position=list(t.pos)))]
            out = []
            for h in self._free(n[1]):
                if h in reserved:
                    continue
                p = self._hole_pos(h)
                out.append((p, WireEnd(kind="hole", hole=h, position=list(p))))
            return out
        best = None
        for pa, ea in ends(u):
            for pb, eb in ends(v):
                if ea.kind == "hole" and eb.kind == "hole" and ea.hole == eb.hole:
                    continue
                d = _dist(pa, pb)
                key = (round(d, 6), ea.hole or ea.pin_ref or "", eb.hole or eb.pin_ref or "")
                if best is None or key < best[0]:
                    best = (key, d, ea, eb)
        if best is None:
            return None
        return best[1], best[2], best[3]
