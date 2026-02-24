"""Tests for Phase 33: Student mode, bilingual help, CLI profiles.

Matrix: SM-001 to SM-005 — CLI mode persistence, i18n format,
help output differences, ANKLUME_LANG override.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = PROJECT_ROOT / "Makefile"
I18N_FR = PROJECT_ROOT / "i18n" / "fr.yml"
MODE_SET_SCRIPT = PROJECT_ROOT / "scripts" / "mode-set.sh"
HELP_I18N_SCRIPT = PROJECT_ROOT / "scripts" / "help-i18n.py"


# ── SM-001: Mode file creation and persistence ───────────


class TestModeFilePersistence:
    """Matrix: SM-001 — mode-set.sh creates and persists mode file."""

    def test_mode_set_script_exists(self):
        # Matrix: SM-001
        assert MODE_SET_SCRIPT.exists()

    def test_mode_set_script_is_executable(self):
        # Matrix: SM-001
        assert os.access(MODE_SET_SCRIPT, os.X_OK)

    def test_mode_set_creates_mode_file(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "student"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        mode_file = tmp_path / ".anklume" / "mode"
        assert mode_file.exists()
        assert mode_file.read_text().strip() == "student"

    def test_mode_set_user(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "user"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        mode_file = tmp_path / ".anklume" / "mode"
        assert mode_file.read_text().strip() == "user"

    def test_mode_set_dev(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "dev"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        mode_file = tmp_path / ".anklume" / "mode"
        assert mode_file.read_text().strip() == "dev"

    def test_mode_set_invalid_rejected(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "invalid"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0
        assert "Invalid mode" in result.stderr

    def test_mode_set_no_args_rejected(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(MODE_SET_SCRIPT)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0

    def test_mode_set_overwrites_previous(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "student"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "dev"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        mode_file = tmp_path / ".anklume" / "mode"
        assert mode_file.read_text().strip() == "dev"

    def test_mode_set_creates_directory(self, tmp_path):
        # Matrix: SM-001
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        # Ensure .anklume does not exist
        assert not (tmp_path / ".anklume").exists()
        subprocess.run(
            ["bash", str(MODE_SET_SCRIPT), "student"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert (tmp_path / ".anklume").is_dir()


# ── SM-002: i18n/fr.yml format validation ────────────────


class TestI18nFormat:
    """Matrix: SM-002 — i18n/fr.yml has valid format and coverage."""

    def test_i18n_fr_exists(self):
        # Matrix: SM-002
        assert I18N_FR.exists(), "i18n/fr.yml must exist"

    def test_i18n_fr_is_valid_yaml(self):
        # Matrix: SM-002
        with open(I18N_FR) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_i18n_fr_values_are_strings(self):
        # Matrix: SM-002
        with open(I18N_FR) as f:
            data = yaml.safe_load(f)
        for key, value in data.items():
            assert isinstance(key, str), f"Key {key!r} must be a string"
            assert isinstance(value, str), f"Value for {key!r} must be a string"

    def test_i18n_fr_covers_help_targets(self):
        """All targets shown in `make help` (user mode) have FR translations."""
        # Matrix: SM-002
        with open(I18N_FR) as f:
            translations = yaml.safe_load(f)

        # Targets from the categorized help (user mode)
        user_targets = [
            "guide", "quickstart", "init",
            "sync", "sync-dry", "apply", "apply-limit", "check",
            "nftables", "doctor",
            "snapshot", "restore", "rollback", "rollback-list",
            "apply-ai", "llm-switch", "llm-status", "llm-bench",
            "llm-dev", "ai-switch", "claude-host",
            "console", "dashboard",
            "disp", "backup", "instance-remove", "file-copy",
            "upgrade", "flush", "import-infra",
            "lab-list", "lab-start", "lab-check",
            "lint", "test", "smoke",
        ]
        missing = [t for t in user_targets if t not in translations]
        assert not missing, f"Missing FR translations: {missing}"

    def test_i18n_fr_covers_all_documented_targets(self):
        """Every Makefile target with ## has a FR translation."""
        # Matrix: SM-002
        content = MAKEFILE.read_text()
        pattern = re.compile(
            r"^([a-zA-Z_-]+):\s*(?:[^#]*?)##\s*(.+)$", re.MULTILINE
        )
        documented = {m.group(1) for m in pattern.finditer(content)}

        with open(I18N_FR) as f:
            translations = yaml.safe_load(f)

        missing = documented - set(translations.keys())
        assert not missing, (
            f"Documented targets missing from i18n/fr.yml: {missing}"
        )

    def test_i18n_fr_no_empty_values(self):
        # Matrix: SM-002
        with open(I18N_FR) as f:
            data = yaml.safe_load(f)
        empty = [k for k, v in data.items() if not v.strip()]
        assert not empty, f"Empty translations: {empty}"


# ── SM-003: Help output differs by mode ──────────────────


