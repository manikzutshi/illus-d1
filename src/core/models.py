from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from .enums import (
    CompetencyLevel,
    PinDirection,
    ComponentCategory,
    ValidationStatus,
    ValidationSeverity,
    ObjectType,
)

def resolve_refs(schema: dict) -> dict:
    """Inline every $ref of a pydantic JSON schema (some providers reject $defs)."""
    schema = dict(schema)
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                resolved = resolve(defs[ref_key])
                new_node = {k: v for k, v in node.items() if k != "$ref"}
                new_node.update(resolved)
                return new_node
            return {k: resolve(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


class CurriculumContext(BaseModel):
    module: str = Field(..., description="The curriculum module this concept belongs to")
    concept: str = Field(..., description="The specific concept being illustrated")
    competency_level: CompetencyLevel = Field(default=CompetencyLevel.BEGINNER, description="Target competency level")

class PinDefinition(BaseModel):
    pin_id: str = Field(..., description="Identifier for the pin (e.g. 'GPIO5', 'VCC', 'TRIG')")
    name: str = Field(..., description="Human readable name of the pin")
    direction: PinDirection = Field(..., description="Electrical direction of the pin")
    electrical_type: Optional[str] = Field(default=None, description="Electrical characteristics (e.g. '3.3V_LOGIC', '5V_TOLERANT')")
    max_voltage: Optional[float] = Field(default=None, description="Maximum voltage this pin can tolerate (for inputs) or output (for outputs), in volts")
    min_voltage: Optional[float] = Field(default=None, description="Minimum voltage this pin can output (for outputs), in volts. For inputs, the minimum logic-high threshold.")
    description: str = Field(default="", description="Detailed description of the pin's function")
    number: Optional[str] = Field(default=None, description="Physical pin number on the package, if known")
    supply: Optional[Literal["source", "sink"]] = Field(
        default=None,
        description="For POWER pins: 'source' if the pin supplies a rail (battery +, regulator output), 'sink' if it consumes one. None = legacy/unknown.",
    )
    nominal_voltage: Optional[float] = Field(default=None, description="Nominal voltage of a supply-source pin, in volts (unknown if None)")


class SymbolSpec(BaseModel):
    """How a component type is drawn in a schematic.

    `name` references a symbol in the schematic symbol library. `pin_map` maps the
    component's engineering pin_id -> symbol pin name. When a pin is not mapped the
    symbol pin with the same name is used; when the symbol is unknown, a generic
    IC box is generated from the pin list.
    """
    name: str = Field(..., description="Symbol library name, e.g. 'resistor', 'led', 'npn', 'ic_box'")
    pin_map: Dict[str, str] = Field(default_factory=dict, description="engineering pin_id -> symbol pin name")
    ref_prefix: Optional[str] = Field(default=None, description="Reference designator prefix (R, C, D, Q, U, ...)")
    box_sides: Dict[str, Literal["left", "right", "top", "bottom"]] = Field(
        default_factory=dict, description="For generated IC boxes: fixed side per engineering pin (others are auto-assigned)")


class PhysicalSpec(BaseModel):
    """Physical/package facts used by future physical (breadboard / 3D) projections.
    Unknown values stay None - they are never guessed."""
    package: Optional[str] = Field(default=None, description="Package, e.g. 'TO-92', 'DIP-14', 'module'")
    mounting: Optional[Literal["THT", "SMD", "module", "virtual"]] = Field(default=None)
    breadboard_compatible: Optional[bool] = Field(default=None)
    pin_pitch_mm: Optional[float] = Field(default=None)
    body_mm: Optional[List[float]] = Field(default=None, description="Approximate body size [w, l, h] in mm")
    asset_3d: Optional[str] = Field(default=None, description="Reference to a 3D asset, if one exists")


class EducationInfo(BaseModel):
    """Short, verifiable explanatory metadata (used by explain/inspect views)."""
    summary: str = Field(default="", description="One-sentence description of what the part does")
    how_it_works: str = Field(default="", description="Short explanation of the operating principle")
    typical_uses: List[str] = Field(default_factory=list)
    common_mistakes: List[str] = Field(default_factory=list)


class DesignConstraint(BaseModel):
    """A machine-checkable design rule attached to a component type.

    kinds understood by the validator:
      series_resistor      - pins must share a net with a resistor (current limiting)
      pullup_required      - each listed pin's net needs a resistor to a supply net
      flyback_diode        - listed pins (an inductive load) need a diode across them
      decoupling_capacitor - a capacitor should connect the listed supply pin to ground
    """
    kind: str
    pins: List[str] = Field(default_factory=list)
    value: Optional[str] = Field(default=None, description="Recommended value, e.g. '4.7k'")
    severity: Literal["ERROR", "WARNING", "INFO"] = "WARNING"
    note: str = ""


class ComponentType(BaseModel):
    component_type_id: str = Field(..., description="Unique identifier for the component type (e.g. 'board:esp32-devkit-v1')")
    name: str = Field(..., description="Human readable name of the component")
    short_name: Optional[str] = Field(default=None, description="Compact part name for drawings (e.g. 'HC-SR04')")
    aliases: List[str] = Field(default_factory=list, description="Alternative names for this component type")
    category: ComponentCategory = Field(..., description="Functional category of the component")
    object_type: ObjectType = Field(..., description="Type of object in the domain model")
    pins: List[PinDefinition] = Field(default_factory=list, description="Pins available on this component")
    electrical_properties: Dict[str, str] = Field(default_factory=dict, description="Inherent electrical properties")
    configurable_parameters: Dict[str, str] = Field(default_factory=dict, description="Parameters that can be configured on instances")
    curriculum_mapping: List[str] = Field(default_factory=list, description="Curriculum concepts this component supports")
    competency_level: CompetencyLevel = Field(default=CompetencyLevel.BEGINNER, description="Required competency level to use this component")
    provenance: str = Field(default="community", description="Origin of this component definition")
    license: str = Field(default="unknown", description="License of the component definition")
    asset_2d: Optional[str] = Field(default=None, description="Path or reference to 2D asset")
    asset_3d: Optional[str] = Field(default=None, description="Path or reference to 3D asset")
    simulation_model: Optional[str] = Field(default=None, description="Reference to simulation model")
    description: str = Field(default="", description="Detailed description of the component")
    validation_status: str = Field(default="proposed", description="Current validation status in the registry")
    interfaces: List[str] = Field(default_factory=list, description="Supported communication interfaces (e.g. 'I2C', 'SPI', 'PWM', 'DIGITAL', 'ANALOG')")
    roles: List[str] = Field(default_factory=list, description="Semantic roles of the component (e.g. 'SENSOR', 'ACTUATOR', 'DISPLAY', 'LOGIC')")
    requires_driver: bool = Field(default=False, description="Whether this component typically requires a dedicated hardware driver")
    recommended_control_interface: Optional[str] = Field(default=None, description="Preferred interface for controlling this component")
    # Symbol metadata for schematic representation
    symbol_library: Optional[str] = Field(default=None, description="Symbol library identifier (e.g. 'kicad', 'custom')")
    symbol_name: Optional[str] = Field(default=None, description="Symbol name within the library")
    symbol_footprint: Optional[str] = Field(default=None, description="Footprint identifier for PCB layout")
    # ── Component intelligence (2D Schematic Studio stage) ──
    family: Optional[str] = Field(default=None, description="Engineering family, e.g. 'resistor', 'led', 'bjt', 'mosfet', 'opamp', 'mcu_board'")
    tags: List[str] = Field(default_factory=list, description="Functional tags used for search and selection")
    symbol: Optional[SymbolSpec] = Field(default=None, description="Structured schematic symbol mapping")
    physical: Optional[PhysicalSpec] = Field(default=None, description="Package / physical facts for future physical projection")
    education: Optional[EducationInfo] = Field(default=None, description="Explanatory metadata")
    design_constraints: List[DesignConstraint] = Field(default_factory=list, description="Machine-checkable design rules")

class EngineeringComponentInstance(BaseModel):
    instance_id: str = Field(..., description="Unique identifier for this instance in the design (e.g. 'u1', 'd1')")
    component_type: str = Field(..., description="Reference to the ComponentType.component_type_id")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Configured parameters for this instance")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional instance metadata")

class PinRef(BaseModel):
    instance_id: str = Field(..., description="Identifier of the component instance")
    pin_id: str = Field(..., description="Identifier of the pin on the instance")

    @property
    def ref(self) -> str:
        return f"{self.instance_id}.{self.pin_id}"

    @classmethod
    def from_str(cls, s: str) -> "PinRef":
        parts = s.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid PinRef string format: {s}. Expected 'instance_id.pin_id'.")
        return cls(instance_id=parts[0], pin_id=parts[1])

class Net(BaseModel):
    net_id: str = Field(..., description="Unique identifier for this net")
    connections: List[PinRef] = Field(..., min_length=2, description="Pins connected to this net")
    net_type: Optional[str] = Field(default=None, description="Type of net (e.g. 'power', 'signal', 'ground')")

class SimulationMetadata(BaseModel):
    target: str = Field(default="none", description="Simulation target engine")
    firmware_path: Optional[str] = Field(default=None, description="Path to firmware file to run")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Simulation parameters")

class LogicCondition(BaseModel):
    input_instance: str = Field(..., description="Instance ID of the input component")
    condition: str = Field(..., description="Comparison operator (e.g., '>', '<', '==', '!=')")
    value: str = Field(..., description="Threshold or state to compare against")

class LogicAction(BaseModel):
    output_instance: str = Field(..., description="Instance ID of the output component")
    state: str = Field(..., description="Target state to apply (e.g., 'HIGH', 'LOW', 'TOGGLE')")

class LogicRule(BaseModel):
    rule_id: str = Field(..., description="Unique identifier for this rule")
    conditions: List[LogicCondition] = Field(default_factory=list, description="Conditions that trigger this rule")
    operator: str = Field(default="AND", description="Logical operator to combine conditions ('AND', 'OR')")
    actions: List[LogicAction] = Field(default_factory=list, description="Actions to execute when conditions are met")

class EngineeringDesignProject(BaseModel):
    schema_version: str = Field(default="0.2.0", description="Schema version of this design project")
    project_id: str = Field(..., description="Unique identifier for the project")
    name: str = Field(..., description="Human readable name of the project")
    description: str = Field(default="", description="Detailed description of the project")
    curriculum_context: Optional[CurriculumContext] = Field(default=None, description="Educational context")
    components: List[EngineeringComponentInstance] = Field(default_factory=list, description="Components used in the design")
    nets: List[Net] = Field(default_factory=list, description="Electrical connections between components")
    logic: List[LogicRule] = Field(default_factory=list, description="Declarative functional logic rules connecting inputs and outputs")
    simulation: Optional[SimulationMetadata] = Field(default=None, description="Simulation settings")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional project metadata")
    assumptions: List[str] = Field(default_factory=list, description="Engineering assumptions made while designing (e.g. unspecified thresholds, chosen currents)")

    @classmethod
    def resolved_schema(cls) -> dict:
        """Return the JSON schema with all $defs fully resolved."""
        return resolve_refs(cls.model_json_schema())

class ValidationError(BaseModel):
    code: str = Field(..., description="Error code (e.g. 'E001')")
    message: str = Field(..., description="Human readable error message")
    severity: ValidationSeverity = Field(..., description="Severity of the validation issue")
    affected_instances: List[str] = Field(default_factory=list, description="Instances related to this issue")
    affected_pins: List[str] = Field(default_factory=list, description="Pins related to this issue")
    affected_nets: List[str] = Field(default_factory=list, description="Nets related to this issue")
    validator: str = Field(default="", description="Name of the validator that produced this issue")

class ValidationCheck(BaseModel):
    """Record of one validation rule that was executed (for explainability)."""
    code: str
    name: str
    outcome: Literal["PASS", "FAIL", "WARN", "NOT_APPLICABLE"]


class ValidationResult(BaseModel):
    status: ValidationStatus = Field(..., description="Overall validation status")
    errors: List[ValidationError] = Field(default_factory=list, description="List of errors")
    warnings: List[ValidationError] = Field(default_factory=list, description="List of warnings")
    infos: List[ValidationError] = Field(default_factory=list, description="Advisory findings (recommended practice)")
    component_count: int = Field(default=0, description="Number of components validated")
    net_count: int = Field(default=0, description="Number of nets validated")
    checks_run: List[ValidationCheck] = Field(default_factory=list, description="Every rule executed and its outcome")