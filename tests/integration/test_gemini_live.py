"""Opt-in live test of the full pipeline with the real Gemini provider.

Runs only when GEMINI_API_KEY is set AND ILLUS_LIVE_TESTS=1, so ordinary test runs never
spend API quota. The key is read by the provider from the environment and never printed.

    set ILLUS_LIVE_TESTS=1 && pytest tests/integration/test_gemini_live.py -s
"""
import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") and os.environ.get("ILLUS_LIVE_TESTS") == "1"),
    reason="live Gemini tests are opt-in (GEMINI_API_KEY and ILLUS_LIVE_TESTS=1)",
)


def test_provider_roundtrip():
    from ai.factory import create_provider
    out = create_provider("gemini").generate([{"role": "user", "content": "Reply with the single word OK."}])
    assert "ok" in out.lower()


def test_prompt_to_validated_schematic():
    from studio import StudioService
    svc = StudioService()
    job = svc.start_generation("A 9 V battery powered circuit that lights an LED when a push button is pressed.", "gemini")
    deadline = time.time() + 900
    while job.status == "running" and time.time() < deadline:
        time.sleep(1)
    if job.status == "failed" and job.error and ("503" in job.error or "429" in job.error or "timed out" in job.error):
        pytest.skip(f"provider unavailable: {job.error[:120]}")
    assert job.status == "done", job.error or job.clarification
    state = job.result
    assert state.validation.status.value == "PASS"
    assert state.verification["ok"]
    assert state.schematic.components
