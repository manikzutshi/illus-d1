# 31 — Physical Verification

Module: `src/physical/verify.py` — `verify_physical(project, design) -> PhysicalVerification`.
Runs on every projection; shown in the Assembly tab, the "build" badge, the Inspector and the CLI
(`physical verify`, non-zero exit on error).

## 1. Independence

The verifier does not trust the placement engine. It rebuilds connectivity from the serialised
Physical IR alone with a union-find over:

* board holes → their node (from the breadboard model: strips and rails),
* each inserted pin → its hole,
* each wire / lead end → hole or off-board pin,
* connections inside a part (`internal_links`, e.g. a 4-pin tactile switch, the Uno's GND pins) and
  pin aliases (ESP32 GND3 = GND2),

and compares the resulting groups with the engineering nets, the same way schematic LVS checks the
drawing.

## 2. Checks

| Code | Severity | Check |
|---|---|---|
| P001 | ERROR | every engineering part has a physical instance |
| P002 | ERROR | every *connected* engineering pin has a physical contact (hole, terminal or alias) |
| P003 | ERROR | every pin and wire ends in a hole that exists on the board |
| P004 | ERROR | no hole holds two leads / wires |
| P005 | ERROR | no two engineering nets are joined physically (**short**) |
| P006 | ERROR | every engineering net is one physical group (**open**) |
| P007 | ERROR | no two part bodies overlap (plan view) |
| P008 | ERROR | every part could be placed |
| P009 | ERROR | nothing is inserted in a hole covered by a part body |
| P010 | ERROR | a pin that is unconnected in the design does not touch a net physically |
| P101 | WARNING | geometry is a stand-in (`assumed`), not the real part |
| P102 | WARNING | the pinout differs between vendors — check the part in hand |
| P103 | WARNING | an SMD part needs a breakout adapter to be breadboarded |
| P104 | INFO | a requested placement could not be kept |
| P105 | INFO | idealised primitives / net symbols have no physical form |

Status: FAIL if any ERROR, else WARN if any WARNING, else PASS; NOT_APPLICABLE for designs made only
of idealised primitives. `ok` = no ERROR = the physical build equals the netlist.

## 3. Evidence that it catches real faults

Tests inject faults into a correct build (temperature alarm) and assert the right code:

* a jumper end moved into the strip of another net → **P005 short**;
* the jumpers of one net removed → **P006 open**;
* a resistor lead moved into a hole already used by the comparator → **P004**;
* a pin moved to a non-existent hole → **P003**;
* a transistor body placed on top of the comparator → **P007**.

During development the verifier also caught two genuine engine bugs before any test was written: the
relay's NO terminal lost to a YAML boolean (**P002**), and two nets left open when strips ran out of
free holes (**P006**, fixed by capacity-aware wiring, report 28 §4).

## 4. Confidence boundaries

* Connectivity only: it does not check currents, voltages, lead lengths, wire gauge, or whether a
  jumper can physically reach (paths are generated, not measured against real wire lengths).
* Collisions are plan-view bounding boxes; tall parts leaning over neighbours are not modelled.
* Its conclusions are only as good as the physical data: an `assumed` or vendor-variant pinout is
  verified as modelled and flagged (P101 / P102), not proven against the real part.
