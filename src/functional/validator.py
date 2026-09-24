"""Deterministic functional (behavioural-intent) validation.

Electrical validation answers "is this circuit electrically acceptable?". This module answers
"does this circuit plausibly implement the behaviour the user asked for?", using only the
design netlist, registry functional profiles and the extracted FunctionalIntent. It never asks a
language model whether the design is right.

Result statuses per check: PASS | FAIL | WARN | NOT_CHECKABLE. Codes:

  F001 INPUT_NOT_IMPLEMENTED     no part provides the requested input quantity
  F002 OUTPUT_NOT_IMPLEMENTED    no part provides the requested output effect
  F003 NO_FUNCTIONAL_PATH        the input cannot influence the output through the circuit
  F004 OUTPUT_NOT_CONTROLLED     the output is permanently powered / never powered / unconnected
  F005 NO_DECISION_STAGE         a threshold behaviour has no stage that can make a decision
  F006 POLARITY_INVERTED         the circuit does the opposite (e.g. ON below instead of above)
  F007 THRESHOLD_NOT_ADJUSTABLE  an adjustable threshold was requested but nothing sets it
  F008 DRIVER_REQUIRED           a load that needs a driver is driven directly by a logic/analog output
  F009 REQUESTED_PART_UNUSED     a part the user asked for is missing or not functionally involved
  F011 LOAD_NEVER_ACTIVATED      a polarised load is wired so it can never be forward-biased
  F010 INSUFFICIENT_DRIVE        the load must be driven high by an output that can only sink (open collector)
                                 and the pull-up cannot supply the current the load needs
  F101 POLARITY_NOT_CHECKABLE    path exists but its direction cannot be determined (NOT_CHECKABLE)
  F102 IMPLICIT_THRESHOLD        threshold relies on a transistor / logic input threshold (WARN)
  F103 PART_NOT_IN_FUNCTION      a part participates in no functional path (WARN)
  F104 FUNCTION_NOT_MODELLED     the function relies on parts whose behaviour is not modelled (NOT_CHECKABLE)
  F105 AMBIGUOUS_POLARITY        different paths give opposite directions (WARN)
  F106 INTENT_INCOMPLETE         intent could not be fully interpreted (NOT_CHECKABLE)
"""
from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from components.registry import ComponentRegistry, get_shared_registry
from core.models import EngineeringDesignProject

from .graph import Edge, FunctionGraph, build_graph, find_paths, reachable
from .intent import FunctionalIntent, normalize_intent

Status = Literal["PASS", "FAIL", "WARN", "NOT_CHECKABLE"]
_RANK = {"PASS": 0, "NOT_CHECKABLE": 1, "WARN": 2, "FAIL": 3}

REL_SIGN = {"above": 1, "present": 1, "pressed": 1, "proportional": 1,
            "below": -1, "absent": -1, "released": -1, "inverse": -1}
EFFECT_SIGN = {"on": 1, "proportional": 1, "pulse": 1, "off": -1, "inverse": -1}
THRESHOLD_RELATIONS = {"above", "below"}
DECIDING = ("explicit", "programmable", "implicit")
PATTERN_HINTS = {
    "F003": ["bjt_low_side_switch", "mosfet_low_side_switch", "led_indicator"],
    "F004": ["bjt_low_side_switch", "mosfet_low_side_switch"],
    "F005": ["comparator_threshold"],
    "F007": ["comparator_threshold"],
    "F008": ["bjt_low_side_switch", "mosfet_low_side_switch", "h_bridge_driver"],
}


class FunctionalFinding(BaseModel):
    code: str
    status: Status
    message: str
    behavior_id: Optional[str] = None
    signal_id: Optional[str] = None
    affected_instances: List[str] = Field(default_factory=list)
    affected_nets: List[str] = Field(default_factory=list)
    affected_pins: List[str] = Field(default_factory=list)
    patterns: List[str] = Field(default_factory=list)
    repair_hint: str = ""


class PathStep(BaseModel):
    instance: str
    kind: str
    from_node: str
    to_node: str
    sign: int
    pins: List[str] = Field(default_factory=list)


class BehaviorResult(BaseModel):
    behavior_id: str
    description: str
    status: Status
    input_instances: List[str] = Field(default_factory=list)
    output_instances: List[str] = Field(default_factory=list)
    path: List[PathStep] = Field(default_factory=list)
    path_sign: Optional[int] = None
    required_sign: Optional[int] = None
    polarity_basis: str = ""
    decision_instance: Optional[str] = None
    decision_kind: Optional[str] = None
    driver_instance: Optional[str] = None
    threshold_set_by: Optional[str] = None
    explanation: List[str] = Field(default_factory=list)


class InferredBehavior(BaseModel):
    input_instance: str
    output_instance: str
    sign: Optional[int]
    via: List[str]
    statement: str


class FunctionalReport(BaseModel):
    status: Status
    intent_present: bool
    summary: str
    behaviors: List[BehaviorResult] = Field(default_factory=list)
    findings: List[FunctionalFinding] = Field(default_factory=list)
    bindings: Dict[str, List[str]] = Field(default_factory=dict)
    inferred: List[InferredBehavior] = Field(default_factory=list)
    involved_instances: List[str] = Field(default_factory=list)
    explanation: List[str] = Field(default_factory=list)
    intent_notes: List[str] = Field(default_factory=list)   # deterministic interpretations of the intent

    def blocking(self) -> List[FunctionalFinding]:
        return [f for f in self.findings if f.status == "FAIL"]


# ── helpers ────────────────────────────────────────────────────────────────

