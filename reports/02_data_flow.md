# Data Flow Trace: Illustration Engine Request Processing

This document traces a complete request through the Illustration Engine system, from CLI input to final validated DesignProject output.

## Complete Request Flow

### 1. CLI Input → Orchestrator Initialization
**File:** `src/cli/main.py`  
**Function:** `run_agent()` in `agent_app.command("run")`  
**Process:**
- User runs: `illustration-engine agent run "Blink an LED on GPIO19"`
- CLI parses arguments (prompt, model, mock flag, etc.)
- Initializes provider based on flags:
  - If `mock`: Uses `MockRepairProvider` (from tests)
  - If `gemini` in model: Uses `RESTGeminiProvider`
  - Else: Uses `RESTOpenAIProvider`
- Creates `Orchestrator(provider, max_repair_attempts)` instance

### 2. Requirements Extraction Phase
**File:** `src/ai/orchestrator.py`  
**Method:** `Orchestrator.run()`  
**Process:**
1. `_log_trace("USER_PROMPT", user_prompt)`
2. Construct requirement extraction messages:
   ```python
   req_messages = [
       {"role": "system", "content": "You are a requirements analyst. Extract the structured requirements from the user's request..."},
       {"role": "user", "content": user_prompt}
   ]
   ```
3. Call provider for structured requirements:
   ```python
   self.metrics["model_call_count"] += 1
   requirements: ProjectRequirements = self.provider.structured_generate(req_messages, ProjectRequirements)
   ```
   - Uses `ProjectRequirements` schema from `ai.models.py` (imported locally)
   - This calls the provider's `structured_generate` method

### 3. Provider Structured Generation
**Files:** 
- `src/ai/provider_gemini.py` (if Gemini selected)
- `src/ai/provider_openai.py` (if OpenAI selected)
**Method:** `structured_generate()`
**Process:**
1. Convert OpenAI-style messages to provider format:
   - `_convert_messages()` transforms message roles/content
   - Handles system/user/assistant/tool roles appropriately
2. Convert Pydantic schema to provider-compatible format:
   - `_sanitize_schema()` removes unsupported JSON Schema keys
   - Flattens anyOf/allOf, infers missing types
3. Configure tool calling for structured output:
   - Creates a tool that wraps the target schema
   - Uses toolConfig to force structured output submission
4. Make API call via `_post()`
5. Parse response:
   - Extract function call arguments or parse JSON from text response
   - Validate against target Pydantic schema using `model_validate()`

### 4. Requirements Processing → History Setup
**File:** `src/ai/orchestrator.py`  
**Method:** `Orchestrator.run()` (continued)
**Process:**
1. Log requirements extraction: `_log_trace("REQUIREMENTS_EXTRACTED", requirements.model_dump())`
2. Handle extraction failures with fallback
3. Build conversation history:
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
4. Set state: `self.state = AgentState.PROPOSING`
5. Get tool definitions: `tools = self._get_tools()`

### 5. Tool Exploration Loop (Reasoning Phase)
**File:** `src/ai/orchestrator.py`  
**Method:** `Orchestrator.run()` (exploration loop)
**Process:** (Loop up to 10 iterations)
1. Check for early termination: `if self.state == AgentState.CLARIFICATION_REQUIRED: return None`
2. Increment model call counter
3. Get tool calls from provider: `message = self.provider.tool_call(self.history, tools=tools)`
4. Append assistant message to history
5. If tool calls present:
   - For each tool call:
     - Execute tool via `_execute_tool(name, args)`
     - Log trace: `_log_trace("TOOL_CALL", {"tool": name, "args": args, "result": result_str})`
     - Append tool result to history as `{"role": "tool", ...}`
     - Check if validated design found: `if self._validated_design is not None: return design`
6. Break loop if no tool calls (proceed to proposal)

### 6. Tool Execution Details
**File:** `src/ai/orchestrator.py`  
**Method:** `_execute_tool(name: str, args: dict) -> str`
**Implemented Tools:**
- `search_components`: 
  - Calls `search_components(args["query"])` from `ai.tools.py`
  - Returns JSON string of matching ComponentType objects
  - Cached for read-only tools
- `get_component`:
  - Calls `get_component(args["component_id"])` from `ai.tools.py`
  - Returns JSON string of single ComponentType or error
- `search_curriculum`:
  - Calls `search_curriculum(args["query"])` from `ai.tools.py`
  - Returns JSON string of matching curriculum concepts
