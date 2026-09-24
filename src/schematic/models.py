"""Schematic IR — how an engineering design is *drawn*.

The schematic is a deterministic projection of an ``EngineeringDesignProject``. It carries
no engineering authority: every drawn object references the engineering object it depicts
(instance_id / pin_id / net_id), and ``schematic.verify`` proves that the connectivity
implied by the geometry equals the engineering nets.

Presentation-only state that users can change (placement, rotation, net drawing style)
lives in :class:`LayoutState`; it contains no connectivity.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

SCHEMATIC_SCHEMA_VERSION = "0.2.0"

Orient = Literal["left", "right", "up", "down"]


# ── Symbol definitions (library data, embedded in each schematic) ──────────

class SymbolPrimitive(BaseModel):
    """A drawing primitive in symbol-local coordinates (grid units, y down).

    kind: line | polyline | polygon | rect | circle | path | text
    """
    kind: Literal["line", "polyline", "polygon", "rect", "circle", "path", "text"]
    points: List[List[float]] = Field(default_factory=list)
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    r: float = 0
    d: str = ""                       # SVG path data (kind == path)
    text: str = ""
    size: float = 1.0
    anchor: Literal["start", "middle", "end"] = "middle"
    fill: Literal["none", "outline", "body"] = "none"
    width: float = 0.15


class SymbolPin(BaseModel):
    name: str                           # symbol pin name
    x: int                              # tip (connection point), local
    y: int
    orientation: Orient                 # direction pointing *away* from the body
    length: float = 2.0                 # drawn from tip back toward the body
    number: Optional[str] = None
    show_name: bool = False
    hidden: bool = False


class SymbolDef(BaseModel):
    symbol_id: str
    kind: Literal["part", "power_flag", "ground_flag"] = "part"
    graphics: List[SymbolPrimitive] = Field(default_factory=list)
    pins: List[SymbolPin] = Field(default_factory=list)
    body: List[float] = Field(default_factory=lambda: [0, 0, 0, 0])   # x0,y0,x1,y1 local, excl. pins
    description: str = ""


# ── Placed objects ──────────────────────────────────────────────────────────

class TextItem(BaseModel):
    x: float
    y: float
    text: str
    size: float = 1.1
    anchor: Literal["start", "middle", "end"] = "start"


class SchematicPin(BaseModel):
    pin_id: str                          # engineering pin id
    symbol_pin: str
    name: str = ""
    x: int                               # world tip
    y: int
    orientation: Orient                  # world outward direction
    net_id: Optional[str] = None
    hidden: bool = False


class SchematicComponentInstance(BaseModel):
    instance_id: str                     # engineering instance id (traceability)
    component_type_id: str
    reference: str                       # R1, U1, ...
    value: str = ""
    symbol_id: str
    x: int
    y: int
    rotation: int = 0
    mirror: bool = False
    locked: bool = False                 # user-placed
    pins: List[SchematicPin] = Field(default_factory=list)
    bbox: List[float] = Field(default_factory=list)   # world, body + pins
    ref_label: Optional[TextItem] = None
    value_label: Optional[TextItem] = None
    port_text: Optional[str] = None      # for power/ground flag symbols: the net name they denote
    metadata: Dict[str, str] = Field(default_factory=dict)


class SchematicWire(BaseModel):
    wire_id: str
    net_id: str
    x1: int
    y1: int
    x2: int
    y2: int


class SchematicJunction(BaseModel):
    junction_id: str
    net_id: str
    x: int
    y: int


class SchematicPowerPort(BaseModel):
    """Power/ground port attached to a pin tip. Ports with equal text are connected."""
    port_id: str
    net_id: str
    kind: Literal["power", "ground"]
    text: str
    x: int
    y: int
    direction: Orient                    # direction the port graphic extends from (x, y)
    pin_ref: Optional[str] = None        # "instance.pin" served by this port


class SchematicNetLabel(BaseModel):
    """Local net label attached to a pin tip. Labels with equal text are connected."""
    label_id: str
    net_id: str
    text: str
    x: int
    y: int
    direction: Orient
    pin_ref: Optional[str] = None


class SchematicTextAnnotation(BaseModel):
    annotation_id: str
    x: float
    y: float
    text: str
    size: float = 1.2
    anchor: Literal["start", "middle", "end"] = "start"


class NetTrace(BaseModel):
    net_id: str
    display_name: str
    net_class: Literal["power", "ground", "signal"]
    style: Literal["wire", "label", "port"]
    pins: List[str] = Field(default_factory=list)
    wires: List[str] = Field(default_factory=list)
    junctions: List[str] = Field(default_factory=list)
    ports: List[str] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)
    voltage: Optional[float] = None


class LayoutStats(BaseModel):
    wire_length: int = 0
    bends: int = 0
    crossings: int = 0
    label_fallback_nets: List[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0


class SchematicProject(BaseModel):
    schema_version: str = SCHEMATIC_SCHEMA_VERSION
    project_id: str
    name: str
    description: str = ""
    engineering_design_reference: Optional[str] = None
    components: List[SchematicComponentInstance] = Field(default_factory=list)
    wires: List[SchematicWire] = Field(default_factory=list)
    junctions: List[SchematicJunction] = Field(default_factory=list)
    power_ports: List[SchematicPowerPort] = Field(default_factory=list)
    net_labels: List[SchematicNetLabel] = Field(default_factory=list)
    text_annotations: List[SchematicTextAnnotation] = Field(default_factory=list)
    symbols: Dict[str, SymbolDef] = Field(default_factory=dict)
    nets: Dict[str, NetTrace] = Field(default_factory=dict)
    bounds: List[float] = Field(default_factory=lambda: [0, 0, 0, 0])
    stats: LayoutStats = Field(default_factory=LayoutStats)
    diagnostics: List[str] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)

    def component(self, instance_id: str) -> Optional[SchematicComponentInstance]:
        return next((c for c in self.components if c.instance_id == instance_id), None)


# ── Presentation state (user-editable, no connectivity) ────────────────────

class Placement(BaseModel):
    x: int
    y: int
    rotation: int = 0
    mirror: bool = False
    locked: bool = False          # True when the user placed/rotated it explicitly
    show_all_pins: bool = False


class LayoutState(BaseModel):
    placements: Dict[str, Placement] = Field(default_factory=dict)
    net_styles: Dict[str, Literal["auto", "wire", "label"]] = Field(default_factory=dict)
