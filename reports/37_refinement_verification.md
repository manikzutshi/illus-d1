# 37 — Product / Visual Refinement: Verification

Date: 2026-09-25. No Git operations.

## 1. Baseline before the stage (GREEN)

See report 33 §1: 513 Python passed / 5 skipped; all reference designs electrically PASS and
schematic-LVS OK, functional and physical statuses as in reports 24 and 32; 24 frontend tests; tsc
clean; browser E2E 23/23 (the first attempt hit a known harness race at 14/15, the re-run passed).

## 2. After the stage

| Suite | Result |
|---|---|
| Python (`pytest`) | **513 passed, 5 skipped**: unchanged. No file under `src/` or `data/` was modified |
| Frontend `tsc -b` / build | clean / builds (main bundle + lazy 3D chunk) |
| Frontend vitest | **38 passed** (24 existing + 14 new) |
| Browser E2E (`scripts/ui_e2e.py`, headless Chrome, software WebGL, fresh server) | **28/28** (23 existing, adapted to the moved controls, + 5 new) |

New unit tests (`frontend/src/studio/ui/ui.test.ts`):
* job phases derived from a real event sequence (mapping, active/done while running, verdicts taken
  from the deterministic result, failure position);
* library search (names, aliases, tags, descriptions, multi-token), kind filter, stable grouping,
  unknown future categories;
* checks summary, per-part issues across all three checks, "not built yet" instead of a guess;
* arched wire rendering keeps both IR endpoints exactly and never goes below the IR route;
* 3D focus targets for parts and nets; schematic locate keeps the zoom;
* selection source (canvas vs panel).

New browser E2E steps:
1. selecting U2 in the schematic and switching to Physical 3D focuses the camera on U2 (fresh focus,
   U2 highlighted);
2. the Checks hub shows the three verdicts (Valid · Does what was asked · Build matches netlist);
3. toolbar zoom changes the view (125 %) and fit restores 100 % without editing the design;
4. a building block (LED indicator) inserts through the engineering op (8 → 10 parts) and undo
   restores 8;
5. the Assistant states the roles and offers the composer.

Adapted steps: checks opened through the hub cards; the view switch addressed by `data-view`; the
assembly-step selection now keeps the Assembly tab open (asserted) before the Inspector is opened.

**Flake fixed**: the "disconnect BZ1 GND" step now waits until the Inspector has loaded registry
details (its layout is then stable) before clicking. It passed in every run of this stage.

## 3. Engineering invariants re-checked

* Schematic LVS and physical verification are shown in the caption, the status bar, the health pills
  and the Checks hub; all come from the backend.
* Visual changes never write to the design: toolbar, locate, labels, camera and hover are view-only;
  moves and inserts are ordinary engineering or presentation ops validated by the backend.
* The arched wire rendering is computed from, and pinned to, the Physical IR endpoints (tested).

## 4. Screens reviewed by eye

Schematic with a selection; Physical 3D focused on a part and fitted; Checks hub; Assistant idle;
Building blocks + Explain; PWM motor build; Assembly step → 3D focus. Issues found and fixed during
review: toolbar label wrapping, hint text under the toolbar, off-centre view switch, fitted 3D view
cutting the board, oversized pin markers and holes, a garish stand-in supply, the Assembly list being
closed by its own selection.

## 5. Remaining limitations

Dark theme only; fixed panel widths; no conversational refinement; procedural 3D models; arches can
cross on dense boards; library thumbnails are symbols only.
