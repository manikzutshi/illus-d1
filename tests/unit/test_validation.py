"""Tests for the deterministic validation engine using golden fixtures.

Phase 2.5: Includes voltage compatibility, short circuit, and level-shifting tests.
"""
import json
import pytest
from pathlib import Path

from components.registry import get_default_registry, ComponentRegistry
from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
from core.enums import ValidationStatus
from validation.engine import DesignValidator

FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden"


@pytest.fixture
def registry() -> ComponentRegistry:
    return get_default_registry()


@pytest.fixture
def validator(registry) -> DesignValidator:
    return DesignValidator(registry)


def _load_fixture(name: str) -> EngineeringDesignProject:
    path = FIXTURES / name
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return EngineeringDesignProject.model_validate(data)


# ═══════════════════════════════════════════════════════════════════════
# Golden valid design (with level-shifted ECHO)
# ═══════════════════════════════════════════════════════════════════════

class TestGoldenValid:
    def test_smart_parking_valid_passes(self, validator):
        design = _load_fixture("smart_parking_valid.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.PASS, (
            f"Expected PASS but got {result.status}. Errors: {[e.code + ': ' + e.message for e in result.errors]}"
        )
        assert len(result.errors) == 0
        assert result.component_count == 8  # u1, s1, d1, r1, r_div_top, r_div_bot, pwr1, gnd1
        assert result.net_count == 7       # power, ground, trigger, echo_raw, echo_divided, led_drive, led_anode

    def test_determinism(self, validator):
        """Running validation twice must produce identical results."""
        design = _load_fixture("smart_parking_valid.json")
        r1 = validator.validate(design)
        r2 = validator.validate(design)
        assert r1.status == r2.status
        assert len(r1.errors) == len(r2.errors)
        assert len(r1.warnings) == len(r2.warnings)

    def test_valid_design_has_level_shifting(self, validator):
        """The golden valid design must include a voltage divider for ECHO."""
        design = _load_fixture("smart_parking_valid.json")
        instance_ids = {c.instance_id for c in design.components}
        assert "r_div_top" in instance_ids, "Golden design must include voltage divider"
        assert "r_div_bot" in instance_ids, "Golden design must include voltage divider"


# ═══════════════════════════════════════════════════════════════════════
# E010: Voltage incompatibility (5V ECHO → 3.3V GPIO)
# ═══════════════════════════════════════════════════════════════════════

