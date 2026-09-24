"""Functional / behavioural-intent validation tests.

Every fixture in tests/fixtures/functional is electrically valid; they differ only in whether
they do what the intent asks. (Regenerate with scripts/make_functional_fixtures.py.)
"""
import json
from pathlib import Path

import pytest

from components.registry import get_default_registry
from core.models import EngineeringDesignProject
from functional import FunctionalIntent, validate_function
from functional.graph import build_graph, find_paths
from functional.intent import canonical_quantity, normalize_intent
from functional.profiles import profile_for
from validation.engine import DesignValidator

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = sorted((ROOT / "tests/fixtures/functional").glob("*.json"))
REG = get_default_registry()


def load_case(name):
    c = json.loads((ROOT / "tests/fixtures/functional" / f"{name}.json").read_text(encoding="utf-8"))
    return EngineeringDesignProject.model_validate(c["design"]), FunctionalIntent.model_validate(c["intent"]), c["expect"]


def codes(report):
    return {f.code for f in report.findings}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_verdicts(path):
    design, intent, expect = load_case(path.stem)
    report = validate_function(design, intent, REG)
    assert report.status == expect["status"], [(f.code, f.message) for f in report.findings]
    for code in expect.get("codes", []):
        assert code in codes(report)
    for code in expect.get("absent_codes", []):
        assert code not in codes(report), [(f.code, f.message) for f in report.findings]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixtures_are_electrically_valid(path):
    """The point of the layer: these circuits all pass electrical validation."""
    design, _, _ = load_case(path.stem)
    assert DesignValidator(REG).validate(design).status.value == "PASS"


# ── the specific scenarios requested for this stage ────────────────────────

def test_1_actuator_not_in_control_path_fails():
    r = validate_function(*load_case("temp_alarm_buzzer_not_in_path")[:2], REG)
    f = next(f for f in r.findings if f.code == "F004")
    assert f.status == "FAIL" and "bz1" in f.affected_instances and "switches" in f.message
    assert f.repair_hint and "bjt_low_side_switch" in f.patterns


def test_2_correct_path_passes_with_traceable_explanation():
    r = validate_function(*load_case("temp_alarm_ok")[:2], REG)
    assert r.status == "PASS"
    b = r.behaviors[0]
    assert (b.input_instances, b.output_instances, b.decision_instance, b.driver_instance, b.threshold_set_by) == \
           (["u1"], ["bz1"], "u2", "q1", "rv1")
    assert b.path_sign == b.required_sign == 1
    text = " ".join(r.explanation)
    for phrase in ("sensing is implemented by u1", "threshold is set by rv1", "u2 (LM393) compares", "q1 (BC547) drives bz1"):
        assert phrase in text


def test_3_above_and_below_are_distinguished():
    above = validate_function(*load_case("temp_alarm_ok")[:2], REG)
    below = validate_function(*load_case("temp_alarm_below_requested")[:2], REG)
    assert above.status == "PASS"
    assert "F006" in codes(below)
    inverted = validate_function(*load_case("temp_alarm_inverted")[:2], REG)
    assert inverted.behaviors[0].path_sign == -1 and "F006" in codes(inverted)


def test_4_powered_but_unused_part_is_detected():
    r = validate_function(*load_case("requested_led_not_used")[:2], REG)
    assert any(f.code == "F009" and "d9" in f.affected_instances for f in r.findings)


def test_5_input_without_processing_stage():
    r = validate_function(*load_case("temp_alarm_no_decision")[:2], REG)
    assert "F005" in codes(r) and r.status == "FAIL"


def test_6_processing_output_not_connected():
    r = validate_function(*load_case("temp_alarm_output_not_connected_to_driver")[:2], REG)
    f = next(f for f in r.findings if f.code == "F003")
    assert "reaches u2" in f.message and "q1" in f.message


def test_7_insufficient_metadata_is_not_checkable_not_fail():
    r = validate_function(*load_case("thermistor_type_unknown")[:2], REG)
    assert r.status == "NOT_CHECKABLE" and not r.blocking()
    ntc = validate_function(*load_case("thermistor_ntc_top_ok")[:2], REG)
    assert ntc.status == "PASS"


