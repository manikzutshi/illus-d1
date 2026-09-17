"""Curriculum concept loader and search."""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from core.enums import CompetencyLevel

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CURRICULUM_PATH = _PROJECT_ROOT / "data" / "curriculum" / "concepts.yaml"


class ConceptRecord(BaseModel):
    """A single curriculum concept."""
    concept_id: str = Field(..., description="Unique identifier for the concept")
    name: str = Field(..., description="Human-readable concept name")
    description: str = Field(default="", description="Detailed description")
    prerequisites: list[str] = Field(default_factory=list, description="Prerequisite concept IDs")
    related_concepts: list[str] = Field(default_factory=list, description="Related concept IDs")
    components: list[str] = Field(default_factory=list, description="Associated component IDs")
    competency_level: CompetencyLevel = Field(default=CompetencyLevel.BEGINNER)
    module: str = Field(default="", description="Parent curriculum module")
    tools: list[str] = Field(default_factory=list, description="Associated tools")
    standards: list[str] = Field(default_factory=list, description="Relevant standards")


class CurriculumStore:
    """Data-driven curriculum concept store. Loaded from YAML."""

    def __init__(self) -> None:
        self._concepts: dict[str, ConceptRecord] = {}

    def load_yaml(self, path: Path) -> int:
        """Load concepts from a YAML file. Returns count loaded."""
        if not path.exists():
            logger.error(f"Curriculum file not found: {path}")
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to read curriculum YAML: {e}")
            return 0

        if not data:
            return 0

        concepts_data = data.get("concepts", {})
        if not isinstance(concepts_data, dict):
            logger.error("Invalid curriculum format: 'concepts' must be a dictionary.")
            return 0

        loaded = 0
        for concept_id, props in concepts_data.items():
            if not isinstance(props, dict):
                continue
            props["concept_id"] = concept_id
            try:
                record = ConceptRecord.model_validate(props)
                self._concepts[concept_id] = record
                loaded += 1
            except Exception as e:
                logger.warning(f"Skipping concept {concept_id}: {e}")

        return loaded

    def get(self, concept_id: str) -> Optional[ConceptRecord]:
        """Get a concept by ID."""
        return self._concepts.get(concept_id)

    def search(self, query: str) -> list[ConceptRecord]:
        """Search by name, ID, or description. Case-insensitive substring."""
        q = query.lower()
        results = []
        for concept in self._concepts.values():
            if (q in concept.concept_id.lower()
                    or q in concept.name.lower()
                    or q in concept.description.lower()):
                results.append(concept)
        return results

    def list_all(self) -> list[ConceptRecord]:
        """Return all concepts."""
        return list(self._concepts.values())

    @property
    def count(self) -> int:
        return len(self._concepts)


def get_default_curriculum() -> CurriculumStore:
    """Load the default curriculum from data/curriculum/concepts.yaml."""
    store = CurriculumStore()
    store.load_yaml(_DEFAULT_CURRICULUM_PATH)
    return store
