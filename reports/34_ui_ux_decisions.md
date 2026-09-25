# 34 — UI / UX Decisions: One Studio

Stage: product / visual refinement (plan: report 33). Frontend only: no file under `src/` or `data/`
changed; the HTTP API, edit ops, validators, schematic and physical engines are untouched.

## 1. Design system

`frontend/src/studio/studio.css` was rewritten around tokens on `:root` (surfaces `--bg`,
`--panel`, `--panel-2/3`, lines, text levels, status colours with soft variants, AI and engine role
colours, and the schematic palette). One dark engineering workspace is shared by the chrome, the
schematic sheet and the 3D scene. Every class name the code and the browser E2E relied on was kept;
new classes are additive.

The schematic keeps its engine and drawing code; only token values changed (dark sheet, amber
symbols, green wires, orange active net, violet labels). The SVG export is rendered by the backend and
is unchanged.

## 2. Layout and hierarchy

```
┌ brand · project name · [✓ valid] [✓ function] [⚠ build]   [ Schematic | Physical 3D ]   Export ▾  ✦ AI Assistant ┐
│ Library | Building blocks | Examples │  Schematic · 8 parts · 7 nets · drawing matches   │ Assistant Inspector Checks │
│  search, kind filter,                │                                                    │ Assembly Explain            │
│  categories with counts              │                 canvas (2D or 3D)                  │                             │
│                                      │     ┌ ↖ ⌇ │ ↶ ↷ │ − 100% + │ ⤢ ◎ │ ✦ Auto-arrange ┐  │  context panel              │
└──────────────────────────────────────┴─ status: messages · drawing ↔ netlist · build ↔ netlist ┴─────────────────────────────┘
```

* **Top bar = project, views, health.** The Schematic / Physical 3D switch is centred and treated
  as the top-level concept (one design, two views). The health pills (Electrical, Function, Build) are
  clickable and open the matching check. Export is one menu (schematic SVG, engineering design JSON,
  and new: physical build JSON).
* **Canvas caption** states what you are looking at and whether it matches the netlist.
* **Floating canvas toolbar** with the same place and grammar in both views: select/wire (2D), undo /
  redo, zoom − % + (2D) or 3D / Top / Front (3D), fit, locate selection, labels (3D), auto-arrange.
* **Left = what you can build** (report 36). **Right = context**: Assistant, Inspector, Checks,
  Assembly, Explain.

## 3. Interaction model: one design, two views

* One engineering selection (component / net / pin) for both views; nothing view-specific is stored.
* **Locate.** "◎ Schematic" and "◎ 3D" in the Inspector, the toolbar ◎ button and the `L` key show the
  selection in either view: the schematic centres it at the current zoom; the 3D camera eases to the
  part, or to the extent of a net.
* **Switching views with a selection** locates it in the new view ("select Q1 in the schematic →
  Physical 3D is already looking at Q1").
* **Selections made outside the 3D canvas** (schematic, Inspector, Assembly steps, Checks lists)
  bring the 3D camera to them; clicks inside the 3D view never move the camera.
* **Selection source.** Canvas selections open the Inspector. Selections made from a list (Assembly
  steps, Checks, Explain) keep that list open, so a build walkthrough is not interrupted. This is stored
  as `selectionSource` in the store; the selection itself is unchanged.
* The AI Assistant stays mounted while hidden, so a generation in progress survives tab switches.

## 4. What was deliberately not copied from the references

Branding, logos, text, file-tree and project-management chrome, credits, deploy/serial consoles.
Taken: the dark low-contrast chrome, the centred view switch, the categorised library with counts,
the assistant as a task checklist with a pinned composer, the floating pill toolbar, the printed
breadboard, arched jumpers and soft lighting.

## 5. Limitations

* Dark theme only (tokens make a light theme a small addition).
* Panels are fixed-width (not resizable or collapsible yet).
* The canvas is not keyboard-navigable beyond shortcuts; lists are the accessible path.
