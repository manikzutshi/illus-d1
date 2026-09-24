import pytest
import json
from pathlib import Path

from core.models import EngineeringDesignProject
from ai.provider import MockModelProvider
from ai.orchestrator import Orchestrator, AgentState

FIXTURES = Path(__file__).parent.parent / "fixtures" / "golden"

def _load_fixture(name: str) -> EngineeringDesignProject:
    path = FIXTURES / name
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return EngineeringDesignProject.model_validate(data)

class MockRepairProvider(MockModelProvider):
    """A specialized mock provider that simulates a full trace of tool calls and design generation."""
    
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.invalid_design = _load_fixture("smart_parking_no_level_shift.json")
        self.valid_design = _load_fixture("smart_parking_valid.json")
        
    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        # Examine history to decide what to do
        has_search = any(msg.get('role') == 'tool' and msg.get('name') == 'search_components' for msg in messages)
        has_detail = any(msg.get('role') == 'tool' and msg.get('name') == 'get_component' for msg in messages)
        
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
        if schema.__name__ == "ProjectRequirements":
            from ai.models import ProjectRequirements
            return ProjectRequirements(intent="mock")
        
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
            if schema.__name__ == "ProjectRequirements":
                from ai.models import ProjectRequirements
                return ProjectRequirements(intent="mock")
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
            if schema.__name__ == "ProjectRequirements":
                from ai.models import ProjectRequirements
                return ProjectRequirements(intent="mock")
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
            if schema.__name__ == "ProjectRequirements":
                from ai.models import ProjectRequirements
                return ProjectRequirements(intent="Build a mock system")
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
class MockToolPassProvider(MockModelProvider):
    """Simulates Gemini using the validate_design tool and getting a PASS."""
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.valid_design = _load_fixture("smart_parking_valid.json")
        self.structured_calls = 0

    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        # Always call validate_design with the valid design
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_validate",
                "type": "function",
                "function": {
                    "name": "validate_design",
                    "arguments": json.dumps({"design": self.valid_design.model_dump()})
                }
            }]
        }

    def structured_generate(self, messages: list[dict], schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            from ai.models import ProjectRequirements
            return ProjectRequirements(intent="mock")
        
        self.structured_calls += 1
        return self.valid_design

def test_orchestrator_tool_pass_terminates_immediately():
    """Test that if validate_design returns PASS, the orchestrator terminates immediately."""
    provider = MockToolPassProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=3)
    
    result = orchestrator.run("Build a smart parking system")
    
    assert result is not None
    assert result.project_id == "smart-parking-mvp"
    assert orchestrator.state == AgentState.COMPLETED
    
    # structured_generate for EngineeringDesignProject should never be called
    assert provider.structured_calls == 0
    
    events = [t["event"] for t in orchestrator.traces]
    assert "PROPOSAL_REQUESTED" not in events
    
    # Tool call should be present
    assert "TOOL_CALL" in events

class MockDirectPassProvider(MockModelProvider):
    """Simulates Gemini not using validate_design tool, but providing a valid design on first structured_generate."""
    def __init__(self):
        super().__init__()
        self.valid_design = _load_fixture("smart_parking_valid.json")
        self.structured_calls = 0

    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        return {"role": "assistant", "content": "I am ready."}

    def structured_generate(self, messages: list[dict], schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            from ai.models import ProjectRequirements
            return ProjectRequirements(intent="mock")
        
        self.structured_calls += 1
        return self.valid_design

def test_orchestrator_initial_proposal_pass():
    """Test initial proposal PASS -> zero repairs -> zero additional requests."""
    provider = MockDirectPassProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=3)
    
    result = orchestrator.run("Build a smart parking system")
    
    assert result is not None
    assert orchestrator.state == AgentState.COMPLETED
    assert provider.structured_calls == 1
    
    events = [t["event"] for t in orchestrator.traces]
    proposal_requests = [e for e in events if e == "PROPOSAL_REQUESTED"]
    assert len(proposal_requests) == 1

class MockFailingExtractionProvider(MockModelProvider):
    def structured_generate(self, messages: list[dict], schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            raise Exception("Mock network timeout")
        return _load_fixture("smart_parking_valid.json")
    
    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        return {"role": "assistant", "content": "Ready"}

def test_requirements_extraction_fallback():
    """Test that a failure in requirements extraction falls back safely to the user prompt."""
    provider = MockFailingExtractionProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=3)
    
    user_prompt = "Build a super special custom project"
    result = orchestrator.run(user_prompt)
    
    events = [t["event"] for t in orchestrator.traces]
    assert "REQUIREMENTS_EXTRACTION_FAILED" in events
    assert result is not None
    
    # The requirement extraction fallback message should contain the original prompt
    assistant_msg = orchestrator.history[2]["content"]
    assert user_prompt in assistant_msg

from ai.orchestrator import Orchestrator, AgentState
from ai.provider import MockModelProvider
from ai.models import ProjectRequirements
import pytest
import json

