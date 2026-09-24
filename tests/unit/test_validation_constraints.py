"""Tests for the 2D-studio-stage validator additions: supply semantics, constraint-driven rules,
polarity, pure-logic designs and the checks_run explainability record."""
import glob
import json
from pathlib import Path

import pytest
import yaml

from components.registry import get_default_registry
from core.models import EngineeringComponentInstance as C, EngineeringDesignProject, Net, PinRef
from validation.engine import DesignValidator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def validator():
    return DesignValidator(get_default_registry())


def net(nid, *refs, nt=None):
    return Net(net_id=nid, net_type=nt, connections=[PinRef(instance_id=r.split(".")[0], pin_id=r.split(".")[1]) for r in refs])


def codes(result):
    return [e.code for e in result.errors], [w.code for w in result.warnings], [i.code for i in result.infos]


def relay_design(with_diode: bool) -> EngineeringDesignProject:
    comps = [C(instance_id="j1", component_type="power:usb-5v"),
             C(instance_id="u1", component_type="board:esp32-devkit-v1"),
             C(instance_id="r1", component_type="passive:resistor-tht", parameters={"resistance": "1k"}),
             C(instance_id="q1", component_type="semiconductor:npn-bc547"),
             C(instance_id="k1", component_type="actuator:relay-5v-coil")]
    v5 = ["j1.VBUS", "u1.VIN", "k1.COIL1"]
    low = ["q1.C", "k1.COIL2"]
    if with_diode:
        comps.append(C(instance_id="d1", component_type="semiconductor:diode-1n4007"))
        v5.append("d1.K")
        low.append("d1.A")
    return EngineeringDesignProject(project_id="r", name="r", components=comps, nets=[
        net("v5", *v5), net("gnd", "j1.GND", "u1.GND1", "q1.E"), net("drv", "u1.GPIO23", "r1.PIN1"),
        net("base", "r1.PIN2", "q1.B"), net("low", *low)])


class TestFlyback:
    def test_relay_without_diode_is_error(self, validator):
        errors, _, _ = codes(validator.validate(relay_design(False)))
        assert "E017" in errors

    def test_relay_with_diode_passes(self, validator):
        res = validator.validate(relay_design(True))
        assert res.status.value == "PASS", res.errors

    def test_motor_without_diode_warns_but_driver_with_clamps_is_fine(self, validator):
        base = [C(instance_id="bt", component_type="power:battery-4xaa"), C(instance_id="q1", component_type="semiconductor:nmos-irlz44n"),
                C(instance_id="m1", component_type="actuator:dc-motor"), C(instance_id="r1", component_type="passive:resistor-tht", parameters={"resistance": "10k"})]
        d = EngineeringDesignProject(project_id="m", name="m", components=base, nets=[
            net("vm", "bt.POS", "m1.PIN1", "r1.PIN1"), net("gnd", "bt.NEG", "q1.S"), net("drain", "q1.D", "m1.PIN2"), net("g", "q1.G", "r1.PIN2")])
        _, warnings, _ = codes(validator.validate(d))
        assert "W005" in warnings

        l293 = [C(instance_id="bt", component_type="power:battery-4xaa"), C(instance_id="u1", component_type="driver:l293d"),
                C(instance_id="m1", component_type="actuator:dc-motor")]
        d2 = EngineeringDesignProject(project_id="m2", name="m2", components=l293, nets=[
            net("vm", "bt.POS", "u1.VCC1", "u1.VCC2", "u1.EN12"), net("gnd", "bt.NEG", "u1.GND1"),
            net("o1", "u1.1Y", "m1.PIN1"), net("o2", "u1.2Y", "m1.PIN2")])
        _, warnings, _ = codes(validator.validate(d2))
        assert "W005" not in warnings


def test_reversed_led_across_supply_is_e018(validator):
    d = EngineeringDesignProject(project_id="p", name="p", components=[
        C(instance_id="bt", component_type="power:battery-9v"), C(instance_id="d1", component_type="passive:led-5mm"),
        C(instance_id="r1", component_type="passive:resistor-tht", parameters={"resistance": "1k"})], nets=[
        net("v", "bt.POS", "r1.PIN1"), net("mid", "r1.PIN2", "d1.CATHODE"), net("gnd", "bt.NEG", "d1.ANODE")])
    # cathode is not on the supply net directly here (resistor in between) -> not flagged
    assert "E018" not in codes(validator.validate(d))[0]
    d2 = EngineeringDesignProject(project_id="p", name="p", components=[
        C(instance_id="bt", component_type="power:battery-9v"), C(instance_id="c1", component_type="passive:capacitor-electrolytic",
                                                                  parameters={"capacitance": "10u"})], nets=[
        net("v", "bt.POS", "c1.CATHODE"), net("gnd", "bt.NEG", "c1.ANODE")])
    assert "E018" in codes(validator.validate(d2))[0]


