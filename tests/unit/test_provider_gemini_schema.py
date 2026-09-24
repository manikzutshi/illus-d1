import json
import pytest
from ai.orchestrator import Orchestrator
from ai.provider import MockModelProvider
from ai.provider_gemini import RESTGeminiProvider

def test_gemini_schema_sanitization():
    # Instantiate the components
    orchestrator = Orchestrator(provider=MockModelProvider())
    gemini_provider = RESTGeminiProvider(model_name="gemini-3.5-flash", api_key="fake")
    
    # Get all tools as OpenAI format
    tools = orchestrator._get_tools()
    
    # Convert them using the Gemini provider (which applies sanitization)
    gemini_tools_payload = gemini_provider._convert_tools(tools)
    
    # Serialize to ensure it is JSON serializable
    json_payload = json.dumps(gemini_tools_payload)
    
    # Ensure there are no unsupported Pydantic/JSON-Schema keywords in the final output
    assert "additionalProperties" not in json_payload
    assert "$defs" not in json_payload
    assert "$ref" not in json_payload
    assert "anyOf" not in json_payload
    assert "title" not in json_payload
    assert "default" not in json_payload
    
    # Find specific tools and assert their properties
    declarations = gemini_tools_payload[0]["functionDeclarations"]
    tool_map = {d["name"]: d for d in declarations}
    
    # Check simpler tool
    search_tool = tool_map["search_components"]
    assert "description" in search_tool
    assert "properties" in search_tool["parameters"]
    assert "query" in search_tool["parameters"]["properties"]
    
    # Check complex tool (validate_design)
    validate_tool = tool_map["validate_design"]
    params = validate_tool["parameters"]
    
    assert params["type"] == "object"
    assert "design" in params["properties"]
    
    design_schema = params["properties"]["design"]
    assert design_schema["type"] == "object"
    assert "components" in design_schema["properties"]
    
    components_schema = design_schema["properties"]["components"]
    assert components_schema["type"] == "array"
    assert "items" in components_schema
    
    component_items = components_schema["items"]
    assert component_items["type"] == "object"
    assert "properties" in component_items
    assert "instance_id" in component_items["properties"]
    assert component_items["properties"]["instance_id"]["type"] == "string"
    
    # Check that 'required' is preserved where applicable
    assert "instance_id" in component_items["required"]
