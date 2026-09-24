"""Orthogonal grid router for schematic wires.

Each signal net is routed as a rectilinear Steiner-like tree: terminals (pin tips) are joined
one at a time to the growing tree by a bend- and crossing-aware A* search on the integer grid.

Hard rules (a violation would make the drawing *imply a wrong connection*):
  * never enter symbol bodies, pin lines, port/label graphics;
  * never touch another net's node (pin tip, corner, wire end, junction);
  * never run collinear with another net's wire, and never turn on another net's wire;
  * crossing another net's wire perpendicularly is allowed (no junction there) but costs.

Everything is deterministic: ties are broken by insertion counters, never by hashing.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

Point = Tuple[int, int]

DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1)]          # right, left, down, up
DIR_INDEX = {"right": 0, "left": 1, "down": 2, "up": 3}
OPP = {0: 1, 1: 0, 2: 3, 3: 2}

STEP_COST = 1.0
BEND_COST = 4.0
CROSS_COST = 7.0
NEAR_BODY_COST = 1.5
SOFT_COST = 2.0
MAX_EXPANSIONS = 120_000


@dataclass
class Terminal:
    point: Point
    orientation: str      # outward direction of the pin at this tip
    ref: str = ""


@dataclass
class RouteResult:
    net_id: str
    edges: List[Tuple[Point, Point]] = field(default_factory=list)
    ok: bool = True
    reason: str = ""


class GridRouter:
    def __init__(self, bounds: Tuple[int, int, int, int]):
        self.x0, self.y0, self.x1, self.y1 = bounds
        self.blocked: Set[Point] = set()
        self.near: Set[Point] = set()
        self.soft: Set[Point] = set()
        self.nodes: Dict[Point, str] = {}          # point -> owning net (tips, corners, ends)
        self.edges_h: Dict[Point, str] = {}        # (x, y) -> net for edge (x,y)-(x+1,y)
        self.edges_v: Dict[Point, str] = {}        # (x, y) -> net for edge (x,y)-(x,y+1)
        self.pass_h: Dict[Point, Set[str]] = {}
        self.pass_v: Dict[Point, Set[str]] = {}

    # ── obstacle registration ────────────────────────────────────────────
    def block(self, points: Iterable[Point]) -> None:
        self.blocked.update(points)

    def block_rect(self, x0: float, y0: float, x1: float, y1: float, near_margin: int = 1) -> None:
        import math
        ix0, iy0, ix1, iy1 = math.ceil(x0), math.ceil(y0), math.floor(x1), math.floor(y1)
        for x in range(ix0, ix1 + 1):
            for y in range(iy0, iy1 + 1):
                self.blocked.add((x, y))
        for x in range(ix0 - near_margin, ix1 + near_margin + 1):
            for y in range(iy0 - near_margin, iy1 + near_margin + 1):
                self.near.add((x, y))

    def soften_rect(self, x0: float, y0: float, x1: float, y1: float) -> None:
        import math
        for x in range(math.floor(x0), math.ceil(x1) + 1):
            for y in range(math.floor(y0), math.ceil(y1) + 1):
                self.soft.add((x, y))

    def reserve_node(self, p: Point, owner: str) -> None:
        self.nodes.setdefault(p, owner)

    # ── queries ──────────────────────────────────────────────────────────
    def _in_bounds(self, p: Point) -> bool:
        return self.x0 <= p[0] <= self.x1 and self.y0 <= p[1] <= self.y1

    def _edge_owner(self, a: Point, b: Point) -> Optional[str]:
        if a[1] == b[1]:
            return self.edges_h.get((min(a[0], b[0]), a[1]))
        return self.edges_v.get((a[0], min(a[1], b[1])))

    def _others(self, table: Dict[Point, Set[str]], p: Point, net: str) -> bool:
        owners = table.get(p)
        return bool(owners) and any(o != net for o in owners)

    # ── routing ──────────────────────────────────────────────────────────
    def route_net(self, net_id: str, terminals: List[Terminal]) -> RouteResult:
        """Route one net. Nothing is committed; call :meth:`commit` with the result."""
        if len(terminals) < 2:
            return RouteResult(net_id, ok=False, reason="fewer than two drawable pins")
        order = sorted(terminals, key=lambda t: (t.point[0], t.point[1], t.ref))
        first = order[0]
        tree: Dict[Point, Optional[int]] = {first.point: DIR_INDEX[first.orientation]}
        tip_dirs = {t.point: DIR_INDEX[t.orientation] for t in terminals}
        edges: List[Tuple[Point, Point]] = []
        remaining = order[1:]
        while remaining:
            # Prim-style: connect the terminal nearest to the current tree next.
            remaining.sort(key=lambda t: (min(abs(t.point[0] - q[0]) + abs(t.point[1] - q[1]) for q in tree), t.point, t.ref))
            term = remaining.pop(0)
            if term.point in tree:
                continue
            path = self._astar(net_id, term, tree, tip_dirs)
            if path is None:
                return RouteResult(net_id, ok=False, reason=f"no route to {term.ref or term.point}")
            for a, b in zip(path, path[1:]):
                edges.append((a, b))
            for p in path:
                if p not in tree:
                    tree[p] = None
        return RouteResult(net_id, edges=edges)

    def _astar(self, net: str, term: Terminal, tree: Dict[Point, Optional[int]], tip_dirs: Dict[Point, int]) -> Optional[List[Point]]:
        # Valid targets: tree points not shared with another net's wire (arriving there would
        # create a junction on a crossing).
        targets = {p for p in tree if not self._others(self.pass_h, p, net) and not self._others(self.pass_v, p, net)}
        if not targets:
            return None
        tlist = sorted(targets)

        def h(p: Point) -> float:
            return min(abs(p[0] - t[0]) + abs(p[1] - t[1]) for t in tlist)

        start = term.point
        sdir = DIR_INDEX[term.orientation]
        counter = 0
        open_heap: list = [(h(start), 0.0, counter, start, -1)]
        best: Dict[Tuple[Point, int], float] = {(start, -1): 0.0}
        parent: Dict[Tuple[Point, int], Tuple[Point, int]] = {}
        expansions = 0
        while open_heap:
            f, g, _, p, d = heapq.heappop(open_heap)
            if best.get((p, d), float("inf")) < g:
                continue
            if p in targets and p != start:
                return self._reconstruct(parent, (p, d))
            expansions += 1
            if expansions > MAX_EXPANSIONS:
                return None
            crossing_here = p != start and (self._others(self.pass_h, p, net) or self._others(self.pass_v, p, net))
            for nd, (dx, dy) in enumerate(DIRS):
                if d != -1 and nd == OPP[d]:
                    continue
                if crossing_here and nd != d:
                    continue  # never turn on top of another net's wire
                if d == -1 and nd == OPP[sdir]:
                    continue  # never leave a pin back into its own body
                q = (p[0] + dx, p[1] + dy)
                if not self._in_bounds(q):
                    continue
                is_target = q in targets
                if q in self.blocked and not is_target:
                    continue
                owner = self.nodes.get(q)
                if owner is not None and owner != net:
                    continue
                eo = self._edge_owner(p, q)
                if eo is not None and eo != net:
                    continue
                horizontal = nd in (0, 1)
                same_axis = self.pass_h if horizontal else self.pass_v
                cross_axis = self.pass_v if horizontal else self.pass_h
                if self._others(same_axis, q, net):
                    continue  # would run along / touch another net's wire
                cost = g + STEP_COST
                if d == -1:
                    if nd != sdir:
                        cost += BEND_COST
                elif nd != d:
                    cost += BEND_COST
                if self._others(cross_axis, q, net):
                    if is_target:
                        continue
                    cost += CROSS_COST
                if q in self.near:
                    cost += NEAR_BODY_COST
                if q in self.soft:
                    cost += SOFT_COST
                if is_target and q in tip_dirs and nd != OPP[tip_dirs[q]]:
                    cost += BEND_COST  # entering a pin sideways reads like a corner
                key = (q, nd)
                if cost < best.get(key, float("inf")):
                    best[key] = cost
                    parent[key] = (p, d)
                    counter += 1
                    heapq.heappush(open_heap, (cost + h(q), cost, counter, q, nd))
        return None

    @staticmethod
    def _reconstruct(parent, key) -> List[Point]:
        path = [key[0]]
        while key in parent:
            key = parent[key]
            path.append(key[0])
        path.reverse()
        return path

    def commit(self, result: RouteResult, tips: Iterable[Point] = ()) -> None:
        net = result.net_id
        degree: Dict[Point, List[str]] = {}
        for a, b in result.edges:
            if a[1] == b[1]:
                self.edges_h[(min(a[0], b[0]), a[1])] = net
                axis = "h"
                self.pass_h.setdefault(a, set()).add(net)
                self.pass_h.setdefault(b, set()).add(net)
            else:
                self.edges_v[(a[0], min(a[1], b[1]))] = net
                axis = "v"
                self.pass_v.setdefault(a, set()).add(net)
                self.pass_v.setdefault(b, set()).add(net)
            degree.setdefault(a, []).append(axis)
            degree.setdefault(b, []).append(axis)
        for p, axes in degree.items():
            # Corners, wire ends and T-points become nodes other nets must avoid.
            if len(axes) != 2 or axes[0] != axes[1]:
                self.nodes[p] = net
        for t in tips:
            self.nodes[t] = net


def edges_to_segments(edges: List[Tuple[Point, Point]], breakpoints: Set[Point]) -> List[Tuple[Point, Point]]:
    """Merge unit edges into maximal straight segments, split at corners, branches and
    ``breakpoints`` (pin tips etc.). Output is sorted for determinism."""
    adj: Dict[Point, Set[Point]] = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    def is_break(p: Point) -> bool:
        n = adj.get(p, set())
        if p in breakpoints or len(n) != 2:
            return True
        a, b = sorted(n)
        return not (a[0] == b[0] == p[0] or a[1] == b[1] == p[1])

    seen: Set[Tuple[Point, Point]] = set()
    segments: List[Tuple[Point, Point]] = []
    for start in sorted(adj):
        if not is_break(start):
            continue
        for nxt in sorted(adj[start]):
            if (start, nxt) in seen:
                continue
            dx, dy = nxt[0] - start[0], nxt[1] - start[1]
            cur, prev = nxt, start
            seen.add((start, nxt)); seen.add((nxt, start))
            while not is_break(cur):
                step = (cur[0] + dx, cur[1] + dy)
                if step not in adj.get(cur, set()):
                    break
                seen.add((cur, step)); seen.add((step, cur))
                prev, cur = cur, step
            a, b = sorted([start, cur])
            segments.append((a, b))
    # Closed loops without break points (cannot occur for trees, kept for safety).
    return sorted(set(segments))
