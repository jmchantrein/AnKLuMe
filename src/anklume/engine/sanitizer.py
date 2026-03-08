"""Sanitisation de données sensibles avant envoi à un LLM externe.

Détecte et remplace les IPs privées, FQDNs internes, credentials
et ressources Incus. Deux modes : mask (placeholders indexés)
et pseudonymize (remplacement cohérent).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
    category: str  # "ip", "resource", "fqdn", "credential"
    position: tuple[int, int]  # (start, end) dans le texte original


@dataclass
class SanitizeResult:
    """Résultat d'une sanitisation."""

    text: str
    replacements: list[Replacement] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Patterns de détection
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


# ---------------------------------------------------------------------------
# sanitize()
# ---------------------------------------------------------------------------


def sanitize(
    text: str,
    *,
    infra: Infrastructure | None = None,
    mode: str = "mask",
) -> SanitizeResult:
    """Détecte et remplace les données sensibles dans le texte.

    Args:
        text: Texte à sanitiser.
        infra: Infrastructure (optionnel, pour détecter les ressources Incus).
        mode: "mask" (placeholders indexés) ou "pseudonymize" (cohérent).

    Returns:
        SanitizeResult avec le texte sanitisé et les remplacements.

    Raises:
        ValueError: mode invalide.
    """
    if mode not in SANITIZE_MODES:
        msg = f"mode invalide : {mode!r} (attendu : {', '.join(sorted(SANITIZE_MODES))})"
        raise ValueError(msg)

    replacements: list[Replacement] = []
    # Compteurs pour les placeholders mask
    counters: dict[str, int] = {}
    # Table de mapping + compteurs par catégorie pour pseudonymize
    pseudo_map: dict[str, str] = {}
    pseudo_counters: dict[str, int] = {}

    # Collecter tous les matches avec leur catégorie
    matches: list[tuple[int, int, str, str]] = []  # (start, end, original, category)

    # IPs privées
    for pattern in (_IP_10, _IP_172, _IP_192):
        for m in pattern.finditer(text):
            matches.append((m.start(1), m.end(1), m.group(1), "ip"))

    # FQDNs internes
    for m in _FQDN_INTERNAL.finditer(text):
        matches.append((m.start(1), m.end(1), m.group(1), "fqdn"))

    # Credentials
    for m in _BEARER.finditer(text):
        matches.append((m.start(1), m.end(1), m.group(1), "credential"))
    for m in _KEY_VALUE.finditer(text):
        matches.append((m.start(1), m.end(1), m.group(1), "credential"))

    # Ressources Incus (si infra fournie)
    if infra is not None:
        resource_names = _collect_resource_names(infra)
        for name in resource_names:
            for m in re.finditer(re.escape(name), text):
                matches.append((m.start(), m.end(), name, "resource"))

    # Dédupliquer et trier par position (fin → début pour remplacement)
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
# Helpers internes
# ---------------------------------------------------------------------------


def _collect_resource_names(infra: Infrastructure) -> list[str]:
    """Collecte les noms de ressources Incus depuis l'infrastructure.

    Retourne les noms triés du plus long au plus court
    (pour éviter les remplacements partiels).
    """
    names: set[str] = set()
    for domain in infra.domains.values():
        # Nom du bridge
        names.add(domain.network_name)
        # Noms des machines
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
        if m[0] >= prev[1]:  # Pas de chevauchement
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

    if category == "ip":
        pseudo = f"10.ZONE.{idx}.1"
    elif category == "fqdn":
        pseudo = f"host-{idx}.example"
    elif category == "credential":
        pseudo = "[CREDENTIAL]"
    elif category == "resource":
        pseudo = f"resource-{idx}"
    else:
        pseudo = "[REDACTED]"

    pseudo_map[original] = pseudo
    return pseudo
