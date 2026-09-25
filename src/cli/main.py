"""Illustration Engine CLI — Phase 2 Implementation.

All commands read from real registries and run deterministic validation.
No AI API key is required.
"""
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import typer

from components.registry import get_default_registry
from core.models import EngineeringDesignProject
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
        design = EngineeringDesignProject.model_validate(data)
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
        sys.path.append(str(Path(__file__).parent.parent.parent))
        from tests.unit.test_orchestrator import MockRepairProvider
        provider = MockRepairProvider()
    else:
        from ai.factory import create_provider
        provider = create_provider(model=model)
        
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


# ── Schematic sub-commands ──────────────────────────────────────────────

schematic_app = typer.Typer(help="Deterministic schematic projection of Design IR files", no_args_is_help=True)
app.add_typer(schematic_app, name="schematic")


def _load_design(design_file: str) -> EngineeringDesignProject:
    path = Path(design_file)
    if not path.exists():
        typer.echo(f"File not found: {design_file}")
        raise typer.Exit(code=1)
    try:
        return EngineeringDesignProject.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        typer.echo(f"Failed to parse Design IR: {e}")
        raise typer.Exit(code=1)


@schematic_app.command("generate")
def schematic_generate(design_file: str, out: Optional[str] = typer.Option(None, "--out", "-o", help="Write Schematic IR JSON here")) -> None:
    """Generate the Schematic IR for a design and report layout statistics."""
    from schematic import generate_schematic, verify_schematic
    design = _load_design(design_file)
    s = generate_schematic(design, get_default_registry())
    rep = verify_schematic(s, design)
    typer.echo(f"Schematic: {s.name}  components={len(s.components)} wires={len(s.wires)} junctions={len(s.junctions)} "
               f"ports={len(s.power_ports)} labels={len(s.net_labels)}")
    typer.echo(f"Layout: wire_length={s.stats.wire_length} bends={s.stats.bends} crossings={s.stats.crossings} "
               f"({s.stats.elapsed_ms} ms)")
    typer.echo(f"Connectivity check: {'OK' if rep.ok else 'MISMATCH'}")
    for d in s.diagnostics:
        typer.echo(f"  note: {d}")
    if out:
        Path(out).write_text(s.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"Wrote {out}")
    if not rep.ok:
        raise typer.Exit(code=1)


@schematic_app.command("svg")
def schematic_svg(design_file: str, out: str = typer.Option(..., "--out", "-o", help="SVG output path")) -> None:
    """Render a design's schematic to a standalone SVG file."""
    from schematic import generate_schematic
    from schematic.svg import render_svg
    s = generate_schematic(_load_design(design_file), get_default_registry())
    Path(out).write_text(render_svg(s), encoding="utf-8")
    typer.echo(f"Wrote {out}")


@schematic_app.command("verify")
def schematic_verify(design_file: str) -> None:
    """Check that the drawn schematic's connectivity equals the engineering nets."""
    from schematic import generate_schematic, verify_schematic
    design = _load_design(design_file)
    rep = verify_schematic(generate_schematic(design, get_default_registry()), design)
    typer.echo("OK" if rep.ok else json.dumps(rep.as_dict(), indent=2))
    if not rep.ok:
        raise typer.Exit(code=1)


@design_app.command("explain")
def design_explain(design_file: str) -> None:
    """Deterministic explanation: parts, rails, signals, checks performed, limitations."""
    from studio import StudioService
    state = StudioService(get_default_registry()).open_design(_load_design(design_file))
    ex = state.explanation
    typer.echo(f"{state.document.design.name}: {ex['summary']}")
    typer.echo(f"Validation: {ex['status']}  ({sum(1 for c in ex['checks'] if c['outcome'] != 'NOT_APPLICABLE')} checks applied)")
    typer.echo("Parts:")
    for p in ex["parts"]:
        typer.echo(f"  {p['reference']:<5} {p['name']:<36} {p['role'] or p['what_it_does']}")
    typer.echo("Power rails:")
    for r in ex["power_rails"]:
        typer.echo(f"  {r['name']:<8} {', '.join(r['members'])}")
    for issue in ex["issues"]:
        typer.echo(f"  ! {issue['code']} {issue['message']}")
    for lim in ex["limitations"]:
        typer.echo(f"  - {lim}")


