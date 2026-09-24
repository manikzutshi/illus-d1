# Orchestrator: Illustration Engine AI Engineering Loop

This document examines the AI orchestration loop in detail, tracing the complete AI engineering process from requirement extraction to final validated design.

## Orchestrator Implementation

**File:** `src/ai/orchestrator.py`  
**Class:** `Orchestrator`

### Core Functionality
```python
class Orchestrator:
    """Manages the lifecycle of an AI engineering proposal, validation, and repair loop."""
    
    SYSTEM_PROMPT = """You are the AI Engineering Orchestrator for the Illustration Engine.
    Your task is to convert a user's natural language request into a valid DesignProject.
    
    CRITICAL RULES:
    1. You MUST use the registry. Never invent components, pin names, or voltage bounds.
    2. The user will specify constraints. Use the tools to find the exact component_type_id in the registry.
    3. If critical engineering parameters (e.g. numeric thresholds) are not specified by the user, DO NOT silently invent them...
    4. DO NOT generate simulation metadata (Wokwi targets) or firmware paths unless explicitly requested...
    5. Once you have enough information, generate a DesignProject.
    6. If validation fails, analyze the structured ValidationResult errors and fix the topology...
    7. DO NOT fabricate validation results.
    
    OPTIMIZATION RULES:
    A. The `search_components` tool returns full component metadata. Do NOT call `get_component` for a component if you already found it via search...
    B. Do not issue the exact same tool call twice in a row..."""
```

### Constructor
```python
def __init__(self, provider: ModelProvider, max_repair_attempts: int = 3):
    self.provider = provider
    self.max_repair_attempts = max_repair_attempts
    self.state = AgentState.RUNNING
    self._validated_design: Optional[DesignProject] = None
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
        "repair_count": 0,
        "start_time": time.time()
    }
```

## Complete AI Engineering Loop

### 1. Entry Point: `run()` Method
**File:** `src/ai/orchestrator.py` lines 226-310  
**Method:** `Orchestrator.run(user_prompt: str) -> Optional[DesignProject]`

#### Phase 1: Requirements Extraction
1. Log user prompt: `self._log_trace("USER_PROMPT", user_prompt)`
2. Prepare requirement extraction messages:
   ```python
   req_messages = [
       {"role": "system", "content": "You are a requirements analyst. Extract the structured requirements from the user's request. Identify inputs, outputs, thresholds, and any ambiguities. CRITICAL: If a threshold is mentioned but no numeric value is provided (e.g., 'crosses a threshold'), you MUST record it in ambiguities as 'Unspecified numeric threshold'."},
       {"role": "user", "content": user_prompt}
   ]
   ```
3. Call provider for structured requirements:
   ```python
   self.metrics["model_call_count"] += 1
   requirements: ProjectRequirements = self.provider.structured_generate(req_messages, ProjectRequirements)
   ```
4. Log extraction results: `self._log_trace("REQUIREMENTS_EXTRACTED", requirements.model_dump())`
5. Handle extraction failures with fallback ProjectRequirements
6. Handle case where only ambiguities exist (continue anyway)
7. Build initial conversation history:
   ```python
   self.history.append({"role": "user", "content": user_prompt})
   self.history.append({
       "role": "assistant", 
       "content": f"I have extracted the following project requirements:\n```json\n{req_str}\n```\nI will use these requirements to propose a valid design."
   })
   self.history.append({
       "role": "user",
       "content": "Please proceed. Use the available tools to explore components and confirm your approach before proposing the final design."
   })
   ```
8. Set state: `self.state = AgentState.PROPOSING`
9. Get tool definitions: `tools = self._get_tools()`

#### Phase 2: Tool Exploration Loop (Lines 271-305)
**Process:** Up to 10 iterations of:
1. **Early Termination Check**: 
   ```python
   if self.state == AgentState.CLARIFICATION_REQUIRED:
       return None
   ```
