import json
import time
from enum import Enum
from typing import Optional, List, Dict, Any

from pydantic import ValidationError

from core.models import EngineeringDesignProject, ValidationResult
from core.enums import ValidationStatus
from .provider import ModelProvider
from .tools import (
    search_components, get_component, search_curriculum, validate_design
)


def _component_for_ai(comp) -> dict:
    """Engineering facts the planner needs, without drawing/packaging/teaching metadata."""
    return comp.model_dump(exclude={"symbol", "physical", "education", "symbol_library", "symbol_name",
                                    "symbol_footprint", "asset_2d", "asset_3d", "simulation_model", "license",
                                    "provenance", "validation_status"}, exclude_none=True)


REQUIREMENTS_PROMPT = """You are a requirements analyst. Extract the structured requirements from the user's request. Identify inputs, outputs, thresholds, and any ambiguities. CRITICAL: If a threshold is mentioned but no numeric value is provided (e.g., 'crosses a threshold'), you MUST record it in ambiguities as 'Unspecified numeric threshold'.

Also fill `functional_intent` - WHAT the circuit must do, independent of how it is built:
- signals: one entry per functional input and output. role = input|output. quantity uses this vocabulary:
  inputs: temperature, light, motion, distance, humidity, gas, acceleration, rotation, press (button/switch), setting (knob/potentiometer as a user input), logic, signal
  outputs: light_emission (LED/lamp), sound_emission (buzzer/alarm), motion_output (motor/servo/fan), display, switching (relay/load), storage, logic, signal
  component_hint: the part name only if the user named one (e.g. 'LM35').
- behaviors: WHEN <input> <relation> THEN <output> <effect>.
  relation: above | below (a threshold), present | absent, pressed | released, proportional | inverse, changes, or periodic/always with no input for autonomous behaviour (blinking, firmware-timed).
  threshold.kind: adjustable if the user wants to set/adjust it, fixed if a value is given, otherwise unspecified.
  effect: on | off | proportional | inverse | display | toggle | pulse.
  Every id used in a behavior (when.input, then.output) MUST be declared in `signals`. A behavior that reads a sensor or control (e.g. showing a measured distance, reacting to a button) must name that input; use periodic/always only when nothing is sensed.
  Example: "buzzer on above an adjustable temperature" -> signals [{id: temp, role: input, quantity: temperature}, {id: alarm, role: output, quantity: sound_emission}]; behaviors [when {input: temp, relation: above, threshold: {kind: adjustable}} then {output: alarm, effect: on}].
  Example: "show the measured distance on a display" -> signals [{id: dist, role: input, quantity: distance}, {id: screen, role: output, quantity: display}]; behaviors [when {input: dist, relation: changes} then {output: screen, effect: display}].
- processing: microcontroller / analog / logic only if the user demands it, else any.
- required_components: parts the user explicitly asked for.
Do not describe how to build it; only what it must do."""


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
Your task is to convert a user's natural language request into a valid EngineeringDesignProject.

CRITICAL RULES:
1. You MUST use the registry. Never invent components, pin names, or voltage bounds.
2. The user will specify constraints. Use the tools to find the exact component_type_id in the registry.
3. If critical engineering parameters (e.g. numeric thresholds) are not specified by the user, DO NOT silently invent them. If a design can still be represented safely without committing to a numeric threshold, preserve a symbolic/unspecified representation (e.g. use "<UNSPECIFIED>" for the logic condition value). Use the `request_clarification` tool ONLY if a specific numeric value is absolutely required to define the architecture.
4. DO NOT generate simulation metadata (Wokwi targets) or firmware paths unless explicitly requested. We are not implementing simulation or firmware in this phase.
5. Once you have enough information, generate an EngineeringDesignProject.
6. If validation fails, analyze the structured ValidationResult errors and fix the topology. Repair ONLY the invalid portions of the design rather than regenerating everything from scratch.
7. DO NOT fabricate validation results.