class _Ctx:
    def __init__(self, design: EngineeringDesignProject, registry: ComponentRegistry, g: FunctionGraph):
        self.design, self.registry, self.g = design, registry, g
        self.refs = {c.instance_id: c.instance_id for c in design.components}
        self.types = {c.instance_id: registry.get(c.component_type) for c in design.components}
        self.partial: set = set()      # parts on partial (broken) paths - involved, just not connected through

    def name(self, iid: str) -> str:
        ct = self.types.get(iid)
        return f"{iid} ({ct.short_name or ct.name})" if ct else iid


def _rule_sign(design: EngineeringDesignProject, upstream: List[str], output: str) -> Tuple[Optional[int], str]:
    """Polarity a microcontroller logic rule gives between an upstream input part and an output part."""
    for rule in design.logic:
        acts = [a for a in rule.actions if a.output_instance == output]
        conds = [c for c in rule.conditions if c.input_instance in upstream]
        if not acts or not conds:
            continue
        c, a = conds[0], acts[0]
        op = c.condition.strip()
        val = str(c.value).strip().upper()
        if op in (">", ">="):
            cs = 1
        elif op in ("<", "<="):
            cs = -1
        elif op in ("==", "=") and val in ("HIGH", "1", "TRUE", "ON", "DETECTED", "PRESSED"):
            cs = 1
        elif op in ("==", "=") and val in ("LOW", "0", "FALSE", "OFF"):
            cs = -1
        else:
            cs = None
        st = a.state.strip().upper()
        as_ = 1 if st in ("HIGH", "ON", "TRUE", "1", "PWM") else (-1 if st in ("LOW", "OFF", "FALSE", "0") else None)
        if cs is None or as_ is None:
            return None, f"logic rule '{rule.rule_id}' is not directional"
        return cs * as_, f"logic rule '{rule.rule_id}' ({c.input_instance} {op} {c.value} → {a.output_instance} {a.state})"
    return None, ""


def path_polarity(design: EngineeringDesignProject, path: List[Edge], output: str) -> Tuple[Optional[int], str]:
    """(sign, basis). None = not checkable."""
    sign = 1
    upstream: List[str] = []
    for k, e in enumerate(path):
        if e.kind == "programmable":
            rs, basis = _rule_sign(design, upstream, output)
            if rs is None and not basis:
                # A rule may name the part the microcontroller pin drives ("btn1 == LOW -> q1 HIGH") rather
                # than the final output: the pin sets that part's control input, and the rest of the path
                # carries the signal on to the output.
                rest = path[k + 1:]
                for j, d in enumerate(rest):
                    if d.instance in (e.instance, output):
                        continue
                    ds, dbasis = _rule_sign(design, upstream, d.instance)
                    if ds is None and not dbasis:
                        continue
                    if ds is None:
                        return None, dbasis
                    tail = 1
                    for t in rest[j:]:
                        if t.sign == 0:
                            return None, f"{dbasis}; then {t.instance} ({t.kind}) passes the signal without a defined direction"
                        tail *= t.sign
                    return sign * ds * tail, f"{dbasis}, then {d.instance} drives {output}"
            if rs is None:
                return None, basis or f"{e.instance} is programmable and no logic rule defines its behaviour"
            return sign * rs, basis
        if e.sign == 0:
            return None, f"{e.instance} ({e.kind}) passes the signal without a defined direction"
        sign *= e.sign
        upstream.append(e.instance)
    return sign, "device transfer directions"


def _has_negative_feedback(ctx: _Ctx, iid: str) -> bool:
    """Op-amp with a passive between its output and inverting input acts as an amplifier, not a comparator."""
    prof = ctx.g.profiles[iid]
    for src_pin, dst_pin, sign in prof.transfers:
        if int(sign) != -1:
            continue
        a, b = ctx.g.node(ctx.g.net_of.get((iid, src_pin))), ctx.g.node(ctx.g.net_of.get((iid, dst_pin)))
        if a and b and any(e.kind == "passive" and e.dst == a for e in ctx.g.edges.get(b, [])):
            return True
    return False


def _decision(ctx: _Ctx, path: List[Edge]) -> Tuple[Optional[str], Optional[str]]:
    best: Tuple[Optional[str], Optional[str]] = (None, None)
    order = {"explicit": 3, "programmable": 3, "implicit": 1}
    for e in path:
        prof = ctx.g.profiles.get(e.instance)
        if prof is None or prof.decision is None or e.kind not in ("transfer", "switch", "programmable"):
            continue
        kind = prof.decision
        if prof.kind == "amplifier" and _has_negative_feedback(ctx, e.instance):
            kind = "implicit"
        if best[1] is None or order[kind] > order[best[1]]:
            best = (e.instance, kind)
    return best


def _driver(ctx: _Ctx, path: List[Edge], decision_iid: Optional[str]) -> Optional[str]:
    after = False if decision_iid else True
    found = None
    for e in path:
        if e.instance == decision_iid:
            after = True
            continue
        if after and e.kind == "switch":
            found = e.instance
    return found


def _bind(ctx: _Ctx, quantity: str, role: str, hint: Optional[str]) -> List[str]:
    nodes = ctx.g.sources if role == "input" else ctx.g.sinks
    cands = [n.split(":", 1)[1] for n, qs in nodes.items() if quantity in qs]
    if role == "input":
        # a user setting (knob) is only an *input* when the intent asks for one
        cands = [c for c in cands if not (ctx.g.profiles[c].kind == "adjustable" and quantity != "setting")]
    if hint:
        hinted = [c for c in cands if _matches(ctx, c, hint)]
        if hinted:
            return hinted
    return sorted(cands)


