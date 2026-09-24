"""Edit operations - the only way the studio changes a document.

Engineering ops (connectivity, parts, parameters) mutate the EngineeringDesignProject and are
checked against the registry *before* they are applied: they may produce an electrically
invalid design (that is what validation feedback is for), but never a structurally invalid
one (unknown part types, unknown pins, dangling references). Presentation ops only touch the
LayoutState. A batch of ops is atomic: any failure leaves the document unchanged.
"""
from __future__ import annotations

import re
from typing import Annotated, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from components.registry import ComponentRegistry
from core.models import EngineeringComponentInstance, Net, PinRef
from core.units import parse_quantity
from functional.intent import FunctionalIntent, normalize_intent
from schematic.models import Placement
from schematic.symbols import ref_prefix, symbol_name_for

from .document import OpResult, StudioDocument

_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-]{0,63}$")
_UNIT_PARAMS = {"ohm": "ohm", "F": "F", "H": "H", "V": "V", "m": None}


class EditError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ── operation models ───────────────────────────────────────────────────────

class AddComponent(BaseModel):
    op: Literal["add_component"] = "add_component"
    component_type: str
    instance_id: Optional[str] = None
    parameters: Dict[str, str] = Field(default_factory=dict)
    x: Optional[int] = None
    y: Optional[int] = None


class RemoveComponent(BaseModel):
    op: Literal["remove_component"] = "remove_component"
    instance_id: str


class SetParameter(BaseModel):
    op: Literal["set_parameter"] = "set_parameter"
    instance_id: str
    key: str
    value: Optional[str] = None      # None removes the parameter


class Connect(BaseModel):
    op: Literal["connect"] = "connect"
    a: str                            # "instance.pin"
    b: str
    net_id: Optional[str] = None      # name for a newly created net


class Disconnect(BaseModel):
    op: Literal["disconnect"] = "disconnect"
    pin: str


class DeleteNet(BaseModel):
    op: Literal["delete_net"] = "delete_net"
    net_id: str


class RenameNet(BaseModel):
    op: Literal["rename_net"] = "rename_net"
    net_id: str
    new_net_id: str


class SetNetType(BaseModel):
    op: Literal["set_net_type"] = "set_net_type"
    net_id: str
    net_type: Optional[Literal["power", "ground", "signal"]] = None


class InsertPattern(BaseModel):
    op: Literal["insert_pattern"] = "insert_pattern"
    pattern_id: str
    prefix: Optional[str] = None
    bindings: Dict[str, str] = Field(default_factory=dict)
    choices: Dict[str, str] = Field(default_factory=dict)
    parameters: Dict[str, Dict[str, str]] = Field(default_factory=dict)


class SetDesignInfo(BaseModel):
    op: Literal["set_design_info"] = "set_design_info"
    name: Optional[str] = None
    description: Optional[str] = None


class MoveComponent(BaseModel):
    op: Literal["move_component"] = "move_component"
    instance_id: str
    x: int
    y: int


class RotateComponent(BaseModel):
    op: Literal["rotate_component"] = "rotate_component"
    instance_id: str
    rotation: Optional[int] = None    # absolute; None = +90°


class MirrorComponent(BaseModel):
    op: Literal["mirror_component"] = "mirror_component"
    instance_id: str


class SetNetStyle(BaseModel):
    op: Literal["set_net_style"] = "set_net_style"
    net_id: str
    style: Literal["auto", "wire", "label"]


class SetShowAllPins(BaseModel):
    op: Literal["set_show_all_pins"] = "set_show_all_pins"
    instance_id: str
    value: bool = True


class SetIntent(BaseModel):
    """Set (or clear, with intent=None) the requested behaviour the design is graded against."""
    op: Literal["set_intent"] = "set_intent"
    intent: Optional[FunctionalIntent] = None


class AutoArrange(BaseModel):
    op: Literal["auto_arrange"] = "auto_arrange"
    keep_locked: bool = False


EditOp = Annotated[Union[AddComponent, RemoveComponent, SetParameter, Connect, Disconnect, DeleteNet, RenameNet,
                         SetNetType, InsertPattern, SetDesignInfo, MoveComponent, RotateComponent, MirrorComponent,
                         SetNetStyle, SetShowAllPins, AutoArrange, SetIntent], Field(discriminator="op")]


class EditBatch(BaseModel):
    ops: List[EditOp]


# ── helpers ────────────────────────────────────────────────────────────────

def _comp(doc: StudioDocument, iid: str) -> EngineeringComponentInstance:
    c = next((c for c in doc.design.components if c.instance_id == iid), None)
    if c is None:
        raise EditError("EDIT_UNKNOWN_INSTANCE", f"No component '{iid}' in the design")
    return c


