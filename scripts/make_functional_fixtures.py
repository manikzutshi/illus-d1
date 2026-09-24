"""Builds tests/fixtures/functional/*.json: {design, intent, expect} cases across functional classes.

Each case is a hand-built design plus the functional intent a user request would produce and
the expected functional verdict. Variants deliberately break one functional property.
"""
import copy
import json
from pathlib import Path

OUT = Path("tests/fixtures/functional")
OUT.mkdir(parents=True, exist_ok=True)


def design(pid, name, comps, nets, logic=None):
    return {"schema_version": "0.2.0", "project_id": pid, "name": name, "description": "",
            "components": [{"instance_id": i, "component_type": t, "parameters": p, "metadata": {}} for i, t, p in comps],
            "nets": [{"net_id": n, "connections": [{"instance_id": r.split(".")[0], "pin_id": r.split(".")[1]} for r in refs],
                      "net_type": None} for n, refs in nets],
            "logic": logic or [], "metadata": {}, "assumptions": []}


def intent(signals, behaviors, required=()):
    return {"signals": [{"id": i, "role": r, "quantity": q, "component_hint": h} for i, r, q, h in signals],
            "behaviors": [{"id": bid, "when": {"input": i, "relation": rel, "threshold": thr}, "then": {"output": o, "effect": eff}}
                          for bid, i, rel, thr, o, eff in behaviors],
            "required_components": list(required)}


CASES = {}

# ── class 1: analog threshold alarm (sensor → comparator → transistor → buzzer) ──
temp_comps = [("bt1", "power:usb-5v", {}), ("u1", "sensor:lm35", {}), ("rv1", "passive:potentiometer", {"resistance": "10k"}),
              ("u2", "ic:comparator-lm393", {}), ("r1", "passive:resistor-tht", {"resistance": "10k"}),
              ("r2", "passive:resistor-tht", {"resistance": "1k"}), ("q1", "semiconductor:npn-bc547", {}),
              ("bz1", "actuator:buzzer-piezo", {})]
temp_nets = [("v9", ["bt1.VBUS", "u1.VS", "rv1.VCC", "u2.VCC", "r1.PIN1", "bz1.VCC"]),
             ("gnd", ["bt1.GND", "u1.GND", "rv1.GND", "u2.GND", "q1.E"]),
             ("temp", ["u1.VOUT", "u2.IN1_P"]), ("ref", ["rv1.OUT", "u2.IN1_N"]),
             ("cmp", ["u2.OUT1", "r1.PIN2", "r2.PIN1"]), ("base", ["r2.PIN2", "q1.B"]), ("coll", ["q1.C", "bz1.GND"])]
temp_intent = intent([("temp", "input", "temperature", "LM35"), ("alarm", "output", "buzzer", None)],
                     [("b1", "temp", "above", {"kind": "adjustable"}, "alarm", "on")])
CASES["temp_alarm_ok"] = (design("t1", "Temperature alarm", temp_comps, temp_nets), temp_intent,
                          {"status": "PASS"})

broken = copy.deepcopy(temp_nets)
broken[-1] = ("coll", ["q1.C", "r2.PIN2"])            # buzzer removed from the collector...
broken[0] = ("v9", broken[0][1])
broken = [n for n in broken if n[0] != "base"] + [("base", ["q1.B", "bz1.GND"])]  # ...placeholder rewired below
CASES["temp_alarm_buzzer_not_in_path"] = (
    design("t2", "Temperature alarm (buzzer not controlled)", temp_comps,
           [("v9", ["bt1.VBUS", "u1.VS", "rv1.VCC", "u2.VCC", "r1.PIN1", "bz1.VCC"]),
            ("gnd", ["bt1.GND", "u1.GND", "rv1.GND", "u2.GND", "q1.E", "bz1.GND"]),
            ("temp", ["u1.VOUT", "u2.IN1_P"]), ("ref", ["rv1.OUT", "u2.IN1_N"]),
            ("cmp", ["u2.OUT1", "r1.PIN2", "r2.PIN1"]), ("base", ["r2.PIN2", "q1.B"])]),
    temp_intent, {"status": "FAIL", "codes": ["F004"]})

