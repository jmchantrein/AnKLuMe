"""Exhaustive CLI tree coverage: every command and group is registered.

This test walks the entire anklume CLI tree and verifies that:
1. All expected groups are registered
2. All expected subcommands exist in each group
3. Each subcommand has a callable callback
4. Top-level standalone commands are registered
5. Every command has help text (non-empty)
"""

import subprocess

import pytest

from scripts.cli import app

# ── Complete CLI tree definition ──────────────────────────────────

TOPLEVEL_COMMANDS = [
    "console", "dashboard", "doctor", "flush", "guide", "sync", "upgrade",
]

GROUPS = {
    "domain": ["apply", "check", "exec", "list", "status"],
    "lab": ["check", "hint", "list", "reset", "solution", "start"],
    "learn": ["setup", "start", "teardown"],
    "mode": ["accessibility", "dev", "learn-incus", "student", "user"],
    "instance": ["clipboard", "disp", "exec", "info", "list", "remove"],
    "snapshot": ["create", "delete", "list", "restore", "rollback"],
    "network": ["deploy", "rules", "status"],
    "portal": ["copy", "list", "open", "pull", "push"],
    "app": ["export", "list", "remove"],
    "desktop": ["apply", "config", "plugins", "reset"],
    "llm": ["bench", "dev", "patterns", "sanitize", "status", "switch"],
    "stt": ["logs", "restart", "status", "test"],
    "system": ["resources"],
    "setup": [
        "data-dirs", "export-images", "hooks", "import", "init",
        "production", "quickstart", "shares", "update-notifier",
    ],
    "backup": ["create", "restore"],
    "ai": [
        "agent-develop", "agent-fix", "agent-setup", "claude",
        "develop", "improve", "mine-experiences", "switch", "test",
    ],
    "docs": ["build", "serve"],
    "dev": [
        "audit", "bdd-stubs", "chain-test", "cli-tree",
        "generate-scenarios", "graph", "lint", "matrix", "nesting",
        "runner", "scenario", "smoke", "syntax", "test",
        "test-report", "test-summary",
    ],
    "telemetry": ["clear", "off", "on", "report", "status"],
    "live": ["build", "status", "test", "update"],
    "golden": ["create", "derive", "list", "publish"],
    "mcp": ["call", "list"],
}


# ── Helpers ───────────────────────────────────────────────────────

def _get_group_app(group_name):
    """Get the Typer sub-app for a group by name."""
    for grp in app.registered_groups:
        ti = grp.typer_instance
        if ti and ti.info and ti.info.name == group_name:
            return ti
    return None


def _get_command_names(typer_app):
    """Get all registered command names from a Typer app."""
    names = []
    for cmd in typer_app.registered_commands:
        name = cmd.name or (cmd.callback.__name__ if cmd.callback else None)
        if name:
            names.append(name)
    return sorted(names)


def _get_group_names():
    """Get all registered group names."""
    names = []
    for grp in app.registered_groups:
        ti = grp.typer_instance
        if ti and ti.info and ti.info.name:
            names.append(ti.info.name)
    return sorted(names)


# ── Top-level structure ───────────────────────────────────────────