OPTIMIZATION RULES:
A. The `search_components` tool returns full component metadata. Do NOT call `get_component` for a component if you already found it via search. Only use `get_component` if you need authoritative data not present in your search results.
B. Do not issue the exact same tool call twice in a row. Use the information already present in the conversation history.

GENERAL DESIGN METHOD (works for any circuit - do not rely on memorised example projects):
1. Decompose the request into functions: sensing, decision/control, actuation/indication, signal conditioning, power supply, interfaces.
2. Call `browse_library` once to see the whole vocabulary (ids, families, pins), then `search_components` / `get_component` for the parts you intend to use. Prefer parts whose supply range and logic levels match each other.
3. Call `search_patterns` / `get_pattern` for proven building blocks (LED indicator, transistor or MOSFET switch, flyback diode, pull-ups, dividers, level shifting, amplifiers, regulators, timers). Reproduce their wiring exactly with your own instance ids.
4. Use `calculate` for component values (LED resistor, divider, base resistor, RC, 555, op-amp gain). Never guess values.
5. Every design needs a real supply: a power source part (battery, USB supply, regulator output, MCU supply-source pin, ideal source for idealised circuits) and a ground reference. Idealised logic-gate diagrams may omit power.
6. Wire by exact pin_id from the registry. Each pin appears in at most one net. Leave unused pins unconnected.
7. Respect design constraints returned with components (series resistors, pull-ups, flyback diodes, decoupling).
8. Loads that exceed a GPIO pin's current (motors, relays, buzzers drawing tens of mA) must be driven through a transistor/MOSFET/driver IC.
9. For every component set metadata.role (what it does in this design, a few words) and, when a value was calculated, metadata.rationale (the calculation). Put design-wide assumptions (e.g. assumed currents, unspecified thresholds) in `assumptions`.
10. Call `validate_design` on your draft before finishing and fix every error it reports.

