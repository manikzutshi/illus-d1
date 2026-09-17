import os
import pytest
from pydantic import BaseModel

from ai.provider_openai import RESTOpenAIProvider

# Skip if no API key is present
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY environment variable not set"
)


class DummySchema(BaseModel):
    is_working: bool
    explanation: str


def test_real_provider_generate():
    provider = RESTOpenAIProvider(model_name="gpt-4o-mini")
    response = provider.generate([{"role": "user", "content": "Say 'hello world' literally."}])
    assert "hello world" in response.lower()


def test_real_provider_structured_generate():
    provider = RESTOpenAIProvider(model_name="gpt-4o-mini")
    response = provider.structured_generate(
        messages=[{"role": "user", "content": "Return true and say 'success'"}],
        schema=DummySchema
    )
    assert isinstance(response, DummySchema)
    assert response.is_working is True
    assert "success" in response.explanation.lower()


def test_real_provider_tool_call():
    provider = RESTOpenAIProvider(model_name="gpt-4o-mini")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather in a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    response = provider.tool_call(
        messages=[{"role": "user", "content": "What's the weather in Seattle?"}],
        tools=tools
    )
    assert "tool_calls" in response
    assert len(response["tool_calls"]) > 0
    assert response["tool_calls"][0]["function"]["name"] == "get_weather"
    assert "Seattle" in response["tool_calls"][0]["function"]["arguments"]