CASES["temp_alarm_inverted"] = (
    design("t3", "Temperature alarm (inverted)", temp_comps,
           [n if n[0] not in ("temp", "ref") else (n[0], [r.replace("IN1_P", "TMP").replace("IN1_N", "IN1_P").replace("TMP", "IN1_N") for r in n[1]])
            for n in temp_nets]),
    temp_intent, {"status": "FAIL", "codes": ["F006"]})

CASES["temp_alarm_below_requested"] = (
    design("t4", "Cold alarm", temp_comps, temp_nets),
    intent([("temp", "input", "temperature", None), ("alarm", "output", "buzzer", None)],
           [("b1", "temp", "below", {"kind": "adjustable"}, "alarm", "on")]),
    {"status": "FAIL", "codes": ["F006"]})

no_pot = [c for c in temp_comps if c[0] != "rv1"] + [("ra", "passive:resistor-tht", {"resistance": "10k"}),
                                                     ("rb", "passive:resistor-tht", {"resistance": "10k"})]
CASES["temp_alarm_fixed_reference"] = (
    design("t5", "Temperature alarm (fixed divider)", no_pot,
           [("v9", ["bt1.VBUS", "u1.VS", "ra.PIN1", "u2.VCC", "r1.PIN1", "bz1.VCC"]),
            ("gnd", ["bt1.GND", "u1.GND", "rb.PIN2", "u2.GND", "q1.E"]),
            ("temp", ["u1.VOUT", "u2.IN1_P"]), ("ref", ["ra.PIN2", "rb.PIN1", "u2.IN1_N"]),
            ("cmp", ["u2.OUT1", "r1.PIN2", "r2.PIN1"]), ("base", ["r2.PIN2", "q1.B"]), ("coll", ["q1.C", "bz1.GND"])]),
    temp_intent, {"status": "FAIL", "codes": ["F007"]})

CASES["temp_alarm_no_decision"] = (
    design("t6", "LM35 straight to buzzer", [("bt1", "power:battery-9v", {}), ("u1", "sensor:lm35", {}),
                                             ("r1", "passive:resistor-tht", {"resistance": "100"}), ("bz1", "actuator:buzzer-piezo", {})],
           [("v9", ["bt1.POS", "u1.VS"]), ("gnd", ["bt1.NEG", "u1.GND", "bz1.GND"]),
            ("t", ["u1.VOUT", "r1.PIN1"]), ("b", ["r1.PIN2", "bz1.VCC"])]),
    intent([("temp", "input", "temperature", None), ("alarm", "output", "buzzer", None)],
           [("b1", "temp", "above", {"kind": "fixed", "value": "30 degC"}, "alarm", "on")]),
    {"status": "FAIL", "codes": ["F005"]})

CASES["temp_alarm_output_not_connected_to_driver"] = (
    design("t7", "Comparator output goes nowhere", temp_comps,
           [("v9", ["bt1.VBUS", "u1.VS", "rv1.VCC", "u2.VCC", "r1.PIN1", "bz1.VCC"]),
            ("gnd", ["bt1.GND", "u1.GND", "rv1.GND", "u2.GND", "q1.E"]),
            ("temp", ["u1.VOUT", "u2.IN1_P"]), ("ref", ["rv1.OUT", "u2.IN1_N"]),
            ("cmp", ["u2.OUT1", "r1.PIN2"]), ("base", ["r2.PIN2", "q1.B"]), ("x", ["r2.PIN1", "u2.OUT2"]),
            ("coll", ["q1.C", "bz1.GND"])]),
    temp_intent, {"status": "FAIL", "codes": ["F003"]})

