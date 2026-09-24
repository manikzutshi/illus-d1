# Validation Engine: Illustration Engine

This document examines the deterministic validation engine in detail, enumerating every implemented validation rule with its specifications.

## Validator Implementation

**File:** `src/validation/engine.py`  
**Class:** `DesignValidator`

### Core Functionality
```python
class DesignValidator:
    """Deterministic validator for DesignProject instances.
    Does NOT use any LLM. All rules are explicit."""
    
    def __init__(self, registry: ComponentRegistry):
        self._registry = registry
```

### Validation Process
The `validate()` method (lines 35-70):
1. Builds lookup dictionaries for efficiency (`_instance_map`)
2. Runs all validation checks, collecting errors and warnings
3. Returns ValidationResult with status PASS if no errors, FAIL otherwise

### Helper Methods
- `_resolve_pin_def()`: Resolves (instance_id, pin_id) to PinDefinition from registry
- Various `_check_*` methods for each validation rule

## Enumerated Validation Rules

Based on the source code comments and implementation, here are all validation rules:

### Structural Rules
These check the basic integrity and connectivity of the design.

#### E001: UNKNOWN_COMPONENT_TYPE
- **File**: `src/validation/engine.py` lines 85-98
- **Method**: `_check_unknown_components()`
- **Triggering Condition**: A component's `component_type` is not found in the registry
- **What it Checks**: Validates that all component types used in instances exist in the component registry
- **What it Does NOT Check**: Does not validate that the component is appropriate for the intended use
- **Type**: Structural
- **Error Message**: "Unknown component type: {comp.component_type}"
- **Affected Data**: `affected_instances=[comp.instance_id]`

#### E002: UNKNOWN_PIN
- **File**: `src/validation/engine.py` lines 100-120
- **Method**: `_check_unknown_pins()`
- **Triggering Condition**: A PinRef references a pin that doesn't exist on the component type
- **What it Checks**: Validates that all pin references in nets correspond to actual pins on the component type
- **What it Does NOT Check**: Does not validate that the pin is being used in a semantically appropriate way
- **Type**: Structural
- **Error Message**: "Unknown pin {pinref.pin_id} on instance {pinref.instance_id}"
- **Affected Data**: 
  - `affected_instances=[pinref.instance_id]`
  - `affected_pins=[pinref.ref]`
  - `affected_nets=[net.net_id]`

#### E003: DUPLICATE_INSTANCE_ID
- **File**: `src/validation/engine.py` lines 122-137
- **Method**: `_check_duplicate_instances()`
- **Triggering Condition**: Two or more components share the same instance_id
- **What it Checks**: Ensures each component instance has a unique identifier within the design
- **What it Does NOT Check**: Does not check for semantic uniqueness (two different components serving the same purpose)
- **Type**: Structural
- **Error Message**: "Duplicate instance ID: {comp.instance_id}"
- **Affected Data**: `affected_instances=[comp.instance_id]`

#### E006: INVALID_CONNECTION_ENDPOINT
- **File**: `src/validation/engine.py` lines 173-188
- **Method**: `_check_invalid_connections()`
- **Triggering Condition**: A PinRef references an instance_id that doesn't exist in the design
- **What it Checks**: Validates that all pin references point to existing component instances
- **What it Does NOT Check**: Does not validate that the connection makes electrical sense
- **Type**: Structural
- **Error Message**: "PinRef refers to unknown instance ID: {pinref.instance_id}"
- **Affected Data**: 
  - `affected_pins=[pinref.ref]`
  - `affected_nets=[net.net_id]`

#### E008: DUPLICATE_NET_ID
- **File**: `src/validation/engine.py` lines 224-239
- **Method**: `_check_duplicate_nets()`
- **Triggering Condition**: Two or more nets share the same net_id
- **What it Checks**: Ensures each net has a unique identifier within the design
- **What it Does NOT Check**: Does not check if duplicate nets should actually be merged
- **Type**: Structural
- **Error Message**: "Duplicate net ID: {net.net_id}"
- **Affected Data**: `affected_nets=[net.net_id]`

#### E009: DISCONNECTED_COMPONENT
- **File**: `src/validation/engine.py` lines 241-259
- **Method**: `_check_disconnected_components()`
- **Triggering Condition**: A component instance has no pins connected to any net
- **What it Checks**: Validates that every component instance participates in at least one net
- **What it Does NOT Check**: Does not validate that the connections are electrically meaningful
- **Type**: Structural
- **Error Message**: "Component {comp.instance_id} is disconnected"
- **Affected Data**: `affected_instances=[comp.instance_id]`

