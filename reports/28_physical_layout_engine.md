# 28 — Physical Layout Engine (placement + wiring)

Modules: `src/physical/placement.py`, `src/physical/wiring.py`, orchestrated by
`src/physical/engine.py::generate_physical(design, registry, layout_state, schematic=None)`.

## 1. Pipeline

1. **Footprints** for every part (report 29): board-insertable templates (two-lead, inline, DIP,
   dual-row, SMD adapter), off-board items with terminals, or virtual (idealised primitives).
2. **Rails**: ground nets take both "−" rails; the busiest supply net takes T+, a second supply the
   B+ rail (otherwise both + rails carry the main supply). Net classes and voltages come from the
   schematic's `classify_nets` (same classification as the 2D view).
3. **Board size**: `auto` tries the half-size board and falls back to full-size if any part cannot be
   placed; the user can force half/full (`set_breadboard`).
4. **Remembered placements first** (user moves and the previous build), in `seq` order; then
   automatic placement, big parts first (DIP / dual-row → inline → two-lead), each class in the
   schematic's left-to-right order (so both views read in the same signal-flow order).
5. **Off-board arrangement**: supplies and batteries left of the board, controller boards below,
   other modules and actuators right; each rotated so its terminals face the board.
6. **Wiring**: leads, then jumpers (§4).
7. **Physical IR**, assembly steps, **physical verification** (report 31).

## 2. The core constraint

Every breadboard *node* (a 5-hole terminal strip, or a rail) carries **at most one engineering net**.
A candidate placement is legal only if each pin lands in a free, uncovered hole whose node is either
unassigned or already carries that pin's net. Unconnected pins receive a private node (`nc:…`), so
nothing else may share their strip. Two pins of one part may share a node only if they are on the
same net. Consequences:

* the placement engine **cannot create a short**;
* pins of the same net that share a strip are connected **by the board itself**, with no wire (for
  example the transistor's emitter in the comparator's GND strip, or a pull-up resistor plugged
  straight into the + rail);
* body collisions (plan view) and holes covered by a body are rejected.

## 3. Candidates and scoring

Placement modes per template: two-lead parts lie along a row (`row`), stand across the trench
(`cross`) or run into a rail (`rail`) with bendable lead spans from the footprint; inline parts lie
along a row; DIP / dual-row parts must straddle the trench. Rotations 0/180 (90/270 for two-lead
across rows).

Score (lower is better): −12 per pin that joins its net through a shared node; + distance to the
nearest node already carrying the pin's net; + a penalty when a rail net is not taken from the rail;
+ distance from the part's target column (signal-flow order spread over the board); small
preferences (keep rows e/f free for DIPs and rows a/j for rail jumpers, prefer the footprint's first
lead span, avoid crowded strips and covered holes). Ties break on (column, row, rotation, span).

**Performance.** Candidates are first ranked with the cheap pin score inside a column window around
the target (plus columns near same-net strips); only the best 30 are checked for body collisions; a
full-board search is the fallback. A first version that fully evaluated every candidate took 0.4–2.7 s
per design; the ranked search takes **41–175 ms** (all reference designs, table in report 32).

## 4. Wiring

* **Leads**: off-board items with flying leads (battery snap, AA holder, USB supply leads, motor)
  push their lead end into a hole of the net's rail when it has one, else a strip already carrying
  the net, else a fresh strip reserved for it.
* **Jumpers**: the net's distinct nodes (used strips, used rails, off-board header pins) are joined by
  a minimum spanning tree (Prim, deterministic). Each edge becomes one jumper between the nearest pair
  of free holes / terminals; rail-to-rail edges are rail bridges.
* **Capacity-aware planning**: a strip has five holes. The tree is first planned as a dry run with
  hole reservations; if it cannot complete (every in-tree strip is full), it is planned again with the
  net's rails added as hubs, like "bring the net to the rail" on a real board. This was introduced
  after the I²C logger failed with two open nets in an early version (see report 32).
* **Paths**: plan-view L routes, lifted 2–3.5 mm above the board, raised above any part body a
  segment crosses; the 3D view smooths the corners. Colours: black ground, red main supply, orange a
  second supply, then a fixed palette per signal net; lead colours follow the part (red/black).

## 5. Editing

`physical_move` (hole anchor for board parts, x/y for off-board items), `physical_rotate`,
`physical_auto_arrange`, `set_breadboard`. A move is validated by running the real projection with the
requested placement locked and the newest `seq`; if the engine cannot keep it, the op is refused with
the engine's own reason and the document is unchanged, e.g.

* "Cannot put q1 at e9: hole e9 is already used by pin:u2.OUT1"
* "Cannot put q1 at a10: pin C would land in top:10, which carries net ref (a short)".

An early version placed locked parts first, so a move onto an occupied spot silently pushed the
other part elsewhere; `seq` ordering (latest move last) fixed that: existing parts stay put.

## 6. Limitations

* One breadboard; no multi-board layouts (an ESP32 DevKit is therefore placed beside the board).
* Greedy placement with local scoring, not a global optimiser; jumper count is small but not minimal.
* Wire paths are not routed around each other (they may cross in plan view, as real jumpers do) and
  may pass over off-board bodies.
* Strip capacity is respected; hole pitch collisions between wires and tall parts are only avoided
  through the "raise over bodies" rule.
