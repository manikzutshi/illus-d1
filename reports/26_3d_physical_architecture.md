# 26 — Physical / 3D Electronics Studio: Architecture

Stage: Physical / 3D Electronics Studio, first vertical slice. Date: 2026-09-25.
Baseline protected: tag `v0.2.0-2d-studio` (460 Python passed / 5 skipped, 13 frontend, tsc clean,
browser E2E 16/16). No Git operations were performed in this stage (the owner manages Git).

## 1. What was inspected (read-only reconnaissance, before any change)

* **Engineering IR** (`src/core/models.py`): `ComponentType.physical: PhysicalSpec` (package,
  mounting, breadboard_compatible, pin_pitch_mm, body_mm, asset_3d) already existed, together with
  pin `number`s. Instances carry no physical data (correct: connectivity only).
* **Registry coverage (measured):** 69 physical types, 40 with a `physical` block, 29 without (the
  original core parts: LED, resistor, capacitors, ESP32, HC-SR04, buzzer, …); body sizes known for 2
  parts; pin numbers for 229 of 444 physical pins (mostly ICs). Nothing in `src/` consumed
  `physical` except one Inspector line.
* **2D stage pattern** (`src/studio/document.py`, `edits.py`, `service.py`, `server.py`): a studio
  document = engineering design + presentation state; every change is a registry-checked op;
  everything shown is derived per request; the server is stateless; the selection is expressed in
  engineering ids. This pattern was proven and is **retained** for the physical projection.
* **Existing 3D prototype** (frontend only):

| Piece | What it actually is | Decision |
|---|---|---|
| `frontend/src/core/PhysicalLayoutEngine.ts` | Hardcoded to one golden project: ESP32 at column 2, HC-SR04 at column 20, resistors recognised by instance id `r1`/`r3` or value `'1k'`/`'2k'`, everything else stacked in row A with no pin anchors | **REPLACE** (backend placement engine) |
| `frontend/src/core/SceneBuilder.ts` | Wires drawn point-to-point in net order; missing anchors fall back to the part centre | **REPLACE** (backend wiring + verification) |
| `frontend/src/core/BreadboardModel.ts` | Hole → coordinate mapping; no connectivity, rails not modelled | **REPLACE** (backend breadboard model with connectivity) |
| `frontend/src/core/assets.ts`, `components/Scene3D.tsx` | 4 hardcoded asset entries; per-part `if` branches; drei `Text` labels (fetch a font from a CDN, so they fail offline) | **REFACTOR** into a kind-keyed procedural asset registry with the GLB path kept |
| `frontend/public/models/*.glb` + `scripts/generate_glbs.py` | Trimesh boxes in "pitch units", no materials, not to scale | **REPLACE** by dimension-driven procedural geometry; files **DEFERRED** (left untouched, unused) |
| old `frontend/src/App.tsx`, `components/Schematic2D.tsx`, prototype vitest files | Not imported by the studio entry point | **DEFER** (untouched, documented as legacy) |
| `studio/components/PhysicalPreview.tsx` | Adapter from the studio to the old SceneBuilder | **REPLACE** by `studio/physical/PhysicalView.tsx`; file left untouched, no longer imported |
| `docs/architecture/physical-layout.md`, `asset-pipeline.md`, ADR-004/005 | Describe the prototype | Superseded by reports 26–32 (not edited) |

Nothing was deleted. The retained decision from ADR-005 — self-contained procedural geometry, no
downloaded community models — still holds; the new asset registry keeps `asset_url` for real models.

## 2. Architecture

```
                         Engineering Design (the only connectivity truth)
                         /                                   \
            Schematic projection                      Physical projection        (src/physical/)
        (src/schematic, report 17)          footprints (registry + data/physical/*.yaml)
                  |                          → rails → deterministic placement → off-board layout
             schematic LVS                   → leads + jumpers → Physical IR → physical verification
                  |                                              |
              2D Studio  ── shared selection (engineering ids) ── 3D Studio (Physical 3D tab, Assembly tab)
```

* **The engineering design stays the source of truth.** The Physical IR (report 27) is a derived,
  serialisable projection; every part, pin, lead and wire names the engineering instance / pin / net
  it realises. There is no independent 3D netlist.
* **The AI decides topology; deterministic code decides space.** The LLM never produces coordinates.
  The placement engine (report 28) places parts on a breadboard model (report 29) under hard
  electrical constraints (a strip or rail carries at most one net), then wires what the board does
  not already connect.
* **Physical verification** (report 31) rebuilds connectivity from the Physical IR alone and compares
  it with the netlist: the physical view can never silently disagree with the design.
* **Studio** (report 30): `StudioDocument.physical` holds user placements only; the projection is
  computed per request when the client asks for it (`physical: true`), so the 2D path is unchanged in
  cost. Physical ops (`physical_move`, `physical_rotate`, `physical_auto_arrange`, `set_breadboard`)
  are presentation ops validated by the placement engine itself.

## 3. Files

| Area | Files |
|---|---|
| Breadboard model | `src/physical/breadboard.py` |
| Physical knowledge (data, not code) | `data/physical/packages.yaml` (20 package templates), `data/physical/parts.yaml` (39 part entries) |
| Footprint resolution | `src/physical/footprints.py` |
| Physical IR | `src/physical/models.py` |
| Placement | `src/physical/placement.py` |
| Wiring | `src/physical/wiring.py` |
| Orchestration, assembly steps | `src/physical/engine.py`, `src/physical/visual.py` |
| Verification | `src/physical/verify.py` |
| Studio integration | `src/studio/document.py`, `service.py`, `server.py`, `edits.py` (+4 ops) |
| CLI | `physical build | verify | steps` in `src/cli/main.py` |
| 3D frontend | `frontend/src/studio/physical/{PhysicalView.tsx, assets.tsx, coords.ts, trace.ts}`, `components/{AssemblyPanel,PhysicalSection}.tsx` |
| Tests | `tests/unit/test_physical.py` (53), `frontend/src/studio/physical/physical.test.ts` (11), `scripts/ui_e2e.py` (+7 steps) |

## 4. Assumptions

* A standard solderless breadboard (half 400 / full 830 tie points) is the first physical target.
  Rails are modelled as continuous (some full-size boards split them; noted in the board info).
* Package facts (DIP 2.54 mm pitch, 7.62 mm rows; 2.54 mm headers; TO-92 formed to 2.54 mm) are
  standard; per-part facts carry their source (`datasheet | standard | typical | assumed`), and
  vendor-dependent pinouts carry a `variant_note` surfaced as warning P102.
* SMD-only parts are shown on a generic SIP breakout adapter (labelled assumption, warning P103).
* Parts whose geometry is unknown are shown as labelled generic modules (warning P101), never guessed.

## 5. Curriculum hooks (not built in this stage)

The Assembly steps, pin → hole tables and the physical verification findings are the material for
the curriculum's *inspect* and *debug* steps (component identification, "why is this strip one
node", "which jumper completes this net", "what would short if …"). The explicit geometry sources
support teaching the difference between a package standard and a vendor pinout.
