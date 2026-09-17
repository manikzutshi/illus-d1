# Design Intermediate Representation (IR) Specification

**Schema Version:** `0.2.0`  
**Implementation Source:** [`src/core/models.py`](file:///Y:/illus-d1/illustration-engine/src/core/models.py)  
**Architecture Decision:** [`ADR-003: Canonical Design IR as Single Source of Engineering Truth`](file:///Y:/illus-d1/illustration-engine/docs/decisions/ADR-003-canonical-design-ir.md)

---

## 1. Overview & Purpose

The **Canonical Design Intermediate Representation (IR)** is the authoritative engineering data model for circuits, systems, and visual illustrations in the platform. It serves as the single source of truth (SSOT) bridging probabilistic AI proposals and deterministic engineering subsystems:

- **AI Proposals:** The AI orchestrator translates natural language intent into a proposed [`DesignProject`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L82-L92).
- **Deterministic Validation:** The [`DesignValidator`](file:///Y:/illus-d1/illustration-engine/src/validation/engine.py#L5-L40) validates the model against the [`ComponentRegistry`](file:///Y:/illus-d1/illustration-engine/src/components/registry.py#L15-L96) for electrical and design rule correctness (DRC/ERC).
- **Simulation Adapters:** Translators convert the IR into external simulator formats (e.g., Wokwi JSON, SPICE netlists) without mutating canonical state.
- **Rendering Engines:** 2D schematic renderers and 3D visualizers construct scene graphs deterministically from components, nets, and layout hints.

All models are implemented using [Pydantic v2](https://docs.pydantic.dev/latest/) in [`src/core/models.py`](file:///Y:/illus-d1/illustration-engine/src/core/models.py).

---

## 2. Core Data Models

### 2.1 [`DesignProject`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L82-L92) (Top-Level Container)

The root model representing a complete, self-contained engineering project.

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | `str` | `"0.2.0"` | Schema specification version of the design project. |
| `project_id` | `str` | *Required* | Unique machine-readable identifier for the project (e.g., `"smart-parking-mvp"`). |
| `name` | `str` | *Required* | Human-readable title of the project (e.g., `"Smart Parking System"`). |
| `description` | `str` | `""` | Detailed description of the project, function, and design intent. |
| `curriculum_context` | `Optional[CurriculumContext]` | `None` | Pedagogical metadata linking the design to curriculum modules. |
| `components` | `List[ComponentInstance]` | `[]` | List of discrete component instances placed in the circuit. |
| `nets` | `List[Net]` | `[]` | List of electrical nets interconnecting component pins. |
| `simulation` | `Optional[SimulationMetadata]` | `None` | Configuration and target environment for simulation engines. |
| `metadata` | `Dict[str, str]` | `{}` | Additional key-value engineering notes, calculations, or metadata. |

---

### 2.2 [`ComponentInstance`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L50-L56)

Represents an instantiated part within the design.

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `instance_id` | `str` | *Required* | Unique instance reference designator within the design (e.g., `"u1"`, `"r1"`, `"d1"`). |
| `component_type` | `str` | *Required* | Canonical component identifier resolving to [`ComponentType.component_type_id`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L26) in the registry (e.g., `"board:esp32-devkit-v1"`, `"passive:resistor-tht"`). |
| `parameters` | `Dict[str, str]` | `{}` | Configurable parameters specific to this instance (e.g., `{"resistance": "330"}`, `{"color": "red"}`). |
| `layout` | `Optional[LayoutHints]` | `None` | Optional spatial coordinates for 2D/3D breadboard visualization. |
| `metadata` | `Dict[str, str]` | `{}` | Semantic metadata for this instance (e.g., `{"role": "distance_sensor"}`). |

---

### 2.3 [`Net`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L72-L76)

Represents an electrical net connecting two or more component pins together.

| Field | Type | Default | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `net_id` | `str` | *Required* | - | Unique identifier for this net (e.g., `"n_power"`, `"n_ground"`, `"n_trigger"`). |
| `connections` | `List[PinRef]` | *Required* | `min_length=2` | Array of pin references electrically tied to this net. A net must connect at least two pins. |
| `net_type` | `Optional[str]` | `None` | - | Classification of net function (e.g., `"power"`, `"ground"`, `"signal"`). |

---

### 2.4 [`PinRef`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L57-L70)

Represents a reference to a specific pin on a component instance.

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `instance_id` | `str` | *Required* | The `instance_id` of the referenced component instance (e.g., `"u1"`). |
| `pin_id` | `str` | *Required* | The `pin_id` on the referenced component type (e.g., `"GPIO5"`, `"VCC"`, `"GND1"`). |

#### Helper Properties and Methods:
- **`ref` property:** Returns formatted string `"{instance_id}.{pin_id}"` (e.g., `"u1.GPIO5"`).
- **`from_str(s: str) -> PinRef`:** Classmethod that parses `"instance_id.pin_id"` string formats into a `PinRef` instance.

---

### 2.5 Supporting Models

#### [`CurriculumContext`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L13-L17)
Links an engineering design to learning objectives:
- `module: str` — The curriculum module (e.g., `"Embedded Systems"`).
- `concept: str` — The specific concept being illustrated (e.g., `"Sensor Integration"`).
- `competency_level: CompetencyLevel` — Enum value: `BEGINNER`, `INTERMEDIATE`, or `ADVANCED` (default: `BEGINNER`).

#### [`LayoutHints`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L44-L49)
Optional 3D/2D coordinates for physical visualization engines:
- `x: float = 0.0` — X position.
- `y: float = 0.0` — Y position.
- `z: float = 0.0` — Z position.
- `rotation: float = 0.0` — Orientation angle in degrees.

#### [`SimulationMetadata`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L77-L81)
Parameters governing simulation environments:
- `target: str = "none"` — Simulator engine target (e.g., `"wokwi"`, `"ngspice"`, `"verilator"`).
- `firmware_path: Optional[str] = None` — Path to microcontroller source or binary.
- `parameters: Dict[str, str] = {}` — Engine-specific execution flags and settings.

---

## 3. Deliberate Exclusion of Validation State (Derived State Architecture)

> [!IMPORTANT]
> **ValidationResult is NOT a field on DesignProject.**

In earlier provisional drafts (schema version `0.1.0-PROVISIONAL`), the model contained an embedded `validation_state` object. In schema `0.2.0`, this field was **deliberately removed** in accordance with [`ADR-003`](file:///Y:/illus-d1/illustration-engine/docs/decisions/ADR-003-canonical-design-ir.md).

### Rationale:
1. **Dynamic Derivation:** Validation status is dynamic. If component pin definitions or electrical rules are updated in the [`ComponentRegistry`](file:///Y:/illus-d1/illustration-engine/src/components/registry.py#L15-L96), a previously validated design must be evaluated against the current rules. Persisting validation state inside the IR produces stale status.
2. **AI Untrusted Boundary:** AI providers cannot be allowed to claim a design is valid by simply outputting `{"validation_state": {"status": "PASS"}}`.
3. **Pure Function:** Validation is executed externally by the deterministic [`DesignValidator`](file:///Y:/illus-d1/illustration-engine/src/validation/engine.py#L5-L40):

```python
validator = DesignValidator(registry=get_default_registry())
result: ValidationResult = validator.validate(design_project)
```

### External Validation Models:
- [`ValidationResult`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L102-L108): Contains `status: ValidationStatus` (`PASS`, `FAIL`, `UNVALIDATED`), `errors: List[ValidationError]`, `warnings: List[ValidationError]`, `component_count: int`, and `net_count: int`.
- [`ValidationError`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L93-L101): Contains `code: str`, `message: str`, `severity: ValidationSeverity` (`ERROR`, `WARNING`, `INFO`), `affected_instances: List[str]`, `affected_pins: List[str]`, `affected_nets: List[str]`, and `validator: str`.

---

## 4. Schema Evolution: v0.1.0 vs v0.2.0

| Feature | v0.1.0-PROVISIONAL | v0.2.0 (Actual Implementation) | Rationale |
| :--- | :--- | :--- | :--- |
| **Components container** | `Dict[str, ComponentInstance]` | `List[ComponentInstance]` | Consistent sequence ordering; explicit `instance_id` field. |
| **Pin references** | Strings (`"u1.GND"`) | Structured [`PinRef`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L57-L70) objects | Type-safe decomposition of instance vs pin; enables validator indexing. |
| **Net connections** | Unconstrained list | `min_length=2` constraint | A net must connect at least two endpoints to be electrically meaningful. |
| **Validation state** | Embedded `validation_state` | **Excluded (Derived state)** | Enforces deterministic validator authority; prevents stale/spoofed status. |
| **Simulation metadata** | `simulation_metadata` dict | Structured [`SimulationMetadata`](file:///Y:/illus-d1/illustration-engine/src/core/models.py#L77-L81) | Type safety and default handling. |

---

## 5. Golden Reference Example: Smart Parking System

Below is the verified, golden JSON fixture ([`tests/fixtures/golden/smart_parking_valid.json`](file:///Y:/illus-d1/illustration-engine/tests/fixtures/golden/smart_parking_valid.json)) conforming to schema `0.2.0`:

```json
{
  "schema_version": "0.2.0",
  "project_id": "smart-parking-mvp",
  "name": "Smart Parking System",
  "description": "ESP32-based smart parking system using ultrasonic sensor and LED indicator. When a vehicle is detected within range, the LED turns on.",
  "curriculum_context": {
    "module": "Embedded Systems",
    "concept": "Sensor Integration",
    "competency_level": "BEGINNER"
  },
  "components": [
    {
      "instance_id": "u1",
      "component_type": "board:esp32-devkit-v1",
      "parameters": {},
      "metadata": {"role": "main_controller"}
    },
    {
      "instance_id": "s1",
      "component_type": "sensor:hc-sr04",
      "parameters": {},
      "metadata": {"role": "distance_sensor"}
    },
    {
      "instance_id": "d1",
      "component_type": "passive:led-5mm",
      "parameters": {"color": "red"},
      "metadata": {"role": "occupancy_indicator"}
    },
    {
      "instance_id": "r1",
      "component_type": "passive:resistor-tht",
      "parameters": {"resistance": "330"},
      "metadata": {"role": "led_current_limiter"}
    },
    {
      "instance_id": "pwr1",
      "component_type": "primitive:power-rail",
      "parameters": {"voltage": "5"},
      "metadata": {}
    },
    {
      "instance_id": "gnd1",
      "component_type": "primitive:ground-rail",
      "parameters": {},
      "metadata": {}
    }
  ],
  "nets": [
    {
      "net_id": "n_power",
      "connections": [
        {"instance_id": "pwr1", "pin_id": "VCC"},
        {"instance_id": "u1", "pin_id": "VIN"},
        {"instance_id": "s1", "pin_id": "VCC"}
      ],
      "net_type": "power"
    },
    {
      "net_id": "n_ground",
      "connections": [
        {"instance_id": "gnd1", "pin_id": "GND"},
        {"instance_id": "u1", "pin_id": "GND1"},
        {"instance_id": "s1", "pin_id": "GND"},
        {"instance_id": "d1", "pin_id": "CATHODE"}
      ],
      "net_type": "ground"
    },
    {
      "net_id": "n_trigger",
      "connections": [
        {"instance_id": "u1", "pin_id": "GPIO5"},
        {"instance_id": "s1", "pin_id": "TRIG"}
      ],
      "net_type": "signal"
    },
    {
      "net_id": "n_echo",
      "connections": [
        {"instance_id": "u1", "pin_id": "GPIO18"},
        {"instance_id": "s1", "pin_id": "ECHO"}
      ],
      "net_type": "signal"
    },
    {
      "net_id": "n_led_drive",
      "connections": [
        {"instance_id": "u1", "pin_id": "GPIO19"},
        {"instance_id": "r1", "pin_id": "PIN1"}
      ],
      "net_type": "signal"
    },
    {
      "net_id": "n_led_anode",
      "connections": [
        {"instance_id": "r1", "pin_id": "PIN2"},
        {"instance_id": "d1", "pin_id": "ANODE"}
      ],
      "net_type": "signal"
    }
  ],
  "simulation": {
    "target": "wokwi",
    "parameters": {}
  },
  "metadata": {
    "engineering_notes": "HC-SR04 ECHO pin outputs 5V but is connected directly to ESP32 GPIO18 (3.3V tolerant). This is a known concern in hobbyist circuits. A voltage divider is recommended for production use.",
    "resistor_calculation": "R = (3.3V - 2.0V) / 10mA = 130 ohm. Using 330 ohm for safety (approximately 3.9mA). Chosen as explicit design parameter."
  }
}
```
