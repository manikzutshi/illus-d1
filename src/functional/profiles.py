"""Functional profiles: signal-flow knowledge about each component type.

Resolution order for a component type:
  1. data/knowledge/functional_profiles.yaml  `components:` entry (per part)
  2. `families:` entry for the registry family
  3. a generic profile derived from registry pin directions (inputs -> outputs, sign unknown)
     marked `derived=True` so findings can say the function is only roughly modelled.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from core.enums import ComponentCategory, PinDirection
from core.models import ComponentType, EngineeringComponentInstance

_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "functional_profiles.yaml"

Kind = Literal["sensor", "resistive_sensor", "adjustable", "actuator", "display", "controller", "comparator",
               "amplifier", "switch", "logic", "timer", "driver", "converter", "passive", "power", "connector",
               "memory", "interface", "unknown"]


class FunctionalProfile(BaseModel):
    kind: Kind = "unknown"
    quantities: List[str] = Field(default_factory=list)
    outputs: Dict[str, int] = Field(default_factory=dict)
    resistance_sign: Optional[int] = None
    sign_parameter: Optional[str] = None
    sign_by_value: Dict[str, int] = Field(default_factory=dict)
    terminals: List[List[str]] = Field(default_factory=list)
    terminals_ends: List[str] = Field(default_factory=list)
    loads: List[List[str]] = Field(default_factory=list)
    polarized: bool = True
    controls: Dict[str, int] = Field(default_factory=dict)
    transfers: List[List] = Field(default_factory=list)
    decision: Optional[Literal["explicit", "implicit", "programmable"]] = None
    programmable: bool = False
    gate_sign: Optional[int] = None
    generator_pins: List[str] = Field(default_factory=list)   # autonomous outputs (oscillators)
    open_collector_outputs: List[str] = Field(default_factory=list)
    # per device polarity (registry symbol name): which outputs can only sink, e.g. an NPN collector
    sink_only_by_symbol: Dict[str, List[str]] = Field(default_factory=dict)
    min_drive_ma: Optional[float] = None
    min_drive_basis: str = ""
    derived: bool = False           # True when generated from pin directions only

    def effective_resistance_sign(self, instance: EngineeringComponentInstance) -> Optional[int]:
        if self.sign_parameter:
            value = str(instance.parameters.get(self.sign_parameter, "")).upper()
            return self.sign_by_value.get(value)
        return self.resistance_sign


_DATA: Optional[dict] = None


def _data() -> dict:
    global _DATA
    if _DATA is None:
        _DATA = yaml.safe_load(_PATH.read_text(encoding="utf-8"))
    return _DATA


def profile_for(ctype: Optional[ComponentType]) -> FunctionalProfile:
    if ctype is None:
        return FunctionalProfile(kind="unknown", derived=True)
    data = _data()
    raw = data.get("components", {}).get(ctype.component_type_id) or data.get("families", {}).get(ctype.family or "")
    if raw is not None:
        prof = FunctionalProfile.model_validate(raw)
        if prof.gate_sign is not None and not prof.transfers:
            prof.transfers = _gate_transfers(ctype, prof.gate_sign)
        if prof.sink_only_by_symbol and ctype.symbol is not None:
            prof.open_collector_outputs = list(prof.open_collector_outputs) +                 list(prof.sink_only_by_symbol.get(ctype.symbol.name, []))
        if prof.kind == "sensor" and not prof.outputs:
            prof.outputs = {p.pin_id: 0 for p in ctype.pins if p.direction in (PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL)}
        return prof
    return _derived(ctype)


def _gate_transfers(ctype: ComponentType, sign: int) -> List[List]:
    """74HC-style gate ICs: pins nA, nB -> nY."""
    ids = {p.pin_id for p in ctype.pins}
    out = []
    for pid in sorted(ids):
        m = re.fullmatch(r"(\d)([AB])", pid)
        if m and f"{m.group(1)}Y" in ids:
            out.append([pid, f"{m.group(1)}Y", sign])
    return out


def _derived(ctype: ComponentType) -> FunctionalProfile:
    """Honest fallback: signal can flow from input-ish pins to output-ish pins; sign unknown."""
    signal_pins = [p for p in ctype.pins if p.direction not in (PinDirection.POWER, PinDirection.GROUND)]
    ins = [p.pin_id for p in signal_pins if p.direction in (PinDirection.INPUT, PinDirection.BIDIRECTIONAL)]
    outs = [p.pin_id for p in signal_pins if p.direction in (PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL)]
    roles = {r.upper() for r in ctype.roles}
    if ctype.category == ComponentCategory.POWER_SOURCE or ctype.category == ComponentCategory.GROUND_NODE:
        return FunctionalProfile(kind="power", derived=True)
    if ctype.category == ComponentCategory.MICROCONTROLLER:
        return FunctionalProfile(kind="controller", programmable=True, decision="programmable", derived=True)
    if len(ctype.pins) == 2 and all(p.direction == PinDirection.PASSIVE for p in ctype.pins):
        return FunctionalProfile(kind="passive", derived=True)
    kind: Kind = "sensor" if (ctype.category == ComponentCategory.SENSOR or "SENSOR" in roles) else "unknown"
    return FunctionalProfile(kind=kind, outputs={p: 0 for p in outs} if kind == "sensor" else {},
                             transfers=[[i, o, 0] for i in ins for o in outs if i != o] if kind == "unknown" else [],
                             derived=True)