_FILLER = {"a", "an", "the", "module", "sensor", "component", "part", "small", "tiny", "little", "mini",
           "large", "big", "standard", "generic", "simple", "some"}
# A rating or size ('6V', '10k', '220R', '100uF', '4.7kΩ', '5mm'), not an identity. Part numbers such as
# LM35 or 2N2222 start with letters or mix letters after digits in other ways and are kept.
_SPEC = re.compile(r"^\d+(\.\d+)?(v|mv|kv|a|ma|ua|w|mw|k|m|r|ohm|ohms|uf|nf|pf|mh|uh|hz|khz|mhz|mm|cm|rpm|%)?$")


def _type_matches(ct, hint: str) -> bool:
    """Does a user-named part ('LM35', 'buzzer', 'NPN transistor', '6V DC motor') refer to this
    registry type? Only identity fields count (id, name, short name, aliases, family), as whole
    words; ratings and size adjectives in the hint are ignored if the full wording does not match."""
    if ct is None or not hint.strip():
        return False
    words = lambda t: set(re.split(r"[^a-z0-9.+]+", t.lower())) - {""}
    ident = [ct.component_type_id, ct.name, ct.short_name or "", ct.family or "", *ct.aliases]
    ident_words = set().union(*(words(n) for n in ident)) | {n.lower() for n in ident if n}
    h = hint.lower().strip()
    if h in ident_words:
        return True
    hw = words(h) - _FILLER
    if hw and hw <= ident_words:
        return True
    core = {w for w in hw if not _SPEC.match(w)}
    return bool(core) and core <= ident_words


def _matches(ctx: _Ctx, iid: str, hint: str) -> bool:
    return _type_matches(ctx.types.get(iid), hint)


# ── main entry point ───────────────────────────────────────────────────────

def validate_function(design: EngineeringDesignProject, intent: Optional[FunctionalIntent],
                      registry: Optional[ComponentRegistry] = None) -> FunctionalReport:
    registry = registry or get_shared_registry()
    g = build_graph(design, registry)
    ctx = _Ctx(design, registry, g)
    findings: List[FunctionalFinding] = []
    involved: set = set()
    behaviors: List[BehaviorResult] = []
    bindings: Dict[str, List[str]] = {}

    findings.extend(_never_activated_loads(ctx))
    inferred = _infer(ctx)
    for inf in inferred:
        involved.update([inf.input_instance, inf.output_instance, *inf.via])

    if intent is None or not intent.behaviors:
        if inferred:          # only meaningful when the circuit has some functional path to compare with
            _unused_parts(ctx, involved, findings, intent_present=False)
        return FunctionalReport(
            status="NOT_CHECKABLE", intent_present=False,
            summary="No functional intent recorded for this design; showing the behaviour inferred from the circuit.",
            findings=findings, inferred=inferred, involved_instances=sorted(involved),
            explanation=[i.statement for i in inferred])

    intent, notes = normalize_intent(intent)
    intent_notes = [n for n in notes if "interpreted as" in n]      # recovered, still checkable
    for n in notes:
        if n not in intent_notes:
            findings.append(FunctionalFinding(code="F106", status="NOT_CHECKABLE", message=f"Intent: {n}"))

    for s in intent.signals:
        bound = _bind(ctx, s.quantity, s.role, s.component_hint)
        bindings[s.id] = bound
        if not bound:
            unknown = [i for i, p in g.profiles.items() if p.derived and p.kind in ("unknown", "sensor")]
            if unknown:
                findings.append(FunctionalFinding(
                    code="F104", status="NOT_CHECKABLE", signal_id=s.id, affected_instances=unknown,
                    message=f"No modelled part provides '{s.quantity}' for {s.role} '{s.id}'; "
                            f"{', '.join(unknown)} may, but its function is not modelled."))
            else:
                findings.append(FunctionalFinding(
                    code="F001" if s.role == "input" else "F002", status="FAIL", signal_id=s.id,
                    message=f"The requested {s.role} '{s.id}' ({s.quantity}) is not implemented: no part in the design "
                            f"{'senses' if s.role == 'input' else 'produces'} {s.quantity}.",
                    repair_hint=f"Add a registry part whose function is {s.quantity}"
                                + (f" (the user asked for {s.component_hint})" if s.component_hint else "") + "."))

    for b in intent.behaviors:
        res = _check_behavior(ctx, intent, b, bindings, findings)
        behaviors.append(res)
        involved.update(res.input_instances + res.output_instances + [st.instance for st in res.path])
        if res.threshold_set_by:
            involved.add(res.threshold_set_by)

    involved |= ctx.partial
    _requested_parts(ctx, intent, involved, findings)
    _unused_parts(ctx, involved, findings, intent_present=True)

    unique: List[FunctionalFinding] = []
    seen_keys = set()
    for f in findings:                      # two behaviours on one path can raise the same defect
        key = (f.code, f.message)
        if key not in seen_keys:
            seen_keys.add(key)
            unique.append(f)
    findings = unique
    # A load that can never turn on (F011) also "responds the wrong way" along every path; reporting
    # F006 as well would point a repair at the sensing side, which is not what is broken.
    dead = {i for f in findings if f.code == "F011" for i in f.affected_instances}
    if dead:
        findings = [f for f in findings if not (f.code == "F006" and set(f.affected_instances) & dead)]
        for b in behaviors:
            still_failing = any(f.behavior_id == b.behavior_id and f.status == "FAIL" for f in findings)
            if b.status == "FAIL" and set(b.output_instances) & dead and not still_failing:
                b.explanation = [ln for ln in b.explanation if not ln.startswith("Behaviour:")]
                b.explanation.append(f"Behaviour: {', '.join(sorted(set(b.output_instances) & dead))} is wired "
                                     f"backwards and can never turn on (F011); the direction cannot be judged until "
                                     f"that is fixed.")
    statuses = [f.status for f in findings] + [b.status for b in behaviors]
    status: Status = max(statuses, key=lambda s: _RANK[s]) if statuses else "PASS"
    fails = [f for f in findings if f.status == "FAIL"]
    summary = (f"Functional validation {status}: {len(behaviors)} behaviour(s) checked"
               + (f", {len(fails)} functional defect(s)" if fails else ""))
    explanation = [line for b in behaviors for line in b.explanation]
    return FunctionalReport(status=status, intent_present=True, summary=summary, behaviors=behaviors,
                            findings=findings, bindings=bindings, inferred=inferred,
                            involved_instances=sorted(involved), explanation=explanation,
                            intent_notes=intent_notes)


