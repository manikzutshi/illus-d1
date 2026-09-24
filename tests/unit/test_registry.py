"""Tests for the Component Registry loader."""
import pytest
from pathlib import Path

from components.registry import ComponentRegistry, get_default_registry
from core.enums import PinDirection, ComponentCategory


class TestComponentRegistry:
    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        return get_default_registry()

    def test_load_default_registry(self, registry):
        assert registry.count >= 8

    def test_get_known_component(self, registry):
        esp32 = registry.get("board:esp32-devkit-v1")
        assert esp32 is not None
        assert esp32.name == "ESP32-DevKitC V1"
        assert esp32.category == ComponentCategory.MICROCONTROLLER

    def test_get_unknown_component(self, registry):
        assert registry.get("nonexistent:widget") is None

    def test_has(self, registry):
        assert registry.has("board:esp32-devkit-v1")
        assert registry.has("passive:led-5mm")
        assert not registry.has("board:arduino-uno")

    def test_search_by_name(self, registry):
        results = registry.search("ESP32")
        assert len(results) >= 1
        assert any("esp32" in r.component_type_id for r in results)

    def test_search_by_alias(self, registry):
        results = registry.search("ultrasonic")
        assert len(results) >= 1
        assert results[0].component_type_id == "sensor:hc-sr04"

    def test_search_case_insensitive(self, registry):
        results = registry.search("led")
        assert len(results) >= 1

    def test_search_no_results(self, registry):
        results = registry.search("quantum_flux_capacitor")
        assert len(results) == 0

    def test_list_all(self, registry):
        all_comps = registry.list_all()
        assert len(all_comps) >= 8

    def test_esp32_has_gpio_pins(self, registry):
        esp32 = registry.get("board:esp32-devkit-v1")
        pin_ids = {p.pin_id for p in esp32.pins}
        assert "GPIO5" in pin_ids
        assert "GPIO18" in pin_ids
        assert "GPIO19" in pin_ids
        assert "VIN" in pin_ids
        assert "GND1" in pin_ids

    def test_esp32_pin_directions(self, registry):
        esp32 = registry.get("board:esp32-devkit-v1")
        pin_map = {p.pin_id: p for p in esp32.pins}
        assert pin_map["VIN"].direction == PinDirection.POWER
        assert pin_map["GND1"].direction == PinDirection.GROUND
        assert pin_map["GPIO5"].direction == PinDirection.BIDIRECTIONAL

    def test_led_has_anode_cathode(self, registry):
        led = registry.get("passive:led-5mm")
        pin_ids = {p.pin_id for p in led.pins}
        assert "ANODE" in pin_ids
        assert "CATHODE" in pin_ids

    def test_resistor_configurable_params(self, registry):
        resistor = registry.get("passive:resistor-tht")
        assert "resistance" in resistor.configurable_parameters

    def test_hcsr04_pins(self, registry):
        sensor = registry.get("sensor:hc-sr04")
        pin_ids = {p.pin_id for p in sensor.pins}
        assert pin_ids == {"VCC", "TRIG", "ECHO", "GND"}

    def test_load_nonexistent_file(self):
        reg = ComponentRegistry()
        count = reg.load_yaml(Path("/nonexistent/file.yaml"))
        assert count == 0
        assert reg.count == 0

    def test_new_components_resolve_by_id(self, registry):
        new_ids = [
            "passive:potentiometer",
            "sensor:thermistor",
            "sensor:ds18b20",
            "sensor:mpu6050",
            "sensor:mq2",
            "sensor:rotary-encoder",
            "actuator:led-rgb",
            "actuator:dc-motor",
            "actuator:relay-module",
            "actuator:oled-i2c",
            "actuator:7-segment",
            "logic:74hc595",
            "actuator:lcd-i2c"
        ]
        for c_id in new_ids:
            comp = registry.get(c_id)
            assert comp is not None, f"Could not resolve {c_id}"
            # Check required pin metadata
            assert len(comp.pins) > 0, f"Component {c_id} has no pins"

    def test_search_by_semantic_metadata(self, registry):
        # MPU6050 by role/alias/description
        assert any(c.component_type_id == "sensor:mpu6050" for c in registry.search("imu"))
        
        # Displays
        display_results = registry.search("display")
        display_ids = [c.component_type_id for c in display_results]
        assert "actuator:oled-i2c" in display_ids
        assert "actuator:7-segment" in display_ids
        
        # RGB light
        assert any(c.component_type_id == "actuator:led-rgb" for c in registry.search("rgb light"))
        
        # I2C interface search
        i2c_results = registry.search("i2c")
        i2c_ids = [c.component_type_id for c in i2c_results]
        assert "sensor:mpu6050" in i2c_ids
        assert "actuator:oled-i2c" in i2c_ids
        assert "board:esp32-devkit-v1" in i2c_ids

    def test_invalid_duplicate_ids_rejected(self, tmp_path):
        import yaml
        from core.models import ComponentType
        
        # Create a mock YAML with an invalid field (e.g. invalid enum category)
        invalid_yaml = tmp_path / "invalid.yaml"
        invalid_yaml.write_text('''
components:
  "test:duplicate-1":
    name: "Valid Component"
    category: SENSOR
    object_type: PHYSICAL
    pins:
      - pin_id: "VCC"
        name: "VCC"
        direction: POWER
  "test:invalid-1":
    name: "Invalid Component"
    category: FAKE_CATEGORY
    object_type: PHYSICAL
    pins: []
''')
        reg = ComponentRegistry()
        count = reg.load_yaml(invalid_yaml)
        # Should load the valid one, skip the invalid one
        assert count == 1
        assert reg.has("test:duplicate-1")
        assert not reg.has("test:invalid-1")

        # Create another yaml with same ID to test overwrite behavior
        duplicate_yaml = tmp_path / "duplicate.yaml"
        duplicate_yaml.write_text('''
components:
  "test:duplicate-1":
    name: "Overwritten Component"
    category: MICROCONTROLLER
    object_type: PHYSICAL
    pins: []
''')
        # Loading the same ID should be rejected now
        count2 = reg.load_yaml(duplicate_yaml)
        assert count2 == 0
        assert reg.get("test:duplicate-1").name == "Valid Component"
