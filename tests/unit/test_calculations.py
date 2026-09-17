"""Tests for the deterministic LED resistor calculation service."""
import pytest

from validation.calculations import calculate_led_resistor, _find_nearest_e24


class TestLedResistorCalculation:
    def test_basic_3v3_red_led(self):
        """Standard 3.3V supply with red LED (Vf=2.0V, 10mA)."""
        result = calculate_led_resistor(3.3, 2.0, 10.0)
        assert result.calculated_resistance == 130.0
        assert result.nearest_standard_value is not None
        assert result.actual_current_ma is not None
        assert result.power_dissipation_mw > 0
        assert len(result.assumptions) > 0

    def test_5v_supply_red_led(self):
        """Standard 5V supply with red LED."""
        result = calculate_led_resistor(5.0, 2.0, 10.0)
        assert result.calculated_resistance == 300.0
        assert result.nearest_standard_value == 300.0  # 300 is in E24

    def test_nearest_standard_value(self):
        """130 ohm should map to nearest E24 value."""
        result = calculate_led_resistor(3.3, 2.0, 10.0)
        assert result.nearest_standard_value == 130.0

    def test_power_dissipation(self):
        """P = I^2 * R = (0.01)^2 * 130 = 0.013W = 13mW."""
        result = calculate_led_resistor(3.3, 2.0, 10.0)
        assert result.power_dissipation_mw == 13.0

    def test_invalid_zero_supply(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_led_resistor(0, 2.0, 10.0)

    def test_invalid_negative_supply(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_led_resistor(-5.0, 2.0, 10.0)

    def test_invalid_vf_exceeds_supply(self):
        with pytest.raises(ValueError, match="less than"):
            calculate_led_resistor(2.0, 3.0, 10.0)

    def test_invalid_zero_current(self):
        with pytest.raises(ValueError, match="positive"):
            calculate_led_resistor(5.0, 2.0, 0.0)

    def test_deterministic(self):
        """Same inputs must always produce same outputs."""
        r1 = calculate_led_resistor(3.3, 2.0, 10.0)
        r2 = calculate_led_resistor(3.3, 2.0, 10.0)
        assert r1.calculated_resistance == r2.calculated_resistance
        assert r1.nearest_standard_value == r2.nearest_standard_value
        assert r1.actual_current_ma == r2.actual_current_ma


class TestFindNearestE24:
    def test_exact_match(self):
        assert _find_nearest_e24(100.0) == 100.0
        assert _find_nearest_e24(330.0) == 330.0

    def test_nearest_above(self):
        # 131 should be near 130
        result = _find_nearest_e24(131.0)
        assert result == 130.0

    def test_standard_led_resistors(self):
        # Common resistor values should be found exactly
        assert _find_nearest_e24(220.0) == 220.0
        assert _find_nearest_e24(470.0) == 470.0
        assert _find_nearest_e24(1000.0) == 1000.0

    def test_zero_returns_none(self):
        assert _find_nearest_e24(0) is None

    def test_negative_returns_none(self):
        assert _find_nearest_e24(-100) is None
