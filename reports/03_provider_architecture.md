# Provider Architecture: Illustration Engine AI Provider Abstraction

This document examines the ModelProvider abstraction and its implementations in detail.

## ModelProvider Interface

**File:** `src/ai/provider.py`  
**Class:** `ModelProvider` (Abstract Base Class)

### Interface Methods

```python
from abc import ABC, abstractmethod
from typing import Type, Optional, Generator, Any
from pydantic import BaseModel

class ModelProvider(ABC):
    """Abstract base class for AI model providers.
    
    The rest of the application MUST NOT depend directly on any
    specific AI vendor's SDK. All LLM interactions go through this interface.
    """
    
    @abstractmethod
    def generate(self, messages: list[dict], context: Optional[dict] = None) -> str:
        """Generate a text response from the model.
        messages should be a list of dicts with 'role' and 'content' keys.
        """
        ...
    
    @abstractmethod
    def structured_generate(self, messages: list[dict], schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
        """Generate a response that conforms to a Pydantic schema."""
        ...
    
    @abstractmethod
    def tool_call(self, messages: list[dict], tools: list[dict], context: Optional[dict] = None) -> Any:
        """Generate tool calls or a final response based on the conversation history."""
        ...
```

### Key Contract Notes:
1. **Message Format**: Expects OpenAI-style messages `[{"role": "system|user|assistant|tool", "content": str}]`
2. **Structured Generation**: Must return a Pydantic model instance matching the provided schema
3. **Tool Calling**: Must return a format compatible with OpenAI tool calls when tools are provided
4. **Context Parameter**: Optional context for provider-specific configuration
5. **SDK Independence**: Explicitly states application must not depend on vendor SDKs

## MockModelProvider Implementation

**File:** `src/ai/provider.py`  
**Class:** `MockModelProvider`

### Purpose:
- Enables full offline testing without API keys or network
- Returns deterministic, pre-configured responses
- Used in unit tests and CI/CD

### Key Methods:

```python
def __init__(self):
    self._responses: dict[str, str] = {}          # key -> text response
    self._structured_responses: dict[str, BaseModel] = {}  # key -> model instance

def set_response(self, prompt_contains: str, response: str) -> None:
    """Configure a response for prompts containing the given substring."""
    self._responses[prompt_contains.lower()] = response

def set_structured_response(self, prompt_contains: str, response: BaseModel) -> None:
    """Configure a structured response for prompts containing the given substring."""
    self._structured_responses[prompt_contains.lower()] = response

def _extract_prompt(self, messages: list[dict]) -> str:
    """Extracts the user prompt from messages (last message content)."""
    if not messages:
        return ""
    return str(messages[-1].get("content", ""))

def generate(self, messages: list[dict], context: Optional[dict] = None) -> str:
    prompt_lower = self._extract_prompt(messages).lower()
    for key, response in self._responses.items():
        if key in prompt_lower:
            return response
    return "[MockModelProvider] No configured response for this prompt."

def structured_generate(self, messages: list[dict], schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
    prompt_lower = self._extract_prompt(messages).lower()
    for key, response in self._structured_responses.items():
        if key in prompt_lower:
            if isinstance(response, schema):
                return response
    raise ValueError(f"[MockModelProvider] No configured structured response matching schema {schema.__name__}")

def tool_call(self, messages: list[dict], tools: list[dict], context: Optional[dict] = None) -> Any:
    return {"role": "assistant", "content": None}  # Mock returns no tool calls by default
```

### Notable Characteristics:
- Simple substring matching for response selection
- No tool call simulation (always returns no tool calls)
- Used extensively in test fixtures via `set_response`/`set_structured_response`

## RESTGeminiProvider Implementation

**File:** `src/ai/provider_gemini.py`  
**Class:** `RESTGeminiProvider`

### Constructor:
```python
def __init__(self, model_name: str = "gemini-1.5-flash", api_key: Optional[str] = None):
    self.model_name = model_name
    self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not self.api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    self.base_url = "https://generativelanguage.googleapis.com/v1beta"
```

### Core Implementation Details:

#### 1. Message Conversion (`_convert_messages`)
**Purpose:** Convert OpenAI-style messages to Gemini format

**Key Logic:**
- Handles system messages by creating `systemInstruction`
- Merges consecutive user/model turns (Gemini forbids consecutive model turns)
- Processes tool calls and tool responses:
  - Tool calls: Converts to Gemini's `functionCall` format
  - Tool responses: Converts to Gemini's `functionResponse` format
- Preserves tool call IDs when not auto-generated

**Complexity Areas:**
- Role mapping: user→user, assistant→model, tool→user (with functionResponse)
- Handling of `raw_parts` for tool calls
- Merging logic to avoid consecutive model turns

#### 2. Schema Sanitization (`_sanitize_schema`)
**Purpose:** Strip unsupported JSON Schema keys for Gemini Function Declarations

**Key Logic:**
- Flattens `anyOf` and `allOf` constructs
- Preserves only supported keys: `["type", "description", "properties", "items", "required", "enum", "format"]`
- Infers missing types when shape is obvious (properties→object, items→array)
- Recursively processes nested schemas