def _check_behavior(ctx: _Ctx, intent: FunctionalIntent, b, bindings, findings: List[FunctionalFinding]) -> BehaviorResult:
    g = ctx.g
    autonomous = b.when.input is None
    outs = bindings.get(b.then.output, [])
    if autonomous:
        # No input: the output must be driven by an oscillator or firmware (generator node).
        order = {"timer": 0, "controller": 1}
        ins = sorted((n.split(":", 1)[1] for n in g.generators), key=lambda i: (order.get(g.generators[f"g:{i}"], 2), i))
    else:
        ins = bindings.get(b.when.input, [])
    in_sig, out_sig = (intent.signal(b.when.input) if not autonomous else None), intent.signal(b.then.output)
    desc = b.description or (f"{b.then.output} {b.then.effect} when {b.when.input} {b.when.relation}")
    res = BehaviorResult(behavior_id=b.id, description=desc, status="PASS", input_instances=ins, output_instances=outs)
    r, e = REL_SIGN.get(b.when.relation), EFFECT_SIGN.get(b.then.effect)
    res.required_sign = r * e if (r is not None and e is not None) else None
    if autonomous and not ins and outs:
        findings.append(FunctionalFinding(
            code="F003", status="FAIL", behavior_id=b.id, affected_instances=outs,
            message=f"'{desc}' needs something that drives {outs[0]} on its own (oscillator, timer or microcontroller), "
                    f"but the design has none.", patterns=["astable_555"],
            repair_hint="Add an oscillator (e.g. 555 astable) or a microcontroller output to drive it."))
        res.status = "FAIL"
        return res
    if not ins or not outs:
        res.status = "FAIL" if any(f.code in ("F001", "F002") for f in findings) else "NOT_CHECKABLE"
        res.explanation.append(f"Behaviour '{desc}' cannot be evaluated: "
                               f"{'input' if not ins else 'output'} not implemented.")
        return res

    # Output must be controllable at all.
    for y in outs:
        if f"a:{y}" not in g.reverse:
            st = g.static_loads.get(y)
            state = st.state if st else "unconnected"
            text = {"always_on": "is permanently powered - nothing in the circuit switches it",
                    "never_on": "can never be powered in this wiring",
                    "unconnected": "is not connected to anything that could drive it"}[state]
            findings.append(FunctionalFinding(
                code="F004", status="FAIL", behavior_id=b.id, signal_id=b.then.output, affected_instances=[y],
                affected_pins=[f"{y}.{p}" for pair in g.profiles[y].loads for p in pair] or [f"{y}.{p}" for p in g.profiles[y].controls],
                patterns=PATTERN_HINTS["F004"],
                message=f"Output {ctx.name(y)} {text}.",
                repair_hint=f"Put {y} in the controlled path: e.g. one terminal to the supply rail and the other to the "
                            f"switched terminal (collector/drain) of a transistor whose control input comes from the decision stage."))
    candidates: List[Tuple[int, str, str, List[Edge]]] = []
    src_prefix = "g" if autonomous else "q"
    for x in ins:
        for y in outs:
            for p in find_paths(g, f"{src_prefix}:{x}", f"a:{y}"):
                candidates.append((0, x, y, p))
    if not candidates:
        res.status = "FAIL"
        x, y = ins[0], outs[0]
        reach = reachable(g, f"{src_prefix}:{x}")
        reached = sorted({e.instance for n in reach for e in g.edges.get(n, [])
                          if g.profiles.get(e.instance) and g.profiles[e.instance].kind not in ("passive",) and e.instance != x})
        controllers = sorted({e.instance for n in reachable(g, f"a:{y}", reverse=True) for e in g.reverse.get(n, [])
                              if e.instance != y and g.profiles.get(e.instance) and g.profiles[e.instance].kind not in ("passive",)})
        last = reached[-1] if reached else None
        ctx.partial.update(reached + controllers + [x, y])
        for adj in (n.split(":", 1)[1] for n in g.sources if g.profiles[n.split(":", 1)[1]].kind == "adjustable"):
            if reachable(g, f"q:{adj}") & reachable(g, f"{src_prefix}:{x}"):
                ctx.partial.add(adj)
        msg = (f"Unable to establish a control path from {ctx.name(x)} to {ctx.name(y)}. "
               + (f"The {in_sig.quantity if in_sig else 'input'} signal reaches {', '.join(reached)}" if reached else f"{x}'s signal reaches no other part")
               + (f"; {y} is influenced only by {', '.join(controllers)}." if controllers else f"; nothing drives {y}."))
        if not any(f.code == "F004" and f.behavior_id == b.id for f in findings):
            findings.append(FunctionalFinding(
                code="F003", status="FAIL", behavior_id=b.id, affected_instances=[x, y] + reached[:4],
                patterns=PATTERN_HINTS["F003"], message=msg,
                repair_hint=f"Connect the output of the last stage that the input reaches ({last or x}) to the control of {y} "
                            f"(directly for small loads, or through a transistor switch)."))
        res.explanation.append(msg)
        return res

    # Score candidate paths: correct polarity first, explicit decision, then shortest.
    scored = []
    for _, x, y, p in candidates:
        sign, basis = path_polarity(ctx.design, p, y)
        dec, dkind = _decision(ctx, p)
        good = 0 if (res.required_sign is None or sign == res.required_sign) else (1 if sign is None else 2)
        scored.append(((good, {"explicit": 0, "programmable": 0, "implicit": 1, None: 2}[dkind], len(p)), x, y, p, sign, basis, dec, dkind))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    _, x, y, path, sign, basis, dec, dkind = scored[0]
    res.input_instances, res.output_instances = [x], [y]
    res.path = [PathStep(instance=e.instance, kind=e.kind, from_node=e.src, to_node=e.dst, sign=e.sign, pins=list(e.pins)) for e in path]
    res.path_sign, res.polarity_basis = sign, basis
    res.decision_instance, res.decision_kind = dec, dkind
    nets = sorted({n.split(":", 1)[1] for e in path for n in (e.src, e.dst) if n.startswith("net:")})
    status: Status = "PASS"

    same = [t for t in scored if t[1] == x and t[2] == y and t[4] is not None]
    nonzero = sorted({t[4] for t in same})
    if len(nonzero) > 1:
        out_pins = {t[4]: sorted({pin for e in t[3][:1] for pin in e.pins}) for t in same}
        prog = [t[6] for t in same if t[7] == "programmable"]
        if prog and all(out_pins.get(sg) for sg in nonzero):
            rising, falling = ", ".join(out_pins.get(1, [])), ", ".join(out_pins.get(-1, []))
            msg = (f"{ctx.name(x)} reaches {prog[0]} through {rising} (rises with the input) and {falling} (falls with it); "
                   f"the logic rule names the part, not the pin, so the direction depends on which pin the firmware reads.")
            hint = f"Wire only the {x} output the rule is written for, or write the rule for that output's polarity."
        else:
            msg = f"Different paths from {x} to {y} act in opposite directions; the net behaviour depends on analog levels."
            hint = None
        findings.append(FunctionalFinding(code="F105", status="WARN", behavior_id=b.id, affected_instances=[x, y],
                                          message=msg, repair_hint=hint))
        status = "WARN"

    if b.when.relation in THRESHOLD_RELATIONS:
        if dec is None:
            findings.append(FunctionalFinding(
                code="F005", status="FAIL", behavior_id=b.id, affected_instances=[x, y], affected_nets=nets,
                patterns=PATTERN_HINTS["F005"],
                message=f"'{desc}' needs a threshold decision, but the path from {x} to {y} has no comparator, "
                        f"microcontroller, logic gate or switching stage - the output would just follow the input.",
                repair_hint="Insert a comparator (sensor on one input, reference divider/potentiometer on the other) "
                            "or route the signal through a microcontroller with a logic rule."))
            status = "FAIL"
        elif dkind == "implicit":
            findings.append(FunctionalFinding(
                code="F102", status="WARN", behavior_id=b.id, affected_instances=[dec],
                message=f"The threshold is set implicitly by {ctx.name(dec)}'s turn-on voltage, not by a comparator or firmware; "
                        f"it will be imprecise and vary with temperature."))
            status = max([status, "WARN"], key=lambda s: _RANK[s])

    if res.required_sign is not None:
        if sign is None:
            findings.append(FunctionalFinding(
                code="F101", status="NOT_CHECKABLE", behavior_id=b.id, affected_instances=[x, y],
                message=f"A path from {x} to {y} exists, but its direction cannot be verified: {basis}.",
                repair_hint=("Add a logic rule to the design stating the firmware behaviour "
                             f"(condition on {x}, action on {y})." if "programmable" in basis or "logic rule" in basis else "")))
            status = max([status, "NOT_CHECKABLE"], key=lambda s: _RANK[s])
        elif sign != res.required_sign:
            opposite = {"above": "below", "below": "above", "present": "absent", "absent": "present",
                        "pressed": "released", "released": "pressed", "proportional": "inverse", "inverse": "proportional"}
            q = in_sig.quantity if in_sig else "input"
            findings.append(FunctionalFinding(
                code="F006", status="FAIL", behavior_id=b.id, affected_instances=[x, y] + ([dec] if dec else []),
                affected_nets=nets,
                message=f"Behaviour is inverted: required '{y} {b.then.effect.upper()} when {q} is {b.when.relation}', "
                        f"but the circuit turns {y} {b.then.effect.upper()} when {q} is "
                        f"{opposite.get(b.when.relation, 'the opposite')} (derived from {basis}).",
                repair_hint=(f"Swap {dec}'s inputs (sensor to the other comparator input) " if dec and ctx.g.profiles[dec].kind in ("comparator", "amplifier")
                             else "Invert the decision (e.g. swap comparator inputs, move the sensor to the other side of its divider, or invert the logic rule) ")
                            + "and re-validate."))
            status = "FAIL"

    # Adjustable threshold.
    thr = b.when.threshold
    if thr is not None and thr.kind == "adjustable" and b.when.relation in THRESHOLD_RELATIONS:
        setter = None
        adjusters = [n.split(":", 1)[1] for n in g.sources if ctx.g.profiles[n.split(":", 1)[1]].kind == "adjustable"]
        if dec:
            dec_inputs = set()
            prof = ctx.g.profiles[dec]
            if prof.programmable:
                dec_inputs = {g.node(g.net_of.get((dec, p.pin_id))) for p in (ctx.types[dec].pins if ctx.types[dec] else [])}
            else:
                dec_inputs = {g.node(g.net_of.get((dec, t[0]))) for t in prof.transfers}
            path_nodes = {e.dst for e in path}
            for adj in adjusters:
                reach = reachable(g, f"q:{adj}")
                if (dec_inputs - path_nodes - {None}) & reach or (prof.programmable and dec_inputs & reach):
                    setter = adj
                    break
        res.threshold_set_by = setter
        if setter is None:
            findings.append(FunctionalFinding(
                code="F007", status="FAIL", behavior_id=b.id, affected_instances=[dec] if dec else [x],
                patterns=PATTERN_HINTS["F007"],
                message=f"An adjustable threshold was requested, but no adjustable part (e.g. potentiometer) sets the "
                        f"reference of the decision stage{f' {dec}' if dec else ''}.",
                repair_hint=f"Connect a potentiometer wiper to {dec + chr(39) + 's other input' if dec else 'the reference input'} "
                            f"(ends to the supply and ground)."))
            status = "FAIL"

    # Driver requirement.
    ct_y = ctx.types.get(y)
    drv = _driver(ctx, path, dec)
    if drv is None and dec and ctx.g.profiles[dec].kind in ("switch", "driver"):
        drv = dec                 # a transistor that makes the decision also drives the load
    res.driver_instance = drv
    if ct_y is not None and ct_y.requires_driver and drv is None:
        src = dec or x
        findings.append(FunctionalFinding(
            code="F008", status="FAIL", behavior_id=b.id, affected_instances=[y, src], patterns=PATTERN_HINTS["F008"],
            message=f"{ctx.name(y)} needs a driver stage (transistor/MOSFET/driver IC) but is driven directly by {ctx.name(src)}.",
            repair_hint=f"Insert a transistor or MOSFET low-side switch between {src} and {y} (pattern mosfet_low_side_switch)."))
        status = "FAIL"

    drive = _drive_check(ctx, path, y)
    if drive is not None:
        drive.behavior_id = b.id
        findings.append(drive)
        status = "FAIL"

    res.status = max([status] + [f.status for f in findings if f.behavior_id == b.id], key=lambda s: _RANK[s])
    res.explanation = _explain(ctx, b, res, in_sig, out_sig)
    return res


