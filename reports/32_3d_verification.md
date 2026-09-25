# 32 — Physical / 3D Stage: Verification

Date: 2026-09-25. All numbers from runs in this checkout at the end of the stage. No Git operations.

## 1. Test results

| Suite | Result |
|---|---|
| Python (`pytest`) | **513 passed**, 5 skipped (opt-in live-provider tests) — baseline 460 / 5, no regressions |
| `tests/unit/test_physical.py` | 53 (breadboard model, footprints and data consistency, all reference designs, build invariants, determinism, serialisation, traceability, colour bands, leads, assembly steps, fault injection, studio ops, HTTP API, CLI, NL → physical flow) |
| Frontend `tsc -b` / vitest | clean / **24 passed** (13 existing + 11 physical: coordinate transforms vs backend geometry, hole rebuild, drag snapping, traceability, view-switch state, API physical flag) |
| Browser E2E (`scripts/ui_e2e.py`, headless Chrome with software WebGL, fresh server on the current code) | **23/23** (16 existing + 7 physical) |
| Frontend build | main bundle 247 KB; 3D chunk ~1.0 MB, lazy |

New browser E2E steps: the Physical 3D view renders the build (WebGL) and the footer shows "build
matches netlist ✓"; the Assembly tab shows verification + 22 build steps; selecting Q1 from a build
step selects it in the Inspector (holes C b14, B b13, E b12) and highlights it in 3D; moving Q1 to a20
through the Inspector is accepted by the backend; moving it to a10 is refused ("pin C would land in
top:10, which carries net ref (a short)"); switching back to the schematic keeps Q1 selected; undo
restores the previous breadboard placement.

The E2E browser now starts with `--use-angle=swiftshader --enable-unsafe-swiftshader` (software
WebGL); the earlier 2D steps are unaffected.

## 2. Reference designs

| Design | Board | On board / beside | Jumpers + leads | Wire length | Physical check | Time |
|---|---|---|---|---|---|---|
| astable_555_blinker | half | 7 / 1 | 8 + 2 | 232 mm | PASS | 136 ms |
| cmos_inverter | — | — | — | — | NOT_APPLICABLE (primitives) | 0 ms |
| common_emitter_amplifier | half | 10 / 1 | 4 + 2 | 178 mm | PASS | 128 ms |
| half_adder | — | — | — | — | NOT_APPLICABLE (primitives) | 0 ms |
| i2c_adc_logger | half | 5 / 1 | 16 + 0 | 524 mm | WARN P101, P103 | 65 ms |
| night_light_transistor | half | 6 / 1 | 4 + 2 | 144 mm | PASS | 84 ms |
| opamp_noninverting | half | 6 / 1 | 4 + 2 | 126 mm | WARN P101, P103 | 72 ms |
| pwm_motor_controller | half | 5 / 3 | 7 + 4 | 662 mm | PASS | 89 ms |
| regulated_5v_supply | half | 7 / 1 | 6 + 2 | 246 mm | PASS | 95 ms |
| relay_driver | half | 3 / 4 | 8 + 2 | 531 mm | WARN P101, P102 | 41 ms |
| temperature_alarm | half | 7 / 1 | 8 + 2 | 237 mm | WARN P101 | 70 ms |
| temperature_monitor | half | 3 / 1 | 8 + 0 | 405 mm | WARN P102 | 41 ms |

Every physical design builds on a half-size board and **matches its netlist (no ERROR)**. Every
warning is an honest data caveat (assumed USB supply or relay geometry, SMD adapters, vendor pinouts),
not a connectivity problem. All 12 were also opened in the browser 3D view without error.

**Hand review of the temperature alarm build** (not just the status): LM393 across the trench with
pin 1 (OUT1) at e9; R1 (10 kΩ pull-up) from the + rail (T+9) straight into OUT1's strip; Q1's emitter
(b12) shares the LM393 GND strip, so no wire is needed; the LM35's supply pin shares the LM393 VCC
strip; the buzzer stands between the bottom + rail and Q1's collector strip; the USB supply's leads go
into T+1 / T−1; every remaining connection is one short jumper. A person could build it from the
Assembly steps.

## 3. Natural language → … → physical build

* **Offline, in the test suite** (`test_natural_language_to_verified_physical_build`): a scripted
  provider returns an intent, a functionally broken first draft (buzzer not in the control path) and
  the repaired design. The studio job completes with electrical PASS, functional PASS (after one
  repair), schematic LVS OK, a physical build and physical verification OK.
* **Live, Gemini** (the key read from the environment, never printed; answered by
  `gemini-3.5-flash-lite` through the fallback chain):

| Prompt | Electrical | Functional | Schematic LVS | Physical | Hand review |
|---|---|---|---|---|---|
| "Build a temperature alarm using an LM35, a comparator, a transistor and a buzzer." | PASS | PASS | OK | WARN (P101 stand-in USB supply), ok, half board, 8 jumpers + 2 leads, 176 ms | correct: every net realised by a shared strip or one jumper; nothing unrelated shares a strip |
| "Make an LED blink about once per second with a 555 timer from a 9V battery." | PASS | PASS | OK | PASS, half board, 8 jumpers + 2 leads, 150 ms | correct: 555 pins 1–8 at e18…e21/f21…f18; TRIG/THRES joined by one jumper; timing capacitor cathode in the GND strip; RESET tied to VCC through strip + rail |

The browser E2E covers the view side of the same flow (state → Physical 3D → selection → edits); it
does not drive a live AI generation (that would spend quota on every run).

## 4. Defects found and fixed during the stage

| Found by | Defect | Fix |
|---|---|---|
| Physical verification (P002) | Relay `NO` terminal missing: YAML 1.1 parses unquoted `NO` as `false` | quoted; data-consistency test for every pin named in the physical data |
| Physical verification (P006) | I²C logger: two nets open — the SMD adapter body covered three rows, leaving one free hole per strip, and the spanning tree ignored hole capacity | SIP adapter modelled upright; capacity-aware dry-run tree with rails as fallback hubs |
| Manual op test | A move onto an occupied spot silently pushed the other part away (locked parts placed first) | `seq` ordering: the latest move must fit around existing parts; otherwise refused with the reason |
| First run | 0.4–2.7 s per design | ranked candidate search: 41–175 ms |
| Screenshot review | Camera too far; right-panel tabs overflowed ("Explain" hidden) | tighter fit, compact tabs |

## 5. Known limitations and risks

* **Physical data**: 29 of 69 physical parts rely on "typical" data and 8 on "assumed" data; vendor
  pinouts vary. Verification flags these (P101/P102), but a real build must still check the part in
  hand. Arduino Uno header positions are approximate (order is correct).
* **Placement**: one breadboard, greedy scoring, no multi-board or perfboard layouts; boards whose
  headers do not fit (ESP32 DevKit) go beside the board.
* **Routing**: automatic L-shaped jumpers; no manual wire editing; wires may cross.
* **3D**: procedural, not photorealistic; no GLB models shipped (the path exists).
* **Not verified**: electrical behaviour on the breadboard (no simulation); wire lengths against real
  jumper sizes; mechanical fit beyond plan-view boxes.
* **Legacy prototype files** (old `App.tsx`, `core/*`, `Scene3D.tsx`, `PhysicalPreview.tsx`, GLBs,
  `generate_glbs.py`) are no longer used by the studio but were left in place (DEFER); the owner may
  remove them.
