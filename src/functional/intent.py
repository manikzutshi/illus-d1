"""Functional intent: what the user asked the circuit to *do*.

Extracted (by AI, from the natural-language request) *before* any design exists, so the
design step cannot redefine what it is graded against. Verified only by the deterministic
functional validator (functional/validator.py).

    signals    : named functional inputs/outputs with a quantity from a controlled vocabulary
    behaviors  : WHEN <input relation threshold> THEN <output effect>
    processing : optional architecture constraint (any / analog / microcontroller / logic)
    required_components : parts the user named explicitly
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field

_VOCAB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "functional_vocabulary.yaml"

Relation = Literal["above", "below", "present", "absent", "pressed", "released", "proportional", "inverse", "changes", "any",
                   "periodic", "always"]
Effect = Literal["on", "off", "proportional", "inverse", "display", "toggle", "pulse"]


class Threshold(BaseModel):
    kind: Literal["fixed", "adjustable", "unspecified"] = Field(
        "unspecified", description="'adjustable' when the user wants to set the threshold (knob/trimmer); 'fixed' when a value is given")
    value: Optional[str] = Field(None, description="Numeric threshold if the user gave one, e.g. '30 degC'")


class IntentSignal(BaseModel):
    id: str = Field(..., description="Short id, e.g. 'temp', 'alarm'")
    role: Literal["input", "output"]
    quantity: str = Field(..., description="Controlled vocabulary: temperature, light, motion, distance, humidity, gas, "
                                           "acceleration, rotation, press, setting, logic, signal (inputs); light_emission, "
                                           "sound_emission, motion_output, display, switching, logic, signal (outputs)")
    description: str = ""
    component_hint: Optional[str] = Field(None, description="Part the user named for this signal, e.g. 'LM35'")


class Condition(BaseModel):
    input: Optional[str] = Field(None, description="IntentSignal id of an input; omit for autonomous behaviour (blinking, firmware-timed)")
    relation: Relation = Field(..., description="above/below a threshold, present/absent, pressed/released, proportional, "
                                                "inverse, changes; periodic/always for autonomous behaviour without an input")
    threshold: Optional[Threshold] = None


class Action(BaseModel):
    output: str = Field(..., description="IntentSignal id of an output")
    effect: Effect = Field(..., description="on, off, proportional, inverse, display, toggle, pulse")


class Behavior(BaseModel):
    id: str
    when: Condition
    then: Action
    description: str = ""


class FunctionalIntent(BaseModel):
    signals: List[IntentSignal] = Field(default_factory=list)
    behaviors: List[Behavior] = Field(default_factory=list)
    processing: Literal["any", "analog", "microcontroller", "logic"] = "any"
    required_components: List[str] = Field(default_factory=list, description="Parts the user explicitly asked for")
    notes: List[str] = Field(default_factory=list)

    def signal(self, sid: str) -> Optional[IntentSignal]:
        return next((s for s in self.signals if s.id == sid), None)


# ── controlled vocabulary ──────────────────────────────────────────────────

_VOCAB: Optional[Dict[str, Dict[str, List[str]]]] = None


def vocabulary() -> Dict[str, Dict[str, List[str]]]:
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = yaml.safe_load(_VOCAB_PATH.read_text(encoding="utf-8"))
    return _VOCAB


def canonical_quantity(text: str, role: str) -> Optional[str]:
    """Map free text ('heat', 'darkness', 'beeper') to a canonical quantity, or None."""
    t = re.sub(r"[^a-z0-9 _]+", " ", (text or "").lower()).strip()
    table = vocabulary()["inputs" if role == "input" else "outputs"]
    if t.replace(" ", "_") in table:
        return t.replace(" ", "_")
    for canon, synonyms in table.items():
        if t == canon or t in synonyms:
            return canon
    words = set(t.replace("_", " ").split())
    for canon, synonyms in table.items():
        if canon in words or any(s in words for s in synonyms if " " not in s):
            return canon
    return None


def normalize_intent(intent: FunctionalIntent) -> tuple[FunctionalIntent, List[str]]:
    """Canonicalise quantities; return (intent, notes about anything that could not be mapped)."""
    out = intent.model_copy(deep=True)
    notes: List[str] = []
    for s in out.signals:
        canon = canonical_quantity(s.quantity, s.role) or canonical_quantity(s.description, s.role)
        if canon is None:
            notes.append(f"signal '{s.id}': quantity '{s.quantity}' is outside the functional vocabulary")
        else:
            s.quantity = canon
    ids = {s.id for s in out.signals}
    # Behaviours sometimes reference signals that were never declared ("light_sensor", "led").
    # When the id itself is vocabulary, declare the signal deterministically and say so.
    for b in out.behaviors:
        for sid, role in ((b.when.input, "input"), (b.then.output, "output")):
            if sid is None or sid in ids:
                continue
            canon = canonical_quantity(sid.replace("_", " "), role)
            if canon is not None:
                out.signals.append(IntentSignal(id=sid, role=role, quantity=canon,
                                                description="declared from the behaviour reference"))
                ids.add(sid)
                notes.append(f"signal '{sid}' was not declared; interpreted as {role} '{canon}' from its name")
    for b in out.behaviors:
        if b.when.input is not None and b.when.input not in ids:
            notes.append(f"behavior '{b.id}' refers to unknown input '{b.when.input}'")
        if b.then.output not in ids:
            notes.append(f"behavior '{b.id}' refers to unknown output '{b.then.output}'")
    return out, notes
