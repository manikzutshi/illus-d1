"""Engineering Design  →  Schematic projection (deterministic, no AI).

    schematic = generate_schematic(design, registry, layout_state)

Pipeline: net classification → symbol resolution → placement → power ports / net labels →
wire routing (label fallback) → segments & junctions → reference designators, values and
traceability index. The same input always yields byte-identical output.
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple

from components.registry import ComponentRegistry, get_shared_registry
from core.enums import PinDirection
from core.models import EngineeringDesignProject
from core.units import format_quantity, parse_quantity

from .geometry import VEC, bbox_inflate, bbox_union, transform_bbox, transform_ipoint, transform_orientation
from .models import (LayoutState, LayoutStats, NetTrace, Placement, SchematicComponentInstance, SchematicJunction,
                     SchematicNetLabel, SchematicPin, SchematicPowerPort, SchematicProject, SchematicTextAnnotation,
                     SchematicWire, SymbolDef)
from .netclass import NetInfo, classify_nets
from .placement import Context, Part, PlacementEngine, footprint, label_items, pin_world, port_extent, role_sign, symbol_bbox_local, text_box
from .routing import GridRouter, Terminal, edges_to_segments
from .symbols import build_box_symbol, get_fixed_symbol, pin_mapping, ref_prefix, symbol_name_for

ENGINE_VERSION = "schematic-layout/1.0"

_VALUE_PARAMS = (("resistance", "Ω", "ohm"), ("capacitance", "F", "F"), ("inductance", "H", "H"), ("voltage", "V", "V"))


# ── port / label geometry (shared with verification and renderers) ─────────

def label_extent(x: int, y: int, direction: str, text: str) -> Tuple[float, float, float, float]:
    length = 0.62 * max(len(text), 1) + 1.2
    vx, vy = VEC[direction]
    if vx:
        x2 = x + vx * length
        return (min(x, x2), y - 0.7, max(x, x2), y + 0.7)
    y2 = y + vy * length
    return (x - 0.7, min(y, y2), x + 0.7, max(y, y2))


def _points_in(box: Tuple[float, float, float, float], exclude: Tuple[int, int]) -> List[Tuple[int, int]]:
    import math
    out = []
    for px in range(math.ceil(box[0]), math.floor(box[2]) + 1):
        for py in range(math.ceil(box[1]), math.floor(box[3]) + 1):
            if (px, py) != exclude:
                out.append((px, py))
    return out


# ── helpers ────────────────────────────────────────────────────────────────

def _value_text(comp, ctype) -> str:
    for key, unit, parse_unit in _VALUE_PARAMS:
        if key in comp.parameters:
            v = parse_quantity(comp.parameters[key], parse_unit)
            return format_quantity(v, unit) if v is not None else str(comp.parameters[key])
    if ctype is None:
        return comp.component_type
    if "color" in comp.parameters and (ctype.family or "") in ("led",):
        return f"{comp.parameters['color']} LED"
    return ctype.short_name or ctype.name


def _assign_references(design: EngineeringDesignProject, prefixes: Dict[str, str]) -> Dict[str, str]:
    refs: Dict[str, str] = {}
    used: set[str] = set()
    for comp in design.components:
        pre = prefixes.get(comp.instance_id)
        if pre is None or pre.startswith("#"):
            continue
        m = re.fullmatch(rf"{re.escape(pre)}(\d+)", comp.instance_id, flags=re.IGNORECASE)
        if m and f"{pre}{int(m.group(1))}" not in used:
            refs[comp.instance_id] = f"{pre}{int(m.group(1))}"
            used.add(refs[comp.instance_id])
    counters: Dict[str, int] = {}
    for comp in design.components:
        iid = comp.instance_id
        if iid in refs or iid not in prefixes:
            continue
        pre = prefixes[iid]
        if pre.startswith("#"):
            refs[iid] = iid
            continue
        n = counters.get(pre, 0)
        while True:
            n += 1
            if f"{pre}{n}" not in used:
                break
        counters[pre] = n
        refs[iid] = f"{pre}{n}"
        used.add(refs[iid])
    return refs


# ── main entry point ───────────────────────────────────────────────────────

def generate_schematic(design: EngineeringDesignProject, registry: Optional[ComponentRegistry] = None,
                       layout: Optional[LayoutState] = None) -> SchematicProject:
    t_start = time.perf_counter()
    registry = registry or get_shared_registry()
    layout = layout or LayoutState()
    diagnostics: List[str] = []
    infos: Dict[str, NetInfo] = classify_nets(design, registry)

    pin_net: Dict[Tuple[str, str], str] = {}
    for net in design.nets:
        for pr in net.connections:
            pin_net.setdefault((pr.instance_id, pr.pin_id), net.net_id)

    # 1. symbol resolution ------------------------------------------------
    parts: Dict[str, Part] = {}
    comp_by_id = {}
    for comp in design.components:
        if comp.instance_id in parts:
            diagnostics.append(f"duplicate instance id '{comp.instance_id}' drawn once")
            continue
        comp_by_id[comp.instance_id] = comp
        ctype = registry.get(comp.component_type)
        if ctype is None:
            pins = sorted({pr.pin_id for net in design.nets for pr in net.connections if pr.instance_id == comp.instance_id})
            eng_pins = [(p, p, PinDirection.PASSIVE, None) for p in pins]
            diagnostics.append(f"{comp.instance_id}: unknown component type '{comp.component_type}' drawn as a generic box")
        else:
            eng_pins = [(p.pin_id, p.name, p.direction, p.number) for p in ctype.pins]
        sname = symbol_name_for(ctype)
        symbol, pmap = None, {}
        if sname != "ic_box":
            symbol = get_fixed_symbol(sname)
            try:
                pmap = pin_mapping(ctype, symbol)
                for sp in symbol.pins:
                    if sp.name not in pmap.values():
                        sp.hidden = True   # optional symbol pins the part does not have
            except ValueError as e:
                diagnostics.append(f"{comp.instance_id}: {e}; using a generic box")
                sname, symbol, pmap = "ic_box", None, {}
        pl = layout.placements.get(comp.instance_id)
        parts[comp.instance_id] = Part(
            iid=comp.instance_id, ctype=ctype, symbol_name=sname, symbol=symbol, pin_map=pmap, eng_pins=eng_pins,
            is_box=sname == "ic_box", is_flag=bool(symbol and symbol.kind in ("power_flag", "ground_flag")),
            show_all_pins=bool(pl and pl.show_all_pins),
        )

    prefixes = {iid: ref_prefix(p.ctype, p.symbol_name) for iid, p in parts.items()}
    refs = _assign_references(design, prefixes)
    for iid, part in parts.items():
        part.reference = refs.get(iid, iid)
        part.value = _value_text(comp_by_id[iid], part.ctype)
        if part.is_flag:
            nets_of = [n for (i, _), n in pin_net.items() if i == iid]
            part.port_text = infos[nets_of[0]].display_name if nets_of else part.value
        else:
            for pid, *_ in part.eng_pins:
                info = infos.get(pin_net.get((iid, pid), ""))
                if info is not None and info.net_class != "signal":
                    part.port_pins[pid] = ("ground" if info.net_class == "ground" else "power", info.display_name)

    def build_box(part: Part, sides: Dict[str, List[str]]) -> None:
        names = {pid: (pid, pid, num) for pid, _n, _d, num in part.eng_pins}
        spec = {side: [names[p] for p in pins] for side, pins in sides.items()}
        part.symbol = build_box_symbol(f"box:{part.iid}", spec, title=part.value,
                                       hidden_count=len(part.hidden_pins))
        part.pin_map = {pid: pid for pins in sides.values() for pid in pins}
        part.fp_cache.clear()

    styles = layout.net_styles
    signal_nets: Dict[str, List[Tuple[str, str]]] = {}
    for net in design.nets:
        if infos[net.net_id].net_class != "signal":
            continue
        members = [(pr.instance_id, pr.pin_id) for pr in net.connections if pr.instance_id in parts]
        if len(members) >= 2 and styles.get(net.net_id, "auto") != "label":
            signal_nets[net.net_id] = members

    def role_side(iid: str, pin_id: str) -> float:
        net = pin_net.get((iid, pin_id))
        total = 0.0
        frontier = [(o, op) for (o, op) in signal_nets.get(net, []) if o != iid]
        visited = {iid}
        for _depth in range(3):
            nxt = []
            for oi, op in frontier:
                if oi in visited:
                    continue
                visited.add(oi)
                other = parts[oi]
                if len(other.eng_pins) == 2 and not other.is_box and other.ctype is not None and \
                        all(d == PinDirection.PASSIVE for _, _, d, _ in other.eng_pins):
                    far = [p for p, *_ in other.eng_pins if p != op]
                    far_net = pin_net.get((oi, far[0])) if far else None
                    nxt += [(o2, p2) for (o2, p2) in signal_nets.get(far_net, []) if o2 not in visited]
                    continue
                total += role_sign(other.ctype)
                pdir = next((d for p, _, d, _ in other.eng_pins if p == op), None)
                if pdir == PinDirection.OUTPUT:
                    total -= 0.5
                elif pdir == PinDirection.INPUT:
                    total += 0.5
            frontier = nxt
        return total

    # 2. placement ----------------------------------------------------------
    ctx = Context(parts=parts, pin_net=pin_net, net_class={k: v.net_class for k, v in infos.items()},
                  signal_nets=signal_nets)
    fixed = {iid: pl for iid, pl in layout.placements.items() if iid in parts}
    poses = PlacementEngine(ctx, fixed, build_box, role_side).run()

    # 3. placed component instances ----------------------------------------
    symbols: Dict[str, SymbolDef] = {}
    instances: List[SchematicComponentInstance] = []
    for comp in design.components:
        iid = comp.instance_id
        if iid not in parts or any(c.instance_id == iid for c in instances):
            continue
        part = parts[iid]
        pose = poses[iid]
        x, y, rot, mir = pose
        symbols[part.symbol.symbol_id] = part.symbol
        spins: List[SchematicPin] = []
        for pid, pname, _d, _num in part.eng_pins:
            sp = part.sym_pin(pid)
            if sp is None:
                spins.append(SchematicPin(pin_id=pid, symbol_pin="", name=pname, x=x, y=y, orientation="left",
                                          net_id=pin_net.get((iid, pid)), hidden=True))
                continue
            (px, py), orient = pin_world(part, pid, pose)
            spins.append(SchematicPin(pin_id=pid, symbol_pin=sp.name, name=pname, x=px, y=py, orientation=orient,
                                      net_id=pin_net.get((iid, pid))))
        ref_t, val_t = label_items(part, pose)
        bb = transform_bbox(symbol_bbox_local(part.symbol), x, y, rot, mir)
        pl = layout.placements.get(iid)
        instances.append(SchematicComponentInstance(
            instance_id=iid, component_type_id=comp.component_type, reference=part.reference, value=part.value,
            symbol_id=part.symbol.symbol_id, x=x, y=y, rotation=rot, mirror=mir, locked=bool(pl and pl.locked),
            pins=spins, bbox=[round(v, 3) for v in bb], ref_label=ref_t, value_label=val_t,
            port_text=part.port_text or None, metadata=dict(comp.metadata),
        ))

    # 4. router setup ---------------------------------------------------------
    occupied = [footprint(parts[c.instance_id], poses[c.instance_id]) for c in instances]
    ports: List[SchematicPowerPort] = []
    port_boxes = []
    for inst in instances:
        part = parts[inst.instance_id]
        if part.is_flag:
            continue
        for sp in inst.pins:
            if sp.hidden or sp.net_id is None:
                continue
            info = infos.get(sp.net_id)
            if info is None or info.net_class == "signal":
                continue
            port = SchematicPowerPort(port_id=f"port:{inst.instance_id}.{sp.pin_id}", net_id=sp.net_id,
                                      kind="ground" if info.net_class == "ground" else "power",
                                      text=info.display_name, x=sp.x, y=sp.y, direction=sp.orientation,
                                      pin_ref=f"{inst.instance_id}.{sp.pin_id}")
            ports.append(port)
            port_boxes.append(port_extent(port.x, port.y, port.direction, port.kind, port.text))

    extent = bbox_union(occupied + port_boxes) if (occupied or port_boxes) else (0, 0, 10, 10)
    margin = 8
    router = GridRouter((int(extent[0]) - margin, int(extent[1]) - margin, int(extent[2]) + margin, int(extent[3]) + margin))
    for inst in instances:
        part = parts[inst.instance_id]
        b = transform_bbox(tuple(part.symbol.body), inst.x, inst.y, inst.rotation, inst.mirror)
        router.block_rect(*b)
        for sp in inst.pins:
            if sp.hidden:
                continue
            owner = sp.net_id or f"__nc__{inst.instance_id}.{sp.pin_id}"
            router.reserve_node((sp.x, sp.y), owner)
            sym_pin = part.sym_pin(sp.pin_id)
            vx, vy = VEC[sp.orientation]
            for k in range(1, int(sym_pin.length) + 1):
                router.block([(sp.x - vx * k, sp.y - vy * k)])
        for t in (inst.ref_label, inst.value_label):
            if t is not None:
                # Wires must never run through text: block the text box (tips stay reachable).
                tips = {(sp.x, sp.y) for sp in inst.pins}
                router.block([pt for pt in _points_in(text_box(t), (10**9, 10**9)) if pt not in tips])
    for port, box in zip(ports, port_boxes):
        router.block(_points_in(box, (port.x, port.y)))

    # 5. routing -------------------------------------------------------------
    pin_lookup = {(i.instance_id, p.pin_id): p for i in instances for p in i.pins}
    net_labels: List[SchematicNetLabel] = []
    label_nets: List[str] = []
    for net in design.nets:
        info = infos[net.net_id]
        if info.net_class != "signal":
            continue
        drawable = [pin_lookup[(pr.instance_id, pr.pin_id)] for pr in net.connections
                    if (pr.instance_id, pr.pin_id) in pin_lookup and not pin_lookup[(pr.instance_id, pr.pin_id)].hidden]
        forced = styles.get(net.net_id, "auto") == "label"
        if forced or len(drawable) < 2:
            label_nets.append(net.net_id)

    def add_labels(net_id: str) -> None:
        net = next(n for n in design.nets if n.net_id == net_id)
        for pr in net.connections:
            sp = pin_lookup.get((pr.instance_id, pr.pin_id))
            if sp is None or sp.hidden:
                continue
            lab = SchematicNetLabel(label_id=f"label:{pr.instance_id}.{pr.pin_id}", net_id=net_id,
                                    text=infos[net_id].display_name, x=sp.x, y=sp.y, direction=sp.orientation,
                                    pin_ref=f"{pr.instance_id}.{pr.pin_id}")
            net_labels.append(lab)
            router.block(_points_in(label_extent(lab.x, lab.y, lab.direction, lab.text), (lab.x, lab.y)))

    for nid in label_nets:
        add_labels(nid)

    def net_order(nid: str):
        pts = [(pin_lookup[m].x, pin_lookup[m].y) for m in signal_nets[nid] if m in pin_lookup]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (len(pts), (max(xs) - min(xs)) + (max(ys) - min(ys)), nid)

    routed_edges: Dict[str, list] = {}
    fallback: List[str] = []
    for nid in sorted((n for n in signal_nets if n not in label_nets), key=net_order):
        terms = [Terminal((pin_lookup[m].x, pin_lookup[m].y), pin_lookup[m].orientation, f"{m[0]}.{m[1]}")
                 for m in signal_nets[nid] if m in pin_lookup and not pin_lookup[m].hidden]
        result = router.route_net(nid, terms)
        if result.ok:
            router.commit(result, [t.point for t in terms])
            routed_edges[nid] = result.edges
        else:
            fallback.append(nid)
            diagnostics.append(f"net '{nid}' drawn with net labels ({result.reason})")
            add_labels(nid)

    # 6. segments & junctions ---------------------------------------------------
    wires: List[SchematicWire] = []
    junctions: List[SchematicJunction] = []
    bends = 0
    length = 0
    for nid in sorted(routed_edges):
        tips = {(pin_lookup[m].x, pin_lookup[m].y) for m in signal_nets[nid] if m in pin_lookup}
        segs = edges_to_segments(routed_edges[nid], tips)
        for k, (a, b) in enumerate(segs):
            wires.append(SchematicWire(wire_id=f"w:{nid}:{k}", net_id=nid, x1=a[0], y1=a[1], x2=b[0], y2=b[1]))
            length += abs(a[0] - b[0]) + abs(a[1] - b[1])
        degree: Dict[Tuple[int, int], int] = {}
        axes: Dict[Tuple[int, int], set] = {}
        for a, b in segs:
            for p in (a, b):
                degree[p] = degree.get(p, 0) + 1
                axes.setdefault(p, set()).add("h" if a[1] == b[1] else "v")
        for t in tips:
            degree[t] = degree.get(t, 0) + 1
        for p in sorted(degree):
            if degree[p] >= 3:
                junctions.append(SchematicJunction(junction_id=f"j:{nid}:{p[0]}_{p[1]}", net_id=nid, x=p[0], y=p[1]))
            elif degree[p] == 2 and len(axes.get(p, ())) == 2:
                bends += 1

    crossings = 0
    for p, owners_h in router.pass_h.items():
        owners_v = router.pass_v.get(p, set())
        if owners_v and any(a != b for a in owners_h for b in owners_v):
            crossings += 1

    # 7. traceability ------------------------------------------------------------
    traces: Dict[str, NetTrace] = {}
    for net in design.nets:
        info = infos[net.net_id]
        style = "port" if info.net_class != "signal" else ("label" if net.net_id in label_nets or net.net_id in fallback else "wire")
        traces[net.net_id] = NetTrace(
            net_id=net.net_id, display_name=info.display_name, net_class=info.net_class, style=style,
            pins=[pr.ref for pr in net.connections], voltage=info.voltage,
            wires=[w.wire_id for w in wires if w.net_id == net.net_id],
            junctions=[j.junction_id for j in junctions if j.net_id == net.net_id],
            ports=[p.port_id for p in ports if p.net_id == net.net_id]
                  + [f"flag:{i.instance_id}" for i in instances if i.port_text and any(sp.net_id == net.net_id for sp in i.pins)],
            labels=[l.label_id for l in net_labels if l.net_id == net.net_id],
        )

    # 8. bounds & annotations ------------------------------------------------------
    boxes = occupied + port_boxes + [label_extent(l.x, l.y, l.direction, l.text) for l in net_labels]
    boxes += [(min(w.x1, w.x2), min(w.y1, w.y2), max(w.x1, w.x2), max(w.y1, w.y2)) for w in wires]
    bounds = bbox_inflate(bbox_union(boxes), 4) if boxes else (0, 0, 40, 30)
    title = SchematicTextAnnotation(annotation_id="title", x=bounds[0], y=bounds[1] - 1.0, text=design.name, size=1.6)
    bounds = (bounds[0], bounds[1] - 3.0, bounds[2], bounds[3])

    return SchematicProject(
        project_id=design.project_id, name=design.name, description=design.description,
        engineering_design_reference=design.project_id, components=instances, wires=wires, junctions=junctions,
        power_ports=ports, net_labels=net_labels, text_annotations=[title], symbols=dict(sorted(symbols.items())),
        nets=traces, bounds=[round(v, 3) for v in bounds],
        stats=LayoutStats(wire_length=length, bends=bends, crossings=crossings, label_fallback_nets=sorted(fallback),
                          elapsed_ms=round((time.perf_counter() - t_start) * 1000, 1)),
        diagnostics=diagnostics,
        metadata={"engine": ENGINE_VERSION, **{k: v for k, v in design.metadata.items() if isinstance(v, str)}},
    )


def placements_from_schematic(schematic: SchematicProject, previous: Optional[LayoutState] = None) -> Dict[str, Placement]:
    """Placements to persist so the next projection is stable (locked flags are preserved)."""
    prev = previous.placements if previous else {}
    out = {}
    for c in schematic.components:
        p = prev.get(c.instance_id)
        out[c.instance_id] = Placement(x=c.x, y=c.y, rotation=c.rotation, mirror=c.mirror,
                                       locked=bool(p and p.locked), show_all_pins=bool(p and p.show_all_pins))
    return out
