# 18 — 2D Schematic Workspace (Studio backend + frontend)

## 1. What existed

`frontend/` (React 19 / Vite 8 / TS / three.js) loaded a static `public/project.json`, built a 3D
breadboard scene, and drew a "2D schematic" by projecting 3D coordinates onto a canvas (boxes and
polylines). There was no backend API; `render web` copied a JSON file into `public/`.

## 2. Architecture decision: the UI is a view over derived state

```
Browser                                   Python (stdlib http.server, 127.0.0.1)
────────                                  ─────────────────────────────────────────
StudioDocument ──(document, ops)──► /api/edit ─► apply_ops (registry-checked, atomic)
   ▲                                              ├─ DesignValidator            (truth)
   │                                              ├─ generate_schematic         (projection)
   └────────────── StudioState ◄──────────────────├─ verify_schematic (LVS)
                                                  └─ explain_design             (no AI)
```

* **StudioDocument** = `EngineeringDesignProject` (only source of connectivity/parameters) +
  `LayoutState` (placement/rotation/mirror/net style — no connectivity) + provenance + revision.
* **Everything else is derived on every request**: validation, schematic, LVS result, explanation.
  The browser never edits the schematic or the netlist locally; every change is an **edit op**.
* The server is stateless for designs (the client sends its document); only AI jobs live in memory.
  No new Python dependencies; bound to 127.0.0.1; the API key never leaves the server.

## 3. Edit operations (`src/studio/edits.py`)

| Engineering ops | Presentation ops |
|---|---|
| add_component, remove_component, set_parameter, connect (create / extend / **merge** nets), disconnect, delete_net, rename_net, set_net_type, insert_pattern, set_design_info | move_component, rotate_component, mirror_component, set_net_style (wire/label), set_show_all_pins, auto_arrange |

Rules: engineering ops are checked against the registry first — unknown part types, unknown pins,
unknown parameters and unparseable values (`"banana"` for a resistance) are rejected with a coded
`EditError` (HTTP 422). They may create an *electrically* invalid design (that is what validation
feedback is for) but never a *structurally* invalid one. Removing a part removes its pins from nets,
deletes nets left with one pin, drops logic rules that referenced it, and drops its placement. A batch
is atomic. New parts added from the library get the view centre as an unlocked placement hint.

## 4. HTTP API (`src/studio/server.py`)

`GET /api/health | providers | library | library/<id> | patterns | examples | jobs/<id>`,
`POST /api/examples/<id> | open | state | edit | export/svg | generate`. Static frontend from
`frontend/dist` with SPA fallback (path containment checked). AI generation runs as a background job;
the orchestrator's trace events are summarised into readable progress lines
("Searching the component library for …", "Validation FAIL: E010", "Repairing the design (attempt 1)").

## 5. Frontend (`frontend/src/studio/`)

* `types.ts` mirrors the backend models; `api.ts` typed client; `geometry.ts` mirrors the Python
  transform; `store.ts` pure reducer (+ hook) with undo/redo of *documents* (undo re-derives state on
  the server, so validation is always current).
* `SchematicCanvas.tsx` — SVG in grid units: dot grid, wheel zoom at cursor, drag-to-pan, click to
  select parts / wires (→ net) / ports / labels / pins, drag parts with integer grid snap (commits a
  `move_component`), wire tool (click pin → click pin → `connect`; rubber band), hover highlights the
  whole net, validation overlays (red/orange boxes on parts, red nets, pin markers), open-pin markers.
* `SymbolGraphics.tsx` — generic renderer for the backend's symbol primitives, upright text,
  power/ground ports, net labels; also library thumbnails.
* `Inspector.tsx` — component (reference, type, idealised/physical, AI role/rationale, rotate/mirror/
  delete/show-all-pins, editable parameters, pins with nets + disconnect/"connect…", registry electrical
  data — "unknown" when absent —, design rules, education, package, curriculum concepts); net (rename,
  drawing style, members, disconnect, delete); design (name/description, provenance, revision,
  drawing↔netlist consistency, layout stats, drawing notes).
* `Panels.tsx` — Validation (status, issues clickable → selects affected object, "not checkable"
  pins, checks performed), Explain, Library (search, categories, symbol thumbnails, add), Examples,
  AI Assistant (prompt, model, live progress log, clarification display, metrics).
* `StudioApp.tsx` — layout (top bar with validity badge, Select/Wire tools, undo/redo, fit,
  auto-arrange, SVG/IR export; left: Assistant/Library/Examples; centre: Schematic / Physical preview;
  right: Inspector/Validation/Explain; status bar), keyboard shortcuts (W, V, Esc, R, M, Del, F,
  Ctrl+Z / Ctrl+Y). The pre-existing 3D breadboard view is kept, lazy-loaded (three.js is a separate
  chunk), fed from the same engineering design, in an error boundary.

## 6. Verification

* **Backend** `tests/unit/test_studio.py` (19): every op incl. net merge, rejection codes, atomicity,
  presentation ops leave the design untouched, auto-arrange, insert_pattern validity, derived state
  completeness, library previews, and a real HTTP server on an ephemeral port (routes, bad requests,
  path traversal, SVG export, and an AI generation *job* driven by the mock provider whose first draft
  fails E010 and is repaired).
* **Frontend** vitest (13): transforms, **cross-language consistency** — every pin position in a
  backend-generated fixture is reproduced by the TypeScript transform — view fit/zoom, reducer
  history/selection semantics. `tsc -b` clean.
* **Real browser** `scripts/ui_e2e.py` drives headless Chrome over CDP with real mouse/keyboard
  events (no test hooks): load → select R3 → edit resistance (470Ω→1kΩ on canvas) → Delete → E007
  appears → Ctrl+Z → add buzzer from library → wire tool connects BZ1− to ground and BZ1+ to the 9 V
  rail → validator reports **E014 (3.3–5 V buzzer on 9 V)** → undo ×3 → drag Q1 (still LVS-consistent)
  → open I2C example → Explain → click a wire selects the SCL net. **12/12 pass.** Two defects were
  found this way and fixed: parts added from the library landed off-screen; a race in the test itself.

## 7. Limitations

* Wires cannot be hand-routed (routing is derived); users steer by moving parts or choosing
  wire/label per net.
* No multi-select, copy/paste, or box selection yet.
* Undo history is per browser session (not persisted).
* The 3D tab only knows a handful of physical footprints (pre-existing prototype).