# ── class 2: light detector, different parts (thermistor-free, op-amp as comparator, PNP high side) ──
CASES["dark_detector_opamp_pnp"] = (
    design("l1", "Dark detector (MCP6001 + PNP high side)",
           [("j1", "power:usb-5v", {}), ("ldr", "sensor:photoresistor", {}), ("rt", "passive:resistor-tht", {"resistance": "10k"}),
            ("ra", "passive:resistor-tht", {"resistance": "10k"}), ("rb", "passive:resistor-tht", {"resistance": "10k"}),
            ("u1", "ic:opamp-mcp6001", {}), ("r1", "passive:resistor-tht", {"resistance": "4.7k"}),
            ("q1", "semiconductor:pnp-2n3906", {}), ("r2", "passive:resistor-tht", {"resistance": "220"}),
            ("d1", "passive:led-5mm", {"color": "white"})],
           [("v5", ["j1.VBUS", "rt.PIN1", "ra.PIN1", "u1.VDD", "q1.E"]),
            ("gnd", ["j1.GND", "ldr.PIN2", "rb.PIN2", "u1.VSS", "d1.CATHODE"]),
            ("sense", ["rt.PIN2", "ldr.PIN1", "u1.VIN_P"]), ("ref", ["ra.PIN2", "rb.PIN1", "u1.VIN_N"]),
            ("o", ["u1.VOUT", "r1.PIN1"]), ("b", ["r1.PIN2", "q1.B"]), ("c", ["q1.C", "r2.PIN1"]), ("a", ["r2.PIN2", "d1.ANODE"])]),
    intent([("light", "input", "light", None), ("lamp", "output", "LED", None)],
           [("b1", "light", "below", {"kind": "fixed"}, "lamp", "on")]),
    # LDR at the bottom: IN+ falls with light (-1); op-amp +1; PNP base→collector -1; LED anode side +1  => +1: ON when bright
    {"status": "FAIL", "codes": ["F006"]})

# ── class 3: microcontroller designs (polarity from logic rules) ──
mcu = [("u1", "board:esp32-devkit-v1", {}), ("pir", "sensor:hc-sr501", {}), ("j1", "power:usb-5v", {}),
       ("r1", "passive:resistor-tht", {"resistance": "1k"}), ("q1", "semiconductor:npn-bc547", {}),
       ("bz1", "actuator:buzzer-piezo", {})]
mcu_nets = [("v5", ["j1.VBUS", "u1.VIN", "pir.VCC", "bz1.VCC"]), ("gnd", ["j1.GND", "u1.GND1", "pir.GND", "q1.E"]),
            ("m", ["pir.OUT", "u1.GPIO4"]), ("d", ["u1.GPIO5", "r1.PIN1"]), ("b", ["r1.PIN2", "q1.B"]), ("c", ["q1.C", "bz1.GND"])]
motion_intent = intent([("motion", "input", "movement", None), ("alarm", "output", "alarm", None)],
                       [("b1", "motion", "present", None, "alarm", "on")])
rule = [{"rule_id": "r1", "conditions": [{"input_instance": "pir", "condition": "==", "value": "HIGH"}], "operator": "AND",
         "actions": [{"output_instance": "bz1", "state": "HIGH"}]}]
CASES["motion_alarm_mcu_rule"] = (design("m1", "Motion alarm (ESP32)", mcu, mcu_nets, rule), motion_intent, {"status": "PASS"})
CASES["motion_alarm_mcu_no_rule"] = (design("m2", "Motion alarm, no firmware rule", mcu, mcu_nets), motion_intent,
                                     {"status": "NOT_CHECKABLE", "codes": ["F101"]})
bad_rule = copy.deepcopy(rule)
bad_rule[0]["actions"][0]["state"] = "LOW"
CASES["motion_alarm_mcu_rule_inverted"] = (design("m3", "Motion alarm, inverted rule", mcu, mcu_nets, bad_rule), motion_intent,
                                           {"status": "FAIL", "codes": ["F006"]})

# ── class 4: button → MCU → relay (driver requirement) ──
relay_c = [("u1", "board:arduino-uno-r3", {}), ("sw1", "passive:push-button-2pin", {}), ("rpd", "passive:resistor-tht", {"resistance": "10k"}),
           ("k1", "actuator:relay-5v-coil", {}), ("d1", "semiconductor:diode-1n4007", {}),
           ("rb", "passive:resistor-tht", {"resistance": "1k"}), ("q1", "active:transistor-npn-2n2222", {})]
relay_ok_nets = [("v5", ["u1.5V", "sw1.PIN1", "k1.COIL1", "d1.K"]), ("gnd", ["u1.GND1", "rpd.PIN2", "q1.E"]),
                 ("btn", ["sw1.PIN2", "rpd.PIN1", "u1.D2"]), ("drv", ["u1.D7", "rb.PIN1"]), ("base", ["rb.PIN2", "q1.B"]),
                 ("coil", ["q1.C", "k1.COIL2", "d1.A"])]
