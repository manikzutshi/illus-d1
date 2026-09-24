"""Design patterns: data model, store, deterministic instantiation and merge into a design."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from core.models import EngineeringComponentInstance, EngineeringDesignProject, Net, PinRef

logger = logging.getLogger(__name__)
_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "patterns.yaml"


class PatternPart(BaseModel):
    role: str
    component_type: str
    alternatives: List[str] = Field(default_factory=list)
    parameters: Dict[str, str] = Field(default_factory=dict)
    purpose: str = ""


class PatternPort(BaseModel):
    name: str
    kind: Literal["signal", "supply", "ground"] = "signal"
    description: str = ""


class PatternNet(BaseModel):
    name: str
    members: List[str]            # "role.PIN" or "port:NAME"


class DesignPattern(BaseModel):
    pattern_id: str
    name: str
    purpose: str
    category: str = ""
    concepts: List[str] = Field(default_factory=list)
    parts: List[PatternPart]
    ports: List[PatternPort] = Field(default_factory=list)
    nets: List[PatternNet]
    calculations: List[str] = Field(default_factory=list)
    design_notes: List[str] = Field(default_factory=list)


class FragmentNet(BaseModel):
    name: str
    members: List[PinRef]


class PatternFragment(BaseModel):
    """A ready-to-merge piece of engineering design produced from a pattern."""
    pattern_id: str
    components: List[EngineeringComponentInstance]
    nets: List[FragmentNet]
    notes: List[str] = Field(default_factory=list)


class PatternStore:
    def __init__(self) -> None:
        self._patterns: Dict[str, DesignPattern] = {}

    def load_yaml(self, path: Path) -> int:
        if not path.exists():
            return 0
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        n = 0
        for pid, props in (data.get("patterns") or {}).items():
            try:
                self._patterns[pid] = DesignPattern.model_validate({**props, "pattern_id": pid})
                n += 1
            except Exception as e:  # pragma: no cover - surfaced by tests on the data file
                logger.warning(f"Skipping pattern {pid}: {e}")
        return n

    def get(self, pattern_id: str) -> Optional[DesignPattern]:
        return self._patterns.get(pattern_id)

    def list_all(self) -> List[DesignPattern]:
        return list(self._patterns.values())

    def search(self, query: str) -> List[DesignPattern]:
        tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t]
        scored = []
        for p in self._patterns.values():
            hay = " ".join([p.pattern_id, p.name, p.purpose, p.category, " ".join(p.concepts)]).lower()
            if tokens and all(t in hay for t in tokens):
                scored.append((-sum(hay.count(t) for t in tokens), p.pattern_id, p))
        return [p for *_, p in sorted(scored)]

    @property
    def count(self) -> int:
        return len(self._patterns)


def get_default_patterns() -> PatternStore:
    store = PatternStore()
    store.load_yaml(_DEFAULT_PATH)
    return store


def instantiate_pattern(pattern: DesignPattern, prefix: str, bindings: Optional[Dict[str, str]] = None,
                        choices: Optional[Dict[str, str]] = None, parameters: Optional[Dict[str, Dict[str, str]]] = None,
                        taken_ids: Optional[set] = None) -> PatternFragment:
    """Create concrete components and nets for a pattern.

    ``bindings`` maps port name -> existing pin ("u1.GPIO5"); ``choices`` maps role ->
    component type (must be the default or one of the listed alternatives); ``parameters``
    maps role -> parameter overrides. Instance ids are ``{prefix}_{role}`` made unique
    against ``taken_ids``.
    """
    bindings = bindings or {}
    choices = choices or {}
    parameters = parameters or {}
    taken = set(taken_ids or ())
    notes: List[str] = []
    ids: Dict[str, str] = {}
    comps: List[EngineeringComponentInstance] = []
    for part in pattern.parts:
        ctype = choices.get(part.role, part.component_type)
        if ctype != part.component_type and ctype not in part.alternatives:
            raise ValueError(f"{pattern.pattern_id}: '{ctype}' is not an allowed choice for role '{part.role}'")
        base = re.sub(r"[^A-Za-z0-9_]", "_", f"{prefix}_{part.role}")
        iid, k = base, 2
        while iid in taken:
            iid, k = f"{base}{k}", k + 1
        taken.add(iid)
        ids[part.role] = iid
        comps.append(EngineeringComponentInstance(instance_id=iid, component_type=ctype,
                                                  parameters={**part.parameters, **parameters.get(part.role, {})},
                                                  metadata={"role": part.purpose or part.role, "pattern": pattern.pattern_id}))
    port_names = {p.name for p in pattern.ports}
    for name in bindings:
        if name not in port_names:
            raise ValueError(f"{pattern.pattern_id}: unknown port '{name}'")
    nets: List[FragmentNet] = []
    for pn in pattern.nets:
        members: List[PinRef] = []
        for m in pn.members:
            if m.startswith("port:"):
                port = m[5:]
                if port in bindings:
                    members.append(PinRef.from_str(bindings[port]))
                else:
                    notes.append(f"port {port} left unbound")
            else:
                role, pin = m.split(".", 1)
                members.append(PinRef(instance_id=ids[role], pin_id=pin))
        if len(members) >= 2:
            nets.append(FragmentNet(name=f"{prefix}_{pn.name}", members=members))
        elif members:
            notes.append(f"net {pn.name} has a single member; bind its port to connect it")
    return PatternFragment(pattern_id=pattern.pattern_id, components=comps, nets=nets, notes=notes)


def apply_fragment(design: EngineeringDesignProject, fragment: PatternFragment) -> EngineeringDesignProject:
    """Merge a fragment into a copy of ``design``. A fragment net whose member pin already lies
    on a design net joins that net (nets are merged), otherwise it becomes a new net."""
    out = design.model_copy(deep=True)
    existing_ids = {c.instance_id for c in out.components}
    for c in fragment.components:
        if c.instance_id in existing_ids:
            raise ValueError(f"instance id {c.instance_id} already exists")
        out.components.append(c)
    for fn in fragment.nets:
        touched = []
        for pr in fn.members:
            for net in out.nets:
                if any(x.ref == pr.ref for x in net.connections) and net not in touched:
                    touched.append(net)
        if not touched:
            name, k = fn.name, 2
            while any(n.net_id == name for n in out.nets):
                name, k = f"{fn.name}_{k}", k + 1
            out.nets.append(Net(net_id=name, connections=list(fn.members)))
            continue
        target = touched[0]
        for other in touched[1:]:
            for pr in other.connections:
                if all(x.ref != pr.ref for x in target.connections):
                    target.connections.append(pr)
            out.nets.remove(other)
        for pr in fn.members:
            if all(x.ref != pr.ref for x in target.connections):
                target.connections.append(pr)
    return out
