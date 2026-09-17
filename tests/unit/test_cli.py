"""Tests for CLI commands using Typer's test runner."""
import pytest
from typer.testing import CliRunner
from cli.main import app

runner = CliRunner()


class TestComponentCLI:
    def test_component_list(self):
        result = runner.invoke(app, ["component", "list"])
        assert result.exit_code == 0
        assert "board:esp32-devkit-v1" in result.output
        assert "Total: 8" in result.output

    def test_component_search_found(self):
        result = runner.invoke(app, ["component", "search", "led"])
        assert result.exit_code == 0
        assert "led" in result.output.lower()

    def test_component_search_not_found(self):
        result = runner.invoke(app, ["component", "search", "quantum"])
        assert result.exit_code == 1

    def test_component_show(self):
        result = runner.invoke(app, ["component", "show", "board:esp32-devkit-v1"])
        assert result.exit_code == 0
        assert "ESP32" in result.output
        assert "GPIO5" in result.output

    def test_component_show_not_found(self):
        result = runner.invoke(app, ["component", "show", "nonexistent:thing"])
        assert result.exit_code == 1


class TestDesignCLI:
    def test_validate_valid_design(self):
        result = runner.invoke(app, [
            "design", "validate",
            "tests/fixtures/golden/smart_parking_valid.json",
        ])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_validate_invalid_led(self):
        result = runner.invoke(app, [
            "design", "validate",
            "tests/fixtures/golden/smart_parking_invalid_led.json",
        ])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "E007" in result.output

    def test_validate_missing_file(self):
        result = runner.invoke(app, ["design", "validate", "nonexistent.json"])
        assert result.exit_code == 1

    def test_validate_unknown_component(self):
        result = runner.invoke(app, [
            "design", "validate",
            "tests/fixtures/golden/smart_parking_unknown_component.json",
        ])
        assert result.exit_code == 1
        assert "E001" in result.output


class TestCalcCLI:
    def test_led_resistor(self):
        result = runner.invoke(app, [
            "calc", "led-resistor",
            "--supply", "3.3",
            "--vf", "2.0",
            "--current", "10",
        ])
        assert result.exit_code == 0
        assert "130" in result.output

    def test_led_resistor_invalid(self):
        result = runner.invoke(app, [
            "calc", "led-resistor",
            "--supply", "2.0",
            "--vf", "3.0",
            "--current", "10",
        ])
        assert result.exit_code == 1


class TestCurriculumCLI:
    def test_search_found(self):
        result = runner.invoke(app, ["curriculum", "search", "CMOS"])
        assert result.exit_code == 0
        assert "cmos_inverter" in result.output

    def test_search_not_found(self):
        result = runner.invoke(app, ["curriculum", "search", "quantum_computing"])
        assert result.exit_code == 1

    def test_show_concept(self):
        result = runner.invoke(app, ["curriculum", "show", "cmos_inverter"])
        assert result.exit_code == 0
        assert "CMOS Inverter" in result.output
        assert "VLSI Basics" in result.output

    def test_show_not_found(self):
        result = runner.invoke(app, ["curriculum", "show", "nonexistent"])
        assert result.exit_code == 1
