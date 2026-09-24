"""Net classification for schematic drawing.

Decides, from registry pin metadata only, whether a net is a *ground*, *power* or *signal*
net, what it should be called on the drawing (``GND``, ``+5V`` …) and its supply voltage when
that voltage is known. Unknown voltages stay None — they are never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from components.registry import ComponentRegistry
from core.enums import ComponentCategory, PinDirection
from core.models import EngineeringDesignProject, PinDefinition
from core.units import parse_quantity


@dataclass
class NetInfo:
    net_id: str
    net_class: str                       # power | ground | signal
    display_name: str
    voltage: Optional[float] = None
    pins: list[str] = field(default_factory=list)


def resolve_pin(design: EngineeringDesignProject, registry: ComponentRegistry, instance_id: str, pin_id: str) -> Optional[PinDefinition]:
    comp = next((c for c in design.components if c.instance_id == instance_id), None)
    if comp is None:
        return None
    ctype = registry.get(comp.component_type)
    if ctype is None:
        return None
    return next((p for p in ctype.pins if p.pin_id == pin_id), None)


def supply_source_voltage(design: EngineeringDesignProject, registry: ComponentRegistry, instance_id: str, pin_id: str) -> tuple[bool, Optional[float]]:
    """(is_source, voltage) for a pin. Mirrors the validator's notion of a supply source."""
    comp = next((c for c in design.components if c.instance_id == instance_id), None)
    if comp is None:
        return False, None
    ctype = registry.get(comp.component_type)
    if ctype is None:
        return False, None
    pin = next((p for p in ctype.pins if p.pin_id == pin_id), None)
    if pin is None or pin.direction != PinDirection.POWER:
        return False, None
    is_source = pin.supply == "source" or (pin.supply is None and ctype.category == ComponentCategory.POWER_SOURCE)
    if not is_source:
        return False, None
    voltage = pin.nominal_voltage
    if voltage is None and "voltage" in comp.parameters and "voltage" in ctype.configurable_parameters:
        voltage = parse_quantity(comp.parameters["voltage"], "V")
    if voltage is None:
        voltage = parse_quantity(pin.electrical_type, "V") if pin.electrical_type else None
    if voltage is None and ctype.category == ComponentCategory.POWER_SOURCE:
        voltage = parse_quantity(ctype.electrical_properties.get("voltage"), "V")
    return True, voltage


def format_rail(voltage: float) -> str:
    text = f"{voltage:g}"
    return f"+{text}V" if voltage >= 0 else f"{text}V"


def classify_nets(design: EngineeringDesignProject, registry: ComponentRegistry) -> Dict[str, NetInfo]:
    infos: Dict[str, NetInfo] = {}
    for net in design.nets:
        pins = [pr.ref for pr in net.connections]
        dirs = []
        sources: list[Optional[float]] = []
        has_signal_driver = False
        for pr in net.connections:
            pdef = resolve_pin(design, registry, pr.instance_id, pr.pin_id)
            if pdef is None:
                continue
            dirs.append(pdef.direction)
            is_src, v = supply_source_voltage(design, registry, pr.instance_id, pr.pin_id)
            if is_src:
                sources.append(v)
            if pdef.direction in (PinDirection.OUTPUT, PinDirection.BIDIRECTIONAL):
                has_signal_driver = True

        if PinDirection.GROUND in dirs or (net.net_type or "").lower() == "ground":
            infos[net.net_id] = NetInfo(net.net_id, "ground", "GND", 0.0, pins)
            continue
        has_power_pin = PinDirection.POWER in dirs
        declared_power = (net.net_type or "").lower() == "power"
        if sources or declared_power or (has_power_pin and not has_signal_driver):
            known = sorted({v for v in sources if v is not None})
            voltage = known[0] if len(known) == 1 else None
            name = format_rail(voltage) if voltage is not None else net.net_id.upper()
            infos[net.net_id] = NetInfo(net.net_id, "power", name, voltage, pins)
            continue
        infos[net.net_id] = NetInfo(net.net_id, "signal", net.net_id, None, pins)

    # Port text must identify exactly one net (ports connect by name).
    by_name: Dict[str, list[str]] = {}
    for info in infos.values():
        if info.net_class != "signal":
            by_name.setdefault(info.display_name, []).append(info.net_id)
    for name, ids in by_name.items():
        if len(ids) > 1:
            for nid in sorted(ids)[1:]:
                infos[nid].display_name = f"{name}_{nid}"
    return infos
