"""Tests for the curriculum store."""
import pytest
from pathlib import Path

from curriculum.store import CurriculumStore, get_default_curriculum
from core.enums import CompetencyLevel


class TestCurriculumStore:
    @pytest.fixture
    def store(self) -> CurriculumStore:
        return get_default_curriculum()

    def test_load_default(self, store):
        assert store.count >= 8
        for cid in ("cmos_inverter", "digital_logic_gate", "fsm_design", "rtl_design", "verification",
                    "timing_analysis", "sensor_integration", "embedded_basics"):
            assert store.get(cid) is not None

    def test_get_known_concept(self, store):
        concept = store.get("cmos_inverter")
        assert concept is not None
        assert concept.name == "CMOS Inverter"
        assert concept.competency_level == CompetencyLevel.INTERMEDIATE

    def test_get_unknown_concept(self, store):
        assert store.get("nonexistent") is None

    def test_search_by_name(self, store):
        results = store.search("Logic Gate")
        assert len(results) >= 1
        assert results[0].concept_id == "digital_logic_gate"

    def test_search_by_description(self, store):
        results = store.search("microcontroller")
        assert len(results) >= 1

    def test_search_no_results(self, store):
        results = store.search("quantum_teleportation")
        assert len(results) == 0

    def test_concept_has_prerequisites(self, store):
        fsm = store.get("fsm_design")
        assert "digital_logic_gate" in fsm.prerequisites

    def test_list_all(self, store):
        all_concepts = store.list_all()
        assert len(all_concepts) == store.count

    def test_load_nonexistent_file(self):
        s = CurriculumStore()
        count = s.load_yaml(Path("/nonexistent/file.yaml"))
        assert count == 0
