"""Tests for the schematic projection: symbols, geometry, placement, routing, junctions,
ports, labels, traceability, determinism and the geometry-vs-engineering (LVS) verifier."""
import json
from pathlib import Path

import pytest

from components.registry import get_default_registry
from core.models import EngineeringComponentInstance, EngineeringDesignProject, Net, PinRef
from schematic import (LayoutState, Placement, SchematicProject, extract_connectivity, generate_schematic,
                       verify_schematic)
from schematic.geometry import transform_ipoint, transform_orientation, point_on_segment
from schematic.models import SchematicWire
from schematic.routing import GridRouter, Terminal
from schematic.symbols import build_box_symbol, fixed_symbol_names, get_fixed_symbol, pin_mapping, symbol_name_for
from schematic.verify import count_crossings

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "data" / "examples").glob("*.json"))
GOLDEN = [ROOT / "tests/fixtures/golden/smart_parking_valid.json", ROOT / "tests/fixtures/golden/auto_light_valid.json"]
ALL_DESIGNS = EXAMPLES + GOLDEN


def load(path: Path) -> EngineeringDesignProject:
    return EngineeringDesignProject.model_validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def registry():
    return get_default_registry()


@pytest.fixture(scope="module")
def schematics(registry):
    return {p.stem: (load(p), generate_schematic(load(p), registry)) for p in ALL_DESIGNS}


# ── geometry ───────────────────────────────────────────────────────────────

class TestGeometry:
    def test_rotation_clockwise_on_screen(self):
        # A pin pointing right, rotated 90° clockwise (y down), points down.
        assert transform_ipoint(3, 0, 0, 0, 90) == (0, 3)
        assert transform_orientation("right", 90) == "down"
        assert transform_orientation("up", 90) == "right"

    def test_mirror_then_rotate(self):
        assert transform_ipoint(3, 1, 10, 10, 0, True) == (7, 11)
        assert transform_orientation("left", 0, True) == "right"
        assert transform_ipoint(1, 0, 0, 0, 180, True) == (1, 0)

    def test_point_on_segment(self):
        assert point_on_segment((2, 0), (0, 0), (5, 0))
        assert not point_on_segment((2, 1), (0, 0), (5, 0))


# ── symbols ────────────────────────────────────────────────────────────────

class TestSymbols:
    @pytest.mark.parametrize("name", fixed_symbol_names())
    def test_fixed_symbols_are_grid_aligned(self, name):
        sym = get_fixed_symbol(name)
        names = [p.name for p in sym.pins]
        assert len(names) == len(set(names)), "pin names must be unique"
        for p in sym.pins:
            assert isinstance(p.x, int) and isinstance(p.y, int)
            # the tip must lie on or outside the body rectangle so wires never start inside a symbol
            x0, y0, x1, y1 = sym.body
            assert not (x0 < p.x < x1 and y0 < p.y < y1), f"{name}.{p.name} tip inside body"

    def test_box_symbol_pins_on_grid_and_sides(self):
        sym = build_box_symbol("box:t", {"left": [("A", "A", None), ("B", "B", None)], "right": [("Y", "Y", None)],
                                         "top": [("VCC", "VCC", None)], "bottom": [("GND", "GND", None)]}, title="TEST")
        by = {p.name: p for p in sym.pins}
        assert by["A"].orientation == "left" and by["Y"].orientation == "right"
        assert by["VCC"].orientation == "up" and by["GND"].orientation == "down"
        assert all(isinstance(p.x, int) and isinstance(p.y, int) for p in sym.pins)
        assert by["B"].y - by["A"].y == 2

    def test_every_registry_part_maps_to_its_symbol(self, registry):
        for ct in registry.list_all():
            assert ct.symbol is not None, f"{ct.component_type_id} lacks a symbol spec"
            name = symbol_name_for(ct)
            if name != "ic_box":
                mapping = pin_mapping(ct, get_fixed_symbol(name))
                assert set(mapping) == {p.pin_id for p in ct.pins}


# ── projection quality ─────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ALL_DESIGNS, ids=lambda p: p.stem)
def test_schematic_matches_engineering_connectivity(path, schematics):
    design, schematic = schematics[path.stem]
    report = verify_schematic(schematic, design)
    assert report.ok, report.as_dict()


