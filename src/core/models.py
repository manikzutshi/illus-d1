from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .enums import (
    CompetencyLevel,
    PinDirection,
    ComponentCategory,
    ValidationStatus,
    ValidationSeverity,
    ObjectType,
)

class CurriculumContext(BaseModel):
    module: str = Field(..., description="The curriculum module this concept belongs to")
    concept: str = Field(..., description="The specific concept being illustrated")
    competency_level: CompetencyLevel = Field(default=CompetencyLevel.BEGINNER, description="Target competency level")

class PinDefinition(BaseModel):
    pin_id: str = Field(..., description="Identifier for the pin (e.g. 'GPIO5', 'VCC', 'TRIG')")
    name: str = Field(..., description="Human readable name of the pin")
    direction: PinDirection = Field(..., description="Electrical direction of the pin")
    electrical_type: Optional[str] = Field(default=None, description="Electrical characteristics (e.g. '3.3V_LOGIC', '5V_TOLERANT')")
    description: str = Field(default="", description="Detailed description of the pin's function")

class ComponentType(BaseModel):
    component_type_id: str = Field(..., description="Unique identifier for the component type (e.g. 'board:esp32-devkit-v1')")
    name: str = Field(..., description="Human readable name of the component")
    aliases: List[str] = Field(default_factory=list, description="Alternative names for this component type")
    category: ComponentCategory = Field(..., description="Functional category of the component")
    object_type: ObjectType = Field(..., description="Type of object in the domain model")
    pins: List[PinDefinition] = Field(default_factory=list, description="Pins available on this component")
    electrical_properties: Dict[str, str] = Field(default_factory=dict, description="Inherent electrical properties")
    configurable_parameters: Dict[str, str] = Field(default_factory=dict, description="Parameters that can be configured on instances")
    curriculum_mapping: List[str] = Field(default_factory=list, description="Curriculum concepts this component supports")
    competency_level: CompetencyLevel = Field(default=CompetencyLevel.BEGINNER, description="Required competency level to use this component")
    provenance: str = Field(default="community", description="Origin of this component definition")
    license: str = Field(default="unknown", description="License of the component definition")
    asset_2d: Optional[str] = Field(default=None, description="Path or reference to 2D asset")
    asset_3d: Optional[str] = Field(default=None, description="Path or reference to 3D asset")
    simulation_model: Optional[str] = Field(default=None, description="Reference to simulation model")
    description: str = Field(default="", description="Detailed description of the component")
    validation_status: str = Field(default="proposed", description="Current validation status in the registry")

class LayoutHints(BaseModel):
    x: float = Field(default=0.0, description="X coordinate")
    y: float = Field(default=0.0, description="Y coordinate")
    z: float = Field(default=0.0, description="Z coordinate")
    rotation: float = Field(default=0.0, description="Rotation angle in degrees")

class ComponentInstance(BaseModel):
    instance_id: str = Field(..., description="Unique identifier for this instance in the design (e.g. 'u1', 'd1')")
    component_type: str = Field(..., description="Reference to the ComponentType.component_type_id")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Configured parameters for this instance")
    layout: Optional[LayoutHints] = Field(default=None, description="Placement hints for visualization")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional instance metadata")

class PinRef(BaseModel):
    instance_id: str = Field(..., description="Identifier of the component instance")
    pin_id: str = Field(..., description="Identifier of the pin on the instance")

    @property
    def ref(self) -> str:
        return f"{self.instance_id}.{self.pin_id}"

    @classmethod
    def from_str(cls, s: str) -> "PinRef":
        parts = s.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid PinRef string format: {s}. Expected 'instance_id.pin_id'.")
        return cls(instance_id=parts[0], pin_id=parts[1])

class Net(BaseModel):
    net_id: str = Field(..., description="Unique identifier for this net")
    connections: List[PinRef] = Field(..., min_length=2, description="Pins connected to this net")
    net_type: Optional[str] = Field(default=None, description="Type of net (e.g. 'power', 'signal', 'ground')")

class SimulationMetadata(BaseModel):
    target: str = Field(default="none", description="Simulation target engine")
    firmware_path: Optional[str] = Field(default=None, description="Path to firmware file to run")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Simulation parameters")

class DesignProject(BaseModel):
    schema_version: str = Field(default="0.2.0", description="Schema version of this design project")
    project_id: str = Field(..., description="Unique identifier for the project")
    name: str = Field(..., description="Human readable name of the project")
    description: str = Field(default="", description="Detailed description of the project")
    curriculum_context: Optional[CurriculumContext] = Field(default=None, description="Educational context")
    components: List[ComponentInstance] = Field(default_factory=list, description="Components used in the design")
    nets: List[Net] = Field(default_factory=list, description="Electrical connections between components")
    simulation: Optional[SimulationMetadata] = Field(default=None, description="Simulation settings")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional project metadata")

class ValidationError(BaseModel):
    code: str = Field(..., description="Error code (e.g. 'E001')")
    message: str = Field(..., description="Human readable error message")
    severity: ValidationSeverity = Field(..., description="Severity of the validation issue")
    affected_instances: List[str] = Field(default_factory=list, description="Instances related to this issue")
    affected_pins: List[str] = Field(default_factory=list, description="Pins related to this issue")
    affected_nets: List[str] = Field(default_factory=list, description="Nets related to this issue")
    validator: str = Field(default="", description="Name of the validator that produced this issue")

class ValidationResult(BaseModel):
    status: ValidationStatus = Field(..., description="Overall validation status")
    errors: List[ValidationError] = Field(default_factory=list, description="List of errors")
    warnings: List[ValidationError] = Field(default_factory=list, description="List of warnings")
    component_count: int = Field(default=0, description="Number of components validated")
    net_count: int = Field(default=0, description="Number of nets validated")
