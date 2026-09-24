import logging
import re
from pathlib import Path
from typing import Optional
import yaml
from pydantic import ValidationError

from core.models import ComponentType

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_REGISTRY_PATH = _PROJECT_ROOT / "data" / "components" / "registry.yaml"
_DEFAULT_LIBRARY_DIR = _PROJECT_ROOT / "data" / "components" / "library"

# Field weights for ranked search. Identity fields dominate; free-text description is weakest.
_FIELD_WEIGHTS = {
    "id": 8, "name": 7, "alias": 7, "family": 6, "tag": 5, "role": 4,
    "interface": 4, "category": 3, "description": 2,
}
_STOPWORDS = {"a", "an", "the", "for", "to", "of", "and", "with", "use", "using", "that", "which"}
# Descriptors that refine an instance (colour, size) rather than identify a part type:
# they may be absent from the registry entry without disqualifying it.
_SOFT_WORDS = {"red", "green", "blue", "white", "yellow", "orange", "warm", "small", "tiny", "mini", "generic",
               "standard", "basic", "simple", "common", "cheap", "part", "component", "module"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9.+]+", text.lower()) if t and t not in _STOPWORDS]


def _stem(token: str) -> str:
    """Tiny plural normaliser: 'sensors' -> 'sensor', 'switches' -> 'switch'."""
    if len(token) > 4 and token.endswith("es") and token[:-2].endswith(("ch", "sh", "x", "ss")):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


class ComponentRegistry:
    """Data-driven registry of component types. Loaded from YAML files."""

    def __init__(self) -> None:
        self._types: dict[str, ComponentType] = {}

    def load_yaml(self, path: Path) -> int:
        """Load component types from a YAML file. Returns count of components loaded.
        The YAML has a top-level 'components' key mapping component_type_id to properties.
        Each entry must be parseable into a ComponentType model.
        When loading, the key itself is the component_type_id and must be injected into the dict before parsing."""
        if not path.exists():
            logger.error(f"Registry file not found: {path}")
            return 0

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to read YAML from {path}: {e}")
            return 0

        if not data:
            logger.warning(f"Empty YAML file: {path}")
            return 0

        components_data = data.get("components", {})
        if not isinstance(components_data, dict):
            logger.error(f"Invalid format in {path}: 'components' key must be a dictionary.")
            return 0

        loaded_count = 0
        for comp_id, comp_props in components_data.items():
            if not isinstance(comp_props, dict):
                logger.warning(f"Skipping component {comp_id}: Invalid properties format.")
                continue

            comp_props["component_type_id"] = comp_id

            try:
                if comp_id in self._types:
                    logger.warning(f"Duplicate component ID found: {comp_id}. Skipping.")
                    continue
                comp_type = ComponentType.model_validate(comp_props)
                self._types[comp_id] = comp_type
                loaded_count += 1
            except ValidationError as e:
                logger.warning(f"Validation error for component {comp_id}: {e}. Skipping.")
            except Exception as e:
                logger.warning(f"Unexpected error loading component {comp_id}: {e}. Skipping.")

        return loaded_count

    def load_directory(self, directory: Path) -> int:
        """Load every *.yaml file in a directory (sorted by name for determinism)."""
        if not directory.is_dir():
            return 0
        return sum(self.load_yaml(p) for p in sorted(directory.glob("*.yaml")))

    def get(self, component_type_id: str) -> Optional[ComponentType]:
        """Get a component type by its canonical ID. Returns None if not found."""
        return self._types.get(component_type_id)

    # ── Search ────────────────────────────────────────────────────────────

    @staticmethod
    def _fields(comp: ComponentType) -> list[tuple[str, str]]:
        fields = [("id", comp.component_type_id), ("name", comp.name),
                  ("category", comp.category.value), ("description", comp.description)]
        fields += [("alias", a) for a in comp.aliases]
        fields += [("tag", t) for t in comp.tags]
        fields += [("role", r) for r in comp.roles]
        fields += [("interface", i) for i in comp.interfaces]
        if comp.family:
            fields.append(("family", comp.family))
        if comp.education and comp.education.summary:
            fields.append(("description", comp.education.summary))
        return fields

    def score(self, comp: ComponentType, query: str) -> float:
        """Relevance score of a component for a query (0 = no match).

        1. Whole-query substring matches (the legacy behaviour) score highest.
        2. Otherwise every query token must match some field (AND semantics), so
           'temperature sensor' finds the DHT11 while 'quantum flux capacitor' finds nothing.
        """
        q = query.lower().strip()
        if not q:
            return 0.0
        fields = [(kind, value.lower()) for kind, value in self._fields(comp)]
        best_whole = max((_FIELD_WEIGHTS[k] for k, v in fields if q in v), default=0)
        if best_whole:
            exact = any(v == q for k, v in fields if k in ("id", "name", "alias", "family"))
            return 100.0 + best_whole * 10 + (50 if exact else 0)

        q_tokens = [_stem(t) for t in _tokens(q)]
        if not q_tokens:
            return 0.0
        field_tokens = [(k, {_stem(t) for t in _tokens(v)}) for k, v in fields]
        from core.units import parse_quantity
        total = 0.0
        matched = 0
        for qt in q_tokens:
            weight = 0
            for kind, toks in field_tokens:
                if qt in toks or (len(qt) >= 4 and any(t.startswith(qt) for t in toks)):
                    weight = max(weight, _FIELD_WEIGHTS[kind])
            if weight == 0:
                # Instance values ("10k", "220") and descriptors ("red") are optional.
                if qt in _SOFT_WORDS or parse_quantity(qt) is not None:
                    continue
                return 0.0
            matched += 1
            total += weight + (3 if comp.family and qt == comp.family.lower() else 0)
        return total if matched else 0.0

    def search(self, query: str, limit: Optional[int] = None) -> list[ComponentType]:
        """Ranked search over id, name, aliases, family, tags, roles, interfaces, category and
        description. Deterministic: ties are broken by component_type_id."""
        scored = [(self.score(c, query), c) for c in self._types.values()]
        ranked = sorted(scored, key=lambda x: (-x[0], x[1].component_type_id))
        results = [c for s, c in ranked if s > 0]
        return results[:limit] if limit else results

    def catalog(self) -> list[dict]:
        """Compact one-row-per-part view of the whole library (for AI planning and UIs)."""
        return [
            {
                "id": c.component_type_id,
                "name": c.name,
                "category": c.category.value,
                "object_type": c.object_type.value,
                "family": c.family,
                "tags": c.tags,
                "pins": [p.pin_id for p in c.pins],
            }
            for c in sorted(self._types.values(), key=lambda c: c.component_type_id)
        ]

    def list_all(self) -> list[ComponentType]:
        """Return all registered component types."""
        return list(self._types.values())

    def has(self, component_type_id: str) -> bool:
        """Check if a component type exists."""
        return component_type_id in self._types

    @property
    def count(self) -> int:
        """Number of registered component types."""
        return len(self._types)


_SHARED_REGISTRY: Optional[ComponentRegistry] = None


def get_default_registry() -> ComponentRegistry:
    """Load the default registry: data/components/registry.yaml plus every YAML file in
    data/components/library/ (sorted). Paths resolve relative to the project root."""
    registry = ComponentRegistry()
    registry.load_yaml(_DEFAULT_REGISTRY_PATH)
    registry.load_directory(_DEFAULT_LIBRARY_DIR)
    return registry


def get_shared_registry() -> ComponentRegistry:
    """Process-wide cached default registry for read-only use (avoids re-parsing YAML per request)."""
    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is None:
        _SHARED_REGISTRY = get_default_registry()
    return _SHARED_REGISTRY