btn_rule = [{"rule_id": "r1", "conditions": [{"input_instance": "sw1", "condition": "==", "value": "HIGH"}], "operator": "AND",
             "actions": [{"output_instance": "k1", "state": "ON"}]}]
relay_intent = intent([("btn", "input", "push button", None), ("load", "output", "relay", None)],
                      [("b1", "btn", "pressed", None, "load", "on")])
CASES["button_relay_ok"] = (design("r1", "Button relay", relay_c, relay_ok_nets, btn_rule), relay_intent, {"status": "PASS"})
CASES["button_relay_no_driver"] = (
    design("r2", "Relay coil on a GPIO", [c for c in relay_c if c[0] not in ("q1", "rb")],
           [("v5", ["u1.5V", "sw1.PIN1"]), ("gnd", ["u1.GND1", "rpd.PIN2", "k1.COIL2", "d1.A"]),
            ("btn", ["sw1.PIN2", "rpd.PIN1", "u1.D2"]), ("drv", ["u1.D7", "k1.COIL1", "d1.K"])], btn_rule),
    relay_intent, {"status": "FAIL", "codes": ["F008"]})

# ── class 5: sensor → converter → MCU → display ──
CASES["adc_to_display"] = (
    design("s1", "Gas level display",
           [("u1", "board:esp32-devkit-v1", {}), ("g1", "sensor:mq2", {}), ("u2", "adc:ads1115", {}), ("ds1", "actuator:oled-i2c", {}),
            ("j1", "power:usb-5v", {}), ("r1", "passive:resistor-tht", {"resistance": "4.7k"}), ("r2", "passive:resistor-tht", {"resistance": "4.7k"})],
           [("v5", ["j1.VBUS", "u1.VIN", "g1.VCC"]), ("v3", ["u1.3V3", "u2.VDD", "ds1.VCC", "r1.PIN1", "r2.PIN1"]),
            ("gnd", ["j1.GND", "u1.GND1", "g1.GND", "u2.GND", "u2.ADDR", "ds1.GND"]),
            ("a0", ["g1.A0", "u2.AIN0"]), ("sda", ["u2.SDA", "u1.GPIO21", "r1.PIN2"]), ("scl", ["u2.SCL", "u1.GPIO22", "r2.PIN2"]),
            ("dsda", ["ds1.SDA", "u1.GPIO18"]), ("dscl", ["ds1.SCL", "u1.GPIO19"])]),
    intent([("gas", "input", "smoke", None), ("screen", "output", "display", None)],
           [("b1", "gas", "changes", None, "screen", "display")]),
    {"status": "PASS"})

# ── class 6: unknown metadata (thermistor without NTC/PTC type) ──
CASES["thermistor_type_unknown"] = (
    design("u1", "Overheat LED (thermistor, type not stated)",
           [("bt1", "power:battery-9v", {}), ("th", "sensor:thermistor", {}), ("rt", "passive:resistor-tht", {"resistance": "10k"}),
            ("ra", "passive:resistor-tht", {"resistance": "10k"}), ("rb", "passive:resistor-tht", {"resistance": "10k"}),
            ("u2", "ic:comparator-lm393", {}), ("rp", "passive:resistor-tht", {"resistance": "1k"}), ("d1", "passive:led-5mm", {})],
           [("v9", ["bt1.POS", "th.PIN1", "ra.PIN1", "u2.VCC", "rp.PIN1"]), ("gnd", ["bt1.NEG", "rt.PIN2", "rb.PIN2", "u2.GND", "d1.CATHODE"]),
            ("s", ["th.PIN2", "rt.PIN1", "u2.IN1_P"]), ("ref", ["ra.PIN2", "rb.PIN1", "u2.IN1_N"]),
            ("o", ["u2.OUT1", "rp.PIN2", "d1.ANODE"])]),
    intent([("t", "input", "heat", None), ("warn", "output", "led", None)],
           [("b1", "t", "above", {"kind": "fixed"}, "warn", "on")]),
    {"status": "NOT_CHECKABLE", "codes": ["F101"]})