#### E013: MULTIPLE_NETS_PER_PIN
- **File**: `src/validation/engine.py` lines 261-280
- **Method**: `_check_multiple_nets_per_pin()`
- **Triggering Condition**: A pin is referenced in more than one net
- **What it Checks**: Ensures each pin connection belongs to exactly one net (prevents shorting nets together)
- **What it Does NOT Check**: Does not allow for legitimate tri-state or shared bus scenarios
- **Type**: Structural
- **Error Message**: "Pin {pref} is connected to multiple nets: {seen_pins[pref]} and {net.net_id}"
- **Affected Data**: 
  - `affected_pins=[pref]`
  - `affected_nets=[seen_pins[pref], net.net_id]`

### Power/Ground Rules
These check for proper power and ground connections.

#### E004: MISSING_POWER
- **File**: `src/validation/engine.py` lines 139-154
- **Method**: `_check_dangling_power()`
- **Triggering Condition**: No POWER-direction pins found in any net
- **What it Checks**: Validates that at least one pin with direction POWER exists in the design
- **What it Does NOT Check**: Does not validate that the power source is adequate, properly regulated, or connected correctly
- **Type**: Electrical
- **Error Message**: "No connected POWER pins found in any net."
- **Affected Data**: None (design-wide issue)

#### E005: MISSING_GROUND
- **File**: `src/validation/engine.py` lines 156-171
- **Method**: `_check_dangling_ground()`
- **Triggering Condition**: No GROUND-direction pins found in any net
- **What it Checks**: Validates that at least one pin with direction GROUND exists in the design
- **What it Does NOT Check**: Does not validate that the ground connection is adequate or properly bonded
- **Type**: Electrical
- **Error Message**: "No connected GROUND pins found in any net."
- **Affected Data**: None (design-wide issue)

### Electrical Compatibility Rules
These check voltage levels and electrical compatibility.

#### E010: VOLTAGE_INCOMPATIBLE
- **File**: `src/validation/engine.py` lines 455-515
- **Method**: `_check_voltage_compatibility()`
- **Triggering Condition**: An OUTPUT/BIDIRECTIONAL pin's max_voltage exceeds an INPUT/BIDIRECTIONAL pin's max_voltage on the same net
- **What it Checks**: Prevents driving inputs beyond their tolerated voltage levels
- **What it Does NOT Check**: 
  - Does not account for voltage dividers or level shifting (handled separately)
  - Does not check min_voltage thresholds (only max_voltage)
  - Skips passive pins (resistors, etc.) correctly
  - Requires both pins to have max_voltage defined (otherwise W002)
- **Type**: Electrical
- **Error Message**: 
  "Voltage incompatibility on net {net.net_id}: {out_ref} outputs up to {out_voltage}V but {in_ref} tolerates max {in_max}V"
- **Affected Data**: 
  - `affected_pins=[out_ref, in_ref]`
  - `affected_nets=[net.net_id]`

#### E014: INCOMPATIBLE_OPERATING_VOLTAGE
- **File**: `src/validation/engine.py` lines 282-351
- **Method**: `_check_operating_voltage()`
- **Triggering Condition**: A component's operating voltage is incompatible with the net voltage it's connected to
- **What it Checks**: Validates that components connected to power nets receive appropriate voltage levels
- **What it Does NOT Check**: 
  - Does not account for voltage regulation onboard components
  - Complex parsing logic for voltage strings and ranges
  - Only checks POWER-direction pins on non-power-source components
- **Type**: Electrical
- **Error Message**: 
  "Component {comp.instance_id} operating voltage ({op_v_str}) is incompatible with net {net.net_id} voltage ({net_v}V)"
- **Affected Data**: 
  - `affected_instances=[comp.instance_id]`
  - `affected_nets=[net.net_id]`

#### E011: SHORT_CIRCUIT
- **File**: `src/validation/engine.py` lines 517-552
- **Method**: `_check_short_circuit()`
- **Triggering Condition**: A net connects a POWER pin directly to a GROUND pin with no intervening passive component
- **What it Checks**: Detects power-to-ground shorts without resistance or load in between
- **What it Does NOT Check**: 
  - Does not detect shorts through active components (transistors, etc.)
  - Defines "passive" narrowly (only PASSIVE, INPUT, OUTPUT, BIDIRECTIONAL count as load)
  - May false positive on intentional power-ground connections through resistors
- **Type**: Electrical
- **Error Message**: "Short circuit: net {net.net_id} connects POWER directly to GROUND with no load"
- **Affected Data**: `affected_nets=[net.net_id]`

#### E015: GPIO_OVERCURRENT
- **File**: `src/validation/engine.py` lines 353-413
- **Method**: `_check_gpio_drive_limit()`
- **Triggering Condition**: Total load current on a GPIO pin exceeds its maximum drive capacity
- **What it Checks**: Prevents overloading microcontroller GPIO pins
- **What it Does NOT Check**: 
  - Requires component to have `gpio_max_current` in electrical_properties
  - Parses current strings with regex (may miss formats)
  - Only considers outputs from MCUs as sources
  - Assumes all connected loads draw their specified operating_current
