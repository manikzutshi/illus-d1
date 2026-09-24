"""Agent tool boundary — deterministic functions exposed to the future AI agent.

Each function here wraps a deterministic subsystem and returns a structured result.
The AI calls these as tools; it cannot bypass their logic.

Architecture:
    LLM -> tool_call -> deterministic function -> structured result -> LLM

The LLM may NOT:
    - Override validation results
    - Invent components not in the registry
    - Skip validation
    - Generate simulation output directly
"""
from pathlib import Path
from typing import Optional

from components.registry import ComponentRegistry, get_default_registry, get_shared_registry
from core.models import (
    ComponentType, EngineeringDesignProject, ValidationResult,
)
from curriculum.store import CurriculumStore, ConceptRecord, get_default_curriculum
from validation.calculations import ResistorCalculation, calculate_led_resistor
from validation.engine import DesignValidator


def search_components(query: str, registry: Optional[ComponentRegistry] = None) -> list[ComponentType]:
    """Search the component registry. Returns matching ComponentType objects.
    The AI uses this to discover which components are supported."""
    if registry is None:
        registry = get_shared_registry()
    return registry.search(query)


def get_component(component_type_id: str, registry: Optional[ComponentRegistry] = None) -> Optional[ComponentType]:
    """Get a specific component type by canonical ID.
    Returns None if the component is not in the registry (must be flagged, not hallucinated)."""
    if registry is None:
        registry = get_shared_registry()
    return registry.get(component_type_id)


def search_curriculum(query: str, store: Optional[CurriculumStore] = None) -> list[ConceptRecord]:
    """Search curriculum concepts. Returns matching ConceptRecord objects."""
    if store is None:
        store = get_default_curriculum()
    return store.search(query)


def validate_design(
    design: EngineeringDesignProject,
    registry: Optional[ComponentRegistry] = None,
) -> ValidationResult:
    """Run deterministic validation on a EngineeringDesignProject.
    The AI MUST NOT override this result."""
    if registry is None:
        registry = get_shared_registry()
    validator = DesignValidator(registry)
    return validator.validate(design)


def calculate_circuit(
    calculation_type: str,
    **kwargs,
) -> ResistorCalculation:
    """Run a deterministic engineering calculation.
    
    Currently supports:
        calculation_type='led_resistor': requires supply_voltage, led_forward_voltage, target_current_ma
    
    Future:
        'voltage_divider', 'rc_time_constant', etc.
    """
    if calculation_type == "led_resistor":
        return calculate_led_resistor(
            supply_voltage=kwargs["supply_voltage"],
            led_forward_voltage=kwargs["led_forward_voltage"],
            target_current_ma=kwargs["target_current_ma"],
        )
    raise ValueError(f"Unknown calculation type: {calculation_type}")