nt = copy.deepcopy(CASES["thermistor_type_unknown"])
nt[0]["components"][1]["parameters"] = {"type": "NTC"}
CASES["thermistor_ntc_top_ok"] = (nt[0], nt[1], {"status": "PASS"})   # NTC at top: temp↑ → R↓ → node↑ → LED on when hot

# ── class 7: requested part present but unused, and extra unused part ──
unused = copy.deepcopy(CASES["temp_alarm_ok"])
unused[0]["components"].append({"instance_id": "d9", "component_type": "passive:led-5mm", "parameters": {}, "metadata": {}})
unused[0]["nets"][0]["connections"].append({"instance_id": "d9", "pin_id": "ANODE"})
unused[0]["nets"].append({"net_id": "x9", "connections": [{"instance_id": "d9", "pin_id": "CATHODE"}, {"instance_id": "u2", "pin_id": "IN2_P"}], "net_type": None})
u_int = copy.deepcopy(temp_intent)
u_int["required_components"] = ["LED"]
CASES["requested_led_not_used"] = (unused[0], u_int, {"status": "FAIL", "codes": ["F009"]})

# ── class 8: pure logic (gate level), different processing type ──
CASES["logic_nand_indicator"] = (
    design("g1", "Alarm unless both inputs high",
           [("a", "primitive:logic-input", {}), ("b", "primitive:logic-input", {}), ("u1", "primitive:gate-nand", {}), ("y", "primitive:logic-output", {})],
           [("na", ["a.OUT", "u1.A"]), ("nb", ["b.OUT", "u1.B"]), ("ny", ["u1.Y", "y.IN"])]),
    intent([("in_a", "input", "logic", None), ("out", "output", "logic output", None)],
           [("b1", "in_a", "absent", None, "out", "on")]),
    {"status": "PASS"})

# ── class 9: regressions from live Gemini runs (designs as the model produced them) ──
# Buzzer powered only through the LM393's 10k open-collector pull-up: ~0.5 mA, never sounds.
CASES["live_temp_alarm_pullup_powered_buzzer"] = (
    design("lv1", "Temperature alarm (buzzer on open-collector pull-up)",
           [("sens1", "sensor:lm35", {}), ("pot1", "passive:potentiometer", {"resistance": "10k"}),
            ("comp1", "ic:comparator-lm393", {}), ("buz1", "actuator:buzzer-piezo", {}),
            ("rpu1", "passive:resistor-tht", {"resistance": "10k"}), ("pwr1", "power:usb-5v", {}), ("gnd1", "primitive:ground-rail", {})],
           [("vcc_net", ["pwr1.VBUS", "comp1.VCC", "sens1.VS", "pot1.VCC", "rpu1.PIN1"]),
            ("gnd_net", ["gnd1.GND", "comp1.GND", "sens1.GND", "pot1.GND", "pwr1.GND", "buz1.GND"]),
            ("sensor_signal_net", ["sens1.VOUT", "comp1.IN1_P"]), ("threshold_net", ["pot1.OUT", "comp1.IN1_N"]),
            ("alarm_output_net", ["comp1.OUT1", "rpu1.PIN2", "buz1.VCC"])]),
    temp_intent, {"status": "FAIL", "codes": ["F010"]})

# Daylight detector with the LED reversed (cathode to +9 V through its resistor): never lights.
day_comps = [("batt1", "power:battery-9v", {}), ("ldr1", "sensor:photoresistor", {}),
             ("r_div", "passive:resistor-tht", {"resistance": "10k"}), ("r_base", "passive:resistor-tht", {"resistance": "1k"}),
             ("q1", "semiconductor:npn-bc547", {}), ("r_led", "passive:resistor-tht", {"resistance": "360"}),
             ("led1", "passive:led-5mm", {}), ("gnd1", "primitive:ground-rail", {})]
day_nets = [("net_vcc", ["batt1.POS", "ldr1.PIN1", "r_led.PIN2"]), ("net_gnd", ["batt1.NEG", "r_div.PIN2", "q1.E", "gnd1.GND"]),
            ("net_divider", ["ldr1.PIN2", "r_div.PIN1", "r_base.PIN1"]), ("net_base", ["r_base.PIN2", "q1.B"]),
            ("net_collector", ["q1.C", "led1.ANODE"]), ("net_led_series", ["led1.CATHODE", "r_led.PIN1"])]
