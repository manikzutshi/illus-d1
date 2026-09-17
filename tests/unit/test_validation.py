"""Tests for the deterministic validation engine using golden fixtures.

Phase 2.5: Includes voltage compatibility, short circuit, and level-shifting tests.
"""
import json
import pytest
from pathlib import Path

from components.registry import get_default_registry, ComponentRegistry
from core.models import DesignProject, ComponentInstance, Net, PinRef
from core.enums import ValidationStatus
from validation.engine import DesignValidator

FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden"


@pytest.fixture
def registry() -> ComponentRegistry:
    return get_default_registry()


@pytest.fixture
def validator(registry) -> DesignValidator:
    return DesignValidator(registry)


def _load_fixture(name: str) -> DesignProject:
    path = FIXTURES / name
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return DesignProject.model_validate(data)


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
        design = DesignProject(project_id="empty", name="Empty", components=[], nets=[])
        result = validator.validate(design)
        assert result.status == ValidationStatus.PASS
        assert result.component_count == 0

    def test_duplicate_instance_id(self, validator):
        design = DesignProject(
            project_id="dup",
            name="Duplicate IDs",
            components=[
                ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
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
        design = DesignProject(
            project_id="dupnet",
            name="Duplicate Net IDs",
            components=[
                ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                ComponentInstance(instance_id="gnd1", component_type="primitive:ground-rail"),
                ComponentInstance(instance_id="pwr1", component_type="primitive:power-rail"),
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
        design = DesignProject(
            project_id="disc",
            name="Disconnected",
            components=[
                ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                ComponentInstance(instance_id="d1", component_type="passive:led-5mm"),
                ComponentInstance(instance_id="gnd1", component_type="primitive:ground-rail"),
                ComponentInstance(instance_id="pwr1", component_type="primitive:power-rail"),
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
        design = DesignProject(
            project_id="nowarn",
            name="Resistor No Value",
            components=[
                ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
                ComponentInstance(instance_id="r1", component_type="passive:resistor-tht", parameters={}),
                ComponentInstance(instance_id="d1", component_type="passive:led-5mm"),
                ComponentInstance(instance_id="gnd1", component_type="primitive:ground-rail"),
                ComponentInstance(instance_id="pwr1", component_type="primitive:power-rail"),
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
    """Full pipeline: JSON file → load registry → parse DesignProject →
    validate → assert structured ValidationResult. No LLM."""

    def test_e2e_valid_design(self):
        """Golden valid fixture → full pipeline → PASS with zero errors."""
        # Step 1: Load registry from YAML
        registry = get_default_registry()
        assert registry.count == 8

        # Step 2: Parse golden JSON into DesignProject
        with open(FIXTURES / "smart_parking_valid.json", "r") as f:
            raw = json.load(f)
        design = DesignProject.model_validate(raw)
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

    def test_e2e_invalid_design_voltage(self):
        """No-level-shift fixture → full pipeline → FAIL with E010."""
        registry = get_default_registry()

        with open(FIXTURES / "smart_parking_no_level_shift.json", "r") as f:
            raw = json.load(f)
        design = DesignProject.model_validate(raw)

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
        design = DesignProject.model_validate(raw)

        validator = DesignValidator(registry)
        result = validator.validate(design)

        assert result.status == ValidationStatus.FAIL
        assert any(e.code == "E011" for e in result.errors)