@design_app.command("function")
def design_function(design_file: str, intent_file: Optional[str] = typer.Option(None, "--intent", "-i",
                    help="FunctionalIntent JSON (default: data/examples/intents/<name>.json if present)")) -> None:
    """Deterministic functional check: does the design do what the intent asks?"""
    from functional import FunctionalIntent, validate_function
    design = _load_design(design_file)
    path = Path(intent_file) if intent_file else Path("data/examples/intents") / Path(design_file).name
    intent = FunctionalIntent.model_validate(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None
    r = validate_function(design, intent, get_default_registry())
    typer.echo(f"{r.summary}  [{r.status}]")
    for f in r.findings:
        typer.echo(f"  {f.code} {f.status:<13} {f.message}")
        if f.repair_hint:
            typer.echo(f"      hint: {f.repair_hint}")
    for line in r.explanation or [i.statement for i in r.inferred]:
        typer.echo(f"  - {line}")
    if r.status == "FAIL":
        raise typer.Exit(code=1)


# ── Physical projection (breadboard build) ─────────────────────────────

physical_app = typer.Typer(help="Physical projection: breadboard build, 3D scene data, physical verification",
                           no_args_is_help=True)
app.add_typer(physical_app, name="physical")


def _physical(design_file: str, board: str):
    from physical import PhysicalLayoutState, generate_physical
    design = _load_design(design_file)
    return generate_physical(design, get_default_registry(), PhysicalLayoutState(board=board))


@physical_app.command("build")
def physical_build(design_file: str,
                   out: Optional[str] = typer.Option(None, "--out", "-o", help="Write the Physical IR JSON here"),
                   board: str = typer.Option("auto", "--board", help="auto | half | full")) -> None:
    """Project a design onto a breadboard and print a summary (or write the Physical IR)."""
    proj = _physical(design_file, board)
    if out:
        Path(out).write_text(proj.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"Wrote {out}")
    s, v = proj.stats, proj.verification
    typer.echo(f"{proj.name}: {proj.board.name if proj.board else 'no physical form'} · {s.parts_on_board} on the board, "
               f"{s.parts_offboard} beside it, {s.wires} wires, {s.leads} leads, {s.wire_length_mm:.0f} mm of wire "
               f"({s.elapsed_ms:.0f} ms) · physical check {v.status}")


@physical_app.command("verify")
def physical_verify(design_file: str, board: str = typer.Option("auto", "--board", help="auto | half | full")) -> None:
    """Check that the breadboard build's connectivity equals the engineering nets (physical LVS)."""
    proj = _physical(design_file, board)
    v = proj.verification
    typer.echo(f"{v.status}: {v.summary}")
    for f in v.findings:
        typer.echo(f"  [{f.severity}] {f.code} {f.message}")
    if not v.ok:
        raise typer.Exit(code=1)


@physical_app.command("steps")
def physical_steps(design_file: str, board: str = typer.Option("auto", "--board", help="auto | half | full")) -> None:
    """Print step-by-step assembly instructions for the breadboard build."""
    proj = _physical(design_file, board)
    for step in proj.assembly:
        typer.echo(f"{step.step:3d}. {step.text}")


# ── Studio server ───────────────────────────────────────────────────────

studio_app = typer.Typer(help="2D Schematic Studio (web workspace)", no_args_is_help=True)
app.add_typer(studio_app, name="studio")


@studio_app.command("serve")
def studio_serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind (keep 127.0.0.1 unless you know why)"),
    port: int = typer.Option(8765, "--port", "-p"),
) -> None:
    """Serve the studio API and the built frontend (frontend/dist)."""
    from studio.server import create_server
    server = create_server(host, port)
    typer.echo(f"Illustration Engine Studio on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("\nStopped.")
    finally:
        server.server_close()


import shutil
import subprocess
import os

render_app = typer.Typer(help="Render DesignProjects in browser")
# We just need to register this to the main app, which we will do in src/cli/main.py

@render_app.command("web")
def render_web(
    project_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        help="Path to the DesignProject JSON file"
    )
) -> None:
    """Launch the browser-based visualization for a given DesignProject."""
    frontend_dir = Path(__file__).parent.parent.parent / "frontend"
    public_dir = frontend_dir / "public"
    public_dir.mkdir(exist_ok=True)
    
    dest = public_dir / "project.json"
    shutil.copy(project_file, dest)
    typer.echo(f"Exported {project_file} to frontend.")
    
    typer.echo("Starting frontend development server...")
    try:
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "run", "dev"], cwd=str(frontend_dir), check=True)
    except KeyboardInterrupt:
        typer.echo("\nServer stopped.")
    except Exception as e:
        typer.echo(f"Failed to start frontend: {e}", err=True)

@render_app.command("export")
def render_export(
    project_file: Path = typer.Argument(..., exists=True),
    out_dir: Path = typer.Option(Path("frontend/public"), "--out", help="Output directory")
) -> None:
    """Export the DesignProject JSON for the frontend to consume statically."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "project.json"
    shutil.copy(project_file, dest)
    typer.echo(f"Exported {project_file} to {dest}.")

app.add_typer(render_app, name='render')


if __name__ == "__main__":
    app()
