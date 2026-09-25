# 27 — Physical IR

Module: `src/physical/models.py` (Pydantic, serialised to the studio as `StudioState.physical`;
TypeScript mirror in `frontend/src/studio/types.ts`). Schema version `0.1.0`.

## 1. Principle

Like the Schematic IR, the Physical IR describes **how an engineering design is built**, never
*what* it is. It is regenerated from the engineering design plus the user's physical placements on
every request, and every object carries the engineering identity it realises:

```
Engineering: Q1.C ── net coll ── BZ1.GND
Physical:    Q1 pin C in hole b14 (strip top:14) ── wire w3 (f14 → e14, net coll) ── BZ1 pin GND in hole j14 (strip bot:14)
```

Units are millimetres. Board frame: x along the breadboard columns, y across the rows (row a at
negative y), z up; the breadboard's top surface is z = 0; off-board items rest on the table at
z = −board height.

## 2. Model

| Object | Key fields | Traceability |
|---|---|---|
| `PhysicalProject` | `applicable`, `board`, `parts`, `wires`, `nets`, `occupied` (hole → occupant), `covered` (holes under bodies), `bounds`, `assembly`, `verification`, `stats`, `diagnostics` | `project_id` = engineering project |
| `BoardInfo` | `kind` half/full, `columns`, `rows`, `row_y`, `column_x`, `size_mm`, `rails[]` (`rail_id`, polarity, y, columns, `net_id`) | rail → engineering net |
| `PhysicalPart` | `mount` breadboard / offboard / virtual / unplaced, `template`, `position`, `rotation`, `anchor` (hole of the first footprint site), `orientation` row / cross / rail / dip / offboard, `span`, `body` (world box), `pins[]`, `visual`, `geometry`, `locked`, `internal_links`, `notes` | `instance_id`, `component_type_id`, `reference` (same designator as the schematic) |
| `PhysicalPin` | `position`, `hole`, `node`, `terminal` (lead / header / screw / pad), `alias_of` | `pin_id`, `net_id` |
| `PhysicalWire` | `kind` jumper / lead / rail_bridge, ends `a`/`b` (`hole` or `pin_ref`), `path` (3D polyline), `color`, `length_mm`, `purpose` | `net_id`, `pin_ref` |
| `PhysicalNetTrace` | `nodes` (strips/rails carrying the net), `wires`, `pins`, `rails`, `color` | `net_id`, display name, net class |
| `VisualSpec` | `kind` (procedural visual), `asset_url`, `fallback`, `params` (e.g. resistor `bands`, LED `color`, `pin_count`) | — |
| `GeometryInfo` | `source` datasheet / standard / typical / assumed, `notes`, `variant_note` | — |
| `PhysicalVerification` | `status`, `ok`, `summary`, `findings[]`, `checks[]` (report 31) | findings name instances / pins / nets / holes / wires |
| `AssemblyStep` | ordered build instructions (`board`, `part`, `lead`, `wire`, `note`) | `instance_id`, `wire_id`, `net_id` |

**Presentation state** (in the studio document, user-editable, no connectivity):
`PhysicalLayoutState { board: auto | half | full, placements: {instance_id → PhysicalPlacement} }`
with `PhysicalPlacement { anchor, orientation, rotation, span | x, y, locked, seq }`. `seq` orders
user moves: the most recent move must fit around earlier placements (report 28 §5).

## 3. Visual parameters come from engineering data

`visual.params` are derived, never guessed: resistor colour bands from the actual `resistance`
parameter (4-band code, e.g. 10 kΩ → brown-black-orange-gold); LED colour from the `color` parameter
(a clear lens when it is not set); DIP / header pin counts from the footprint.

## 4. Serialisation and determinism

`PhysicalProject.model_validate(json)` round-trips; two projections of the same document are
identical apart from `stats.elapsed_ms` (tested). Wire ids, hole choices and tie-breaks are
deterministic (sorted keys at every choice).