class TestHelpOutputByMode:
    """Matrix: SM-003 — Help output changes based on ANKLUME_MODE."""

    def test_help_i18n_script_exists(self):
        # Matrix: SM-003
        assert HELP_I18N_SCRIPT.exists()

    def test_student_help_shows_french(self):
        # Matrix: SM-003
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "student", "fr"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        # Student mode should show French category names
        assert "POUR COMMENCER" in result.stdout
        assert "WORKFLOW PRINCIPAL" in result.stdout

    def test_student_help_shows_fr_descriptions(self):
        # Matrix: SM-003
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "student", "fr"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        # Should contain a French description for sync
        assert "Generer" in result.stdout or "generer" in result.stdout

    def test_dev_help_shows_all_targets(self):
        # Matrix: SM-003
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "dev", "fr"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "dev mode" in result.stdout
        # Dev mode should list many targets
        assert "lint-yaml" in result.stdout
        assert "apply-infra" in result.stdout
        assert "test-generator" in result.stdout

    def test_user_mode_not_handled_by_i18n(self):
        # Matrix: SM-003
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "user"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        # user mode should exit with error (Makefile handles it natively)
        assert result.returncode != 0

    def test_student_shows_mode_indicator(self):
        # Matrix: SM-003
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "student", "fr"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert "student" in result.stdout
        assert "mode-user" in result.stdout

    def test_dev_shows_mode_indicator(self):
        # Matrix: SM-003
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "dev", "fr"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert "dev" in result.stdout
        assert "mode-user" in result.stdout


# ── SM-004: ANKLUME_LANG override ────────────────────────


class TestAnklumeLangOverride:
    """Matrix: SM-004 — ANKLUME_LANG env var overrides default language."""

    def test_makefile_reads_anklume_mode(self):
        # Matrix: SM-004
        content = MAKEFILE.read_text()
        assert "ANKLUME_MODE" in content
        assert "cat" in content and ".anklume/mode" in content

    def test_makefile_reads_anklume_lang(self):
        # Matrix: SM-004
        content = MAKEFILE.read_text()
        assert "ANKLUME_LANG" in content

    def test_student_mode_defaults_to_fr(self):
        """In student mode, ANKLUME_LANG defaults to fr."""
        # Matrix: SM-004
        content = MAKEFILE.read_text()
        # The Makefile should set ANKLUME_LANG to fr when mode is student
        assert re.search(r"ANKLUME_LANG.*student.*fr", content)

    def test_help_i18n_accepts_lang_arg(self):
        # Matrix: SM-004
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "student", "fr"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0

    def test_missing_lang_file_no_crash(self):
        """If the language file does not exist, help still works."""
        # Matrix: SM-004
        result = subprocess.run(
            ["python3", str(HELP_I18N_SCRIPT), "student", "nonexistent"],
            capture_output=True, text=True, timeout=10,
            cwd=str(PROJECT_ROOT),
        )
        # Should still succeed, just without translations
        assert result.returncode == 0


# ── SM-005: Makefile mode targets ────────────────────────


class TestMakeModeTargets:
    """Matrix: SM-005 — mode-student, mode-user, mode-dev targets exist."""

    def test_mode_targets_in_makefile(self):
        # Matrix: SM-005
        content = MAKEFILE.read_text()
        for target in ["mode-student", "mode-user", "mode-dev"]:
            assert f"\n{target}:" in content, (
                f"Target '{target}' not found in Makefile"
            )

    def test_mode_targets_in_phony(self):
        # Matrix: SM-005
        content = MAKEFILE.read_text()
        phony_match = re.search(
            r"^\.PHONY:\s*(.*?)(?:\n(?!\s)|\Z)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert phony_match, ".PHONY declaration not found"
        raw = phony_match.group(1).replace("\\\n", " ")
        phony_set = set(raw.split())
        for target in ["mode-student", "mode-user", "mode-dev"]:
            assert target in phony_set, (
                f"'{target}' missing from .PHONY"
            )

    def test_mode_targets_have_descriptions(self):
        # Matrix: SM-005
        content = MAKEFILE.read_text()
        pattern = re.compile(
            r"^([a-zA-Z_-]+):\s*(?:[^#]*?)##\s*(.+)$", re.MULTILINE
        )
        documented = {m.group(1): m.group(2).strip() for m in pattern.finditer(content)}
        for target in ["mode-student", "mode-user", "mode-dev"]:
            assert target in documented, (
                f"Target '{target}' has no ## description"
            )

    def test_mode_targets_call_mode_set(self):
        # Matrix: SM-005
        content = MAKEFILE.read_text()
        assert "mode-set.sh student" in content
        assert "mode-set.sh user" in content
        assert "mode-set.sh dev" in content

    def test_make_help_default_mode(self):
        """Default mode (no mode file) shows standard help."""
        # Matrix: SM-005
        env = os.environ.copy()
        env["HOME"] = "/tmp/anklume-test-nonexistent-home"
        env.pop("ANKLUME_MODE", None)
        result = subprocess.run(
            ["make", "help"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            env=env, timeout=15,
        )
        assert result.returncode == 0
        # Default mode (user) should show English categories
        assert "GETTING STARTED" in result.stdout

    def test_make_help_student_mode_override(self):
        """ANKLUME_MODE=student shows French help."""
        # Matrix: SM-005
        env = os.environ.copy()
        env["ANKLUME_MODE"] = "student"
        result = subprocess.run(
            ["make", "help"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            env=env, timeout=15,
        )
        assert result.returncode == 0
        assert "POUR COMMENCER" in result.stdout


# ── Shell quality ────────────────────────────────────────


@pytest.mark.skipif(
    shutil.which("shellcheck") is None,
    reason="shellcheck not installed",
)
class TestModeSetShellQuality:
    """Validate mode-set.sh passes shellcheck."""

    def test_mode_set_shellcheck(self):
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(MODE_SET_SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}\n{result.stderr}"
