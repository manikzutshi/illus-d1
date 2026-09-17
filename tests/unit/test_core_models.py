"""Tests for core domain models and enums."""
import pytest
from pydantic import ValidationError as PydanticValidationError

from core.enums import (
    CompetencyLevel, PinDirection, ComponentCategory,
    ValidationStatus, ValidationSeverity, ObjectType,
)
from core.models import (
    CurriculumContext, PinDefinition, ComponentType, LayoutHints,
    ComponentInstance, PinRef, Net, SimulationMetadata,
    DesignProject, ValidationError, ValidationResult,
)


class TestEnums:
    def test_competency_levels(self):
        assert CompetencyLevel.BEGINNER == "BEGINNER"
        assert CompetencyLevel.ADVANCED == "ADVANCED"

    def test_pin_direction_values(self):
        assert len(PinDirection) == 6
        assert PinDirection.BIDIRECTIONAL == "BIDIRECTIONAL"

    def test_component_category_values(self):
        assert ComponentCategory.MICROCONTROLLER == "MICROCONTROLLER"
        assert ComponentCategory.ROUTING == "ROUTING"

    def test_validation_status(self):
        assert ValidationStatus.PASS == "PASS"
        assert ValidationStatus.FAIL == "FAIL"
        assert ValidationStatus.UNVALIDATED == "UNVALIDATED"


class TestPinRef:
    def test_from_str_valid(self):
        ref = PinRef.from_str("u1.GPIO5")
        assert ref.instance_id == "u1"
        assert ref.pin_id == "GPIO5"

    def test_from_str_invalid(self):
        with pytest.raises(ValueError, match="Invalid PinRef"):
            PinRef.from_str("just_a_string")

    def test_ref_property(self):
        ref = PinRef(instance_id="d1", pin_id="ANODE")
        assert ref.ref == "d1.ANODE"

    def test_from_str_roundtrip(self):
        original = "r1.PIN2"
        ref = PinRef.from_str(original)
        assert ref.ref == original


class TestComponentInstance:
    def test_minimal(self):
        ci = ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1")
        assert ci.parameters == {}
        assert ci.layout is None

    def test_with_parameters(self):
        ci = ComponentInstance(
            instance_id="r1",
            component_type="passive:resistor-tht",
            parameters={"resistance": "330"}
        )
        assert ci.parameters["resistance"] == "330"


class TestNet:
    def test_min_connections(self):
        """Net must have at least 2 connections."""
        with pytest.raises(PydanticValidationError):
            Net(
                net_id="n1",
                connections=[PinRef(instance_id="u1", pin_id="GND1")]
            )

    def test_valid_net(self):
        net = Net(
            net_id="n_power",
            connections=[
                PinRef(instance_id="u1", pin_id="VIN"),
                PinRef(instance_id="pwr1", pin_id="VCC"),
            ],
            net_type="power",
        )
        assert len(net.connections) == 2
        assert net.net_type == "power"


class TestDesignProject:
    def test_minimal_valid(self):
        dp = DesignProject(
            project_id="test",
            name="Test Project",
            components=[
                ComponentInstance(instance_id="u1", component_type="board:esp32-devkit-v1"),
            ],
            nets=[],
        )
        assert dp.schema_version == "0.2.0"
        assert dp.project_id == "test"

    def test_empty_components(self):
        dp = DesignProject(project_id="empty", name="Empty", components=[], nets=[])
        assert len(dp.components) == 0

    def test_missing_required_fields(self):
        with pytest.raises(PydanticValidationError):
            DesignProject(name="Missing ID")


class TestValidationResult:
    def test_pass_result(self):
        vr = ValidationResult(
            status=ValidationStatus.PASS,
            component_count=3,
            net_count=4,
        )
        assert vr.status == ValidationStatus.PASS
        assert len(vr.errors) == 0

    def test_fail_result_with_errors(self):
        vr = ValidationResult(
            status=ValidationStatus.FAIL,
            errors=[
                ValidationError(
                    code="E001",
                    message="Unknown component",
                    severity=ValidationSeverity.ERROR,
                    affected_instances=["x1"],
                )
            ],
            component_count=1,
        )
        assert vr.status == ValidationStatus.FAIL
        assert vr.errors[0].code == "E001"
