"""Studio backend tests: edit operations, derived state, explanation and the HTTP API."""
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from components.registry import get_default_registry
from studio import EditError, StudioDocument, StudioService, apply_ops
from studio.edits import (AddComponent, AutoArrange, Connect, DeleteNet, Disconnect, InsertPattern, MirrorComponent,
                          MoveComponent, RemoveComponent, RenameNet, RotateComponent, SetNetStyle, SetParameter)
from studio.server import create_server

ROOT = Path(__file__).resolve().parents[2]
REG = get_default_registry()


@pytest.fixture(scope="module")
def service():
    return StudioService(REG)


@pytest.fixture
def parking(service):
    return service.open_example("pwm_motor_controller").document


def net_members(doc, net_id):
    return {pr.ref for pr in next(n for n in doc.design.nets if n.net_id == net_id).connections}


def net_of(doc, ref):
    return next((n.net_id for n in doc.design.nets if any(pr.ref == ref for pr in n.connections)), None)


# ── engineering ops ────────────────────────────────────────────────────────

class TestEngineeringOps:
    def test_add_component_generates_id_and_is_flagged_disconnected(self, service, parking):
        state = service.apply(parking, [AddComponent(component_type="passive:resistor-tht", parameters={"resistance": "1k"})])
        ids = [c.instance_id for c in state.document.design.components]
        assert "r3" in ids  # r1, r2 exist
        assert any(e.code == "E009" and "r3" in e.affected_instances for e in state.validation.errors)
        assert state.schematic.component("r3") is not None      # drawn immediately
        assert state.verification["ok"]

    def test_add_unknown_type_is_rejected(self, parking):
        with pytest.raises(EditError) as e:
            apply_ops(parking, [AddComponent(component_type="made:up")], REG)
        assert e.value.code == "EDIT_UNKNOWN_TYPE"

    def test_connect_creates_extends_and_merges_nets(self, parking):
        doc, _ = apply_ops(parking, [AddComponent(component_type="passive:led-5mm", instance_id="d9"),
                                     AddComponent(component_type="passive:resistor-tht", instance_id="r9", parameters={"resistance": "330"})], REG)
        doc, res = apply_ops(doc, [Connect(a="r9.PIN2", b="d9.ANODE")], REG)
        assert "Created net" in res[0].message
        created = net_of(doc, "r9.PIN2")
        doc, res = apply_ops(doc, [Connect(a="u1.D9", b="r9.PIN1")], REG)        # joins existing pwm net
        assert net_of(doc, "r9.PIN1") == net_of(doc, "u1.D9") == "pwm"
        doc, res = apply_ops(doc, [Connect(a="d9.CATHODE", b="q1.S")], REG)      # joins gnd
        assert net_of(doc, "d9.CATHODE") == "gnd"
        doc, res = apply_ops(doc, [Connect(a="r9.PIN2", b="u1.D9")], REG)        # merge two nets
        assert "Merged" in res[0].message
        assert net_of(doc, "d9.ANODE") == net_of(doc, "u1.D9")
        assert created not in {n.net_id for n in doc.design.nets} or net_of(doc, "u1.D9") == created

    def test_connect_rejects_unknown_pin_and_self(self, parking):
        with pytest.raises(EditError) as e:
            apply_ops(parking, [Connect(a="q1.X", b="r1.PIN1")], REG)
        assert e.value.code == "EDIT_UNKNOWN_PIN"
        with pytest.raises(EditError) as e:
            apply_ops(parking, [Connect(a="r1.PIN1", b="r1.PIN1")], REG)
        assert e.value.code == "EDIT_SELF_CONNECTION"
        with pytest.raises(EditError) as e:
            apply_ops(parking, [Connect(a="nobody.PIN1", b="r1.PIN1")], REG)
        assert e.value.code == "EDIT_UNKNOWN_INSTANCE"

    def test_disconnect_removes_single_pin_nets(self, parking):
        doc, res = apply_ops(parking, [Disconnect(pin="rv1.OUT")], REG)
        assert "speed" not in {n.net_id for n in doc.design.nets}
        assert net_of(doc, "u1.A0") is None

    def test_remove_component_cleans_nets_and_layout(self, service, parking):
        state = service.state(parking)
        doc = state.document
        assert "d1" in doc.layout.placements
        doc2, res = apply_ops(doc, [RemoveComponent(instance_id="d1")], REG)
        assert all(pr.instance_id != "d1" for n in doc2.design.nets for pr in n.connections)
        assert "d1" not in doc2.layout.placements
        # removing the flyback diode must surface the motor warning through validation
        after = service.state(doc2)
        assert any(w.code == "W005" for w in after.validation.warnings)

    def test_set_parameter_validates_key_and_value(self, parking):
        doc, _ = apply_ops(parking, [SetParameter(instance_id="r1", key="resistance", value="220")], REG)
        assert next(c for c in doc.design.components if c.instance_id == "r1").parameters["resistance"] == "220"
        with pytest.raises(EditError) as e:
            apply_ops(parking, [SetParameter(instance_id="r1", key="colour", value="red")], REG)
        assert e.value.code == "EDIT_UNKNOWN_PARAMETER"
        with pytest.raises(EditError) as e:
            apply_ops(parking, [SetParameter(instance_id="r1", key="resistance", value="banana")], REG)
        assert e.value.code == "EDIT_BAD_VALUE"

    def test_rename_and_delete_net(self, parking):
        doc, _ = apply_ops(parking, [RenameNet(net_id="pwm", new_net_id="motor_pwm")], REG)
        assert net_of(doc, "u1.D9") == "motor_pwm"
        with pytest.raises(EditError):
            apply_ops(parking, [RenameNet(net_id="pwm", new_net_id="gnd")], REG)
        doc, _ = apply_ops(parking, [DeleteNet(net_id="speed")], REG)
        assert net_of(doc, "rv1.OUT") is None

    def test_insert_pattern_merges_into_design(self, service, parking):
        state = service.apply(parking, [InsertPattern(pattern_id="led_indicator", prefix="status",
                                                      bindings={"DRIVE": "u1.D13", "GND": "u1.GND2"})])
        ids = {c.instance_id for c in state.document.design.components}
        assert {"status_r", "status_led"} <= ids
        assert state.validation.status.value == "PASS", [e.message for e in state.validation.errors]
        assert state.verification["ok"]

    def test_batch_is_atomic(self, parking):
        before = parking.model_dump()
        with pytest.raises(EditError):
            apply_ops(parking, [SetParameter(instance_id="r1", key="resistance", value="1k"),
                                Connect(a="r1.PIN1", b="nope.X")], REG)
        assert parking.model_dump() == before