day_intent = intent([("light_sensor", "input", "light", None), ("led", "output", "LED", None)],
                    [("b1", "light_sensor", "above", {"kind": "unspecified"}, "led", "on")])
CASES["live_daylight_led_reversed"] = (design("lv2", "Daylight LED (LED reversed)", day_comps, day_nets), day_intent,
                                       {"status": "FAIL", "codes": ["F011"], "absent_codes": ["F006"]})
day_fixed = [(n, [r.replace("led1.ANODE", "X").replace("led1.CATHODE", "led1.ANODE").replace("X", "led1.CATHODE") for r in refs])
             for n, refs in day_nets]
CASES["live_daylight_led_fixed"] = (design("lv3", "Daylight LED", day_comps, day_fixed), day_intent,
                                    {"status": "WARN", "codes": ["F102"]})

# MQ-2 module D0 is active-low: 'D0 == HIGH -> LED on' lights the LED when there is NO gas.
gas_comps = [("mcu1", "board:arduino-uno-r3", {}), ("gas1", "sensor:mq2", {}), ("led1", "passive:led-5mm", {}),
             ("r1", "passive:resistor-tht", {"resistance": "150"}), ("pwr1", "primitive:power-rail", {}), ("gnd1", "primitive:ground-rail", {})]
gas_nets = [("net_5v", ["pwr1.VCC", "mcu1.5V", "gas1.VCC"]), ("net_gnd", ["gnd1.GND", "mcu1.GND1", "gas1.GND", "led1.CATHODE"]),
            ("net_sensor_out", ["gas1.D0", "mcu1.D2"]), ("net_led_drive", ["mcu1.D13", "r1.PIN1"]),
            ("net_led_resistor", ["r1.PIN2", "led1.ANODE"])]
gas_intent = intent([("gas_sensor", "input", "gas", None), ("warning_led", "output", "LED", None)],
                    [("warn_on_gas", "gas_sensor", "present", None, "warning_led", "on")])


def gas_rule(level):
    return [{"rule_id": "warn_on_gas", "conditions": [{"input_instance": "gas1", "condition": "==", "value": level}],
             "operator": "AND", "actions": [{"output_instance": "led1", "state": "HIGH"}]}]


CASES["live_gas_led_active_high_rule"] = (design("lv4", "Gas warning (rule assumes active-high D0)", gas_comps, gas_nets, gas_rule("HIGH")),
                                          gas_intent, {"status": "FAIL", "codes": ["F006"]})
CASES["live_gas_led_active_low_rule"] = (design("lv5", "Gas warning", gas_comps, gas_nets, gas_rule("LOW")),
                                         gas_intent, {"status": "PASS"})
# Same intent with the signal declarations dropped (as Gemini returned it): recovered from the ids, still graded.
no_sig = copy.deepcopy(gas_intent)
no_sig["signals"] = []
CASES["live_gas_intent_signals_undeclared"] = (design("lv6", "Gas warning", gas_comps, gas_nets, gas_rule("LOW")),
                                               no_sig, {"status": "PASS", "absent_codes": ["F106"]})

# Freezer alarm as generated: buzzer between the NPN collector and ground (nothing can push current
# through it), and LM35 on IN+ (which, once the buzzer is fixed, sounds when WARM). The two defects
# cancel in a pure sign analysis; F010 catches the first, F006 the second after it is fixed.
frz_comps = [("p1", "power:usb-5v", {}), ("g1", "primitive:ground-rail", {}), ("sensor1", "sensor:lm35", {}),
             ("pot1", "passive:potentiometer", {"resistance": "10k"}), ("comp1", "ic:comparator-lm393", {}),
             ("r_pullup", "passive:resistor-tht", {"resistance": "10k"}), ("r_base", "passive:resistor-tht", {"resistance": "1k"}),
             ("q1", "semiconductor:npn-bc547", {}), ("buzzer1", "actuator:buzzer-piezo", {})]
frz_common = [("NET_TEMP_SENSE", ["sensor1.VOUT", "comp1.IN1_P"]), ("NET_THRESHOLD_SET", ["pot1.OUT", "comp1.IN1_N"]),
              ("NET_COMP_OUT", ["comp1.OUT1", "r_pullup.PIN2", "r_base.PIN1"]), ("NET_BASE_DRIVE", ["r_base.PIN2", "q1.B"])]
