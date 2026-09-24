from enum import Enum

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
    # Added in the 2D Schematic Studio stage. None of these are special-cased by
    # legacy validator rules; behaviour comes from pin metadata instead.
    SEMICONDUCTOR = "SEMICONDUCTOR"            # discrete diodes, BJTs, MOSFETs
    INTEGRATED_CIRCUIT = "INTEGRATED_CIRCUIT"  # op-amps, timers, logic ICs, ADC/DAC
    POWER_MANAGEMENT = "POWER_MANAGEMENT"      # regulators, converters
    SWITCH = "SWITCH"
    DISPLAY = "DISPLAY"
    ACTUATOR = "ACTUATOR"
    MEMORY = "MEMORY"
    INTERFACE = "INTERFACE"                    # transceivers, level shifters
    LOGIC = "LOGIC"                            # idealised logic primitives

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
