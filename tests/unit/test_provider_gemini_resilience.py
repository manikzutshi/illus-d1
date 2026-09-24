"""Gemini provider resilience: model fallback on overload, retired models, rate-limit waits,
and the API key never appearing in URLs. No network access."""
import io
import json
import urllib.error

import pytest

import ai.provider_gemini as pg
from ai.provider_gemini import RESTGeminiProvider


def make(monkeypatch, fallbacks=("b", "c")):
    p = RESTGeminiProvider(model_name="a", api_key="SECRET-KEY", fallback_models=list(fallbacks))
    p.OVERLOAD_PAUSE_S = 0
    monkeypatch.setattr("time.sleep", lambda s: None)
    return p


def test_falls_back_on_overload_and_reports_model(monkeypatch):
    p = make(monkeypatch)
    calls = []

    def fake(payload):
        calls.append(p.model_name)
        if p.model_name in ("a", "b"):
            raise RuntimeError("Gemini API Error 503: overloaded")
        return {"ok": True}
    monkeypatch.setattr(p, "_post_once", fake)
    assert p._post({}) == {"ok": True}
    assert calls == ["a", "b", "c"] and p.model_name == "c"


def test_cycles_again_after_all_candidates_overloaded(monkeypatch):
    p = make(monkeypatch)
    attempts = {"n": 0}

    def fake(payload):
        attempts["n"] += 1
        if attempts["n"] <= 4:
            raise RuntimeError("Gemini API Error 503: overloaded")
        return {"ok": p.model_name}
    monkeypatch.setattr(p, "_post_once", fake)
    assert p._post({}) == {"ok": "b"}          # a,b,c fail, pause, a fails, b succeeds


def test_gives_up_after_bounded_rounds(monkeypatch):
    p = make(monkeypatch)
    monkeypatch.setattr(p, "_post_once", lambda payload: (_ for _ in ()).throw(RuntimeError("Gemini API Error 503: x")))
    with pytest.raises(RuntimeError):
        p._post({})


def test_other_errors_are_not_retried(monkeypatch):
    p = make(monkeypatch)
    n = {"c": 0}

    def fake(payload):
        n["c"] += 1
        raise RuntimeError("Gemini API Error 400: bad request")
    monkeypatch.setattr(p, "_post_once", fake)
    with pytest.raises(RuntimeError):
        p._post({})
    assert n["c"] == 1


def test_rate_limit_waits_for_retry_delay_and_key_stays_out_of_url(monkeypatch):
    p = make(monkeypatch, fallbacks=())
    seen = []
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    body = json.dumps({"error": {"code": 429, "details": [{"retryDelay": "7s"}]}}).replace('"retryDelay": "7s"', '"retryDelay": "7s"')

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=None):
        seen.append((req.full_url, dict(req.header_items())))
        if len(seen) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "rate", {}, io.BytesIO(body.encode()))
        return Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}).encode())
    monkeypatch.setattr(pg.urllib.request, "urlopen", fake_urlopen)
    assert p.generate([{"role": "user", "content": "x"}]) == "hi"
    assert slept and slept[0] >= 7
    for url, headers in seen:
        assert "SECRET-KEY" not in url
        assert any(v == "SECRET-KEY" for k, v in headers.items() if k.lower() == "x-goog-api-key")


def test_factory_configures_fallbacks_without_exposing_keys(monkeypatch):
    from ai.factory import available_providers, create_provider
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY")
    p = create_provider("gemini")
    assert p.fallback_models and p.model_name not in p.fallback_models
    assert "SECRET-KEY" not in json.dumps(available_providers())


def test_daily_quota_moves_to_another_model(monkeypatch):
    p = make(monkeypatch)
    calls = []

    def fake(payload):
        calls.append(p.model_name)
        if p.model_name == "a":
            raise RuntimeError("Gemini API Error 429 (daily quota exhausted): ...")
        return {"ok": p.model_name}
    monkeypatch.setattr(p, "_post_once", fake)
    assert p._post({}) == {"ok": "b"}
    assert calls == ["a", "b"]