class TestGoldenVoltageMismatch:
    def test_direct_echo_to_gpio_rejected(self, validator):
        """HC-SR04 ECHO (5V) directly to ESP32 GPIO (3.6V max) must be E010."""
        design = _load_fixture("smart_parking_no_level_shift.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E010" in error_codes
        # Verify the error mentions the specific net
        e010_errors = [e for e in result.errors if e.code == "E010"]
        assert any("n_echo_direct" in e.affected_nets for e in e010_errors)


# ═══════════════════════════════════════════════════════════════════════
# E011: Short circuit (VCC → GND)
# ═══════════════════════════════════════════════════════════════════════

class TestGoldenShortCircuit:
    def test_vcc_to_gnd_short_detected(self, validator):
        design = _load_fixture("smart_parking_short_circuit.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E011" in error_codes
        e011_errors = [e for e in result.errors if e.code == "E011"]
        assert any("n_short" in e.affected_nets for e in e011_errors)


# ═══════════════════════════════════════════════════════════════════════
# Existing golden fixture tests (Phase 2 — preserved)
# ═══════════════════════════════════════════════════════════════════════

class TestGoldenMissingGround:
    def test_missing_ground_detected(self, validator):
        design = _load_fixture("smart_parking_missing_ground.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E005" in error_codes


class TestGoldenInvalidLed:
    def test_led_without_resistor_detected(self, validator):
        design = _load_fixture("smart_parking_invalid_led.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E007" in error_codes
        e007_errors = [e for e in result.errors if e.code == "E007"]
        assert any("d1" in e.affected_instances for e in e007_errors)


class TestGoldenUnknownComponent:
    def test_unknown_component_detected(self, validator):
        design = _load_fixture("smart_parking_unknown_component.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E001" in error_codes
        e001_errors = [e for e in result.errors if e.code == "E001"]
        assert any("s1" in e.affected_instances for e in e001_errors)


class TestGoldenUnknownPin:
    def test_unknown_pin_detected(self, validator):
        design = _load_fixture("smart_parking_unknown_pin.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E002" in error_codes


class TestGoldenBadConnection:
    def test_bad_connection_detected(self, validator):
        design = _load_fixture("smart_parking_bad_connection.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E006" in error_codes


# ═══════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorEdgeCases:
    def test_empty_design(self, validator):
        design = EngineeringDesignProject(project_id="empty", name="Empty", components=[], nets=[])
        result = validator.validate(design)
        assert result.status == ValidationStatus.PASS
        assert result.component_count == 0

    def test_duplicate_instance_id(self, validator):
        design = EngineeringDesignProject(
            project_id="dup",
            name="Duplicate IDs",
            components=[
                EngineeringComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                EngineeringComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
            ],
            nets=[
                Net(
                    net_id="n1",
                    connections=[
                        PinRef(instance_id="u1", pin_id="GND1"),
                        PinRef(instance_id="u1", pin_id="GND2"),
                    ]
                )
            ],
        )
        result = validator.validate(design)
        assert result.status == ValidationStatus.FAIL
        error_codes = {e.code for e in result.errors}
        assert "E003" in error_codes

    def test_duplicate_net_id(self, validator):
        design = EngineeringDesignProject(
            project_id="dupnet",
            name="Duplicate Net IDs",
            components=[
                EngineeringComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                EngineeringComponentInstance(instance_id="gnd1", component_type="primitive:ground-rail"),
                EngineeringComponentInstance(instance_id="pwr1", component_type="primitive:power-rail"),
            ],
            nets=[
                Net(
                    net_id="n1",
                    connections=[
                        PinRef(instance_id="u1", pin_id="GND1"),
                        PinRef(instance_id="gnd1", pin_id="GND"),
                    ]
                ),
                Net(
                    net_id="n1",
                    connections=[
                        PinRef(instance_id="u1", pin_id="VIN"),
                        PinRef(instance_id="pwr1", pin_id="VCC"),
                    ]
                ),
            ],
        )
        result = validator.validate(design)
        error_codes = {e.code for e in result.errors}
        assert "E008" in error_codes

    def test_disconnected_component(self, validator):
        design = EngineeringDesignProject(
            project_id="disc",
            name="Disconnected",
            components=[
                EngineeringComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                EngineeringComponentInstance(instance_id="d1", component_type="passive:led-5mm"),
                EngineeringComponentInstance(instance_id="gnd1", component_type="primitive:ground-rail"),
                EngineeringComponentInstance(instance_id="pwr1", component_type="primitive:power-rail"),
            ],
            nets=[
                Net(
                    net_id="n_power",
                    connections=[
                        PinRef(instance_id="u1", pin_id="VIN"),
                        PinRef(instance_id="pwr1", pin_id="VCC"),
                    ]
                ),
                Net(
                    net_id="n_gnd",
                    connections=[
                        PinRef(instance_id="u1", pin_id="GND1"),
                        PinRef(instance_id="gnd1", pin_id="GND"),
                    ]
                ),
            ],
        )
        result = validator.validate(design)
        error_codes = {e.code for e in result.errors}
        assert "E009" in error_codes
        e009 = [e for e in result.errors if e.code == "E009"]
        assert any("d1" in e.affected_instances for e in e009)

    def test_resistor_missing_value_warning(self, validator):
        design = EngineeringDesignProject(
            project_id="nowarn",
            name="Resistor No Value",
            components=[
                EngineeringComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                EngineeringComponentInstance(instance_id="r1", component_type="passive:resistor-tht", parameters={}),
                EngineeringComponentInstance(instance_id="d1", component_type="passive:led-5mm"),
                EngineeringComponentInstance(instance_id="gnd1", component_type="primitive:ground-rail"),
                EngineeringComponentInstance(instance_id="pwr1", component_type="primitive:power-rail"),
            ],
            nets=[
                Net(
                    net_id="n_pwr",
                    connections=[
                        PinRef(instance_id="u1", pin_id="VIN"),
                        PinRef(instance_id="pwr1", pin_id="VCC"),
                    ]
                ),
                Net(
                    net_id="n_gnd",
                    connections=[
                        PinRef(instance_id="u1", pin_id="GND1"),
                        PinRef(instance_id="gnd1", pin_id="GND"),
                        PinRef(instance_id="d1", pin_id="CATHODE"),
                    ]
                ),
                Net(
                    net_id="n_led",
                    connections=[
                        PinRef(instance_id="u1", pin_id="GPIO19"),
                        PinRef(instance_id="r1", pin_id="PIN1"),
                    ]
                ),
                Net(
                    net_id="n_led_a",
                    connections=[
                        PinRef(instance_id="r1", pin_id="PIN2"),
                        PinRef(instance_id="d1", pin_id="ANODE"),
                    ]
                ),
            ],
        )
        result = validator.validate(design)
        warning_codes = {w.code for w in result.warnings}
        assert "W001" in warning_codes


# ═══════════════════════════════════════════════════════════════════════
# End-to-end deterministic pipeline test
# ═══════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full pipeline: JSON file → load registry → parse EngineeringDesignProject →
    validate → assert structured ValidationResult. No LLM."""

    def test_e2e_valid_design(self):
        """Golden valid fixture → full pipeline → PASS with zero errors."""
        # Step 1: Load registry from YAML
        registry = get_default_registry()
        assert registry.count >= 8

        # Step 2: Parse golden JSON into EngineeringDesignProject
        with open(FIXTURES / "smart_parking_valid.json", "r") as f:
            raw = json.load(f)
        design = EngineeringDesignProject.model_validate(raw)
        assert design.project_id == "smart-parking-mvp"
        assert len(design.components) == 8
        assert len(design.nets) == 7

        # Step 3: Validate deterministically
        validator = DesignValidator(registry)
        result = validator.validate(design)

        # Step 4: Assert structured result
        assert result.status == ValidationStatus.PASS
        assert result.errors == []
        assert result.component_count == 8
        assert result.net_count == 7

    def test_auto_light_valid(self):
        """Auto light valid fixture → full pipeline → PASS."""
        registry = get_default_registry()
        with open(FIXTURES / "auto_light_valid.json", "r") as f:
            raw = json.load(f)
        design = EngineeringDesignProject.model_validate(raw)
        validator = DesignValidator(registry)
        result = validator.validate(design)
        assert result.status == ValidationStatus.PASS
        assert result.errors == []

    def test_e2e_invalid_design_voltage(self):
        """No-level-shift fixture → full pipeline → FAIL with E010."""
        registry = get_default_registry()

        with open(FIXTURES / "smart_parking_no_level_shift.json", "r") as f:
            raw = json.load(f)
        design = EngineeringDesignProject.model_validate(raw)

        validator = DesignValidator(registry)
        result = validator.validate(design)

        assert result.status == ValidationStatus.FAIL
        assert any(e.code == "E010" for e in result.errors)
        # The result is a proper structured object, not a string
        assert isinstance(result.errors[0].code, str)
        assert isinstance(result.errors[0].affected_nets, list)

    def test_e2e_invalid_design_short(self):
        """Short-circuit fixture → full pipeline → FAIL with E011."""
        registry = get_default_registry()

        with open(FIXTURES / "smart_parking_short_circuit.json", "r") as f:
            raw = json.load(f)
        design = EngineeringDesignProject.model_validate(raw)

        validator = DesignValidator(registry)
        result = validator.validate(design)

        assert result.status == ValidationStatus.FAIL
        assert any(e.code == "E011" for e in result.errors)


def test_w001_generic_resistor(validator):
    design = EngineeringDesignProject(
        project_id="test_w001",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="r1", component_type="passive:resistor-tht")
        ],
        nets=[]
    )
    res = validator.validate(design)
    assert any(w.code == "W001" for w in res.warnings)

def test_w001_generic_resistor_with_resistance(validator):
    design = EngineeringDesignProject(
        project_id="test_w001",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="r1", component_type="passive:resistor-tht", parameters={"resistance": "10k"})
        ],
        nets=[]
    )
    res = validator.validate(design)
    assert not any(w.code == "W001" for w in res.warnings)

def test_w001_photoresistor(validator):
    design = EngineeringDesignProject(
        project_id="test_w001",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="ldr1", component_type="sensor:photoresistor")
        ],
        nets=[]
    )
    res = validator.validate(design)
    assert not any(w.code == "W001" for w in res.warnings)


def test_duplicate_pin_across_nets(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
    from core.enums import ValidationStatus
    design = EngineeringDesignProject(
        project_id="dup_pin",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="bz1", component_type="sensor:hc-sr501"),
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1")
        ],
        nets=[
            Net(net_id="n1", connections=[PinRef(instance_id="esp", pin_id="3V3"), PinRef(instance_id="bz1", pin_id="VCC")]),
            Net(net_id="n2", connections=[PinRef(instance_id="esp", pin_id="GPIO4"), PinRef(instance_id="bz1", pin_id="VCC")])
        ]
    )
    res = validator.validate(design)
    assert any(e.code == "E013" for e in res.errors)

def test_hcsr501_powered_from_3v3_error(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
    design = EngineeringDesignProject(
        project_id="bad_volt",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="pir", component_type="sensor:hc-sr501"),
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1")
        ],
        nets=[
            Net(net_id="pwr", connections=[PinRef(instance_id="esp", pin_id="3V3"), PinRef(instance_id="pir", pin_id="VCC")]),
            Net(net_id="gnd", connections=[PinRef(instance_id="esp", pin_id="GND1"), PinRef(instance_id="pir", pin_id="GND")])
        ]
    )
    res = validator.validate(design)
    assert any(e.code == "E014" for e in res.errors)

def test_hcsr501_powered_from_compatible_voltage(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
    design = EngineeringDesignProject(
        project_id="good_volt",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="pir", component_type="sensor:hc-sr501"),
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1")
        ],
        nets=[
            Net(net_id="pwr", connections=[PinRef(instance_id="esp", pin_id="VIN"), PinRef(instance_id="pir", pin_id="VCC")]),
            Net(net_id="gnd", connections=[PinRef(instance_id="esp", pin_id="GND1"), PinRef(instance_id="pir", pin_id="GND")])
        ]
    )
    res = validator.validate(design)
    assert not any(e.code == "E014" for e in res.errors)

def test_motion_alert_corrected_topology(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
    # Buzzer doesn't exist in registry? The prompt says "bz1" is a buzzer, let's just use generic output or passive for testing
    # Or let's see if there is an output:buzzer-active in registry.

    design = EngineeringDesignProject(
        project_id="motion_alert_correct",
        name="Motion Alert",
        components=[
            EngineeringComponentInstance(instance_id="pir", component_type="sensor:hc-sr501"),
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="bz1", component_type="actuator:buzzer-piezo")
        ],
        nets=[
            Net(net_id="pir_pwr", connections=[PinRef(instance_id="esp", pin_id="VIN"), PinRef(instance_id="pir", pin_id="VCC")]),
            Net(net_id="pir_gnd", connections=[PinRef(instance_id="esp", pin_id="GND1"), PinRef(instance_id="pir", pin_id="GND")]),
            Net(net_id="pir_sig", connections=[PinRef(instance_id="esp", pin_id="GPIO4"), PinRef(instance_id="pir", pin_id="OUT")]),
            Net(net_id="bz_pwr", connections=[PinRef(instance_id="esp", pin_id="GPIO5"), PinRef(instance_id="bz1", pin_id="VCC")]),
            Net(net_id="bz_gnd", connections=[PinRef(instance_id="esp", pin_id="GND2"), PinRef(instance_id="bz1", pin_id="GND")])
        ]
    )
    res = validator.validate(design)
    assert not any(e.code in ("E013", "E014") for e in res.errors)


def test_gpio_overcurrent(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef, ComponentType, PinDefinition
    from core.enums import ComponentCategory, PinDirection, ObjectType

    # Mock a heavy load actuator
    heavy_motor = ComponentType(
        component_type_id="actuator:heavy-motor",
        name="Heavy Motor",
        category=ComponentCategory.ACTIVE_COMPONENT,
        object_type=ObjectType.PHYSICAL,
        pins=[
            PinDefinition(pin_id="IN", name="IN", direction=PinDirection.INPUT, max_voltage=5.0),
            PinDefinition(pin_id="GND", name="GND", direction=PinDirection.GROUND, max_voltage=0.0)
        ],
        electrical_properties={"operating_current": "100mA"}
    )
    validator._registry._types["actuator:heavy-motor"] = heavy_motor

    design = EngineeringDesignProject(
        project_id="overcurrent",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="m1", component_type="actuator:heavy-motor")
        ],
        nets=[
            Net(net_id="n1", connections=[PinRef(instance_id="esp", pin_id="GPIO4"), PinRef(instance_id="m1", pin_id="IN")])
        ]
    )
    res = validator.validate(design)
    assert any(e.code == "E015" for e in res.errors), "Should detect GPIO overcurrent"

def test_gpio_unspecified_load(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef, ComponentType, PinDefinition
    from core.enums import ComponentCategory, PinDirection, ObjectType

    # Mock an unspecified load actuator
    mystery_load = ComponentType(
        component_type_id="actuator:mystery-load",
        name="Mystery Load",
        category=ComponentCategory.ACTIVE_COMPONENT,
        object_type=ObjectType.PHYSICAL,
        pins=[
            PinDefinition(pin_id="IN", name="IN", direction=PinDirection.INPUT, max_voltage=5.0),
        ]
    )
    validator._registry._types["actuator:mystery-load"] = mystery_load

    design = EngineeringDesignProject(
        project_id="mystery",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="m1", component_type="actuator:mystery-load")
        ],
        nets=[
            Net(net_id="n1", connections=[PinRef(instance_id="esp", pin_id="GPIO4"), PinRef(instance_id="m1", pin_id="IN")])
        ]
    )
    res = validator.validate(design)
    assert not any(e.code == "E015" for e in res.errors), "Should NOT invent current failure for unspecified load"

def test_gpio_valid_low_current_load(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef, ComponentType, PinDefinition
    from core.enums import ComponentCategory, PinDirection, ObjectType

    low_load = ComponentType(
        component_type_id="actuator:low-load",
        name="Low Load",
        category=ComponentCategory.ACTIVE_COMPONENT,
        object_type=ObjectType.PHYSICAL,
        pins=[
            PinDefinition(pin_id="IN", name="IN", direction=PinDirection.INPUT, max_voltage=5.0),
        ],
        electrical_properties={"operating_current": "10mA"}
    )
    validator._registry._types["actuator:low-load"] = low_load

    design = EngineeringDesignProject(
        project_id="low_load",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="m1", component_type="actuator:low-load")
        ],
        nets=[
            Net(net_id="n1", connections=[PinRef(instance_id="esp", pin_id="GPIO4"), PinRef(instance_id="m1", pin_id="IN")])
        ]
    )
    res = validator.validate(design)
    assert not any(e.code == "E015" for e in res.errors), "Should pass valid low current load"

def test_missing_power_source_vin_only(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
    design = EngineeringDesignProject(
        project_id="missing_pwr",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="pir", component_type="sensor:hc-sr501")
        ],
        nets=[
            # VIN is an input, it does not supply power.
            Net(net_id="pwr", connections=[PinRef(instance_id="esp", pin_id="VIN"), PinRef(instance_id="pir", pin_id="VCC")])
        ]
    )
    res = validator.validate(design)
    assert any(e.code == "E016" for e in res.errors), "Should detect when only VIN is connected"

def test_valid_externally_powered_vin(validator):
    from core.models import EngineeringDesignProject, EngineeringComponentInstance, Net, PinRef
    design = EngineeringDesignProject(
        project_id="good_pwr",
        name="Test",
        components=[
            EngineeringComponentInstance(instance_id="esp", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="pir", component_type="sensor:hc-sr501"),
            EngineeringComponentInstance(instance_id="rail", component_type="primitive:power-rail")
        ],
        nets=[
            # Power rail acts as the source
            Net(net_id="pwr", connections=[
                PinRef(instance_id="rail", pin_id="VCC"),
                PinRef(instance_id="esp", pin_id="VIN"),
                PinRef(instance_id="pir", pin_id="VCC")
            ])
        ]
    )
    res = validator.validate(design)
    assert not any(e.code == "E016" for e in res.errors), "Should pass when valid power rail is present"
