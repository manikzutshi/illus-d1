# ADR 006: Schematic as a Deterministic Projection; Studio Edits as Operations

## Status
Accepted (2D Schematic Studio stage, 2026-09-24)

## Context
The product needs a real, editable 2D schematic. ADR-003 makes the engineering design the single
source of truth. A schematic editor naturally tempts a second source of truth (drawn wires that
"are" the connectivity), and an AI tempts pixel-level generation.

## Decision
1. **Projection.** `schematic = generate_schematic(design, registry, layout_state)` — deterministic,
   integer-grid, no AI. `LayoutState` stores presentation only (placement, rotation, mirror, per-net
   wire/label style); it contains no connectivity.
2. **Operations.** The UI changes nothing locally. Every change is a typed edit op; engineering ops
   are registry-checked and applied to the engineering design, then validation and projection re-run.
   Presentation ops touch only `LayoutState`. Batches are atomic.
3. **Symbols are data** embedded in the Schematic IR; the browser is a generic renderer.
4. **Schematic LVS.** Connectivity extracted from the drawing must equal the engineering nets; this is
   checked on every state and surfaced in the UI.
5. **Knowledge kinds are separate**: physical parts, idealised primitives, design patterns, and
   curriculum concepts/engineering objects. Non-physical topics never masquerade as parts.
6. **Transport:** Python stdlib HTTP server (no new dependencies), stateless for documents,
   localhost-only; provider keys stay server-side.

## Consequences
+ The drawing cannot diverge from engineering truth unnoticed; edits are auditable and undoable.
+ The same projection pattern will serve the physical/3D view (design → physical layout state).
− Users cannot hand-route individual wire segments; they steer the router by moving parts and
  choosing wire vs label per net.
− Each edit round-trips to the server (tens of ms locally).
