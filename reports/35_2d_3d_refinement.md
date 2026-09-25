# 35 — 2D and 3D Refinement

## 1. Schematic (2D)

Engine, projection, LVS, edit ops and traceability are unchanged. Changes are presentation only:

* dark sheet via tokens; selection box, issue boxes and the active-net colour retuned for contrast;
* the floating toolbar drives the canvas through view-only commands (`CanvasCmd`: fit, zoom in/out,
  locate) and the canvas reports its zoom as a percentage of the fitted view;
* **locate** centres the selected part (its bounding box) or net (wires + pin tips) at the current
  zoom, widening only when it does not fit (`geometry.centerOn`, unit-tested);
* the canvas caption and status bar state drawing ↔ netlist consistency.

## 2. Physical 3D

The Physical IR, placement, wiring and verification are unchanged; everything below is rendering.

| Area | Before | Now |
|---|---|---|
| Scene | light grey, flat light | dark studio: hemisphere + key light with 2048 px soft shadows + cool rim light, contact shadows under the build, depth fog, damped orbit limited above the table |
| Breadboard | white box, instanced dark squares | layered ivory body, centre channel, **printed** column numbers (1, 5, 10, …) on both sides, row letters, red/blue rail lines and +/− marks, recessed holes (canvas texture drawn from `BoardInfo`, so it is always exact) |
| Wires | L-routes lifted 2–3 mm | smooth **arched jumpers** whose apex grows with span, never lower than the IR route (so they still clear part bodies); black insulated pin ends in the holes; endpoints taken exactly from the IR (unit-tested) |
| Parts | procedural kinds | same kinds, sized from real body data; DIP packages now carry their part marking; the stand-in USB supply is a neutral breakout board instead of a purple box |
| Selection | outline | outline + label with part name and value; hover shows a blue outline and the same label; pin markers smaller |
| Labels | always on | toggle in the toolbar (selected / hovered labels always shown) |
| Camera | fixed presets | 3D / Top / Front presets and **eased locate** on the selection (`focusTarget`, unit-tested) |
| Hints | overlay on the canvas | compact hint at top right: hovered hole id, strip/rail node and occupant |

The 3D bundle is still a separate lazy chunk; holes are now part of one texture (fewer meshes than the
instanced version). Rendering stays responsive on software WebGL (the headless E2E browser).

## 3. Limitations

* Procedural models, not photorealistic; no GLB models shipped (the asset path remains).
* Arched jumpers are a rendering choice; the IR keeps its flat route for tools that need it. Arches
  can cross each other on dense boards.
* The camera does not avoid occluding parts when locating.