def _rail_tie(ctx: _Ctx, net: Optional[str], seen: Optional[set] = None) -> Optional[str]:
    """If `net` is held at a rail only through series passives (no active pin on the way),
    return that rail net; otherwise None."""
    g = ctx.g
    if net is None:
        return None
    if g.is_rail(net):
        return net
    seen = seen or set()
    seen.add(net)
    members = [(i, p) for (i, p), n in g.net_of.items() if n == net]
    passives = []
    for iid, pin in members:
        kind = g.profiles[iid].kind
        if kind == "passive" and (ctx.types.get(iid) and (ctx.types[iid].family or "") != "capacitor"):
            passives.append((iid, pin))
        elif kind not in ("actuator", "display"):
            return None                     # an active pin can move this net
    for iid, pin in passives:
        for (i2, p2), n2 in g.net_of.items():
            if i2 == iid and p2 != pin and n2 not in seen:
                tie = _rail_tie(ctx, n2, seen)
                if tie is not None:
                    return tie
    return None


def _never_activated_loads(ctx: _Ctx) -> List[FunctionalFinding]:
    """F011: polarised load (LED, buzzer...) whose negative side is tied to the highest supply,
    or whose positive side is tied to ground: it can never be forward-biased."""
    g = ctx.g
    out = []
    supplies = [v for n, v in g.net_voltage.items() if g.net_class.get(n) == "power" and v is not None]
    top = max(supplies) if supplies else None
    for iid, prof in g.profiles.items():
        if not prof.polarized or not prof.loads:
            continue
        for pos, neg in prof.loads:
            pn, nn = g.net_of.get((iid, pos)), g.net_of.get((iid, neg))
            if pn is None or nn is None:
                continue
            neg_tie, pos_tie = _rail_tie(ctx, nn), _rail_tie(ctx, pn)
            reason = None
            if neg_tie and g.net_class.get(neg_tie) == "power" and top is not None and \
                    g.net_voltage.get(neg_tie) == top and not (pos_tie and g.net_class.get(pos_tie) == "power"):
                reason = (f"its negative terminal {neg} is held at the highest supply ({neg_tie}) through passives, "
                          f"so {pos} can never be driven above it")
            elif pos_tie and g.net_class.get(pos_tie) == "ground" and not (neg_tie and g.net_class.get(neg_tie) == "ground"):
                reason = f"its positive terminal {pos} is held at ground ({pos_tie}) through passives, so it can never be above {neg}"
            if reason:
                out.append(FunctionalFinding(
                    code="F011", status="FAIL", affected_instances=[iid], affected_pins=[f"{iid}.{pos}", f"{iid}.{neg}"],
                    affected_nets=[pn, nn],
                    message=f"{ctx.name(iid)} can never turn on: {reason} (it is wired backwards).",
                    repair_hint=f"Swap {iid}'s terminals: {pos} towards the supply side, {neg} towards the switched/ground side."))
    return out