class MockExtractionProvider(MockModelProvider):
    def __init__(self, mock_reqs: ProjectRequirements):
        super().__init__()
        self.mock_reqs = mock_reqs
        
    def structured_generate(self, messages: list[dict], schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            return self.mock_reqs
        return super().structured_generate(messages, schema, context)
        
    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        return {"role": "assistant", "content": "Tool call mock"}

def test_unspecified_threshold_ambiguity():
    """Test that unspecified thresholds remain explicit in the pipeline."""
    reqs = ProjectRequirements(
        intent="Build water level",
        ambiguities=["Unspecified numeric threshold for water level"]
    )
    provider = MockExtractionProvider(reqs)
    orchestrator = Orchestrator(provider, max_repair_attempts=0)
    
    orchestrator.run("Build water level with threshold")
    
    # Check that the ambiguity was passed to the main loop
    req_msg = orchestrator.history[2]["content"]
    assert "Unspecified numeric threshold" in req_msg

def test_explicit_threshold():
    """Test that explicit thresholds are passed to the pipeline."""
    reqs = ProjectRequirements(
        intent="Build water level",
        thresholds=["distance < 20cm"]
    )
    provider = MockExtractionProvider(reqs)
    orchestrator = Orchestrator(provider, max_repair_attempts=0)
    
    orchestrator.run("Build water level with < 20cm threshold")
    
    req_msg = orchestrator.history[2]["content"]
    assert "distance < 20cm" in req_msg
    assert "Unspecified" not in req_msg


def test_no_simulation_metadata_by_default():
    """Test that the system prompt explicitly forbids generating Wokwi/firmware metadata."""
    from ai.orchestrator import Orchestrator
    from ai.provider import MockModelProvider
    orchestrator = Orchestrator(MockModelProvider())
    assert "DO NOT generate simulation metadata" in orchestrator.SYSTEM_PROMPT
    assert "Wokwi" in orchestrator.SYSTEM_PROMPT


def test_tool_caching_search_and_get():
    from ai.provider import MockModelProvider
    from ai.orchestrator import Orchestrator
    
    # We don't even need a complex provider, just the orchestrator
    orchestrator = Orchestrator(MockModelProvider())
    
    # Execute a search tool twice
    args = {"query": "resistor"}
    res1 = orchestrator._execute_tool("search_components", args)
    assert orchestrator.metrics["cache_misses"] == 1
    assert orchestrator.metrics["cache_hits"] == 0
    
    res2 = orchestrator._execute_tool("search_components", args)
    assert orchestrator.metrics["cache_misses"] == 1
    assert orchestrator.metrics["cache_hits"] == 1
    assert res1 == res2
    
    # Execute a get tool twice
    args2 = {"component_id": "passive:resistor-tht"}
    res3 = orchestrator._execute_tool("get_component", args2)
    assert orchestrator.metrics["cache_misses"] == 2
    assert orchestrator.metrics["cache_hits"] == 1
    
    res4 = orchestrator._execute_tool("get_component", args2)
    assert orchestrator.metrics["cache_misses"] == 2
    assert orchestrator.metrics["cache_hits"] == 2
    assert res3 == res4

def test_tool_caching_validation_unchanged():
    from ai.provider import MockModelProvider
    from ai.orchestrator import Orchestrator
    from core.models import EngineeringDesignProject
    import json
    
    orchestrator = Orchestrator(MockModelProvider())
    design = _load_fixture("smart_parking_no_level_shift.json")
    design_dict = design.model_dump()
    
    args = {"design": design_dict}
    
    res1 = orchestrator._execute_tool("validate_design", args)
    assert orchestrator.metrics["validation_call_count"] == 1
    
    # Execute again with same design
    res2 = orchestrator._execute_tool("validate_design", args)
    assert orchestrator.metrics["validation_call_count"] == 1  # Should NOT increment
    assert res1 == res2

def test_tool_caching_validation_changed():
    from ai.provider import MockModelProvider
    from ai.orchestrator import Orchestrator
    from core.models import EngineeringDesignProject
    
    orchestrator = Orchestrator(MockModelProvider())
    design = _load_fixture("smart_parking_no_level_shift.json")
    
    args1 = {"design": design.model_dump()}
    res1 = orchestrator._execute_tool("validate_design", args1)
    assert orchestrator.metrics["validation_call_count"] == 1

class MockFailingExtractionProvider(MockModelProvider):
    def structured_generate(self, messages: list[dict], schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            raise Exception("Mock network timeout")
        return _load_fixture("smart_parking_valid.json")
    
    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        return {"role": "assistant", "content": "Ready"}

def test_requirements_extraction_fallback():
    """Test that a failure in requirements extraction falls back safely to the user prompt."""
    provider = MockFailingExtractionProvider()
    orchestrator = Orchestrator(provider, max_repair_attempts=3)
    
    user_prompt = "Build a super special custom project"
    result = orchestrator.run(user_prompt)
    
    events = [t["event"] for t in orchestrator.traces]
    assert "REQUIREMENTS_EXTRACTION_FAILED" in events
    assert result is not None
    
    # The requirement extraction fallback message should contain the original prompt
    assistant_msg = orchestrator.history[2]["content"]
    assert user_prompt in assistant_msg

from ai.orchestrator import Orchestrator, AgentState
from ai.provider import MockModelProvider
from ai.models import ProjectRequirements
import pytest
import json

class MockExtractionProvider(MockModelProvider):
    def __init__(self, mock_reqs: ProjectRequirements):
        super().__init__()
        self.mock_reqs = mock_reqs
        
    def structured_generate(self, messages: list[dict], schema, context=None):
        if schema.__name__ == "ProjectRequirements":
            return self.mock_reqs
        return super().structured_generate(messages, schema, context)
        
    def tool_call(self, messages: list[dict], tools: list[dict], context=None):
        return {"role": "assistant", "content": "Tool call mock"}

def test_unspecified_threshold_ambiguity():
    """Test that unspecified thresholds remain explicit in the pipeline."""
    reqs = ProjectRequirements(
        intent="Build water level",
        ambiguities=["Unspecified numeric threshold for water level"]
    )
    provider = MockExtractionProvider(reqs)
    orchestrator = Orchestrator(provider, max_repair_attempts=0)
    
    orchestrator.run("Build water level with threshold")
    
    # Check that the ambiguity was passed to the main loop
    req_msg = orchestrator.history[2]["content"]
    assert "Unspecified numeric threshold" in req_msg

def test_explicit_threshold():
    """Test that explicit thresholds are passed to the pipeline."""
    reqs = ProjectRequirements(
        intent="Build water level",
        thresholds=["distance < 20cm"]
    )
    provider = MockExtractionProvider(reqs)
    orchestrator = Orchestrator(provider, max_repair_attempts=0)
    
    orchestrator.run("Build water level with < 20cm threshold")
    
    req_msg = orchestrator.history[2]["content"]
    assert "distance < 20cm" in req_msg
    assert "Unspecified" not in req_msg


def test_no_simulation_metadata_by_default():
    """Test that the system prompt explicitly forbids generating Wokwi/firmware metadata."""
    from ai.orchestrator import Orchestrator
    from ai.provider import MockModelProvider
    orchestrator = Orchestrator(MockModelProvider())
    assert "DO NOT generate simulation metadata" in orchestrator.SYSTEM_PROMPT
    assert "Wokwi" in orchestrator.SYSTEM_PROMPT


def test_tool_caching_search_and_get():
    from ai.provider import MockModelProvider
    from ai.orchestrator import Orchestrator
    
    # We don't even need a complex provider, just the orchestrator
    orchestrator = Orchestrator(MockModelProvider())
    
    # Execute a search tool twice
    args = {"query": "resistor"}
    res1 = orchestrator._execute_tool("search_components", args)
    assert orchestrator.metrics["cache_misses"] == 1
    assert orchestrator.metrics["cache_hits"] == 0
    
    res2 = orchestrator._execute_tool("search_components", args)
    assert orchestrator.metrics["cache_misses"] == 1
    assert orchestrator.metrics["cache_hits"] == 1
    assert res1 == res2
    
    # Execute a get tool twice
    args2 = {"component_id": "passive:resistor-tht"}
    res3 = orchestrator._execute_tool("get_component", args2)
    assert orchestrator.metrics["cache_misses"] == 2
    assert orchestrator.metrics["cache_hits"] == 1
    
    res4 = orchestrator._execute_tool("get_component", args2)
    assert orchestrator.metrics["cache_misses"] == 2
    assert orchestrator.metrics["cache_hits"] == 2
    assert res3 == res4

def test_tool_caching_validation_unchanged():
    from ai.provider import MockModelProvider
    from ai.orchestrator import Orchestrator
    from core.models import EngineeringDesignProject
    import json
    
    orchestrator = Orchestrator(MockModelProvider())
    design = _load_fixture("smart_parking_no_level_shift.json")
    design_dict = design.model_dump()
    
    args = {"design": design_dict}
    
    res1 = orchestrator._execute_tool("validate_design", args)
    assert orchestrator.metrics["validation_call_count"] == 1
    
    # Execute again with same design
    res2 = orchestrator._execute_tool("validate_design", args)
    assert orchestrator.metrics["validation_call_count"] == 1  # Should NOT increment
    assert res1 == res2

def test_tool_caching_validation_changed():
    from ai.provider import MockModelProvider
    from ai.orchestrator import Orchestrator
    from core.models import EngineeringDesignProject
    
    orchestrator = Orchestrator(MockModelProvider())
    design = _load_fixture("smart_parking_no_level_shift.json")
    
    args1 = {"design": design.model_dump()}
    res1 = orchestrator._execute_tool("validate_design", args1)
    assert orchestrator.metrics["validation_call_count"] == 1
    
    # Change the design
    design.name = "Modified Name"
    args2 = {"design": design.model_dump()}
    
    res2 = orchestrator._execute_tool("validate_design", args2)
    assert orchestrator.metrics["validation_call_count"] == 2  # Should increment because design changed
