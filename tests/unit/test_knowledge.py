"""Knowledge ecosystem tests: design patterns, calculators and curriculum-graph integrity."""
import pytest

from components.registry import get_default_registry
from core.models import EngineeringComponentInstance as C, EngineeringDesignProject, Net, PinRef
from curriculum.store import get_default_curriculum
from knowledge import apply_fragment, get_default_patterns, instantiate_pattern
from schematic import generate_schematic, verify_schematic
from validation.calculations import CALCULATORS, run_calculation
from validation.engine import DesignValidator

REG = get_default_registry()
PATTERNS = get_default_patterns()
CURR = get_default_curriculum()


def harness() -> EngineeringDesignProject:
    """A 5 V USB supply, a 9 V battery sharing ground, and nothing else."""
    return EngineeringDesignProject(project_id="h", name="harness", components=[
        C(instance_id="usb", component_type="power:usb-5v"), C(instance_id="bat", component_type="power:battery-9v"),
        C(instance_id="rload", component_type="passive:resistor-tht", parameters={"resistance": "10k"})],
        nets=[Net(net_id="gnd", connections=[PinRef(instance_id="usb", pin_id="GND"), PinRef(instance_id="bat", pin_id="NEG"),
                                             PinRef(instance_id="rload", pin_id="PIN2")]),
              Net(net_id="v5", connections=[PinRef(instance_id="usb", pin_id="VBUS"), PinRef(instance_id="rload", pin_id="PIN1")])])


def bind_ports(design: EngineeringDesignProject, pattern) -> dict:
    """Bind supply ports to the 5 V / 9 V sources, ground to ground, signals to fresh headers."""
    bindings = {}
    for port in pattern.ports:
        if port.kind == "ground":
            bindings[port.name] = "usb.GND"
        elif port.kind == "supply":
            bindings[port.name] = "bat.POS" if port.name in ("VMOTOR", "VIN") else "usb.VBUS"
        else:
            hid = f"j_{port.name.lower()}"
            design.components.append(C(instance_id=hid, component_type="connector:header-1x2"))
            design.nets.append(Net(net_id=f"{hid}_gnd", connections=[PinRef(instance_id=hid, pin_id="P2"),
                                                                     PinRef(instance_id="usb", pin_id="GND")]))
            bindings[port.name] = f"{hid}.P1"
    return bindings


def merge_ground_nets(design: EngineeringDesignProject) -> EngineeringDesignProject:
    """Header ground nets and the harness ground are the same node; merge them."""
    gnd = next(n for n in design.nets if n.net_id == "gnd")
    for n in [n for n in design.nets if n.net_id.endswith("_gnd") and n is not gnd]:
        for pr in n.connections:
            if all(x.ref != pr.ref for x in gnd.connections):
                gnd.connections.append(pr)
        design.nets.remove(n)
    # nets that now contain a ground pin already present on gnd are merged by apply_fragment
    return design


class TestPatterns:
    def test_patterns_load(self):
        assert PATTERNS.count >= 15

    @pytest.mark.parametrize("pid", sorted(p.pattern_id for p in get_default_patterns().list_all()))
    def test_pattern_references_are_real(self, pid):
        p = PATTERNS.get(pid)
        roles = {part.role: part for part in p.parts}
        for part in p.parts:
            for ctype_id in [part.component_type, *part.alternatives]:
                ct = REG.get(ctype_id)
                assert ct is not None, f"{pid}: unknown component {ctype_id}"
        ports = {port.name for port in p.ports}
        for net in p.nets:
            for m in net.members:
                if m.startswith("port:"):
                    assert m[5:] in ports
                else:
                    role, pin = m.split(".", 1)
                    for ctype_id in [roles[role].component_type, *roles[role].alternatives]:
                        assert pin in {x.pin_id for x in REG.get(ctype_id).pins}, f"{pid}: {ctype_id} has no pin {pin}"
        for concept in p.concepts:
            assert CURR.get(concept) is not None, f"{pid}: unknown concept {concept}"
        for calc in p.calculations:
            assert calc in CALCULATORS

    @pytest.mark.parametrize("pid", sorted(p.pattern_id for p in get_default_patterns().list_all()))
    def test_every_pattern_instantiates_into_a_valid_drawable_design(self, pid):
        p = PATTERNS.get(pid)
        design = harness()
        bindings = bind_ports(design, p)
        design = merge_ground_nets(design)
        frag = instantiate_pattern(p, "x", bindings, taken_ids={c.instance_id for c in design.components})
        merged = apply_fragment(design, frag)
        result = DesignValidator(REG).validate(merged)
        assert result.status.value == "PASS", [e.message for e in result.errors]
        schematic = generate_schematic(merged, REG)
        assert verify_schematic(schematic, merged).ok

    def test_alternative_choice_and_parameter_override(self):
        p = PATTERNS.get("bjt_low_side_switch")
        frag = instantiate_pattern(p, "sw", choices={"q": "active:transistor-npn-2n2222"}, parameters={"rb": {"resistance": "2.2k"}})
        types = {c.instance_id: c.component_type for c in frag.components}
        assert types["sw_q"] == "active:transistor-npn-2n2222"
        assert next(c for c in frag.components if c.instance_id == "sw_rb").parameters["resistance"] == "2.2k"
        with pytest.raises(ValueError):
            instantiate_pattern(p, "sw", choices={"q": "passive:led-5mm"})
        with pytest.raises(ValueError):
            instantiate_pattern(p, "sw", bindings={"NOPE": "a.b"})

    def test_apply_fragment_merges_into_existing_nets(self):
        design = EngineeringDesignProject(project_id="d", name="d", components=[
            C(instance_id="u1", component_type="board:esp32-devkit-v1"), C(instance_id="r9", component_type="passive:resistor-tht")],
            nets=[Net(net_id="sig", connections=[PinRef(instance_id="u1", pin_id="GPIO5"), PinRef(instance_id="r9", pin_id="PIN1")])])
        frag = instantiate_pattern(PATTERNS.get("led_indicator"), "st", {"DRIVE": "u1.GPIO5", "GND": "u1.GND1"})
        merged = apply_fragment(design, frag)
        sig = next(n for n in merged.nets if n.net_id == "sig")
        assert {pr.ref for pr in sig.connections} == {"u1.GPIO5", "r9.PIN1", "st_r.PIN1"}
        assert len({c.instance_id for c in merged.components}) == len(merged.components)

    def test_search(self):
        assert PATTERNS.search("flyback")[0].pattern_id == "flyback_protection"
        assert PATTERNS.search("i2c")[0].pattern_id == "i2c_bus_pullups"


