"""Illustration Engine CLI — Phase 2 Implementation.

All commands read from real registries and run deterministic validation.
No AI API key is required.
"""
import json
import sys
from pathlib import Path
from typing import Optional

import typer

from components.registry import get_default_registry
from core.models import DesignProject
from curriculum.store import get_default_curriculum
from validation.calculations import calculate_led_resistor
from validation.engine import DesignValidator

app = typer.Typer(
    help="Illustration Engine: Curriculum-Grounded Engineering Visualization CLI",
    no_args_is_help=True,
)

# ── Component sub-commands ──────────────────────────────────────────────

component_app = typer.Typer(help="Query the Component Registry", no_args_is_help=True)
app.add_typer(component_app, name="component")


@component_app.command("list")
def component_list() -> None:
    """List all component types in the registry."""
    registry = get_default_registry()
    for ct in registry.list_all():
        pin_count = len(ct.pins)
        typer.echo(f"  {ct.component_type_id:<30s}  {ct.name:<40s}  pins={pin_count}")
    typer.echo(f"\nTotal: {registry.count} component types")


@component_app.command("search")
def component_search(query: str) -> None:
    """Search components by name, alias, or ID."""
    registry = get_default_registry()
    results = registry.search(query)
    if not results:
        typer.echo(f"No components matching '{query}'.")
        raise typer.Exit(code=1)
    for ct in results:
        typer.echo(f"  {ct.component_type_id:<30s}  {ct.name}")
    typer.echo(f"\n{len(results)} result(s)")


@component_app.command("show")
def component_show(component_id: str) -> None:
    """Show detailed information for a component type."""
    registry = get_default_registry()
    ct = registry.get(component_id)
    if ct is None:
        typer.echo(f"Component type '{component_id}' not found in registry.")
        raise typer.Exit(code=1)

    typer.echo(f"Component: {ct.component_type_id}")
    typer.echo(f"  Name:       {ct.name}")
    typer.echo(f"  Category:   {ct.category.value}")
    typer.echo(f"  Type:       {ct.object_type.value}")
    typer.echo(f"  Level:      {ct.competency_level.value}")
    if ct.aliases:
        typer.echo(f"  Aliases:    {', '.join(ct.aliases)}")
    if ct.description:
        typer.echo(f"  Desc:       {ct.description}")
    if ct.electrical_properties:
        typer.echo("  Electrical:")
        for k, v in ct.electrical_properties.items():
            typer.echo(f"    {k}: {v}")
    if ct.configurable_parameters:
        typer.echo("  Parameters:")
        for k, v in ct.configurable_parameters.items():
            typer.echo(f"    {k} ({v})")
    typer.echo(f"  Pins ({len(ct.pins)}):")
    for pin in ct.pins:
        etype = f"  [{pin.electrical_type}]" if pin.electrical_type else ""
        typer.echo(f"    {pin.pin_id:<10s}  {pin.direction.value:<14s}{etype}")


# ── Curriculum sub-commands ─────────────────────────────────────────────

curriculum_app = typer.Typer(help="Query the Curriculum Knowledge Graph", no_args_is_help=True)
app.add_typer(curriculum_app, name="curriculum")


@curriculum_app.command("search")
def curriculum_search(query: str) -> None:
    """Search curriculum concepts by name or description."""
    store = get_default_curriculum()
    results = store.search(query)
    if not results:
        typer.echo(f"No concepts matching '{query}'.")
        raise typer.Exit(code=1)
    for c in results:
        typer.echo(f"  {c.concept_id:<25s}  {c.name:<35s}  [{c.competency_level.value}]")
    typer.echo(f"\n{len(results)} result(s)")


@curriculum_app.command("show")
def curriculum_show(concept_id: str) -> None:
    """Show detailed concept information."""
    store = get_default_curriculum()
    c = store.get(concept_id)
    if c is None:
        typer.echo(f"Concept '{concept_id}' not found.")
        raise typer.Exit(code=1)

    typer.echo(f"Concept: {c.concept_id}")
    typer.echo(f"  Name:          {c.name}")
    typer.echo(f"  Module:        {c.module}")
    typer.echo(f"  Level:         {c.competency_level.value}")
    typer.echo(f"  Description:   {c.description}")
    if c.prerequisites:
        typer.echo(f"  Prerequisites: {', '.join(c.prerequisites)}")
    if c.related_concepts:
        typer.echo(f"  Related:       {', '.join(c.related_concepts)}")
    if c.components:
        typer.echo(f"  Components:    {', '.join(c.components)}")
    if c.tools:
        typer.echo(f"  Tools:         {', '.join(c.tools)}")


# ── Design sub-commands ─────────────────────────────────────────────────

design_app = typer.Typer(help="Manage and validate Design IRs", no_args_is_help=True)
app.add_typer(design_app, name="design")