2. **Model Call for Tool Usage**:
   ```python
   self.metrics["model_call_count"] += 1
   message = self.provider.tool_call(self.history, tools=tools)
   self.history.append(message)
   ```
3. **Tool Execution** (if tool calls present):
   ```python
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
   ```
4. **Break Condition**: Exit loop if no tool calls (proceed to proposal)

#### Phase 3: Proposal and Repair Loop (Lines 312-394)
**Method:** `_propose_and_repair_loop() -> Optional[DesignProject]`

1. **History Preparation** (Gemini-specific workaround):
   ```python
   # Ensure we don't send a history ending in an assistant turn, which causes Gemini to throw 400 INVALID_ARGUMENT
   if self.history and self.history[-1]["role"] == "assistant":
       self.history.append({
           "role": "user",
           "content": "Please generate the final proposed DesignProject using the tools and logic rules discussed."
       })
   ```

2. **Main Loop** (while attempts ≤ max_repair_attempts):
   - Set state: PROPOSING (attempt=0) or REPAIRING (attempt>0)
   
   **Design Generation**:
   ```python
   try:
       self._log_trace("PROPOSAL_REQUESTED", {"attempt": attempts})
       self.metrics["model_call_count"] += 1
       design: DesignProject = self.provider.structured_generate(self.history, DesignProject)
   except Exception as e:
       self.history.append({
           "role": "user",
           "content": f"Failed to parse structured output: {str(e)}. Please try again."
       })
       attempts += 1
       continue
   ```
   
   - Log proposed design: `self._log_trace("PROPOSED_DESIGN", design.model_dump())`
   
   **Validation**:
   ```python
   self.state = AgentState.VALIDATING
   validation_result = validate_design(design)
   self._log_trace("VALIDATION_RESULT", validation_result.model_dump())
   
   if validation_result.status == ValidationStatus.PASS:
       self.state = AgentState.COMPLETED
       return design
   ```
   
   **Repair Process** (if validation fails):
   ```python
   # Must repair
   self.metrics["repair_count"] += 1
   self.history.append({
       "role": "assistant",
       "content": f"Proposed design ID: {design.project_id}"
   })
   
   error_message = json.dumps(validation_result.model_dump(), indent=2)
   self.history.append({
       "role": "user",
       "content": f"Validation failed with the following errors. You MUST repair the design to resolve these errors:\n\n{error_message}"
   })
   
   # Allow up to 3 tool calls for repair exploration
   tools = self._get_tools()
   for _ in range(3):
       self.metrics["model_call_count"] += 1
       message = self.provider.tool_call(self.history, tools=tools)
       if not message.get("tool_calls"):
           # Handle empty message
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
   ```
   
3. **Failure Handling** (if max attempts exceeded):
   ```python
   self.state = AgentState.FAILED
   self._log_trace("FAILED", {"reason": "MAX_REPAIR_ATTEMPTS_EXCEEDED"})
   return None
   ```

## Key Internal Methods

### 1. `_log_trace()` Method (Lines 67-74)
```python
def _log_trace(self, event: str, data: Any) -> None:
    self.traces.append({
        "timestamp": time.time(),
        "event": event,
        "data": data
    })
    if hasattr(self, "verbose_callback") and self.verbose_callback:
        self.verbose_callback(event, data)
```
- Records timestamped events for debugging and monitoring
- Supports optional verbose callback for real-time tracing

### 2. `_get_tools()` Method (Lines 76-159)
Returns list of tool definitions in OpenAI format:
```python
[
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
                    "design": DesignProject.resolved_schema()
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
```