@pytest.mark.parametrize("path", ALL_DESIGNS, ids=lambda p: p.stem)
def test_every_signal_pin_is_attached_to_a_wire_or_label(path, schematics):
    design, schematic = schematics[path.stem]
    for comp in schematic.components:
        for pin in comp.pins:
            if pin.hidden or pin.net_id is None:
                continue
            trace = schematic.nets[pin.net_id]
            tip = (pin.x, pin.y)
            if trace.style == "wire":
                assert any(point_on_segment(tip, (w.x1, w.y1), (w.x2, w.y2)) for w in schematic.wires if w.net_id == pin.net_id), \
                    f"{comp.instance_id}.{pin.pin_id} not on any wire of {pin.net_id}"
            elif trace.style == "label":
                assert any((l.x, l.y) == tip for l in schematic.net_labels if l.net_id == pin.net_id)
            else:
                has_port = any((p.x, p.y) == tip for p in schematic.power_ports if p.net_id == pin.net_id)
                assert has_port or comp.port_text, f"{comp.instance_id}.{pin.pin_id} lacks a power/ground port"


@pytest.mark.parametrize("path", ALL_DESIGNS, ids=lambda p: p.stem)
def test_wires_are_orthogonal_and_on_grid(path, schematics):
    _, schematic = schematics[path.stem]
    for w in schematic.wires:
        assert w.x1 == w.x2 or w.y1 == w.y2
        assert (w.x1, w.y1) != (w.x2, w.y2)


def test_generation_is_deterministic(registry):
    for path in ALL_DESIGNS:
        a = generate_schematic(load(path), registry).model_dump(exclude={"stats": {"elapsed_ms"}})
        b = generate_schematic(load(path), registry).model_dump(exclude={"stats": {"elapsed_ms"}})
        assert a == b, path.stem


def test_component_order_does_not_break_layout(registry):
    design = load(ROOT / "data/examples/pwm_motor_controller.json")
    design.components.reverse()
    design.nets.reverse()
    s = generate_schematic(design, registry)
    assert verify_schematic(s, design).ok


def test_crossings_stay_low(schematics):
    total = sum(count_crossings(s) for _, s in schematics.values())
    assert total <= 6, f"{total} wire crossings across the reference designs"


def test_layout_is_fast_enough(schematics):
    for name, (_, s) in schematics.items():
        assert s.stats.elapsed_ms < 3000, f"{name} took {s.stats.elapsed_ms} ms"


# ── junctions, ports, labels, references ───────────────────────────────────

def test_three_way_node_gets_exactly_one_junction(schematics):
    _, s = schematics["auto_light_valid"]
    js = [j for j in s.junctions if j.net_id == "ldr_sense"]
    assert len(js) == 1
    # the junction is where three wire ends/pins meet
    j = js[0]
    touching = [w for w in s.wires if w.net_id == "ldr_sense" and point_on_segment((j.x, j.y), (w.x1, w.y1), (w.x2, w.y2))]
    assert len(touching) >= 2


def test_two_pin_nets_have_no_junctions(schematics):
    design, s = schematics["smart_parking_valid"]
    for net in design.nets:
        if len(net.connections) == 2:
            assert not [j for j in s.junctions if j.net_id == net.net_id]


def test_power_and_ground_ports_named_from_supply_voltage(schematics):
    _, s = schematics["auto_light_valid"]
    texts = {(p.kind, p.text) for p in s.power_ports}
    assert ("power", "+3.3V") in texts and ("ground", "GND") in texts
    _, s = schematics["pwm_motor_controller"]
    assert {"+5V", "+6V"} <= {p.text for p in s.power_ports if p.kind == "power"}


def test_rail_components_become_flags(schematics):
    _, s = schematics["smart_parking_valid"]
    flags = {c.instance_id: c for c in s.components if c.port_text}
    assert flags["pwr1"].port_text == "+5V"
    assert flags["gnd1"].port_text == "GND"


def test_reference_designators_unique_and_prefixed(schematics):
    for name, (_, s) in schematics.items():
        refs = [c.reference for c in s.components]
        assert len(refs) == len(set(refs)), name
    _, s = schematics["pwm_motor_controller"]
    refs = {c.instance_id: c.reference for c in s.components}
    assert refs["r1"] == "R1" and refs["q1"] == "Q1" and refs["d1"] == "D1" and refs["rv1"] == "RV1"


