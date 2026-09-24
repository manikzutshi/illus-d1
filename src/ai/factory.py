"""Single place that maps a provider name + model to a ModelProvider instance.

Keeps the rest of the application provider-neutral: callers say "gemini"/"openai" and never
import vendor code. API keys are read from the environment by the providers themselves and
are never returned, logged or echoed.
"""
from __future__ import annotations

import os
from typing import Optional

from .provider import ModelProvider

DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "openai": "gpt-4o-mini",
}
# Tried in order when the requested Gemini model is overloaded (HTTP 503) or retired (HTTP 404).
GEMINI_FALLBACKS = ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash"]
KEY_ENV = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}


def infer_provider(model: str) -> str:
    return "gemini" if "gemini" in model.lower() or "gemma" in model.lower() else "openai"


def available_providers() -> list[dict]:
    """Which providers are configured (booleans only - key values are never exposed)."""
    return [{"name": name, "configured": bool(os.environ.get(env)), "default_model": DEFAULT_MODELS[name]}
            for name, env in KEY_ENV.items()]


def create_provider(provider: Optional[str] = None, model: Optional[str] = None) -> ModelProvider:
    name = (provider or (infer_provider(model) if model else "gemini")).lower()
    model = model or DEFAULT_MODELS.get(name)
    if name == "gemini":
        from .provider_gemini import RESTGeminiProvider
        return RESTGeminiProvider(model_name=model, fallback_models=list(GEMINI_FALLBACKS))
    if name == "openai":
        from .provider_openai import RESTOpenAIProvider
        return RESTOpenAIProvider(model_name=model)
    raise ValueError(f"Unknown provider '{provider}'. Known: {sorted(KEY_ENV)}")
