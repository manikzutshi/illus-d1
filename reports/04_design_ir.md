# Design Intermediate Representation (IR): Illustration Engine

This document examines the actual Pydantic model hierarchy that constitutes the Design IR in the Illustration Engine system.

## Design IR Source
**File:** `src/core/models.py`  
**Primary Class:** `DesignProject`

## Complete Model Hierarchy

### 1. Enumerations (from `src/core/enums.py`)
These define the standardized values used throughout the IR:

```python
class CompetencyLevel(str, Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"

class PinDirection(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    POWER = "POWER"
    GROUND = "GROUND"
    PASSIVE = "PASSIVE"

class ComponentCategory(str, Enum):
    MICROCONTROLLER = "MICROCONTROLLER"
    SENSOR = "SENSOR"
    PASSIVE_COMPONENT = "PASSIVE_COMPONENT"
    ACTIVE_COMPONENT = "ACTIVE_COMPONENT"
    CONNECTOR = "CONNECTOR"
    POWER_SOURCE = "POWER_SOURCE"
    GROUND_NODE = "GROUND_NODE"
    ROUTING = "ROUTING"

class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNVALIDATED = "UNVALIDATED"
    NOT_CHECKABLE = "NOT_CHECKABLE"

class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

class ObjectType(str, Enum):
    PHYSICAL = "PHYSICAL"
    CIRCUIT_PRIMITIVE = "CIRCUIT_PRIMITIVE"
    DIGITAL_PRIMITIVE = "DIGITAL_PRIMITIVE"
    RTL_OBJECT = "RTL_OBJECT"
    SEMICONDUCTOR_PRIMITIVE = "SEMICONDUCTOR_PRIMITIVE"
    VERIFICATION_OBJECT = "VERIFICATION_OBJECT"
    VISUALIZATION_PRIMITIVE = "VISUALIZATION_PRIMITIVE"
    PACKAGING_OBJECT = "PACKAGING_OBJECT"
```

### 2. Supporting Models

#### CurriculumContext
```python
class CurriculumContext(BaseModel):
    module: str = Field(..., description="The curriculum module this concept belongs to")
    concept: str = Field(..., description="The specific concept being illustrated")
    competency_level: CompetencyLevel = Field(default=CompetencyLevel.BEGINNER, description="Target competency level")
```

#### PinDefinition
```python
class PinDefinition(BaseModel):
    pin_id: str = Field(..., description="Identifier for the pin (e.g. 'GPIO5', 'VCC', 'TRIG')")
    name: str = Field(..., description="Human readable name of the pin")
    direction: PinDirection = Field(..., description="Electrical direction of the pin")
    electrical_type: Optional[str] = Field(default=None, description="Electrical characteristics (e.g. '3.3V_LOGIC', '5V_TOLERANT')")
    max_voltage: Optional[float] = Field(default=None, description="Maximum voltage this pin can tolerate (for inputs) or output (for outputs), in volts")
    min_voltage: Optional[float] = Field(default=None, description="Minimum voltage this pin can output (for outputs), in volts. For inputs, the minimum logic-high threshold.")
    description: str = Field(default="", description="Detailed description of the pin's function")
```

#### ComponentType
```python
class ComponentType(BaseModel):
    component_type_id: str = Field(..., description="Unique identifier for the component type (e.g. 'board:esp32-devkit-v1')")
    name: str = Field(..., description="Human readable name of the component")
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
```

#### LayoutHints
```python
class LayoutHints(BaseModel):
    x: float = Field(default=0.0, description="X coordinate")
    y: float = Field(default=0.0, description="Y coordinate")
    z: float = Field(default=0.0, description="Z coordinate")
    rotation: float = Field(default=0.0, description="Rotation angle in degrees")
```

#### ComponentInstance
```python
class ComponentInstance(BaseModel):
    instance_id: str = Field(..., description="Unique identifier for this instance in the design (e.g. 'u1', 'd1')")
    component_type: str = Field(..., description="Reference to the ComponentType.component_type_id")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Configured parameters for this instance")
    layout: Optional[LayoutHints] = Field(default=None, description="Placement hints for visualization")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional instance metadata")
```

#### PinRef
```python
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
```

