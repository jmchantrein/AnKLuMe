"""NER-based sanitization enhancement for LLM proxy (Phase 39 enhancement).

Complements regex-based patterns with Named Entity Recognition to detect
infrastructure entities that regex cannot reliably catch: custom project
names, non-standard domain naming, service names in natural language.

Supports two backends (auto-detected):
  - GLiNER: zero-shot NER, lightweight, no training data needed
  - spaCy: traditional NER with custom entity training

Falls back to enhanced heuristic detection when neither is available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class NerEntity:
    """A detected infrastructure entity."""

    text: str
    label: str  # INFRA_HOST, INFRA_PROJECT, INFRA_SERVICE, INFRA_DOMAIN
    start: int
    end: int
    confidence: float
    source: str  # "gliner", "spacy", "heuristic"


INFRA_LABELS = [
    "INFRA_HOST",
    "INFRA_PROJECT",
    "INFRA_SERVICE",
    "INFRA_DOMAIN",
    "INFRA_NETWORK",
    "INFRA_CREDENTIAL",
]

# Heuristic patterns for infrastructure naming conventions
_HEURISTIC_PATTERNS = {
    "INFRA_HOST": re.compile(
        r"\b[a-z][a-z0-9]+-[a-z][a-z0-9]+(?:-[a-z0-9]+)?\b"
    ),
    "INFRA_PROJECT": re.compile(
        r"\b(?:project|proj)\s+([a-z][a-z0-9-]{1,30})\b", re.IGNORECASE
    ),
    "INFRA_NETWORK": re.compile(
        r"\b(?:bridge|network|subnet|vlan)\s+([a-z][a-z0-9-]{1,30})\b",
        re.IGNORECASE,
    ),
}

# Common English words to exclude from heuristic host detection
_COMMON_WORDS = frozenset(
    {
        "the-end",
        "up-to",
        "set-up",
        "how-to",
        "log-in",
        "sign-in",
        "opt-in",
        "opt-out",
        "run-time",
        "real-time",
        "read-only",
        "read-write",
        "non-root",
        "pre-built",
        "well-known",
        "built-in",
    }
)


class NerBackend(Protocol):
    """Interface for NER backends."""

    def detect(self, text: str) -> list[NerEntity]: ...

    @property
    def name(self) -> str: ...


class GlinerBackend:
    """GLiNER zero-shot NER backend."""

    def __init__(self, model_name: str = "urchade/gliner_base"):
        from gliner import GLiNER  # type: ignore[import-untyped]

        self._model = GLiNER.from_pretrained(model_name)

    @property
    def name(self) -> str:
        return "gliner"

    def detect(self, text: str) -> list[NerEntity]:
        raw = self._model.predict_entities(text, INFRA_LABELS)
        return [
            NerEntity(
                text=e["text"],
                label=e["label"],
                start=e["start"],
                end=e["end"],
                confidence=e["score"],
                source="gliner",
            )
            for e in raw
            if e["score"] >= 0.5
        ]


class SpacyBackend:
    """spaCy NER backend with custom IaC entity labels."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        import spacy  # type: ignore[import-untyped]

        self._nlp = spacy.load(model_name)

    @property
    def name(self) -> str:
        return "spacy"

    def detect(self, text: str) -> list[NerEntity]:
        doc = self._nlp(text)
        results = []
        for ent in doc.ents:
            label = _map_spacy_label(ent.label_)
            if label:
                results.append(
                    NerEntity(
                        text=ent.text,
                        label=label,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=0.7,
                        source="spacy",
                    )
                )
        return results


def _map_spacy_label(spacy_label: str) -> str | None:
    """Map standard spaCy labels to infrastructure labels."""
    mapping = {
        "ORG": "INFRA_PROJECT",
        "PRODUCT": "INFRA_SERVICE",
        "FAC": "INFRA_NETWORK",
    }
    return mapping.get(spacy_label)


class HeuristicBackend:
    """Fallback heuristic detection using naming conventions."""

    @property
    def name(self) -> str:
        return "heuristic"

    def detect(self, text: str) -> list[NerEntity]:
        results: list[NerEntity] = []
        for label, pattern in _HEURISTIC_PATTERNS.items():
            for m in pattern.finditer(text):
                matched = m.group(1) if m.lastindex else m.group(0)
                if matched.lower() in _COMMON_WORDS:
                    continue
                if len(matched) < 3:
                    continue
                results.append(
                    NerEntity(
                        text=matched,
                        label=label,
                        start=m.start(),
                        end=m.end(),
                        confidence=0.6,
                        source="heuristic",
                    )
                )
        return results


@dataclass
class NerSanitizer:
    """NER-based sanitizer that complements regex patterns."""

    backend: NerBackend = field(default_factory=HeuristicBackend)
    min_confidence: float = 0.5
    replacement_map: dict[str, str] = field(default_factory=lambda: {
        "INFRA_HOST": "[REDACTED_HOST]",
        "INFRA_PROJECT": "[REDACTED_PROJECT]",
        "INFRA_SERVICE": "[REDACTED_SERVICE]",
        "INFRA_DOMAIN": "[REDACTED_DOMAIN]",
        "INFRA_NETWORK": "[REDACTED_NETWORK]",
        "INFRA_CREDENTIAL": "[REDACTED]",
    })

    def detect(self, text: str) -> list[NerEntity]:
        """Detect infrastructure entities in text."""
        entities = self.backend.detect(text)
        return [e for e in entities if e.confidence >= self.min_confidence]

    def sanitize(self, text: str) -> tuple[str, list[NerEntity]]:
        """Sanitize text by replacing detected entities."""
        entities = self.detect(text)
        entities.sort(key=lambda e: e.start, reverse=True)
        result = text
        for entity in entities:
            replacement = self.replacement_map.get(entity.label, "[REDACTED]")
            result = result[:entity.start] + replacement + result[entity.end:]
        return result, entities


def create_backend(preferred: str = "auto") -> NerBackend:
    """Create the best available NER backend."""
    if preferred == "gliner" or preferred == "auto":
        try:
            return GlinerBackend()
        except ImportError:
            pass
    if preferred == "spacy" or preferred == "auto":
        try:
            return SpacyBackend()
        except (ImportError, OSError):
            pass
    return HeuristicBackend()
