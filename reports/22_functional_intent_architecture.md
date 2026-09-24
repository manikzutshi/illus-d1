# 22 — Functional Intent Architecture

Stage: "electrically valid" vs "does what the user asked". Date: 2026-09-25.

## 1. What was discovered

Verified state at the start: 363 Python tests passed / 5 skipped, 13 frontend tests, `tsc` clean,
86 component types, 16 patterns, 6 calculators, 53 curriculum concepts (reports 00, 21).

The pipeline accepted any design that was structurally valid, electrically valid and LVS-consistent.
Nothing compared the design with *what the user asked it to do*. Reconnaissance of existing
representations:

| Existing representation | Where | Usable as functional intent? |
|---|---|---|
| `ProjectRequirements` (`intent`, `inputs`, `outputs`, `thresholds`, …) | `src/ai/models.py` | Free-text lists only; nothing machine-checkable |
| `LogicRule` (condition on input instance → action on output instance) | `EngineeringDesignProject.logic` | Written by the *designer* (AI) as part of the design → cannot be the specification it is graded against; **reused** as the firmware specification for microcontroller designs |
| Registry `roles`, `requires_driver`, `family`, `tags` | component registry | Useful hints, but no pin-level signal-flow semantics |
| Design patterns (ports, purposes) | `data/knowledge/patterns.yaml` | Useful as repair suggestions; no behavioural semantics |

Also found and fixed while mapping the problem: the buzzer's pins were `POWER`/`GROUND`, so a
low-side-switched buzzer put a "GROUND" pin on a transistor collector net (misclassified as a rail).
They are now `PASSIVE` (ids unchanged); E014 was generalised so a two-terminal load's voltage rating
is still enforced against the rail it connects to.

## 2. Architecture

```
Natural language
   └─► Requirements (AI)  ── functional_intent: FunctionalIntent   (extracted BEFORE any design exists)
          └─► AI topology proposal (tools: library, patterns, calculators, validate_design)
                 └─► Electrical validation (E0xx/W0xx)             deterministic
                 └─► Functional validation (F0xx/F1xx)             deterministic  ◄── this stage
                        └─► repair loop receives coded findings + repair hints + patterns
                 └─► Schematic projection + LVS                    deterministic
                        └─► 2D Studio: "✓ valid" + "✓/✕ function", Function tab, path highlight
```

**Principle kept:** the AI may *extract* intent; it never judges whether the intent is met. The
intent is taken from the requirements step, stored separately from the design
(`StudioDocument.intent`, `Orchestrator.functional_intent`), and the design step cannot rewrite it.

## 3. `FunctionalIntent` (`src/functional/intent.py`)

```
signals:   [{id, role: input|output, quantity, component_hint?}]
behaviors: [{id, when: {input?, relation, threshold?{kind: fixed|adjustable|unspecified, value?}},
                  then: {output, effect}}]
processing: any | analog | microcontroller | logic
required_components: [...]
```
* `relation`: above, below, present, absent, pressed, released, proportional, inverse, changes, any;
  `periodic`/`always` with no input for autonomous behaviour (oscillators, firmware).
* `effect`: on, off, proportional, inverse, display, toggle, pulse.
* `quantity` comes from a controlled vocabulary (`data/knowledge/functional_vocabulary.yaml`):
  inputs temperature, light, motion, distance, humidity, gas, acceleration, rotation, press,
  setting, logic, signal; outputs light_emission, sound_emission, motion_output, display, switching,
  storage, logic, signal. Free wording ("heat", "beeper", "darkness") is mapped deterministically;
  unmapped wording becomes NOT CHECKABLE (F106), never a guess.
* Every id a behaviour uses must be declared in `signals`. Live runs showed Gemini sometimes returns
  `signals: []` with ids such as `light_sensor`/`warning_led` in the behaviours (3 of 6 first-round
  runs). The prompt now states the rule with a second worked example, and `normalize_intent`
  recovers such ids deterministically when the id itself is vocabulary; the recovery is shown to the
  user as an interpretation note, never silently.

