from abc import ABC, abstractmethod
from typing import Type, Optional, Generator, Any
from pydantic import BaseModel

class ModelProvider(ABC):
    """Abstract base class for AI model providers.
    
    The rest of the application MUST NOT depend directly on any
    specific AI vendor's SDK. All LLM interactions go through this interface.
    """
    
    @abstractmethod
    def generate(self, prompt: str, context: Optional[dict] = None) -> str:
        """Generate a text response from the model."""
        ...
    
    @abstractmethod
    def structured_generate(self, prompt: str, schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
        """Generate a response that conforms to a Pydantic schema."""
        ...
    
    @abstractmethod
    def tool_call(self, prompt: str, tools: list[dict], context: Optional[dict] = None) -> list[dict]:
        """Generate tool calls based on the prompt and available tools."""
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
    
    def generate(self, prompt: str, context: Optional[dict] = None) -> str:
        prompt_lower = prompt.lower()
        for key, response in self._responses.items():
            if key in prompt_lower:
                return response
        return "[MockModelProvider] No configured response for this prompt."
    
    def structured_generate(self, prompt: str, schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
        prompt_lower = prompt.lower()
        for key, response in self._structured_responses.items():
            if key in prompt_lower:
                if isinstance(response, schema):
                    return response
        raise ValueError(f"[MockModelProvider] No configured structured response matching schema {schema.__name__}")
    
    def tool_call(self, prompt: str, tools: list[dict], context: Optional[dict] = None) -> list[dict]:
        return []  # Mock returns no tool calls by default
