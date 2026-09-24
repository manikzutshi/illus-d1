# Illustration Engine

**Describe an electronic circuit in plain language and get a real, verified schematic that you can
inspect, understand and edit.**

Illustration Engine is an AI-assisted electronics design and teaching tool. A language model plans a
circuit from a curated component and knowledge library. Deterministic engineering software then
decides whether the design is electrically sound, whether it does what was asked, and how it is
drawn. The result opens in an interactive 2D Schematic Studio in the browser.

> **AI proposes. Deterministic systems verify.**

Current milestone: **2D Schematic Studio + functional validation** (see [Roadmap](#roadmap)).

---

## The problem

Generative AI can produce circuit descriptions that look right and are wrong. It invents parts or
pins, wires a buzzer that can never sound, reverses an LED, or reads an active-low sensor as
active-high. Hand-drawn or AI-drawn diagrams can also silently disagree with the netlist they claim
to show. For education this is worse than useless, because the learner has no way to tell.

Illustration Engine keeps the AI in the role it is good at (understanding a request and proposing
an architecture) and hands every judgement to deterministic, testable code:

* the parts must exist in the registry, with their real pins and ratings;
* the design must pass electrical rule checks;
* the design must **functionally** implement the requested behaviour, in the requested direction;
* the drawing is generated from the design, never by the AI, and is checked back against the
  netlist (schematic LVS).

## Architecture

```
Natural language
  → Requirements + Functional Intent      AI extracts WHAT the circuit must do (kept apart from the design)
  → AI planning                           tool calls: library, patterns, calculators, validate_design
  → Component / knowledge ecosystem       registry · design patterns · calculators · functional profiles · curriculum
  → Engineering Design IR                 parts, pins, nets, parameters, logic rules  (connectivity source of truth)
  → Electrical validation                 E001–E019 / W001–W007, deterministic
  → Functional validation                 F001–F011 / F101–F106, deterministic signal-flow analysis
        ↺ repair loop: coded findings + repair hints + patterns go back to the AI until both pass
  → Deterministic schematic generation    symbols, placement, orthogonal routing, junctions, ports
  → Schematic LVS                         drawn connectivity == engineering nets
  → Interactive 2D Schematic Studio       view · inspect · edit · explain · export
```

| Layer | Code |
|---|---|
| AI orchestration and repair loop | `src/ai/orchestrator.py`, `src/ai/tools.py` |
| Provider abstraction (Gemini REST, OpenAI-compatible, mock) | `src/ai/provider.py`, `src/ai/factory.py`, `src/ai/provider_gemini.py`, `src/ai/provider_openai.py` |
| Engineering Design IR (Pydantic) | `src/core/models.py`, `src/core/enums.py`, `src/core/units.py` |
| Component registry | `src/components/`, `data/components/registry.yaml`, `data/components/library/` |
| Design patterns | `src/knowledge/`, `data/knowledge/patterns.yaml` |
| Calculators | `src/validation/calculations.py` |
| Electrical validation | `src/validation/engine.py` |
| Functional validation | `src/functional/`, `data/knowledge/functional_profiles.yaml`, `data/knowledge/functional_vocabulary.yaml` |
| Schematic projection, layout, SVG, LVS | `src/schematic/` |
| Studio document, edit operations, HTTP API | `src/studio/` |
| Studio web app (React + TypeScript + Vite) | `frontend/src/studio/` |
| Curriculum knowledge graph | `src/curriculum/`, `data/curriculum/` |
| CLI (Typer) | `src/cli/main.py` |

## Core philosophy

**AI proposes. Deterministic systems verify.**

* The AI never draws, never decides validity and never grades its own design.
* Unknown parts are rejected, not hallucinated. Missing numeric requirements are kept symbolic
  (`<UNSPECIFIED>`) or clarified, not invented.
* Every verdict is reproducible, carries a code, names the affected parts, pins and nets, and comes
  with a repair hint.
* When something cannot be checked, the answer is **NOT CHECKABLE**, never a guess.

## Current capabilities

* **Natural-language circuit generation.** Prompt → requirements and functional intent → a
  registry-grounded design, with an automatic validate → repair loop.
* **Component registry.** 86 component types with real pins, electrical types, ratings, roles,
  driver requirements, design constraints, symbols and teaching notes.
* **Design patterns.** 16 reusable, instantiable circuit fragments (e.g. `bjt_low_side_switch`,
  `comparator_threshold`, `i2c_bus_pullups`, `flyback_protection`, `h_bridge_driver`).
* **Calculators.** 6 deterministic calculators: LED series resistor (E24), voltage divider, RC time
  constant, BJT base resistor, 555 astable, non-inverting gain.
* **Deterministic electrical validation.** Unknown parts or pins, duplicates, power and ground,
  LED resistors, voltage compatibility, level shifting, series-resistor constraints and more.
  Results carry codes and list the checks that were run.
* **Functional / behavioural validation.** Does the requested input reach the requested output
  through a decision stage, in the requested direction (ON *above* vs *below*), with an adjustable
  threshold, a driver where required, enough drive current, and no reversed loads? Firmware
  behaviour is taken from the design's logic rules.
* **Schematic layout engine.** Deterministic placement and orthogonal routing with junctions, rail
  and ground ports, and full traceability from every drawn element to its engineering origin.
* **Schematic LVS.** Verifies the drawing's connectivity equals the engineering nets.
* **Interactive 2D workspace** in the browser (see below), with component library and search,
  explanations, electrical and functional feedback, editing with undo/redo, auto-arrange, and
  SVG / IR export.
* **Gemini integration** through a REST provider with a model fallback chain. The key is read
  from `GEMINI_API_KEY`, never stored or logged.
* **Provider abstraction.** A single `ModelProvider` interface; Gemini, OpenAI-compatible and mock
  providers; no vendor SDK dependency.

## Component and knowledge ecosystem

| Asset | Count | Notes |
|---|---|---|
| Component types | **86** | 69 physical parts + 17 idealised primitives, in 53 families |
| Design patterns | **16** | ports, purpose, instantiable into a design |
| Calculators | **6** | exposed to the AI as tools and in the CLI |
| Functional profiles | every registry part | family profiles + per-part overrides; honest derived fallback |
| Curriculum concepts | **53** | in **23** modules (14 core + 9 industry/specialisation) |
| Reference designs | **12** | `data/examples/`, 10 with functional intents in `data/examples/intents/` |

Physical parts span passives, diodes and LEDs, BJTs and MOSFETs, op-amps and comparators, the 555,
74HC logic, regulators, ADC/DAC, EEPROM, drivers (ULN2003, L293D), sensors (LM35, DS18B20, DHT,
LDR, thermistor, PIR, HC-SR04, MQ-2, MPU-6050, encoder), actuators (buzzer, motor, servo, relay,
OLED/LCD), connectors, power sources, and boards (Arduino Uno, ESP32, Raspberry Pi Pico).

## Curriculum integration

The knowledge base is mapped to an industry-oriented VLSI and electronics curriculum blueprint and
deliberately keeps four kinds of knowledge apart:

| Kind | What it is | Examples | Where |
|---|---|---|---|
| **Physical components** | Real, buyable parts with packages and ratings | BC547, LM393, LM35, Arduino Uno | registry, `object_type: PHYSICAL` |
| **Idealised primitives** | Textbook elements for teaching and gate/transistor-level circuits; not buyable | ideal NMOS/PMOS, ideal op-amp, AND/NAND/XOR gates, D flip-flop, ideal DC source | registry, `object_type ≠ PHYSICAL` (`primitive:*`) |
| **Design patterns** | Reusable circuit idioms built from components | low-side transistor switch, comparator threshold, I²C pull-ups | `data/knowledge/patterns.yaml` |
| **Engineering concepts** | Higher-level ideas, methods and processes | CMOS inverter operation, static timing, DFT, fabrication | curriculum graph, by kind and abstraction level (device → circuit → gate → RTL → system …) |

Parts and patterns link to the concepts they teach, so a schematic can point a learner at the
underlying idea.

## The 2D Schematic Studio

```
┌ Illustration Engine · Schematic Studio   [✓ valid] [✓ function]   Select · Wire · ↶ ↷ · Fit · Auto-arrange · Export SVG · Export IR ┐
│ AI Assistant │ Library │ Examples  │            Schematic canvas             │ Inspector │ Function │ Electrical │ Explain │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

* **AI Assistant.** Describe a circuit. Progress shows each step: the required behaviour, library
  lookups, "Functional check → FAIL: F006 …", repairs. The result opens on the canvas.
* **Library and Examples.** Search the registry and add parts or whole patterns; open any
  reference design.
* **Schematic canvas.** Pan and zoom; select parts and nets; the status bar shows
  "drawing matches netlist ✓".
* **Inspector.** Part identity, role, pins and their nets (disconnect with ✕), editable
  parameters, registry electrical characteristics, rotate, mirror, delete.
* **Electrical.** Validation errors and warnings with codes, highlighted on the drawing.
* **Function.** The requested behaviour, the verdict, the signal path (click to highlight), the
  decision, driver and threshold parts, findings with repair hints, and any interpretation of the
  intent.
* **Explain.** A deterministic explanation of parts, rails, signals, checks performed and
  limitations.
* **Editing.** Wire tool, move, rotate, mirror, add, delete, rename nets, set parameters, insert
  patterns. Every edit is a registry-checked engineering operation, followed by re-validation and
  re-projection. Full undo/redo.
* **Auto-arrange** re-runs the deterministic layout. **Export** gives SVG (drawing) or IR (the
  engineering design JSON).
* *Physical preview (3D, experimental)* is a pre-existing prototype tab, not part of this milestone.

## Architectural invariants

1. **The Engineering Design is the connectivity source of truth.** Parts, pins, nets, parameters
   and logic rules live only there.
2. **The schematic is a projection.** It is generated deterministically from the design and can be
   regenerated at any time; layout hints never change connectivity.
3. **The UI does not own engineering truth.** The browser sends edit operations; the backend applies
   them to the design, validates and re-projects.
4. **Deterministic validation gates AI output.** A design is accepted only with electrical PASS
   and no functional FAIL.
5. **Schematic LVS checks the drawing against the netlist** on every projection.
6. **The provider abstraction stays intact.** Callers name a provider and model; vendor code sits
   behind `ModelProvider`.

## Quick start (Windows, as used in development)

Requirements: Python ≥ 3.11, Node.js (for building the frontend), and optionally a Gemini API key.

```powershell
cd illustration-engine
python -m venv .venv
.\.venv\Scripts\pip install -e .            # runtime: typer, pydantic, pyyaml
.\.venv\Scripts\pip install pytest websockets  # tests; websockets only for the browser E2E

cd frontend
npm install
npm run build                                # produces frontend/dist
cd ..

.\studio                                     # launcher -> http://127.0.0.1:8765
# equivalent: .\.venv\Scripts\python.exe -m cli.main studio serve [--port 8765]
```

For AI generation, set `GEMINI_API_KEY` in the environment of the shell that starts the studio. The
examples, library, editing and validation all work without a key.

> Use the project's virtual environment. The system Python does not have the dependencies, so
> `python -m cli.main …` outside the venv fails with `No module named 'cli'`.

Frontend development with hot reload: start the server as above, then `cd frontend && npm run dev`.
Vite proxies `/api` to port 8765.

### Command line

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m cli.main component list | search <text> | show <component_type_id>
& $py -m cli.main design validate data/examples/relay_driver.json      # electrical rules
& $py -m cli.main design function data/examples/temperature_alarm.json  # functional check (intent from data/examples/intents/)
& $py -m cli.main design explain  data/examples/temperature_monitor.json
& $py -m cli.main schematic svg      data/examples/cmos_inverter.json -o cmos.svg
& $py -m cli.main schematic verify   data/examples/relay_driver.json    # schematic LVS
& $py -m cli.main calc led-resistor --supply 3.3 --vf 2.0 --current 10
& $py -m cli.main curriculum search "CMOS inverter"
& $py -m cli.main agent run "night light with an LDR and a 9 V battery" -v   # needs GEMINI_API_KEY
```

## Testing

Verified on 2026-09-25 for this milestone:

| Suite | Command | Result |
|---|---|---|
| Python unit and integration | `.\.venv\Scripts\python.exe -m pytest` | **460 passed, 5 skipped** (the skips are opt-in live-provider tests) |
| Frontend unit | `cd frontend && npm test` | **13 passed** (includes backend ↔ frontend geometry consistency) |
| TypeScript | `cd frontend && npx tsc -b` | **clean** |
| Browser E2E (real Chrome via DevTools protocol) | `.\.venv\Scripts\python.exe scripts\ui_e2e.py --url http://127.0.0.1:8765` (server running) | **16/16** |
| Live Gemini (opt-in, spends quota) | `$env:ILLUS_LIVE_TESTS=1; .\.venv\Scripts\python.exe -m pytest tests/integration/test_gemini_live.py` | not part of the default run |

The functional layer has 28 fixture designs. All are electrically valid, and each isolates one
functional property; ten reproduce real mistakes from live Gemini output. Reports `reports/16`–`24`
document the design decisions and verification in detail.

## Known limitations

* **Intent extraction is done by the AI.** A wrongly extracted intent is enforced faithfully. The
  Function tab shows the intent so a user can spot and correct it.
* **Firmware is only what the logic rules say.** Microcontroller code is not analysed. Rules name
  parts, not pins; a missing rule makes the behaviour NOT CHECKABLE.
* **No simulation.** Checks are topology, ratings and signs; there are no voltage levels, timing,
  gain, hysteresis or frequency. Drive-strength checks are estimates.
* **Validator gaps.** No floating-input, current-budget or thermal rules yet.
* **Layout** is greedy placement with local refinement; there is no hierarchical grouping of large
  designs yet.
* **No conversational refinement** of an existing design by the AI yet (edits are manual).
* The **3D / physical view** is an older experimental prototype and is not maintained in this
  milestone.
* Development and verification were done on Windows. Other platforms are expected to work but have
  not been verified.
* Live AI behaviour has been sampled on a limited set of prompts with the Gemini flash tiers.

## Roadmap

| Stage | Status |
|---|---|
| Deterministic foundation: Design IR, registry, electrical validation, calculators | done |
| AI orchestration with tool calling, validation boundaries and repair | done |
| **2D Schematic Studio**: layout engine, schematic LVS, interactive workspace, library expansion, curriculum mapping | **done (current)** |
| **Functional / behavioural validation**, integrated into the repair loop and the studio | **done (current)** |
| **Physical / 3D Electronics Studio**: breadboard and physical layout projected from the same Engineering Design, with physical ↔ netlist verification | **next major stage, not started** |
| Simulation (SPICE / microcontroller), richer educational workflows (guided labs, misconception feedback, curriculum paths), conversational design refinement, more providers | future |

## Repository layout

```
illustration-engine/
├── src/            ai · cli · components · core · curriculum · functional · knowledge · schematic · studio · validation
├── data/           components (registry + library) · knowledge (patterns, functional profiles, vocabulary) · curriculum · examples
├── frontend/       React + TypeScript studio (Vite); built output in frontend/dist
├── tests/          unit · integration · fixtures (golden, functional, AI-generated/rejected)
├── scripts/        fixture generators · browser E2E
├── docs/           architecture notes · ADR-001 … ADR-006
├── reports/        audit and stage reports 00–25
└── studio.cmd      Windows launcher for the studio
```