## 4. Functional profiles — registry knowledge (`data/knowledge/functional_profiles.yaml`)

Per family, with per-part overrides where pin names differ; unknown parts get an honest derived
profile (inputs → outputs, sign unknown). A profile states:

* what the part senses or produces (`quantities`),
* sensor output pins and their **sign** (LM35 VOUT +1; PIR OUT +1; digital/encoded outputs 0),
* resistive sensors' dR/dq (LDR −1; button −1; thermistor from the instance `type` parameter
  NTC −1 / PTC +1 / unknown → 0),
* load terminals (LED anode/cathode, buzzer, motor and relay coil — unpolarised where relevant),
  control inputs (relay module, servo, displays),
* signal transfers with signs — comparator/op-amp IN+→OUT +1, IN−→OUT −1; transistor
  control→collector/drain −1, control→emitter/source +1; 555 TRIG/THRES→OUT −1; logic gates
  ±1/0; ULN2003 IN→OUT −1; L293D A→Y +1; ADC/DAC 0,
* decision capability: explicit (comparator, open-loop op-amp, 555), programmable (MCU), implicit
  (transistor V_BE, logic thresholds),
* generators: parts that drive outputs without an input (555 OUT, microcontrollers).

* minimum drive current for loads (`min_drive_ma`, with the basis stated) and which outputs are
  open-collector/open-drain (`open_collector_outputs`), for F010.

Where a registry part is a *module*, the profile describes the module: `sensor:mq2` (VCC/GND/A0/D0
breakout) has A0 +1 and D0 −1, because its D0 comes from an on-board LM393 and goes low above the
trimmer setting.

These are standard device-physics facts. There are no component-name special cases in code.

## 5. Signal-flow graph (`src/functional/graph.py`)

Nodes: signal nets (power and ground rails are **never traversed**, so a pull-up to VCC is not a
path), `q:<part>` (a quantity enters), `a:<part>` (an output is activated), `g:<part>`
(autonomous generator). Edges carry a sign. A path's sign is the product of its edge signs. Two
cases are special:
* a resistive sensor's sign depends on its **divider position** (to the supply = top, to ground =
  bottom), computed from the rails its terminals touch;
* a microcontroller edge takes its sign from the design's `LogicRule` (e.g. `ldr1 < T → led1 HIGH`
  gives −1); without a rule the polarity is NOT CHECKABLE.

## 6. Where it plugs in

* `Orchestrator`: requirements prompt asks for `functional_intent` (with vocabulary and example);
  `_full_validation` = electrical + functional; acceptance needs electrical PASS **and** no functional
  FAIL; the `validate_design` tool returns a `functional` block and an `overall: REJECTED…` marker;
  the repair message appends the coded functional failures with repair hints and patterns.
* Progress log: the studio job log now shows "Required behaviour: alarm on when temp above" and
  "Functional check → FAIL: F010 …" instead of raw event names, and a failed job's error lists the
  last functional failures as well as electrical errors (it was empty when only function failed).
* `StudioDocument.intent`, `StudioState.functional`, `explanation["function"]`, edit op
  `set_intent`, `/api/open` accepts an intent, examples load `data/examples/intents/<id>.json`.
* CLI `design function <design.json> [--intent file]`.
* UI: Function tab (verdict, requested behaviours with decision/driver roles, findings with repair
  hints, click-to-highlight the path on the canvas), a "function" badge next to the electrical badge;
  the electrical tab is now labelled "Electrical".

## 7. Hooks for the future physical/3D stage

No 3D work was done. The functional graph is independent of both projections (schematic and future
physical); it depends only on the engineering design and registry knowledge, so a breadboard/3D view
can reuse it unchanged (e.g. to highlight the active signal path physically).
