"""Tests for the deterministic validation engine using golden fixtures."""
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


class TestGoldenValid:
    def test_smart_parking_valid_passes(self, validator):
        design = _load_fixture("smart_parking_valid.json")
        result = validator.validate(design)
        assert result.status == ValidationStatus.PASS
        assert len(result.errors) == 0
        assert result.component_count == 6
        assert result.net_count == 6

    def test_determinism(self, validator):
        """Running validation twice must produce identical results."""
        design = _load_fixture("smart_parking_valid.json")
        r1 = validator.validate(design)
        r2 = validator.validate(design)
        assert r1.status == r2.status
        assert len(r1.errors) == len(r2.errors)
        assert len(r1.warnings) == len(r2.warnings)


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
        # Verify the affected instance is the LED
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
