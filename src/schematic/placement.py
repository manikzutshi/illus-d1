"""Deterministic schematic placement.

Strategy ("pin-directed growth"), chosen because it reproduces how people draw schematics:

1. Components connected by *signal* nets form clusters. Power/ground nets do not pull parts
   together — they are drawn as ports.
2. Each cluster grows from a root (the most connected part, or any part the user already
   placed). The next part to place is attached to an already-placed pin: it is put *in front
   of* that pin (in the pin's outward direction) and oriented so its own connecting pin
   faces back (straight wire) or is perpendicular (one bend).
3. Orientation is chosen by scoring all 8 rotations/mirrors: ground pins should point down,
   supply pins up, and other signal pins toward the neighbours they connect to.
4. Positions are searched outward (gap, lateral offset) until the footprint (symbol + text,
   plus clearance) collides with nothing. All coordinates are integers.
5. IC boxes get pin sides in two passes: role heuristics first, then the side facing the
   placed neighbours, with pins ordered by neighbour height to avoid crossings.

Parts with no signal connections (decoupling caps, supply flags) go in a support row below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.enums import ComponentCategory, PinDirection
from core.models import ComponentType
from .geometry import OPPOSITE, VEC, bbox_inflate, bbox_intersects, bbox_union, transform_bbox, transform_ipoint, transform_orientation
from .models import Placement, SymbolDef, SymbolPin, TextItem

Pose = Tuple[int, int, int, bool]           # x, y, rotation, mirror
ALL_ORIENTATIONS = [(r, m) for m in (False, True) for r in (0, 90, 180, 270)]
CLEARANCE = 1.0


@dataclass
class Part:
    iid: str
    ctype: Optional[ComponentType]
    symbol_name: str
    symbol: Optional[SymbolDef]                     # None until a box symbol is built
    pin_map: Dict[str, str]                          # engineering pin -> symbol pin
    eng_pins: List[Tuple[str, str, PinDirection, Optional[str]]]   # (pin_id, name, direction, number)
    is_box: bool = False
    is_flag: bool = False
    reference: str = ""
    value: str = ""
    port_text: str = ""
    show_all_pins: bool = False
    hidden_pins: List[str] = field(default_factory=list)
    port_pins: Dict[str, Tuple[str, str]] = field(default_factory=dict)   # pin -> (power|ground, text)
    fp_cache: Dict[tuple, tuple] = field(default_factory=dict, repr=False)

    def sym_pin(self, pin_id: str) -> Optional[SymbolPin]:
        if self.symbol is None:
            return None
        name = self.pin_map.get(pin_id)
        return next((p for p in self.symbol.pins if p.name == name), None)


@dataclass
class Context:
    parts: Dict[str, Part]
    pin_net: Dict[Tuple[str, str], str]              # (iid, pin) -> net_id
    net_class: Dict[str, str]                        # net_id -> power|ground|signal
    signal_nets: Dict[str, List[Tuple[str, str]]]    # routable signal nets -> [(iid, pin)]


def pin_world(part: Part, pin_id: str, pose: Pose) -> Tuple[Tuple[int, int], str]:
    sp = part.sym_pin(pin_id)
    x, y, rot, mir = pose
    return transform_ipoint(sp.x, sp.y, x, y, rot, mir), transform_orientation(sp.orientation, rot, mir)


def symbol_bbox_local(sym: SymbolDef) -> Tuple[float, float, float, float]:
    boxes = [tuple(sym.body)] + [(p.x, p.y, p.x, p.y) for p in sym.pins if not p.hidden]
    return bbox_union(boxes)


def text_box(t: TextItem) -> Tuple[float, float, float, float]:
    w = 0.62 * t.size * max(len(t.text), 1)
    x0 = {"start": t.x, "middle": t.x - w / 2, "end": t.x - w}[t.anchor]
    return (x0, t.y - 0.85 * t.size, x0 + w, t.y + 0.25 * t.size)


def label_items(part: Part, pose: Pose) -> Tuple[Optional[TextItem], Optional[TextItem]]:
    """World positions of the reference and value texts (always upright)."""
    x, y, rot, mir = pose
    b = transform_bbox(tuple(part.symbol.body), x, y, rot, mir)
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    if part.is_flag:
        pin = part.symbol.pins[0]
        out = OPPOSITE[transform_orientation(pin.orientation, rot, mir)]
        tip = transform_ipoint(pin.x, pin.y, x, y, rot, mir)
        vx, vy = VEC[out]
        reach = 2.6 if part.symbol.kind == "power_flag" else 3.4
        tx, ty = tip[0] + vx * reach, tip[1] + vy * reach + (0.4 if vy == 0 else (0.0 if vy < 0 else 0.6))
        anchor = "middle" if vx == 0 else ("start" if vx > 0 else "end")
        return None, TextItem(x=round(tx, 2), y=round(ty, 2), text=part.port_text or part.value, size=1.0, anchor=anchor)
    r, v = part.reference, part.value
    pins_w = []
    for p in part.symbol.pins:
        if p.hidden:
            continue
        tip = transform_ipoint(p.x, p.y, x, y, rot, mir)
        o = transform_orientation(p.orientation, rot, mir)
        vx, vy = VEC[o]
        inner = (tip[0] - vx * p.length, tip[1] - vy * p.length)
        pins_w.append((tip, inner, o))
    obstacles = []
    for tip, inner, o in pins_w:
        obstacles.append((min(tip[0], inner[0]) - 0.3, min(tip[1], inner[1]) - 0.3, max(tip[0], inner[0]) + 0.3, max(tip[1], inner[1]) + 0.3))
    for pid, (kind, text) in part.port_pins.items():
        sp = part.sym_pin(pid)
        if sp is not None and not sp.hidden:
            tip = transform_ipoint(sp.x, sp.y, x, y, rot, mir)
            obstacles.append(port_extent(tip[0], tip[1], transform_orientation(sp.orientation, rot, mir), kind, text))
    body = (b[0] - 0.2, b[1] - 0.2, b[2] + 0.2, b[3] + 0.2)
    candidates = [
        ("right", TextItem(x=b[2] + 0.7, y=cy - 0.25, text=r, anchor="start"), TextItem(x=b[2] + 0.7, y=cy + 1.15, text=v, size=1.0, anchor="start")),
        ("topbottom", TextItem(x=cx, y=b[1] - 0.55, text=r, anchor="middle"), TextItem(x=cx, y=b[3] + 1.45, text=v, size=1.0, anchor="middle")),
        ("left", TextItem(x=b[0] - 0.7, y=cy - 0.25, text=r, anchor="end"), TextItem(x=b[0] - 0.7, y=cy + 1.15, text=v, size=1.0, anchor="end")),
        ("topright", TextItem(x=cx + 1.3, y=b[1] - 1.7, text=r, anchor="start"), TextItem(x=cx + 1.3, y=b[1] - 0.5, text=v, size=1.0, anchor="start")),
        ("bottomright", TextItem(x=cx + 1.3, y=b[3] + 1.2, text=r, anchor="start"), TextItem(x=cx + 1.3, y=b[3] + 2.4, text=v, size=1.0, anchor="start")),
        ("above", TextItem(x=cx, y=b[1] - 1.8, text=r, anchor="middle"), TextItem(x=cx, y=b[1] - 0.55, text=v, size=1.0, anchor="middle")),
    ]
    chosen = candidates[-1]
    for cand in candidates:
        boxes = [text_box(t) for t in cand[1:] if t.text]
        if not any(bbox_intersects(tb, ob) for tb in boxes for ob in obstacles + [body]):
            chosen = cand
            break
    ref, val = chosen[1], chosen[2]
    for t in (ref, val):
        t.x, t.y = round(t.x, 2), round(t.y, 2)
    return ref, (val if v else None)


def port_extent(x: int, y: int, direction: str, kind: str, text: str) -> Tuple[float, float, float, float]:
    """Area covered by a power/ground port drawn at (x, y) extending in ``direction``."""
    vx, vy = VEC[direction]
    reach, half = 2.0, 1.2
    tip = (x + vx * reach, y + vy * reach)
    if vx == 0:
        box = (x - half, min(y, tip[1]), x + half, max(y, tip[1]))
    else:
        box = (min(x, tip[0]), y - half, max(x, tip[0]), y + half)
    if kind == "ground" and text == "GND":
        return box
    tw = 0.62 * max(len(text), 1)
    tx, ty = x + vx * (reach + 0.9), y + vy * (reach + 0.9)
    if vx == 0:
        tbox = (tx - tw / 2, ty - 0.9, tx + tw / 2, ty + 0.4)
    elif vx > 0:
        tbox = (tx, ty - 0.6, tx + tw, ty + 0.6)
    else:
        tbox = (tx - tw, ty - 0.6, tx, ty + 0.6)
    return bbox_union([box, tbox])


def footprint(part: Part, pose: Pose) -> Tuple[float, float, float, float]:
    """World-space area a part claims: symbol, pins, reference/value text and power ports.
    Memoised per (symbol, rotation, mirror); translation is applied afterwards."""
    x, y, rot, mir = pose
    key = (id(part.symbol), rot, mir)
    rel = part.fp_cache.get(key)
    if rel is None:
        rel = _footprint_at_origin(part, rot, mir)
        part.fp_cache[key] = rel
    return (rel[0] + x, rel[1] + y, rel[2] + x, rel[3] + y)


def _footprint_at_origin(part: Part, rot: int, mir: bool) -> Tuple[float, float, float, float]:
    x, y, pose = 0, 0, (0, 0, rot, mir)
    boxes = [transform_bbox(symbol_bbox_local(part.symbol), x, y, rot, mir)]
    boxes += [text_box(t) for t in label_items(part, pose) if t is not None]
    for pid, (kind, text) in part.port_pins.items():
        sp = part.sym_pin(pid)
        if sp is None or sp.hidden:
            continue
        (px, py), orient = pin_world(part, pid, pose)
        boxes.append(port_extent(px, py, orient, kind, text))
    return bbox_union(boxes)


class PlacementEngine:
    def __init__(self, ctx: Context, fixed: Dict[str, Placement], build_box: Callable[[Part, Dict[str, List[str]]], None],
                 role_side: Callable[[str, str], float]):
        self.ctx = ctx
        self.fixed = fixed
        self.build_box = build_box
        self.role_side = role_side          # (iid, pin) -> negative=left, positive=right

    # ── neighbourhood helpers ────────────────────────────────────────────
    def neighbours(self, iid: str) -> List[Tuple[str, str, str, str]]:
        """(my_pin, net_id, other_iid, other_pin) over routable signal nets, deterministic order."""
        out = []
        for net_id in sorted(self.ctx.signal_nets):
            members = self.ctx.signal_nets[net_id]
            mine = [p for (i, p) in members if i == iid]
            for my_pin in mine:
                for (oi, op) in members:
                    if oi != iid:
                        out.append((my_pin, net_id, oi, op))
        return out

    def clusters(self) -> List[List[str]]:
        seen, out = set(), []
        for iid in sorted(self.ctx.parts):
            if iid in seen:
                continue
            stack, comp = [iid], []
            seen.add(iid)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for _, _, other, _ in self.neighbours(cur):
                    if other not in seen and other in self.ctx.parts:
                        seen.add(other)
                        stack.append(other)
            out.append(sorted(comp))
        return out

    def degree(self, iid: str) -> int:
        return len({n for (_, n, _, _) in self.neighbours(iid)})

    # ── box pin sides ────────────────────────────────────────────────────
    def initial_sides(self, part: Part) -> Dict[str, List[str]]:
        sides: Dict[str, List[str]] = {"left": [], "right": [], "top": [], "bottom": []}
        many = len(part.eng_pins) > 10 and not part.show_all_pins
        part.hidden_pins = []
        floating: List[Tuple[str, PinDirection]] = []
        fixed_sides = part.ctype.symbol.box_sides if (part.ctype and part.ctype.symbol) else {}
        for pin_id, _name, direction, _num in part.eng_pins:
            net = self.ctx.pin_net.get((part.iid, pin_id))
            if pin_id in fixed_sides:
                sides[fixed_sides[pin_id]].append(pin_id)
                continue
            cls = self.ctx.net_class.get(net) if net else None
            if cls == "ground" or (cls is None and direction == PinDirection.GROUND):
                if cls is None and many:
                    part.hidden_pins.append(pin_id); continue
                sides["bottom"].append(pin_id)
            elif cls == "power" or (cls is None and direction == PinDirection.POWER):
                if cls is None and many:
                    part.hidden_pins.append(pin_id); continue
                sides["top"].append(pin_id)
            elif cls == "signal":
                score = self.role_side(part.iid, pin_id)
                if direction == PinDirection.INPUT:
                    score -= 0.5
                elif direction == PinDirection.OUTPUT:
                    score += 0.5
                if score < 0:
                    sides["left"].append(pin_id)
                elif score > 0:
                    sides["right"].append(pin_id)
                else:
                    floating.append((pin_id, direction))
            else:
                if many:
                    part.hidden_pins.append(pin_id); continue
                floating.append((pin_id, direction))
        for pin_id, direction in floating:
            if direction == PinDirection.INPUT:
                sides["left"].append(pin_id)
            elif direction == PinDirection.OUTPUT:
                sides["right"].append(pin_id)
            else:
                (sides["left"] if len(sides["left"]) < len(sides["right"]) else sides["right"]).append(pin_id)
        return sides

    def refined_sides(self, part: Part, poses: Dict[str, Pose], old: Dict[str, List[str]]) -> Dict[str, List[str]]:
        x, y, _, _ = poses[part.iid]
        sides = {"left": [], "right": [], "top": list(old["top"]), "bottom": list(old["bottom"])}
        keyed: Dict[str, List[Tuple[float, int, str]]] = {"left": [], "right": []}
        order = {pid: i for i, (pid, *_rest) in enumerate(part.eng_pins)}
        fixed_sides = part.ctype.symbol.box_sides if (part.ctype and part.ctype.symbol) else {}
        for side in ("left", "right"):
            for pin_id in old[side]:
                pts = []
                net = self.ctx.pin_net.get((part.iid, pin_id))
                for (oi, op) in self.ctx.signal_nets.get(net, []):
                    if oi == part.iid or oi not in poses:
                        continue
                    other = self.ctx.parts[oi]
                    if other.symbol is None:
                        continue
                    (px, py), _ = pin_world(other, op, poses[oi])
                    pts.append((px, py))
                if pts:
                    cx = sum(p[0] for p in pts) / len(pts)
                    cy = sum(p[1] for p in pts) / len(pts)
                    new_side = fixed_sides.get(pin_id) or ("left" if cx < x else "right")
                    keyed[new_side].append((cy, order[pin_id], pin_id))
                else:
                    keyed[side].append((float("inf"), order[pin_id], pin_id))
        for side in ("left", "right"):
            sides[side] = [pid for _, _, pid in sorted(keyed[side])]
        return sides

    # ── orientation scoring ──────────────────────────────────────────────
    def orientation_score(self, part: Part, rot: int, mir: bool, anchor_pin: Optional[str], placed_points: Dict[str, List[Tuple[int, int]]],
                          origin: Tuple[int, int]) -> float:
        score = 0.3 * mir + 0.02 * (rot // 90)
        for pin_id, *_ in part.eng_pins:
            sp = part.sym_pin(pin_id)
            if sp is None or sp.hidden:
                continue
            orient = transform_orientation(sp.orientation, rot, mir)
            net = self.ctx.pin_net.get((part.iid, pin_id))
            cls = self.ctx.net_class.get(net) if net else None
            if cls == "ground":
                score += {"down": 0.0, "up": 4.0}.get(orient, 2.5)
            elif cls == "power":
                score += {"up": 0.0, "down": 4.0}.get(orient, 2.5)
            elif pin_id != anchor_pin and pin_id in placed_points:
                vx, vy = VEC[orient]
                px, py = transform_ipoint(sp.x, sp.y, origin[0], origin[1], rot, mir)
                for tx, ty in placed_points[pin_id]:
                    dot = vx * (tx - px) + vy * (ty - py)
                    score += 0.0 if dot > 0 else 1.5
        return score

    # ── core placement ───────────────────────────────────────────────────
    def collides(self, fp, occupied: Dict[str, Tuple[float, float, float, float]], ignore: str = "") -> bool:
        box = bbox_inflate(fp, CLEARANCE)
        return any(bbox_intersects(box, bbox_inflate(o, CLEARANCE)) for k, o in occupied.items() if k != ignore)

    def best_attached_pose(self, part: Part, my_pin: str, anchor: Tuple[int, int], anchor_dir: str,
                           occupied, placed_points, orientations) -> Optional[Tuple[float, Pose]]:
        ax, ay = anchor
        dax, day = VEC[anchor_dir]
        perp = (0, 1) if dax != 0 else (1, 0)
        best: Optional[Tuple[float, Pose]] = None
        lat_seq = [0]
        for k in range(1, 12):
            lat_seq += [2 * k, -2 * k]
        for rot, mir in orientations:
            sp = part.sym_pin(my_pin)
            if sp is None:
                continue
            dc = transform_orientation(sp.orientation, rot, mir)
            same_way = dc == anchor_dir
            if same_way and not part.is_box:
                continue  # rotatable parts never need a U-turn; boxes get their sides fixed in pass 2
            facing = dc == OPPOSITE[anchor_dir]
            back = (0, 0) if (facing or same_way) else tuple(-v * 2 for v in VEC[dc])
            local_tip = transform_ipoint(sp.x, sp.y, 0, 0, rot, mir)
            found = None
            for lat in lat_seq:
                if found is not None and 0.35 * 3 + 0.5 * abs(lat) >= found[0]:
                    break
                for gap in range(3, 40):
                    tx = ax + dax * gap + back[0] + perp[0] * lat
                    ty = ay + day * gap + back[1] + perp[1] * lat
                    pose = (tx - local_tip[0], ty - local_tip[1], rot, mir)
                    fp = footprint(part, pose)
                    if not self.collides(fp, occupied):
                        cost = 0.35 * gap + 0.5 * abs(lat) + (0.0 if facing else (4.0 if same_way else 1.0))
                        if found is None or cost < found[0]:
                            found = (cost, pose)
                        break
                if found is not None and found[0] <= 0.35 * 3 + (0 if facing else 1.0):
                    break
            if found is None:
                continue
            cost, pose = found
            cost += self.orientation_score(part, rot, mir, my_pin, placed_points, (pose[0], pose[1]))
            if best is None or cost < best[0] - 1e-9:
                best = (cost, pose)
        return best

    def free_pose_near(self, part: Part, x: int, y: int, rot: int, mir: bool, occupied, ignore: str = "") -> Pose:
        for radius in range(0, 60):
            cands = []
            for dx in range(-radius, radius + 1):
                for dy in (-radius, radius) if radius else (0,):
                    cands.append((dx, dy))
            for dy in range(-radius + 1, radius):
                if radius:
                    cands += [(-radius, dy), (radius, dy)]
            for dx, dy in sorted(cands, key=lambda d: (abs(d[0]) + abs(d[1]), d[1], d[0])):
                pose = (x + 2 * dx, y + 2 * dy, rot, mir)
                if not self.collides(footprint(part, pose), occupied, ignore):
                    return pose
        return (x, y, rot, mir)

    def best_isolated_orientation(self, part: Part) -> Tuple[int, bool]:
        options = [(0, False)] if (part.is_box or part.is_flag) else ALL_ORIENTATIONS
        return min(options, key=lambda o: (self.orientation_score(part, o[0], o[1], None, {}, (0, 0)), o[1], o[0]))

    def place_pass(self) -> Dict[str, Pose]:
        parts = self.ctx.parts
        poses: Dict[str, Pose] = {}
        occupied: Dict[str, Tuple[float, float, float, float]] = {}
        for iid, pl in sorted(self.fixed.items()):
            if iid in parts:
                poses[iid] = (pl.x, pl.y, pl.rotation, pl.mirror)
                occupied[iid] = footprint(parts[iid], poses[iid])

        connected_clusters = [c for c in self.clusters() if len(c) > 1 or self.degree(c[0]) > 0]
        loners = [c[0] for c in self.clusters() if len(c) == 1 and self.degree(c[0]) == 0]
        connected_clusters.sort(key=lambda c: (-max(self.degree(i) for i in c), -len(c), c[0]))

        for cluster in connected_clusters:
            members = set(cluster)
            if not any(i in poses for i in cluster):
                root = max(cluster, key=lambda i: (self.degree(i), parts[i].is_box, len(parts[i].eng_pins), [-ord(ch) for ch in i]))
                rot, mir = self.best_isolated_orientation(parts[root])
                if occupied:
                    total = bbox_union(occupied.values())
                    guess = (int(total[2]) + 12, int(total[1]) + 6)
                else:
                    guess = (0, 0)
                poses[root] = self.free_pose_near(parts[root], guess[0], guess[1], rot, mir, occupied)
                occupied[root] = footprint(parts[root], poses[root])
            while True:
                frontier = []
                for iid in sorted(members - set(poses)):
                    links = [(mp, n, oi, op) for (mp, n, oi, op) in self.neighbours(iid) if oi in poses]
                    if not links:
                        continue
                    # Prefer direct (2-pin) nets, then anchors high on the page, then pin order.
                    def link_key(l):
                        mp, n, oi, op = l
                        (px, py), _ = pin_world(parts[oi], op, poses[oi])
                        return (len(self.ctx.signal_nets[n]), py, px, oi, op, mp)
                    links.sort(key=link_key)
                    (ax, ay), _ = pin_world(parts[links[0][2]], links[0][3], poses[links[0][2]])
                    frontier.append((-len(links), ay, ax, iid, links))
                if not frontier:
                    break
                frontier.sort()
                _, _, _, iid, links = frontier[0]
                part = parts[iid]
                placed_points: Dict[str, List[Tuple[int, int]]] = {}
                for mp, n, oi, op in links:
                    placed_points.setdefault(mp, []).append(pin_world(parts[oi], op, poses[oi])[0])
                orientations = [(0, False)] if (part.is_box or part.is_flag) else ALL_ORIENTATIONS
                best = None
                for mp, n, oi, op in links[:3]:
                    anchor, adir = pin_world(parts[oi], op, poses[oi])
                    cand = self.best_attached_pose(part, mp, anchor, adir, occupied, placed_points, orientations)
                    if cand and (best is None or cand[0] < best[0] - 1e-9):
                        best = cand
                if best is None:
                    rot, mir = self.best_isolated_orientation(part)
                    total = bbox_union(occupied.values())
                    poses[iid] = self.free_pose_near(part, int(total[2]) + 6, int(total[1]), rot, mir, occupied)
                else:
                    poses[iid] = best[1]
                occupied[iid] = footprint(part, poses[iid])

        # Support row: parts that only touch power/ground (or nothing).
        remaining = [i for i in loners if i not in poses]
        remaining.sort(key=lambda i: (not parts[i].is_flag, i))
        if remaining:
            total = bbox_union(occupied.values()) if occupied else (0, 0, 0, 0)
            cursor_x = int(total[0])
            row_top = int(total[3]) + 5 if occupied else 0
            for iid in remaining:
                part = parts[iid]
                rot, mir = self.best_isolated_orientation(part)
                fp0 = footprint(part, (0, 0, rot, mir))
                x = cursor_x - int(fp0[0]) + 1
                y = row_top - int(fp0[1])
                poses[iid] = self.free_pose_near(part, x, y, rot, mir, occupied)
                occupied[iid] = footprint(part, poses[iid])
                cursor_x = int(occupied[iid][2]) + 4
        return poses

    def resolve_kept_collisions(self, poses: Dict[str, Pose]) -> Dict[str, Pose]:
        """Kept (unlocked) placements may collide after a symbol changed size: nudge them."""
        occupied = {i: footprint(self.ctx.parts[i], p) for i, p in poses.items()}
        for iid in sorted(poses):
            pl = self.fixed.get(iid)
            if pl is None or pl.locked:
                continue
            if self.collides(occupied[iid], occupied, ignore=iid):
                x, y, r, m = poses[iid]
                poses[iid] = self.free_pose_near(self.ctx.parts[iid], x, y, r, m, occupied, ignore=iid)
                occupied[iid] = footprint(self.ctx.parts[iid], poses[iid])
        return poses

    def wire_cost(self, iid: str, pose: Pose, poses: Dict[str, Pose]) -> float:
        """Estimated wiring cost of a part in a pose: distance from each signal pin to the
        centroid of the pins it connects to (+ a detour penalty when the pin faces away)."""
        part = self.ctx.parts[iid]
        total = 0.0
        for pin_id, *_ in part.eng_pins:
            net = self.ctx.pin_net.get((iid, pin_id))
            if net not in self.ctx.signal_nets:
                continue
            sp = part.sym_pin(pin_id)
            if sp is None or sp.hidden:
                continue
            (px, py), orient = pin_world(part, pin_id, pose)
            pts = []
            for oi, op in self.ctx.signal_nets[net]:
                if oi == iid or oi not in poses or self.ctx.parts[oi].symbol is None:
                    continue
                pts.append(pin_world(self.ctx.parts[oi], op, poses[oi])[0])
            if not pts:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            total += abs(cx - px) + abs(cy - py)
            vx, vy = VEC[orient]
            if vx * (cx - px) + vy * (cy - py) < 0:
                total += 4.0
        return total

    def refine_orientations(self, poses: Dict[str, Pose], rounds: int = 2) -> Dict[str, Pose]:
        for _ in range(rounds):
            improved = False
            occupied = {i: footprint(self.ctx.parts[i], p) for i, p in poses.items()}
            for iid in sorted(poses):
                part = self.ctx.parts[iid]
                if part.is_box or part.is_flag or iid in self.fixed:
                    continue
                x, y, r0, m0 = poses[iid]
                def total(pose):
                    return self.wire_cost(iid, pose, poses) + 2.0 * self.orientation_score(part, pose[2], pose[3], None, {}, (pose[0], pose[1]))
                best_pose, best_cost = poses[iid], total(poses[iid])
                for rot, mir in ALL_ORIENTATIONS:
                    cand = (x, y, rot, mir)
                    if cand == poses[iid]:
                        continue
                    if self.collides(footprint(part, cand), occupied, ignore=iid):
                        continue
                    cost = total(cand)
                    if cost < best_cost - 0.5:
                        best_pose, best_cost = cand, cost
                if best_pose != poses[iid]:
                    poses[iid] = best_pose
                    occupied[iid] = footprint(part, best_pose)
                    improved = True
            if not improved:
                break
        return poses

    def run(self) -> Dict[str, Pose]:
        boxes = [p for p in self.ctx.parts.values() if p.is_box]
        sides = {p.iid: self.initial_sides(p) for p in boxes}
        for p in boxes:
            self.build_box(p, sides[p.iid])
        poses = self.place_pass()
        if boxes:
            changed = False
            for p in boxes:
                new = self.refined_sides(p, poses, sides[p.iid])
                if new != sides[p.iid]:
                    sides[p.iid] = new
                    self.build_box(p, new)
                    changed = True
            if changed:
                poses = self.place_pass()
        poses = self.refine_orientations(poses)
        return self.resolve_kept_collisions(poses)


def role_sign(ctype: Optional[ComponentType], pin_direction: Optional[PinDirection] = None) -> float:
    """-1: belongs left of a controller (inputs/sensors), +1: right (outputs/actuators)."""
    if ctype is None:
        return 0.0
    roles = {r.upper() for r in ctype.roles}
    if ctype.category in (ComponentCategory.SENSOR, ComponentCategory.SWITCH) or roles & {"SENSOR", "INPUT"}:
        return -1.0
    if ctype.category in (ComponentCategory.ACTUATOR, ComponentCategory.DISPLAY) or roles & {"ACTUATOR", "DISPLAY", "OUTPUT"}:
        return 1.0
    return 0.0
