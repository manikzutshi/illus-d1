# Component Registry: Illustration Engine

This document examines the component registry implementation and enumerates all currently supported components with their detailed specifications.

## Registry Implementation

**File:** `src/components/registry.py`  
**Class:** `ComponentRegistry`

### Core Functionality

#### Loading Mechanism
```python
def load_yaml(self, path: Path) -> int:
    """Load component types from a YAML file. Returns count of components loaded.
    The YAML has a top-level 'components' key mapping component_type_id to properties.
    Each entry must be parseable into a ComponentType model.
    When loading, the key itself is the component_type_id and must be injected into the dict before parsing."""
```
- Resolves path relative to project root (`_PROJECT_ROOT`)
- Loads YAML file with UTF-8 encoding
- Expects top-level `components` key containing dictionary
- For each entry, injects `component_type_id` equal to the key before validation
- Uses `ComponentType.model_validate()` for Pydantic validation
- Handles duplicates, validation errors, and unexpected exceptions gracefully
- Returns count of successfully loaded components

#### Component Access Methods
```python
def get(self, component_type_id: str) -> Optional[ComponentType]:
    """Get a component type by its canonical ID. Returns None if not found."""
    return self._types.get(component_id)

def search(self, query: str) -> list[ComponentType]:
    """Search by name, alias, type ID, or description (for intent). Case-insensitive substring match."""
    query_lower = query.lower()
    results: list[ComponentType] = []
    for comp in self._types.values():
        # Primary match: component_type_id or name
        if query_lower in comp.component_type_id.lower() or query_lower in comp.name.lower():
            results.append(comp)
            continue
        
        # Alias match
        if any(query_lower in alias.lower() for alias in comp.aliases):
            results.append(comp)
            continue
        
        # Role match
        if any(query_lower in role.lower() for role in comp.roles):
            results.append(comp)
            continue
        
        # Interface match
        if any(query_lower in iface.lower() for iface in comp.interfaces):
            results.append(comp)
            continue
        
        # Description/intent match
        if query_lower in comp.description.lower():
            results.append(comp)
            
    return results

def list_all(self) -> list[ComponentType]:
    """Return all registered component types."""
    return list(self._types.values())

def has(self, component_type_id: str) -> bool:
    """Check if a component type exists."""
    return component_type_id in self._types

@property
def count(self) -> int:
    """Number of registered component types."""
    return len(self._types)
```

### Default Registry Loader
**Function:** `get_default_registry() -> ComponentRegistry`  
**Location:** Lines 116-121  
- Creates new ComponentRegistry instance
- Loads from `_DEFAULT_REGISTRY_PATH` (`data/components/registry.yaml`)
- Returns populated registry

## Component Definitions

**Source File:** `data/components/registry.yaml`  
**Format:** YAML with top-level `components:` key

Let me enumerate all components with their complete specifications:

### 1. board:esp32-devkit-v1
```yaml
board:esp32-devkit-v1:
  name: ESP32-DevKitC V1
  aliases: [esp32, esp32-devkit]
  category: MICROCONTROLLER
  object_type: PHYSICAL
  description: ESP32-DevKitC V1 (30-pin) development board
  pins:
    - pin_id: VIN
      name: VIN
      direction: POWER
      electrical_type: 5V
      max_voltage: 12.0
      description: 5V input (regulated down to 3.3V on-board)
    - pin_id: 3V3
      name: 3V3
      direction: POWER
      electrical_type: 3.3V
      max_voltage: 3.3
      description: 3.3V regulated output
    - [28 GROUND pins: GND1-GND3]
    - [26 GPIO pins: GPIO2, GPIO4-GPIO5, GPIO12-GPIO19, GPIO21-GPIO27, GPIO32-GPIO33]
      (all: direction: BIDIRECTIONAL, electrical_type: 3.3V_LOGIC, max_voltage: 3.6)
    - pin_id: EN
      name: EN
      direction: INPUT
      max_voltage: 3.6
      description: active-high enable
  electrical_properties:
    operating_voltage: 3.3V
    input_voltage_max: 12V
    gpio_max_current: 40mA
    gpio_abs_max_voltage: 3.6V
    wifi: 802.11 b/g/n
    bluetooth: BLE 4.2
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL, ANALOG, I2C, SPI, UART, PWM]
  roles: [LOGIC, POWER]
  requires_driver: false
```

