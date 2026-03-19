"""Sanitisation de données sensibles avant envoi à un LLM externe.

Détecte et remplace les IPs privées, FQDNs internes, credentials,
MAC addresses, sockets Unix, commandes Incus et ressources Incus.
Deux modes : mask (placeholders indexés) et pseudonymize (cohérent).
Détection NER optionnelle (GLiNER/spaCy). Audit logging.
"""

from __future__ import annotations

import functools
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anklume.engine.models import Infrastructure

SANITIZE_MODES = {"mask", "pseudonymize"}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Replacement:
    """Un remplacement effectué par le sanitizer."""

    original: str
    replaced: str
    category: str  # ip, resource, fqdn, credential, mac, socket, incus_cmd, ner
    position: tuple[int, int]  # (start, end) dans le texte original


@dataclass
class SanitizeResult:
    """Résultat d'une sanitisation."""

    text: str
    replacements: list[Replacement] = field(default_factory=list)


@dataclass
class AuditEntry:
    """Une entrée d'audit de sanitisation."""

    timestamp: str  # ISO 8601
    mode: str  # mask | pseudonymize
    categories: dict[str, int]  # {"ip": 2, "credential": 1}
    total_redactions: int


# ---------------------------------------------------------------------------
# Patterns de détection — registre data-driven
# ---------------------------------------------------------------------------