class TestCalculators:
    def test_voltage_divider_matches_smart_parking_design(self):
        out = run_calculation("voltage_divider", {"v_in": 5, "r_top": "1k", "r_bottom": "2k"}).outputs
        assert out["v_out"] == pytest.approx(3.3333, abs=1e-3)

    def test_base_resistor_prefers_lower_standard_value(self):
        out = run_calculation("bjt_base_resistor", {"v_drive": 3.3, "load_current_ma": 71, "hfe_min": 100}).outputs
        assert out["rb_standard_ohms"] <= out["rb_ohms"]

    def test_555_frequency(self):
        out = run_calculation("astable_555", {"r1": "1k", "r2": "100k", "c": "10u"}).outputs
        assert out["frequency_hz"] == pytest.approx(0.7164, rel=1e-3)

    def test_rc_and_gain(self):
        assert run_calculation("rc_time_constant", {"r": "10k", "c": "100n"}).outputs["tau_s"] == pytest.approx(1e-3)
        assert run_calculation("noninverting_gain", {"rf": "10k", "rg": "10k"}).outputs["gain"] == 2

    @pytest.mark.parametrize("calc,params", [("unknown", {}), ("rc_time_constant", {"r": "abc", "c": 1}),
                                             ("rc_time_constant", {"r": 1}), ("voltage_divider", {"v_in": 5, "r_top": 0, "r_bottom": 1})])
    def test_invalid_inputs_raise(self, calc, params):
        with pytest.raises(ValueError):
            run_calculation(calc, params)


class TestCurriculumGraph:
    def test_backbone_modules_present(self):
        core = [m for m in CURR.modules() if m.layer == "core"]
        assert sorted(m.number for m in core) == list(range(1, 15))

    def test_concept_references_resolve(self):
        pattern_ids = {p.pattern_id for p in PATTERNS.list_all()}
        for c in CURR.list_all():
            for comp in c.components:
                assert REG.has(comp), f"{c.concept_id}: unknown component {comp}"
            for p in c.patterns:
                assert p in pattern_ids, f"{c.concept_id}: unknown pattern {p}"
            for pre in c.prerequisites + c.related_concepts:
                assert CURR.get(pre) is not None, f"{c.concept_id}: unknown concept {pre}"

    def test_non_physical_concepts_are_not_parts(self):
        """RTL/verification/process knowledge must not masquerade as registry components."""
        for c in CURR.list_all():
            if c.abstraction_level in ("rtl", "verification", "implementation", "manufacturing", "package", "methodology"):
                for comp in c.components:
                    assert REG.get(comp).object_type.value != "PHYSICAL" or c.abstraction_level == "rtl", c.concept_id

    def test_registry_curriculum_mappings_resolve(self):
        for ct in REG.list_all():
            for concept in ct.curriculum_mapping:
                assert CURR.get(concept) is not None, f"{ct.component_type_id}: unknown concept {concept}"