### 2. sensor:hc-sr04
```yaml
sensor:hc-sr04:
  name: HC-SR04 Ultrasonic Distance Sensor
  aliases: [hc-sr04, ultrasonic]
  category: SENSOR
  object_type: PHYSICAL
  description: "HC-SR04 Ultrasonic Distance Sensor. ECHO pin outputs 5V logic — requires level shifting when connecting to 3.3V microcontrollers."
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      electrical_type: 5V
      max_voltage: 5.0
      description: 5V power input
    - pin_id: TRIG
      name: TRIG
      direction: INPUT
      electrical_type: 5V_TOLERANT
      max_voltage: 5.0
      description: Trigger input. Accepts 3.3V logic high.
    - pin_id: ECHO
      name: ECHO
      direction: OUTPUT
      electrical_type: 5V
      max_voltage: 5.0
      min_voltage: 4.8
      description: Echo output. Outputs 5V pulse proportional to distance. REQUIRES level shifting for 3.3V MCUs.
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties:
    operating_voltage: 5V
    measuring_range: 2cm-400cm
    trigger_pulse: 10us
    echo_output_voltage: 5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [SENSOR]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 3. passive:led-5mm
```yaml
passive:led-5mm:
  name: Generic 5mm LED
  aliases: [led, 5mm-led]
  category: PASSIVE_COMPONENT
  object_type: PHYSICAL
  description: Generic 5mm through-hole LED
  pins:
    - pin_id: ANODE
      name: ANODE
      direction: PASSIVE
    - pin_id: CATHODE
      name: CATHODE
      direction: PASSIVE
  electrical_properties:
    forward_voltage_typical: 2.0V
    forward_voltage_max: 2.4V
    max_forward_current: 20mA
    recommended_current: 10mA
  configurable_parameters:
    color: enum
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL, PWM]
  roles: [ACTUATOR, DISPLAY]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 4. passive:resistor-tht
```yaml
passive:resistor-tht:
  name: Generic Resistor THT
  aliases: [resistor]
  category: PASSIVE_COMPONENT
  object_type: PHYSICAL
  description: Generic through-hole resistor
  pins:
    - pin_id: PIN1
      name: PIN1
      direction: PASSIVE
    - pin_id: PIN2
      name: PIN2
      direction: PASSIVE
  electrical_properties:
    power_rating: 0.25W
  configurable_parameters:
    resistance: ohm
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: []
  roles: [POWER, LOGIC]
  requires_driver: false
```

### 5. passive:push-button-tactile
```yaml
passive:push-button-tactile:
  name: Tactile Push Button
  aliases: [button, push-button]
  category: PASSIVE_COMPONENT
  object_type: PHYSICAL
  description: Tactile push button (4-pin, 2 connected pairs)
  pins:
    - pin_id: PIN1A
      name: PIN1A
      direction: PASSIVE
    - pin_id: PIN1B
      name: PIN1B
      direction: PASSIVE
    - pin_id: PIN2A
      name: PIN2A
      direction: PASSIVE
    - pin_id: PIN2B
      name: PIN2B
      direction: PASSIVE
  electrical_properties:
    max_voltage: 12V
    max_current: 50mA
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [INPUT]
  requires_driver: false
```

### 6. primitive:power-rail
```yaml
primitive:power-rail:
  name: Power Rail
  aliases: [power, vcc]
  category: POWER_SOURCE
  object_type: CIRCUIT_PRIMITIVE
  description: Represents a power source rail
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
  electrical_properties:
    voltage: 5V
  configurable_parameters:
    voltage: V
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: []
  roles: [POWER]
  requires_driver: false
```

### 7. primitive:ground-rail
```yaml
primitive:ground-rail:
  name: Ground Rail
  aliases: [ground, gnd]
  category: GROUND_NODE
  object_type: CIRCUIT_PRIMITIVE
  description: Represents a ground node
  pins:
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties: {}
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: []
  roles: [POWER]
  requires_driver: false
```

### 8. routing:jumper-wire
```yaml
routing:jumper-wire:
  name: Jumper Wire
  aliases: [wire, jumper]
  category: ROUTING
  object_type: CIRCUIT_PRIMITIVE
  description: Represents a jumper wire connection
  pins:
    - pin_id: PIN1
      name: PIN1
      direction: PASSIVE
    - pin_id: PIN2
      name: PIN2
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: []
  roles: []
  requires_driver: false
```