# IPs privées RFC 1918
_IP_10 = re.compile(r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_IP_172 = re.compile(r"\b(172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")
_IP_192 = re.compile(r"\b(192\.168\.\d{1,3}\.\d{1,3})\b")

# FQDNs internes
_FQDN_INTERNAL = re.compile(r"\b([\w][\w.-]*\.(internal|local|corp))\b")

# Credentials
_BEARER = re.compile(r"Bearer\s+(\S+)", re.IGNORECASE)
_KEY_VALUE = re.compile(
    r"(?:api_key|token|secret|password|key)\s*[=:]\s*(\S+)",
    re.IGNORECASE,
)

# MAC addresses
_MAC = re.compile(r"\b([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b")

# Sockets Unix
_SOCKET = re.compile(
    r"(/(?:var/)?run/[\w./-]+(?:\.sock(?:et)?|_socket)|/tmp/[\w./-]+\.sock(?:et)?)"
)

# Commandes Incus
_INCUS_CMD = re.compile(
    r"(incus\s+(?:exec|launch|start|stop|delete|config|copy|move|snapshot)"
    r"\s+[^\n;|&]+)"
)

# Registre : catégorie → liste de patterns compilés
_PATTERN_REGISTRY: list[tuple[str, list[re.Pattern[str]]]] = [
    ("ip", [_IP_10, _IP_172, _IP_192]),
    ("fqdn", [_FQDN_INTERNAL]),
    ("credential", [_BEARER, _KEY_VALUE]),
    ("mac", [_MAC]),
    ("socket", [_SOCKET]),
    ("incus_cmd", [_INCUS_CMD]),
]

# Pseudonymes par catégorie (idx → texte de remplacement)
_PSEUDO_TEMPLATES: dict[str, Callable[[int], str]] = {
    "ip": lambda idx: f"10.ZONE.{idx}.1",
    "fqdn": lambda idx: f"host-{idx}.example",
    "credential": lambda _idx: "[CREDENTIAL]",
    "resource": lambda idx: f"resource-{idx}",
    "mac": lambda idx: f"00:00:00:00:00:{idx:02d}",
    "socket": lambda idx: f"/run/redacted-{idx}.sock",
    "incus_cmd": lambda idx: f"incus [COMMAND_{idx}]",
    "ner": lambda idx: f"[ENTITY_{idx}]",
}


# ---------------------------------------------------------------------------
# sanitize()
# ---------------------------------------------------------------------------


def sanitize(
    text: str,
    *,
    infra: Infrastructure | None = None,
    mode: str = "mask",
    ner: bool = False,
    categories: set[str] | None = None,
) -> SanitizeResult:
    """Détecte et remplace les données sensibles dans le texte.

    Args:
        text: Texte à sanitiser.
        infra: Infrastructure (optionnel, pour détecter les ressources Incus).
        mode: "mask" (placeholders indexés) ou "pseudonymize" (cohérent).
        ner: Activer la détection NER (GLiNER/spaCy).
        categories: Catégories à détecter (None = toutes).

    Returns:
        SanitizeResult avec le texte sanitisé et les remplacements.

    Raises:
        ValueError: mode invalide.
    """
    if mode not in SANITIZE_MODES:
        msg = f"mode invalide : {mode!r} (attendu : {', '.join(sorted(SANITIZE_MODES))})"
        raise ValueError(msg)

    # Ensemble vide = aucune catégorie active
    if categories is not None and len(categories) == 0:
        return SanitizeResult(text=text, replacements=[])

    replacements: list[Replacement] = []
    counters: dict[str, int] = {}
    pseudo_map: dict[str, str] = {}
    pseudo_counters: dict[str, int] = {}

    # Collecter tous les matches avec leur catégorie
    matches: list[tuple[int, int, str, str]] = []

    def _cat_active(cat: str) -> bool:
        return categories is None or cat in categories

    # Patterns regex (data-driven)
    for cat, patterns in _PATTERN_REGISTRY:
        if _cat_active(cat):
            for pattern in patterns:
                for m in pattern.finditer(text):
                    matches.append((m.start(1), m.end(1), m.group(1), cat))

    # Ressources Incus (si infra fournie)
    if _cat_active("resource") and infra is not None:
        resource_names = _collect_resource_names(infra)
        for name in resource_names:
            for m in re.finditer(re.escape(name), text):
                matches.append((m.start(), m.end(), name, "resource"))

    # NER optionnel
    if ner and _cat_active("ner"):
        backend = detect_ner_backend()
        if backend:
            for start, end, entity_text in ner_extract(text, backend):
                matches.append((start, end, entity_text, "ner"))

    # Dédupliquer et trier par position
    matches = _deduplicate_matches(matches)
    matches.sort(key=lambda x: x[0])

    # Construire les remplacements
    for start, end, original, category in matches:
        replaced = _make_replacement(
            original,
            category,
            mode,
            counters,
            pseudo_map,
            pseudo_counters,
        )
        replacements.append(
            Replacement(
                original=original,
                replaced=replaced,
                category=category,
                position=(start, end),
            )
        )

    # Appliquer les remplacements (de droite à gauche pour conserver les positions)
    result_text = text
    for repl in reversed(replacements):
        s, e = repl.position
        result_text = result_text[:s] + repl.replaced + result_text[e:]

    return SanitizeResult(text=result_text, replacements=replacements)


# ---------------------------------------------------------------------------
# desanitize()
# ---------------------------------------------------------------------------


def desanitize(text: str, replacements: list[Replacement]) -> str:
    """Restaure les valeurs originales dans un texte sanitisé.

    Remplace chaque placeholder par sa valeur originale.
    """
    result = text
    for repl in replacements:
        result = result.replace(repl.replaced, repl.original, 1)
    return result


# ---------------------------------------------------------------------------
# NER optionnel
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def detect_ner_backend() -> str | None:
    """Détecte le backend NER disponible (gliner > spacy > None)."""
    try:
        import gliner  # noqa: F401

        return "gliner"
    except ImportError:
        pass
    try:
        import spacy  # noqa: F401

        return "spacy"
    except ImportError:
        pass
    return None


def ner_extract(text: str, backend: str) -> list[tuple[int, int, str]]:
    """Extrait les entités via NER. Retourne [(start, end, entity_text)].

    Fallback gracieux : retourne liste vide si le backend est indisponible.
    """
    if backend == "gliner":
        return _ner_gliner(text)
    if backend == "spacy":
        return _ner_spacy(text)
    return []


@functools.lru_cache(maxsize=1)
def _get_gliner_model():
    """Charge le modèle GLiNER (caché après premier appel)."""
    from gliner import GLiNER

    return GLiNER.from_pretrained("urchade/gliner_base")


@functools.lru_cache(maxsize=1)
def _get_spacy_model():
    """Charge le modèle spaCy (caché après premier appel)."""
    import spacy

    return spacy.load("fr_core_news_sm")


def _ner_gliner(text: str) -> list[tuple[int, int, str]]:
    """Extraction NER via GLiNER."""
    try:
        model = _get_gliner_model()
        labels = ["person", "organization", "location"]
        entities = model.predict_entities(text, labels)
        return [(e["start"], e["end"], e["text"]) for e in entities]
    except Exception:
        return []


def _ner_spacy(text: str) -> list[tuple[int, int, str]]:
    """Extraction NER via spaCy."""
    try:
        nlp = _get_spacy_model()
        doc = nlp(text)
        return [
            (ent.start_char, ent.end_char, ent.text)
            for ent in doc.ents
            if ent.label_ in {"PER", "ORG", "LOC"}
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def audit_log(
    result: SanitizeResult,
    *,
    mode: str,
    log_path: Path | None = None,
) -> AuditEntry:
    """Écrit une entrée d'audit et la retourne.

    log_path: chemin du fichier d'audit
    (défaut: /var/log/anklume/sanitizer/audit.jsonl).
    """
    if log_path is None:
        log_path = Path("/var/log/anklume/sanitizer/audit.jsonl")

    entry = AuditEntry(
        timestamp=datetime.now(tz=UTC).isoformat(),
        mode=mode,
        categories=dict(Counter(r.category for r in result.replacements)),
        total_redactions=len(result.replacements),
    )

    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with log_path.open("a") as f:
        f.write(json.dumps(asdict(entry)) + "\n")
    log_path.chmod(0o600)

    return entry


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _collect_resource_names(infra: Infrastructure) -> list[str]:
    """Collecte les noms de ressources Incus depuis l'infrastructure.

    Retourne les noms triés du plus long au plus court
    (pour éviter les remplacements partiels).
    """
    names: set[str] = set()
    for domain in infra.domains.values():
        names.add(domain.network_name)
        for machine in domain.machines.values():
            names.add(machine.full_name)
    return sorted(names, key=len, reverse=True)


def _deduplicate_matches(
    matches: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Supprime les matches qui se chevauchent (garde le plus spécifique)."""
    if not matches:
        return []
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    result: list[tuple[int, int, str, str]] = [matches[0]]
    for m in matches[1:]:
        prev = result[-1]
        if m[0] >= prev[1]:
            result.append(m)
    return result


def _make_replacement(
    original: str,
    category: str,
    mode: str,
    counters: dict[str, int],
    pseudo_map: dict[str, str],
    pseudo_counters: dict[str, int],
) -> str:
    """Génère le texte de remplacement selon le mode."""
    if mode == "mask":
        return _mask_replacement(original, category, counters)
    return _pseudonymize_replacement(original, category, pseudo_map, pseudo_counters)


def _mask_replacement(
    original: str,
    category: str,
    counters: dict[str, int],
) -> str:
    """Mode mask : placeholder indexé."""
    label = category.upper()
    counters[category] = counters.get(category, 0) + 1
    return f"[{label}_REDACTED_{counters[category]}]"


def _pseudonymize_replacement(
    original: str,
    category: str,
    pseudo_map: dict[str, str],
    pseudo_counters: dict[str, int],
) -> str:
    """Mode pseudonymize : remplacement cohérent par catégorie."""
    if original in pseudo_map:
        return pseudo_map[original]

    pseudo_counters[category] = pseudo_counters.get(category, 0) + 1
    idx = pseudo_counters[category]

    pseudo = _PSEUDO_TEMPLATES.get(category, lambda i: "[REDACTED]")(idx)

    pseudo_map[original] = pseudo
    return pseudo
