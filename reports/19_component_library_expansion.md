# 19 — Component & Knowledge Ecosystem Expansion

## 1. Starting point

29 registry entries (report 05 said 30; 29 load), no symbol data, string-only electrical properties,
substring search, 8 curriculum concepts whose `components` referenced non-existent IDs.

## 2. Model extensions (`src/core/models.py`, all optional / backward compatible)

* `PinDefinition`: `number` (package pin), `supply: source|sink` (who drives a rail),
  `nominal_voltage`.
* `ComponentType`: `short_name`, `family`, `tags`, `symbol {name, pin_map, ref_prefix, box_sides}`,
  `physical {package, mounting, breadboard_compatible, pin_pitch_mm, body_mm, asset_3d}` (for the
  future physical/3D projection), `education {summary, how_it_works, typical_uses, common_mistakes}`,
  `design_constraints [{kind, pins, value, severity, note}]` — machine-checkable rules.
* New categories: SEMICONDUCTOR, INTEGRATED_CIRCUIT, POWER_MANAGEMENT, SWITCH, DISPLAY, ACTUATOR,
  MEMORY, INTERFACE, LOGIC.
* `EngineeringDesignProject.assumptions`; `ValidationResult.infos` and `checks_run`.
* `core/units.py`: engineering-notation parser/formatter (`4k7`, `100nF`, `3.3V-5V`); unparseable →
  None (= unknown), never a guess.

## 3. Library (86 types, `data/components/registry.yaml` + `data/components/library/*.yaml`)

| Domain | Added |
|---|---|
| Passives / switches | inductor, 2-pin push button, SPST slide switch |
| Discrete semiconductors | 1N4148, 1N4007, 1N5819 Schottky, 1N4733A Zener, BC547, 2N3906, 2N7000, IRLZ44N (logic-level), BS250 |
| Power | 9 V, 4×AA, 2×AA batteries, USB 5 V; LM7805, AMS1117-3.3 |
| Analog / mixed-signal ICs | MCP6001, LM358, LM393, NE555, ADS1115, MCP3008, MCP4725 |
| Digital logic | 74HC00/04/08/32/86/74 (standard DIP pinouts) |
| Drivers / interface / memory | L293D, ULN2003A, BSS138 4-ch level shifter, 24LC256 |
| Boards / sensors / actuators / connectors | Arduino Uno R3, Raspberry Pi Pico, LM35, 5 V relay (bare coil), 1×2/1×3/1×4 headers, screw terminal |
| Idealised primitives (object_type ≠ PHYSICAL) | ideal DC source, ideal NMOS/PMOS, ideal op-amp, AND/OR/NOT/NAND/NOR/XOR/XNOR, D flip-flop, logic input/output |

Every entry has a family, symbol mapping (verified bijective by tests), and — for physical parts —
package data. Existing entries gained symbols, families, short names, supply roles (ESP32 3V3 =
source 3.3 V, VIN = sink; rail = source), constraints (LED series resistor; DS18B20/DHT11 pull-ups;
motor flyback) and education text.

**Data honesty rules** (stated at the top of each YAML file): headline datasheet values only;
supply-dependent limits (e.g. CMOS input max = VCC+0.5 V) are *omitted* so the validator reports
"not checkable" (W002) instead of assuming a number; load-current keys are reserved for loads
(the tactile button's `max_current` was renamed `contact_current_max` because E015 counted it as a
50 mA load — a latent false positive).

**Integrity found by tests during the work:** the loader silently skipped entries with YAML-typing
mistakes (`aliases: [7805]` → int; `1,2EN` split inside a flow mapping). A test now asserts every
declared entry loads. Another test found a pattern listing a pin-incompatible "alternative" part.

## 4. Search

`ComponentRegistry.search` is ranked: whole-query substring (legacy behaviour, highest) else AND
over tokens across id/name/aliases/family/tags/roles/interfaces/category/description with field
weights, plural stemming, exact-family bonus, and *optional* value/descriptor tokens (`10k`, `red`,
`small`). "temperature sensor" → LM35/DS18B20/DHT11/thermistor; "resistor 10k" → resistor;
"quantum flux capacitor" → nothing. `catalog()` gives the AI a compact one-row-per-part view.

## 5. Knowledge beyond parts

* **Design patterns** (`data/knowledge/patterns.yaml`, `src/knowledge/`): 16 functional blocks —
  LED indicator, voltage divider, divider level shifter, button pull-down, NPN and MOSFET low-side
  switches, flyback diode, I2C pull-ups, RC low-pass, non-inverting amplifier, common-emitter stage,
  CMOS inverter, 555 astable, linear regulator, comparator threshold, H-bridge. Each has parts
  (roles, allowed alternatives), ports, pin-level nets, calculators. `instantiate_pattern` +
  `apply_fragment` merge a block into a design (nets merge when a port binds to an existing net).
  **Test:** every pattern, bound into a harness, passes deterministic validation and yields an
  LVS-clean schematic.
* **Calculators** (`validation/calculations.py`): LED resistor, voltage divider, RC time constant,
  BJT base resistor (rounds *down* to keep saturation), 555 astable, non-inverting gain — exposed to
  the AI as the `calculate` tool.
* **Validation from metadata:** constraints drive E007 (generalised), E017/W005 flyback, W003 series
  resistor, W004 pull-ups, W006 decoupling (INFO level → `infos`); E018 polarity uses the symbol pin
  map to find anode/cathode. New parts gain checks through data, not code.

## 6. Validator changes (codes unchanged in meaning)

* Single supply notion for E014/E016: pin `supply` metadata, instance `voltage` parameter for
  configurable sources (a `power-rail` with `voltage: 3.3` is now 3.3 V, previously treated as 5 V),
  legacy fallback for entries without metadata.
* E016 propagates supply through series elements (switch, jumper, fuse, inductor, diode), so a power
  switch in front of a regulator is no longer a false error.
* E004/E005 apply only to designs containing parts with supply/ground pins (pure gate-level diagrams
  are legitimate). W002 skips idealised primitives.
* `checks_run` records every rule and its outcome (PASS/FAIL/WARN/NOT_APPLICABLE) for explanation.
* **E019 SOURCE_RETURN_OPEN** and **W007 SUPPLY_UNCONNECTED** were added after a live Gemini design
  (Pico PWM motor) passed validation with the battery's negative terminal unconnected and the Pico's
  supply inputs unconnected — E009 only checks that a part has *some* connection. The design is kept
  in `tests/fixtures/ai_rejected/` and must stay rejected.
* Tests: `tests/unit/test_validation_constraints.py` (28) + all 31 legacy validator tests unchanged.

## 7. Limitations

* 86 parts is deliberately curated, not exhaustive; SPICE models are not attached.
* Many signal pins lack voltage limits by design (supply-dependent); a future improvement is
  expressing limits relative to the part's supply pin ("VCC+0.5") and resolving them per design.
* Multi-unit ICs (dual op-amps, quad gates) are one symbol.