### 3. `_execute_tool()` Method (Lines 161-224)
Executes tools and returns JSON string results:
```python
def _execute_tool(self, name: str, args: dict) -> str:
    self.metrics["tool_call_count"] += 1
    self.metrics["tool_calls_by_name"][name] = self.metrics["tool_calls_by_name"].get(name, 0) + 1
    
    # Check cache for read-only tools
    cache_key = None
    if name in ("search_components", "get_component", "search_curriculum"):
        cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
        if cache_key in self._tool_cache:
            self.metrics["cache_hits"] += 1
            return self._tool_cache[cache_key]
    
    self.metrics["cache_misses"] += 1
    
    try:
        result_str = ""
        if name == "search_components":
            results = search_components(args["query"])
            result_str = json.dumps([r.model_dump() for r in results])
        elif name == "get_component":
            comp = get_component(args["component_id"])
            result_str = json.dumps(comp.model_dump()) if comp else json.dumps({"error": "Component not found"})
        elif name == "search_curriculum":
            results = search_curriculum(args["query"])
            result_str = json.dumps([r.model_dump() for r in results])
        elif name == "calculate_led_resistor":
            from validation.calculations import calculate_led_resistor
            res = calculate_led_resistor(args["supply_voltage"], args["forward_voltage"], args["target_current_ma"])
            result_str = json.dumps(res.model_dump())
        elif name == "validate_design":
            from core.models import DesignProject
            from ai.tools import validate_design
            from core.enums import ValidationStatus
            provisional_design = DesignProject.model_validate(args["design"])
            
            # Cache based on serialized design to skip redundant validation
            design_hash = json.dumps(provisional_design.model_dump(), sort_keys=True)
            val_cache_key = f"validate_design:{design_hash}"
            if val_cache_key in self._tool_cache:
                val_res_dict = json.loads(self._tool_cache[val_cache_key])
                # Re-hydrate if needed, or just return the string
                if val_res_dict.get("status") == ValidationStatus.PASS.value:
                    self._validated_design = provisional_design
                return self._tool_cache[val_cache_key]
            
            self.metrics["validation_call_count"] += 1
            val_res = validate_design(provisional_design)
            if val_res.status == ValidationStatus.PASS:
                self._validated_design = provisional_design
            result_str = json.dumps(val_res.model_dump())
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
```

## Agent State Management

**File:** `src/ai/orchestrator.py` lines 16-24
```python
class AgentState(str, Enum):
    RUNNING = "RUNNING"
    PROPOSING = "PROPOSING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
```

### State Transitions
1. **RUNNING**: Initial state after construction
2. **PROPOSING**: 
   - During requirement processing (before tool loop)
   - During proposal generation (attempt=0 in repair loop)
3. **TOOL_USAGE**: Implicit during tool execution (not explicitly tracked as state)
4. **VALIDATING**: After proposal generation, before checking results
5. **REPAIRING**: During validation failure handling (attempt>0)
6. **COMPLETED**: When validation passes
7. **FAILED**: When max repair attempts exceeded
8. **CLARIFICATION_REQUIRED**: When unsupported component or ambiguous intent detected

## Caching Mechanisms

### 1. Tool Result Cache (`_tool_cache`)
- **Key**: `f"{tool_name}:{json.dumps(args, sort_keys=True)}"`
- **Used For**: search_components, get_component, search_curriculum (read-only tools)
- **Purpose**: Avoid redundant tool calls for identical inputs
- **Metrics**: Tracks `cache_hits` and `cache_misses`

### 2. Validation Cache
- **Key**: `f"validate_design:{design_hash}"` where `design_hash = json.dumps(provisional_design.model_dump(), sort_keys=True)`
- **Purpose**: Skip redundant validation of identical designs
- **Special Handling**: If cached result shows PASS, sets `self._validated_design`

## Metrics and Tracing

### Metrics Tracked
- `model_call_count`: Number of calls to provider methods
- `tool_call_count`: Number of tool executions
- `tool_calls_by_name`: Count per tool name
- `cache_hits`/`cache_misses`: Tool cache effectiveness
- `validation_call_count`: Number of validation runs
- `repair_count`: Number of repair attempts
- `start_time`/`elapsed_time`: Timing information

