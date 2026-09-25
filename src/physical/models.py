"""Physical IR — how an engineering design is *built*: parts on a breadboard, leads, jumper wires.

Like the Schematic IR, this is a deterministic projection of an ``EngineeringDesignProject`` and
holds no engineering authority. Every physical object references the engineering object it
realises (instance_id / pin_id / net_id), and ``physical.verify`` proves that the connectivity
implied by holes, strips, rails, leads and wires equals the engineering nets.

Units: millimetres. Board frame: x along the breadboard columns, y across the rows (row a at
negative y, row j at positive y), z up; the breadboard's top surface is z = 0 and the table
(where off-board items rest) is z = -board height.

User-editable presentation state lives in :class:`PhysicalLayoutState`; it has no connectivity.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

PHYSICAL_SCHEMA_VERSION = "0.1.0"

Vec3 = List[float]
Mount = Literal["breadboard", "offboard", "virtual", "unplaced"]
GeometrySource = Literal["datasheet", "standard", "typical", "assumed"]


class RailInfo(BaseModel):
    rail_id: str                       # "T+", "T-", "B+", "B-"
    polarity: Literal["+", "-"]
    y: float
    columns: List[int] = Field(default_factory=list)
    net_id: Optional[str] = None       # engineering net assigned to this rail (if used)


class BoardInfo(BaseModel):
    board_id: str = "bb1"
    kind: Literal["half", "full"]
    name: str
    columns: int
    rows: List[str]
    row_y: Dict[str, float]            # terminal row -> y (mm)
    column_x: List[float]              # x (mm) of columns 1..N
    pitch_mm: float = 2.54
    size_mm: List[float]               # [length, width, height]
    rails: List[RailInfo] = Field(default_factory=list)
    note: str = ""


class PhysicalPin(BaseModel):
    pin_id: str
    name: str = ""
    net_id: Optional[str] = None
    position: Vec3                     # contact point: the hole it is inserted in, or the terminal
    hole: Optional[str] = None         # breadboard hole the pin is inserted into
    node: Optional[str] = None         # breadboard node of that hole ("top:12", "rail:T+")
    terminal: Optional[str] = None     # off-board terminal style: lead | header | screw | pad
    alias_of: Optional[str] = None     # shares the physical pin of another engineering pin


class VisualSpec(BaseModel):
    kind: str                          # procedural visual kind, e.g. axial_resistor, dip, to92, generic_module
    asset_url: Optional[str] = None    # detailed model, when one exists; procedural otherwise
    fallback: bool = False             # True = generic stand-in, not a representation of the real part
    label: str = ""
    params: Dict[str, str] = Field(default_factory=dict)   # e.g. bands, color, pin_count, text


class Box(BaseModel):
    center: Vec3
    size: Vec3                         # world-aligned [dx, dy, dz] after rotation


class GeometryInfo(BaseModel):
    source: GeometrySource
    notes: List[str] = Field(default_factory=list)
    variant_note: Optional[str] = None


class PhysicalPart(BaseModel):
    instance_id: str                   # engineering instance (traceability)
    component_type_id: str
    reference: str = ""
    value: str = ""
    mount: Mount
    template: str = ""
    position: Vec3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: int = 0                  # degrees about z: 0, 90, 180, 270
    anchor: Optional[str] = None       # breadboard hole of the first footprint site
    orientation: str = ""              # placement mode: row | cross | rail | dip | offboard
    span: Optional[int] = None         # two-lead parts: lead span in grid steps
    body: Optional[Box] = None
    pins: List[PhysicalPin] = Field(default_factory=list)
    visual: VisualSpec
    geometry: GeometryInfo
    locked: bool = False
    internal_links: List[List[str]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class WireEnd(BaseModel):
    kind: Literal["hole", "pin"]
    hole: Optional[str] = None
    pin_ref: Optional[str] = None      # "instance.pin" for wires attached to an off-board terminal
    position: Vec3


class PhysicalWire(BaseModel):
    wire_id: str
    net_id: str
    kind: Literal["jumper", "lead", "rail_bridge"]
    a: WireEnd
    b: WireEnd
    path: List[Vec3] = Field(default_factory=list)
    color: str = "#f1c40f"
    length_mm: float = 0.0
    purpose: str = ""                  # human-readable: "VCC to the + rail", ...


class PhysicalNetTrace(BaseModel):
    net_id: str
    display_name: str
    net_class: Literal["power", "ground", "signal"]
    nodes: List[str] = Field(default_factory=list)     # breadboard nodes carrying the net
    wires: List[str] = Field(default_factory=list)
    pins: List[str] = Field(default_factory=list)
    rails: List[str] = Field(default_factory=list)
    color: str = ""


class PhysicalFinding(BaseModel):
    code: str
    severity: Literal["ERROR", "WARNING", "INFO"]
    message: str
    instances: List[str] = Field(default_factory=list)
    pins: List[str] = Field(default_factory=list)
    nets: List[str] = Field(default_factory=list)
    holes: List[str] = Field(default_factory=list)
    wires: List[str] = Field(default_factory=list)


class PhysicalCheck(BaseModel):
    code: str
    name: str
    outcome: Literal["PASS", "FAIL", "WARN", "NOT_APPLICABLE"]


class PhysicalVerification(BaseModel):
    status: Literal["PASS", "WARN", "FAIL", "NOT_APPLICABLE"]
    ok: bool                           # no ERROR findings: the physical build equals the netlist
    summary: str
    findings: List[PhysicalFinding] = Field(default_factory=list)
    checks: List[PhysicalCheck] = Field(default_factory=list)


class PhysicalStats(BaseModel):
    parts_on_board: int = 0
    parts_offboard: int = 0
    parts_virtual: int = 0
    wires: int = 0
    leads: int = 0
    wire_length_mm: float = 0.0
    holes_used: int = 0
    elapsed_ms: float = 0.0


class AssemblyStep(BaseModel):
    step: int
    kind: Literal["board", "part", "lead", "wire", "note"]
    text: str
    instance_id: Optional[str] = None
    wire_id: Optional[str] = None
    net_id: Optional[str] = None


class PhysicalProject(BaseModel):
    schema_version: str = PHYSICAL_SCHEMA_VERSION
    project_id: str
    name: str
    applicable: bool = True            # False when the design has no physical parts (idealised primitives only)
    board: Optional[BoardInfo] = None
    parts: List[PhysicalPart] = Field(default_factory=list)
    wires: List[PhysicalWire] = Field(default_factory=list)
    nets: Dict[str, PhysicalNetTrace] = Field(default_factory=dict)
    occupied: Dict[str, str] = Field(default_factory=dict)   # hole -> "pin:inst.pin" | "wire:w3.a"
    covered: List[str] = Field(default_factory=list)          # holes under a part body (not usable)
    bounds: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0])
    assembly: List[AssemblyStep] = Field(default_factory=list)
    verification: Optional[PhysicalVerification] = None
    stats: PhysicalStats = Field(default_factory=PhysicalStats)
    diagnostics: List[str] = Field(default_factory=list)

    def part(self, instance_id: str) -> Optional[PhysicalPart]:
        return next((p for p in self.parts if p.instance_id == instance_id), None)


# ── Presentation state (user-editable, no connectivity) ────────────────────

class PhysicalPlacement(BaseModel):
    """Where the user (or a previous layout) put a part. Board parts use a hole anchor; off-board
    parts use a position on the table."""
    anchor: Optional[str] = None       # breadboard hole of the first footprint site
    orientation: Optional[str] = None  # row | cross | rail | dip
    rotation: int = 0
    span: Optional[int] = None
    x: Optional[float] = None          # off-board position (mm)
    y: Optional[float] = None
    locked: bool = False               # True when the user placed it explicitly
    seq: int = 0                       # order of user moves: the latest move must fit around earlier ones


class PhysicalLayoutState(BaseModel):
    board: Literal["auto", "half", "full"] = "auto"
    placements: Dict[str, PhysicalPlacement] = Field(default_factory=dict)
