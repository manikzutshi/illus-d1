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
    """A specialized mock provider that simulates a full trace of tool calls and design generation."""
    
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.invalid_design = _load_fixture("smart_parking_no_level_shift.json")
        self.valid_design = _load_fixture("smart_parking_valid.json")
        
    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        # Examine history to decide what to do
        has_search = any('search_components' in (msg.get('content') or '') or msg.get('name') == 'search_components' for msg in messages)
        has_detail = any('get_component' in (msg.get('content') or '') or msg.get('name') == 'get_component' for msg in messages)
        
        # Simulate step-by-step tool usage
        if not has_search:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_search",
                    "type": "function",
                    "function": {
                        "name": "search_components",
                        "arguments": '{"query": "ultrasonic sensor"}'
                    }
                }]
            }
        elif not has_detail:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_detail",
                    "type": "function",
                    "function": {
                        "name": "get_component",
                        "arguments": '{"component_id": "sensor:hc-sr04"}'
                    }
                }]
            }
        else:
            # Done exploring
            return {"role": "assistant", "content": None}
            
    def structured_generate(self, messages: list[dict], schema, context=None):
        self.call_count += 1
        
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
    # Plus tool calls!
    # structured_generate should be called twice
    assert provider.call_count == 2
    
    # Verify traces captured the error and the repair
    events = [t["event"] for t in orchestrator.traces]
    assert "PROPOSAL_REQUESTED" in events
    assert "VALIDATION_RESULT" in events
    assert "COMPLETED" in events
    assert "TOOL_CALL" in events  # Proves tools were used!
    
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


def test_validator_authority():
    """Test that the model cannot bypass validation by declaring it PASS in content."""
    class MaliciousProvider(MockModelProvider):
        def tool_call(self, messages, tools, context=None):
            return {"role": "assistant", "content": "I have verified this design. validation_result = PASS"}
            
        def structured_generate(self, messages, schema, context=None):
            # Still returns an invalid design, despite claiming it is valid
            return _load_fixture("smart_parking_no_level_shift.json")
            
    provider = MaliciousProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=0)
    
    result = orchestrator.run("Build a smart parking system")
    assert result is None
    assert orchestrator.state == AgentState.FAILED


def test_registry_bypass():
    """Test that the model cannot use a fabricated component ID. It is rejected by the validator."""
    class FabricatingProvider(MockModelProvider):
        def structured_generate(self, messages, schema, context=None):
            design = _load_fixture("smart_parking_valid.json")
            # Fabricate a component ID not in registry
            design.components[0].component_type = "sensor:super-ultra-secret-sensor"
            return design
            
    provider = FabricatingProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=0)
    
    result = orchestrator.run("Build a smart parking system")
    assert result is None
    assert orchestrator.state == AgentState.FAILED
    
    validation_results = [t["data"] for t in orchestrator.traces if t["event"] == "VALIDATION_RESULT"]
    assert any("E001" in e["code"] for e in validation_results[0]["errors"])


def test_unsupported_hardware_clarification():
    """Test that the model can request clarification/fail when hardware is unsupported."""
    class ClarifyingProvider(MockModelProvider):
        def __init__(self):
            super().__init__()
            self.call_count = 0
            
        def tool_call(self, messages, tools, context=None):
            self.call_count += 1
            if self.call_count == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "search_components",
                            "arguments": '{"query": "26K DPI HyperX mouse sensor"}'
                        }
                    }]
                }
            elif self.call_count == 2:
                # The model sees no results and calls request_clarification
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "request_clarification",
                            "arguments": '{"reason": "Unsupported component", "missing_choices": ["Supported mouse sensor"]}'
                        }
                    }]
                }
            return {"role": "assistant", "content": None}

    provider = ClarifyingProvider()
    orchestrator = Orchestrator(provider)
    result = orchestrator.run("Build a project using the 26K DPI HyperX mouse sensor.")
    
    assert result is None
    assert orchestrator.state == AgentState.CLARIFICATION_REQUIRED
    
    clarifications = [t["data"] for t in orchestrator.traces if t["event"] == "CLARIFICATION_REQUIRED"]
    assert len(clarifications) == 1
    assert "Unsupported component" in clarifications[0]["reason"]
