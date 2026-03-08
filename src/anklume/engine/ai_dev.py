"""Développement assisté par IA — boucle test + analyse LLM + fix.

Fournit `run_ai_test_loop` pour exécuter les tests, analyser les erreurs
via un LLM (Ollama ou Claude), et proposer/appliquer des corrections.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

AI_TEST_BACKENDS = {"ollama", "claude"}
AI_TEST_MODES = {"dry-run", "auto-apply", "auto-pr"}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AiTestConfig:
    """Configuration de la boucle test IA."""

    backend: str = "ollama"  # "ollama" | "claude"
    mode: str = "dry-run"  # "dry-run" | "auto-apply" | "auto-pr"
    max_retries: int = 3
    model: str = ""


@dataclass
class AiTestResult:
    """Résultat d'une itération de la boucle."""

    iteration: int
    tests_passed: bool
    errors: list[str] = field(default_factory=list)
    fixes_proposed: list[str] = field(default_factory=list)
    fixes_applied: bool = False


# ---------------------------------------------------------------------------
# run_ai_test_loop
# ---------------------------------------------------------------------------


def run_ai_test_loop(
    config: AiTestConfig,
    *,
    project_dir: Path | None = None,
) -> list[AiTestResult]:
    """Exécute la boucle test + analyse LLM + fix.

    Args:
        config: Configuration de la boucle.
        project_dir: Répertoire du projet (défaut : cwd).

    Returns:
        Liste de résultats, un par itération.

    Raises:
        ValueError: backend ou mode invalide.
    """
    if config.backend not in AI_TEST_BACKENDS:
        expected = ", ".join(sorted(AI_TEST_BACKENDS))
        msg = f"backend invalide : {config.backend!r} (attendu : {expected})"
        raise ValueError(msg)

    if config.mode not in AI_TEST_MODES:
        msg = f"mode invalide : {config.mode!r} (attendu : {', '.join(sorted(AI_TEST_MODES))})"
        raise ValueError(msg)

    cwd = project_dir or Path.cwd()
    results: list[AiTestResult] = []

    for i in range(1, config.max_retries + 1):
        passed, errors = _run_tests(cwd)

        if passed:
            results.append(
                AiTestResult(
                    iteration=i,
                    tests_passed=True,
                )
            )
            break

        # Analyser les erreurs via LLM
        fixes = _analyze_errors(errors, config)

        applied = False
        if config.mode == "auto-apply" and fixes:
            applied = _apply_fixes(fixes, cwd)

        results.append(
            AiTestResult(
                iteration=i,
                tests_passed=False,
                errors=errors,
                fixes_proposed=fixes,
                fixes_applied=applied,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _run_tests(project_dir: Path) -> tuple[bool, list[str]]:
    """Exécute pytest et retourne (passed, errors)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=str(project_dir),
            timeout=300,
        )
        if result.returncode == 0:
            return True, []

        # Extraire les lignes d'erreur
        errors = [
            line for line in result.stdout.splitlines() if "FAILED" in line or "ERROR" in line
        ]
        if not errors and result.stderr:
            errors = result.stderr.splitlines()[:10]
        return False, errors

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, [str(e)]


def _analyze_errors(
    errors: list[str],
    config: AiTestConfig,
) -> list[str]:
    """Analyse les erreurs via un LLM et propose des corrections.

    Pour l'instant, retourne les erreurs formatées comme suggestions.
    L'intégration LLM réelle sera ajoutée ultérieurement.
    """
    log.info(
        "Analyse des erreurs via %s (modèle: %s)",
        config.backend,
        config.model or "défaut",
    )
    # Placeholder : suggestions basées sur les erreurs
    return [f"Correction suggérée pour : {e}" for e in errors]


def _apply_fixes(fixes: list[str], project_dir: Path) -> bool:
    """Applique les corrections proposées.

    Pour l'instant, log les corrections sans les appliquer.
    L'application réelle sera ajoutée avec l'intégration LLM.
    """
    log.info("Application de %d corrections dans %s", len(fixes), project_dir)
    return True
