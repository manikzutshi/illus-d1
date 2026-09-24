# 17 — Schematic Layout Engine

Package: `src/schematic/` (replaces the non-importable `src/schematic/models.py` of report 15).

## 1. What existed

`generate_schematic_from_engineering()` placed components on a 4-column grid with 3 mm spacing,
drew every net as "horizontal then vertical" lines from the first pin's *component origin* (not
from pins), used `PinDirection` without importing it, and could not be imported at all
(`from ..core.models` beyond the top-level package). No tests referenced it. It was a sketch, not
a starting point worth preserving; its public name is kept as a compatibility wrapper.

## 2. Architecture

```
EngineeringDesignProject + ComponentRegistry + LayoutState
        │
        ▼  netclass.py      power / ground / signal nets, display names (+5V, GND), voltages
        ▼  symbols.py       fixed symbols (37) or generated IC boxes; engineering pin → symbol pin map
        ▼  placement.py     pin-directed growth placement, orientation scoring, box pin sides,
        │                   collision avoidance, orientation refinement, stable kept placements
        ▼  engine.py        ports & net labels, router set-up, refs/values, traceability index
        ▼  routing.py       bend/crossing-aware A* on the integer grid, label fallback
        ▼  verify.py        connectivity extracted from geometry == engineering nets ("schematic LVS")
        ▼  svg.py           standalone SVG export (CLI / docs / visual checks)
SchematicProject (IR 0.2.0): components, wires, junctions, power_ports, net_labels,
                              symbols, nets (traceability), bounds, stats, diagnostics
```

**Coordinates.** Everything is on an integer grid (grid units, y down). Symbol pin tips are
integers; transforms are mirror → rotate (0/90/180/270, clockwise on screen) → translate, so every
placed pin is an integer point and output is byte-identical for identical input.

**Symbols are data** (`SymbolDef`: primitives + pins with tip, outward orientation, length). The
schematic JSON embeds the symbols it uses, so the browser is a generic renderer; the Python SVG
exporter and the React renderer consume the same definitions. The registry maps parts to symbols
through `ComponentType.symbol = {name, pin_map, ref_prefix, box_sides}`; a bad mapping raises
(and falls back to a box with a diagnostic) instead of drawing a wrong symbol.

Fixed symbols: resistor, photoresistor, thermistor, potentiometer, capacitor (plain/polarised),
inductor, diode/zener/Schottky/LED, NPN/PNP, NMOS/PMOS, op-amp, AND/OR/NAND/NOR/XOR/XNOR/NOT/BUF,
D flip-flop, push buttons (2/4-pin), SPST, battery, ideal DC source, motor, buzzer, regulator,
jumper, logic in/out ports, power & ground flags. Everything else gets a generated IC box (part name
inside, pin labels, optional hidden unused pins with a "+N unused pins" note).

## 3. Placement algorithm (placement.py)

Chosen because it reproduces how people draw schematics and generalises to any topology:

1. **Only signal nets pull parts together.** Power/ground nets are drawn as ports, so they impose no
   geometry. Parts form clusters over signal nets.
2. **Pin-directed growth.** Each cluster grows from a root (most signal-connected part, or any part
   the user placed). The next part attaches to an already-placed pin: it is put *in front of* that
   pin (pin's outward direction), oriented so its own pin faces back (straight wire) or is
   perpendicular (one bend), searched over gap and lateral offset until its **footprint** (symbol +
   pins + reference/value text + power-port graphics, + clearance) collides with nothing.
3. **Orientation scoring** over all 8 rotations/mirrors: ground pins down, supply pins up, other
   signal pins toward their placed neighbours, mild penalties for mirroring/rotation.
4. **IC boxes, two passes.** Pass 1 assigns pin sides from roles (sensor/input → left,
   actuator/output → right, through series passives up to depth 3), supply top, ground bottom. Pass 2
   re-assigns sides from where neighbours actually landed and orders pins by neighbour height (same-net
   pins stay adjacent). Registry `box_sides` fixes sides where convention demands (555, relays, headers).
5. **Orientation refinement.** A local-improvement pass re-evaluates each free part's 8 orientations
   against estimated wirelength (distance to connected-pin centroids + a detour penalty for pins facing
   away) plus the orientation score; accepted only if collision-free and strictly better.
6. **Support row.** Parts with no signal connection (supply sources, decoupling caps, flags) are placed
   in a row below.
7. **Stability.** Placements the user made (`locked`) are fixed; placements kept from the previous
   projection are fixed but nudged to the nearest free spot if a symbol changed size. So editing a
   design does not reshuffle the drawing; "Auto-arrange" clears them.

Footprints are memoised per (symbol, rotation, mirror) — this took the worst reference design from
~1.95 s to ~60 ms.

## 4. Routing (routing.py)

Each routable signal net is a Prim-style tree: the terminal nearest the tree is joined by A* over
states (point, heading) with costs: step 1, bend 4, crossing another net 7, near a body 1.5.
**Hard rules** — anything that would make the drawing imply a wrong connection is forbidden:
entering bodies, pin lines, text boxes, port/label graphics; touching another net's node (pin tip,
corner, wire end); running collinear with, or turning on, another net's wire; ending on a tree point
that is itself a crossing. Perpendicular crossings are allowed (they are not connections). If a net
cannot be routed, it is ripped up and drawn with net labels at every pin (recorded in
`stats.label_fallback_nets` and `diagnostics`). Users can force label style per net.

