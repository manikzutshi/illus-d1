"""Functional / behavioural-intent layer: intent model, component functional profiles,
signal-flow graph and the deterministic functional validator."""
from .intent import Action, Behavior, Condition, FunctionalIntent, IntentSignal, Threshold, normalize_intent
from .validator import FunctionalReport, validate_function

__all__ = ["Action", "Behavior", "Condition", "FunctionalIntent", "IntentSignal", "Threshold", "normalize_intent",
           "FunctionalReport", "validate_function"]