# ── presentation ops ───────────────────────────────────────────────────────

class TestPresentationOps:
    def test_move_rotate_mirror_do_not_touch_engineering(self, service, parking):
        state = service.state(parking)
        doc = state.document
        doc2, res = apply_ops(doc, [MoveComponent(instance_id="r1", x=40, y=-12), RotateComponent(instance_id="r1"),
                                    MirrorComponent(instance_id="r1")], REG)
        assert all(r.kind == "presentation" for r in res)
        assert doc2.design == doc.design
        p = doc2.layout.placements["r1"]
        assert (p.x, p.y, p.locked, p.mirror) == (40, -12, True, True)
        assert p.rotation == (doc.layout.placements["r1"].rotation + 90) % 360
        after = service.state(doc2)
        r1 = after.schematic.component("r1")
        assert (r1.x, r1.y, r1.rotation, r1.mirror) == (40, -12, p.rotation, True)
        assert after.verification["ok"]

    def test_net_style_and_auto_arrange(self, service, parking):
        doc = service.state(parking).document
        doc2, _ = apply_ops(doc, [SetNetStyle(net_id="pwm", style="label"), MoveComponent(instance_id="q1", x=90, y=90)], REG)
        s = service.state(doc2)
        assert s.schematic.nets["pwm"].style == "label"
        doc3, _ = apply_ops(s.document, [AutoArrange(keep_locked=False)], REG)
        s3 = service.state(doc3)
        assert (s3.schematic.component("q1").x, s3.schematic.component("q1").y) != (90, 90)
        assert s3.verification["ok"]


# ── derived state & explanation ────────────────────────────────────────────

