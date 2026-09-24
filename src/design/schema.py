# Legacy file - kept for reference but not used in current implementation
# Current implementation uses EngineeringDesignProject and EngineeringComponentInstance from core.models
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional

class CurriculumContext(BaseModel):
    module: str
    concept: str

class LayoutHints(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

class ComponentInstance(BaseModel):
    type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    layout_hints: Optional[LayoutHints] = None

class Net(BaseModel):
    id: str
    connections: List[str]

class ValidationState(BaseModel):
    status: str = "UNVALIDATED"
    errors: List[str] = Field(default_factory=list)

class SimulationMetadata(BaseModel):
    target: str
    firmware_path: Optional[str] = None

class DesignIR(BaseModel):
    schema_version: str = "0.1.0-PROVISIONAL"
    project_name: str
    curriculum_context: Optional[CurriculumContext] = None
    components: Dict[str, ComponentInstance]
    nets: List[Net]
    validation_state: ValidationState = Field(default_factory=ValidationState)
    simulation_metadata: Optional[SimulationMetadata] = None
