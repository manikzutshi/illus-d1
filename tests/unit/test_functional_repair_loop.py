"""The AI repair loop receives deterministic functional feedback (mock provider, no network)."""
import json
from pathlib import Path

from ai.models import ProjectRequirements
from ai.orchestrator import AgentState, Orchestrator
from ai.provider import MockModelProvider
from core.models import EngineeringDesignProject
from functional import FunctionalIntent

ROOT = Path(__file__).resolve().parents[2]


def case(name):
    c = json.loads((ROOT / "tests/fixtures/functional" / f"{name}.json").read_text(encoding="utf-8"))
    return EngineeringDesignProject.model_validate(c["design"]), FunctionalIntent.model_validate(c["intent"])


BROKEN, INTENT = case("temp_alarm_buzzer_not_in_path")
FIXED, _ = case("temp_alarm_ok")


class FunctionalRepairProvider(MockModelProvider):
    """Returns intent-bearing requirements, a functionally broken first draft, then the fixed design."""

    def __init__(self, repaired=FIXED):
        super().__init__()
        self.repair_messages = []
        self.repaired = repaired

    def structured_generate(self, messages, schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            return ProjectRequirements(intent="adjustable temperature alarm", functional_intent=INTENT)
        repair = [m["content"] for m in messages if "FUNCTIONAL validation FAILED" in (m.get("content") or "")]
        self.repair_messages = repair
        return self.repaired if repair else BROKEN


def test_broken_draft_is_electrically_valid_so_the_old_pipeline_would_accept_it():
    from ai.tools import validate_design
    assert validate_design(BROKEN).status.value == "PASS"


def test_repair_loop_uses_functional_feedback():
    provider = FunctionalRepairProvider()
    orch = Orchestrator(provider, max_repair_attempts=2)
    result = orch.run("Build an adjustable temperature alarm. The buzzer must turn ON above the threshold and OFF below it.")
    assert result is not None and result.project_id == FIXED.project_id
    assert orch.state == AgentState.COMPLETED
    assert orch.metrics["functional_fail_count"] == 1
    # The repair request contained structured, actionable functional feedback.
    assert provider.repair_messages
    msg = provider.repair_messages[-1]
    assert '"code": "F004"' in msg and "bz1" in msg and "repair_hint" in msg and "bjt_low_side_switch" in msg
    statuses = [t["data"]["status"] for t in orch.traces if t["event"] == "FUNCTIONAL_RESULT"]
    assert statuses == ["FAIL", "PASS"]
    assert any(t["event"] == "FUNCTIONAL_INTENT" for t in orch.traces)


def test_loop_gives_up_when_function_is_never_fixed():
    orch = Orchestrator(FunctionalRepairProvider(repaired=BROKEN), max_repair_attempts=1)
    assert orch.run("temperature alarm") is None
    assert orch.state == AgentState.FAILED


def test_validate_design_tool_reports_functional_failure_and_does_not_accept():
    orch = Orchestrator(MockModelProvider())
    orch.functional_intent = INTENT
    out = json.loads(orch._execute_tool("validate_design", {"design": BROKEN.model_dump(mode="json")}))
    assert out["status"] == "PASS"                              # electrically fine...
    assert out["functional"]["status"] == "FAIL"                 # ...but it does not do the job
    assert out["overall"].startswith("REJECTED")
    assert any(f["code"] == "F004" for f in out["functional"]["failures"])
    assert orch._validated_design is None
    ok = json.loads(orch._execute_tool("validate_design", {"design": FIXED.model_dump(mode="json")}))
    assert ok["functional"]["status"] == "PASS" and orch._validated_design is not None


def test_without_intent_behaviour_is_unchanged():
    """Requirements with no functional intent: validation gates exactly as before."""
    orch = Orchestrator(MockModelProvider())
    out = json.loads(orch._execute_tool("validate_design", {"design": BROKEN.model_dump(mode="json")}))
    assert "functional" not in out and orch._validated_design is not None


def test_requirements_schema_is_provider_safe():
    from ai.provider_gemini import RESTGeminiProvider
    schema = RESTGeminiProvider(api_key="x")._sanitize_schema(ProjectRequirements.resolved_schema())
    fi = schema["properties"]["functional_intent"]
    assert "$ref" not in json.dumps(schema) and "$defs" not in json.dumps(schema)
    assert set(fi["properties"]["behaviors"]["items"]["properties"]["when"]["properties"]["relation"]["enum"]) >= {"above", "below"}