def test_one_wire_pullup_rule(validator):
    base = [C(instance_id="u1", component_type="board:esp32-devkit-v1"), C(instance_id="t1", component_type="sensor:ds18b20")]
    nets = [net("v", "u1.3V3", "t1.VCC"), net("g", "u1.GND1", "t1.GND"), net("dq", "t1.DQ", "u1.GPIO4")]
    d = EngineeringDesignProject(project_id="t", name="t", components=base, nets=nets)
    assert "W004" in codes(validator.validate(d))[1]
    d2 = EngineeringDesignProject(project_id="t", name="t",
                                  components=base + [C(instance_id="r1", component_type="passive:resistor-tht", parameters={"resistance": "4.7k"})],
                                  nets=[net("v", "u1.3V3", "t1.VCC", "r1.PIN1"), net("g", "u1.GND1", "t1.GND"),
                                        net("dq", "t1.DQ", "u1.GPIO4", "r1.PIN2")])
    assert "W004" not in codes(validator.validate(d2))[1]


def test_base_resistor_recommendation(validator):
    d = EngineeringDesignProject(project_id="b", name="b", components=[
        C(instance_id="u1", component_type="board:esp32-devkit-v1"), C(instance_id="q1", component_type="semiconductor:npn-bc547")], nets=[
        net("g", "u1.GND1", "q1.E"), net("b", "u1.GPIO4", "q1.B"), net("v", "u1.3V3", "q1.C")])
    assert "W003" in codes(validator.validate(d))[1]


def test_regulator_input_capacitor_warning(validator):
    d = EngineeringDesignProject(project_id="r", name="r", components=[
        C(instance_id="bt", component_type="power:battery-9v"), C(instance_id="u1", component_type="ic:regulator-lm7805")], nets=[
        net("vin", "bt.POS", "u1.VIN"), net("g", "bt.NEG", "u1.GND"), net("v5", "u1.VOUT", "u1.VOUT")])
    _, warnings, infos = codes(validator.validate(d))
    assert "W006" in warnings  # input capacitor is WARNING level
    assert "W006" in infos     # output capacitor is INFO level


class TestSupplySemantics:
    def test_regulator_output_is_a_source(self, validator):
        d = EngineeringDesignProject(project_id="s", name="s", components=[
            C(instance_id="bt", component_type="power:battery-9v"), C(instance_id="u1", component_type="ic:regulator-lm7805"),
            C(instance_id="u2", component_type="logic:74hc04")], nets=[
            net("vin", "bt.POS", "u1.VIN"), net("g", "bt.NEG", "u1.GND", "u2.GND"), net("v5", "u1.VOUT", "u2.VCC")])
        assert "E016" not in codes(validator.validate(d))[0]

    def test_supply_propagates_through_switch_but_not_without_source(self, validator):
        comps = [C(instance_id="bt", component_type="power:battery-9v"), C(instance_id="sw", component_type="passive:switch-slide-spst"),
                 C(instance_id="u1", component_type="ic:regulator-lm7805")]
        d = EngineeringDesignProject(project_id="s", name="s", components=comps, nets=[
            net("vb", "bt.POS", "sw.PIN1"), net("vin", "sw.PIN2", "u1.VIN"), net("g", "bt.NEG", "u1.GND")])
        assert "E016" not in codes(validator.validate(d))[0]
        d2 = EngineeringDesignProject(project_id="s", name="s", components=comps[1:] + [C(instance_id="bt", component_type="power:battery-9v")],
                                      nets=[net("vin", "sw.PIN2", "u1.VIN"), net("x", "sw.PIN1", "bt.NEG"), net("g", "bt.POS", "u1.GND")])
        assert "E016" in codes(validator.validate(d2))[0]

    def test_power_rail_voltage_parameter_is_used(self, validator):
        d = EngineeringDesignProject(project_id="v", name="v", components=[
            C(instance_id="rail", component_type="primitive:power-rail", parameters={"voltage": "3.3"}),
            C(instance_id="g", component_type="primitive:ground-rail"), C(instance_id="pir", component_type="sensor:hc-sr501")], nets=[
            net("v", "rail.VCC", "pir.VCC"), net("gnd", "g.GND", "pir.GND")])
        errors = validator.validate(d).errors
        assert any(e.code == "E014" and "3.3" in e.message for e in errors)

    def test_esp32_vin_is_a_sink(self, validator):
        d = EngineeringDesignProject(project_id="v", name="v", components=[
            C(instance_id="u1", component_type="board:esp32-devkit-v1"), C(instance_id="pir", component_type="sensor:hc-sr501")], nets=[
            net("v", "u1.VIN", "pir.VCC"), net("g", "u1.GND1", "pir.GND")])
        assert "E016" in codes(validator.validate(d))[0]