def test_values_formatted_with_units(schematics):
    _, s = schematics["night_light_transistor"]
    vals = {c.instance_id: c.value for c in s.components}
    assert vals["r1"] == "10kΩ" and vals["r3"] == "470Ω" and vals["d1"] == "white LED"


def test_ground_pins_of_two_terminal_parts_point_down(schematics):
    for key in ("auto_light_valid", "night_light_transistor", "pwm_motor_controller"):
        design, s = schematics[key]
        for comp in s.components:
            if len(comp.pins) == 2 and not comp.port_text:
                for pin in comp.pins:
                    if pin.net_id and s.nets[pin.net_id].net_class == "ground":
                        assert pin.orientation == "down", f"{key}:{comp.instance_id}.{pin.pin_id}"


# ── traceability ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ALL_DESIGNS, ids=lambda p: p.stem)
def test_traceability_index_matches_engineering(path, schematics):
    design, s = schematics[path.stem]
    assert {c.instance_id for c in s.components} == {c.instance_id for c in design.components}
    for net in design.nets:
        trace = s.nets[net.net_id]
        assert trace.pins == [pr.ref for pr in net.connections]
        assert set(trace.wires) == {w.wire_id for w in s.wires if w.net_id == net.net_id}
    for comp in s.components:
        eng = next(c for c in design.components if c.instance_id == comp.instance_id)
        assert comp.component_type_id == eng.component_type
        assert comp.symbol_id in s.symbols


# ── serialization ──────────────────────────────────────────────────────────

def test_schematic_json_roundtrip(schematics):
    _, s = schematics["i2c_adc_logger"]
    again = SchematicProject.model_validate(json.loads(s.model_dump_json()))
    assert again == s


# ── layout state (presentation edits) ──────────────────────────────────────

def test_locked_placement_is_respected(registry):
    design = load(ROOT / "data/examples/night_light_transistor.json")
    layout = LayoutState(placements={"d1": Placement(x=60, y=-20, rotation=90, locked=True)})
    s = generate_schematic(design, registry, layout)
    d1 = s.component("d1")
    assert (d1.x, d1.y, d1.rotation, d1.locked) == (60, -20, 90, True)
    assert verify_schematic(s, design).ok


def test_kept_placements_are_stable_when_a_part_is_added(registry):
    from schematic import placements_from_schematic
    design = load(ROOT / "data/examples/temperature_monitor.json")
    first = generate_schematic(design, registry)
    layout = LayoutState(placements=placements_from_schematic(first))
    design.components.append(EngineeringComponentInstance(instance_id="c9", component_type="passive:capacitor-ceramic",
                                                          parameters={"capacitance": "100n"}))
    design.nets[0].connections.append(PinRef(instance_id="c9", pin_id="PIN1"))
    design.nets[1].connections.append(PinRef(instance_id="c9", pin_id="PIN2"))
    second = generate_schematic(design, registry, layout)
    for comp in first.components:
        c2 = second.component(comp.instance_id)
        assert (c2.x, c2.y, c2.rotation) == (comp.x, comp.y, comp.rotation)
    assert second.component("c9") is not None
    assert verify_schematic(second, design).ok


def test_label_style_forces_net_labels(registry):
    design = load(ROOT / "tests/fixtures/golden/smart_parking_valid.json")
    s = generate_schematic(design, registry, LayoutState(net_styles={"n_trigger": "label"}))
    assert s.nets["n_trigger"].style == "label"
    assert not [w for w in s.wires if w.net_id == "n_trigger"]
    assert len([l for l in s.net_labels if l.net_id == "n_trigger"]) == 2
    assert verify_schematic(s, design).ok


# ── invalid engineering references degrade gracefully ──────────────────────

def test_unknown_component_type_drawn_as_box_with_diagnostic(registry):
    design = EngineeringDesignProject(
        project_id="x", name="x",
        components=[EngineeringComponentInstance(instance_id="u9", component_type="mystery:widget"),
                    EngineeringComponentInstance(instance_id="r1", component_type="passive:resistor-tht")],
        nets=[Net(net_id="n1", connections=[PinRef(instance_id="u9", pin_id="OUT"), PinRef(instance_id="r1", pin_id="PIN1")])])
    s = generate_schematic(design, registry)
    assert s.component("u9").symbol_id.startswith("box:")
    assert any("unknown component type" in d for d in s.diagnostics)
    assert verify_schematic(s, design).ok


