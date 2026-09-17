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


class MockModelProvider(ModelProvider):
    """Mock provider for testing. Returns deterministic, pre-configured responses.
    
    This allows the entire system to run and test without any API key or internet.
    """
    
    def __init__(self):
        self._responses: dict[str, str] = {}
        self._structured_responses: dict[str, BaseModel] = {}
    
    def set_response(self, prompt_contains: str, response: str) -> None:
        """Configure a response for prompts containing the given substring."""
        self._responses[prompt_contains.lower()] = response
    
    def set_structured_response(self, prompt_contains: str, response: BaseModel) -> None:
        """Configure a structured response for prompts containing the given substring."""
        self._structured_responses[prompt_contains.lower()] = response
    
    def _extract_prompt(self, messages: list[dict]) -> str:
        if not messages:
            return ""
        # Get the last message content
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
