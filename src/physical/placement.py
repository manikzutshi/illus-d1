"""Deterministic breadboard placement.

The AI never chooses coordinates. Given the engineering design, the part footprints and the
user's locked placements, this engine decides where every part goes:

* Every breadboard *node* (a 5-hole terminal strip or a power rail) carries at most one engineering
  net. A candidate placement is legal only if each pin lands in a free, uncovered hole whose node is
  unassigned or already carries that pin's net, and unconnected pins get a node of their own. So a
  placement can never create a short, and pins that share a node are connected without a wire.
* Power and ground nets are assigned to the rails first (ground on both "-" rails, the main supply
  on "+", a second supply on the other "+" rail).
* Parts are placed big-first (DIPs, dual-row modules, inline parts, then two-lead parts), each at
  the legal candidate with the best score: connections made by shared strips, closeness to the
  part's position in the signal flow (the schematic's left-to-right order), short leads.
* Off-board items (batteries, supplies, boards that do not fit, motors, modules) are arranged
  around the board: supplies left, controller boards below, other modules right.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .breadboard import PITCH_MM, RAIL_YP, ROW_YP, Breadboard, make_breadboard, parse_hole
from .footprints import Footprint

Rect = Tuple[float, float, float, float]         # xmin, ymin, xmax, ymax (mm)

ROW_ORDER = "abcdefghij"
_ALL_YP = sorted(list(ROW_YP.values()) + list(RAIL_YP.values()))


def rotate(dx: float, dy: float, rot: int) -> Tuple[float, float]:
    r = rot % 360
    if r == 0:
        return dx, dy
    if r == 90:
        return -dy, dx
    if r == 180:
        return -dx, -dy
    return dy, -dx


def overlaps(a: Rect, b: Rect, tol: float = 0.05) -> bool:
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


@dataclass
class Placed:
    instance_id: str
    footprint: Footprint
    mount: str                               # breadboard | offboard | unplaced | virtual
    rotation: int = 0
    orientation: str = ""
    span: Optional[int] = None
    anchor: Optional[str] = None
    pin_holes: Dict[str, str] = field(default_factory=dict)
    body_rect: Optional[Rect] = None
    body_center: Tuple[float, float] = (0.0, 0.0)
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)     # off-board body centre
    locked: bool = False
    reason: str = ""                         # why a locked/preferred placement could not be kept


@dataclass
class BoardState:
    bb: Breadboard
    occupied: Dict[str, str] = field(default_factory=dict)        # hole -> occupant
    covered: Set[str] = field(default_factory=set)
    node_net: Dict[str, str] = field(default_factory=dict)       # node -> net id | "nc:<ref>"
    bodies: List[Tuple[str, Rect]] = field(default_factory=list)
    net_nodes: Dict[str, List[str]] = field(default_factory=dict)

    def assign(self, node: str, net: str) -> None:
        if node not in self.node_net:
            self.node_net[node] = net
            self.net_nodes.setdefault(net, []).append(node)

    def free_holes(self, node: str) -> List[str]:
        return [h for h in self.bb.node_holes.get(node, []) if h not in self.occupied and h not in self.covered]


@dataclass
class Candidate:
    rotation: int
    orientation: str
    span: Optional[int]
    anchor: str
    pin_holes: Dict[str, str]
    body_rect: Rect
    body_center: Tuple[float, float]
    covered: List[str]


class PlacementEngine:
    def __init__(self, board_kind: str, pin_net: Dict[Tuple[str, str], Optional[str]],
                 rail_nets: Dict[str, Optional[str]]):
        self.state = BoardState(make_breadboard(board_kind))
        self.pin_net = pin_net
        self.rail_nets = rail_nets
        for rail, net in rail_nets.items():
            if net:
                self.state.assign(f"rail:{rail}", net)

    # ── geometry ──────────────────────────────────────────────────────────
    def _pin_holes(self, fp: Footprint, col: int, yp: float, rot: int, span: Optional[int]) -> Optional[Dict[str, str]]:
        bb = self.state.bb
        holes: Dict[str, str] = {}
        for pin, dx, dy in fp.sites(span):
            rx, ry = rotate(dx, dy, rot)
            if abs(rx - round(rx)) > 1e-6:
                return None
            hid = bb.by_grid.get((col + int(round(rx)), yp + ry))
            if hid is None:
                return None
            holes[pin] = hid
        return holes

    def _pins_ok(self, iid: str, holes: Dict[str, str]) -> Optional[str]:
        st = self.state
        seen: Dict[str, str] = {}
        for pin, hid in holes.items():
            if hid in st.occupied:
                return f"hole {hid} is already used by {st.occupied[hid]}"
            if hid in st.covered:
                return f"hole {hid} is covered by another part"
            node = st.bb.holes[hid].node
            net = self.pin_net.get((iid, pin)) or f"nc:{iid}.{pin}"
            owner = st.node_net.get(node)
            if owner is not None and owner != net:
                what = "an unconnected pin" if owner.startswith("nc:") else f"net {owner}"
                return f"pin {pin} would land in {node}, which carries {what} (a short)"
            if node in seen and seen[node] != net:
                return f"two pins of {iid} would share {node} (a short)"
            seen[node] = net
        return None

    def _finish(self, fp: Footprint, holes: Dict[str, str], rot: int, span: Optional[int],
                orientation: str) -> Candidate:
        bb = self.state.bb
        sites = fp.sites(span)
        anchor = holes[sites[0][0]]
        a = bb.holes[anchor]
        bcx, bcy = fp.body_center_mm(sites)
        ox, oy = rotate(bcx, bcy, rot)
        L, D = fp.body_mm[0], fp.body_mm[1]
        if rot % 180:
            L, D = D, L
        cx, cy = a.x + ox, a.y + oy
        rect = (cx - L / 2, cy - D / 2, cx + L / 2, cy + D / 2)
        own = set(holes.values())
        cov = []
        half = (bb.columns + 1) / 2.0
        c0 = int((rect[0] / PITCH_MM) + half) - 1
        c1 = int((rect[2] / PITCH_MM) + half) + 1
        for col in range(max(c0, 1), min(c1, bb.columns) + 1):
            for yp in _ALL_YP:
                hid = bb.by_grid.get((col, yp))
                if hid is None or hid in own:
                    continue
                h = bb.holes[hid]
                if rect[0] + 0.3 < h.x < rect[2] - 0.3 and rect[1] + 0.3 < h.y < rect[3] - 0.3:
                    cov.append(hid)
        if orientation == "cross" and any(bb.holes[h].node.startswith("rail:") for h in holes.values()):
            orientation = "rail"
        return Candidate(rot, orientation, span, anchor, dict(holes), rect, (cx, cy), cov)

    def _candidate(self, iid: str, fp: Footprint, col: int, yp: float, rot: int, span: Optional[int],
                   orientation: str) -> Optional[Candidate]:
        holes = self._pin_holes(fp, col, yp, rot, span)
        if holes is None:
            return None
        return self._finish(fp, holes, rot, span, orientation)

    def legal(self, iid: str, fp: Footprint, c: Candidate) -> Optional[str]:
        """None if legal, else the reason (used for user moves)."""
        st = self.state
        why = self._pins_ok(iid, c.pin_holes)
        if why:
            return why
        for hid in c.covered:
            if hid in st.occupied:
                return f"its body would cover {hid}, which is in use"
        for other, rect in st.bodies:
            if overlaps(rect, c.body_rect):
                return f"it would collide with {other}"
        halves = {st.bb.holes[h].node.split(":")[0] for h in c.pin_holes.values()}
        if c.orientation == "dip" and not {"top", "bot"} <= halves:
            return "it must straddle the centre trench"
        if c.orientation == "cross" and not {"top", "bot"} <= halves:
            return "a part standing across rows must bridge the centre trench"
        return None

    def _combos(self, fp: Footprint) -> List[Tuple[float, int, Optional[int], str]]:
        combos: List[Tuple[float, int, Optional[int], str]] = []
        if fp.template == "two_lead":
            for span in fp.spans or [1]:
                combos += [(yp, rot, span, "row") for yp in ROW_YP.values() for rot in (0, 180)]
                combos += [(yp, rot, span, "cross") for yp in _ALL_YP for rot in (90, 270)]
        elif fp.template in ("inline", "smd_adapter"):
            combos = [(yp, rot, None, "row") for yp in ROW_YP.values() for rot in (0, 180)]
        elif fp.template in ("dip", "dual_row"):
            combos = [(yp, rot, None, "dip") for yp in ROW_YP.values() for rot in (0, 180)]
        return combos

    def candidates(self, iid: str, fp: Footprint, columns: Optional[Sequence[int]] = None) -> List[Candidate]:
        """Candidates whose pins are legal (body checks happen in ``legal``)."""
        cols = columns or range(1, self.state.bb.columns + 1)
        out: List[Candidate] = []
        for yp, rot, span, orient in self._combos(fp):
            for col in cols:
                holes = self._pin_holes(fp, col, yp, rot, span)
                if holes is None or self._pins_ok(iid, holes) is not None:
                    continue
                out.append(self._finish(fp, holes, rot, span, orient))
        return out

    # ── scoring ───────────────────────────────────────────────────────────
    def pin_score(self, iid: str, fp: Footprint, holes: Dict[str, str], orientation: str, span: Optional[int],
                  target_col: float) -> float:
        """Score from pin positions only (cheap; lower is better)."""
        st, bb = self.state, self.state.bb
        s = 0.0
        cols = []
        rows = set()
        for pin, hid in holes.items():
            h = bb.holes[hid]
            cols.append(h.column)
            rows.add(h.row)
            net = self.pin_net.get((iid, pin))
            if net is None:
                continue
            if st.node_net.get(h.node) == net:
                s -= 12.0                                    # connected by the board itself
            else:
                others = [n for n in st.net_nodes.get(net, []) if not n.startswith("rail:")]
                if others:
                    s += 0.6 * min(abs(int(n.split(":")[1]) - h.column) for n in others)
                if net in self.rail_nets.values():
                    s += 1.5                                 # a rail net not taken from the rail needs a wire
            if not h.node.startswith("rail:"):
                used = sum(1 for x in bb.node_holes.get(h.node, ()) if x in st.occupied)
                if used >= 3:
                    s += 2.0                                 # keep room in the strip for wires
        s += 0.35 * abs((min(cols) + max(cols)) / 2 - target_col)
        if orientation == "row" and rows & {"e", "f"}:
            s += 0.8                                         # leave the rows next to the trench for DIPs
        if orientation == "row" and rows & {"a", "j"}:
            s += 0.4                                         # and the outer rows for rail jumpers
        if orientation == "cross":
            s += 1.0
        if fp.template == "two_lead" and span is not None and fp.spans:
            s += 0.8 * fp.spans.index(span)
        return s

    def score(self, iid: str, fp: Footprint, c: Candidate, target_col: float) -> float:
        orient = "row" if c.orientation == "row" else ("cross" if c.orientation == "cross" else c.orientation)
        return self.pin_score(iid, fp, c.pin_holes, orient, c.span, target_col) +             0.2 * len(c.covered) / max(len(c.pin_holes), 1)

    # ── commit ────────────────────────────────────────────────────────────
    def commit(self, iid: str, fp: Footprint, c: Candidate, locked: bool) -> Placed:
        st = self.state
        for pin, hid in c.pin_holes.items():
            st.occupied[hid] = f"pin:{iid}.{pin}"
            node = st.bb.holes[hid].node
            st.assign(node, self.pin_net.get((iid, pin)) or f"nc:{iid}.{pin}")
        st.covered.update(c.covered)
        st.bodies.append((iid, c.body_rect))
        return Placed(iid, fp, "breadboard", c.rotation, c.orientation, c.span, c.anchor, dict(c.pin_holes),
                      c.body_rect, c.body_center, locked=locked)

    def place(self, iid: str, fp: Footprint, target_col: float, window: int = 14, evaluate: int = 30) -> Optional[Placed]:
        """Best legal placement. Candidates are ranked by the cheap pin score; only the best few are
        checked for body collisions (a full search over the board is the fallback)."""
        bb = self.state.bb
        near_cols = set()
        for (i, pin), net in self.pin_net.items():
            if i == iid and net:
                for node in self.state.net_nodes.get(net, []):
                    if not node.startswith("rail:"):
                        c = int(node.split(":")[1])
                        near_cols.update(range(c - 4, c + 5))
        for cols in (sorted({c for c in range(int(target_col) - window, int(target_col) + window + 1)} | near_cols),
                     list(range(1, bb.columns + 1))):
            cols = [c for c in cols if 1 <= c <= bb.columns]
            ranked = []
            for yp, rot, span, orient in self._combos(fp):
                for col in cols:
                    holes = self._pin_holes(fp, col, yp, rot, span)
                    if holes is None or self._pins_ok(iid, holes) is not None:
                        continue
                    a = bb.holes[holes[fp.sites(span)[0][0]]]
                    ps = self.pin_score(iid, fp, holes, orient, span, target_col)
                    ranked.append(((round(ps, 6), a.column, a.yp, rot, span or 0), holes, rot, span, orient))
            ranked.sort(key=lambda t: t[0])
            best, best_key, checked = None, None, 0
            for _, holes, rot, span, orient in ranked:
                c = self._finish(fp, holes, rot, span, orient)
                if self.legal(iid, fp, c) is not None:
                    continue
                a = bb.holes[c.anchor]
                key = (round(self.score(iid, fp, c, target_col), 6), a.column, a.yp, c.rotation, c.span or 0)
                if best_key is None or key < best_key:
                    best, best_key = c, key
                checked += 1
                if checked >= evaluate:
                    break
            if best is not None:
                return self.commit(iid, fp, best, False)
        return None

    def place_at(self, iid: str, fp: Footprint, anchor: str, rotation: int, span: Optional[int],
                 locked: bool) -> Tuple[Optional[Placed], str]:
        """Place with the first site at a given hole (user move or a remembered placement)."""
        bb = self.state.bb
        if anchor not in bb.holes:
            return None, f"there is no hole {anchor} on this board"
        a = bb.holes[anchor]
        if fp.template == "two_lead":
            spans = [span] if span else (fp.spans or [1])
        else:
            spans = [None]
        reasons = []
        for sp in spans:
            orient = "dip" if fp.template in ("dip", "dual_row") else ("row" if rotation % 180 == 0 else "cross")
            c = self._candidate(iid, fp, a.column, a.yp, rotation, sp, orient)
            if c is None:
                reasons.append(f"its pins would fall off the board at {anchor}")
                continue
            why = self.legal(iid, fp, c)
            if why is None:
                return self.commit(iid, fp, c, locked), ""
            reasons.append(why)
        return None, reasons[0] if reasons else "no legal position"


def column_targets(order: Sequence[Tuple[str, Footprint]], columns: int) -> Dict[str, float]:
    """Spread parts left-to-right in signal-flow order, proportional to their width."""
    widths = [(iid, max(fp.extent_steps(), 1) + 1) for iid, fp in order]
    total = sum(w for _, w in widths) or 1
    usable = max(columns - 2, 1)
    scale = min(1.0, usable / total)
    x = 2.0
    out = {}
    for iid, w in widths:
        out[iid] = x + (w * scale) / 2
        x += w * scale
    return out


def estimate_columns(footprints: Sequence[Footprint]) -> int:
    return sum(fp.extent_steps() + 1 for fp in footprints if fp.mount == "breadboard")