def _drive_check(ctx: _Ctx, path: List[Edge], y: str) -> Optional[FunctionalFinding]:
    """F010: a load that must be pulled HIGH by an open-collector/open-drain output only gets the
    pull-up resistor's current. Compare that with the load's minimum useful drive current."""
    from core.units import parse_quantity
    g = ctx.g
    if not path or path[-1].kind != "load":
        return None
    sign = path[-1].sign
    i = len(path) - 2
    while i >= 0 and path[i].kind == "passive":
        sign *= path[i].sign
        i -= 1
    if i < 0 or sign != 1:
        return None                      # load is activated by pulling low (sinking) - fine for open collector
    driver = path[i]
    prof = g.profiles.get(driver.instance)
    out_pin = driver.pins[-1] if driver.pins else None
    if prof is None or out_pin not in prof.open_collector_outputs:
        return None
    driven_net = driver.dst.split(":", 1)[1]
    need = g.profiles[y].min_drive_ma
    current_ma = 0.0
    pullups = []
    for comp in ctx.design.components:
        ct = ctx.types.get(comp.instance_id)
        if ct is None or (ct.family or "") != "resistor":
            continue
        nets = [g.net_of.get((comp.instance_id, p.pin_id)) for p in ct.pins]
        if driven_net in nets:
            other = [n for n in nets if n != driven_net]
            if other and g.net_class.get(other[0]) == "power":
                r = parse_quantity(comp.parameters.get("resistance"), "ohm")
                v = g.net_voltage.get(other[0])
                if r and v:
                    current_ma += 1000.0 * v / r
                    pullups.append(f"{comp.instance_id} ({comp.parameters.get('resistance')}Ω)")
    ref = ctx.name(driver.instance)
    if prof.kind == "switch":           # discrete transistor: the load belongs between supply and collector/drain
        if pullups and (need is None or current_ma >= need):
            return None
        return FunctionalFinding(
            code="F010", status="FAIL", affected_instances=[driver.instance, y], affected_nets=[driven_net],
            patterns=["bjt_low_side_switch", "mosfet_low_side_switch"],
            message=f"{ctx.name(y)} sits between {ref}'s {out_pin} and ground, but {out_pin} can only sink current, "
                    f"so nothing ever pushes current through {y} - it can never turn on.",
            repair_hint=f"Low-side switch: connect {y} between the supply and {ref}.{out_pin} (its emitter/source to "
                        f"ground), so turning {ref} on pulls current through {y}.")
    if not pullups:
        return FunctionalFinding(
            code="F010", status="FAIL", affected_instances=[driver.instance, y], affected_nets=[driven_net],
            patterns=["bjt_low_side_switch", "mosfet_low_side_switch"],
            message=f"{ctx.name(y)} needs {driven_net} pulled high, but {ref} output {out_pin} is open-collector "
                    f"(it can only sink current) and nothing pulls the net up - the load can never turn on.",
            repair_hint=f"Let {ref} drive a transistor switch (base/gate through a resistor, pull-up on the comparator "
                        f"output) and put {y} in the transistor's collector/drain path.")
    if need is not None and current_ma < need:
        return FunctionalFinding(
            code="F010", status="FAIL", affected_instances=[driver.instance, y], affected_nets=[driven_net],
            patterns=["bjt_low_side_switch", "mosfet_low_side_switch"],
            message=f"{ctx.name(y)} is powered only through the pull-up {', '.join(pullups)} of {ref}'s open-collector "
                    f"output {out_pin}: about {current_ma:.1f} mA available, but it needs at least ~{need:g} mA "
                    f"({g.profiles[y].min_drive_basis}).",
            repair_hint=f"Drive {y} with a transistor: {ref} output → base resistor → NPN/MOSFET, {y} between the supply "
                        f"and the collector/drain (keep the pull-up on {out_pin}).")
    return None


