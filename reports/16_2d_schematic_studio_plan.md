# 16 — 2D Schematic Studio: Reconnaissance & Plan

Stage: merged "Phase 2 Schematic Layout Engine" + "Phase 3 2D Schematic Viewer/Editor".
Date: 2026-09-24.

## 1. What was inspected

All of `src/` (core, components, curriculum, validation, ai, cli, schematic, design), all of
`tests/`, `data/`, `frontend/src/`, `docs/`, reports 00–15, the run traces in `runs/`, and
`Industry_Ready_VLSI_Curriculum_Blueprint.docx` (text extracted, 757 paragraphs).

## 2. Verified facts (checked against source, not reports)

| Claim | Verified result |
|---|---|
| Test suite 140 passed / 3 skipped | **True** (`pytest -q`, 8.3 s). The 3 skips are OpenAI live tests (no `OPENAI_API_KEY`). |
| Frontend tests | 4 vitest tests pass, `tsc -b` clean. |
| Report 15: "Schematic generation tests pass" | **False.** No test references the schematic module. `src/schematic/models.py` cannot even be imported: it uses `from ..core.models` (relative import beyond the top-level package, because `src/` is the import root) and references `PinDirection` without importing it. |
| Report 14 (IR/schematic architecture review) | The file is a verbatim duplicate of `00_master_audit.md`; the actual review content is only summarised inside 00. |
| Registry symbol metadata (`symbol_library/symbol_name`) | Fields exist on `ComponentType`, **no registry entry sets them.** |
| Gemini provider | Works (run traces show completed live runs), but its default model `gemini-1.5-flash` is no longer offered by the API. Key is sent as a URL query parameter. `GEMINI_API_KEY` exists in the Windows *User* environment; this agent's process did not inherit it, so live runs inject it into child processes without printing it. |
| 2D view | `frontend/src/components/Schematic2D.tsx` is a canvas projection of 3D breadboard coordinates: boxes + polylines, no symbols, no pin geometry, no interaction. |
| Frontend data path | Static `public/project.json` copied by `render web`; no backend API exists. |

Other observations relevant to this stage:

* Validator rules key off string prefixes (`passive:resistor`, `passive:led`) and treat any
  `POWER_SOURCE` component's first POWER pin as the rail voltage (a 3.3 V `power-rail`
  parameter is ignored: the rail pin's `max_voltage` 5.0 is used).
* `passive:push-button-tactile` declares `max_current: 50mA`; the GPIO drive-limit check (E015)
  sums `max_current` as a *load*, so a button on a GPIO net is treated as a 50 mA load — a latent
  false positive caused by ambiguous property naming.
* Registry search is a single substring match — "temperature sensor" does not find the DHT11
  whose description says "temperature and humidity sensor".
* `tests/unit/test_orchestrator.py` defines several test functions twice (later definitions
  shadow earlier ones).
* Curriculum store holds 8 concepts; the blueprint defines a 14-module backbone plus a
  40-domain knowledge architecture.

## 3. Mental model

```
NL prompt ─► Orchestrator (provider-neutral) ─► requirements ─► tool loop (registry, curriculum,
calculators, validate) ─► EngineeringDesignProject ─► DesignValidator ─► repair loop
                                   │
                                   ▼  (this stage)
                 deterministic schematic projection ─► 2D Studio (view/inspect/edit)
                 (future) deterministic physical projection ─► 3D / breadboard
```

The engineering IR (`EngineeringDesignProject`) is the only source of connectivity truth. It is
good enough to keep: components reference registry types, nets are lists of `instance.pin`.

## 4. Architecture decisions for this stage

1. **Schematic = pure projection.** `schematic = project(design, registry, layout_state)`.
   The schematic is never edited directly. `layout_state` holds *presentation only*
   (placement, rotation, mirror, per-net wire/label style) and has no connectivity.
2. **Edits are operations on the engineering design.** A typed, atomic op set
   (`add_component`, `remove_component`, `set_parameter`, `connect`, `disconnect`,
   `rename_net`, …) mutates the engineering IR, then validation and projection re-run.
   Presentation ops (`move`, `rotate`, `mirror`, `set_net_style`) only touch `layout_state`.
3. **Symbols are data.** A Python symbol library produces symbol definitions (graphics
   primitives + pins with grid positions and orientation). The schematic JSON embeds the symbol
   defs it uses, so the frontend is a generic renderer with no per-part code.
4. **Integer grid geometry.** All pins, placements and wire vertices are integers in grid units.
   Output is byte-stable for identical input.
5. **Layout engine is layered and replaceable:** classification (power/ground/signal nets) →
   orientation scoring → pin-directed greedy placement with collision avoidance → bend- and
   crossing-aware A* orthogonal routing with net-label fallback → junctions → labels.
6. **Schematic LVS.** A verifier extracts connectivity *from the drawn geometry alone* (wire
   endpoints, T-junctions, labels, power ports) and compares it with the engineering nets. This
   proves the picture cannot silently diverge from engineering truth.
7. **Power/ground nets are drawn as ports** (standard schematic practice), signal nets as wires.
8. **Knowledge ecosystem separates kinds:** physical parts, idealised circuit/digital primitives,
   reusable design patterns (functional blocks built from parts), and curriculum concepts
   (non-physical: RTL, CDC, UVM …). Nothing non-physical is forced into the part registry.
9. **Backend API via stdlib `http.server`** (no new Python dependencies), bound to 127.0.0.1.
   The API key stays server-side.
10. **Frontend:** existing React/Vite/TS stack, SVG rendering, no new UI frameworks. Existing 3D
    breadboard view kept as a secondary "Physical preview" tab.

## 5. Plan (executed in this order)

1. Core model extensions (backward compatible) + registry multi-file loading + ranked search.
2. Schematic engine (symbols, geometry, placement, routing, junctions, labels, verifier, SVG export).
3. Library expansion + design patterns + curriculum graph.
4. Validator: supply-role aware power checks, metadata-driven constraint checks, `checks_run`.
5. Studio backend: document, edit ops, service, HTTP API, CLI.
6. AI layer: provider factory, Gemini default model/header auth, catalog/pattern/calculator tools.
7. Frontend Schematic Studio.
8. Verification (unit, integration, live Gemini, headless screenshots) and reports 17–21.
