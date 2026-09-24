from typing import List, Optional
from pydantic import BaseModel, Field

from functional.intent import FunctionalIntent

class ProjectRequirements(BaseModel):
    """Extracted requirements from the user's natural language request."""
    intent: str = Field(..., description="The overall goal or intent of the project (e.g. 'Build a water level monitoring system')")
    functional_requirements: List[str] = Field(default_factory=list, description="Specific functional requirements")
    inputs: List[str] = Field(default_factory=list, description="Physical or logical inputs required (e.g. 'distance sensor', 'button')")
    outputs: List[str] = Field(default_factory=list, description="Physical or logical outputs required (e.g. 'LED', 'buzzer')")
    actions: List[str] = Field(default_factory=list, description="Actions the system should take")
    thresholds: List[str] = Field(default_factory=list, description="Explicit thresholds or conditions (e.g. 'distance < 10cm')")
    constraints: List[str] = Field(default_factory=list, description="Hard constraints (e.g. 'must use ESP32', 'battery powered')")
    requested_components: List[str] = Field(default_factory=list, description="Specific components mentioned by name")
    ambiguities: List[str] = Field(default_factory=list, description="Questions or ambiguities that need clarification")
    functional_intent: Optional[FunctionalIntent] = Field(
        default=None, description="Structured behaviour the circuit must implement: input/output signals and WHEN->THEN behaviours")

    @classmethod
    def resolved_schema(cls) -> dict:
        from core.models import resolve_refs
        return resolve_refs(cls.model_json_schema())