frz_intent = intent([("temp", "input", "temperature", None), ("alarm", "output", "buzzer", None)],
                    [("b1", "temp", "below", {"kind": "adjustable"}, "alarm", "on")])
CASES["live_freezer_buzzer_under_collector"] = (
    design("lv7", "Freezer alarm (buzzer below the collector)", frz_comps,
           [("VCC_5V", ["p1.VBUS", "comp1.VCC", "sensor1.VS", "pot1.VCC", "r_pullup.PIN1"]),
            ("GND_RAIL", ["g1.GND", "p1.GND", "sensor1.GND", "pot1.GND", "comp1.GND", "q1.E", "buzzer1.GND"]),
            *frz_common, ("NET_BUZZER_DRIVE", ["q1.C", "buzzer1.VCC"])]),
    frz_intent, {"status": "FAIL", "codes": ["F010"]})
CASES["live_freezer_buzzer_fixed_still_inverted"] = (
    design("lv8", "Freezer alarm (low-side buzzer, comparator not inverted)", frz_comps,
           [("VCC_5V", ["p1.VBUS", "comp1.VCC", "sensor1.VS", "pot1.VCC", "r_pullup.PIN1", "buzzer1.VCC"]),
            ("GND_RAIL", ["g1.GND", "p1.GND", "sensor1.GND", "pot1.GND", "comp1.GND", "q1.E"]),
            *frz_common, ("NET_BUZZER_DRIVE", ["q1.C", "buzzer1.GND"])]),
    frz_intent, {"status": "FAIL", "codes": ["F006"], "absent_codes": ["F010"]})

# Button -> Uno -> IRLZ44N -> 6 V motor, with the firmware rule written against the MOSFET the pin drives
# ("btn1 == LOW -> q1 HIGH"). Button to ground: pressed reads LOW (internal pull-up).
bm_comps = [("u1", "board:arduino-uno-r3", {}), ("bat1", "power:battery-4xaa", {}), ("m1", "actuator:dc-motor", {}),
            ("btn1", "passive:push-button-2pin", {}), ("q1", "semiconductor:nmos-irlz44n", {}),
            ("rg1", "passive:resistor-tht", {"resistance": "100"}), ("rpd1", "passive:resistor-tht", {"resistance": "10k"}),
            ("d1", "semiconductor:diode-1n4007", {})]
bm_nets = [("net_btn_signal", ["u1.D2", "btn1.PIN1"]), ("net_btn_gnd", ["btn1.PIN2", "u1.GND1"]),
           ("net_ctrl", ["u1.D3", "rg1.PIN1"]), ("net_gate", ["rg1.PIN2", "rpd1.PIN1", "q1.G"]),
           ("net_motor_pos", ["bat1.POS", "m1.PIN1", "d1.K"]), ("net_motor_low", ["m1.PIN2", "q1.D", "d1.A"]),
           ("net_gnd", ["q1.S", "rpd1.PIN2", "u1.GND2", "bat1.NEG"])]
bm_intent = intent([("btn", "input", "press", None), ("motor", "output", "motor", None)],
                   [("motor_run", "btn", "pressed", None, "motor", "on")], required=["6V DC motor", "4xAA battery pack"])


def bm_rule(level):
    return [{"rule_id": "motor_run_rule", "conditions": [{"input_instance": "btn1", "condition": "==", "value": level}],
             "operator": "AND", "actions": [{"output_instance": "q1", "state": "HIGH"}]}]


CASES["live_button_motor_rule_on_mosfet"] = (design("lv9", "Button motor (Uno + IRLZ44N)", bm_comps, bm_nets, bm_rule("LOW")),
                                             bm_intent, {"status": "PASS"})
CASES["live_button_motor_rule_wrong_level"] = (design("lv10", "Button motor (rule reads HIGH)", bm_comps, bm_nets, bm_rule("HIGH")),
                                               bm_intent, {"status": "FAIL", "codes": ["F006"]})

for name, (d, i, e) in CASES.items():
    (OUT / f"{name}.json").write_text(json.dumps({"design": d, "intent": i, "expect": e}, indent=2) + "\n", encoding="utf-8")
print("wrote", len(CASES))