#### Net
```python
class Net(BaseModel):
    net_id: str = Field(..., description="Unique identifier for this net")
    connections: List[PinRef] = Field(..., min_length=2, description="Pins connected to this net")
    net_type: Optional[str] = Field(default=None, description="Type of net (e.g. 'power', 'signal', 'ground')")
```

#### SimulationMetadata
```python
class SimulationMetadata(BaseModel):
    target: str = Field(default="none", description="Simulation target engine")
    firmware_path: Optional[str] = Field(default=None, description="Path to firmware file to run")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Simulation parameters")
```

#### LogicCondition
```python
class LogicCondition(BaseModel):
    input_instance: str = Field(..., description="Instance ID of the input component")
    condition: str = Field(..., description="Comparison operator (e.g., '>', '<', '==', '!=')")
    value: str = Field(..., description="Threshold or state to compare against")
```

#### LogicAction
```python
class LogicAction(BaseModel):
    output_instance: str = Field(..., description="Instance ID of the output component")
    state: str = Field(..., description="Target state to apply (e.g., 'HIGH', 'LOW', 'TOGGLE')")
```

#### LogicRule
```python
class LogicRule(BaseModel):
    rule_id: str = Field(..., description="Unique identifier for this rule")
    conditions: List[LogicCondition] = Field(default_factory=list, description="Conditions that trigger this rule")
    operator: str = Field(default="AND", description="Logical operator to combine conditions ('AND', 'OR')")
    actions: List[LogicAction] = Field(default_factory=list, description="Actions to execute when conditions are met")
```

#### ValidationError
```python
class ValidationError(BaseModel):
    code: str = Field(..., description="Error code (e.g. 'E001')")
    message: str = Field(..., description="Human readable error message")
    severity: ValidationSeverity = Field(..., description="Severity of the validation issue")
    affected_instances: List[str] = Field(default_factory=list, description="Instances related to this issue")
    affected_pins: List[str] = Field(default_factory=list, description="Pins related to this issue")
    affected_nets: List[str] = Field(default_factory=list, description="Nets related to this issue")
    validator: str = Field(default="", description="Name of the validator that produced this issue")
```

#### ValidationResult
```python
class ValidationResult(BaseModel):
    status: ValidationStatus = Field(..., description="Overall validation status")
    errors: List[ValidationError] = Field(default_factory=list, description="List of errors")
    warnings: List[ValidationError] = Field(default_factory=list, description="List of warnings")
    component_count: int = Field(default=0, description="Number of components validated")
    net_count: int = Field(default=0, description="Number of nets validated")
```

### 3. Top-Level Model: DesignProject
```python
class DesignProject(BaseModel):
    schema_version: str = Field(default="0.2.0", description="Schema version of this design project")
    project_id: str = Field(..., description="Unique identifier for the project")
    name: str = Field(..., description="Human readable name of the project")
    description: str = Field(default="", description="Detailed description of the project")
    curriculum_context: Optional[CurriculumContext] = Field(default=None, description="Educational context")
    components: List[ComponentInstance] = Field(default_factory=list, description="Components used in the design")
    nets: List[Net] = Field(default_factory=list, description="Electrical connections between components")
    logic: List[LogicRule] = Field(default_factory=list, description="Declarative functional logic rules connecting inputs and outputs")
    simulation: Optional[SimulationMetadata] = Field(default=None, description="Simulation settings")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional project metadata")

    @classmethod
    def resolved_schema(cls) -> dict:
        """Return the JSON schema with all $defs fully resolved."""
        schema = cls.model_json_schema()
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
```

## Field Classification Analysis

For each field in the Design IR, I'll classify it as:
- **A. Authoritative engineering data**: Core electrical/logical properties that determine circuit behavior
- **B. Model-generated proposal**: Data that comes from AI generation and may be refined
- **C. Derived data**: Computed from other fields, not stored independently
- **D. Presentation metadata**: UI/display information not affecting functionality

### DesignProject Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `schema_version` | D | Version tracking for schema evolution |
| `project_id` | A | Unique identifier for the design (authoritative) |
| `name` | D | Human-readable name (presentation) |
| `description` | D | Detailed description (presentation/documentation) |
| `curriculum_context` | B | Educational context from AI requirements extraction |
| `components` | A | List of component instances (core design data) |
| `nets` | A | Electrical connections (core design data) |
| `logic` | A | Declarative functional rules (core design data) |
| `simulation` | B/C | Simulation target (AI-proposed) + parameters (could be derived) |
| `metadata` | D | Arbitrary key-value pairs (presentation/extensibility) |