### Traces Recorded
Each trace entry contains:
- `timestamp`: Time of event
- `event`: String identifier (USER_PROMPT, REQUIREMENTS_EXTRACTED, TOOL_CALL, VALIDATION_RESULT, PROPOSAL_REQUESTED, COMPLETED, FAILED, CLARIFICATION_REQUIRED)
- `data`: Event-specific data

## Provider Interaction Patterns

### 1. Requirements Extraction
- Uses `provider.structured_generate()` with `ProjectRequirements` schema
- System prompt emphasizes unambiguous requirement extraction

### 2. Tool Usage Loop
- Uses `provider.tool_call()` with conversation history and tool definitions
- Expects OpenAI-compatible tool call format in response
- Processes tool calls sequentially, updating history with results

### 3. Design Proposal
- Uses `provider.structured_generate()` with `DesignProject` schema
- Expects complete DesignProject instance in response
- Relies on provider to use conversation history for context

### 4. Provider-Specific Workarounds
**Gemini-Specific** (lines 315-320):
```python
# Ensure we don't send a history ending in an assistant turn, which causes Gemini to throw 400 INVALID_ARGUMENT
if self.history and self.history[-1]["role"] == "assistant":
    self.history.append({
        "role": "user",
        "content": "Please generate the final proposed DesignProject using the tools and logic rules discussed."
    })
```
- History manipulation to satisfy Gemini API requirements
- Leaks provider-specific knowledge into orchestrator

## Termination Conditions

### Success Conditions
1. **Validation Pass**: `validation_result.status == ValidationStatus.PASS`
   - Sets state to COMPLETED
   - Returns validated design
   - Records completion trace with metrics

### Failure Conditions
1. **Max Repair Attempts Exceeded**: `attempts > self.max_repair_attempts`
   - Sets state to FAILED
   - Returns None
   - Records failure trace

2. **Clarification Required**: `self.state == AgentState.CLARIFICATION_REQUIRED`
   - Can be triggered by:
     - Requirements extraction failure
     - `request_clarification` tool call
   - Returns None immediately

3. **Extraction Failure**: Provider failure during structured generation
   - Falls back to basic ProjectRequirements
   - Continues processing (may succeed despite extraction issues)

## Dependencies and Coupling

### Internal Dependencies
- **Components**: `from components.registry import get_default_registry, search_components, get_component`
- **Curriculum**: `from curriculum.store import get_default_curriculum, search_curriculum`
- **Validation**: `from validation.engine import DesignValidator`, `from validation.calculations import calculate_led_resistor`
- **Models**: `from core.models import DesignProject, ProjectRequirements`
- **AI Tools**: `from ai.tools import validate_design`

### External Dependencies
- **Provider**: Abstract `ModelProvider` interface (dependency injection)
- **Standard Library**: `json`, `time`, `typing`, `pathlib`

### Provider-Specific Coupling Issues
1. **History Manipulation**: Gemini-specific workaround in `_propose_and_repair_loop()`
2. **Provider Selection Logic**: Conditional imports in CLI (not in orchestrator itself, but affects usage)
3. **Tool Format Assumptions**: Expects OpenAI tool call format specifically
4. **Schema Assumptions**: Uses `DesignProject.resolved_schema()` for validation tool

## Orchestration Quality Assessment

### Strengths
1. **Clear Separation of Concerns**: 
   - Distinct phases: requirements, exploration, proposal/repair
   - Clean interface with provider abstraction
   - Deterministic validation completely separated

2. **Robust Error Handling**:
   - Graceful degradation on requirement extraction failure
   - Tool execution error handling
   - Validation caching to prevent redundant work

3. **Effective Repair Loop**:
   - Specific error feedback to guide repairs
   - Limited tool usage during repair to prevent infinite loops
   - Tracking of repair attempts

4. **Comprehensive Tracing and Metrics**:
   - Detailed event tracing for debugging
   - Performance metrics for optimization
   - Verbose callback support for real-time monitoring

5. **State Management**:
   - Clear state transitions
   - Proper handling of edge cases (clarification, failure)

