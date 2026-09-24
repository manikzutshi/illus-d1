import json
import pytest
from core.models import EngineeringDesignProject, EngineeringComponentInstance

def test_resolved_schema_no_defs():
    """Ensure that the resolved schema has no $defs and still describes the model."""
    schema = EngineeringDesignProject.resolved_schema()

    # $defs should be completely eliminated
    assert "$defs" not in schema
    assert "$ref" not in json.dumps(schema)

    # Check that key properties exist and are fully expanded
    assert "components" in schema["properties"]
    assert schema["properties"]["components"]["type"] == "array"
    items = schema["properties"]["components"]["items"]
    assert "properties" in items
    assert "instance_id" in items["properties"]

    assert "nets" in schema["properties"]
    assert schema["properties"]["nets"]["type"] == "array"
    net_items = schema["properties"]["nets"]["items"]
    assert "properties" in net_items
    assert "connections" in net_items["properties"]

def test_serialization_contract():
    """Test that a canonical EngineeringDesignProject survives the JSON serialization boundary."""
    # Build a simple valid project
    from core.models import EngineeringComponentInstance, Net, PinRef, LogicRule, LogicCondition, LogicAction
    from core.enums import ValidationStatus

    dp = EngineeringDesignProject(
        project_id="water-level",
        name="Water Level Monitor",
        components=[
            EngineeringComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
            EngineeringComponentInstance(instance_id="d1", component_type="passive:led-5mm")
        ],
        nets=[
            Net(net_id="n1", connections=[
                PinRef(instance_id="u1", pin_id="GPIO5"),
                PinRef(instance_id="d1", pin_id="ANODE")
            ])
        ],
        logic=[
            LogicRule(
                rule_id="rule1",
                conditions=[LogicCondition(input_instance="u1", condition=">", value="50")],
                actions=[LogicAction(output_instance="d1", state="HIGH")]
            )
        ],
        metadata={"user": "test"}
    )

    # Dump to JSON exactly as it would pass through the tool boundary
    json_str = dp.model_dump_json()
    parsed_dict = json.loads(json_str)

    # Gemini returns the parsed dict, then Orchestrator calls EngineeringDesignProject.model_validate
    reconstructed = EngineeringDesignProject.model_validate(parsed_dict)

    # Assert structural integrity
    assert reconstructed.project_id == "water-level"
    assert reconstructed.name == "Water Level Monitor"
    assert len(reconstructed.components) == 2
    assert reconstructed.components[0].instance_id == "u1"

    assert len(reconstructed.nets) == 1
    assert reconstructed.nets[0].net_id == "n1"
    assert len(reconstructed.nets[0].connections) == 2
    assert reconstructed.nets[0].connections[0].instance_id == "u1"

    assert len(reconstructed.logic) == 1
    assert reconstructed.logic[0].conditions[0].condition == ">"
