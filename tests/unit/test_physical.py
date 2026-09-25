"""Physical projection: breadboard model, footprints, placement, wiring, verification, studio ops."""
import json
import time
from pathlib import Path

import pytest
import yaml

from components.registry import get_default_registry
from core.enums import ObjectType
from core.models import EngineeringDesignProject
from physical import (BOARD_SPECS, PhysicalLayoutState, generate_physical, make_breadboard, physical_connectivity,
                      resolve_footprint, verify_physical)
from physical.breadboard import parse_hole
from physical.models import PhysicalProject
from studio import StudioService
from studio.edits import EditError, PhysicalAutoArrange, PhysicalMove, PhysicalRotate, RemoveComponent, SetBreadboard, Disconnect

ROOT = Path(__file__).resolve().parents[2]
REG = get_default_registry()
EXAMPLES = sorted((ROOT / "data" / "examples").glob("*.json"))
PRIMITIVE_ONLY = {"cmos_inverter", "half_adder"}


def design(name: str) -> EngineeringDesignProject:
    return EngineeringDesignProject.model_validate(json.loads((ROOT / "data/examples" / f"{name}.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def alarm() -> PhysicalProject:
    return generate_physical(design("temperature_alarm"), REG)


# ── breadboard model ───────────────────────────────────────────────────────

@pytest.mark.parametrize("kind,tie_points", [("half", 400), ("full", 830)])
def test_breadboard_tie_points_match_the_board_it_models(kind, tie_points):
    bb = make_breadboard(kind)
    assert len(bb.holes) == tie_points
    assert str(tie_points) in BOARD_SPECS[kind].name


def test_breadboard_connectivity_strips_trench_and_rails():
    bb = make_breadboard("half")
    assert {bb.node_of(f"{r}7") for r in "abcde"} == {"top:7"}
    assert {bb.node_of(f"{r}7") for r in "fghij"} == {"bot:7"}
    assert bb.node_of("e7") != bb.node_of("f7")                       # the trench separates the halves
    assert bb.node_of("a7") != bb.node_of("a8")                       # columns are separate strips
    assert {bb.node_of(h) for h in ("T+1", "T+29")} == {"rail:T+"}    # a rail is one node
    assert bb.hole_at(30, -9.5) is None                               # gap in the rail groups
    assert parse_hole("T-12") == ("T-", 12) and parse_hole("j30") == ("j", 30)
    e, f = bb.holes["e1"], bb.holes["f1"]
    assert round(f.y - e.y, 3) == 7.62                                # DIP row spacing across the trench


# ── footprints ────────────────────────────────────────────────────────────

def test_every_registry_part_resolves_to_a_physical_definition():
    for ct in REG.list_all():
        fp = resolve_footprint(ct)
        if ct.object_type != ObjectType.PHYSICAL:
            assert fp.mount == "virtual", ct.component_type_id
            continue
        assert fp.mount in ("breadboard", "offboard"), ct.component_type_id
        assert fp.source in ("datasheet", "standard", "typical", "assumed")
        if fp.fallback:
            assert fp.source == "assumed" and fp.notes          # a stand-in always says so
        if fp.mount == "breadboard":
            assert fp.sites(), ct.component_type_id


def test_physical_data_only_names_pins_that_exist():
    """Guards against YAML pitfalls (e.g. an unquoted NO pin read as boolean false)."""
    parts = yaml.safe_load((ROOT / "data/physical/parts.yaml").read_text(encoding="utf-8"))["parts"]
    for cid, entry in parts.items():
        ct = REG.get(cid)
        assert ct is not None, cid
        pins = {p.pin_id for p in ct.pins}
        named = set(entry.get("pin_order", [])) | set(entry.get("pin_numbers", {})) | set(entry.get("pin_alias", {}))
        named |= {t["pin"] for t in entry.get("terminals", [])}
        for key in ("header", "header2"):
            named |= set(entry.get(key, {}).get("pins", []))
        for g in entry.get("internal_links", []):
            named |= set(g)
        assert all(isinstance(p, str) for p in named), (cid, named)
        assert named <= pins, (cid, named - pins)


def test_dip_numbering_straddles_the_trench_counter_clockwise():
    fp = resolve_footprint(REG.get("ic:comparator-lm393"))
    sites = {p: (dx, dy) for p, dx, dy in fp.sites()}
    assert sites["OUT1"] == (0, 0) and sites["GND"] == (3, 0)          # pins 1-4 along the top row
    assert sites["IN2_P"] == (3, 3) and sites["VCC"] == (0, 3)         # pins 5-8 back along the bottom row


def test_to92_and_board_pinouts_come_from_data():
    assert resolve_footprint(REG.get("semiconductor:npn-bc547")).pins == ["C", "B", "E"]
    assert resolve_footprint(REG.get("sensor:ds18b20")).pins == ["GND", "DQ", "VCC"]
    pico = resolve_footprint(REG.get("board:raspberry-pi-pico"))
    assert pico.template == "dual_row" and pico.total_pins == 40 and pico.numbers["VBUS"] == 40 and pico.row_span == 7
    esp = resolve_footprint(REG.get("board:esp32-devkit-v1"))
    assert esp.mount == "offboard" and esp.pin_alias == {"GND3": "GND2"} and esp.variant_note


def test_unknown_geometry_is_a_labelled_fallback_not_a_guess():
    ct = REG.get("passive:resistor-tht").model_copy(update={"component_type_id": "test:mystery", "physical": None})
    fp = resolve_footprint(ct)
    assert fp.fallback and fp.mount == "offboard" and fp.source == "assumed" and "generic module" in fp.notes[0]


# ── projection of every reference design ───────────────────────────────────

@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_builds_and_the_build_matches_the_netlist(path):
    d = design(path.stem)
    proj = generate_physical(d, REG)
    v = proj.verification
    if path.stem in PRIMITIVE_ONLY:
        assert not proj.applicable and v.status == "NOT_APPLICABLE"
        return
    assert v.ok, [(f.code, f.message) for f in v.findings if f.severity == "ERROR"]
    assert v.status in ("PASS", "WARN")
    assert {p.instance_id for p in proj.parts} == {c.instance_id for c in d.components}
    assert proj.stats.elapsed_ms < 3000


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_build_invariants(path):
    """Independent of the verifier: one net per node, one thing per hole, pins inside the board."""
    d = design(path.stem)
    proj = generate_physical(d, REG)
    if not proj.applicable:
        return
    bb = make_breadboard(proj.board.kind)
    node_nets = {}
    for part in proj.parts:
        for pin in part.pins:
            if pin.hole and pin.net_id:
                node_nets.setdefault(bb.node_of(pin.hole), set()).add(pin.net_id)
    for w in proj.wires:
        for end in (w.a, w.b):
            if end.kind == "hole":
                node_nets.setdefault(bb.node_of(end.hole), set()).add(w.net_id)
    assert all(len(n) == 1 for n in node_nets.values()), {k: v for k, v in node_nets.items() if len(v) > 1}
    holes = [p.hole for part in proj.parts for p in part.pins if p.hole] + \
            [e.hole for w in proj.wires for e in (w.a, w.b) if e.kind == "hole"]
    assert len(holes) == len(set(holes))
    assert all(h in bb.holes for h in holes)


def test_ground_and_supply_take_the_rails(alarm):
    rails = {r.rail_id: r.net_id for r in alarm.board.rails}
    assert rails["T-"] == "gnd" and rails["T+"] == "v5"


def test_dip_straddles_the_trench_and_parts_share_strips(alarm):
    u2 = alarm.part("u2")
    assert u2.orientation == "dip" and u2.anchor and u2.anchor[0] in ("e", "f")
    halves = {p.node.split(":")[0] for p in u2.pins}
    assert halves == {"top", "bot"}
    # at least one engineering connection is made by a shared strip (no wire)
    shared = [n for n, t in alarm.nets.items() if len({p.split(".")[0] for p in t.pins}) > 1 and not t.wires]
    nodes_by_net = {n: len(t.nodes) for n, t in alarm.nets.items()}
    assert shared or any(v == 1 for v in nodes_by_net.values())


def test_projection_is_deterministic_and_serialisable():
    d = design("temperature_alarm")
    a = generate_physical(d, REG).model_dump(mode="json")
    b = generate_physical(d, REG).model_dump(mode="json")
    a["stats"].pop("elapsed_ms"), b["stats"].pop("elapsed_ms")
    assert a == b
    again = PhysicalProject.model_validate(json.loads(json.dumps(a)))
    assert again.model_dump(mode="json")["parts"] == a["parts"]


def test_traceability_every_physical_object_names_its_engineering_origin(alarm):
    d = design("temperature_alarm")
    nets = {n.net_id for n in d.nets}
    comps = {c.instance_id: REG.get(c.component_type) for c in d.components}
    for part in alarm.parts:
        assert part.instance_id in comps
        assert {p.pin_id for p in part.pins} <= {p.pin_id for p in comps[part.instance_id].pins}
    for w in alarm.wires:
        assert w.net_id in nets
        for end in (w.a, w.b):
            if end.kind == "pin":
                iid, pin = end.pin_ref.split(".")
                assert pin in {p.pin_id for p in comps[iid].pins}


def test_resistor_colour_bands_follow_the_value(alarm):
    assert alarm.part("r1").visual.params["bands"] == "brown,black,orange,gold"     # 10k
    assert alarm.part("r2").visual.params["bands"] == "brown,black,red,gold"        # 1k


def test_offboard_items_have_leads_into_the_board(alarm):
    leads = [w for w in alarm.wires if w.kind == "lead"]
    assert {w.a.pin_ref for w in leads} == {"bt1.VBUS", "bt1.GND"}
    assert all(w.b.hole and w.b.hole[:2] in ("T+", "T-", "B+", "B-") for w in leads)


def test_assembly_steps_cover_every_part_and_wire(alarm):
    text = " ".join(s.text for s in alarm.assembly)
    for part in alarm.parts:
        assert part.reference in text
    assert sum(1 for s in alarm.assembly if s.kind in ("wire", "lead")) == len(alarm.wires)


def test_board_size_can_be_forced():
    d = design("temperature_alarm")
    assert generate_physical(d, REG, PhysicalLayoutState(board="full")).board.kind == "full"


# ── physical verification catches real faults ─────────────────────────────

def _codes(proj):
    return {f.code for f in verify_physical(proj, design("temperature_alarm")).findings if f.severity == "ERROR"}


def test_verification_detects_a_short(alarm):
    bad = alarm.model_copy(deep=True)
    w = next(w for w in bad.wires if w.kind == "jumper" and w.net_id == "temp")
    other = next(p for p in bad.part("u2").pins if p.net_id == "ref")
    col = int(other.hole[1:])
    w.b.hole = f"a{col}" if other.hole[0] in "abcde" else f"j{col}"
    assert "P005" in _codes(bad)


def test_verification_detects_an_open(alarm):
    bad = alarm.model_copy(deep=True)
    bad.wires = [w for w in bad.wires if w.net_id != "temp"]
    assert "P006" in _codes(bad)


def test_verification_detects_hole_conflicts_bad_holes_and_collisions(alarm):
    bad = alarm.model_copy(deep=True)
    r1 = bad.part("r1")
    r1.pins[1].hole = bad.part("u2").pins[0].hole
    assert "P004" in _codes(bad)
    bad2 = alarm.model_copy(deep=True)
    bad2.part("r2").pins[0].hole = "z99"
    assert "P003" in _codes(bad2)
    bad3 = alarm.model_copy(deep=True)
    bad3.part("q1").body = bad3.part("u2").body.model_copy()
    assert "P007" in _codes(bad3)


def test_verification_connectivity_is_rebuilt_from_the_ir_alone(alarm):
    dsu, bad, uses = physical_connectivity(alarm)
    assert not bad and max(uses.values()) == 1
    assert dsu.find("u1.VOUT") == dsu.find("u2.IN1_P")
    assert dsu.find("u1.VOUT") != dsu.find("u2.IN1_N")


def test_unknown_or_virtual_parts_are_reported_honestly():
    proj = generate_physical(design("relay_driver"), REG)
    codes = {f.code for f in proj.verification.findings}
    assert {"P101", "P102"} <= codes                     # stand-in relay / supply, vendor pinouts
    assert proj.verification.ok
    half = generate_physical(design("half_adder"), REG)
    assert half.verification.status == "NOT_APPLICABLE" and any(f.code == "P105" for f in half.verification.findings)


# ── studio: document state and physical ops ────────────────────────────────

@pytest.fixture
def svc():
    return StudioService(REG)


def test_physical_is_only_computed_when_requested(svc):
    assert svc.open_example("temperature_alarm").physical is None
    st = svc.open_example("temperature_alarm", physical=True)
    assert st.physical is not None and st.physical.verification.ok
    assert st.document.physical.placements["u2"].anchor == st.physical.part("u2").anchor


def test_move_is_accepted_or_refused_by_the_placement_engine(svc):
    st = svc.open_example("temperature_alarm", physical=True)
    moved = svc.apply(st.document, [PhysicalMove(instance_id="q1", anchor="a20")], physical=True)
    assert moved.physical.part("q1").anchor == "a20" and moved.physical.verification.ok
    assert moved.document.design == st.document.design                 # no engineering change
    u2_first = st.physical.part("u2").pins[0].hole
    with pytest.raises(EditError) as e:
        svc.apply(st.document, [PhysicalMove(instance_id="q1", anchor=u2_first)], physical=True)
    assert e.value.code == "EDIT_PHYSICAL_BLOCKED" and "already used" in e.value.message
    with pytest.raises(EditError) as e:
        svc.apply(st.document, [PhysicalMove(instance_id="q1", anchor="a10")], physical=True)
    assert "short" in e.value.message
    with pytest.raises(EditError):
        svc.apply(st.document, [PhysicalMove(instance_id="q1", anchor="zz1")], physical=True)


def test_rotate_auto_arrange_board_and_offboard_moves(svc):
    st = svc.open_example("temperature_alarm", physical=True)
    r = svc.apply(st.document, [PhysicalRotate(instance_id="r2")], physical=True)
    assert r.physical.part("r2").rotation != st.physical.part("r2").rotation and r.physical.verification.ok
    full = svc.apply(r.document, [SetBreadboard(board="full")], physical=True)
    assert full.physical.board.kind == "full" and full.physical.verification.ok
    back = svc.apply(full.document, [PhysicalAutoArrange(keep_locked=False), SetBreadboard(board="auto")], physical=True)
    assert back.physical.board.kind == "half"
    off = svc.apply(st.document, [PhysicalMove(instance_id="bt1", x=-90, y=-30)], physical=True)
    assert off.physical.part("bt1").position[:2] == [-90.0, -30.0] and off.physical.verification.ok
    with pytest.raises(EditError):
        svc.apply(st.document, [PhysicalMove(instance_id="bt1", x=0, y=0)], physical=True)   # on top of the board


def test_engineering_edits_reproject_the_build(svc):
    st = svc.open_example("temperature_alarm", physical=True)
    gone = svc.apply(st.document, [RemoveComponent(instance_id="r2")], physical=True)
    assert gone.physical.part("r2") is None and "r2" not in gone.document.physical.placements
    assert gone.physical.verification.ok
    dis = svc.apply(st.document, [Disconnect(pin="bz1.GND")], physical=True)
    assert dis.physical.verification.ok                                 # the build follows the netlist
    assert dis.physical.part("bz1").pins[1].net_id is None


def test_primitive_parts_cannot_be_moved_physically(svc):
    st = svc.open_example("half_adder", physical=True)
    iid = st.document.design.components[0].instance_id
    with pytest.raises(EditError) as e:
        svc.apply(st.document, [PhysicalMove(instance_id=iid, anchor="a1")], physical=True)
    assert e.value.code == "EDIT_NOT_PHYSICAL"


# ── end-to-end: natural language -> ... -> physical build ─────────────────

def _repair_provider():
    """Scripted provider (no network): intent-bearing requirements, a functionally broken first draft
    (buzzer not in the control path), then the repaired design."""
    from ai.models import ProjectRequirements
    from ai.provider import MockModelProvider
    from functional import FunctionalIntent

    def case(name):
        c = json.loads((ROOT / "tests/fixtures/functional" / f"{name}.json").read_text(encoding="utf-8"))
        return EngineeringDesignProject.model_validate(c["design"]), FunctionalIntent.model_validate(c["intent"])

    broken, intent = case("temp_alarm_buzzer_not_in_path")
    fixed, _ = case("temp_alarm_ok")

    class Provider(MockModelProvider):
        def structured_generate(self, messages, schema, context=None):
            if schema.__name__ == "ProjectRequirements":
                return ProjectRequirements(intent="adjustable temperature alarm", functional_intent=intent)
            repair = any("FUNCTIONAL validation FAILED" in (m.get("content") or "") for m in messages)
            return fixed if repair else broken
    return Provider()


def test_natural_language_to_verified_physical_build():
    svc = StudioService(REG, provider_factory=lambda provider, model: _repair_provider())
    job = svc.start_generation("Build an adjustable temperature alarm. The buzzer must turn ON above the threshold.")
    t = time.time()
    while job.status == "running" and time.time() - t < 60:
        time.sleep(0.05)
    assert job.status == "done", job.error
    st = job.result
    assert st.validation.status.value == "PASS"                        # electrical
    assert st.functional.status == "PASS"                              # functional (after one repair)
    assert st.verification["ok"]                                       # schematic LVS
    assert st.physical is not None and st.physical.applicable           # physical projection
    assert st.physical.verification.ok                                 # physical verification
    assert {p.instance_id for p in st.physical.parts} == {c.instance_id for c in st.document.design.components}


# ── HTTP API and CLI ───────────────────────────────────────────────────────

def test_http_api_includes_the_build_only_on_request():
    import threading
    import urllib.request
    from studio.server import create_server
    server = create_server("127.0.0.1", 0, StudioService(REG), static_dir=None)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(path, payload):
        req = urllib.request.Request(base + path, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        s, plain = post("/api/examples/temperature_alarm", {})
        assert s == 200 and plain["physical"] is None
        s, st = post("/api/examples/temperature_alarm", {"physical": True})
        assert s == 200 and st["physical"]["verification"]["ok"] is True
        s, moved = post("/api/edit", {"document": st["document"], "physical": True,
                                      "ops": [{"op": "physical_move", "instance_id": "q1", "anchor": "a20"}]})
        assert s == 200 and next(p for p in moved["physical"]["parts"] if p["instance_id"] == "q1")["anchor"] == "a20"
        s, err = post("/api/edit", {"document": st["document"], "physical": True,
                                    "ops": [{"op": "physical_move", "instance_id": "q1", "anchor": "a10"}]})
        assert s == 422 and err["error"]["code"] == "EDIT_PHYSICAL_BLOCKED"
        s, again = post("/api/state", {"document": moved["document"], "physical": True})
        assert s == 200 and next(p for p in again["physical"]["parts"] if p["instance_id"] == "q1")["anchor"] == "a20"
    finally:
        server.shutdown()
        server.server_close()


def test_cli_physical_commands():
    from typer.testing import CliRunner
    from cli.main import app
    runner = CliRunner()
    path = str(ROOT / "data/examples/temperature_alarm.json")
    r = runner.invoke(app, ["physical", "build", path])
    assert r.exit_code == 0 and "Half-size breadboard" in r.output and "physical check" in r.output
    r = runner.invoke(app, ["physical", "verify", path])
    assert r.exit_code == 0 and r.output.startswith(("PASS", "WARN"))
    r = runner.invoke(app, ["physical", "steps", path])
    assert r.exit_code == 0 and "across the centre gap" in r.output
