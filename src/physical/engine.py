"""Physical projection: EngineeringDesignProject -> PhysicalProject (breadboard build).

    Engineering Design ──► footprints (registry + data/physical) ──► rails ──► placement
        ──► off-board arrangement ──► leads + jumpers ──► Physical IR ──► physical verification

Deterministic: the same design and layout state always give the same build.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from components.registry import ComponentRegistry, get_shared_registry
from core.enums import ComponentCategory
from core.models import EngineeringDesignProject
from schematic.netclass import classify_nets

from .breadboard import BOARD_SPECS, PITCH_MM, RAIL_POLARITY, RAIL_YP, ROW_YP, make_breadboard
from .footprints import Footprint, resolve_footprint
from .models import (AssemblyStep, BoardInfo, Box, GeometryInfo, PhysicalLayoutState, PhysicalNetTrace,
                     PhysicalPart, PhysicalPin, PhysicalPlacement, PhysicalProject, PhysicalStats, RailInfo,
                     VisualSpec)
from .placement import Placed, PlacementEngine, column_targets, estimate_columns, overlaps, rotate
from .verify import verify_physical
from .visual import visual_params
from .wiring import BodyBox, Terminal3D, Wirer, net_colors

BOARD_GAP = 14.0          # mm between the breadboard and off-board items
PLACE_CLASS = {"dual_row": 0, "dip": 0, "inline": 1, "smd_adapter": 1, "two_lead": 2}


def _rail_assignment(info, pin_net, fps) -> Tuple[Dict[str, Optional[str]], List[str]]:
    """Ground on both '-' rails; the busiest supply on T+, a second supply on B+."""
    used_nets = {n for (iid, _), n in pin_net.items() if n and fps[iid].mount != "virtual"}
    count: Dict[str, int] = {}
    for (iid, _), n in pin_net.items():
        if n and fps[iid].mount != "virtual":
            count[n] = count.get(n, 0) + 1
    grounds = sorted((n for n, i in info.items() if i.net_class == "ground" and n in used_nets),
                     key=lambda n: (-count.get(n, 0), n))
    supplies = sorted((n for n, i in info.items() if i.net_class == "power" and n in used_nets),
                      key=lambda n: (-count.get(n, 0), -(info[n].voltage or 0), n))
    rails: Dict[str, Optional[str]] = {"T+": None, "T-": None, "B+": None, "B-": None}
    if grounds:
        rails["T-"] = rails["B-"] = grounds[0]
    if supplies:
        rails["T+"] = supplies[0]
        rails["B+"] = supplies[1] if len(supplies) > 1 else supplies[0]
    return rails, supplies


def _offboard_side(ctype) -> str:
    if ctype is None:
        return "right"
    if ctype.category in (ComponentCategory.POWER_SOURCE, ComponentCategory.POWER_MANAGEMENT):
        return "left"
    if ctype.category == ComponentCategory.MICROCONTROLLER:
        return "bottom"
    return "right"


class _Build:
    """Mutable working state of one projection attempt."""

    def __init__(self, kind: str):
        self.kind = kind
        self.placed: Dict[str, Placed] = {}
        self.notes: Dict[str, List[str]] = {}
        self.engine: Optional[PlacementEngine] = None
        self.order: List[str] = []


def generate_physical(design: EngineeringDesignProject, registry: Optional[ComponentRegistry] = None,
                      layout: Optional[PhysicalLayoutState] = None, schematic=None) -> PhysicalProject:
    t0 = time.perf_counter()
    registry = registry or get_shared_registry()
    layout = layout or PhysicalLayoutState()
    ctypes = {c.instance_id: registry.get(c.component_type) for c in design.components}
    fps: Dict[str, Footprint] = {iid: resolve_footprint(ct) for iid, ct in ctypes.items()}
    pin_net: Dict[Tuple[str, str], Optional[str]] = {}
    for net in design.nets:
        for pr in net.connections:
            pin_net[(pr.instance_id, pr.pin_id)] = net.net_id
    for iid, fp in fps.items():                       # an aliased pin brings its net to the pin it shares
        for a, t in fp.pin_alias.items():
            if pin_net.get((iid, a)) and not pin_net.get((iid, t)):
                pin_net[(iid, t)] = pin_net[(iid, a)]

    if schematic is None:
        try:
            from schematic import generate_schematic
            schematic = generate_schematic(design, registry)
        except Exception:                                 # ordering hint only; never fatal
            schematic = None
    hint: Dict[str, Tuple[float, float]] = {}
    refs: Dict[str, Tuple[str, str]] = {}
    if schematic is not None:
        for c in schematic.components:
            hint[c.instance_id] = (c.x, c.y)
            refs[c.instance_id] = (c.reference, c.value)
    order_of = {c.instance_id: k for k, c in enumerate(design.components)}

    def hint_key(iid: str):
        x, y = hint.get(iid, (1e6, 0))
        return (x, y, order_of[iid])

    physical_ids = [c.instance_id for c in design.components if fps[c.instance_id].mount != "virtual"]
    if not physical_ids:
        proj = PhysicalProject(project_id=design.project_id, name=design.name, applicable=False,
                               parts=[_virtual_part(iid, design, ctypes, fps, refs) for iid in fps])
        proj.verification = verify_physical(proj, design)
        proj.stats = PhysicalStats(parts_virtual=len(fps), elapsed_ms=round((time.perf_counter() - t0) * 1000, 2))
        return proj

    info = classify_nets(design, registry)
    rail_nets, supplies = _rail_assignment(info, pin_net, fps)
    board_ids = sorted((i for i in physical_ids if fps[i].mount == "breadboard"), key=hint_key)

    if layout.board != "auto":
        kinds = [layout.board]
    else:
        # Two-lead parts often stand across the trench or go into a rail, so the flat-row estimate is
        # pessimistic: try the half-size board unless the design is clearly larger.
        need = estimate_columns([fps[i] for i in board_ids])
        kinds = ["half", "full"] if need <= 2 * BOARD_SPECS["half"].columns else ["full"]
    build = None
    for kind in kinds:
        build = _place_board(kind, board_ids, fps, pin_net, rail_nets, layout, hint_key)
        if all(p.mount == "breadboard" for p in build.placed.values()) or kind == kinds[-1]:
            break
    assert build is not None and build.engine is not None
    st = build.engine.state
    bb = st.bb
    board_h = bb.spec.size_mm[2]

    # ── off-board items ─────────────────────────────────────────────────
    off_ids = sorted((i for i in physical_ids if fps[i].mount == "offboard"), key=hint_key)
    _arrange_offboard(build, off_ids, fps, ctypes, layout, board_h)
    unplaced = [iid for iid, p in build.placed.items() if p.mount == "unplaced"]
    _park_unplaced(build, unplaced, fps, board_h)

    # ── terminals, bodies, wiring ───────────────────────────────────────
    terminals: List[Terminal3D] = []
    for iid in off_ids:
        p = build.placed[iid]
        for t in fps[iid].terminals:
            dx, dy = rotate(t.at[0], t.at[1], p.rotation)
            pos = (round(p.position[0] + dx, 3), round(p.position[1] + dy, 3), round(-board_h + t.at[2], 3))
            terminals.append(Terminal3D(f"{iid}.{t.pin_id}", pin_net.get((iid, t.pin_id)), t.style, pos, t.color))
    bodies = []
    for iid, p in build.placed.items():
        if p.body_rect and p.mount == "breadboard":
            fp = fps[iid]
            bodies.append(BodyBox(iid, p.body_rect, fp.body_z + fp.body_mm[2]))
    colors = net_colors(info, supplies)
    wirer = Wirer(st, bodies, colors, board_h)
    lead_holes = wirer.plug_leads(terminals, rail_nets)
    nets_to_join = sorted({n for (iid, _), n in pin_net.items() if n and fps[iid].mount != "virtual"})
    open_nets = wirer.connect_nets(nets_to_join, terminals, rail_nets)

    # ── Physical IR ─────────────────────────────────────────────────────
    term_pos = {t.pin_ref: t for t in terminals}
    parts: List[PhysicalPart] = []
    for c in design.components:
        iid = c.instance_id
        fp, ct = fps[iid], ctypes[iid]
        if fp.mount == "virtual":
            parts.append(_virtual_part(iid, design, ctypes, fps, refs))
            continue
        pl = build.placed[iid]
        ref, value = refs.get(iid, (iid.upper(), ""))
        pins: List[PhysicalPin] = []
        pin_names = {p.pin_id: p.name for p in ct.pins} if ct else {}
        for pid in [p.pin_id for p in ct.pins] if ct else []:
            net = pin_net.get((iid, pid))
            if pid in fp.pin_alias:
                tgt = fp.pin_alias[pid]
                pos = _pin_position(pl, tgt, fp, bb, term_pos, iid)
                pins.append(PhysicalPin(pin_id=pid, name=pin_names.get(pid, pid), net_id=net, position=pos,
                                        alias_of=tgt))
                continue
            if pl.mount == "breadboard" and pid in pl.pin_holes:
                h = bb.holes[pl.pin_holes[pid]]
                pins.append(PhysicalPin(pin_id=pid, name=pin_names.get(pid, pid), net_id=net, position=[h.x, h.y, 0.0],
                                        hole=h.hole_id, node=h.node))
            elif pl.mount == "offboard" and f"{iid}.{pid}" in term_pos:
                t = term_pos[f"{iid}.{pid}"]
                pins.append(PhysicalPin(pin_id=pid, name=pin_names.get(pid, pid), net_id=net, position=list(t.pos),
                                        terminal=t.style))
            else:
                pins.append(PhysicalPin(pin_id=pid, name=pin_names.get(pid, pid), net_id=net,
                                        position=[pl.position[0], pl.position[1], pl.position[2]]))
        body = _body_box(pl, fp, board_h)
        vparams = visual_params(fp.visual, c.parameters, ct.name if ct else iid, ct.short_name if ct else None)
        if fp.template in ("dip", "dual_row"):
            vparams["pin_count"] = str(fp.total_pins)
            vparams["row_span"] = str(fp.row_span)
            vparams["pitch_steps"] = str(fp.pitch_steps)
        elif fp.template in ("inline", "smd_adapter"):
            vparams["pin_count"] = str(len(fp.pins))
        geometry = GeometryInfo(source=fp.source, notes=list(fp.notes), variant_note=fp.variant_note)
        notes = list(build.notes.get(iid, []))
        if iid in unplaced:
            notes.insert(0, "No legal position on the breadboard for this part (all candidate positions would short or collide).")
        parts.append(PhysicalPart(
            instance_id=iid, component_type_id=c.component_type, reference=ref, value=value, mount=pl.mount,
            template=fp.template, position=[round(v, 3) for v in (pl.body_center[0], pl.body_center[1], 0.0)]
            if pl.mount == "breadboard" else [round(v, 3) for v in pl.position],
            rotation=pl.rotation, anchor=pl.anchor, orientation=pl.orientation, span=pl.span, body=body, pins=pins,
            visual=VisualSpec(kind=fp.visual, asset_url=fp.asset_url, fallback=fp.fallback, label=ref, params=vparams),
            geometry=geometry, locked=pl.locked, internal_links=fp.internal_links, notes=notes))

    rails = []
    for rail, yp in RAIL_YP.items():
        used = any(h in st.occupied for h in bb.node_holes.get(f"rail:{rail}", []))
        rails.append(RailInfo(rail_id=rail, polarity=RAIL_POLARITY[rail], y=round(yp * PITCH_MM, 4),
                              columns=bb.rail_columns(), net_id=rail_nets.get(rail) if used else None))
    board = BoardInfo(kind=bb.spec.kind, name=bb.spec.name, columns=bb.columns, rows=list(ROW_YP),
                      row_y={r: round(v * PITCH_MM, 4) for r, v in ROW_YP.items()},
                      column_x=[round(bb.column_xp(c) * PITCH_MM, 4) for c in range(1, bb.columns + 1)],
                      size_mm=list(bb.spec.size_mm), rails=rails, note=bb.spec.note)

    nets: Dict[str, PhysicalNetTrace] = {}
    for net in design.nets:
        ni = info.get(net.net_id)
        nodes = sorted(n for n in st.net_nodes.get(net.net_id, [])
                       if any(h in st.occupied for h in bb.node_holes.get(n, [])))
        nets[net.net_id] = PhysicalNetTrace(
            net_id=net.net_id, display_name=ni.display_name if ni else net.net_id,
            net_class=ni.net_class if ni else "signal", nodes=nodes,
            wires=[w.wire_id for w in wirer.wires if w.net_id == net.net_id],
            pins=[pr.ref for pr in net.connections if fps[pr.instance_id].mount != "virtual"],
            rails=[r.rail_id for r in rails if r.net_id == net.net_id], color=colors.get(net.net_id, ""))

    diagnostics = [f"Net {n} could not be completed with jumper wires (no free holes)." for n in open_nets]
    proj = PhysicalProject(project_id=design.project_id, name=design.name, board=board, parts=parts,
                           wires=wirer.wires, nets=nets, occupied=dict(sorted(st.occupied.items())),
                           covered=sorted(st.covered), diagnostics=diagnostics)
    proj.bounds = _bounds(proj)
    proj.assembly = _assembly(proj, build, ctypes, info)
    proj.verification = verify_physical(proj, design)
    proj.stats = PhysicalStats(
        parts_on_board=sum(1 for p in parts if p.mount == "breadboard"),
        parts_offboard=sum(1 for p in parts if p.mount == "offboard"),
        parts_virtual=sum(1 for p in parts if p.mount == "virtual"),
        wires=sum(1 for w in wirer.wires if w.kind != "lead"), leads=sum(1 for w in wirer.wires if w.kind == "lead"),
        wire_length_mm=round(sum(w.length_mm for w in wirer.wires), 1), holes_used=len(st.occupied),
        elapsed_ms=round((time.perf_counter() - t0) * 1000, 2))
    return proj


# ── placement passes ───────────────────────────────────────────────────────

def _place_board(kind, board_ids, fps, pin_net, rail_nets, layout, hint_key) -> _Build:
    build = _Build(kind)
    eng = PlacementEngine(kind, pin_net, rail_nets)
    build.engine = eng
    bb = eng.state.bb
    # Earlier placements first; the latest user move (highest seq) must fit around them, so a drop
    # onto an occupied spot is refused instead of shoving other parts away.
    remembered = [i for i in board_ids if i in layout.placements and layout.placements[i].anchor]
    remembered.sort(key=lambda i: (layout.placements[i].seq, not layout.placements[i].locked, hint_key(i)))
    for iid in remembered:
        pl = layout.placements[iid]
        placed, why = eng.place_at(iid, fps[iid], pl.anchor, pl.rotation, pl.span, pl.locked)
        if placed:
            build.placed[iid] = placed
        elif pl.locked:
            build.notes.setdefault(iid, []).append(f"Requested placement at {pl.anchor} could not be kept: {why}.")
    rest = [i for i in board_ids if i not in build.placed]
    targets = column_targets([(i, fps[i]) for i in board_ids], bb.columns)
    rest.sort(key=lambda i: (PLACE_CLASS.get(fps[i].template, 3), hint_key(i)))
    for iid in rest:
        placed = eng.place(iid, fps[iid], targets.get(iid, bb.columns / 2))
        build.placed[iid] = placed or Placed(iid, fps[iid], "unplaced")
    return build


def _arrange_offboard(build: _Build, off_ids, fps, ctypes, layout, board_h) -> None:
    st = build.engine.state
    bx0, by0, bx1, by1 = st.bb.bounds_mm()
    taken: List[Tuple[float, float, float, float]] = [(bx0, by0, bx1, by1)]
    cursor = {"left": by0, "right": by0, "bottom": bx0}
    board_c = (0.0, 0.0)

    def rect_at(x, y, w, d):
        return (x - w / 2, y - d / 2, x + w / 2, y + d / 2)

    placed_first = sorted((i for i in off_ids if (layout.placements.get(i) and layout.placements[i].x is not None)),
                          key=lambda i: (layout.placements[i].seq, off_ids.index(i)))
    for iid in placed_first + [i for i in off_ids if i not in placed_first]:
        fp = fps[iid]
        pl = layout.placements.get(iid)
        if pl and pl.x is not None and pl.y is not None:
            L, D = fp.body_mm[0], fp.body_mm[1]
            if pl.rotation % 180:
                L, D = D, L
            r = rect_at(pl.x, pl.y, L, D)
            if not any(overlaps(r, t) for t in taken):
                taken.append(r)
                build.placed[iid] = Placed(iid, fp, "offboard", pl.rotation, "offboard", position=(pl.x, pl.y, -board_h),
                                           body_rect=r, body_center=(pl.x, pl.y), locked=pl.locked)
                continue
            if pl.locked:
                build.notes.setdefault(iid, []).append("Requested placement could not be kept: it overlaps the board or another item.")
        side = _offboard_side(ctypes.get(iid))
        best = None
        for rot in (0, 90, 180, 270):
            L, D = fp.body_mm[0], fp.body_mm[1]
            if rot % 180:
                L, D = D, L
            if side == "left":
                x, y = bx0 - BOARD_GAP - L / 2, cursor["left"] + D / 2
            elif side == "right":
                x, y = bx1 + BOARD_GAP + L / 2, cursor["right"] + D / 2
            else:
                x, y = cursor["bottom"] + L / 2, by1 + BOARD_GAP + D / 2
            r = rect_at(x, y, L, D)
            if any(overlaps(r, t) for t in taken):
                continue
            terms = fp.terminals or []
            if terms:
                d = sum(((x + rotate(t.at[0], t.at[1], rot)[0] - board_c[0]) ** 2 +
                         (y + rotate(t.at[0], t.at[1], rot)[1] - board_c[1]) ** 2) ** 0.5 for t in terms) / len(terms)
            else:
                d = 0.0
            key = (round(d, 3), rot)
            if best is None or key < best[0]:
                best = (key, rot, x, y, r, L, D)
        if best is None:                       # stack further out
            L, D = fp.body_mm[0], fp.body_mm[1]
            x, y = bx1 + BOARD_GAP * 2 + L / 2, cursor["right"] + D / 2
            best = ((0, 0), 0, x, y, rect_at(x, y, L, D), L, D)
        _, rot, x, y, r, L, D = best
        taken.append(r)
        if side == "left":
            cursor["left"] += D + 6.0
        elif side == "right":
            cursor["right"] += D + 6.0
        else:
            cursor["bottom"] += L + 8.0
        build.placed[iid] = Placed(iid, fp, "offboard", rot, "offboard", position=(round(x, 3), round(y, 3), -board_h),
                                   body_rect=r, body_center=(x, y), locked=bool(pl and pl.locked and pl.x is not None))


def _park_unplaced(build: _Build, unplaced, fps, board_h) -> None:
    bx0, by0, bx1, by1 = build.engine.state.bb.bounds_mm()
    x = bx0
    for iid in unplaced:
        fp = fps[iid]
        L, D = fp.body_mm[0], fp.body_mm[1]
        y = by0 - BOARD_GAP - 20.0 - D / 2
        build.placed[iid].position = (round(x + L / 2, 3), round(y, 3), -board_h)
        build.placed[iid].body_center = (x + L / 2, y)
        x += L + 6.0


def _pin_position(pl: Placed, pin: str, fp: Footprint, bb, term_pos, iid) -> List[float]:
    if pl.mount == "breadboard" and pin in pl.pin_holes:
        h = bb.holes[pl.pin_holes[pin]]
        return [h.x, h.y, 0.0]
    t = term_pos.get(f"{iid}.{pin}")
    return list(t.pos) if t else [pl.position[0], pl.position[1], pl.position[2]]


def _body_box(pl: Placed, fp: Footprint, board_h: float) -> Optional[Box]:
    L, D, H = fp.body_mm
    if pl.rotation % 180:
        L, D = D, L
    if pl.mount == "breadboard":
        return Box(center=[round(pl.body_center[0], 3), round(pl.body_center[1], 3), round(fp.body_z + H / 2, 3)],
                   size=[L, D, H])
    if pl.mount in ("offboard", "unplaced"):
        return Box(center=[round(pl.position[0], 3), round(pl.position[1], 3), round(-board_h + H / 2, 3)],
                   size=[L, D, H])
    return None


def _virtual_part(iid, design, ctypes, fps, refs) -> PhysicalPart:
    c = next(c for c in design.components if c.instance_id == iid)
    ct = ctypes.get(iid)
    ref, value = refs.get(iid, (iid.upper(), ""))
    return PhysicalPart(instance_id=iid, component_type_id=c.component_type, reference=ref, value=value, mount="virtual",
                        template="virtual", visual=VisualSpec(kind="none", label=ref),
                        geometry=GeometryInfo(source="standard", notes=fps[iid].notes),
                        notes=["Idealised primitive or net symbol: no physical form."] if ct else ["Unknown component type."])


def _bounds(proj: PhysicalProject) -> List[float]:
    xs, ys = [], []
    if proj.board:
        L, W, _ = proj.board.size_mm
        xs += [-L / 2, L / 2]
        ys += [-W / 2, W / 2]
    for p in proj.parts:
        if p.body:
            xs += [p.body.center[0] - p.body.size[0] / 2, p.body.center[0] + p.body.size[0] / 2]
            ys += [p.body.center[1] - p.body.size[1] / 2, p.body.center[1] + p.body.size[1] / 2]
    for w in proj.wires:
        for q in w.path:
            xs.append(q[0])
            ys.append(q[1])
    return [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)] if xs else [0, 0, 0, 0]


def _end_text(end, proj: PhysicalProject) -> str:
    if end.kind == "hole":
        return str(end.hole)
    iid, pin = (end.pin_ref or ".").split(".", 1)
    p = proj.part(iid)
    return f"{p.reference if p else iid} pin {pin}"


def _assembly(proj: PhysicalProject, build: _Build, ctypes, info) -> List[AssemblyStep]:
    steps: List[AssemblyStep] = []

    def add(kind, text, **kw):
        steps.append(AssemblyStep(step=len(steps) + 1, kind=kind, text=text, **kw))

    b = proj.board
    add("board", f"Take a {b.name.lower()}. Rows a-e and f-j of each column are connected; the four long rails run along the edges.")
    for r in b.rails:
        if r.net_id:
            ni = info.get(r.net_id)
            side = "top" if r.rail_id.startswith("T") else "bottom"
            line = "red (+) line" if r.polarity == "+" else "blue (-) line"
            add("note", f"The {side} rail next to the {line} carries {ni.display_name if ni else r.net_id}.", net_id=r.net_id)
    board_parts = [p for p in proj.parts if p.mount == "breadboard"]
    board_parts.sort(key=lambda p: (PLACE_CLASS.get(p.template, 3), p.position[0]))
    for p in board_parts:
        ct = ctypes.get(p.instance_id)
        name = ct.short_name or ct.name if ct else p.component_type_id
        pins = [pin for pin in p.pins if pin.hole]
        if p.template in ("dip", "dual_row"):
            first = next((pin for pin in pins if pin.hole == p.anchor), pins[0] if pins else None)
            txt = f"Insert {p.reference} ({name}) across the centre gap, pin 1 in {p.anchor}"
            if first:
                txt += f" ({first.pin_id})"
            txt += "; the notch / pin-1 mark points toward the lower column numbers." if p.rotation == 0 else \
                "; the notch / pin-1 mark points toward the higher column numbers."
        else:
            txt = f"Insert {p.reference} ({name}" + (f", {p.value}" if p.value and p.value != name else "") + "): " + \
                  ", ".join(f"{pin.pin_id} in {pin.hole}" for pin in pins[:6]) + (" …" if len(pins) > 6 else "") + "."
        if p.geometry.variant_note:
            txt += " Check the pin order on your part."
        add("part", txt, instance_id=p.instance_id)
    for p in proj.parts:
        if p.mount == "offboard":
            ct = ctypes.get(p.instance_id)
            name = ct.short_name or ct.name if ct else p.component_type_id
            add("part", f"Place {p.reference} ({name}) beside the breadboard.", instance_id=p.instance_id)
    for w in proj.wires:
        if w.kind == "lead":
            add("lead", f"Push the {w.a.pin_ref} lead into {w.b.hole}.", wire_id=w.wire_id, net_id=w.net_id)
    for w in proj.wires:
        if w.kind != "lead":
            ni = info.get(w.net_id)
            add("wire", f"Wire {w.wire_id} ({_color_name(w.color)}): {_end_text(w.a, proj)} → {_end_text(w.b, proj)} "
                        f"[{ni.display_name if ni else w.net_id}].", wire_id=w.wire_id, net_id=w.net_id)
    return steps


def _color_name(hex_color: str) -> str:
    return {"#212121": "black", "#d32f2f": "red", "#ef6c00": "orange", "#c2185b": "magenta", "#fbc02d": "yellow",
            "#388e3c": "green", "#1e88e5": "blue", "#8e24aa": "purple", "#00acc1": "cyan", "#eeeeee": "white",
            "#6d4c41": "brown", "#546e7a": "grey"}.get(hex_color.lower(), hex_color)


def placements_from_physical(proj: PhysicalProject, previous: Optional[PhysicalLayoutState] = None) -> Dict[str, PhysicalPlacement]:
    """Resolved placements to persist, so later edits keep the build stable."""
    prev = previous.placements if previous else {}
    out: Dict[str, PhysicalPlacement] = {}
    for p in proj.parts:
        old = prev.get(p.instance_id)
        if p.mount == "breadboard":
            locked = bool(old and old.locked and old.anchor == p.anchor)
            out[p.instance_id] = PhysicalPlacement(anchor=p.anchor, orientation=p.orientation, rotation=p.rotation,
                                                   span=p.span, locked=locked, seq=old.seq if locked else 0)
        elif p.mount == "offboard":
            locked = bool(old and old.locked and old.x is not None)
            out[p.instance_id] = PhysicalPlacement(x=p.position[0], y=p.position[1], rotation=p.rotation, locked=locked,
                                                   seq=old.seq if locked else 0)
    return out
