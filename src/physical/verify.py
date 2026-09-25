"""Physical verification: does the physical build equal the engineering netlist?

Independent of the placement engine: connectivity is rebuilt from the serialised Physical IR alone
(the board's strips and rails, inserted pins, leads, jumper wires, and connections inside parts)
and compared with the engineering nets, the way schematic LVS checks the drawing.

Codes
  P001 PART_MISSING         a physical engineering part has no physical instance
  P002 PIN_UNMAPPED         a connected engineering pin has no physical contact
  P003 BAD_ENDPOINT         a pin or wire ends in a hole that does not exist on the board
  P004 HOLE_CONFLICT        two things are inserted in the same hole
  P005 SHORT                two engineering nets are joined physically
  P006 OPEN                 an engineering net is split into separate physical groups
  P007 COLLISION            two part bodies overlap
  P008 UNPLACED             a part could not be placed
  P009 COVERED_HOLE         a pin or wire is inserted in a hole covered by a part body
  P010 NC_CONNECTED         a pin that is unconnected in the design touches a net physically
  P101 GEOMETRY_ASSUMED     (warning) geometry is a stand-in, not the real part
  P102 VARIANT_PINOUT       (warning) the pinout differs between vendors - check the part in hand
  P103 SMD_ADAPTER          (warning) an SMD part needs a breakout adapter to be breadboarded
  P104 PLACEMENT_NOT_KEPT   (info) a requested placement could not be kept
  P105 NOT_PHYSICAL         (info) idealised primitives have no physical form
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from core.models import EngineeringDesignProject

from .breadboard import make_breadboard
from .models import PhysicalCheck, PhysicalFinding, PhysicalProject, PhysicalVerification
from .placement import overlaps


class _DSU:
    def __init__(self):
        self.p: Dict[str, str] = {}

    def find(self, a: str) -> str:
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def physical_connectivity(project: PhysicalProject) -> Tuple[_DSU, Set[str], Dict[str, int]]:
    """DSU over pin refs, holes and board nodes. Returns (dsu, bad_holes, hole_use_count)."""
    dsu = _DSU()
    bb = make_breadboard(project.board.kind) if project.board else None
    bad: Set[str] = set()
    uses: Dict[str, int] = defaultdict(int)

    def hole(h: str) -> str:
        key = f"hole:{h}"
        if bb is None or h not in bb.holes:
            bad.add(h)
        else:
            dsu.union(key, f"node:{bb.holes[h].node}")
        return key

    for part in project.parts:
        for pin in part.pins:
            ref = f"{part.instance_id}.{pin.pin_id}"
            dsu.find(ref)
            if pin.alias_of:
                dsu.union(ref, f"{part.instance_id}.{pin.alias_of}")
            if pin.hole:
                uses[pin.hole] += 1
                dsu.union(ref, hole(pin.hole))
        for group in part.internal_links:
            refs = [f"{part.instance_id}.{p}" for p in group if any(pp.pin_id == p for pp in part.pins)]
            for r in refs[1:]:
                dsu.union(refs[0], r)
    for w in project.wires:
        keys = []
        for end in (w.a, w.b):
            if end.kind == "hole" and end.hole:
                uses[end.hole] += 1
                keys.append(hole(end.hole))
            elif end.pin_ref:
                keys.append(end.pin_ref)
        if len(keys) == 2:
            dsu.union(keys[0], keys[1])
    return dsu, bad, uses


def verify_physical(project: PhysicalProject, design: EngineeringDesignProject) -> PhysicalVerification:
    findings: List[PhysicalFinding] = []
    checks: List[PhysicalCheck] = []

    def check(code: str, name: str, found: List[PhysicalFinding], warn: bool = False) -> None:
        findings.extend(found)
        checks.append(PhysicalCheck(code=code, name=name, outcome=("WARN" if warn else "FAIL") if found else "PASS"))

    if not project.applicable:
        return PhysicalVerification(status="NOT_APPLICABLE", ok=True,
                                    summary="This design uses only idealised primitives; it has no physical form to build.",
                                    findings=[PhysicalFinding(code="P105", severity="INFO",
                                                              message="Idealised primitives (ideal sources, ideal transistors, logic gates) have no physical form.")],
                                    checks=[])

    parts = {p.instance_id: p for p in project.parts}
    virtual = {p.instance_id for p in project.parts if p.mount == "virtual"}

    # P001 / P008
    missing = [c.instance_id for c in design.components if c.instance_id not in parts]
    check("P001", "every engineering part has a physical instance",
          [PhysicalFinding(code="P001", severity="ERROR", instances=[i], message=f"{i} is missing from the physical build.") for i in missing])
    unplaced = [p for p in project.parts if p.mount == "unplaced"]
    check("P008", "every part is placed",
          [PhysicalFinding(code="P008", severity="ERROR", instances=[p.instance_id],
                           message=f"{p.instance_id} could not be placed" + (f": {p.notes[0]}" if p.notes else "."))
           for p in unplaced])

    # engineering pin -> net
    eng_net: Dict[str, str] = {}
    for net in design.nets:
        for pr in net.connections:
            if pr.instance_id not in virtual:
                eng_net[pr.ref] = net.net_id

    # P002 connected pins need a physical contact
    contact: Set[str] = set()
    for p in project.parts:
        for pin in p.pins:
            if pin.hole or pin.terminal or pin.alias_of:
                contact.add(f"{p.instance_id}.{pin.pin_id}")
    unmapped = [ref for ref in sorted(eng_net) if ref.split(".")[0] in parts
                and parts[ref.split(".")[0]].mount not in ("unplaced",) and ref not in contact]
    check("P002", "every connected engineering pin has a physical contact",
          [PhysicalFinding(code="P002", severity="ERROR", pins=[r], instances=[r.split(".")[0]], nets=[eng_net[r]],
                           message=f"{r} is connected to {eng_net[r]} in the design but has no physical pin position on this part.")
           for r in unmapped])

    dsu, bad, uses = physical_connectivity(project)

    # P003 / P004 / P009
    check("P003", "every pin and wire ends in a real hole",
          [PhysicalFinding(code="P003", severity="ERROR", holes=[h], message=f"Hole {h} does not exist on this board.") for h in sorted(bad)])
    check("P004", "no hole is used twice",
          [PhysicalFinding(code="P004", severity="ERROR", holes=[h], message=f"Hole {h} holds {n} leads/wires; one hole takes one.")
           for h, n in sorted(uses.items()) if n > 1])
    covered = set(project.covered)
    check("P009", "nothing is inserted under a part body",
          [PhysicalFinding(code="P009", severity="ERROR", holes=[h], message=f"Hole {h} is under a part body but something is inserted in it.")
           for h in sorted(uses) if h in covered])

    # P005 / P006 / P010 connectivity against the netlist
    group_nets: Dict[str, Set[str]] = defaultdict(set)
    net_groups: Dict[str, Set[str]] = defaultdict(set)
    for ref, net in eng_net.items():
        if ref in contact:
            root = dsu.find(ref)
            group_nets[root].add(net)
            net_groups[net].add(root)
    shorts = []
    for root, nets in sorted(group_nets.items(), key=lambda t: sorted(t[1])):
        if len(nets) > 1:
            ns = sorted(nets)
            shorts.append(PhysicalFinding(code="P005", severity="ERROR", nets=ns,
                                          message=f"Nets {', '.join(ns)} are connected to each other on the breadboard (a short)."))
    check("P005", "no two nets are joined physically", shorts)
    opens = []
    for net, roots in sorted(net_groups.items()):
        if len(roots) > 1:
            pins_by = defaultdict(list)
            for ref, n in eng_net.items():
                if n == net and ref in contact:
                    pins_by[dsu.find(ref)].append(ref)
            parts_txt = " | ".join(", ".join(sorted(v)) for v in sorted(pins_by.values()))
            opens.append(PhysicalFinding(code="P006", severity="ERROR", nets=[net],
                                         message=f"Net {net} is split into {len(roots)} separate groups on the breadboard: {parts_txt}."))
    check("P006", "every net is one connected group", opens)
    stray = []
    net_root = {net: next(iter(roots)) for net, roots in net_groups.items() if len(roots) == 1}
    root_net = {r: n for n, r in net_root.items()}
    for p in project.parts:
        linked = {x for g in p.internal_links for x in g}       # tied inside the part: same node by design
        for pin in p.pins:
            ref = f"{p.instance_id}.{pin.pin_id}"
            if ref in eng_net or ref not in contact or pin.alias_of or pin.pin_id in linked:
                continue
            r = dsu.find(ref)
            if r in root_net:
                stray.append(PhysicalFinding(code="P010", severity="ERROR", pins=[ref], nets=[root_net[r]], instances=[p.instance_id],
                                             message=f"{ref} is unconnected in the design but touches net {root_net[r]} on the breadboard."))
    check("P010", "unconnected pins stay unconnected", stray)

    # P007 collisions (plan view)
    rects = [(p.instance_id, (p.body.center[0] - p.body.size[0] / 2, p.body.center[1] - p.body.size[1] / 2,
                              p.body.center[0] + p.body.size[0] / 2, p.body.center[1] + p.body.size[1] / 2))
             for p in project.parts if p.body and p.mount in ("breadboard", "offboard")]
    coll = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if overlaps(rects[i][1], rects[j][1]):
                coll.append(PhysicalFinding(code="P007", severity="ERROR", instances=[rects[i][0], rects[j][0]],
                                            message=f"{rects[i][0]} and {rects[j][0]} overlap."))
    check("P007", "no two part bodies overlap", coll)

    # warnings / infos
    assumed = [PhysicalFinding(code="P101", severity="WARNING", instances=[p.instance_id],
                               message=f"{p.instance_id} ({p.component_type_id}) is shown with stand-in geometry: "
                                       + (p.geometry.notes[0] if p.geometry.notes else "no physical data in the library."))
               for p in project.parts if p.geometry.source == "assumed" and p.mount != "virtual"]
    check("P101", "geometry comes from real data", assumed, warn=True)
    variants = [PhysicalFinding(code="P102", severity="WARNING", instances=[p.instance_id], message=f"{p.instance_id}: {p.geometry.variant_note}")
                for p in project.parts if p.geometry.variant_note and p.mount != "virtual"]
    check("P102", "pinouts are vendor-independent", variants, warn=True)
    smd = [PhysicalFinding(code="P103", severity="WARNING", instances=[p.instance_id],
                           message=f"{p.instance_id} is an SMD part; it needs a breakout adapter (shown) to go on a breadboard.")
           for p in project.parts if p.template == "smd_adapter"]
    check("P103", "all parts are breadboard-insertable", smd, warn=True)
    kept = [PhysicalFinding(code="P104", severity="INFO", instances=[p.instance_id], message=n)
            for p in project.parts for n in p.notes if n.startswith("Requested placement")]
    findings.extend(kept)
    if virtual:
        findings.append(PhysicalFinding(code="P105", severity="INFO", instances=sorted(virtual),
                                        message=f"{', '.join(sorted(virtual))} are idealised primitives or net symbols and have no physical form."))

    errors = [f for f in findings if f.severity == "ERROR"]
    warns = [f for f in findings if f.severity == "WARNING"]
    status = "FAIL" if errors else ("WARN" if warns else "PASS")
    if errors:
        summary = f"The physical build does NOT match the design: {len(errors)} problem(s)."
    elif warns:
        summary = "The physical build matches the netlist; some geometry needs checking against the real parts."
    else:
        summary = "The physical build matches the netlist exactly."
    return PhysicalVerification(status=status, ok=not errors, summary=summary, findings=findings, checks=checks)
