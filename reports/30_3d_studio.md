# 30 — 3D Studio (Physical 3D view)

Frontend: `frontend/src/studio/physical/` (`PhysicalView.tsx`, `assets.tsx`, `coords.ts`,
`trace.ts`), `components/AssemblyPanel.tsx`, `components/PhysicalSection.tsx`; wired into
`StudioApp.tsx`, `store.ts`, `api.ts`, `types.ts`.

## 1. Product shape

The existing 2D Studio is kept intact; the centre panel now has **[ Schematic ] [ Physical 3D ]**
over one shared document, with the same AI Assistant, Library, Examples, Inspector, Function,
Electrical and Explain panels, plus a new **Assembly** tab and a "build" badge next to
"valid" / "function" in the title bar. The status bar reads
"drawing matches netlist ✓ · build matches netlist ✓".

| Area | What it does |
|---|---|
| Physical 3D canvas | Breadboard (instanced holes, rail stripes, trench), parts with legs from their real pin holes, leads and jumper wires as tubes, off-board items on the table, labels with the schematic's reference designators; orbit / pan / zoom; 3D / Top / Front presets; hover a hole to see its id, node and occupant |
| Selection | One engineering selection for both views: click a part → component; a wire → its net (other wires dim); a pin marker → pin (its net lights up). Switching views keeps the selection |
| Moving | Drag a part: it snaps to holes while dragging; on release a `physical_move` op is sent; the backend accepts or refuses it with the reason (e.g. "would short net ref"). Off-board items move freely on the table. R rotates (in the 3D tab) |
| Inspector → Physical build | Where the part is (board / beside / anchor hole / mode), where its geometry comes from, a pin → hole → net table, variant-pinout warnings, "Rotate on board", "Move to hole" |
| Assembly tab | Physical verification status and findings (clickable), board size (auto/half/full), "Re-arrange build", the list of checks run, and numbered **build steps** (board, rails, each part with its holes, leads, each wire from → to with colour and net); clicking a step selects the part or net |
| Primitive-only designs | "This design uses only idealised primitives; it has no physical form to build" instead of an empty scene |

## 2. Source-of-truth rules in the UI

* The view never computes placement or connectivity; it renders `state.physical`.
* Physical edits are ops (`physical_move`, `physical_rotate`, `physical_auto_arrange`,
  `set_breadboard`) that only touch `document.physical`; engineering edits (delete, parameters, wiring)
  go through the same engineering ops as in 2D and the build is re-projected.
* Undo/redo covers physical edits (the document holds the placements).

## 3. Assets

Procedural visuals keyed by `visual.kind` (39 kinds; every kind named in the physical data has a renderer: axial resistor with value-derived colour bands,
axial diode with the cathode band at the K lead, 5 mm LED coloured from its parameter, radial and
electrolytic capacitors, TO-92, TO-220, DIP with notch and pin-1 dot, headers, trimpot, tactile
switch, buzzer, LDR, HC-SR04, OLED, Pico, SMD adapter, 9 V battery, AA holder, USB supply, Uno,
ESP32, relay module, servo, motor, …). Bodies use the real `body_mm` from the Physical IR; legs and
header pins are drawn from the actual pin holes, so the drawing and the build cannot disagree.
Unknown kinds or `fallback` parts use a labelled generic block ("?" label, dashed tag). A detailed
model can be supplied via `visual.asset_url` (GLB, lazy, with the procedural body as the Suspense
fallback and an error boundary). Text on parts uses canvas textures and labels are HTML overlays, so
nothing is fetched from a CDN (the prototype's drei `Text` needed a network font).

## 4. Performance

* The whole 3D stack (three.js, react-three-fiber, drei) is a separate lazy chunk (~1.0 MB), loaded
  only when the Physical 3D tab is opened; the main bundle is ~247 KB.
* The server computes the physical build only when the client asks (`physical: true`, sticky once
  the 3D tab has been opened), so the 2D-only workflow costs the same as before.
* Board holes are one `InstancedMesh`; tube geometries are memoised and disposed; projection time is
  41–175 ms per reference design.

## 5. Coordinate conventions (tested)

Physical (x, y, z; z up) → three.js (x, z, y); a physical rotation of +θ about z is −θ about three's
Y axis; `boardHoles()` rebuilds every hole from `BoardInfo` and is tested to reproduce every inserted
pin's backend position exactly.

## 6. Limitations

* Procedural models are schematic-accurate, not photorealistic; no detailed GLB models are shipped.
* Off-board items can be moved but not rotated by drag (use R).
* Wires cannot be re-routed by hand; they follow the automatic route.
* The canvas is not keyboard-navigable; the Assembly list and Inspector are the accessible path.
