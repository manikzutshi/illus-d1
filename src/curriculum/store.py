"""Curriculum concept graph: loader and search.

Concepts are *knowledge*, not parts. Each concept records what kind of thing it is
(``kind``), at which abstraction level it lives, how it can be visualised, and which
registry components / design patterns realise it (if any). The structure follows the
curriculum blueprint's loop: understand → design → simulate → inspect → debug → optimize → explain.
"""

import logging
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from core.enums import CompetencyLevel

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CURRICULUM_DIR = _PROJECT_ROOT / "data" / "curriculum"
_DEFAULT_CURRICULUM_PATH = _DEFAULT_CURRICULUM_DIR / "concepts.yaml"

ConceptKind = Literal["concept", "engineering_object", "design_pattern", "process", "methodology"]
AbstractionLevel = Literal["physics", "device", "circuit", "gate", "rtl", "architecture", "system",
                           "verification", "implementation", "manufacturing", "package", "methodology"]


class LearningLoop(BaseModel):
    """Pointers for the understand → design → simulate → debug → optimize → explain loop."""
    design_task: str = ""
    simulate: str = ""
    debug_task: str = ""
    optimize: str = ""
    explain: str = ""


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
    # ── Knowledge-graph extensions (2D Schematic Studio stage) ──
    kind: ConceptKind = Field(default="concept", description="What sort of knowledge object this is")
    domain: str = Field(default="", description="One of the blueprint's knowledge domains")
    abstraction_level: Optional[AbstractionLevel] = Field(default=None)
    representations: list[str] = Field(default_factory=list,
                                       description="How it can be shown: schematic, waveform, block_diagram, layout, cross_section, ...")
    patterns: list[str] = Field(default_factory=list, description="Design-pattern IDs that realise this concept")
    learning_loop: Optional[LearningLoop] = None


class ModuleRecord(BaseModel):
    module_id: str
    number: Optional[int] = None
    name: str
    layer: Literal["core", "industry"] = "core"
    domains: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class CurriculumStore:
    """Data-driven curriculum concept store. Loaded from YAML."""

    def __init__(self) -> None:
        self._concepts: dict[str, ConceptRecord] = {}
        self._modules: dict[str, ModuleRecord] = {}

    def load_yaml(self, path: Path) -> int:
        """Load concepts (and optional modules) from a YAML file. Returns concept count loaded."""
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

        for module_id, props in (data.get("modules") or {}).items():
            try:
                self._modules[module_id] = ModuleRecord.model_validate({**props, "module_id": module_id})
            except Exception as e:
                logger.warning(f"Skipping module {module_id}: {e}")

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

    def modules(self) -> List[ModuleRecord]:
        return list(self._modules.values())

    def concepts_for_component(self, component_type_id: str) -> List[ConceptRecord]:
        return [c for c in self._concepts.values() if component_type_id in c.components]

    def by_domain(self) -> Dict[str, List[ConceptRecord]]:
        out: Dict[str, List[ConceptRecord]] = {}
        for c in self._concepts.values():
            out.setdefault(c.domain or "unassigned", []).append(c)
        return out

    @property
    def count(self) -> int:
        return len(self._concepts)


def get_default_curriculum() -> CurriculumStore:
    """Load data/curriculum/concepts.yaml, then every other YAML file in that directory (sorted)."""
    store = CurriculumStore()
    store.load_yaml(_DEFAULT_CURRICULUM_PATH)
    for path in sorted(_DEFAULT_CURRICULUM_DIR.glob("*.yaml")):
        if path != _DEFAULT_CURRICULUM_PATH:
            store.load_yaml(path)
    return store
