# 21 — Stage Verification (2D Schematic Studio)

Date: 2026-09-24. All numbers below were produced by commands run in this session.

## 1. Automated tests

| Suite | Command | Result |
|---|---|---|
| Python (all) | `pytest` | **363 passed, 5 skipped** (baseline at start of stage: 140 passed, 3 skipped) |
| — legacy tests | (unchanged files) | all 140 original tests still pass; 2 assertions in `test_curriculum.py` relaxed from `count == 8` to `>= 8` + "the 8 originals still exist" (they encoded data size, not behaviour) |
| — schematic engine | `tests/unit/test_schematic_engine.py` | 119 (incl. AI-generated fixtures) |
| — validator additions | `tests/unit/test_validation_constraints.py` | 30 |
| — knowledge (patterns, calculators, curriculum graph) | `tests/unit/test_knowledge.py` | 48 |
| — studio backend + HTTP API | `tests/unit/test_studio.py` | 19 |
| — Gemini resilience (no network) | `tests/unit/test_provider_gemini_resilience.py` | 7 |
| Skipped | OpenAI live (no key) ×3, Gemini live ×2 (opt-in: `ILLUS_LIVE_TESTS=1`) | — |
| Frontend | `npm test` (vitest) | **13 passed**, `tsc -b` clean, `vite build` OK |
| Real browser | `python scripts/ui_e2e.py` (Chrome DevTools Protocol) | **12/12 UI checks passed** |

## 2. End-to-end vertical slice (live Gemini)

Prompt: *"Make an automatic night light that turns an LED on when it gets dark. Power it from a 9V
battery and do not use a microcontroller."* (`scratch/stage2/live_generate.py`)

```
[ 0.0s] Reading the request
[27.1s] Understood intent: Make an automatic night light powered by a 9V battery without a microcontroller
[33.0s] Using tool browse_library
[41.1s] Using tool calculate_led_resistor
[46.2s] Checking a draft design with the deterministic validator → PASS
STATUS: done | model: gemini-3.5-flash-lite | 4 model calls, 3 tool calls, 0 repairs
DESIGN: 11 parts, 8 nets — LDR divider, LM393 comparator with potentiometer threshold,
        10k output pull-up, 2N2222 driver, LED + 330 Ω, 9 V battery
VALIDATION: PASS (3× W002 "not checkable")      SCHEMATIC LVS: consistent, 1 crossing, 37 ms
```

The design is not one of the reference examples (the AI chose a comparator topology on its own) and
is electrically correct on review (dark → IN+ > IN− → open-collector output released → pull-up turns
the transistor on). It is kept as `tests/fixtures/ai_generated/night_light_comparator_gemini.json`
and must keep validating and drawing cleanly. In the browser, generated states load through the same
`StudioState` path exercised by the UI E2E test (the mock-provider HTTP test covers the job route).

**Second prompt (different domain):** *"Control the speed of a small 6V DC motor with PWM from a
Raspberry Pi Pico. The motor runs from a 4xAA battery pack."* The model looked up the
`mosfet_low_side_switch` and `flyback_protection` patterns and reproduced them (IRLZ44N, 100 Ω gate
resistor, 10 k pull-down, 1N4007). **First run: validation PASSED although the battery's negative
terminal was unconnected** — a genuine validator gap (E009 only checks that a part has *some*
connection). Added **E019 SOURCE_RETURN_OPEN** and **W007 SUPPLY_UNCONNECTED**; the flawed design is
kept in `tests/fixtures/ai_rejected/` and is now rejected. Second run (same prompt): correct common
ground on the first draft (PASS, W007 noting the Pico's own supply is not wired — implicitly USB).
It did not exercise a repair; AI output varies between runs, which is why the rules, not the model,
are the gate. Both passing AI designs are kept in `tests/fixtures/ai_generated/`.

**Provider reality encountered.** During the session `gemini-3.5-flash` was persistently overloaded
(503), several models were overloaded or rate-limited (free tier: 5 requests/min and 20
requests/day per model), and long requests timed out. Resulting provider changes: header-based auth
(key never in URLs), timeouts, retry on transient errors, honouring `retryDelay` on per-minute 429,
model fallback chain on 503/404/timeouts/daily-quota exhaustion, bounded re-cycling, and reporting the
model that actually answered. All covered by offline unit tests. The API key was never printed; live
runs loaded it from the Windows user environment into the child process only.

## 3. Reference designs

13 designs (11 new examples across analog, digital, mixed-signal, power, MCU; 2 golden fixtures):
all pass validation, all schematics LVS-consistent with 0 overlaps, 5 crossings in total, 0 routing
fallbacks, 6–200 ms layout each.

## 4. Issues found and fixed during verification (evidence of the checks working)

* `src/schematic/models.py` was not importable (report 15's "schematic tests pass" claim was false).
* `.venv` console script / editable install pointed at a different checkout on `Y:` (fixed the `.pth`;
  the `.exe` still points to Y: — use `python -m cli.main`; documented).
* `cli/main.py` registered the `render` commands after the `__main__` guard (fixed).
* YAML typing mistakes silently dropped parts (now a test fails if any declared entry doesn't load).
* A pattern listed a pin-incompatible alternative (caught by the pattern-reference test).
* Tactile button contact rating counted as a GPIO load by E015 (data renamed).
* E016 false positive through a power switch; E004/E005 false positives for gate-level diagrams;
  rail `voltage` parameter ignored by E014.
* Layout defects found by rendering (flags rotated, wires through text, crowded box labels, ports
  missing from footprints) and UI defects found by the browser test (new parts off-screen).

## 5. Known gaps (not hidden)

* No validation yet for unused-input termination (e.g. LM393 channel 2 left floating), MCU boards assumed USB-powered
  without an explicit assumption (W007 only warns), rail current
  budgets, or thermal dissipation; no simulation.
* Live AI success depends on provider availability/quota; failures are reported, never masked.
* The AI loop is single-shot per prompt (no conversational refinement of an existing design yet —
  the edit-op API is the foundation for it).