def test_8_novel_topology_with_different_parts():
    """Op-amp used as comparator and a PNP high-side switch: the polarity chain is still derived."""
    r = validate_function(*load_case("dark_detector_opamp_pnp")[:2], REG)
    b = r.behaviors[0]
    assert b.decision_instance == "u1" and b.driver_instance == "q1"
    assert b.path_sign == 1 and b.required_sign == -1 and "F006" in codes(r)


def test_9_reference_designs_do_not_regress():
    expected = {"astable_555_blinker": "PASS", "cmos_inverter": "PASS", "half_adder": "PASS", "i2c_adc_logger": "PASS",
                "night_light_transistor": "WARN", "opamp_noninverting": "PASS", "pwm_motor_controller": "NOT_CHECKABLE",
                "relay_driver": "PASS", "temperature_monitor": "PASS"}
    for name, status in expected.items():
        d = EngineeringDesignProject.model_validate(json.loads((ROOT / f"data/examples/{name}.json").read_text(encoding="utf-8")))
        i = FunctionalIntent.model_validate(json.loads((ROOT / f"data/examples/intents/{name}.json").read_text(encoding="utf-8")))
        r = validate_function(d, i, REG)
        assert r.status == status, (name, [(f.code, f.message) for f in r.findings])
        assert not r.blocking()


def test_mcu_polarity_comes_from_logic_rules():
    ok = validate_function(*load_case("motion_alarm_mcu_rule")[:2], REG)
    assert ok.status == "PASS" and "logic rule 'r1'" in ok.behaviors[0].polarity_basis
    no_rule = validate_function(*load_case("motion_alarm_mcu_no_rule")[:2], REG)
    f = next(f for f in no_rule.findings if f.code == "F101")
    assert "logic rule" in f.repair_hint
    inverted = validate_function(*load_case("motion_alarm_mcu_rule_inverted")[:2], REG)
    assert "F006" in codes(inverted)


def test_driver_requirement_from_registry():
    r = validate_function(*load_case("button_relay_no_driver")[:2], REG)
    assert "F008" in codes(r)
    assert validate_function(*load_case("button_relay_ok")[:2], REG).status == "PASS"


def test_missing_input_or_output_part():
    design, intent, _ = load_case("temp_alarm_ok")
    intent = intent.model_copy(deep=True)
    intent.signals[0].quantity = "humidity"
    intent.signals[0].component_hint = None
    r = validate_function(design, intent, REG)
    assert "F001" in codes(r)
    intent2 = load_case("temp_alarm_ok")[1].model_copy(deep=True)
    intent2.signals[1].quantity = "display"
    assert "F002" in codes(validate_function(design, intent2, REG))


def test_autonomous_behaviour_needs_a_generator():
    d = EngineeringDesignProject.model_validate(json.loads((ROOT / "data/examples/astable_555_blinker.json").read_text(encoding="utf-8")))
    intent = FunctionalIntent.model_validate({"signals": [{"id": "led", "role": "output", "quantity": "led"}],
                                              "behaviors": [{"id": "b", "when": {"relation": "periodic"}, "then": {"output": "led", "effect": "pulse"}}]})
    r = validate_function(d, intent, REG)
    assert r.status == "PASS" and r.behaviors[0].input_instances == ["u1"]
    lone = d.model_copy(deep=True)
    lone.components = [c for c in lone.components if c.instance_id != "u1"]
    for n in lone.nets:
        n.connections = [pr for pr in n.connections if pr.instance_id != "u1"]
    lone.nets = [n for n in lone.nets if len(n.connections) >= 2]
    assert "F003" in codes(validate_function(lone, intent, REG))


def test_no_intent_gives_inferred_behaviour_and_not_checkable():
    d = EngineeringDesignProject.model_validate(json.loads((ROOT / "data/examples/common_emitter_amplifier.json").read_text(encoding="utf-8")))
    r = validate_function(d, None, REG)
    assert r.status == "NOT_CHECKABLE" and not r.intent_present
    inf = next(i for i in r.inferred if i.input_instance == "j1" and i.output_instance == "j2")
    assert inf.sign == -1        # common-emitter stage inverts