@design_app.command("validate")
def design_validate(design_file: str) -> None:
    """Run deterministic validation (DRC/ERC) on a Design IR JSON file."""
    path = Path(design_file)
    if not path.exists():
        typer.echo(f"File not found: {design_file}")
        raise typer.Exit(code=1)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        design = DesignProject.model_validate(data)
    except Exception as e:
        typer.echo(f"Failed to parse Design IR: {e}")
        raise typer.Exit(code=1)

    registry = get_default_registry()
    validator = DesignValidator(registry)
    result = validator.validate(design)

    typer.echo(f"\nProject: {design.name} ({design.project_id})")
    typer.echo(f"Status:  {result.status.value}")
    typer.echo(f"\nComponents: {result.component_count}")
    typer.echo(f"Nets:       {result.net_count}")
    typer.echo(f"\nErrors:   {len(result.errors)}")
    typer.echo(f"Warnings: {len(result.warnings)}")

    for err in result.errors:
        affected = ""
        if err.affected_instances:
            affected += f"  instances={err.affected_instances}"
        if err.affected_pins:
            affected += f"  pins={err.affected_pins}"
        if err.affected_nets:
            affected += f"  nets={err.affected_nets}"
        typer.echo(f"\n  {err.code} {err.message}{affected}")

    for warn in result.warnings:
        affected = ""
        if warn.affected_instances:
            affected += f"  instances={warn.affected_instances}"
        typer.echo(f"\n  {warn.code} [WARNING] {warn.message}{affected}")

    if result.status.value == "FAIL":
        raise typer.Exit(code=1)


# ── Calculate sub-commands ──────────────────────────────────────────────

calc_app = typer.Typer(help="Deterministic engineering calculations", no_args_is_help=True)
app.add_typer(calc_app, name="calc")


@calc_app.command("led-resistor")
def calc_led_resistor(
    supply_voltage: float = typer.Option(..., "--supply", "-s", help="Supply voltage (V)"),
    forward_voltage: float = typer.Option(..., "--vf", "-f", help="LED forward voltage (V)"),
    current_ma: float = typer.Option(10.0, "--current", "-i", help="Target current (mA)"),
) -> None:
    """Calculate LED series resistor value using Ohm's Law."""
    try:
        result = calculate_led_resistor(supply_voltage, forward_voltage, current_ma)
    except ValueError as e:
        typer.echo(f"Calculation error: {e}")
        raise typer.Exit(code=1)

    typer.echo(f"\nLED Resistor Calculation")
    typer.echo(f"  Formula:              R = (V_supply - V_forward) / I_target")
    typer.echo(f"  Supply voltage:       {result.supply_voltage} V")
    typer.echo(f"  LED forward voltage:  {result.led_forward_voltage} V")
    typer.echo(f"  Target current:       {result.target_current_ma} mA")
    typer.echo(f"  Calculated R:         {result.calculated_resistance} Ω")
    if result.nearest_standard_value:
        typer.echo(f"  Selected E24 value:   {result.nearest_standard_value} Ω")
    if result.actual_current_ma:
        typer.echo(f"  Predicted current:    {result.actual_current_ma} mA")
    typer.echo(f"  Power dissipation:    {result.power_dissipation_mw} mW")
    typer.echo(f"\nAssumptions:")
    for a in result.assumptions:
        typer.echo(f"  - {a}")


# ── Agent sub-commands ──────────────────────────────────────────────────

import time
from ai.provider_openai import RESTOpenAIProvider
from ai.provider import MockModelProvider
from ai.orchestrator import Orchestrator

agent_app = typer.Typer(help="AI orchestration loop", no_args_is_help=True)
app.add_typer(agent_app, name="agent")


@agent_app.command("run")
def run_agent(
    prompt: str,
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="Model name"),
    mock: bool = typer.Option(False, "--mock", help="Use offline MockModelProvider"),
    max_repair_attempts: int = typer.Option(3, "--max-repair", help="Maximum repair attempts"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show internal tool and validation traces"),
) -> None:
    """Run the complete AI orchestration pipeline (prompt -> proposal -> validate -> repair)."""
    typer.echo(f"Initializing orchestrator (model={model}, mock={mock})")
    
    if mock:
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent.parent))
        from tests.unit.test_orchestrator import MockRepairProvider
        provider = MockRepairProvider()
    else:
        provider = RESTOpenAIProvider(model_name=model)
        
    orchestrator = Orchestrator(provider, max_repair_attempts=max_repair_attempts)
    
    if verbose:
        def verbose_cb(event, data):
            if event == "TOOL_CALL":
                typer.echo(f"[tool] {data.get('tool')}(...)")
            elif event == "VALIDATION_RESULT":
                if isinstance(data, dict):
                    status = data.get("status")
                    if status == "FAIL":
                        errors = data.get("errors", [])
                        codes = [e.get("code") for e in errors]
                        typer.echo(f"[validation] FAIL {codes}")
                    else:
                        typer.echo(f"[validation] {status}")
            elif event == "PROPOSAL_REQUESTED":
                typer.echo(f"[agent] repair attempt {data.get('attempt', 0)}")
            elif event == "CLARIFICATION_REQUIRED":
                typer.echo(f"[agent] clarification required: {data}")
        orchestrator.verbose_callback = verbose_cb

    typer.echo(f"Processing request: '{prompt}'")
    
    try:
        final_design = orchestrator.run(prompt)
    except Exception as e:
        typer.echo(f"Agent failed with error: {str(e)}")
        final_design = None
        
    typer.echo(f"\nFinal State: {orchestrator.state.value}")
    if final_design:
        typer.echo(f"Resulting Design Project ID: {final_design.project_id}")
        typer.echo(f"Valid Components: {len(final_design.components)}")
        typer.echo(f"Valid Nets: {len(final_design.nets)}")
    else:
        typer.echo("No valid design produced.")
        
    # Save trace
    timestamp = int(time.time())
    run_dir = Path(f"runs/{timestamp}")
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "trace.json"
    
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(orchestrator.traces, f, indent=2)
        
    typer.echo(f"\nSaved trace to {trace_path}")
    
    if orchestrator.state != "COMPLETED":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
