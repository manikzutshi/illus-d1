# 33 — Product / Visual Refinement: Plan

Date: 2026-09-25. Written before implementation. No Git operations (owner-managed).

## 1. GREEN verification (before any change)

| Check | Command | Result |
|---|---|---|
| Backend | `pytest` | 513 passed, 5 skipped (opt-in live-provider tests) |
| Electrical / functional / schematic LVS / physical, per reference design | `design validate`, `design function`, `schematic verify`, `physical verify` over `data/examples/*` | all 12 electrically PASS and schematic LVS OK; function PASS ×8, WARN ×1, NOT_CHECKABLE ×3 (as in report 24); physical PASS ×5, WARN ×5 (data caveats only, no errors), NOT_APPLICABLE ×2 |
| Frontend | `npx vitest run` / `npx tsc -b` / `npm run build` | 24 passed / clean / builds |
| Browser E2E | `scripts/ui_e2e.py` (fresh server, current code) | 23/23. The first attempt stopped at 14/15 on the known flaky step "disconnect BZ1's GND in the Inspector" (the click landed while the Inspector re-rendered with registry details; no request reached the server); the re-run passed. The harness race is fixed in this stage (test-only change). |

**CURRENT SYSTEM: GREEN.** Untouched in this stage: Engineering IR, electrical validator, functional
validator, schematic engine + LVS, physical engine + verification, orchestrator / provider
abstraction, edit-op semantics, HTTP API contract.

## 2. What the reference images show (design language, not content)

Four screenshots of a commercial AI electronics builder (`ex-ss/`). Taken as design references only;
no branding, text, logos or assets are reused.

* **Chrome**: near-black neutral surfaces, 1 px low-contrast borders, compact 12–13 px type, small
  uppercase section labels, very little colour except status and one high-contrast primary action.
* **Hierarchy**: a top bar with the view switch centred ("3D ↔ Schematic" as a top-level concept),
  a project line with a caption ("N components · N wires"), the canvas dominating.
* **Library** (left): search, collapsible categories with counts, expanding into tiles.
* **AI assistant** (right): a task checklist that ticks off steps as the AI works, questions as
  choices, the prompt composer pinned at the bottom.
* **Canvas**: floating pill toolbar at the bottom (undo/redo, zoom %, fit, labels toggle); dark
  surround; the 3D board white with printed numbers, jumper wires as smooth arches, soft light.

## 3. Diagnosis of the current studio

It works, but it reads as tools placed side by side:

* light, generic chrome; tools crowded into the title bar; view switch hidden in a secondary tab row;
* the AI assistant is a textarea plus a raw event log, not a visible process;
* the library is one long flat list with no sense of scale or categories, and design patterns (a key
  asset) are not offered at all;
* "is it right?" is split across Electrical, Function and Assembly tabs;
* the 3D scene uses a test-like light background, flat lighting and L-shaped wires; the camera does
  not follow the selection, so cross-view traceability is technically there but not *felt*.

## 4. Decisions

1. **One dark engineering workspace** (design tokens on `:root`): chrome, schematic and 3D share one
   surface family. The schematic keeps its engine; only token values change (dark sheet, light
   symbols), so SVG export (backend-rendered) is unaffected.
2. **Top bar = project + views + health**: project name and caption, a centred
   **Schematic | Physical 3D** switch, and a health cluster (Electrical · Function · Build) that opens
   the relevant check. Export moves into one menu.
3. **Floating canvas toolbar** per view (2D: select/wire, undo/redo, zoom, fit, auto-arrange;
   3D: undo/redo, view presets, fit, labels, re-arrange).
4. **Left = Library** (Components · Building blocks · Examples): data-driven categories with counts,
   search over names/aliases/tags/families, idealised/physical filter, an expandable detail card per
   part (description, package, pins, what it does) with an Add action; patterns insertable via the
   existing `insert_pattern` op. Nothing assumes today's 86 parts.
5. **Right = context**: Assistant · Inspect · Checks · Assembly · Explain.
   * *Assistant*: the AI process as a checklist of phases derived from real job events
     (understand → search library → choose parts → calculate → validate → repair → schematic →
     physical build), a result card with the deterministic verdicts, suggestions, raw log folded.
   * *Checks*: one hub with three status cards (Electrical, Function, Physical build) and the existing
     panels as sections (reused, not rewritten); "assumptions / not checkable" surfaced.
   * *Inspect*: part card + sections (connections, parameters, physical build, this part's checks,
     what it does, concepts) and **Locate in schematic / Locate in 3D**.
6. **3D polish without touching the physical engine**: studio lighting, contact shadows, a printed
   breadboard (column numbers, row letters, rail marks), arched jumper rendering computed from the
   IR endpoints (the IR path is unchanged; endpoints are preserved exactly), hover highlight and
   tooltip, a labels toggle, better materials, and a camera that **eases to the selected part or net**
   (so "select Q1 in the schematic → switch → the 3D view is looking at Q1").
7. **No new frameworks**; React + existing CSS; react-three-fiber/drei already present.

## 5. Protection

* Engineering, schematic and physical code untouched; the only backend change allowed would be
  additive and tested (none planned).
* Every phase ends with pytest, vitest, tsc, build and the browser E2E.
* New pure logic (job phases, library grouping/search, checks summary, wire arcs, focus targets) is
  unit-tested; the E2E gains steps for the new interaction model (view switch, library, checks hub,
  locate / focus).