### Weaknesses and Coupling Issues
1. **Provider-Specific Leak**: Gemini history manipulation violates abstraction
2. **Tool Definition Duplication**: Tools defined in orchestrator rather than shared
3. **History Format Assumptions**: Assumes specific conversation history format
4. **Caching Complexity**: Dual caching mechanisms increase complexity
5. **Magic Numbers**: Hard-coded limits (10 exploration attempts, 3 repair tool calls)

### Evidence of Coupling
From lines 315-320:
```python
# Ensure we don't send a history ending in an assistant turn, which causes Gemini to throw 400 INVALID_ARGUMENT
if self.history and self.history[-1]["role"] == "assistant":
    self.history.append({
        "role": "user",
        "content": "Please generate the final proposed DesignProject using the tools and logic rules discussed."
    })
```
This comment explicitly acknowledges the provider-specific nature of this workaround.

## Integration with CLI

**File:** `src/cli/main.py` lines 229-298  
**Function:** `run_agent()`

### CLI-Specific Orchestrator Usage
1. **Provider Selection** (lines 240-250):
   ```python
   if mock:
       # Uses MockRepairProvider from tests
   elif "gemini" in model.lower():
       from ai.provider_gemini import RESTGeminiProvider
       provider = RESTGeminiProvider(model_name=model)
   else:
       from ai.provider_openai import RESTOpenAIProvider
       provider = RESTOpenAIProvider(model_name=model)
   ```
   
2. **Orchestrator Creation** (line 252):
   ```python
   orchestrator = Orchestrator(provider, max_repair_attempts=max_repair_attempts)
   ```
   
3. **Verbose Callback Setup** (lines 254-271):
   ```python
   if verbose:
       def verbose_cb(event, data):
           # Handle different event types for display
       orchestrator.verbose_callback = verbose_cb
   ```
   
4. **Execution and Result Handling** (lines 273-298):
   ```python
   try:
       final_design = orchestrator.run(prompt)
   except Exception as e:
       typer.echo(f"Agent failed with error: {str(e)}")
       final_design = None
       
   typer.echo(f"\nFinal State: {orchestrator.state.value}")
   if final_design:
       typer.echo(f"Resulting Design Project ID: {final_design.project_id}")
       typer.echo(f"Valid Components: {len(final_design.components)}")
       typer.echo(f"Valid Nets: {len(final_design.nets)}")
   else:
       typer.echo("No valid design produced.")
   ```
   
5. **Trace Saving** (lines 289-298):
   ```python
   timestamp = int(time.time())
   run_dir = Path(f"runs/{timestamp}")
   run_dir.mkdir(parents=True, exist_ok=True)
   trace_path = run_dir / "trace.json"
   
   with open(trace_path, "w", encoding="utf-8") as f:
       json.dump(orchestrator.traces, f, indent=2)
   
   typer.echo(f"\nSaved trace to {trace_path}")
   
   if orchestrator.state != "COMPLETED":
       typer.Exit(code=1)
   ```

## Summary

The orchestrator implements a sophisticated AI engineering loop that effectively balances AI creativity with deterministic validation. Key strengths include:

1. **Clear Phase Separation**: Requirements → Exploration → Proposal/Repair
2. **Deterministic Safety Net**: Validation layer prevents AI hallucination from affecting correctness
3. **Intelligent Repair Loop**: Specific error feedback guides corrections rather than blind regeneration
4. **Comprehensive Instrumentation**: Tracing, metrics, and verbose output for monitoring
5. **Provider Agnostic Core**: Main logic depends only on ModelProvider abstraction

The primary areas for improvement relate to provider-specific coupling:
1. Remove Gemini-specific history manipulation from orchestrator
2. Centralize tool definitions to avoid duplication
3. Consider making history format more provider-agnostic
4. Extract caching mechanisms into reusable components

Despite these minor coupling issues, the orchestrator successfully implements the "AI Proposes, Determinism Disposes" philosophy and provides a solid foundation for adding new providers like Claude.