def _explain(ctx: _Ctx, b, res: BehaviorResult, in_sig, out_sig) -> List[str]:
    x, y = res.input_instances[0], res.output_instances[0]
    if b.when.input is None:
        how = "oscillates on its own" if ctx.g.profiles[x].kind == "timer" else "drives it from firmware"
        return [f"{ctx.name(x)} {how}.",
                f"{ctx.name(y)} is controlled through: {' → '.join(dict.fromkeys(s.instance for s in res.path))}."]
    lines = [f"{(in_sig.quantity if in_sig else 'Input').replace('_', ' ').capitalize()} sensing is implemented by {ctx.name(x)}."]
    if res.threshold_set_by:
        lines.append(f"The threshold is set by {ctx.name(res.threshold_set_by)}.")
    if res.decision_instance:
        kind = ctx.g.profiles[res.decision_instance].kind
        verb = {"comparator": "compares the sensor signal with the reference",
                "amplifier": "compares/amplifies the sensor signal",
                "controller": "evaluates the signal in firmware" + (f" ({res.polarity_basis})" if "logic rule" in res.polarity_basis else ""),
                "timer": "switches its output when its trigger/threshold inputs cross 1/3·2/3 VCC",
                "switch": "switches when its control voltage crosses its turn-on threshold",
                "logic": "switches at its logic input threshold"}.get(kind, "makes the decision")
        lines.append(f"{ctx.name(res.decision_instance)} {verb}.")
    if res.driver_instance:
        lines.append(f"{ctx.name(res.driver_instance)} drives {y}.")
    lines.append(f"{ctx.name(y)} is controlled through: {' → '.join(dict.fromkeys(s.instance for s in res.path))}.")
    if res.required_sign is not None and res.path_sign is not None:
        rel = b.when.relation
        ok = res.path_sign == res.required_sign
        opposite = {"above": "below", "below": "above", "present": "absent", "absent": "present", "pressed": "released",
                    "released": "pressed", "proportional": "inverse", "inverse": "proportional"}
        actual = rel if ok else opposite.get(rel, rel)
        cond = (f"{x}'s {in_sig.quantity if in_sig else 'input'} is {actual} the threshold" if rel in THRESHOLD_RELATIONS
                else f"{x} reports '{actual}'")
        lines.append(f"Behaviour: {y} turns {b.then.effect.upper()} when {cond} - "
                     f"{'as requested' if ok else 'NOT as requested'} (from {res.polarity_basis}).")
    elif res.required_sign is not None:
        lines.append(f"Direction not verifiable: {res.polarity_basis}.")
    return lines


