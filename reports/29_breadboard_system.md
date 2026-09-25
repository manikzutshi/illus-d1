# 29 — Breadboard System and Physical Component Data

## 1. Breadboard model (`src/physical/breadboard.py`)

| Board | Terminal holes | Rails | Tie points | Outline (modelled) |
|---|---|---|---|---|
| half | 30 columns × rows a–j = 300 | 4 × 25 (groups of 5, one-hole gaps) | **400** | 82.5 × 57.4 × 8.5 mm |
| full | 63 × 10 = 630 | 4 × 50 | **830** | 165.1 × 57.4 × 8.5 mm |

(Tie-point totals are tested against the board names.) Geometry on the 2.54 mm grid: rows a–e at
y = −5.5 … −1.5 pitch, f–j at +1.5 … +5.5 pitch, so the rows either side of the trench are 7.62 mm
apart (DIP row spacing); rails at ±8.5 (+) and ±9.5 (−) pitch. The modelled width (57.4 mm) follows the
rail spacing; real boards are about 54.5 mm (noted in the board info).

Connectivity: rows a–e of a column are one node `top:<col>`, rows f–j `bot:<col>`, each rail one node
`rail:T+`, `rail:T-`, `rail:B+`, `rail:B-` (continuous; split rails on some full-size boards are not
modelled). Hole ids: `e12`, `T+7`.

## 2. Physical component data (`data/physical/`)

Registry `physical` blocks were reused; the missing knowledge lives in two data files so that no
part-specific code exists:

* `packages.yaml` — **20** package templates keyed by the registry's `physical.package` (DIP-8/14/16,
  TO-92, TO-220, DO-35, DO-41, axial 1/4 W, 6 mm tactile, 1×2/1×3/1×4 headers, SOT-23-5/6, SOT-223,
  MSOP-10, PP3, AA holders, 5.08 mm screw terminal).
* `parts.yaml` — **39** per-part entries: the 29 core parts that had no `physical` block, boards and
  modules (Pico pin numbers from its datasheet, Arduino Uno R3 header order, ESP32 DevKit V1 header
  order), off-board terminals and lead colours, pin aliases and internal links.

Template fields: `template` (two_lead | inline | dip | dual_row | smd_adapter | offboard), pin order or
pin numbers, bendable lead `spans`, `row_span`, `pitch_steps`, `body_mm`, `body_z`, `body_offset_mm`,
`visual`, `source`, `note`, `variant_note`, `terminals`, `internal_links`, `pin_alias`.

**Coverage of the 69 physical registry types (measured):** 53 breadboard-insertable (18 inline,
14 two-lead, 14 DIP, 3 dual-row, 4 via SMD adapter) and 16 off-board; geometry source 4 datasheet,
28 standard, 29 typical, 8 assumed; **0 generic fallbacks** (the fallback path exists and is tested for
parts added later without data).

**Honesty rules** (from the stage brief, "unknown should remain unknown"):

* nothing is invented silently: every definition records `source`; `assumed` geometry raises P101;
* vendor-dependent pinouts (2N2222 TO-92 E-B-C, OLED GND/VCC order, DHT11 3-pin module, HC-SR501,
  MQ-2 module, ESP32 30-pin, relay modules, 7-segment) carry a `variant_note` → P102 and a "check the
  pin order on your part" line in the build steps;
* a part with no usable data becomes a labelled generic module with a registry-order header (P101),
  shown with a "?" label and dashed tag in 3D;
* SMD parts are shown on a generic SIP breakout adapter (P103), because a bare SOT-23 or MSOP cannot
  be pushed into a breadboard.

A data-consistency test checks that every pin named in `parts.yaml` exists in the registry. It was
added after a real bug: in YAML 1.1 an unquoted `NO` parses as boolean `false`, which silently
removed the relay's NO terminal (caught by physical verification as P002, then fixed by quoting).

## 3. Mounting classes

| Class | Examples | Physical form |
|---|---|---|
| Two-lead, bendable | resistors, diodes, LEDs, capacitors, LDR, thermistor, buzzer | row / across the trench / into a rail |
| Inline | TO-92, TO-220, headers, trimpot, HC-SR04, MPU-6050, OLED | along a row; module bodies may overhang the board edge |
| DIP / dual-row | 555, LM393, 74HC, L293D, ULN2003, 24LC256, Pico, 7-segment, 4-pin tactile | straddle the trench |
| SMD | MCP6001, ADS1115, MCP4725, AMS1117 | SIP breakout adapter (assumed) |
| Off-board | batteries, USB supply, Arduino Uno, ESP32 DevKit, relays, motor, servo, sensor modules, LCD | beside the board with leads / jumpers |
| Virtual | ideal sources, ideal transistors, gates, rail/ground symbols | no physical form (P105) |