### ComponentInstance Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `instance_id` | A | Unique instance identifier (authoritative) |
| `component_type` | A | Reference to component type (authoritative) |
| `parameters` | A | Configured parameters (authoritative - affects behavior) |
| `layout` | D | Placement hints (visualization only) |
| `metadata` | D | Additional instance metadata (presentation/extensibility) |

### ComponentType Fields (from registry)

| Field | Classification | Justification |
|-------|---------------|---------------|
| `component_type_id` | A | Unique type identifier (authoritative) |
| `name` | D | Human-readable name (presentation) |
| `aliases` | D | Alternative names (presentation/search) |
| `category` | A | Functional category (authoritative - determines behavior) |
| `object_type` | A | Domain object type (authoritative - determines behavior) |
| `pins` | A | Pin definitions (authoritative - core electrical interface) |
| `electrical_properties` | A | Inherent electrical properties (authoritative - affects validation) |
| `configurable_parameters` | A | User-configurable parameters (authoritative - affects behavior) |
| `curriculum_mapping` | B | Educational concept mapping (AI-generated/provided) |
| `competency_level` | B | Required skill level (AI-generated/provided) |
| `provenance` | D | Origin tracking (presentation/audit) |
| `license` | D | Licensing info (presentation/legal) |
| `asset_2d`/`asset_3d` | D | Asset references (presentation/visualization) |
| `simulation_model` | B/C | Simulation reference (AI-proposed, could be derived) |
| `description` | D | Detailed description (presentation/documentation) |
| `validation_status` | D | Registry status (presentation/process) |
| `interfaces` | A | Supported interfaces (authoritative - determines connectivity) |
| `roles` | A | Semantic roles (authoritative - determines usage) |
| `requires_driver` | A | Driver requirement (authoritative - affects integration) |
| `recommended_control_interface` | B | Preferred control (AI-generated/provided) |

### PinDefinition Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `pin_id` | A | Pin identifier (authoritative - part of interface) |
| `name` | D | Human-readable name (presentation) |
| `direction` | A | Electrical direction (authoritative - determines connectivity) |
| `electrical_type` | A | Electrical characteristics (authoritative - affects validation) |
| `max_voltage` | A | Voltage limits (authoritative - affects validation) |
| `min_voltage` | A | Voltage limits (authoritative - affects validation) |
| `description` | D | Detailed description (presentation/documentation) |

### Net Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `net_id` | A | Net identifier (authoritative) |
| `connections` | A | Pin connections (authoritative - defines topology) |
| `net_type` | B/C | Net classification (could be AI-proposed or derived from connections) |

### LogicRule Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `rule_id` | A | Rule identifier (authoritative) |
| `conditions` | A | Trigger conditions (authoritative - defines behavior) |
| `operator` | A | Logic combination (authoritative - defines behavior) |
| `actions` | A | Output actions (authoritative - defines behavior) |

### LogicCondition Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `input_instance` | A | Input component reference (authoritative) |
| `condition` | A | Comparison operator (authoritative) |
| `value` | A | Threshold/state value (authoritative) |

### LogicAction Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `output_instance` | A | Output component reference (authoritative) |
| `state` | A | Target state (authoritative) |

### ValidationResult Fields

| Field | Classification | Justification |
|-------|---------------|---------------|
| `status` | C | Derived from errors/warnings (PASS if empty errors) |
| `errors` | A | Validation failures (authoritative - deterministically computed) |
| `warnings` | A | Validation warnings (authoritative - deterministically computed) |
| `component_count` | C | Derived from len(components) |
| `net_count` | C | Derived from len(nets) |

### Supporting Models Fields

| Model | Field | Classification | Justification |
|-------|-------|---------------|---------------|
| CurriculumContext | module | B | Educational module (AI-generated/provided) |
| CurriculumContext | concept | B | Specific concept (AI-generated/provided) |
| CurriculumContext | competency_level | B | Target level (AI-generated/provided) |
| LayoutHints | x/y/z/rotation | D | Visualization coordinates (presentation only) |
| SimulationMetadata | target | B/C | Simulation engine (AI-proposed) |
| SimulationMetadata | firmware_path | B | Firmware reference (AI-proposed) |
| SimulationMetadata | parameters | B/C | Sim parameters (AI-proposed or derived) |