#### 3. Tool Conversion (`_convert_tools`)
**Purpose:** Convert OpenAI-style tools to Gemini format

**Key Logic:**
- Extracts function name, description, and parameters
- Sanitizes parameters schema via `_sanitize_schema`
- Wraps in Gemini's `functionDeclarations` format

#### 4. HTTP Communication (`_post`)
**Purpose:** Make REST API calls to Gemini endpoint

**Key Logic:**
- Constructs URL: `https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}`
- Sends JSON payload with proper headers
- Handles HTTP errors with detailed error messages

#### 5. Text Generation (`generate`)
**Process:**
1. Convert messages via `_convert_messages`
2. Build payload with contents and generationConfig (temperature=0.2)
3. Add systemInstruction if present
4. POST to Gemini endpoint
5. Extract text from `result["candidates"][0]["content"]["parts"][0]["text"]`

#### 6. Structured Generation (`structured_generate`)
**Process:**
1. Convert messages and schema
2. Build payload with:
   - contents (converted messages)
   - tools: Single function declaration `submit_structured_output` with sanitized schema
   - toolConfig: Force ANY mode with allowedFunctionNames=["submit_structured_output"]
   - generationConfig: temperature=0.2
3. POST to Gemini endpoint
4. Parse response:
   - Extract functionCall arguments from `result["candidates"][0]["content"]["parts"][0]`
   - Parse JSON text response as fallback
   - Validate against target schema using `schema.model_validate(args)`

#### 7. Tool Calling (`tool_call`)
**Process:**
1. Convert messages and tools
2. Build payload with contents, tools, and generationConfig
3. POST to Gemini endpoint
4. Parse response:
   - Extract functionCall(s) from parts
   - Convert back to OpenAI format for orchestrator compatibility:
     ```json
     {
       "role": "assistant",
       "content": null,
       "tool_calls": [
         {
           "id": fc.get("id", "call_" + fc["name"]),
           "type": "function",
           "function": {
             "name": fc["name"],
             "arguments": json.dumps(fc.get("args", {}))
           }
         }
       ],
       "raw_parts": all_parts  // Preserve for conversation history
     }
     ```
   - Return text content if no tool calls

## RESTOpenAIProvider Implementation

**File:** `src/ai/provider_openai.py`  
**Class:** `RESTOpenAIProvider`

### Constructor:
```python
def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None):
    self.model_name = model_name
    self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not self.api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
```

### Key Differences from Gemini Provider:

#### 1. Message Handling
- Pass-through: No conversion needed (OpenAI uses same format as interface)
- No system message merging complexity
- Tool calls and responses passed through unchanged

#### 2. Schema Handling
- No sanitization needed (OpenAI supports full JSON Schema)
- Direct use of `schema.model_json_schema()`

#### 3. Tool Calling
- Direct passthrough: OpenAI tools format matches interface expectation
- No conversion needed in `_convert_tools`

#### 4. Structured Generation Approach
Two strategies visible in code:
- **Function Calling**: Uses `tools` with `function_calling` config (like Gemini)
- **JSON Mode**: Alternative approach using `response_format: {"type": "json_object"}`
- Current implementation appears to use function calling approach

#### 5. HTTP Endpoint
- Different URL: `https://api.openai.com/v1/chat/completions`
- Different headers: `Authorization: Bearer {api_key}`

## Provider-Specific Orchestration Dependencies

**File:** `src/ai/orchestrator.py`  
**Key Dependencies:**

### 1. Provider Instantiation (CLI)
**Location:** `src/cli/main.py:run_agent()`
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
**Issue:** Direct conditional imports create tight coupling to specific provider implementations

### 2. Gemini-Specific Workaround
**Location:** `src/ai/orchestrator.py:_propose_and_repair_loop()`
```python
# Ensure we don't send a history ending in an assistant turn, which causes Gemini to throw 400 INVALID_ARGUMENT
if self.history and self.history[-1]["role"] == "assistant":
    self.history.append({
        "role": "user",
        "content": "Please generate the final proposed DesignProject using the tools and logic rules discussed."
    })
```
**Issue:** History manipulation is provider-specific (Gemini-only requirement) leaked into orchestrator logic

### 3. Validation Caching Key
**Location:** `src/ai/orchestrator.py:_execute_tool()`
```python
# Cache based on serialized design to skip redundant validation
design_hash = json.dumps(provisional_design.model_dump(), sort_keys=True)
val_cache_key = f"validate_design:{design_hash}"
```
**Note:** This is provider-agnostic but shows caching strategy

## Tool-Calling Assumptions

### Interface Expectation (from ModelProvider.tool_call):
```python
def tool_call(self, messages: list[dict], tools: list[dict], context: Optional[dict] = None) -> Any:
    """Generate tool calls or a final response based on the conversation history."""
    ...
```

