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

    def run(self, user_prompt: str) -> Optional[DesignProject]:
        """Main entry point for the orchestrator."""
        self.history.append({"role": "user", "content": user_prompt})
        self._log_trace("USER_PROMPT", user_prompt)
        
        # Tools available to the agent for exploration
        exploration_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_components",
                    "description": "Search the component registry for parts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search term e.g. esp32, ultrasonic, resistor"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        
        # We start by letting the model explore and build a proposal
        self.state = AgentState.PROPOSING
        
        # Run a small reasoning loop to let it call exploration tools
        for _ in range(5):
            message = self.provider.tool_call(self.history, tools=exploration_tools)
            self.history.append(message)
            
            if "tool_calls" in message and message["tool_calls"]:
                for tool_call in message["tool_calls"]:
                    if tool_call["function"]["name"] == "search_components":
                        args = json.loads(tool_call["function"]["arguments"])
                        results = search_components(args["query"])
                        # Convert to JSON serializable list
                        result_str = json.dumps([r.model_dump() for r in results])
                        self._log_trace("TOOL_CALL", {"tool": "search_components", "args": args, "result": result_str})
                        
                        self.history.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": tool_call["function"]["name"],
                            "content": result_str
                        })
            else:
                # If no tools called, we assume it's ready to propose the design
                break
                
        # Now force the model to output a DesignProject
        return self._propose_and_repair_loop()

    def _propose_and_repair_loop(self) -> Optional[DesignProject]:
        attempts = 0
        
        while attempts <= self.max_repair_attempts:
            self.state = AgentState.PROPOSING if attempts == 0 else AgentState.REPAIRING
            
            # Request the structured DesignProject
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
            
            # Validation phase
            self.state = AgentState.VALIDATING
            validation_result = validate_design(design)
            self._log_trace("VALIDATION_RESULT", validation_result.model_dump())
            
            if validation_result.status == ValidationStatus.PASS:
                self.state = AgentState.COMPLETED
                self._log_trace("COMPLETED", {"status": "SUCCESS"})
                return design
                
            # If invalid, feed the errors back to the model
            self.history.append({
                "role": "assistant",
                "content": f"Proposed design ID: {design.project_id}"
            })
            
            error_message = json.dumps(validation_result.model_dump(), indent=2)
            self.history.append({
                "role": "user",
                "content": f"Validation failed with the following errors. You MUST repair the design to resolve these errors:\n\n{error_message}"
            })
            
            attempts += 1
            
        self.state = AgentState.FAILED
        self._log_trace("FAILED", {"reason": "MAX_REPAIR_ATTEMPTS_EXCEEDED"})
        return None
