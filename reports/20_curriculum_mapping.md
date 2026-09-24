# 20 — Curriculum Mapping (Industry-Ready VLSI Blueprint → knowledge graph)

## 1. Source

`Industry_Ready_VLSI_Curriculum_Blueprint.docx` (text extracted and read in full): a 14-module core
VLSI backbone, a 40-domain knowledge architecture, an industry layer (analog, power/HV, memory, SoC,
protocols, chiplets, AI hardware, security, safety…), a competency ladder L0–L4, a topic-record schema,
and the learning loop *understand → work an example → design → simulate → inspect → debug →
optimize → explain*.

## 2. Principle applied: knowledge is not parts

The blueprint is mostly about RTL, verification, timing, physical design, fabrication, packaging.
None of these are purchasable components. So the ecosystem now has four separate kinds of object:

| Kind | Where | Example |
|---|---|---|
| Physical part | component registry, `object_type: PHYSICAL` | LM7805, 74HC00, IRLZ44N |
| Idealised primitive | component registry, `object_type` ≠ PHYSICAL | ideal NMOS, NAND gate, DC source |
| Design pattern (functional block) | `data/knowledge/patterns.yaml` | MOSFET low-side switch, CMOS inverter |
| Concept / engineering object / process / methodology | curriculum graph | CDC synchroniser, AXI4-Lite, UVM testbench, STA, CMOS process flow |

`ConceptRecord` gained `kind`, `domain` (blueprint domain), `abstraction_level`
(physics/device/circuit/gate/rtl/architecture/system/verification/implementation/manufacturing/
package/methodology), `representations` (schematic, waveform, block_diagram, layout, cross_section,
vtc_plot…), `patterns`, and a `learning_loop` (design task, simulate, debug task, optimize, explain).
A test enforces that RTL/verification/process concepts never point at physical parts.

## 3. What was added (`data/curriculum/10_backbone_and_industry.yaml`)

* 23 modules: the 14 core modules (numbered 1–14) + 9 industry-layer modules, each with its domains.
* 45 new concepts (53 total). Schematic-representable ones (PN junction, BJT/MOSFET, CMOS logic,
  noise margins, logical effort, Ohm's law, RC timing, transistor switch, common-emitter amplifier,
  op-amp feedback, comparators, regulation, inductive loads, PWM, H-bridge, ADC/DAC, level shifting,
  I2C/SPI, oscillators, sensor interfacing, flip-flops, setup/hold…) link to registry parts and
  patterns. Higher-level objects (RTL module, AXI4-Lite, async FIFO, CDC synchroniser, UVM testbench,
  assertions/coverage, scan chain, floorplanning, CMOS process flow, chiplets/UCIe, ESD/latch-up,
  systolic array, hardware trust, ISO 26262) are recorded with their abstraction level and natural
  representations (block diagram, waveform, layout, cross-section) — ready for future non-schematic
  views, without polluting the part library.
* The 8 original concepts were kept (tests depend on them) and re-pointed at real registry IDs.
* Integrity tests: every component/pattern/prerequisite/related reference resolves; every registry
  `curriculum_mapping` resolves.

## 4. How it is used now

* Inspector shows the curriculum concepts for a selected part; the Explain panel lists the concepts a
  design touches; each part's education text and common mistakes are shown next to validation.
* The explanation model (parts & roles, rails, signal flow, checks performed, assumptions,
  limitations) is the *explain* step of the blueprint's loop, computed deterministically.
* Reference examples double as learning artefacts (each carries a `curriculum_context`), and several
  validator findings are exactly the blueprint's "debug a deliberately broken version" tasks
  (missing flyback diode, missing pull-up, reversed polarity, overdriven GPIO, 5 V into 3.3 V).

## 5. Not done (deliberately)

No educational platform features (paths, assessments, skill passport, company/country mappings).
The graph structure (modules/domains/kind/level/representations/learning_loop) is the hook for them.