- **Type**: Electrical
- **Error Message**: 
  "GPIO {gpio_pin_ref} maximum drive current is {gpio_max_mA}mA, but load draws {total_load_mA}mA"
- **Affected Data**: 
  - `affected_pins=[gpio_pin_ref]`
  - `affected_nets=[net.net_id]`

#### E016: MISSING_POWER_SOURCE
- **File**: `src/validation/engine.py` lines 415-453
- **Method**: `_check_missing_power_source()`
- **Triggering Condition**: A net has POWER-direction pins but no valid power source component
- **What it Checks**: Ensures power nets are driven by actual power sources (not just microcontroller VIN pins)
- **What it Does NOT Check**: 
  - Complex logic to determine what constitutes a "valid" power source
  - Considers MCU VCC as valid only if it matches MCU operating voltage
  - May not recognize all valid power regulation topologies
- **Type**: Electrical
- **Error Message**: 
  "Net {net.net_id} contains POWER pins but has no valid power source (e.g. power rail or MCU regulated output)"
- **Affected Data**: `affected_nets=[net.net_id]`

### Component-Specific Rules

#### E007: LED_REQUIRES_RESISTOR
- **File**: `src/validation/engine.py` lines 190-222
- **Method**: `_check_led_resistor()`
- **Triggering Condition**: An LED instance has no resistor in series on any connected net
- **What it Checks**: Prevents connecting LEDs directly to voltage sources without current limiting
- **What it Does NOT Check**: 
  - Does not validate resistor value appropriateness
  - Only checks for specific LED component types (passive:led-5mm and passive:led prefixes)
  - Assumes resistor must be on same net as LED anode/cathode
  - Doesn't account for constant current drivers or other LED drive methods
- **Type**: Electrical
- **Error Message**: "LED {comp.instance_id} requires a resistor in series"
- **Affected Data**: `affected_instances=[comp.instance_id]`

### Logic Rules

#### E012: LOGIC_INVALID_INSTANCE
- **File**: `src/validation/engine.py` lines 554-576
- **Method**: `_check_logic_instances()`
- **Triggering Condition**: A logic rule references an instance_id that doesn't exist in the design
- **What it Checks**: Validates that all component instances referenced in logic rules actually exist
- **What it Does NOT Check**: 
  - Does not validate that the referenced components have appropriate pin types for logic
  - Does not check for timing conflicts or race conditions
  - Does not validate that the logic is functionally correct or minimal
- **Type**: Logical
- **Error Message**: 
  "Logic rule '{rule.rule_id}' references unknown input instance: {cond.input_instance}"
  (similar for output instances)
- **Affected Data**: `affected_instances=[cond.input_instance]` or `[act.output_instance]`

### Warning Rules

#### W001: MISSING_RESISTOR_VALUE
- **File**: `src/validation/engine.py` lines 579-593
- **Method**: `_check_resistor_parameters()`
- **Triggering Condition**: A resistor instance is missing the 'resistance' parameter
- **What it Checks**: Alerts when resistors lack their defining parameter
- **What it Does NOT Check**: 
  - Does not validate that the resistance value is appropriate
  - Does not check units or reasonableness of the value
  - Only applies to components whose type ID starts with 'passive:resistor'
- **Type**: Informational
- **Error Message**: "Resistor {comp.instance_id} is missing 'resistance' parameter"
- **Affected Data**: `affected_instances=[comp.instance_id]`

#### W002: VOLTAGE_NOT_CHECKABLE
- **File**: `src/validation/engine.py` lines 595-623
- **Method**: `_check_voltage_metadata_coverage()`
- **Triggering Condition**: A signal pin (INPUT/OUTPUT/BIDIRECTIONAL) lacks max_voltage definition
- **What it Checks**: Identifies missing electrical metadata that prevents voltage compatibility checking
- **What it Does NOT Check**: 
  - Does not check for missing min_voltage
  - Does not check for missing electrical_type or other voltage-related fields
  - Only applies to signal-direction pins (excludes PASSIVE, POWER, GROUND)
- **Type**: Informational
- **Error Message**: 
  "Voltage metadata missing for {pinref.ref}: cannot verify voltage compatibility"
- **Affected Data**: 
  - `affected_pins=[pinref.ref]`
  - `affected_nets=[net.net_id]`

## Validator Blind Spots Relevant to Schematic Generation