class TestPureLogic:
    def test_ideal_gate_diagram_needs_no_supply(self, validator):
        d = json.loads((ROOT / "data/examples/half_adder.json").read_text(encoding="utf-8"))
        res = validator.validate(EngineeringDesignProject.model_validate(d))
        assert res.status.value == "PASS" and not res.warnings

    def test_physical_design_still_requires_power(self, validator):
        d = EngineeringDesignProject(project_id="x", name="x", components=[C(instance_id="u1", component_type="logic:74hc00")],
                                     nets=[net("n", "u1.1A", "u1.1B")])
        errors = codes(validator.validate(d))[0]
        assert "E004" in errors and "E005" in errors


def test_checks_run_records_every_rule(validator):
    d = json.loads((ROOT / "data/examples/relay_driver.json").read_text(encoding="utf-8"))
    res = validator.validate(EngineeringDesignProject.model_validate(d))
    by_code = {c.code: c.outcome for c in res.checks_run}
    assert len(res.checks_run) == len(DesignValidator.CHECKS)
    assert by_code["E017/W005"] == "PASS"          # relay has its flyback diode
    assert by_code["W004"] == "NOT_APPLICABLE"      # nothing needs a pull-up
    assert all(c.outcome in ("PASS", "WARN", "NOT_APPLICABLE") for c in res.checks_run)


@pytest.mark.parametrize("path", sorted((ROOT / "data/examples").glob("*.json")), ids=lambda p: p.stem)
def test_reference_examples_are_valid(path, validator):
    res = validator.validate(EngineeringDesignProject.model_validate(json.loads(path.read_text(encoding="utf-8"))))
    assert res.status.value == "PASS", [e.message for e in res.errors]


# ── library integrity ──────────────────────────────────────────────────────

def test_every_declared_library_entry_loads():
    files = [ROOT / "data/components/registry.yaml"] + sorted((ROOT / "data/components/library").glob("*.yaml"))
    declared = set()
    for f in files:
        declared |= set(yaml.safe_load(f.read_text(encoding="utf-8"))["components"])
    reg = get_default_registry()
    assert {c.component_type_id for c in reg.list_all()} == declared


def test_library_metadata_quality():
    reg = get_default_registry()
    assert reg.count >= 80
    for ct in reg.list_all():
        assert ct.family, f"{ct.component_type_id} has no family"
        assert ct.symbol is not None
        pins = [p.pin_id for p in ct.pins]
        assert len(pins) == len(set(pins)), ct.component_type_id
        for p in ct.pins:
            if p.supply is not None:
                assert p.direction.value == "POWER", f"{ct.component_type_id}.{p.pin_id}: supply role on non-POWER pin"
        for c in ct.design_constraints:
            assert set(c.pins) <= set(pins), f"{ct.component_type_id}: constraint references unknown pin"


def test_ranked_search_is_semantic_and_strict():
    reg = get_default_registry()
    assert reg.search("temperature sensor")[0].family == "temperature_sensor"
    assert reg.search("5v regulator")[0].component_type_id == "ic:regulator-lm7805"
    assert reg.search("quantum flux capacitor") == []
    assert [c.component_type_id for c in reg.search("xor", limit=2)][0] == "primitive:gate-xor"


# ── supply topology rules added after a live AI design slipped past E009 ──

def test_battery_without_return_path_is_e019(validator):
    """Captured from a live Gemini run: the motor battery's negative terminal was left open."""
    d = EngineeringDesignProject.model_validate(json.loads(
        (ROOT / "tests/fixtures/ai_rejected/pico_motor_battery_return_open.json").read_text(encoding="utf-8")))
    res = validator.validate(d)
    errors, warnings, _ = codes(res)
    assert "E019" in errors
    assert "W007" in warnings        # the Pico's supply inputs are unconnected too
    fixed = d.model_copy(deep=True)
    next(n for n in fixed.nets if n.net_id == "net_ground").connections.append(PinRef(instance_id="bat1", pin_id="NEG"))
    assert "E019" not in codes(validator.validate(fixed))[0]


def test_supply_input_unconnected_warning(validator):
    d = EngineeringDesignProject(project_id="w", name="w", components=[
        C(instance_id="bt", component_type="power:battery-9v"), C(instance_id="u1", component_type="ic:timer-ne555"),
        C(instance_id="r1", component_type="passive:resistor-tht", parameters={"resistance": "1k"})], nets=[
        net("v", "bt.POS", "r1.PIN1"), net("g", "bt.NEG", "u1.GND"), net("o", "u1.OUT", "r1.PIN2")])
    assert "W007" in codes(validator.validate(d))[1]
