import json
import time
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import ValidationError

from core.models import DesignProject, ValidationResult
from core.enums import ValidationStatus
from .provider import ModelProvider
from .tools import (
    search_components, get_component, search_curriculum, validate_design
)


class AgentState(str, Enum):
    RUNNING = "RUNNING"
    PROPOSING = "PROPOSING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class Orchestrator:
    """Manages the lifecycle of an AI engineering proposal, validation, and repair loop."""
    
    SYSTEM_PROMPT = """You are the AI Engineering Orchestrator for the Illustration Engine.
Your task is to convert a user's natural language request into a valid DesignProject.

CRITICAL RULES:
1. You MUST use the registry. Never invent components, pin names, or voltage bounds.
2. The user will specify constraints (e.g. "smart parking using ESP32"). Use the tools to find the exact component_type_id in the registry.
3. If multiple variants exist, select the most appropriate or ask for clarification.
4. Once you have enough information, generate a DesignProject.
5. If validation fails, you will receive the exact structured ValidationResult. Analyze the errors (e.g. E010 VOLTAGE_INCOMPATIBLE means you need a voltage divider or level shifter). 
6. Fix the topology and propose the repaired DesignProject.
7. DO NOT fabricate validation results.
"""

    def __init__(self, provider: ModelProvider, max_repair_attempts: int = 3):
        self.provider = provider
        self.max_repair_attempts = max_repair_attempts
        self.state = AgentState.RUNNING
        self.history: List[Dict[str, Any]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]
        self.traces: List[Dict[str, Any]] = []

    def _log_trace(self, event: str, data: Any) -> None:
        self.traces.append({
            "timestamp": time.time(),
            "event": event,
            "data": data
        })
        if hasattr(self, "verbose_callback") and self.verbose_callback:
            self.verbose_callback(event, data)

    def _get_tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_components",
                    "description": "Search the component registry for parts.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_component",
                    "description": "Get detailed authoritative data for a specific component_type_id.",
                    "parameters": {
                        "type": "object",
                        "properties": {"component_id": {"type": "string"}},
                        "required": ["component_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_curriculum",
                    "description": "Search curriculum concepts.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_led_resistor",
                    "description": "Calculate required LED resistor deterministically.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "supply_voltage": {"type": "number"},
                            "forward_voltage": {"type": "number"},
                            "target_current_ma": {"type": "number"}
                        },
                        "required": ["supply_voltage", "forward_voltage", "target_current_ma"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "validate_design",
                    "description": "Run deterministic validation on a provisional design before submitting it.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "design": {"type": "object", "description": "A provisional DesignProject dictionary representation"}
                        },
                        "required": ["design"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_clarification",
                    "description": "Call this if a required component is unsupported or the user's intent is ambiguous.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Why clarification is needed (e.g. 'UNSUPPORTED component')"},
                            "missing_choices": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["reason", "missing_choices"]
                    }
                }
            }
        ]

    def _execute_tool(self, name: str, args: dict) -> str:
        try:
            if name == "search_components":
                results = search_components(args["query"])
                return json.dumps([r.model_dump() for r in results])
            elif name == "get_component":
                comp = get_component(args["component_id"])
                return json.dumps(comp.model_dump()) if comp else json.dumps({"error": "Component not found"})
            elif name == "search_curriculum":
                results = search_curriculum(args["query"])
                return json.dumps([r.model_dump() for r in results])
            elif name == "calculate_led_resistor":
                from validation.calculations import calculate_led_resistor
                res = calculate_led_resistor(args["supply_voltage"], args["forward_voltage"], args["target_current_ma"])
                return json.dumps(res.model_dump())
            elif name == "validate_design":
                from core.models import DesignProject
                from ai.tools import validate_design
                provisional_design = DesignProject.model_validate(args["design"])
                val_res = validate_design(provisional_design)
                return json.dumps(val_res.model_dump())
            elif name == "request_clarification":
                self.state = AgentState.CLARIFICATION_REQUIRED
                self._log_trace("CLARIFICATION_REQUIRED", args)
                return json.dumps({"status": "Clarification requested. Agent will halt."})
            else:
                return json.dumps({"error": f"Unknown tool {name}"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def run(self, user_prompt: str) -> Optional[DesignProject]:
        """Main entry point for the orchestrator."""
        self.history.append({"role": "user", "content": user_prompt})
        self._log_trace("USER_PROMPT", user_prompt)
        
        self.state = AgentState.PROPOSING
        tools = self._get_tools()
        
        # Reasoning and exploration loop
        for _ in range(10):
            if self.state == AgentState.CLARIFICATION_REQUIRED:
                return None
                
            message = self.provider.tool_call(self.history, tools=tools)
            self.history.append(message)
            
            if "tool_calls" in message and message["tool_calls"]:
                for tool_call in message["tool_calls"]:
                    name = tool_call["function"]["name"]
                    args = json.loads(tool_call["function"]["arguments"])
                    
                    result_str = self._execute_tool(name, args)
                    self._log_trace("TOOL_CALL", {"tool": name, "args": args, "result": result_str})
                    
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": name,
                        "content": result_str
                    })
                    
                if self.state == AgentState.CLARIFICATION_REQUIRED:
                    return None
            else:
                # No more tool calls; transition to proposing structured output
                break
                
        return self._propose_and_repair_loop()

    def _propose_and_repair_loop(self) -> Optional[DesignProject]:
        attempts = 0
        
        while attempts <= self.max_repair_attempts:
            self.state = AgentState.PROPOSING if attempts == 0 else AgentState.REPAIRING
            
            try:
                self._log_trace("PROPOSAL_REQUESTED", {"attempt": attempts})
                design: DesignProject = self.provider.structured_generate(self.history, DesignProject)
            except Exception as e:
                self.history.append({
                    "role": "user",
                    "content": f"Failed to parse structured output: {str(e)}. Please try again."
                })
                attempts += 1
                continue
                
            self._log_trace("PROPOSED_DESIGN", design.model_dump())
            
            self.state = AgentState.VALIDATING
            validation_result = validate_design(design)
            self._log_trace("VALIDATION_RESULT", validation_result.model_dump())
            
            if validation_result.status == ValidationStatus.PASS:
                self.state = AgentState.COMPLETED
                self._log_trace("COMPLETED", {"status": "SUCCESS"})
                return design
                
            # Must repair
            self.history.append({
                "role": "assistant",
                "content": f"Proposed design ID: {design.project_id}"
            })
            
            error_message = json.dumps(validation_result.model_dump(), indent=2)
            self.history.append({
                "role": "user",
                "content": f"Validation failed with the following errors. You MUST repair the design to resolve these errors:\n\n{error_message}"
            })
            
            # The model could potentially want to use tools again during repair.
            # We let it do up to 3 tool calls before forcing the structure again.
            tools = self._get_tools()
            for _ in range(3):
                message = self.provider.tool_call(self.history, tools=tools)
                if not message.get("tool_calls"):
                    # Optionally remove the empty text message if we just want structured output next
                    if not message.get("content"):
                        pass
                    else:
                        self.history.append(message)
                    break
                self.history.append(message)
                for tool_call in message["tool_calls"]:
                    name = tool_call["function"]["name"]
                    args = json.loads(tool_call["function"]["arguments"])
                    result_str = self._execute_tool(name, args)
                    self._log_trace("TOOL_CALL", {"tool": name, "args": args, "result": result_str})
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": name,
                        "content": result_str
                    })
            
            attempts += 1
            
        self.state = AgentState.FAILED
        self._log_trace("FAILED", {"reason": "MAX_REPAIR_ATTEMPTS_EXCEEDED"})
        return None
