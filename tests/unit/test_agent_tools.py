"""Tests for the agent tool boundary functions."""
import pytest

from ai.tools import (
    search_components,
    get_component,
    search_curriculum,
    validate_design,
    calculate_circuit,
)
from core.models import DesignProject, ComponentInstance, Net, PinRef
from core.enums import ValidationStatus


class TestSearchComponents:
    def test_search_finds_esp32(self):
        results = search_components("esp32")
        assert len(results) >= 1
        assert any("esp32" in r.component_type_id for r in results)

    def test_search_returns_empty_for_unknown(self):
        results = search_components("quantum_flux")
        assert len(results) == 0


class TestGetComponent:
    def test_get_known(self):
        ct = get_component("board:esp32-devkit-v1")
        assert ct is not None
        assert ct.name == "ESP32-DevKitC V1"

    def test_get_unknown_returns_none(self):
        assert get_component("sensor:imaginary") is None


class TestSearchCurriculum:
    def test_search_finds_cmos(self):
        results = search_curriculum("CMOS")
        assert len(results) >= 1

    def test_search_returns_empty(self):
        results = search_curriculum("quantum_computing")
        assert len(results) == 0


class TestValidateDesign:
    def test_empty_design_passes(self):
        design = DesignProject(project_id="t", name="T", components=[], nets=[])
        result = validate_design(design)
        assert result.status == ValidationStatus.PASS

    def test_unknown_component_fails(self):
        design = DesignProject(
            project_id="t", name="T",
            components=[ComponentInstance(instance_id="x1", component_type="fake:widget")],
            nets=[
                Net(
                    net_id="n1",
                    connections=[
                        PinRef(instance_id="x1", pin_id="PIN1"),
                        PinRef(instance_id="x1", pin_id="PIN2"),
                    ]
                )
            ],
        )
        result = validate_design(design)
        assert result.status == ValidationStatus.FAIL
        assert any(e.code == "E001" for e in result.errors)


class TestCalculateCircuit:
    def test_led_resistor(self):
        result = calculate_circuit(
            "led_resistor",
            supply_voltage=3.3,
            led_forward_voltage=2.0,
            target_current_ma=10.0,
        )
        assert result.calculated_resistance == 130.0

    def test_unknown_calculation_raises(self):
        with pytest.raises(ValueError, match="Unknown calculation type"):
            calculate_circuit("antigravity_drive")
