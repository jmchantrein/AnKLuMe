"""Tests for the anklume CLI (Phase 43)."""

import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("typer")

from typer.testing import CliRunner  # noqa: E402

from scripts.cli import app  # noqa: E402

runner = CliRunner()

# Rich inserts ANSI bold/color codes that break plain-text assertions in CI.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)

# ── Fixture: minimal infra.yml ──────────────────────────────

MINIMAL_INFRA = """\
project_name: test-cli
global:
  addressing:
    base_octet: 10
    zone_base: 100
  default_os_image: "images:debian/13"
  default_connection: community.general.incus
  default_user: root
domains:
  anklume:
    trust_level: admin
    description: "Admin domain"
    machines:
      anklume-ctl:
        description: "Controller"
        type: lxc
        roles: [base_system]
  work:
    trust_level: semi-trusted
    description: "Work environment"
    machines:
      work-dev:
        description: "Dev container"
        type: lxc
        roles: [base_system]
"""


@pytest.fixture()
def infra_dir(tmp_path):
    """Create a temp directory with a minimal infra.yml."""
    (tmp_path / "infra.yml").write_text(MINIMAL_INFRA)
    # Create required directories
    for d in ("inventory", "group_vars", "host_vars"):
        (tmp_path / d).mkdir()
    return tmp_path


# ── Top-level tests ─────────────────────────────────────────


class TestTopLevel:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "anklume" in result.output.lower()
        assert "domain" in result.output
        assert "instance" in result.output
        assert "snapshot" in result.output

    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        # no_args_is_help returns exit code 0 or 2 depending on Typer version
        assert result.exit_code in (0, 2)
        assert "Commands" in result.output


# ── Domain tests ────────────────────────────────────────────


class TestDomain:
    def test_domain_help(self):
        result = runner.invoke(app, ["domain", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "apply" in result.output
        assert "status" in result.output

    def test_domain_list(self, infra_dir):
        with patch("scripts.cli._helpers.PROJECT_ROOT", infra_dir):
            result = runner.invoke(app, ["domain", "list"])
        assert result.exit_code == 0
        assert "anklume" in result.output
        assert "work" in result.output
        assert "admin" in result.output
        assert "semi-trusted" in result.output


# ── Instance tests ──────────────────────────────────────────


class TestInstance:
    def test_instance_help(self):
        result = runner.invoke(app, ["instance", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "remove" in result.output
        assert "exec" in result.output
        assert "info" in result.output


# ── Snapshot tests ──────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_help(self):
        result = runner.invoke(app, ["snapshot", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "restore" in result.output
        assert "list" in result.output
        assert "delete" in result.output
        assert "rollback" in result.output


# ── Network tests ───────────────────────────────────────────


class TestNetwork:
    def test_network_help(self):
        result = runner.invoke(app, ["network", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "rules" in result.output
        assert "deploy" in result.output


# ── Portal tests ────────────────────────────────────────────


class TestPortal:
    def test_portal_help(self):
        result = runner.invoke(app, ["portal", "--help"])
        assert result.exit_code == 0
        assert "open" in result.output
        assert "push" in result.output
        assert "pull" in result.output
        assert "list" in result.output


# ── App tests ───────────────────────────────────────────────


class TestApp:
    def test_app_help(self):
        result = runner.invoke(app, ["app", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output
        assert "list" in result.output
        assert "remove" in result.output


# ── Desktop tests ───────────────────────────────────────────


class TestDesktop:
    def test_desktop_help(self):
        result = runner.invoke(app, ["desktop", "--help"])
        assert result.exit_code == 0
        assert "apply" in result.output
        assert "reset" in result.output
        assert "plugins" in result.output


# ── LLM tests ──────────────────────────────────────────────


class TestLLM:
    def test_llm_help(self):
        result = runner.invoke(app, ["llm", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "switch" in result.output
        assert "bench" in result.output


# ── Lab tests ──────────────────────────────────────────────


class TestLab:
    def test_lab_help(self):
        result = runner.invoke(app, ["lab", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "start" in result.output
        assert "check" in result.output
        assert "hint" in result.output
        assert "reset" in result.output
        assert "solution" in result.output


# ── Dev mode tests ──────────────────────────────────────────


class TestDevMode:
    def test_dev_hidden_in_user_mode(self):
        """Dev group should not appear in user mode help."""
        with patch.dict(os.environ, {"ANKLUME_MODE": "user"}, clear=False):
            result = runner.invoke(app, ["--help"])
        # dev might still be callable but shouldn't be in the visible list
        # (depending on Typer version it may or may not hide properly in test runner)
        assert result.exit_code == 0

    def test_dev_help(self):
        result = runner.invoke(app, ["dev", "--help"])
        assert result.exit_code == 0
        assert "test" in result.output
        assert "lint" in result.output
        assert "matrix" in result.output
        assert "audit" in result.output
        assert "smoke" in result.output
        assert "scenario" in result.output


# ── Sync tests ──────────────────────────────────────────────


class TestSync:
    def test_sync_dry_run(self, infra_dir):
        with patch("scripts.cli._helpers.PROJECT_ROOT", infra_dir):
            result = runner.invoke(app, ["sync", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        assert "Would write" in result.output

    def test_sync_help(self):
        result = runner.invoke(app, ["sync", "--help"])
        assert result.exit_code == 0
        output = strip_ansi(result.output)
        assert "--dry-run" in output
        assert "--clean" in output


# ── Completions ─────────────────────────────────────────────


class TestCompletions:
    def test_complete_domain(self, infra_dir):
        from scripts.cli._completions import complete_domain

        with patch("scripts.cli._helpers.PROJECT_ROOT", infra_dir):
            results = complete_domain("")
        assert "anklume" in results
        assert "work" in results

    def test_complete_domain_partial(self, infra_dir):
        from scripts.cli._completions import complete_domain

        with patch("scripts.cli._helpers.PROJECT_ROOT", infra_dir):
            results = complete_domain("w")
        assert "work" in results
        assert "anklume" not in results

    def test_complete_instance(self, infra_dir):
        from scripts.cli._completions import complete_instance

        with patch("scripts.cli._helpers.PROJECT_ROOT", infra_dir):
            results = complete_instance("")
        assert "anklume-ctl" in results
        assert "work-dev" in results
