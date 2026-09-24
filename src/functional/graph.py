"""Signal-flow graph of an engineering design.

Nodes
  net:<id>   a *signal* net (power and ground rails are never traversed)
  q:<iid>    a quantity entering the circuit at a sensor / input part
  a:<iid>    the activation of an output part (LED lit, buzzer sounding, motor running...)
Edges carry a sign: +1 (the destination rises with the source), -1 (falls), 0 (encoded,
programmable or unknown). The sign of a path is the product of its edge signs; any 0 makes
the path's polarity *not checkable* (unless a microcontroller logic rule defines it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from components.registry import ComponentRegistry
from core.models import EngineeringDesignProject
from schematic.netclass import classify_nets

from .profiles import FunctionalProfile, profile_for


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    sign: int
    instance: str
    kind: str                    # sense | adjust | transfer | switch | passive | programmable | load | control | connector
    pins: Tuple[str, ...] = ()


@dataclass
class StaticLoad:
    instance: str
    state: str                   # always_on | never_on | unconnected


@dataclass
class FunctionGraph:
    edges: Dict[str, List[Edge]] = field(default_factory=dict)
    reverse: Dict[str, List[Edge]] = field(default_factory=dict)
    profiles: Dict[str, FunctionalProfile] = field(default_factory=dict)
    net_of: Dict[Tuple[str, str], str] = field(default_factory=dict)
    net_class: Dict[str, str] = field(default_factory=dict)
    sources: Dict[str, List[str]] = field(default_factory=dict)      # q node -> quantities
    sinks: Dict[str, List[str]] = field(default_factory=dict)        # a node -> quantities
    generators: Dict[str, str] = field(default_factory=dict)         # g node -> kind (timer | controller)
    static_loads: Dict[str, StaticLoad] = field(default_factory=dict)
    net_voltage: Dict[str, Optional[float]] = field(default_factory=dict)

    def add(self, e: Edge) -> None:
        if e.src == e.dst:
            return
        self.edges.setdefault(e.src, []).append(e)
        self.reverse.setdefault(e.dst, []).append(e)

    def is_rail(self, net: Optional[str]) -> bool:
        return net is not None and self.net_class.get(net) in ("power", "ground")

    def node(self, net: Optional[str]) -> Optional[str]:
        return None if net is None or self.is_rail(net) else f"net:{net}"


def build_graph(design: EngineeringDesignProject, registry: ComponentRegistry) -> FunctionGraph:
    g = FunctionGraph()
    infos = classify_nets(design, registry)
    g.net_class = {k: v.net_class for k, v in infos.items()}
    g.net_voltage = {k: v.voltage for k, v in infos.items()}
    for net in design.nets:
        for pr in net.connections:
            g.net_of.setdefault((pr.instance_id, pr.pin_id), net.net_id)

    for comp in design.components:
        iid = comp.instance_id
        ctype = registry.get(comp.component_type)
        prof = profile_for(ctype)
        g.profiles[iid] = prof
        net = lambda pin: g.net_of.get((iid, pin))

        if prof.kind in ("sensor",) or (prof.kind == "connector" and prof.quantities):
            q = f"q:{iid}"
            g.sources[q] = list(prof.quantities)
        if prof.kind == "sensor":
            for pin, sign in prof.outputs.items():
                n = g.node(net(pin))
                if n:
                    g.add(Edge(f"q:{iid}", n, sign, iid, "sense", (pin,)))

        elif prof.kind == "resistive_sensor":
            g.sources[f"q:{iid}"] = list(prof.quantities)
            sides = prof.terminals or [[p.pin_id] for p in (ctype.pins if ctype else [])]
            side_nets = [next((net(p) for p in side if net(p)), None) for side in sides[:2]]
            rs = prof.effective_resistance_sign(comp)
            if len(side_nets) == 2:
                a, b = side_nets
                for this, other in ((a, b), (b, a)):
                    n = g.node(this)
                    if not n:
                        continue
                    if g.is_rail(other):
                        # divider position decides polarity: sensor to supply = "top" element
                        top = g.net_class[other] == "power"
                        sign = 0 if rs is None else (-rs if top else rs)
                        g.add(Edge(f"q:{iid}", n, sign, iid, "sense", tuple(sides[0] + sides[1])))
                    else:
                        g.add(Edge(f"q:{iid}", n, 0, iid, "sense", ()))
                if g.node(a) and g.node(b):
                    g.add(Edge(g.node(a), g.node(b), 1, iid, "passive"))
                    g.add(Edge(g.node(b), g.node(a), 1, iid, "passive"))

        elif prof.kind == "adjustable":
            g.sources[f"q:{iid}"] = list(prof.quantities)
            for pin, sign in prof.outputs.items():
                n = g.node(net(pin))
                if n:
                    g.add(Edge(f"q:{iid}", n, sign, iid, "adjust", (pin,)))
            ends = [g.node(net(p)) for p in prof.terminals_ends]
            wiper = g.node(net(next(iter(prof.outputs), "")))
            for e in ends:                       # used as a variable resistor between signal nets
                if e and wiper:
                    g.add(Edge(e, wiper, 1, iid, "passive"))
                    g.add(Edge(wiper, e, 1, iid, "passive"))

        elif prof.kind in ("actuator", "display", "memory") or (prof.kind == "connector" and prof.quantities):
            a = f"a:{iid}"
            g.sinks[a] = list(prof.quantities)
            driven = False
            for pair in prof.loads:
                p_net, n_net = net(pair[0]), net(pair[1])
                pn, nn = g.node(p_net), g.node(n_net)
                if pn:
                    sign = 1 if (prof.polarized or not g.is_rail(n_net) or g.net_class.get(n_net) == "ground") else -1
                    g.add(Edge(pn, a, sign, iid, "load", tuple(pair)))
                    driven = True
                if nn:
                    sign = -1 if (prof.polarized or not g.is_rail(p_net) or g.net_class.get(p_net) == "power") else 1
                    g.add(Edge(nn, a, sign, iid, "load", tuple(pair)))
                    driven = True
                if not pn and not nn:
                    if p_net is None or n_net is None:
                        state = "unconnected"
                    else:
                        cp, cn = g.net_class.get(p_net), g.net_class.get(n_net)
                        on = (cp == "power" and cn == "ground") or (not prof.polarized and cp == "ground" and cn == "power")
                        state = "always_on" if on else "never_on"
                    if iid not in g.static_loads or state == "always_on":
                        g.static_loads[iid] = StaticLoad(iid, state)
            for pin, sign in prof.controls.items():
                n = g.node(net(pin))
                if n:
                    g.add(Edge(n, a, sign, iid, "control", (pin,)))
                    driven = True
            if prof.kind == "connector":
                for p in (ctype.pins if ctype else []):
                    n = g.node(net(p.pin_id))
                    if n:
                        g.add(Edge(f"q:{iid}", n, 1, iid, "connector", (p.pin_id,)))
                        g.add(Edge(n, a, 1, iid, "connector", (p.pin_id,)))
            if driven:
                g.static_loads.pop(iid, None)

        elif prof.kind == "passive":
            pins = [p.pin_id for p in (ctype.pins if ctype else [])]
            nets = [g.node(net(p)) for p in pins]
            if len(nets) == 2 and nets[0] and nets[1]:
                g.add(Edge(nets[0], nets[1], 1, iid, "passive", tuple(pins)))
                g.add(Edge(nets[1], nets[0], 1, iid, "passive", tuple(pins)))

        if prof.transfers:
            kind = "switch" if prof.kind in ("switch", "driver") else "transfer"
            for src_pin, dst_pin, sign in prof.transfers:
                s, d = g.node(net(src_pin)), g.node(net(dst_pin))
                if s and d:
                    g.add(Edge(s, d, int(sign), iid, kind, (src_pin, dst_pin)))

        for pin in prof.generator_pins:
            n = g.node(net(pin))
            if n:
                g.generators[f"g:{iid}"] = prof.kind
                g.add(Edge(f"g:{iid}", n, 0, iid, "generate", (pin,)))

        if prof.programmable and ctype is not None:
            ios = [p.pin_id for p in ctype.pins if p.direction.value in ("INPUT", "OUTPUT", "BIDIRECTIONAL")]
            nodes = [(p, g.node(net(p))) for p in ios if g.node(net(p))]
            if nodes:
                g.generators[f"g:{iid}"] = "controller"
                for p, n in nodes:
                    g.add(Edge(f"g:{iid}", n, 0, iid, "generate", (p,)))
            for pi, ni in nodes:
                for po, no in nodes:
                    if ni != no:
                        g.add(Edge(ni, no, 0, iid, "programmable", (pi, po)))
    return g


def reachable(g: FunctionGraph, start: str, reverse: bool = False, limit_kinds: Optional[Set[str]] = None) -> Set[str]:
    seen = {start}
    stack = [start]
    table = g.reverse if reverse else g.edges
    while stack:
        cur = stack.pop()
        for e in table.get(cur, []):
            nxt = e.src if reverse else e.dst
            if limit_kinds and e.kind not in limit_kinds:
                continue
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def find_paths(g: FunctionGraph, src: str, dst: str, max_paths: int = 300, max_depth: int = 40) -> List[List[Edge]]:
    """Simple paths from src to dst (deterministic order)."""
    paths: List[List[Edge]] = []
    can_reach_dst = reachable(g, dst, reverse=True)
    if src not in can_reach_dst:
        return []

    def dfs(node: str, path: List[Edge], visited: Set[str]) -> None:
        if len(paths) >= max_paths or len(path) > max_depth:
            return
        for e in sorted(g.edges.get(node, []), key=lambda e: (e.dst, e.instance, e.pins)):
            if e.dst in visited or e.dst not in can_reach_dst:
                continue
            if e.dst == dst:
                paths.append(path + [e])
                continue
            if e.dst.startswith(("a:", "q:", "g:")):
                continue
            visited.add(e.dst)
            dfs(e.dst, path + [e], visited)
            visited.discard(e.dst)

    dfs(src, [], {src})
    return paths
