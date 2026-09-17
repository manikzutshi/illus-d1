import logging
from pathlib import Path
from typing import Optional
import yaml
from pydantic import ValidationError

from core.models import ComponentType

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_REGISTRY_PATH = _PROJECT_ROOT / "data" / "components" / "registry.yaml"


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
                comp_type = ComponentType.model_validate(comp_props)
                self._types[comp_id] = comp_type
                loaded_count += 1
            except ValidationError as e:
                logger.warning(f"Validation error for component {comp_id}: {e}. Skipping.")
            except Exception as e:
                logger.warning(f"Unexpected error loading component {comp_id}: {e}. Skipping.")
                
        return loaded_count

    def get(self, component_type_id: str) -> Optional[ComponentType]:
        """Get a component type by its canonical ID. Returns None if not found."""
        return self._types.get(component_type_id)
    
    def search(self, query: str) -> list[ComponentType]:
        """Search by name, alias, or type ID. Case-insensitive substring match."""
        query_lower = query.lower()
        results: list[ComponentType] = []
        for comp in self._types.values():
            if query_lower in comp.component_type_id.lower() or query_lower in comp.name.lower():
                results.append(comp)
                continue
            
            # Check aliases
            if any(query_lower in alias.lower() for alias in comp.aliases):
                results.append(comp)
                
        return results
    
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


def get_default_registry() -> ComponentRegistry:
    """Load the default registry from data/components/registry.yaml.
    This function resolves the path relative to the project root."""
    registry = ComponentRegistry()
    registry.load_yaml(_DEFAULT_REGISTRY_PATH)
    return registry