Edges are merged into maximal straight segments split at corners, branches and pin tips. A junction
dot is emitted exactly where ≥3 wire ends/pins meet.

## 5. Power, labels, references

* Nets with a GROUND pin → `GND` ground ports; nets with a supply-source pin (registry `supply:
  source`, or legacy POWER_SOURCE parts) → power ports named from the *authoritative* voltage
  (`+3.3V`, `+5V`, `+9V`); unknown voltage → the net id. Port names are made unique because ports
  connect by name.
* Rail primitives (`primitive:power-rail/ground-rail`) are drawn *as* flags carrying the net name.
* Reference designators: prefix from the registry/symbol (R, C, D, Q, U, SW, BT, …); an instance id
  that already reads like a designator (`r1`, `q1`) keeps its number; others take the next free number
  in design order (stable under moves).
* Values: `resistance/capacitance/inductance/voltage` formatted with SI prefixes (`4.7kΩ`, `100nF`),
  LED colour, else the part's short name.
* Reference/value text is placed by trying candidate positions (right, above/below, left, corners)
  and taking the first that avoids the part's own pins and ports.

## 6. Traceability

Every component carries `instance_id`/`component_type_id`; every pin its engineering `pin_id` and
`net_id`; every wire/junction/port/label its `net_id` (ports/labels also `pin_ref`). `schematic.nets`
indexes, per engineering net, its pins, wires, junctions, ports and labels. Visual object →
schematic object → engineering object is always one lookup.

## 7. Verification ("schematic LVS")

`verify_schematic` rebuilds connectivity from geometry alone (endpoint-on-segment unions, crossings
don't connect, ports/labels connect by text) and compares it with the engineering nets: *opens*
(a net split across drawn groups), *shorts* (a drawn group spanning nets or stray pins), and hygiene
(symbol overlap, wires through bodies, references to unknown ids). It runs on every studio state,
and its result is shown in the UI ("drawing matches netlist ✓").

## 8. Results

On the 13 reference designs (11 new examples + 2 golden fixtures): all LVS-clean, 0 overlaps,
**total 5 wire crossings** (half adder 1 — inherent; 555 1; op-amp 1; others 0), 0 label fallbacks,
6–200 ms per layout. Visual checks were done by rendering SVG → PNG in headless Chrome after every
algorithm change; defects found that way (and fixed) included flags rotated 180°, wires through
value text, box value text crowding channels, port graphics missing from footprints, sideways ground
ports, and a sensor box that could not attach to a same-facing pin.

## 9. Tests — `tests/unit/test_schematic_engine.py` (117 tests)

Geometry transforms; every fixed symbol grid-aligned with tips outside the body; box symbols;
every registry part maps bijectively to its symbol; LVS for all designs; every signal pin attached to
a wire/label, every rail pin to a port; orthogonal integer wires; determinism (twice → identical);
component-order independence; crossing budget; speed; exactly one junction on a 3-way node; none on
2-pin nets; port names from voltages; rail flags; unique/prefixed references; value formatting;
ground pins of 2-terminal parts point down; traceability index == engineering nets; JSON round-trip;
locked placement respected; stability when a part is added; forced label style; unknown part type →
box + diagnostic; nets to missing instances don't crash; the verifier detects injected opens and
shorts; router avoids bodies, never shares nodes/edges with another net, reports unroutable nets.

## 10. Limitations / next steps

* Placement is greedy + local refinement, not global optimisation; dense MCU designs with many
  peripherals will need hierarchical grouping (by design pattern) and a crossing-minimising
  improvement loop (e.g. pin-order swaps with re-route cost).
* Wires are not user-editable waypoint by waypoint (routing is derived); users steer layout by
  moving/rotating parts and choosing wire vs label per net.
* Multi-unit parts (e.g. the 4 gates of a 74HC00) are drawn as one box.
* No sheet hierarchy / multi-page schematics yet.