### 9. passive:capacitor-ceramic
```yaml
passive:capacitor-ceramic:
  name: Ceramic Capacitor
  aliases: [capacitor, ceramic-cap]
  category: PASSIVE_COMPONENT
  object_type: PHYSICAL
  description: Generic ceramic capacitor (non-polarized)
  pins:
    - pin_id: PIN1
      name: PIN1
      direction: PASSIVE
    - pin_id: PIN2
      name: PIN2
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters:
    capacitance: F
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: []
  roles: [POWER]
  requires_driver: false
```

### 10. passive:capacitor-electrolytic
```yaml
passive:capacitor-electrolytic:
  name: Electrolytic Capacitor
  aliases: [capacitor, electrolytic-cap]
  category: PASSIVE_COMPONENT
  object_type: PHYSICAL
  description: Polarized electrolytic capacitor
  pins:
    - pin_id: ANODE
      name: ANODE
      direction: PASSIVE
    - pin_id: CATHODE
      name: CATHODE
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters:
    capacitance: F
    max_voltage: V
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: []
  roles: [POWER]
  requires_driver: false
```

### 11. sensor:photoresistor
```yaml
sensor:photoresistor:
  name: Photoresistor (LDR)
  aliases: [ldr, light-sensor, photoresistor]
  category: SENSOR
  object_type: PHYSICAL
  description: Light Dependent Resistor
  pins:
    - pin_id: PIN1
      name: PIN1
      direction: PASSIVE
    - pin_id: PIN2
      name: PIN2
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [ANALOG]
  roles: [SENSOR]
  requires_driver: false
```

### 12. sensor:dht11
```yaml
sensor:dht11:
  name: DHT11 Temperature & Humidity Sensor
  aliases: [dht11, temperature-sensor, humidity-sensor]
  category: SENSOR
  object_type: PHYSICAL
  description: Digital temperature and humidity sensor
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.5
    - pin_id: DATA
      name: DATA
      direction: BIDIRECTIONAL
      electrical_type: DIGITAL
      max_voltage: 5.5
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties:
    operating_voltage: 3.3V-5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [SENSOR]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 13. sensor:hc-sr501
```yaml
sensor:hc-sr501:
  name: HC-SR501 PIR Motion Sensor
  aliases: [pir, motion-sensor]
  category: SENSOR
  object_type: PHYSICAL
  description: Passive Infrared motion sensor
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 12.0
    - pin_id: OUT
      name: OUT
      direction: OUTPUT
      electrical_type: 3.3V_LOGIC
      max_voltage: 3.3
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties:
    operating_voltage: 4.5V-20V
    output_voltage: 3.3V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [SENSOR]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 14. actuator:buzzer-piezo
```yaml
actuator:buzzer-piezo:
  name: Piezo Buzzer
  aliases: [buzzer, piezo]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Active piezo buzzer
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties:
    operating_voltage: 3.3V-5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL, PWM]
  roles: [ACTUATOR]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 15. actuator:servo-sg90
```yaml
actuator:servo-sg90:
  name: SG90 Micro Servo Motor
  aliases: [servo, sg90, motor]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Standard 9g micro servo motor
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 6.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: PWM
      name: PWM
      direction: INPUT
      electrical_type: 5V_TOLERANT
      max_voltage: 5.0
  electrical_properties:
    operating_voltage: 4.8V-6.0V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [PWM]
  roles: [ACTUATOR]
  requires_driver: false
  recommended_control_interface: PWM
```

### 16. active:transistor-npn-2n2222
```yaml
active:transistor-npn-2n2222:
  name: 2N2222 NPN Transistor
  aliases: [npn, transistor, 2n2222]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Standard NPN bipolar junction transistor
  pins:
    - pin_id: C
      name: COLLECTOR
      direction: PASSIVE
    - pin_id: B
      name: BASE
      direction: PASSIVE
    - pin_id: E
      name: EMITTER
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [ANALOG, DIGITAL]
  roles: [LOGIC]
  requires_driver: false
