"""The studio document: engineering truth + presentation state.

    StudioDocument
      ├── design   : EngineeringDesignProject   (the only source of connectivity/parameters)
      ├── layout   : LayoutState                 (placement / rotation / net style - no connectivity)
      ├── intent   : FunctionalIntent            (requested behaviour; graded by the functional validator)
      └── provenance

Everything else the studio shows (validation, schematic, explanation) is *derived* from the
document on every request and never stored as authority.
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from core.models import EngineeringDesignProject, ValidationResult
from functional.intent import FunctionalIntent
from functional.validator import FunctionalReport
from schematic.models import LayoutState, SchematicProject

DOCUMENT_SCHEMA_VERSION = "1.0"


class Provenance(BaseModel):
    source: Literal["ai", "example", "manual", "import"] = "manual"
    prompt: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    example: Optional[str] = None


class StudioDocument(BaseModel):
    schema_version: str = DOCUMENT_SCHEMA_VERSION
    design: EngineeringDesignProject
    layout: LayoutState = Field(default_factory=LayoutState)
    intent: Optional[FunctionalIntent] = None      # what the design must do (from the request), not how
    provenance: Provenance = Field(default_factory=Provenance)
    revision: int = 0


class OpResult(BaseModel):
    op: str
    kind: Literal["engineering", "presentation"]
    message: str


class StudioState(BaseModel):
    """What the studio renders: the document plus everything derived from it."""
    document: StudioDocument
    validation: ValidationResult
    functional: FunctionalReport
    schematic: SchematicProject
    verification: Dict[str, object]
    explanation: Dict[str, object] = Field(default_factory=dict)
    op_results: List[OpResult] = Field(default_factory=list)
