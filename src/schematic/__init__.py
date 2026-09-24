"""Schematic projection of engineering designs (layout engine, symbols, verification, SVG)."""
from .models import (LayoutState, Placement, SchematicProject, SchematicComponentInstance, SchematicWire,
                     SchematicJunction, SchematicPowerPort, SchematicNetLabel, SymbolDef)
from .engine import generate_schematic, placements_from_schematic
from .verify import extract_connectivity, verify_schematic


def generate_schematic_from_engineering(engineering_design, component_registry=None, layout=None) -> SchematicProject:
    """Backward-compatible name for :func:`generate_schematic`.

    ``component_registry`` may be a ComponentRegistry or (legacy signature) a dict of
    component_type_id -> ComponentType.
    """
    from components.registry import ComponentRegistry
    reg = component_registry
    if isinstance(component_registry, dict):
        reg = ComponentRegistry()
        reg._types.update(component_registry)
    return generate_schematic(engineering_design, reg, layout)


__all__ = [
    "LayoutState", "Placement", "SchematicProject", "SchematicComponentInstance", "SchematicWire",
    "SchematicJunction", "SchematicPowerPort", "SchematicNetLabel", "SymbolDef",
    "generate_schematic", "generate_schematic_from_engineering", "placements_from_schematic",
    "extract_connectivity", "verify_schematic",
]
