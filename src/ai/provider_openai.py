import json
import os
import urllib.request
import urllib.error
from typing import Type, Optional, Any
from pydantic import BaseModel

from .provider import ModelProvider


class RESTOpenAIProvider(ModelProvider):
    """A generic REST provider that communicates with OpenAI-compatible APIs.
    
    This avoids importing heavyweight vendor SDKs while supporting OpenAI, 
    LiteLLM proxies, Ollama, vLLM, and LM Studio.
    """
    
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        
    def _post(self, payload: dict) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"OpenAI API Error {e.code}: {error_body}")
            
    def generate(self, messages: list[dict], context: Optional[dict] = None) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2
        }
        result = self._post(payload)
        return result["choices"][0]["message"].get("content", "")
        
    def structured_generate(self, messages: list[dict], schema: Type[BaseModel], context: Optional[dict] = None) -> BaseModel:
        # We use tool calling to enforce structured output, which is the most widely supported method
        # across different OpenAI-compatible backends (including local models).
        schema_json = schema.model_json_schema()
        
        # Remove '$defs' if present as some strict tools don't like it (simplify the schema if needed)
        # But for DesignProject, Pydantic handles it cleanly.
        
        tool = {
            "type": "function",
            "function": {
                "name": "submit_structured_output",
                "description": f"Submit the final structured {schema.__name__}",
                "parameters": schema_json
            }
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2,
            "tools": [tool],
            "tool_choice": {"type": "function", "function": {"name": "submit_structured_output"}}
        }
        
        result = self._post(payload)
        message = result["choices"][0]["message"]
        
        if "tool_calls" in message and message["tool_calls"]:
            arguments = message["tool_calls"][0]["function"]["arguments"]
            data = json.loads(arguments)
            return schema.model_validate(data)
            
        # Fallback if model puts it in content
        if message.get("content"):
            try:
                # Naive json extraction if wrapped in code blocks
                content = message["content"]
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                data = json.loads(content)
                return schema.model_validate(data)
            except Exception:
                pass
                
        raise ValueError(f"Failed to generate structured output for {schema.__name__}. Raw message: {message}")

    def tool_call(self, messages: list[dict], tools: list[dict], context: Optional[dict] = None) -> Any:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2,
            "tools": tools,
            "tool_choice": "auto"
        }
        result = self._post(payload)
        return result["choices"][0]["message"]