def _net(doc: StudioDocument, net_id: str) -> Net:
    n = next((n for n in doc.design.nets if n.net_id == net_id), None)
    if n is None:
        raise EditError("EDIT_UNKNOWN_NET", f"No net '{net_id}' in the design")
    return n


def _pinref(doc: StudioDocument, registry: ComponentRegistry, ref: str) -> PinRef:
    try:
        pr = PinRef.from_str(ref)
    except ValueError:
        raise EditError("EDIT_BAD_PIN_REF", f"'{ref}' is not of the form instance.pin")
    comp = _comp(doc, pr.instance_id)
    ctype = registry.get(comp.component_type)
    if ctype is None:
        raise EditError("EDIT_UNKNOWN_TYPE", f"{pr.instance_id} has unknown type {comp.component_type}; fix the part first")
    if pr.pin_id not in {p.pin_id for p in ctype.pins}:
        raise EditError("EDIT_UNKNOWN_PIN", f"{ctype.name} has no pin '{pr.pin_id}' (pins: {', '.join(p.pin_id for p in ctype.pins)})")
    return pr


def _net_of(doc: StudioDocument, ref: str) -> Optional[Net]:
    return next((n for n in doc.design.nets if any(c.ref == ref for c in n.connections)), None)


def _check_id(value: str, what: str) -> str:
    if not _ID_RE.match(value):
        raise EditError("EDIT_BAD_ID", f"Invalid {what} '{value}' (letters, digits, _ and - only)")
    return value


def _fresh_net_id(doc: StudioDocument) -> str:
    used = {n.net_id for n in doc.design.nets}
    k = 1
    while f"net{k}" in used:
        k += 1
    return f"net{k}"


def _validate_param(ctype, key: str, value: str) -> None:
    unit = ctype.configurable_parameters.get(key)
    if unit is None:
        allowed = ", ".join(ctype.configurable_parameters) or "none"
        raise EditError("EDIT_UNKNOWN_PARAMETER", f"{ctype.name} has no configurable parameter '{key}' (allowed: {allowed})")
    if unit in _UNIT_PARAMS and parse_quantity(value, _UNIT_PARAMS[unit]) is None:
        raise EditError("EDIT_BAD_VALUE", f"'{value}' is not a valid value for {key} ({unit}); e.g. 4.7k, 100n, 3.3")


# ── application ────────────────────────────────────────────────────────────

def apply_ops(doc: StudioDocument, ops: List[EditOp], registry: ComponentRegistry) -> Tuple[StudioDocument, List[OpResult]]:
    """Apply ops to a copy of ``doc``. Raises EditError (document untouched) on any failure."""
    work = doc.model_copy(deep=True)
    results: List[OpResult] = []
    for op in ops:
        results.append(_apply_one(work, op, registry))
    work.revision = doc.revision + 1
    return work, results