### Missing Electrical Checks
1. **Power Budget Validation**: No validation of total power consumption vs. supply capacity
2. **Current Density**: No checks for trace width/via sizing based on current
3. **Impedance Matching**: No validation for high-speed signal requirements
4. **Decoupling Capacitors**: No validation for adequate power supply decoupling
5. **Thermal Validation**: No junction temperature or power dissipation validation
6. **Signal Integrity**: No validation for reflection, crosstalk, or grounding issues

### Missing Logical Checks
1. **Timing Analysis**: No setup/hold time validation, clock frequency checking
2. **Resource Validation**: No validation of peripheral pin conflicts (e.g., two peripherals needing same UART)
3. **Memory Mapping**: No validation of address space overlaps
4. **Interrupt Validation**: No validation of interrupt vector conflicts or priority issues

### Missing Structural Checks
1. **Physical Layout**: No validation of component footprint clearance or mechanical interference
2. **Manufacturing Constraints**: No validation of minimum trace width, drill sizes, etc.
3. **Test Point Accessibility**: No validation that test points are reachable
4. **Thermal Relief**: No validation of adequate thermal relief for soldering

### Component-Specific Limitations
1. **Analog Component Validation**: Limited validation of analog signal ranges, impedance, bandwidth
2. **Communication Protocol Validation**: No validation of bus speeds, pull-up requirements, termination
3. **Mechanical Validation**: No validation of connector mating, cable strain relief, mounting
4. **Optical Validation**: No validation of LED current vs. brightness, sensor field of view

### Current Implementation Limitations
1. **Passive Component Handling in Voltage Checks**: Correctly skips passives, but doesn't model their actual electrical effect (voltage dividers are handled by checking endpoints)
2. **Complex Power Topologies**: May not recognize valid power regulation schemes (LDOs, switching regulators)
3. **Bidirectional Pin Modeling**: Complex logic for determining pin directionality in different contexts
4. **Voltage Parsing**: Fragile parsing of voltage strings like "3.3V-5V" may fail on edge cases
5. **Temperature Dependence**: No accounting for temperature effects on electrical characteristics

## Evidence from Source Code

### Deterministic Nature
From file header comments (lines 21-22):
```
All rules are deterministic. No LLM dependency.
```

### Validation Flow
From `validate()` method (lines 35-70):
- Builds `_instance_map` for efficient lookups
- Calls each `_check_*` method in sequence
- Accumulates errors and warnings
- Returns FAIL status if any errors exist

### Example: Voltage Incompatibility Check
Lines 455-515 show sophisticated logic:
- Separates output-capable and input-capable pins on each net
- Skips PASSIVE, POWER, GROUND pins (correctly transparent to voltage checking)
- Compares each output's max_voltage against each input's max_voltage
- Skips pairs where voltage data is missing (triggers W002 instead)
- Detailed error reporting showing specific pins and net

### Example: LED Resistor Check
Lines 190-222:
- First identifies all nets containing resistors
- Then checks each LED to see if it shares a net with any resistor
- Binary pass/fail: either has resistor or doesn't
- Doesn't validate resistor size appropriateness

### Example: GPIO Overcurrent Check
Lines 353-413:
- Finds GPIO pins on microcontrollers
- Parses `gpio_max_current` from electrical_properties
- Sums `operating_current` from all connected loads
- Compares total load against GPIO capacity
- Makes assumptions about load current consumption

## Validation Result Structure

**File:** `src/core/models.py` lines 145-151
```python
class ValidationResult(BaseModel):
    status: ValidationStatus = Field(..., description="Overall validation status")
    errors: List[ValidationError] = Field(default_factory=list, description="List of errors")
    warnings: List[ValidationError] = Field(default_factory=list, description="List of warnings")
    component_count: int = Field(default=0, description="Number of components validated")
    net_count: int = Field(default=0, description="Number of nets validated")
```

## Test Coverage Evidence

From `tests/unit/test_validation.py`:
- Tests for every error code (E001-E016) and warning code (W001-W002)
- Golden fixtures showing valid and invalid designs for each rule
- Determinism tests showing identical results on repeated validation
- Edge case tests (empty design, duplicate IDs, etc.)
- Complex scenario tests (voltage compatibility, GPIO overcurrent, etc.)

## Conclusion

The validation engine provides comprehensive structural, electrical, and logical checking with 16 error codes and 2 warning codes. It successfully catches common beginner mistakes like missing power/ground, loose wires, LED-resistor omissions, and voltage mismatches.

The rules are deterministic and LLM-independent, fulfilling the "AI Proposes, Determinism Disposes" philosophy. However, for advancing to a full 2D schematic renderer with advanced validation capabilities, the current implementation would need enhancements in power analysis, signal integrity, timing validation, and physical design rule checking.

The validator's clean separation from the AI layer makes it an excellent foundation that can be extended without affecting the proposal generation logic.