```

### 17. passive:potentiometer
```yaml
passive:potentiometer:
  name: Potentiometer
  aliases: [pot, variable-resistor]
  category: PASSIVE_COMPONENT
  object_type: PHYSICAL
  description: Variable resistor/voltage divider
  pins:
    - pin_id: VCC
      name: VCC
      direction: PASSIVE
    - pin_id: OUT
      name: WIPER
      direction: PASSIVE
    - pin_id: GND
      name: GND
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters:
    resistance: ohm
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [ANALOG]
  roles: [INPUT]
  requires_driver: false
```

### 18. sensor:thermistor
```yaml
sensor:thermistor:
  name: Thermistor
  aliases: [temperature-dependent resistor, ntc, ptc]
  category: SENSOR
  object_type: PHYSICAL
  description: Temperature dependent resistor
  pins:
    - pin_id: PIN1
      name: PIN1
      direction: PASSIVE
    - pin_id: PIN2
      name: PIN2
      direction: PASSIVE
  electrical_properties: {}
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [ANALOG]
  roles: [SENSOR]
  requires_driver: false
```

### 19. sensor:ds18b20
```yaml
sensor:ds18b20:
  name: DS18B20 Temperature Sensor
  aliases: [ds18b20, 1-wire temperature sensor]
  category: SENSOR
  object_type: PHYSICAL
  description: 1-Wire digital temperature sensor
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.5
    - pin_id: DQ
      name: DATA
      direction: BIDIRECTIONAL
      electrical_type: DIGITAL
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties:
    operating_voltage: 3.0V-5.5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [SENSOR]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 20. sensor:mpu6050
```yaml
sensor:mpu6050:
  name: MPU6050 IMU
  aliases: [mpu6050, imu, accelerometer, gyroscope]
  category: SENSOR
  object_type: PHYSICAL
  description: 3-axis accelerometer and gyroscope (I2C)
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: SCL
      name: SCL
      direction: INPUT
      electrical_type: I2C
    - pin_id: SDA
      name: SDA
      direction: BIDIRECTIONAL
      electrical_type: I2C
    - pin_id: XDA
      name: XDA
      direction: BIDIRECTIONAL
      electrical_type: I2C
    - pin_id: XCL
      name: XCL
      direction: OUTPUT
      electrical_type: I2C
    - pin_id: ADD
      name: ADD
      direction: INPUT
      electrical_type: I2C
    - pin_id: INT
      name: INT
      direction: OUTPUT
      electrical_type: I2C
  electrical_properties:
    operating_voltage: 3.3V-5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [I2C]
  roles: [SENSOR]
  requires_driver: false
  recommended_control_interface: I2C
```

### 21. sensor:mq2
```yaml
sensor:mq2:
  name: MQ-2 Gas Sensor
  aliases: [mq-2, mq2, gas sensor, smoke sensor]
  category: SENSOR
  object_type: PHYSICAL
  description: Gas and smoke sensor module
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: A0
      name: ANALOG OUT
      direction: OUTPUT
      electrical_type: ANALOG
    - pin_id: D0
      name: DIGITAL OUT
      direction: OUTPUT
      electrical_type: DIGITAL
  electrical_properties:
    operating_voltage: 5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [ANALOG, DIGITAL]
  roles: [SENSOR]
  requires_driver: false
```

### 22. sensor:rotary-encoder
```yaml
sensor:rotary-encoder:
  name: Rotary Encoder
  aliases: [rotary encoder, encoder]
  category: SENSOR
  object_type: PHYSICAL
  description: Mechanical rotary encoder with push button
  pins:
    - pin_id: CLK
      name: CLK
      direction: OUTPUT
      electrical_type: DIGITAL
    - pin_id: DT
      name: DT
      direction: OUTPUT
      electrical_type: DIGITAL
    - pin_id: SW
      name: SW
      direction: OUTPUT
      electrical_type: DIGITAL
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
  electrical_properties:
    operating_voltage: 3.3V-5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [INPUT, SENSOR]
  requires_driver: false
```