- `calculate_led_resistor`:
  - Imports and calls `calculate_led_resistor()` from `validation.calculations`
  - Returns JSON string of ResistorCalculation
- `validate_design`:
  - Imports `DesignProject` and `validate_design` from respective modules
  - Validates provisional design, caches result
  - Sets `self._validated_design` if validation passes
- `request_clarification`:
  - Sets state to `CLARIFICATION_REQUIRED`
  - Logs trace and returns JSON indicating clarification needed

**File:** `src/ai/tools.py`  
**Functions:**
- `search_components(query: str) -> list[ComponentType]`
- `get_component(component_id: str) -> Optional[ComponentType]`
- `search_curriculum(query: str) -> list[Concept]`
- `validate_design(design: DesignProject) -> ValidationResult`

### 7. Design Proposal and Repair Loop
**File:** `src/ai/orchestrator.py`  
**Method:** `_propose_and_repair_loop() -> Optional[DesignProject]`
**Process:** (While attempts ≤ max_repair_attempts)
1. Ensure history doesn't end with assistant turn (Gemini requirement)
2. Set state: PROPOSING (attempt=0) or REPAIRING (attempt>0)
3. Generate structured design proposal:
   ```python
   design: DesignProject = self.provider.structured_generate(self.history, DesignProject)
   ```
4. Log proposed design: `_log_trace("PROPOSED_DESIGN", design.model_dump())`
5. Set state to VALIDATING
6. Run validation: `validation_result = validate_design(design)`
7. Log validation result: `_log_trace("VALIDATION_RESULT", validation_result.model_dump())`
8. If validation passes (status=PASS):
   - Set state to COMPLETED
   - Return the validated design
9. If validation fails:
   - Increment repair counter
   - Add proposed design ID to history
   - Add validation errors to history as user message
   - Allow up to 3 tool calls for repair exploration
   - Check if validated design found during repair
   - Increment attempt counter
10. If max attempts exceeded:
    - Set state to FAILED
    - Log failure trace
    - Return None

### 8. Final Output
**File:** `src/cli/main.py`  
**Function:** `run_agent()` (continued)
**Process:**
- Receive final design from orchestrator.run()
- Display final state: `typer.echo(f"\nFinal State: {orchestrator.state.value}")`
- If design exists:
  - Show project ID, component count, net count
- Else: Show "No valid design produced."
- Save traces to `runs/{timestamp}/trace.json`
- Exit with code 1 if not COMPLETED state

## Key Data Structures in Flow

### Conversation History
- List of dictionaries with `role` and `content`
- Roles: "system", "user", "assistant", "tool"
- Tool messages include: `tool_call_id`, `name`, `content` (JSON string)
- Used for context in all provider calls

### Tool Call Structure
From provider implementations:
```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    {
      "id": "call_xyz",
      "type": "function",
      "function": {
        "name": "tool_name",
        "arguments": "{\"param\": \"value\"}"
      }
    }
  ]
}
```

### Tool Result Structure
- JSON string returned from `_execute_tool`
- Becomes the `content` field in history entries with `role: "tool"`

### DesignProject Flow
1. Created via `provider.structured_generate(history, DesignProject)`
2. Passed to `validate_design(design)` function
3. If valid, returned as final output
4. If invalid, error messages added to history for repair attempt

## Provider-Specific Notes

### Gemini Provider Specifics
- Requires history to not end with assistant turn (400 INVALID_ARGUMENT)
- Uses function calling with `submit_structured_output` for structured generation
- Converts between OpenAI and Gemini message formats extensively
- Requires schema sanitization for Gemini Function Declarations

### Common Flow Points
- All providers must implement the `ModelProvider` interface
- Orchestrator depends only on the abstract interface
- Tool execution is provider-agnostic (same `_execute_tool` used)
- Validation and calculations are completely separate from AI layer

## Summary of Key Files in Flow
1. `src/cli/main.py` - CLI entry point
2. `src/ai/orchestrator.py` - Main orchestration logic
3. `src/ai/provider_*.py` - Provider implementations (Gemini/OpenAI)
4. `src/ai/tools.py` - Tool implementations
5. `src/validation/engine.py` - Deterministic validation
6. `src/validation/calculations.py` - LED resistor calculation
7. `src/core/models.py` - DesignProject and related Pydantic models