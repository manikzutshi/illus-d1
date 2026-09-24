import pytest
import json
from ai.provider_gemini import RESTGeminiProvider

def test_gemini_function_response_serialization():
    # We construct a mock history that mimics the orchestrator's state after Gemini has returned 
    # a model turn with 3 tool calls, and our orchestrator has appended the 3 tool responses.
    
    provider = RESTGeminiProvider(model_name="gemini-3.5-flash", api_key="fake")
    
    # Fake raw parts returned by Gemini in the previous turn
    raw_model_parts = [
        {"text": "I will search for the components now."},
        {"functionCall": {"name": "search_components", "args": {"query": "ESP32"}, "id": "call_abc123"}},
        {"functionCall": {"name": "search_components", "args": {"query": "HC-SR04"}, "id": "call_def456"}},
        {"functionCall": {"name": "search_components", "args": {"query": "LED"}, "id": "call_ghi789"}}
    ]
    
    # Fake tool return values (lists of objects!)
    esp32_result = '[{"id": "board:esp32", "name": "ESP32"}]'
    hc_result = '[{"id": "sensor:hcsr04", "name": "HC-SR04"}]'
    led_result = '[{"id": "passive:led", "name": "LED"}]'
    
    messages = [
        {"role": "user", "content": "Build a water level monitor."},
        {
            "role": "assistant", 
            "content": None, 
            "tool_calls": [
                {"id": "call_abc123", "function": {"name": "search_components", "arguments": "{}"}},
                {"id": "call_def456", "function": {"name": "search_components", "arguments": "{}"}},
                {"id": "call_ghi789", "function": {"name": "search_components", "arguments": "{}"}}
            ],
            "raw_parts": raw_model_parts
        },
        {"role": "tool", "tool_call_id": "call_abc123", "name": "search_components", "content": esp32_result},
        {"role": "tool", "tool_call_id": "call_def456", "name": "search_components", "content": hc_result},
        {"role": "tool", "tool_call_id": "call_ghi789", "name": "search_components", "content": led_result}
    ]
    
    contents, sys_instr = provider._convert_messages(messages)
    
    # The first message is user
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Build a water level monitor."
    
    # The second message is model
    assert contents[1]["role"] == "model"
    # Ensure it preserved the raw parts exactly
    assert contents[1]["parts"] == raw_model_parts
    
    # The third message MUST be exactly ONE user turn containing all 3 function responses
    assert len(contents) == 3
    assert contents[2]["role"] == "user"
    assert len(contents[2]["parts"]) == 3
    
    for i, expected_id in enumerate(["call_abc123", "call_def456", "call_ghi789"]):
        part = contents[2]["parts"][i]
        assert "functionResponse" in part
        fr = part["functionResponse"]
        
        # Name preserved
        assert fr["name"] == "search_components"
        
        # ID preserved
        assert fr["id"] == expected_id
        
        # Response is an OBJECT/DICT, not a list!
        resp = fr["response"]
        assert isinstance(resp, dict)
        assert "result" in resp
        assert isinstance(resp["result"], list)
        assert len(resp["result"]) == 1