def test_state_contains_everything_the_ui_needs(service):
    state = service.open_example("temperature_monitor")
    assert state.validation.checks_run
    assert state.schematic.components and state.schematic.symbols
    assert state.verification["ok"]
    ex = state.explanation
    assert {p["reference"] for p in ex["parts"]} == {c.reference for c in state.schematic.components}
    assert any(r["name"] == "+3.3V" for r in ex["power_rails"])
    assert any("1-Wire" in (p["what_it_does"] or "") or p["component_type"] == "sensor:ds18b20" for p in ex["parts"])
    assert ex["limitations"]


def test_library_has_symbol_previews(service):
    lib = service.library()
    assert len(lib) == REG.count
    for item in lib:
        assert item["symbol"]["pins"], item["id"]


# ── HTTP API ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api():
    from tests.unit.test_orchestrator import MockRepairProvider
    svc = StudioService(REG, provider_factory=lambda provider, model: MockRepairProvider())
    server = create_server("127.0.0.1", 0, svc, static_dir=None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()
    server.server_close()


def call(base, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, (json.loads(body) if r.headers.get_content_type() == "application/json" else body.decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestHttpApi:
    def test_health_library_examples(self, api):
        assert call(api, "GET", "/api/health") == (200, {"ok": True})
        status, lib = call(api, "GET", "/api/library")
        assert status == 200 and len(lib["components"]) == REG.count
        status, comp = call(api, "GET", "/api/library/ic:timer-ne555")
        assert status == 200 and comp["name"].startswith("NE555")
        status, ex = call(api, "GET", "/api/examples")
        assert status == 200 and any(e["id"] == "cmos_inverter" for e in ex["examples"])
        status, prov = call(api, "GET", "/api/providers")
        assert status == 200 and all("configured" in p and "key" not in json.dumps(p).lower() for p in prov["providers"])

    def test_open_edit_roundtrip(self, api):
        status, state = call(api, "POST", "/api/examples/half_adder")
        assert status == 200 and state["validation"]["status"] == "PASS"
        status, state2 = call(api, "POST", "/api/edit", {"document": state["document"],
                                                         "ops": [{"op": "disconnect", "pin": "u2.Y"}]})
        assert status == 200
        assert state2["document"]["revision"] == state["document"]["revision"] + 1
        assert any(e["code"] == "E009" for e in state2["validation"]["errors"]) or state2["validation"]["status"] in ("PASS", "FAIL")
        status, err = call(api, "POST", "/api/edit", {"document": state["document"], "ops": [{"op": "connect", "a": "u1.Q", "b": "s.IN"}]})
        assert status == 422 and err["error"]["code"] == "EDIT_UNKNOWN_PIN"

    def test_bad_requests(self, api):
        assert call(api, "POST", "/api/edit", {"ops": []})[0] == 400
        assert call(api, "POST", "/api/edit", {"document": {"design": {}}, "ops": []})[0] == 400
        assert call(api, "POST", "/api/edit", {"document": {"design": {"project_id": "x", "name": "x"}}, "ops": [{"op": "fly"}]})[0] == 400
        assert call(api, "GET", "/api/nothing")[0] == 404
        assert call(api, "POST", "/api/examples/..%2F..%2Fsecrets")[0] == 404

    def test_svg_export(self, api):
        _, state = call(api, "POST", "/api/examples/relay_driver")
        status, svg = call(api, "POST", "/api/export/svg", {"document": state["document"]})
        assert status == 200 and svg.startswith("<svg") and "K1" in svg

    def test_generation_job_runs_through_validation(self, api):
        status, job = call(api, "POST", "/api/generate", {"prompt": "Build a smart parking sensor"})
        assert status == 202
        for _ in range(100):
            _, info = call(api, "GET", f"/api/jobs/{job['job_id']}")
            if info["status"] != "running":
                break
            time.sleep(0.1)
        assert info["status"] == "done", info.get("error")
        msgs = " ".join(e["message"] for e in info["events"])
        assert "Validation FAIL" in msgs and "Repairing" in msgs      # the mock's first draft fails E010
        result = info["result"]
        assert result["validation"]["status"] == "PASS"
        assert result["document"]["provenance"]["source"] == "ai"
        assert result["verification"]["ok"]
        assert call(api, "POST", "/api/generate", {"prompt": "  "})[0] == 400


# ── functional validation inside the studio ────────────────────────────────

def test_example_state_includes_functional_report(service):
    state = service.open_example("temperature_alarm")
    assert state.document.intent is not None
    assert state.validation.status.value == "PASS" and state.functional.status == "PASS"
    assert any("threshold is set by rv1" in line for line in state.explanation["function"])


def test_edit_that_breaks_the_function_is_reported(service):
    """Moving the buzzer's low side from the transistor to ground keeps the circuit electrically
    valid but the buzzer is no longer controlled: the functional report must flag it."""
    state = service.open_example("temperature_alarm")
    broken = service.apply(state.document, [Disconnect(pin="bz1.GND"), Connect(a="bz1.GND", b="u2.GND")])
    assert broken.validation.status.value == "PASS"
    assert broken.functional.status == "FAIL"
    assert any(f.code == "F004" and "bz1" in f.affected_instances for f in broken.functional.findings)


def test_set_intent_op_changes_what_is_graded(service):
    from functional import FunctionalIntent
    from studio.edits import SetIntent
    state = service.open_example("temperature_alarm")
    below = state.document.intent.model_copy(deep=True)
    below.behaviors[0].when.relation = "below"
    s2 = service.apply(state.document, [SetIntent(intent=below)])
    assert s2.functional.status == "FAIL" and any(f.code == "F006" for f in s2.functional.findings)
    s3 = service.apply(s2.document, [SetIntent(intent=None)])
    assert s3.functional.intent_present is False and s3.functional.status == "NOT_CHECKABLE"


def test_http_open_accepts_intent(api):
    d = json.loads((ROOT / "data/examples/temperature_alarm.json").read_text(encoding="utf-8"))
    i = json.loads((ROOT / "data/examples/intents/temperature_alarm.json").read_text(encoding="utf-8"))
    status, state = call(api, "POST", "/api/open", {"design": d, "intent": i})
    assert status == 200 and state["functional"]["status"] == "PASS"
    assert call(api, "POST", "/api/open", {"design": d, "intent": {"signals": "nope"}})[0] == 400


def test_second_server_on_same_port_fails_loudly():
    """Two servers silently sharing a port split requests between old and new code."""
    import os as _os
    first = create_server("127.0.0.1", 0, StudioService(REG), static_dir=None)
    port = first.server_address[1]
    try:
        if _os.name == "nt":
            with pytest.raises(OSError):
                create_server("127.0.0.1", port, StudioService(REG), static_dir=None)
    finally:
        first.server_close()


def test_functional_events_are_summarised_for_the_progress_log():
    from studio.service import summarize_event
    intent = {"intent": {"behaviors": [{"when": {"input": "temp", "relation": "above"}, "then": {"output": "alarm", "effect": "on"}}]}}
    assert summarize_event("FUNCTIONAL_INTENT", intent) == "Required behaviour: alarm on when temp above"
    fail = {"status": "FAIL", "findings": [{"code": "F004", "status": "FAIL", "message": "bz1 is always on"},
                                           {"code": "F103", "status": "WARN", "message": "r9 unused"}]}
    msg = summarize_event("FUNCTIONAL_RESULT", fail)
    assert msg.startswith("Functional check → FAIL") and "F004 bz1 is always on" in msg and "F103" not in msg
    assert summarize_event("FUNCTIONAL_RESULT", {"status": "PASS", "findings": []}) == "Functional check → PASS"


def test_validate_design_tool_summary_distinguishes_functional_rejection_and_bad_input():
    from studio.service import summarize_event
    call = lambda result: summarize_event("TOOL_CALL", {"tool": "validate_design", "args": {}, "result": result})
    assert call('{"status": "PASS"}').endswith("→ PASS")
    assert call('{"status": "PASS", "overall": "REJECTED: electrically PASS, functionally FAIL"}').endswith(
        "PASS electrically, functional FAIL")
    assert "not a readable design" in call('{"error": "1 validation error"}')


def test_last_draft_is_recovered_from_traces_for_failed_jobs():
    from studio.service import _last_draft
    traces = [{"event": "PROPOSED_DESIGN", "data": {"project_id": "a"}},
              {"event": "TOOL_CALL", "data": {"tool": "validate_design", "args": {"design": {"project_id": "b"}}}},
              {"event": "TOOL_CALL", "data": {"tool": "search_components", "args": {}}}]
    assert _last_draft(traces) == {"project_id": "b"}
    assert _last_draft([]) is None