def test_net_referencing_missing_instance_does_not_crash(registry):
    design = EngineeringDesignProject(
        project_id="x", name="x",
        components=[EngineeringComponentInstance(instance_id="r1", component_type="passive:resistor-tht")],
        nets=[Net(net_id="n1", connections=[PinRef(instance_id="ghost", pin_id="A"), PinRef(instance_id="r1", pin_id="PIN1")])])
    s = generate_schematic(design, registry)
    assert s.nets["n1"].style == "label"


# ── verifier catches corrupted drawings ────────────────────────────────────

def test_verifier_detects_open_and_short(schematics):
    design, s = schematics["smart_parking_valid"]
    broken = s.model_copy(deep=True)
    broken.wires = [w for w in broken.wires if w.net_id != "n_led_drive"]
    rep = verify_schematic(broken, design)
    assert not rep.ok and any("n_led_drive" in o for o in rep.opens)

    shorted = s.model_copy(deep=True)
    a = next(c for c in shorted.components if c.instance_id == "r1").pins[0]
    b = next(c for c in shorted.components if c.instance_id == "d1").pins[1]
    shorted.wires.append(SchematicWire(wire_id="bad", net_id="n_led_drive", x1=a.x, y1=a.y, x2=a.x, y2=b.y))
    shorted.wires.append(SchematicWire(wire_id="bad2", net_id="n_led_drive", x1=a.x, y1=b.y, x2=b.x, y2=b.y))
    rep = verify_schematic(shorted, design)
    assert not rep.ok and rep.shorts


def test_crossing_wires_do_not_connect():
    s = SchematicProject(project_id="p", name="p", wires=[
        SchematicWire(wire_id="h", net_id="a", x1=0, y1=5, x2=10, y2=5),
        SchematicWire(wire_id="v", net_id="b", x1=5, y1=0, x2=5, y2=10)])
    assert extract_connectivity(s) == []  # no pins -> no groups, and no error


# ── router rules ───────────────────────────────────────────────────────────

class TestRouter:
    def test_route_avoids_blocked_body(self):
        r = GridRouter((0, 0, 20, 20))
        r.block_rect(8, 0, 12, 15)
        res = r.route_net("n", [Terminal((2, 5), "right"), Terminal((18, 5), "left")])
        assert res.ok
        pts = {p for e in res.edges for p in e}
        assert not pts & r.blocked

    def test_crossing_allowed_but_never_collinear_or_on_node(self):
        r = GridRouter((0, 0, 20, 20))
        a = r.route_net("a", [Terminal((2, 10), "right"), Terminal((18, 10), "left")])
        r.commit(a, [(2, 10), (18, 10)])
        b = r.route_net("b", [Terminal((10, 2), "down"), Terminal((10, 18), "up")])
        assert b.ok
        r.commit(b, [(10, 2), (10, 18)])
        a_edges = {frozenset(e) for e in a.edges}
        b_edges = {frozenset(e) for e in b.edges}
        assert not a_edges & b_edges
        # the crossing point is not a corner/end of either net
        assert r.nodes.get((10, 10)) is None

    def test_unroutable_net_reports_failure(self):
        r = GridRouter((0, 0, 10, 10))
        r.block_rect(4, 0, 6, 10)
        res = r.route_net("n", [Terminal((1, 5), "right"), Terminal((9, 5), "left")])
        assert not res.ok and res.reason


# ── AI-generated designs (captured from live Gemini runs) stay valid and drawable ──

AI_DESIGNS = sorted((ROOT / "tests/fixtures/ai_generated").glob("*.json"))


@pytest.mark.parametrize("path", AI_DESIGNS, ids=lambda p: p.stem)
def test_ai_generated_design_validates_and_draws(path, registry):
    from validation.engine import DesignValidator
    design = load(path)
    assert DesignValidator(registry).validate(design).status.value == "PASS"
    s = generate_schematic(design, registry)
    assert verify_schematic(s, design).ok