### 23. actuator:led-rgb
```yaml
actuator:led-rgb:
  name: RGB LED
  aliases: [rgb led, rgb light, color led]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Common cathode RGB LED
  pins:
    - pin_id: R
      name: RED
      direction: PASSIVE
    - pin_id: G
      name: GREEN
      direction: PASSIVE
    - pin_id: B
      name: BLUE
      direction: PASSIVE
    - pin_id: COM
      name: COMMON
      direction: PASSIVE
  electrical_properties:
    max_forward_current: 20mA
    recommended_current: 10mA
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [PWM, DIGITAL]
  roles: [ACTUATOR, DISPLAY]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 24. actuator:dc-motor
```yaml
actuator:dc-motor:
  name: DC Motor
  aliases: [dc motor, motor]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Generic DC motor
  pins:
    - pin_id: PIN1
      name: PIN1
      direction: PASSIVE
    - pin_id: PIN2
      name: PIN2
      direction: PASSIVE
  electrical_properties:
    operating_voltage: 3V-6V
    max_current: 500mA
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: BEGINNER
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [ANALOG, PWM]
  roles: [ACTUATOR]
  requires_driver: true
```

### 25. actuator:relay-module
```yaml
actuator:relay-module:
  name: Relay Module
  aliases: [relay, relay module]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: 1-channel relay module
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: IN
      name: IN
      direction: INPUT
      electrical_type: DIGITAL
    - pin_id: NO
      name: NORMALLY OPEN
      direction: PASSIVE
    - pin_id: NC
      name: NORMALLY CLOSED
      direction: PASSIVE
    - pin_id: COM
      name: COMMON
      direction: PASSIVE
  electrical_properties:
    operating_voltage: 5V
    max_current: 10A
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [ACTUATOR, LOGIC]
  requires_driver: false
  recommended_control_interface: DIGITAL
```

### 26. actuator:oled-i2c
```yaml
actuator:oled-i2c:
  name: OLED Display I2C
  aliases: [oled, display, small oled i2c display, i2c oled]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Small OLED display using I2C
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: SCL
      name: SCL
      direction: INPUT
      electrical_type: I2C
    - pin_id: SDA
      name: SDA
      direction: BIDIRECTIONAL
      electrical_type: I2C
  electrical_properties:
    operating_voltage: 3.3V-5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [I2C]
  roles: [DISPLAY, ACTUATOR]
  requires_driver: false
  recommended_control_interface: I2C
```

### 27. actuator:7-segment
```yaml
actuator:7-segment:
  name: 7-Segment Display
  aliases: [7-segment display, 7-segment, display]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: Single digit 7-segment display
  pins:
    - pin_id: A
      name: A
      direction: PASSIVE
    - pin_id: B
      name: B
      direction: PASSIVE
    - pin_id: C
      name: C
      direction: PASSIVE
    - pin_id: D
      name: D
      direction: PASSIVE
    - pin_id: E
      name: E
      direction: PASSIVE
    - pin_id: F
      name: F
      direction: PASSIVE
    - pin_id: G
      name: G
      direction: PASSIVE
    - pin_id: DP
      name: DP
      direction: PASSIVE
    - pin_id: COM1
      name: COM1
      direction: PASSIVE
    - pin_id: COM2
      name: COM2
      direction: PASSIVE
  electrical_properties:
    max_forward_current: 20mA
    recommended_current: 10mA
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL]
  roles: [DISPLAY, ACTUATOR]
  requires_driver: false
```

### 28. logic:74hc595
```yaml
logic:74hc595:
  name: 74HC595 Shift Register
  aliases: [74hc595, shift register]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: 8-bit serial-in, serial or parallel-out shift register
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 6.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: SER
      name: DATA
      direction: INPUT
      electrical_type: DIGITAL
    - pin_id: OE
      name: OUTPUT ENABLE
      direction: INPUT
      electrical_type: DIGITAL
    - pin_id: RCLK
      name: LATCH
      direction: INPUT
      electrical_type: DIGITAL
    - pin_id: SRCLK
      name: CLOCK
      direction: INPUT
      electrical_type: DIGITAL
    - pin_id: SRCLR
      name: CLEAR
      direction: INPUT
      electrical_type: DIGITAL
    - [8 output pins: QA-QH, QH_PRIME]
      (all: direction: OUTPUT, electrical_type: DIGITAL)
  electrical_properties:
    operating_voltage: 2.0V-6.0V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: ADVANCED
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [DIGITAL, SPI]
  roles: [LOGIC]
  requires_driver: false