def _infer(ctx: _Ctx) -> List[InferredBehavior]:
    """Behaviour the circuit implements regardless of intent: every input part → output part path."""
    out = []
    covered = set()
    for q in sorted(ctx.g.sources):
        x = q.split(":", 1)[1]
        for a in sorted(ctx.g.sinks):
            y = a.split(":", 1)[1]
            if x == y:
                continue
            paths = find_paths(ctx.g, q, a, max_paths=40)
            if not paths:
                continue
            best = min(paths, key=len)
            sign, basis = path_polarity(ctx.design, best, y)
            via = list(dict.fromkeys(e.instance for e in best if e.instance not in (x, y)))
            qty = (ctx.g.sources[q] or ["input"])[0].replace("_", " ")
            direction = {1: f"rises with {qty}", -1: f"falls as {qty} rises", None: f"depends on {qty} ({basis})"}[sign]
            covered.add(y)
            out.append(InferredBehavior(input_instance=x, output_instance=y, sign=sign, via=via,
                                        statement=f"{ctx.name(y)} activation {direction} at {ctx.name(x)}"
                                                  + (f", via {', '.join(via)}" if via else "") + "."))
    for gnode in sorted(ctx.g.generators):
        x = gnode.split(":", 1)[1]
        for a in sorted(ctx.g.sinks):
            y = a.split(":", 1)[1]
            if y in covered or x == y:
                continue
            paths = find_paths(ctx.g, gnode, a, max_paths=40)
            if not paths:
                continue
            via = list(dict.fromkeys(e.instance for e in min(paths, key=len) if e.instance not in (x, y)))
            how = "oscillation" if ctx.g.generators[gnode] == "timer" else "firmware"
            out.append(InferredBehavior(input_instance=x, output_instance=y, sign=None, via=via,
                                        statement=f"{ctx.name(y)} is driven by {ctx.name(x)} ({how})"
                                                  + (f", via {', '.join(via)}" if via else "") + "."))
    return out


def _requested_parts(ctx: _Ctx, intent: FunctionalIntent, involved: set, findings: List[FunctionalFinding]) -> None:
    wanted = list(intent.required_components) + [s.component_hint for s in intent.signals if s.component_hint]
    for hint in dict.fromkeys(w for w in wanted if w):
        matches = [i for i in ctx.types if _matches(ctx, i, hint)]
        if not matches:
            in_library = [t.component_type_id for t in ctx.registry.list_all() if _type_matches(t, hint)]
            if in_library:
                findings.append(FunctionalFinding(
                    code="F009", status="FAIL", message=f"The requested part '{hint}' is not in the design.",
                    repair_hint=f"Use {' or '.join(in_library[:3])} for '{hint}' in the functional path."))
            else:   # a design cannot satisfy it; blocking would only exhaust the repair budget
                findings.append(FunctionalFinding(
                    code="F009", status="WARN",
                    message=f"The requested part '{hint}' does not match any library part by name, so its use cannot be confirmed.",
                    repair_hint="Check that a library part serving this role is in the design, or name the part differently."))
            continue
        powerish = all(ctx.g.profiles[m].kind == "power" for m in matches)
        if not powerish and not (set(matches) & involved):
            findings.append(FunctionalFinding(
                code="F009", status="FAIL", affected_instances=matches,
                message=f"The requested part '{hint}' ({', '.join(matches)}) is present but not part of any functional path.",
                repair_hint=f"Wire {matches[0]} into the behaviour it was requested for."))


def _unused_parts(ctx: _Ctx, involved: set, findings: List[FunctionalFinding], intent_present: bool) -> None:
    path_nets = set()
    for iid in involved:
        for (i, _p), n in ctx.g.net_of.items():
            if i == iid and not ctx.g.is_rail(n):
                path_nets.add(n)
    for comp in ctx.design.components:
        iid = comp.instance_id
        prof = ctx.g.profiles[iid]
        if iid in involved or prof.kind in ("power",):
            continue
        nets = [n for (i, _p), n in ctx.g.net_of.items() if i == iid]
        signal_nets = [n for n in nets if not ctx.g.is_rail(n)]
        if not signal_nets:
            if prof.kind in ("passive",):
                continue          # decoupling / bias parts between rails
            if prof.kind in ("actuator", "display") and ctx.g.static_loads.get(iid, None) and ctx.g.static_loads[iid].state == "always_on":
                if intent_present:
                    continue      # reported by F004 when an intended output
                findings.append(FunctionalFinding(code="F103", status="WARN", affected_instances=[iid],
                                                  message=f"{ctx.name(iid)} is permanently powered (e.g. a power indicator)."))
                continue
        if set(signal_nets) & path_nets:
            continue              # support part on a functional net (pull-up, base resistor, flyback diode...)
        findings.append(FunctionalFinding(
            code="F103", status="WARN", affected_instances=[iid],
            message=f"{ctx.name(iid)} does not take part in any functional path"
                    + (" of the requested behaviour." if intent_present else ".")))
