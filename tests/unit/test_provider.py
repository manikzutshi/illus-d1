"""Tests for the mock model provider."""
import pytest

from ai.provider import MockModelProvider, ModelProvider
from core.models import DesignProject, ComponentInstance


class TestMockModelProvider:
    def test_is_model_provider(self):
        provider = MockModelProvider()
        assert isinstance(provider, ModelProvider)

    def test_default_response(self):
        provider = MockModelProvider()
        result = provider.generate("hello")
        assert "No configured response" in result

    def test_configured_response(self):
        provider = MockModelProvider()
        provider.set_response("parking", "Here is a smart parking design.")
        result = provider.generate("Build a smart parking system")
        assert result == "Here is a smart parking design."

    def test_case_insensitive_matching(self):
        provider = MockModelProvider()
        provider.set_response("PARKING", "found it")
        result = provider.generate("build a parking system")
        assert result == "found it"

    def test_structured_generate_with_match(self):
        provider = MockModelProvider()
        design = DesignProject(
            project_id="test", name="Test", components=[], nets=[]
        )
        provider.set_structured_response("parking", design)
        result = provider.structured_generate("smart parking", DesignProject)
        assert result.project_id == "test"

    def test_structured_generate_no_match_raises(self):
        provider = MockModelProvider()
        with pytest.raises(ValueError, match="No configured structured response"):
            provider.structured_generate("unknown prompt", DesignProject)

    def test_tool_call_returns_empty(self):
        provider = MockModelProvider()
        result = provider.tool_call("do something", [{"name": "test"}])
        assert result == []

    def test_no_api_key_needed(self):
        """The mock provider must work without any environment variable or API key."""
        provider = MockModelProvider()
        provider.set_response("test", "works")
        assert provider.generate("test") == "works"