def _apply_one(doc: StudioDocument, op, registry: ComponentRegistry) -> OpResult:
    d = doc.design
    L = doc.layout

    if isinstance(op, AddComponent):
        ctype = registry.get(op.component_type)
        if ctype is None:
            raise EditError("EDIT_UNKNOWN_TYPE", f"'{op.component_type}' is not in the component registry")
        for k, v in op.parameters.items():
            _validate_param(ctype, k, v)
        used = {c.instance_id for c in d.components}
        if op.instance_id:
            iid = _check_id(op.instance_id, "instance id")
            if iid in used:
                raise EditError("EDIT_DUPLICATE_ID", f"Instance id '{iid}' already exists")
        else:
            pre = re.sub(r"[^a-z]", "", ref_prefix(ctype, symbol_name_for(ctype)).lower()) or "u"
            k = 1
            while f"{pre}{k}" in used:
                k += 1
            iid = f"{pre}{k}"
        d.components.append(EngineeringComponentInstance(instance_id=iid, component_type=op.component_type,
                                                         parameters=dict(op.parameters)))
        if op.x is not None and op.y is not None:
            # A hint (e.g. the centre of the user's view): not locked, so the layout engine
            # nudges it to the nearest free spot instead of overlapping existing parts.
            L.placements[iid] = Placement(x=op.x, y=op.y, locked=False)
        return OpResult(op=op.op, kind="engineering", message=f"Added {iid} ({ctype.name}); it is unconnected until wired")

    if isinstance(op, RemoveComponent):
        _comp(doc, op.instance_id)
        d.components = [c for c in d.components if c.instance_id != op.instance_id]
        removed_nets = []
        for net in list(d.nets):
            net.connections = [pr for pr in net.connections if pr.instance_id != op.instance_id]
            if len(net.connections) < 2:
                d.nets.remove(net)
                removed_nets.append(net.net_id)
                L.net_styles.pop(net.net_id, None)
        dropped_rules = []
        for rule in list(d.logic):
            if any(c.input_instance == op.instance_id for c in rule.conditions) or \
               any(a.output_instance == op.instance_id for a in rule.actions):
                d.logic.remove(rule)
                dropped_rules.append(rule.rule_id)
        L.placements.pop(op.instance_id, None)
        msg = f"Removed {op.instance_id}"
        if removed_nets:
            msg += f"; nets left with one pin were deleted: {', '.join(removed_nets)}"
        if dropped_rules:
            msg += f"; logic rules referencing it were removed: {', '.join(dropped_rules)}"
        return OpResult(op=op.op, kind="engineering", message=msg)

    if isinstance(op, SetParameter):
        comp = _comp(doc, op.instance_id)
        ctype = registry.get(comp.component_type)
        if ctype is None:
            raise EditError("EDIT_UNKNOWN_TYPE", f"{op.instance_id} has unknown type {comp.component_type}")
        if op.value is None or op.value == "":
            if op.key not in comp.parameters:
                raise EditError("EDIT_UNKNOWN_PARAMETER", f"{op.instance_id} has no parameter '{op.key}'")
            comp.parameters.pop(op.key)
            return OpResult(op=op.op, kind="engineering", message=f"Cleared {op.instance_id}.{op.key}")
        _validate_param(ctype, op.key, op.value)
        comp.parameters[op.key] = op.value
        return OpResult(op=op.op, kind="engineering", message=f"{op.instance_id}.{op.key} = {op.value}")

    if isinstance(op, Connect):
        a, b = _pinref(doc, registry, op.a), _pinref(doc, registry, op.b)
        if a.ref == b.ref:
            raise EditError("EDIT_SELF_CONNECTION", "Cannot connect a pin to itself")
        na, nb = _net_of(doc, a.ref), _net_of(doc, b.ref)
        if na is not None and na is nb:
            return OpResult(op=op.op, kind="engineering", message=f"{a.ref} and {b.ref} are already on net {na.net_id}")
        if na is None and nb is None:
            nid = _check_id(op.net_id, "net id") if op.net_id else _fresh_net_id(doc)
            if any(n.net_id == nid for n in d.nets):
                raise EditError("EDIT_DUPLICATE_NET", f"Net '{nid}' already exists")
            d.nets.append(Net(net_id=nid, connections=[a, b]))
            return OpResult(op=op.op, kind="engineering", message=f"Created net {nid}: {a.ref} ↔ {b.ref}")
        if na is None or nb is None:
            target, pin = (nb, a) if na is None else (na, b)
            target.connections.append(pin)
            return OpResult(op=op.op, kind="engineering", message=f"Added {pin.ref} to net {target.net_id}")
        # Merge two nets. Keep the one that carries a declared type, then the larger, then the name order.
        keep, drop = sorted([na, nb], key=lambda n: (n.net_type is None, -len(n.connections), n.net_id))
        for pr in drop.connections:
            keep.connections.append(pr)
        if keep.net_type is None:
            keep.net_type = drop.net_type
        d.nets.remove(drop)
        L.net_styles.pop(drop.net_id, None)
        return OpResult(op=op.op, kind="engineering", message=f"Merged net {drop.net_id} into {keep.net_id}")

    if isinstance(op, Disconnect):
        pr = _pinref(doc, registry, op.pin)
        net = _net_of(doc, pr.ref)
        if net is None:
            raise EditError("EDIT_NOT_CONNECTED", f"{pr.ref} is not connected")
        net.connections = [c for c in net.connections if c.ref != pr.ref]
        if len(net.connections) < 2:
            d.nets.remove(net)
            L.net_styles.pop(net.net_id, None)
            return OpResult(op=op.op, kind="engineering", message=f"Disconnected {pr.ref}; net {net.net_id} had one pin left and was removed")
        return OpResult(op=op.op, kind="engineering", message=f"Disconnected {pr.ref} from {net.net_id}")

    if isinstance(op, DeleteNet):
        net = _net(doc, op.net_id)
        d.nets.remove(net)
        L.net_styles.pop(net.net_id, None)
        return OpResult(op=op.op, kind="engineering", message=f"Deleted net {net.net_id}")

    if isinstance(op, RenameNet):
        net = _net(doc, op.net_id)
        new = _check_id(op.new_net_id, "net id")
        if new != net.net_id and any(n.net_id == new for n in d.nets):
            raise EditError("EDIT_DUPLICATE_NET", f"Net '{new}' already exists")
        if op.net_id in L.net_styles:
            L.net_styles[new] = L.net_styles.pop(op.net_id)
        net.net_id = new
        return OpResult(op=op.op, kind="engineering", message=f"Renamed net {op.net_id} → {new}")

    if isinstance(op, SetNetType):
        net = _net(doc, op.net_id)
        net.net_type = op.net_type
        return OpResult(op=op.op, kind="engineering", message=f"Net {net.net_id} type = {op.net_type}")

    if isinstance(op, InsertPattern):
        from knowledge import apply_fragment, get_default_patterns, instantiate_pattern
        pattern = get_default_patterns().get(op.pattern_id)
        if pattern is None:
            raise EditError("EDIT_UNKNOWN_PATTERN", f"No design pattern '{op.pattern_id}'")
        for port, ref in op.bindings.items():
            _pinref(doc, registry, ref)
        try:
            frag = instantiate_pattern(pattern, op.prefix or op.pattern_id.split("_")[0], op.bindings, op.choices,
                                       op.parameters, taken_ids={c.instance_id for c in d.components})
            doc.design = apply_fragment(d, frag)
        except ValueError as e:
            raise EditError("EDIT_PATTERN", str(e))
        return OpResult(op=op.op, kind="engineering",
                        message=f"Inserted {pattern.name} ({', '.join(c.instance_id for c in frag.components)})"
                                + (f"; {'; '.join(frag.notes)}" if frag.notes else ""))

    if isinstance(op, SetIntent):
        if op.intent is None:
            doc.intent = None
            return OpResult(op=op.op, kind="engineering", message="Cleared the functional intent")
        doc.intent, notes = normalize_intent(op.intent)
        return OpResult(op=op.op, kind="engineering",
                        message=f"Functional intent set ({len(doc.intent.behaviors)} behaviour(s))" + (f"; {'; '.join(notes)}" if notes else ""))

    if isinstance(op, SetDesignInfo):
        if op.name is not None:
            d.name = op.name
        if op.description is not None:
            d.description = op.description
        return OpResult(op=op.op, kind="engineering", message="Updated design information")

    # ── presentation ops ──
    if isinstance(op, MoveComponent):
        _comp(doc, op.instance_id)
        prev = L.placements.get(op.instance_id)
        L.placements[op.instance_id] = Placement(x=op.x, y=op.y, rotation=prev.rotation if prev else 0,
                                                 mirror=prev.mirror if prev else False, locked=True,
                                                 show_all_pins=prev.show_all_pins if prev else False)
        return OpResult(op=op.op, kind="presentation", message=f"Moved {op.instance_id}")

    if isinstance(op, (RotateComponent, MirrorComponent, SetShowAllPins)):
        _comp(doc, op.instance_id)
        prev = L.placements.get(op.instance_id)
        if prev is None:
            raise EditError("EDIT_NOT_PLACED", f"{op.instance_id} has no placement yet; refresh the schematic first")
        p = prev.model_copy()
        if isinstance(op, RotateComponent):
            rot = op.rotation if op.rotation is not None else (p.rotation + 90) % 360
            if rot not in (0, 90, 180, 270):
                raise EditError("EDIT_BAD_ROTATION", "Rotation must be 0, 90, 180 or 270")
            p.rotation, p.locked = rot, True
            msg = f"Rotated {op.instance_id} to {rot}°"
        elif isinstance(op, MirrorComponent):
            p.mirror, p.locked = not p.mirror, True
            msg = f"Mirrored {op.instance_id}"
        else:
            p.show_all_pins = op.value
            msg = f"{'Showing' if op.value else 'Hiding'} unused pins of {op.instance_id}"
        L.placements[op.instance_id] = p
        return OpResult(op=op.op, kind="presentation", message=msg)

    if isinstance(op, SetNetStyle):
        _net(doc, op.net_id)
        if op.style == "auto":
            L.net_styles.pop(op.net_id, None)
        else:
            L.net_styles[op.net_id] = op.style
        return OpResult(op=op.op, kind="presentation", message=f"Net {op.net_id} drawn as {op.style}")

    if isinstance(op, AutoArrange):
        L.placements = {k: v for k, v in L.placements.items() if op.keep_locked and v.locked}
        return OpResult(op=op.op, kind="presentation", message="Re-arranged the schematic")

    raise EditError("EDIT_UNKNOWN_OP", f"Unsupported operation {getattr(op, 'op', op)}")