### Expected Return Format:
Orchestrator expects OpenAI-compatible format:
```json
{
  "role": "assistant",
  "content": null|str,
  "tool_calls": [
    {
      "id": "call_id",
      "type": "function",
      "function": {
        "name": "tool_name",
        "arguments": "{\"param\": \"value\"}"
      }
    }
  ],
  "raw_parts": [...]  // Optional but used by Gemini
}
```

### Provider Implementations:
- **Mock**: Returns `{"role": "assistant", "content": None}` (no tool calls)
- **Gemini**: Converts internal format to OpenAI format, preserves `raw_parts`
- **OpenAI**: Passes through OpenAI format directly

## Structured-Output Assumptions

### Interface Expectation:
```python
def structured_generate(self, messages: list[dict], schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
    """Generate a response that conforms to a Pydantic schema."""
    ...
```

### Provider Implementations:
- **Mock**: Matches response by substring, validates isinstance
- **Gemini**: 
  - Uses function calling with `submit_structured_output` tool
  - Sanitizes schema for Gemini Function Declarations
  - Parses function call arguments or JSON text response
  - Uses `schema.model_validate()` for validation
- **OpenAI**: Similar approach (implementation in provider_openai.py)

### Key Requirement:
Providers must return a valid Pydantic model instance, not raw data

## Conversation/History Assumptions

### Format Expectation:
All providers expect: `list[dict]` where each dict has:
- `"role"`: "system" | "user" | "assistant" | "tool"
- `"content"`: str (message content)
- Optional for assistant with tool calls: `"tool_calls"`: list[dict]
- Optional for tool messages: `"tool_call_id"`: str, `"name"`: str

### Provider-Specific Handling:
- **Mock**: Uses `_extract_prompt()` to get last user message content
- **Gemini**: 
  - Full conversion via `_convert_messages()`
  - Handles role mapping, turn merging, tool call/response conversion
  - Preserves `raw_parts` in assistant messages when tool calls present
- **OpenAI**: 
  - Minimal processing (mostly pass-through)
  - Some implementations may add `raw_parts` for consistency

## What Must Change to Add Claude Cleanly

### 1. Create New Provider Implementation
**File:** `src/ai/provider_claude.py`
**Class:** `RESTClaudeProvider` implementing `ModelProvider`

### 2. Must Implement All Three Methods:
- `generate()`: Text generation
- `structured_generate()`: Pydantic model generation  
- `tool_call()`: Tool call handling

### 3. Key Implementation Considerations:
#### Message Format:
- Determine Claude's message format expectations
- Implement conversion if different from OpenAI format
- Handle system messages, tool calls, tool responses appropriately

#### Structured Output:
- Claude may support JSON mode, tool use, or both
- Implement appropriate schema adaptation
- May need schema sanitization if Claude has restrictions

#### Tool Calling:
- Determine Claude's tool call format
- Implement conversion to/from OpenAI format if needed
- Handle tool call ID generation/preservation

#### HTTP Integration:
- Configure Anthropic API endpoint
- Handle authentication (likely Bearer token)
- Implement error handling and response parsing

### 4. Update Provider Selection Logic
**File:** `src/cli/main.py:run_agent()`
Add Claude detection:
```python
elif "claude" in model.lower():
    from ai.provider_claude import RESTClaudeProvider
    provider = RESTClaudeProvider(model_name=model)
```

### 5. Address Provider-Specific Orchestrator Coupling
**Issues to Fix:**
1. Remove Gemini-specific history manipulation from orchestrator
2. Move provider instantiation to factory pattern or dependency injection
3. Consider making history formatting provider-agnostic

### 6. Test Integration
- Add Claude provider tests similar to test_provider.py
- Configure API key handling in test environment
- Verify structured output and tool call functionality

## Summary of Provider Architecture Strengths

1. **Clean Abstraction**: ModelProvider ABC defines clear interface
2. **SDK Independence**: No direct vendor SDK dependencies in core logic
3. **Mock Capability**: Full offline testing enabled
4. **Extensible Design**: New providers can be added by implementing ABC
5. **Dual Implementation Proof**: Gemini and OpenAI show the pattern works

## Summary of Provider Architecture Weaknesses

1. **Provider-Specific Leaks**: Gemini-specific history manipulation in orchestrator
2. **Conditional Imports**: Direct provider imports in CLI create coupling
3. **Tool Format Assumptions**: Orchestrator expects OpenAI tool format specifically
4. **Schema Sanitization Duplication**: Each provider may need similar sanitization logic
5. **Error Handling Variation**: Different providers may have different error response formats

## Recommended Improvements for Claude Integration

1. **Refactor Orchestrator**: Remove provider-specific history manipulation
2. **Factory Pattern**: Create provider factory to decouple instantiation
3. **Standardize Tool History**: Define clear contract for tool call/response in history
4. **Schema Utilities**: Extract schema sanitization to shared utility module
5. **Response Parsing**: Create common utilities for extracting structured output

The provider architecture is fundamentally sound and follows the "Provider Agnostic" principle stated in the README. With minor refactoring to address the coupling points, adding Claude support would be straightforward.