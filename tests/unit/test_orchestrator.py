import pytest
import json
from pathlib import Path

from core.models import DesignProject
from ai.provider import MockModelProvider
from ai.orchestrator import Orchestrator, AgentState

FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden"

def _load_fixture(name: str) -> DesignProject:
    path = FIXTURES / name
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return DesignProject.model_validate(data)

class MockRepairProvider(MockModelProvider):
    """A specialized mock provider that returns an invalid design first, then a valid one when prompted with errors."""
    
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.invalid_design = _load_fixture("smart_parking_no_level_shift.json")
        self.valid_design = _load_fixture("smart_parking_valid.json")
        
    def structured_generate(self, messages: list[dict], schema, context=None):
        self.call_count += 1
        
        # Check if we are in the repair phase (error feedback was given)
        is_repair = any(
            "Validation failed" in (msg.get("content") or "") 
            for msg in messages
        )
        
        if not is_repair:
            return self.invalid_design
        else:
            return self.valid_design

def test_orchestrator_repair_loop():
    """Test that the orchestrator properly loops, feeds E010 error back, and accepts the repaired design."""
    provider = MockRepairProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=3)
    
    result = orchestrator.run("Build a smart parking system")
    
    # Verify the result is the valid design
    assert result is not None
    assert result.project_id == "smart-parking-mvp"
    
    # Verify the orchestrator state
    assert orchestrator.state == AgentState.COMPLETED
    
    # Verify the mock was called exactly twice (once for initial, once for repair)
    assert provider.call_count == 2
    
    # Verify traces captured the error and the repair
    events = [t["event"] for t in orchestrator.traces]
    assert "PROPOSAL_REQUESTED" in events
    assert "VALIDATION_RESULT" in events
    assert "COMPLETED" in events
    
    # Verify the first validation result was a FAIL
    validation_results = [t["data"] for t in orchestrator.traces if t["event"] == "VALIDATION_RESULT"]
    assert len(validation_results) == 2
    assert validation_results[0]["status"] == "FAIL"
    
    # Verify the specific error E010 was captured in the trace
    assert any(e["code"] == "E010" for e in validation_results[0]["errors"])
    
    # Verify the second validation was a PASS
    assert validation_results[1]["status"] == "PASS"

def test_orchestrator_repair_limit_exceeded():
    """Test that the orchestrator aborts if max repair attempts are exhausted."""
    class FailAlwaysProvider(MockModelProvider):
        def structured_generate(self, messages, schema, context=None):
            return _load_fixture("smart_parking_no_level_shift.json")
            
    provider = FailAlwaysProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=2)
    
    result = orchestrator.run("Build a smart parking system")
    
    assert result is None
    assert orchestrator.state == AgentState.FAILED
    
    # Initial + 2 repairs = 3 attempts total
    validation_results = [t["data"] for t in orchestrator.traces if t["event"] == "VALIDATION_RESULT"]
    assert len(validation_results) == 3
