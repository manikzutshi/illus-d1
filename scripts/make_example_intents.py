"""Writes data/examples/<name>.intent.json - the functional intent each reference example was
designed for (what a user request would say). Used by the studio and as regression tests."""
import json
from pathlib import Path

D = Path("data/examples/intents")


def intent(signals, behaviors, required=(), processing="any"):
    return {"signals": [{"id": i, "role": r, "quantity": q, "component_hint": h, "description": ""} for i, r, q, h in signals],
            "behaviors": [{"id": bid, "when": {"input": i, "relation": rel, "threshold": thr}, "then": {"output": o, "effect": eff},
                           "description": desc} for bid, i, rel, thr, o, eff, desc in behaviors],
            "processing": processing, "required_components": list(required), "notes": []}


INTENTS = {
    "night_light_transistor": intent(
        [("light", "input", "light", None), ("lamp", "output", "light_emission", None)],
        [("dark_on", "light", "below", {"kind": "unspecified"}, "lamp", "on", "LED on when it is dark")], processing="analog"),
    "temperature_monitor": intent(
        [("temp", "input", "temperature", "DS18B20"), ("screen", "output", "display", None)],
        [("show", "temp", "changes", None, "screen", "display", "Show the temperature on the display")]),
    "pwm_motor_controller": intent(
        [("knob", "input", "setting", None), ("motor", "output", "motion_output", None)],
        [("speed", "knob", "proportional", None, "motor", "proportional", "Motor speed follows the knob")]),
    "relay_driver": intent(
        [("relay", "output", "switching", None)],
        [("cmd", None, "always", None, "relay", "on", "Firmware switches the relay")]),
    "astable_555_blinker": intent([("led", "output", "light_emission", None)],
                                  [("blink", None, "periodic", None, "led", "pulse", "LED blinks on its own")]),
    "half_adder": intent(
        [("a", "input", "logic", None), ("sum", "output", "logic", None)],
        [("s", "a", "changes", None, "sum", "display", "Sum output responds to input A")]),
    "cmos_inverter": intent(
        [("vin", "input", "logic", None), ("vout", "output", "logic", None)],
        [("inv", "vin", "absent", None, "vout", "on", "Output high when input is low")]),
    "opamp_noninverting": intent(
        [("in", "input", "setting", None), ("out", "output", "signal", None)],
        [("gain", "in", "proportional", None, "out", "proportional", "Output follows the input (gain 2)")]),
    "i2c_adc_logger": intent(
        [("knob", "input", "setting", None), ("log", "output", "storage", None)],
        [("record", "knob", "changes", None, "log", "display", "Store knob readings in the EEPROM")]),
}

for name, it in INTENTS.items():
    (D / f"{name}.json").write_text(json.dumps(it, indent=2) + "\n", encoding="utf-8")
print("wrote", len(INTENTS))
