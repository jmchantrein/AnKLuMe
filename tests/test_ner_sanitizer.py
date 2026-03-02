"""Tests for NER-based sanitization enhancement (Phase 39 enhancement).

Tests the heuristic backend (always available) and the NerSanitizer
interface. GLiNER/spaCy backends are tested only when available.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ner_sanitizer import (
    INFRA_LABELS,
    GlinerBackend,
    HeuristicBackend,
    NerEntity,
    NerSanitizer,
    SpacyBackend,
    create_backend,
)


def _gliner_available() -> bool:
    try:
        import gliner  # type: ignore[import-untyped] # noqa: F401
        return True
    except ImportError:
        return False


def _spacy_available() -> bool:
    try:
        import spacy  # type: ignore[import-untyped] # noqa: F401
        return True
    except ImportError:
        return False


class TestNerEntity:
    def test_entity_fields(self):
        e = NerEntity("pro-dev", "INFRA_HOST", 0, 7, 0.9, "heuristic")
        assert e.text == "pro-dev"
        assert e.label == "INFRA_HOST"
        assert e.confidence == 0.9
        assert e.source == "heuristic"

    def test_infra_labels_complete(self):
        assert "INFRA_HOST" in INFRA_LABELS
        assert "INFRA_PROJECT" in INFRA_LABELS
        assert "INFRA_SERVICE" in INFRA_LABELS
        assert "INFRA_DOMAIN" in INFRA_LABELS
        assert "INFRA_NETWORK" in INFRA_LABELS
        assert len(INFRA_LABELS) == 6


class TestHeuristicBackend:
    def setup_method(self):
        self.backend = HeuristicBackend()

    def test_name(self):
        assert self.backend.name == "heuristic"

    def test_detects_host_pattern(self):
        entities = self.backend.detect("connecting to pro-dev on port 22")
        names = [e.text for e in entities]
        assert "pro-dev" in names

    def test_detects_compound_host(self):
        entities = self.backend.detect("instance ai-gpu-worker is running")
        names = [e.text for e in entities]
        assert any("ai-gpu" in n for n in names)

    def test_ignores_common_words(self):
        entities = self.backend.detect("this is a read-only built-in feature")
        names = [e.text.lower() for e in entities]
        assert "read-only" not in names
        assert "built-in" not in names

    def test_detects_project_context(self):
        entities = self.backend.detect("switch to project ai-tools now")
        labels = [e.label for e in entities]
        assert "INFRA_PROJECT" in labels

    def test_detects_network_context(self):
        entities = self.backend.detect("bridge net-production is up")
        labels = [e.label for e in entities]
        assert "INFRA_NETWORK" in labels

    def test_ignores_short_matches(self):
        entities = self.backend.detect("project ab is small")
        project_entities = [e for e in entities if e.label == "INFRA_PROJECT"]
        assert len(project_entities) == 0

    def test_empty_text(self):
        assert self.backend.detect("") == []

    def test_no_infra_text(self):
        entities = self.backend.detect("The weather is nice today.")
        host_entities = [e for e in entities if e.label == "INFRA_HOST"]
        assert len(host_entities) == 0


class TestNerSanitizer:
    def setup_method(self):
        self.sanitizer = NerSanitizer(backend=HeuristicBackend())

    def test_sanitize_replaces_hosts(self):
        text = "connecting to pro-dev on port 22"
        result, entities = self.sanitizer.sanitize(text)
        assert "pro-dev" not in result
        assert "[REDACTED_HOST]" in result
        assert len(entities) > 0

    def test_sanitize_returns_entities(self):
        text = "instance perso-desktop is running"
        _, entities = self.sanitizer.sanitize(text)
        assert any(e.text == "perso-desktop" for e in entities)

    def test_sanitize_preserves_non_infra(self):
        text = "the system is running fine"
        result, entities = self.sanitizer.sanitize(text)
        assert result == text
        assert len(entities) == 0

    def test_min_confidence_filter(self):
        sanitizer = NerSanitizer(
            backend=HeuristicBackend(), min_confidence=0.9
        )
        entities = sanitizer.detect("connecting to pro-dev")
        assert len(entities) == 0

    def test_custom_replacement_map(self):
        sanitizer = NerSanitizer(
            backend=HeuristicBackend(),
            min_confidence=0.3,
            replacement_map={"INFRA_HOST": "***"},
        )
        result, _ = sanitizer.sanitize("host pro-dev is ready")
        assert "***" in result

    def test_multiple_entities(self):
        text = "from pro-dev to ai-gpu via bridge net-internal"
        result, entities = self.sanitizer.sanitize(text)
        assert len(entities) >= 2

    def test_detect_method(self):
        entities = self.sanitizer.detect("project learn has instances")
        assert isinstance(entities, list)


class TestCreateBackend:
    def test_auto_returns_backend(self):
        backend = create_backend("auto")
        assert hasattr(backend, "detect")
        assert hasattr(backend, "name")

    def test_heuristic_always_available(self):
        backend = create_backend("heuristic_only")
        assert backend.name == "heuristic"

    def test_gliner_import_error(self):
        backend = create_backend("gliner")
        assert backend.name in ("gliner", "heuristic")

    def test_spacy_import_error(self):
        backend = create_backend("spacy")
        assert backend.name in ("spacy", "heuristic")


@pytest.mark.skipif(not _gliner_available(), reason="GLiNER not installed")
class TestGlinerBackend:
    def test_gliner_detect(self):
        backend = GlinerBackend()
        entities = backend.detect("connecting to pro-dev instance")
        assert isinstance(entities, list)


@pytest.mark.skipif(not _spacy_available(), reason="spaCy not installed")
class TestSpacyBackend:
    def test_spacy_detect(self):
        backend = SpacyBackend()
        entities = backend.detect("deployed to Production server")
        assert isinstance(entities, list)