```

### 29. actuator:lcd-i2c
```yaml
actuator:lcd-i2c:
  name: I2C LCD Module
  aliases: [lcd, i2c lcd, display, lcd1602]
  category: ACTIVE_COMPONENT
  object_type: PHYSICAL
  description: 16x2 or 20x4 LCD with I2C backpack
  pins:
    - pin_id: VCC
      name: VCC
      direction: POWER
      max_voltage: 5.0
    - pin_id: GND
      name: GND
      direction: GROUND
      max_voltage: 0.0
    - pin_id: SDA
      name: SDA
      direction: BIDIRECTIONAL
      electrical_type: I2C
    - pin_id: SCL
      name: SCL
      direction: INPUT
      electrical_type: I2C
  electrical_properties:
    operating_voltage: 5V
  configurable_parameters: {}
  curriculum_mapping: []
  competency_level: INTERMEDIATE
  provenance: community
  license: unknown
  validation_status: proposed
  interfaces: [I2C]
  roles: [DISPLAY, ACTUATOR]
  requires_driver: false
  recommended_control_interface: I2C
```

## Search and Index Behavior

Based on the `search()` method in `src/components/registry.py`:

### Search Algorithm (Case-Insensitive Substring Match)
1. **Primary Match**: Check if query appears in `component_type_id` or `name`
2. **Alias Match**: Check if query appears in any alias
3. **Role Match**: Check if query appears in any role
4. **Interface Match**: Check if query appears in any interface
5. **Description Match**: Check if query appears in description

### Search Examples from Code
- `illustration-engine component search led` would match:
  - `passive:led-5mm` (name contains "led")
  - `actuator:led-rgb` (name contains "led")
  - Any component with "led" in aliases, roles, interfaces, or description

### Component Count
From examining the YAML file:
- **Total Components**: 29 components

## Electrical Metadata Completeness Analysis

### Voltage Specifications
- **Complete**: Most components have `max_voltage` specified on pins
- **Partial**: Some have `min_voltage` (mainly for sensors with specific output levels)
- **Inferred**: Operating voltages often in `electrical_properties` as strings like "3.3V-5V"

### Current Specifications
- **Output Current**: Specified for some components (LEDs: `max_forward_current`, motors: `max_current`)
- **Input Current**: Less commonly specified
- **GPIO Limits**: Microcontroller has `gpio_max_current`: 40mA

### Power Specifications
- **Power Rating**: Resistors have `power_rating`: 0.25W
- **Missing**: Most active components lack power dissipation specs

### Missing Electrical Information
1. **Impedance/Frequency Response**: Not specified for any component
2. **Timing Characteristics**: Rise/fall times, propagation delays not specified
3. **Thermal Characteristics**: Operating temperature ranges, thermal resistance not specified
4. **Noise Characteristics**: Voltage/current noise specs not present
5. **Details on Electrical Properties**: Many `electrical_properties` are empty or minimal

### Search Effectiveness
The search functionality is robust, covering:
- Direct ID/name matching
- Aliases (alternative names)
- Functional roles (SENSOR, ACTUATOR, etc.)
- Supported interfaces (I2C, SPI, PWM, etc.)
- Conceptual matching through descriptions

This enables natural language queries like "find a distance sensor" or "show me I2C displays" to work effectively.

## Registry Implementation Quality

### Strengths
1. **Clean Separation**: Loading logic separate from access logic
2. **Error Handling**: Graceful handling of malformed YAML, duplicates, validation errors
3. **Performance**: Lookup O(1), search O(n) with early termination optimization
4. **Extensibility**: Easy to add new components via YAML
5. **Validation**: Uses Pydantic models for automatic validation
6. **Path Resolution**: Correctly resolves paths relative to project root

### Limitations
1. **No Hot Reloading**: Registry loaded once at startup
2. **Limited Search Features**: No fuzzy search, regex, or weighted ranking
3. **No Relationship Tracking**: Doesn't track component compatibility or typical pairings
4. **Static Definition**: Components can't be modified at runtime
5. **Validation Timing**: Validation happens only at load time, not per-access

## Conclusion

The component registry provides a solid foundation for the Illustration Engine's component-based design approach. With 29 well-defined components covering microcontrollers, sensors, actuators, and passives, it offers sufficient variety for beginner to intermediate projects. The search functionality is particularly strong, enabling intuitive discovery through multiple matching strategies.

The YAML-driven approach makes it easy to expand the registry, and the Pydantic validation ensures data integrity. For future enhancements, adding more detailed electrical specifications (impedance, timing, thermal) would support more advanced validation rules, but the current structure provides an excellent extensible foundation.