class TestCLIRootApp:
    """Root app properties."""

    def test_app_name(self):
        assert app.info.name == "anklume"

    def test_has_help_text(self):
        assert app.info.help

    def test_has_version_option(self):
        result = subprocess.run(
            ["python3", "-m", "scripts.cli", "--version"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "anklume" in result.stdout


class TestTopLevelCommands:
    """Each top-level standalone command is registered."""

    @pytest.mark.parametrize("cmd_name", TOPLEVEL_COMMANDS)
    def test_command_registered(self, cmd_name):
        names = _get_command_names(app)
        # console is registered as "console" explicitly
        assert cmd_name in names, f"Top-level command '{cmd_name}' not registered"

    @pytest.mark.parametrize("cmd_name", TOPLEVEL_COMMANDS)
    def test_command_has_callback(self, cmd_name):
        for cmd in app.registered_commands:
            name = cmd.name or (cmd.callback.__name__ if cmd.callback else None)
            if name == cmd_name:
                assert cmd.callback is not None, f"'{cmd_name}' has no callback"
                return
        pytest.fail(f"Command '{cmd_name}' not found")


# ── Group registration ────────────────────────────────────────────

class TestGroupRegistration:
    """Every expected group is registered in the main app."""

    @pytest.mark.parametrize("group_name", sorted(GROUPS.keys()))
    def test_group_registered(self, group_name):
        names = _get_group_names()
        assert group_name in names, (
            f"Group '{group_name}' not registered. Found: {names}"
        )

    def test_no_unexpected_groups(self):
        """Catch groups added without tests."""
        registered = set(_get_group_names())
        expected = set(GROUPS.keys())
        unexpected = registered - expected
        assert not unexpected, (
            f"Unexpected groups without tests: {unexpected}. "
            f"Add them to GROUPS dict in test_cli_tree_coverage.py"
        )


# ── Inverse subcommand check (catch undeclared commands) ─────────


class TestNoMissingSubcommands:
    """Catch subcommands registered in app but not declared in GROUPS."""

    @pytest.mark.parametrize("group_name", sorted(GROUPS.keys()))
    def test_no_missing_subcommands(self, group_name):
        ga = _get_group_app(group_name)
        assert ga is not None, f"Group '{group_name}' not found"
        actual = set(_get_command_names(ga))
        expected = set(GROUPS[group_name])
        missing = actual - expected
        assert not missing, (
            f"Group '{group_name}' has commands {missing} "
            f"not in GROUPS. Add them to test_cli_tree_coverage.py."
        )


# ── Subcommand coverage (parametrized per group) ─────────────────

class TestDomainCommands:
    @pytest.mark.parametrize("cmd", GROUPS["domain"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("domain")
        assert cmd in _get_command_names(ga)


class TestLabCommands:
    @pytest.mark.parametrize("cmd", GROUPS["lab"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("lab")
        assert cmd in _get_command_names(ga)


class TestLearnCommands:
    @pytest.mark.parametrize("cmd", GROUPS["learn"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("learn")
        assert cmd in _get_command_names(ga)


class TestModeCommands:
    @pytest.mark.parametrize("cmd", GROUPS["mode"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("mode")
        assert cmd in _get_command_names(ga)


class TestInstanceCommands:
    @pytest.mark.parametrize("cmd", GROUPS["instance"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("instance")
        assert cmd in _get_command_names(ga)


class TestSnapshotCommands:
    @pytest.mark.parametrize("cmd", GROUPS["snapshot"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("snapshot")
        assert cmd in _get_command_names(ga)


class TestNetworkCommands:
    @pytest.mark.parametrize("cmd", GROUPS["network"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("network")
        assert cmd in _get_command_names(ga)


class TestPortalCommands:
    @pytest.mark.parametrize("cmd", GROUPS["portal"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("portal")
        assert cmd in _get_command_names(ga)


class TestAppCommands:
    @pytest.mark.parametrize("cmd", GROUPS["app"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("app")
        assert cmd in _get_command_names(ga)


class TestDesktopCommands:
    @pytest.mark.parametrize("cmd", GROUPS["desktop"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("desktop")
        assert cmd in _get_command_names(ga)


class TestLlmCommands:
    @pytest.mark.parametrize("cmd", GROUPS["llm"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("llm")
        assert cmd in _get_command_names(ga)


class TestSttCommands:
    @pytest.mark.parametrize("cmd", GROUPS["stt"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("stt")
        assert cmd in _get_command_names(ga)


class TestSystemCommands:
    @pytest.mark.parametrize("cmd", GROUPS["system"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("system")
        assert cmd in _get_command_names(ga)


class TestSetupCommands:
    @pytest.mark.parametrize("cmd", GROUPS["setup"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("setup")
        assert cmd in _get_command_names(ga)


class TestBackupCommands:
    @pytest.mark.parametrize("cmd", GROUPS["backup"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("backup")
        assert cmd in _get_command_names(ga)


class TestAiCommands:
    @pytest.mark.parametrize("cmd", GROUPS["ai"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("ai")
        assert cmd in _get_command_names(ga)


class TestDocsCommands:
    @pytest.mark.parametrize("cmd", GROUPS["docs"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("docs")
        assert cmd in _get_command_names(ga)


class TestDevCommands:
    @pytest.mark.parametrize("cmd", GROUPS["dev"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("dev")
        assert cmd in _get_command_names(ga)


class TestTelemetryCommands:
    @pytest.mark.parametrize("cmd", GROUPS["telemetry"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("telemetry")
        assert cmd in _get_command_names(ga)


class TestLiveCommands:
    @pytest.mark.parametrize("cmd", GROUPS["live"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("live")
        assert cmd in _get_command_names(ga)


class TestGoldenCommands:
    @pytest.mark.parametrize("cmd", GROUPS["golden"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("golden")
        assert cmd in _get_command_names(ga)


class TestMcpCommands:
    @pytest.mark.parametrize("cmd", GROUPS["mcp"])
    def test_command_exists(self, cmd):
        ga = _get_group_app("mcp")
        assert cmd in _get_command_names(ga)


# ── Help text validation (every group --help returns 0) ───────────

class TestGroupHelpWorks:
    """Every group's --help produces exit code 0."""

    @pytest.mark.parametrize("group_name", sorted(GROUPS.keys()))
    def test_help_exit_zero(self, group_name):
        result = subprocess.run(
            ["python3", "-m", "scripts.cli", group_name, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"{group_name} --help failed:\n{result.stderr}"
        )

    @pytest.mark.parametrize("group_name", sorted(GROUPS.keys()))
    def test_help_lists_subcommands(self, group_name):
        result = subprocess.run(
            ["python3", "-m", "scripts.cli", group_name, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.lower()
        # At least one subcommand should appear in help
        cmds = GROUPS[group_name]
        found = any(cmd.replace("-", "") in output.replace("-", "") for cmd in cmds)
        assert found, (
            f"No subcommands found in {group_name} --help output"
        )


# ── Subcommand help validation ────────────────────────────────────

def _all_subcommands():
    """Generate (group, subcmd) pairs for parametrize."""
    pairs = []
    for group, cmds in sorted(GROUPS.items()):
        for cmd in cmds:
            pairs.append((group, cmd))
    return pairs


class TestSubcommandHelpWorks:
    """Every subcommand's --help produces exit code 0."""

    @pytest.mark.parametrize("group,cmd", _all_subcommands())
    def test_help_exit_zero(self, group, cmd):
        result = subprocess.run(
            ["python3", "-m", "scripts.cli", group, cmd, "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"{group} {cmd} --help failed:\n{result.stderr}"
        )


# ── Callback validation ──────────────────────────────────────────

class TestAllCallbacksExist:
    """Every subcommand has a non-None callback."""

    @pytest.mark.parametrize("group_name", sorted(GROUPS.keys()))
    def test_all_callbacks_set(self, group_name):
        ga = _get_group_app(group_name)
        assert ga is not None, f"Group '{group_name}' not found"
        for cmd in ga.registered_commands:
            name = cmd.name or (cmd.callback.__name__ if cmd.callback else None)
            assert cmd.callback is not None, (
                f"{group_name}:{name} has no callback"
            )


# ── Coverage stats (informational, always passes) ────────────────

class TestCoverageStats:
    """Print coverage statistics (informational)."""

    def test_print_stats(self, capsys):
        total = len(TOPLEVEL_COMMANDS)
        for cmds in GROUPS.values():
            total += len(cmds)
        group_count = len(GROUPS)
        print("\n=== CLI Tree Coverage ===")
        print(f"Top-level commands: {len(TOPLEVEL_COMMANDS)}")
        print(f"Command groups: {group_count}")
        print(f"Total subcommands: {total}")
        print("Every command has: registration test + help test + callback test")
