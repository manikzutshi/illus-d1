# 23 — Functional Validator

Module: `src/functional/validator.py` — `validate_function(design, intent, registry) -> FunctionalReport`.

## 1. Checks (deterministic)

| Code | Status | Check |
|---|---|---|
| F001 | FAIL | a requested **input** quantity is implemented by some part (by profile, not by name) |
| F002 | FAIL | a requested **output** effect is implemented by some part |
| F003 | FAIL | the input can influence the output through the circuit (signal-flow path exists) |
| F004 | FAIL | the output is **controlled** — not permanently powered, never powered, or unconnected |
| F005 | FAIL | a threshold behaviour (above/below) has a stage able to decide (comparator, MCU, logic, switch) |
| F006 | FAIL | the **direction** matches (ON above vs ON below; present vs absent; proportional vs inverse) |
| F007 | FAIL | an adjustable threshold is set by an adjustable part feeding the decision stage's *other* input (or an MCU input) |
| F008 | FAIL | a load the registry marks `requires_driver` has a switch/driver stage after the decision |
| F009 | FAIL / WARN | parts the user named are present **and** on a functional path. Names match identity fields as whole words; ratings and size words ("6V", "10k", "small") are ignored when the full wording does not match. If **no library part** matches the name, the finding is a WARN (a design cannot satisfy it, so blocking would only exhaust the repair budget) |
| F010 | FAIL | the output stage can actually **drive** the load: when a load is powered only through an open-collector/open-drain output's pull-up, the pull-up current (V/R summed over pull-ups to supply rails) must reach the load's `min_drive_ma` (LED 1 mA, buzzer 10 mA, motor/relay 50 mA) |
| F010 (transistors) | FAIL | an NPN collector / N-channel drain can only sink: a load between it and ground can never be driven (polarity from the registry symbol, `sink_only_by_symbol`) |
| F011 | FAIL | a polarised load can ever be **forward-biased**: its negative terminal is not held at the highest supply (nor its positive terminal at ground) through passives only |
| F101 | NOT_CHECKABLE | a path exists but its direction is undefined (MCU without logic rule, encoded/digital sensor, thermistor type unknown) |
| F102 | WARN | the threshold is implicit (transistor V_BE, logic input threshold) — works, imprecise |
| F103 | WARN | a part takes part in no functional path (support parts on functional nets — pull-ups, base resistors, flyback diodes — are not flagged) |
| F104 | NOT_CHECKABLE | the function would rely on parts whose behaviour is not modelled |
| F105 | WARN | different paths act in opposite directions. When they meet in a microcontroller through different sensor pins (e.g. MQ-2 A0 rises, D0 falls), the message names the pins: the logic rule names the part, not the pin |
| F106 | NOT_CHECKABLE | intent wording outside the vocabulary / dangling references |

Overall status = worst of FAIL > WARN > NOT_CHECKABLE > PASS. Only FAIL blocks acceptance.

When F011 fires for a load, F006 is **suppressed** for that load: a reversed LED also "responds the
wrong way" along every path, and reporting "behaviour is inverted" would steer a repair towards the
sensing side, which is not what is broken. The behaviour's explanation then says the direction cannot
be judged until the load is fixed.

Identical findings raised by two behaviours on the same path are reported once.

**Intent interpretation notes.** If a behaviour refers to a signal id that was never declared but
whose name is vocabulary ("light_sensor" → input `light`, "warning_led" → output `light_emission`),
`normalize_intent` declares it and the report lists this under `intent_notes` (shown in the Function
tab as "Interpreted: …"). It is graded normally. Ids that are not vocabulary remain F106.

**Path selection.** All simple paths (bounded) from every bound input to every bound output are
scored: correct polarity first, explicit decision stage next, then length. The report keeps the best
path per behaviour with its steps, sign, polarity basis, decision part, driver part and threshold
setter.

**Diagnosis on failure** is specific. For example: "Unable to establish a control path from u1
(LM35) to bz1 (Buzzer). The temperature signal reaches u2; bz1 is influenced only by q1." Every
finding carries `affected_instances/nets/pins`, the `behavior_id` / `signal_id` it grades, relevant
design `patterns` (e.g. `bjt_low_side_switch`, `comparator_threshold`) and a `repair_hint`.