## Key Observations About the Design IR

### Strengths
1. **Clear Separation**: Distinction between authoritative data (A) and presentation/data (D) is well-maintained
2. **Extensibility**: Uses `metadata` fields for extensibility without breaking core schema
3. **Deterministic Core**: All validation-relevant fields are classified as authoritative (A)
4. **Rich Typing**: Uses Pydantic's strong typing with custom enums for domain concepts
5. **Reference Integrity**: Uses string references (`component_type`, `instance_id`) that are validated by the engine

### Limitations and Gaps
1. **Limited Layout Information**: `LayoutHints` only has basic coordinates/rotation, no routing information
2. **No Physical Properties**: Missing dimensions, package types, mounting hole info for physical layout
3. **Signal Flow Logic**: Logic rules are present but no timing or sequencing information
4. **Power Analysis**: No power budget fields or energy consumption tracking
5. **Thermal Info**: No temperature ratings, power dissipation requirements, or cooling needs
6. **Manufacturing Info**: No footprint, assembly instructions, or test points
7. **Versioning Granularity**: Schema version is at project level, not component level
8. **Electrical Modeling**: Basic voltage/current checks but no impedance, frequency response, or noise analysis

### Evidence from Source Code

#### Authoritative Usage in Validation
From `src/validation/engine.py`:
- Uses `component.component_type` to look up in registry (line 77, 80, 107, etc.)
- Uses `pin.direction` to determine electrical behavior (lines 144, 160, 336, etc.)
- Uses `pin.max_voltage` for voltage compatibility checking (lines 491, 498)
- Uses `net.connections` to build connectivity maps (lines 45, 246, 267, etc.)
- Uses `logic.conditions` and `logic.actions` for logic validation (lines 558-576)

#### Model-Generated Evidence
From `src/ai/orchestrator.py`:
- Sets `curriculum_context` during requirements extraction (lines 233-248)
- Uses `provider.structured_generate(..., DesignProject)` for proposal generation (lines 328, 365)
- AI is responsible for proposing reasonable `parameters`, `connections`, `logic`

#### Presentation Metadata Evidence
- `layout` fields default to None/zero and are only used in frontend renderer
- `metadata` fields store arbitrary key-value pairs for extensibility
- `description` fields are purely for human consumption
- `name` fields are for display purposes

## Schema Resolution Mechanism

The `resolved_schema()` method in DesignProject (lines 115-134) demonstrates how the system handles Pydantic's internal referencing:
1. Gets base JSON schema via `model_json_schema()`
2. Pops out `$defs` section containing referenced schemas
3. Recursively resolves `$ref` pointers by looking them up in `$defs`
4. Returns a flattened schema with all references resolved

This is used for AI structured generation to provide the complete schema to providers.

## Comparison with Golden Fixtures

Examining `tests/fixtures/golden/smart_parking_valid.json` shows:
- All required fields present per the model
- `curriculum_context` populated with educational info
- `parameters` used for component configuration (resistance values, LED color)
- `metadata` used for roles and documentation
- Empty `{}` for optional objects when not used
- `layout` fields omitted (default to None)
- `simulation` present with target and empty parameters

## Conclusion

The Design IR in Illustration Engine is a well-structured Pydantic model that successfully separates:
- **Authoritative engineering data** (component types, instances, connections, logic, electrical properties)
- **AI-generated/proposal data** (curriculum context, some parameters, simulation targets)
- **Presentation metadata** (names, descriptions, layout hints, arbitrary metadata)

The core innovation is maintaining a clean boundary where the deterministic validation engine operates only on the authoritative data, ensuring correctness regardless of AI proposal quality. The IR is sufficiently rich to support the current validation rules and provides clear extension points for future capabilities like 2D schematic generation.

The primary limitations for advancing to a full 2D schematic renderer are:
1. Lack of detailed physical/package information in components
2. Limited routing/net geometry information
3. Absence of layer information for PCB design
4. No constraint-driven layout specifications

However, the IR's extensibility through `metadata` fields and the clean separation of concerns make it suitable for evolution toward the target architecture.