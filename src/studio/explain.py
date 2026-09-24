"""Deterministic design explanation.

Answers "what was built, what does each part do, how do power and signals flow, what was
checked, what is assumed, what could not be verified" from the design, the registry, the
curriculum and the validation result only. No language model is involved, so nothing here
can be invented; AI-authored rationale (component metadata 'role'/'rationale', design
assumptions) is surfaced but labelled as such.
"""
from __future__ import annotations

from typing import Dict, List

from components.registry import ComponentRegistry
from core.enums import PinDirection
from core.models import EngineeringDesignProject, ValidationResult
from curriculum.store import CurriculumStore
from schematic.models import SchematicProject


def explain_design(design: EngineeringDesignProject, registry: ComponentRegistry, validation: ValidationResult,
                   schematic: SchematicProject, curriculum: CurriculumStore) -> Dict[str, object]:
    refs = {c.instance_id: c.reference for c in schematic.components}
    parts: List[dict] = []
    concepts: Dict[str, str] = {}
    for comp in design.components:
        ct = registry.get(comp.component_type)
        entry = {
            "instance_id": comp.instance_id,
            "reference": refs.get(comp.instance_id, comp.instance_id),
            "component_type": comp.component_type,
            "name": ct.name if ct else "UNKNOWN PART",
            "parameters": comp.parameters,
            "role": comp.metadata.get("role", ""),
            "rationale": comp.metadata.get("rationale", "") or comp.metadata.get("calculation", ""),
            "what_it_does": (ct.education.summary if ct and ct.education else (ct.description if ct else "")),
            "common_mistakes": (ct.education.common_mistakes if ct and ct.education else []),
            "physical": bool(ct and ct.object_type.value == "PHYSICAL"),
        }
        parts.append(entry)
        if ct:
            for cid in ct.curriculum_mapping:
                c = curriculum.get(cid)
                if c:
                    concepts[cid] = c.name
            for c in curriculum.concepts_for_component(ct.component_type_id):
                concepts[c.concept_id] = c.name

    rails, signals = [], []
    for net in design.nets:
        trace = schematic.nets.get(net.net_id)
        members = []
        drivers, receivers = [], []
        for pr in net.connections:
            comp = next((c for c in design.components if c.instance_id == pr.instance_id), None)
            ct = registry.get(comp.component_type) if comp else None
            pd = next((p for p in ct.pins if p.pin_id == pr.pin_id), None) if ct else None
            label = f"{refs.get(pr.instance_id, pr.instance_id)}.{pr.pin_id}"
            members.append(label)
            if pd is not None:
                if pd.direction == PinDirection.OUTPUT or (pd.direction == PinDirection.POWER and pd.supply == "source"):
                    drivers.append(label)
                elif pd.direction in (PinDirection.INPUT, PinDirection.POWER):
                    receivers.append(label)
        item = {"net_id": net.net_id, "members": members, "drivers": drivers, "receivers": receivers}
        if trace and trace.net_class in ("power", "ground"):
            rails.append({**item, "name": trace.display_name, "kind": trace.net_class, "voltage": trace.voltage})
        else:
            signals.append(item)

    not_checkable = [w.message for w in validation.warnings if w.code == "W002"]
    limitations = []
    if not_checkable:
        limitations.append(f"{len(not_checkable)} pin(s) lack voltage-limit data, so logic-level compatibility "
                           f"could not be verified for them (W002).")
    virtual = [p["reference"] for p in parts if not p["physical"]]
    if virtual:
        limitations.append(f"Idealised (non-physical) parts: {', '.join(virtual)} - they model behaviour, not real devices.")
    limitations.append("Validation is rule-based (ERC/DRC style); no SPICE or timing simulation was run.")

    return {
        "summary": design.description or design.name,
        "counts": {"components": len(design.components), "nets": len(design.nets),
                   "physical_parts": sum(1 for p in parts if p["physical"])},
        "parts": parts,
        "power_rails": rails,
        "signals": signals,
        "checks": [c.model_dump() for c in validation.checks_run],
        "status": validation.status.value,
        "issues": [e.model_dump() for e in validation.errors] + [w.model_dump() for w in validation.warnings if w.code != "W002"],
        "suggestions": [i.model_dump() for i in validation.infos],
        "assumptions": list(design.assumptions),
        "limitations": limitations,
        "concepts": [{"concept_id": k, "name": v} for k, v in sorted(concepts.items())],
    }
