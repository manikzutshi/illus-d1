# Model Provider Abstraction

## Philosophy
The core application logic must **NOT** depend directly on specific AI vendor SDKs (e.g., `openai`, `anthropic`, or `google-genai`). To future-proof the architecture, allow for cost optimization, and enable local execution, all interactions with LLMs must pass through a unified `ModelProvider` abstraction layer.

## Intended Interface (Provisional)

The exact implementation may leverage a library like `LiteLLM` or a custom adapter. Conceptually, the interface will look like this:

```python
class ModelProvider:
    def generate(self, prompt: str, context: dict = None) -> str:
        """Standard text generation."""
        pass
        
    def structured_generate(self, prompt: str, schema: Type[BaseModel], context: dict = None) -> BaseModel:
        """Force the LLM to return data matching a specific Pydantic schema."""
        pass
        
    def tool_call(self, prompt: str, tools: list, context: dict = None) -> list:
        """Invoke LLM with available tools/functions."""
        pass
        
    def stream(self, prompt: str, context: dict = None) -> Generator[str, None, None]:
        """Stream standard text generation."""
        pass
```

## Supported Backends (Future)
The abstraction layer is designed to support:
- **Frontier Hosted APIs:** GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro.
- **Cheaper Hosted Models:** GPT-4o-mini, Claude 3 Haiku, Gemini 1.5 Flash.
- **Local/Open Models:** Llama 3, Mistral (via Ollama or vLLM).

This enables dynamic routing where complex planning uses frontier models, while simple classification or schema mapping uses cheaper/local models.