FUNCTIONAL CORRECTNESS: the extracted requirements contain `functional_intent` (signals and WHEN->THEN behaviours).
An electrically valid circuit is not enough - `validate_design` also runs a deterministic FUNCTIONAL check that the
requested input actually reaches the requested output through a decision stage (comparator / microcontroller / logic),
with the requested direction (e.g. ON *above* vs *below* a threshold), an adjustable reference when asked, and a driver
stage for loads that need one. Every output must be *controlled*, not merely powered. For microcontroller designs, add a
`logic` rule (condition on the input instance, action on the output instance) that states the firmware behaviour.
Fix every functional FAIL (codes F0xx) using its repair hint.
"""

    def __init__(self, provider: ModelProvider, max_repair_attempts: int = 3):
        self.provider = provider
        self.max_repair_attempts = max_repair_attempts
        self.state = AgentState.RUNNING
        self._validated_design: Optional[EngineeringDesignProject] = None
        self.functional_intent = None          # FunctionalIntent from requirements (never from the design)
        self.last_functional_report = None
        self.history: List[Dict[str, Any]] = [
            {"role": "system", "content": self.SYSTEM_PROMPT}
        ]
        self.traces: List[Dict[str, Any]] = []
        self._tool_cache: Dict[str, str] = {}
        self.metrics = {
            "model_call_count": 0,
            "tool_call_count": 0,
            "tool_calls_by_name": {},
            "cache_hits": 0,
            "cache_misses": 0,
            "validation_call_count": 0,
            "functional_fail_count": 0,
            "repair_count": 0,
            "start_time": time.time()
        }

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
                    "name": "browse_library",
                    "description": "Compact list of every registered component: id, name, category, family, tags and pin ids. Optionally filter by category.",
                    "parameters": {
                        "type": "object",
                        "properties": {"category": {"type": "string", "description": "Optional category filter, e.g. SENSOR, SEMICONDUCTOR, INTEGRATED_CIRCUIT"}},
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_patterns",
                    "description": "Search proven design patterns (functional building blocks) by keyword, e.g. 'led', 'switch', 'flyback', 'i2c', 'amplifier', 'regulator'.",
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
                    "name": "get_pattern",
                    "description": "Full wiring of a design pattern: parts (roles, component ids), ports and pin-level nets.",
                    "parameters": {
                        "type": "object",
                        "properties": {"pattern_id": {"type": "string"}},
                        "required": ["pattern_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Deterministic engineering calculation. calculation is one of: led_resistor(supply_voltage, forward_voltage, target_current_ma), voltage_divider(v_in, r_top, r_bottom), rc_time_constant(r, c), bjt_base_resistor(v_drive, load_current_ma, hfe_min), astable_555(r1, r2, c), noninverting_gain(rf, rg). parameters_json is a JSON object of numeric inputs (engineering notation like '4.7k' allowed).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "calculation": {"type": "string"},
                            "parameters_json": {"type": "string"}
                        },
                        "required": ["calculation", "parameters_json"]
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
                            "design": EngineeringDesignProject.resolved_schema()
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
        self.metrics["tool_call_count"] += 1
        self.metrics["tool_calls_by_name"][name] = self.metrics["tool_calls_by_name"].get(name, 0) + 1
        
        # Check cache for read-only tools
        cache_key = None
        if name in ("search_components", "get_component", "search_curriculum", "browse_library", "search_patterns", "get_pattern"):
            cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
            if cache_key in self._tool_cache:
                self.metrics["cache_hits"] += 1
                return self._tool_cache[cache_key]
        
        self.metrics["cache_misses"] += 1

        try:
            result_str = ""
            if name == "search_components":
                results = search_components(args["query"])[:8]
                result_str = json.dumps([_component_for_ai(r) for r in results])
            elif name == "get_component":
                comp = get_component(args["component_id"])
                result_str = json.dumps(_component_for_ai(comp)) if comp else json.dumps({"error": "Component not found"})
            elif name == "browse_library":
                from components.registry import get_shared_registry
                rows = get_shared_registry().catalog()
                cat = (args.get("category") or "").upper()
                if cat:
                    rows = [r for r in rows if r["category"] == cat]
                result_str = json.dumps({"components": rows})
            elif name == "search_patterns":
                from knowledge import get_default_patterns
                found = get_default_patterns().search(args["query"])[:6]
                result_str = json.dumps({"patterns": [{"pattern_id": p.pattern_id, "name": p.name, "purpose": p.purpose,
                                                       "ports": [pt.name for pt in p.ports]} for p in found]})
            elif name == "get_pattern":
                from knowledge import get_default_patterns
                pat = get_default_patterns().get(args["pattern_id"])
                result_str = json.dumps(pat.model_dump() if pat else {"error": "Pattern not found"})
            elif name == "calculate":
                from validation.calculations import run_calculation
                params = args.get("parameters_json") or "{}"
                params = json.loads(params) if isinstance(params, str) else params
                result_str = json.dumps(run_calculation(args["calculation"], params).model_dump())
            elif name == "search_curriculum":
                results = search_curriculum(args["query"])
                result_str = json.dumps([r.model_dump() for r in results])
            elif name == "calculate_led_resistor":
                from validation.calculations import calculate_led_resistor
                res = calculate_led_resistor(args["supply_voltage"], args["forward_voltage"], args["target_current_ma"])
                result_str = json.dumps(res.model_dump())
            elif name == "validate_design":
                from core.models import EngineeringDesignProject
                from ai.tools import validate_design
                from core.enums import ValidationStatus
                provisional_design = EngineeringDesignProject.model_validate(args["design"])
                
                # Cache based on serialized design to skip redundant validation
                design_hash = json.dumps(provisional_design.model_dump(), sort_keys=True)
                val_cache_key = f"validate_design:{design_hash}"
                if val_cache_key in self._tool_cache:
                    val_res_dict = json.loads(self._tool_cache[val_cache_key])
                    # Re-hydrate if needed, or just return the string
                    functional_ok = val_res_dict.get("functional", {}).get("status") != "FAIL"
                    if val_res_dict.get("status") == ValidationStatus.PASS.value and functional_ok:
                        self._validated_design = provisional_design
                    return self._tool_cache[val_cache_key]
                
                self.metrics["validation_call_count"] += 1
                val_res, func, accepted = self._full_validation(provisional_design)
                if accepted:
                    self._validated_design = provisional_design
                payload = val_res.model_dump(mode="json")
                if func is not None:
                    payload["functional"] = self._functional_feedback(func)
                    if func.blocking():
                        payload["overall"] = "REJECTED: electrically " + val_res.status.value + ", functionally FAIL"
                result_str = json.dumps(payload)
                self._tool_cache[val_cache_key] = result_str
                return result_str
            elif name == "request_clarification":
                self.state = AgentState.CLARIFICATION_REQUIRED
                self._log_trace("CLARIFICATION_REQUIRED", args)
                result_str = json.dumps({"status": "Clarification requested. Agent will halt."})
            else:
                result_str = json.dumps({"error": f"Unknown tool {name}"})
                
            if cache_key:
                self._tool_cache[cache_key] = result_str
            return result_str
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _full_validation(self, design: EngineeringDesignProject):
        """Electrical validation, then functional validation against the extracted intent.
        Returns (validation_result, functional_report_or_None, accepted)."""
        from functional import validate_function
        val_res = validate_design(design)
        func = validate_function(design, self.functional_intent) if self.functional_intent else None
        self.last_functional_report = func
        if func is not None:
            self._log_trace("FUNCTIONAL_RESULT", {"status": func.status,
                                                  "findings": [f.model_dump() for f in func.findings]})
            if func.blocking():
                self.metrics["functional_fail_count"] += 1
        accepted = val_res.status == ValidationStatus.PASS and (func is None or not func.blocking())
        return val_res, func, accepted

    @staticmethod
    def _functional_feedback(func) -> dict:
        return {
            "status": func.status,
            "summary": func.summary,
            "failures": [{"code": f.code, "message": f.message, "repair_hint": f.repair_hint,
                          "affected_instances": f.affected_instances, "patterns": f.patterns,
                          "behavior": f.behavior_id} for f in func.findings if f.status == "FAIL"],
            "not_checkable": [f"{f.code}: {f.message}" for f in func.findings if f.status == "NOT_CHECKABLE"],
            "behaviours": [{"id": b.behavior_id, "status": b.status, "path": [st.instance for st in b.path]}
                           for b in func.behaviors],
        }

    def run(self, user_prompt: str) -> Optional[EngineeringDesignProject]:
        """Main entry point for the orchestrator."""
        from ai.models import ProjectRequirements
        
        self._log_trace("USER_PROMPT", user_prompt)
        
        # Phase 1: Requirements Extraction
        req_messages = [
            {"role": "system", "content": REQUIREMENTS_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            self.metrics["model_call_count"] += 1
            requirements: ProjectRequirements = self.provider.structured_generate(req_messages, ProjectRequirements)
            self._log_trace("REQUIREMENTS_EXTRACTED", requirements.model_dump())
            if requirements.functional_intent is not None and requirements.functional_intent.behaviors:
                from functional.intent import normalize_intent
                self.functional_intent, notes = normalize_intent(requirements.functional_intent)
                self._log_trace("FUNCTIONAL_INTENT", {"intent": self.functional_intent.model_dump(), "notes": notes})
        except Exception as e:
            self._log_trace("REQUIREMENTS_EXTRACTION_FAILED", str(e))
            requirements = ProjectRequirements(
                intent=f"Design as requested: {user_prompt}", 
                functional_requirements=[user_prompt],
                ambiguities=["Failed to extract structured requirements due to network or provider error. Proceed using the original request directly."]
            )
            
        if requirements.ambiguities and len(requirements.ambiguities) > 0 and len(requirements.functional_requirements) == 0:
            # If there's nothing but ambiguities, we might need to ask for clarification, but for now we continue
            pass

        # Feed the requirements into the main history
        req_str = json.dumps(requirements.model_dump(), indent=2)
        
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({
            "role": "assistant", 
            "content": f"I have extracted the following project requirements:\n```json\n{req_str}\n```\nI will use these requirements to propose a valid design."
        })
        self.history.append({
            "role": "user",
            "content": "Please proceed. Use the available tools to explore components and confirm your approach before proposing the final design."
        })
        
        self.state = AgentState.PROPOSING
        tools = self._get_tools()
        
        # Reasoning and exploration loop
        for _ in range(14):
            if self.state == AgentState.CLARIFICATION_REQUIRED:
                return None
                
            self.metrics["model_call_count"] += 1
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
                    
                if self._validated_design is not None:
                    self.state = AgentState.COMPLETED
                    self.metrics["elapsed_time"] = time.time() - self.metrics["start_time"]
                    self._log_trace("COMPLETED", {"status": "SUCCESS", "metrics": self.metrics})
                    return self._validated_design
            else:
                # No more tool calls; transition to proposing structured output
                break
                
        res = self._propose_and_repair_loop()
        if self.state == AgentState.COMPLETED:
            self.metrics["elapsed_time"] = time.time() - self.metrics["start_time"]
            self._log_trace("COMPLETED", {"status": "SUCCESS", "metrics": self.metrics})
        return res

    def _propose_and_repair_loop(self) -> Optional[EngineeringDesignProject]:
        attempts = 0
        
        # Ensure we don't send a history ending in an assistant turn, which causes Gemini to throw 400 INVALID_ARGUMENT
        if self.history and self.history[-1]["role"] == "assistant":
            self.history.append({
                "role": "user",
                "content": "Please generate the final proposed EngineeringDesignProject using the tools and logic rules discussed."
            })
            
        while attempts <= self.max_repair_attempts:
            self.state = AgentState.PROPOSING if attempts == 0 else AgentState.REPAIRING
            
            try:
                self._log_trace("PROPOSAL_REQUESTED", {"attempt": attempts})
                self.metrics["model_call_count"] += 1
                design: EngineeringDesignProject = self.provider.structured_generate(self.history, EngineeringDesignProject)
            except Exception as e:
                self.history.append({
                    "role": "user",
                    "content": f"Failed to parse structured output: {str(e)}. Please try again."
                })
                attempts += 1
                continue
                
            self._log_trace("PROPOSED_DESIGN", design.model_dump())
            
            self.state = AgentState.VALIDATING
            validation_result, func, accepted = self._full_validation(design)
            self._log_trace("VALIDATION_RESULT", validation_result.model_dump())
            
            if accepted:
                self.state = AgentState.COMPLETED
                return design
                
            # Must repair
            self.metrics["repair_count"] += 1
            self.history.append({
                "role": "assistant",
                "content": f"Proposed design ID: {design.project_id}"
            })
            
            error_message = json.dumps(validation_result.model_dump(mode="json"), indent=2)
            functional_text = ""
            if func is not None and func.blocking():
                functional_text = ("\n\nFUNCTIONAL validation FAILED - the circuit does not do what was requested. "
                                   "Fix each failure using its repair hint (keep what already works):\n\n"
                                   + json.dumps(self._functional_feedback(func), indent=2))
            self.history.append({
                "role": "user",
                "content": f"Validation failed with the following errors. You MUST repair the design to resolve these errors:\n\n{error_message}{functional_text}"
            })
            
            # The model could potentially want to use tools again during repair.
            # We let it do up to 3 tool calls before forcing the structure again.
            tools = self._get_tools()
            for _ in range(3):
                self.metrics["model_call_count"] += 1
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
                    
                if self._validated_design is not None:
                    self.state = AgentState.COMPLETED
                    return self._validated_design
            
            attempts += 1
            
        self.state = AgentState.FAILED
        self._log_trace("FAILED", {"reason": "MAX_REPAIR_ATTEMPTS_EXCEEDED"})
        return None