**Explanation lines** (deterministic), e.g.:
"Temperature sensing is implemented by u1 (LM35)." · "The threshold is set by rv1 (Pot)." ·
"u2 (LM393) compares the sensor signal with the reference." · "q1 (BC547) drives bz1." ·
"Behaviour: bz1 turns ON when u1's temperature is above the threshold - as requested (from device
transfer directions)."

**Without intent** (manual designs, older examples), the report infers what the circuit does. For
example, the common-emitter example yields "j2 activation falls as signal rises at j1, via c1, q1, c3",
correctly an inverting stage. The status is NOT_CHECKABLE (no requirement to compare against).

## 2. Confidence boundaries (what it does NOT claim)

* Topology and **sign** reasoning only: no voltages, gains, hysteresis, timing or frequency. It says
  "the buzzer rises with temperature through a comparator" — not "at 31.2 °C".
* Analog competition between paths is flagged (F105), not resolved.
* Microcontroller behaviour is exactly what the design's logic rules state; firmware itself is not
  analysed. No rule → NOT_CHECKABLE, with a hint to add one. A rule may name the output itself or
  any part the microcontroller drives on the way to it (`btn1 == LOW → q1 HIGH` sets q1's control
  input; q1's transfer then carries the sign to the motor).
* Parts without a profile are treated generically (sign unknown) and the report says so.
* F010 only estimates the pull-up current (V/R, ignoring the load's own drop); it does not check
  transistor saturation, gate drive or supply capacity. F011 only recognises loads tied to a rail
  through passives; a load reversed between two active stages is not detected.
* Module-level facts are encoded where the registry part is a module: `sensor:mq2` is the common
  breakout whose D0 comes from an on-board LM393 and is **active-low** (A0 rises with gas). A bare
  MQ-2 element or a module with an inverting buffer would need a different profile.
* The intent is only as good as the requirements extraction. A wrongly extracted intent will be
  enforced faithfully; the Function tab shows the intent so a user can spot it, and `set_intent` can
  correct it.

## 3. Tests

* `tests/unit/test_functional.py` (78): 28 fixture cases across 9 functional classes (analog threshold
  alarm; light detector with op-amp + PNP; MCU + logic rules; button → MCU → relay with driver
  requirement; sensor → ADC → MCU → display; thermistor with unknown vs NTC type; requested part unused;
  gate-level logic; **regressions reproduced from live Gemini designs**: buzzer powered only by an
  open-collector pull-up → F010, daylight LED reversed → F011 without F006, and the same LED flipped →
  WARN F102 only, MQ-2 rule `D0 == HIGH` → F006 vs `D0 == LOW` → PASS, intent with undeclared
  signals → still graded; a requested "6V DC motor" / "small 5V buzzer" is recognised; a requested
  part absent from the library warns instead of blocking; an MCU reading both MQ-2 outputs names the pins;
  freezer alarm with the buzzer under an NPN collector → F010, and once moved → F006; button → Uno →
  IRLZ44N → motor with the rule written against the MOSFET → PASS, wrong level → F006). **All 28 fixtures are electrically valid** — they differ only functionally. Also:
  the 10 scenarios requested for this stage, reference-design regression, autonomous behaviour
  (555 blinker; removing the oscillator → F003), intent-free inference, vocabulary normalisation,
  every registry part's profile consistent with its pins, rails never traversed, determinism.
* `tests/unit/test_functional_repair_loop.py` (6): the broken temperature alarm passes electrical
  validation (the old pipeline would accept it); with intent the orchestrator rejects it, the repair
  message contains `F004`, `bz1`, its repair hint and `bjt_low_side_switch`; the repaired design is
  accepted; a never-fixed design fails after the repair budget; the `validate_design` tool reports
  `overall: REJECTED`; without intent behaviour is unchanged; the requirements schema is
  provider-safe (no `$ref`, enums preserved).
* `tests/unit/test_studio.py` (+8; the additions cover failed-job `last_attempt`, the validate-design summary "PASS electrically, functional FAIL", and the progress-log summaries "Required behaviour: …" and
  "Functional check → FAIL: F004 …", which previously appeared as raw event names): example states carry the report; an edit that disconnects the
  buzzer drive keeps electrical PASS but turns function FAIL (F004); `set_intent` changes what is
  graded; `/api/open` accepts an intent; a second server on the same port fails loudly.
* Browser E2E (+4 steps, 16/16): temperature alarm shows "does what was asked"; clicking the behaviour
  highlights its path; disconnecting BZ1's low side in the Inspector → badges "✓ valid" + "✕ function",
  F004 with hint; undo → PASS.