def test_vocabulary_normalisation():
    assert canonical_quantity("heat", "input") == "temperature"
    assert canonical_quantity("darkness", "input") == "light"
    assert canonical_quantity("beeper", "output") == "sound_emission"
    assert canonical_quantity("light", "output") == "light_emission"
    assert canonical_quantity("quantum flux", "input") is None
    it = FunctionalIntent.model_validate({"signals": [{"id": "x", "role": "input", "quantity": "flux"}],
                                          "behaviors": [{"id": "b", "when": {"input": "x", "relation": "above"}, "then": {"output": "nope", "effect": "on"}}]})
    _, notes = normalize_intent(it)
    assert any("outside the functional vocabulary" in n for n in notes) and any("unknown output" in n for n in notes)


def test_every_registry_part_has_a_profile_or_honest_fallback():
    for ct in REG.list_all():
        prof = profile_for(ct)
        assert prof.kind, ct.component_type_id
        pins = {p.pin_id for p in ct.pins}
        for src, dst, sign in prof.transfers:
            assert {src, dst} <= pins or prof.kind in ("converter",), f"{ct.component_type_id}: transfer {src}->{dst}"
            assert sign in (-1, 0, 1)
        for pair in prof.loads:
            assert set(pair) <= pins, ct.component_type_id
        assert set(prof.controls) <= pins, ct.component_type_id
        for pin in prof.outputs:
            assert pin in pins or prof.kind == "sensor", ct.component_type_id


def test_rails_are_never_traversed():
    design, _, _ = load_case("temp_alarm_ok")
    g = build_graph(design, REG)
    assert "net:v9" not in g.edges and "net:gnd" not in g.edges
    # the pull-up on the comparator output must not create a path from the supply
    assert not find_paths(g, "q:rv1", "a:bz1") or all(e.instance != "r1" for p in find_paths(g, "q:rv1", "a:bz1") for e in p)


def test_functional_report_is_deterministic():
    design, intent, _ = load_case("dark_detector_opamp_pnp")
    assert validate_function(design, intent, REG).model_dump() == validate_function(design, intent, REG).model_dump()


def test_requested_part_with_ratings_in_its_name_is_recognised():
    """Live regression: Gemini extracted required_components ['6V DC motor']; the rating made every
    design fail F009 until the repair budget ran out."""
    design, intent, _ = load_case("temp_alarm_ok")
    intent.required_components = ["small 5V buzzer", "10k resistor", "LM35"]
    r = validate_function(design, intent, REG)
    assert r.status == "PASS", [(f.code, f.message) for f in r.findings]


def test_requested_part_absent_from_library_warns_instead_of_blocking():
    design, intent, _ = load_case("temp_alarm_ok")
    intent.required_components = ["flux capacitor"]
    r = validate_function(design, intent, REG)
    f9 = [f for f in r.findings if f.code == "F009"]
    assert r.status == "WARN" and f9 and f9[0].status == "WARN" and not r.blocking()


def test_requested_library_part_missing_from_design_still_fails_with_the_part_id():
    design, intent, _ = load_case("temp_alarm_ok")
    intent.required_components = ["6V DC motor"]
    r = validate_function(design, intent, REG)
    f9 = [f for f in r.blocking() if f.code == "F009"]
    assert f9 and "actuator:dc-motor" in f9[0].repair_hint


def test_mcu_reading_both_outputs_of_a_sensor_names_the_pins():
    """Live regression: MQ-2 A0 (+) and D0 (-) both wired to the Uno, rule 'gas1 > threshold'."""
    design, intent, _ = load_case("live_gas_led_active_low_rule")
    d = design.model_dump()
    d["nets"].append({"net_id": "net_a0", "connections": [{"instance_id": "gas1", "pin_id": "A0"},
                                                          {"instance_id": "mcu1", "pin_id": "A0"}], "net_type": None})
    r = validate_function(EngineeringDesignProject.model_validate(d), intent, REG)
    f105 = [f for f in r.findings if f.code == "F105"]
    assert r.status == "WARN" and f105
    assert "A0" in f105[0].message and "D0" in f105[0].message and "which pin" in f105[0].message
