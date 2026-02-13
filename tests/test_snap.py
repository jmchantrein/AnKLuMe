"""Tests for scripts/snap.sh — snapshot management."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

SNAP_SH = Path(__file__).resolve().parent.parent / "scripts" / "snap.sh"

# Fake Incus JSON output: two instances across two projects
FAKE_INCUS_LIST = json.dumps([
    {"name": "admin-ansible", "project": "admin", "status": "Running"},
    {"name": "dev-workspace", "project": "work", "status": "Running"},
])


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock incus binary that logs calls and returns fake data."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "incus.log"

    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default,YES,YES,YES,YES,YES,YES,Default,0"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--all-projects"* ]]; then
    echo '{FAKE_INCUS_LIST}'
    exit 0
fi
if [[ "$1" == "snapshot" ]]; then
    exit 0
fi
echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file


def run_snap(args, env, input_text=None):
    """Run snap.sh with given args and environment."""
    result = subprocess.run(
        ["bash", str(SNAP_SH)] + args,
        capture_output=True, text=True, env=env, input=input_text,
    )
    return result


def read_log(log_file):
    """Return list of incus commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


# ── create ───────────────────────────────────────────────────


class TestCreate:
    def test_create_with_name(self, mock_env):
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create admin-ansible my-snap --project admin" in c for c in cmds)

    def test_create_auto_name(self, mock_env):
        env, log = mock_env
        result = run_snap(["create", "admin-ansible"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create admin-ansible snap-" in c for c in cmds)

    def test_create_unknown_instance(self, mock_env):
        env, _ = mock_env
        result = run_snap(["create", "nonexistent", "s1"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_create_missing_args(self, mock_env):
        env, _ = mock_env
        result = run_snap(["create"], env)
        assert result.returncode != 0


# ── restore ──────────────────────────────────────────────────


class TestRestore:
    def test_restore(self, mock_env):
        env, log = mock_env
        result = run_snap(["restore", "dev-workspace", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore dev-workspace my-snap --project work" in c for c in cmds)

    def test_restore_missing_snap_name(self, mock_env):
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible"], env)
        assert result.returncode != 0

    def test_self_restore_requires_confirmation(self, mock_env):
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "my-snap"], env, input_text="no\n")
        assert result.returncode != 0
        assert "WARNING" in result.stdout or "WARNING" in result.stderr

    def test_self_restore_with_force(self, mock_env):
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "--force", "self", "my-snap"], env)
        assert result.returncode == 0


# ── list ─────────────────────────────────────────────────────


class TestList:
    def test_list_instance(self, mock_env):
        env, log = mock_env
        result = run_snap(["list", "admin-ansible"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot list admin-ansible" in c for c in cmds)

    def test_list_all(self, mock_env):
        env, log = mock_env
        result = run_snap(["list"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("admin-ansible" in c for c in cmds)
        assert any("dev-workspace" in c for c in cmds)


# ── delete ───────────────────────────────────────────────────


class TestDelete:
    def test_delete(self, mock_env):
        env, log = mock_env
        result = run_snap(["delete", "admin-ansible", "my-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot delete admin-ansible my-snap --project admin" in c for c in cmds)


# ── self detection ───────────────────────────────────────────


class TestSelf:
    def test_self_resolves_hostname(self, mock_env):
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["create", "self", "test-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create dev-workspace test-snap --project work" in c for c in cmds)


# ── usage ────────────────────────────────────────────────────


class TestUsage:
    def test_help(self, mock_env):
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_command(self, mock_env):
        env, _ = mock_env
        result = run_snap(["bogus"], env)
        assert result.returncode != 0

    def test_no_args_shows_help(self, mock_env):
        env, _ = mock_env
        result = run_snap([], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout


# ── edge cases ──────────────────────────────────────────────


class TestEdgeCases:
    def test_snapshot_name_with_dots_and_underscores(self, mock_env):
        """Snapshot names with dots/underscores are accepted."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "snap-2026.02.13_backup"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snap-2026.02.13_backup" in c for c in cmds)

    def test_delete_missing_snap_name(self, mock_env):
        """Delete without snapshot name is an error."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible"], env)
        assert result.returncode != 0

    def test_self_unknown_hostname(self, mock_env):
        """Self with unknown HOSTNAME gives an error."""
        env, _ = mock_env
        env["HOSTNAME"] = "nonexistent-machine"
        result = run_snap(["create", "self", "snap1"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_list_unknown_instance(self, mock_env):
        """Listing snapshots for an unknown instance gives an error."""
        env, _ = mock_env
        result = run_snap(["list", "nonexistent"], env)
        assert result.returncode != 0

    def test_restore_unknown_instance(self, mock_env):
        """Restoring unknown instance gives an error."""
        env, _ = mock_env
        result = run_snap(["restore", "nonexistent", "snap1"], env)
        assert result.returncode != 0

    def test_delete_unknown_instance(self, mock_env):
        """Deleting snapshot of unknown instance gives an error."""
        env, _ = mock_env
        result = run_snap(["delete", "nonexistent", "snap1"], env)
        assert result.returncode != 0

    def test_incus_not_available(self, tmp_path):
        """Script fails gracefully when incus binary is not found."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        # Symlink bash so subprocess can run, but incus is missing
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_snap(["create", "test", "snap1"], env)
        assert result.returncode != 0


# ── list empty ──────────────────────────────────────────


class TestSnapListEmpty:
    """Test list subcommand when domain has no snapshots."""

    def test_list_instance_no_snapshots(self, mock_env):
        """List for a valid instance with no snapshots exits 0."""
        env, log = mock_env
        # The mock incus returns exit 0 for snapshot commands,
        # simulating an empty snapshot list (no output).
        result = run_snap(["list", "admin-ansible"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot list admin-ansible" in c for c in cmds)

    def test_list_instance_output_contains_header(self, mock_env):
        """List for a valid instance outputs the instance name in header."""
        env, _ = mock_env
        result = run_snap(["list", "dev-workspace"], env)
        assert result.returncode == 0
        assert "dev-workspace" in result.stdout


# ── restore with confirmation ───────────────────────────


class TestSnapRestoreConfirm:
    """Test restore with user input 'yes' → restore executes."""

    def test_self_restore_confirm_yes(self, mock_env):
        """Typing 'yes' at the self-restore prompt proceeds with restore."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(
            ["restore", "self", "my-snap"], env, input_text="yes\n",
        )
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot restore admin-ansible my-snap --project admin" in c
            for c in cmds
        )

    def test_self_restore_confirm_shows_warning(self, mock_env):
        """Restore self shows WARNING before asking for confirmation."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(
            ["restore", "self", "my-snap"], env, input_text="yes\n",
        )
        assert "WARNING" in result.stdout


# ── restore decline ─────────────────────────────────────


class TestSnapRestoreDecline:
    """Test restore with user input 'no' → restore aborted."""

    def test_self_restore_decline_no(self, mock_env):
        """Typing 'no' at the self-restore prompt aborts."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(
            ["restore", "self", "my-snap"], env, input_text="no\n",
        )
        assert result.returncode != 0
        # The actual snapshot restore command should NOT appear in the log
        cmds = read_log(log)
        assert not any(
            "snapshot restore admin-ansible my-snap" in c for c in cmds
        )

    def test_self_restore_decline_shows_aborted(self, mock_env):
        """Declining self-restore prints 'Aborted'."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(
            ["restore", "self", "my-snap"], env, input_text="no\n",
        )
        assert "Aborted" in result.stderr or "Aborted" in result.stdout

    def test_self_restore_decline_random_input(self, mock_env):
        """Any input other than 'yes' aborts the self-restore."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(
            ["restore", "self", "my-snap"], env, input_text="maybe\n",
        )
        assert result.returncode != 0


# ── argument validation ─────────────────────────────────────


class TestSnapInvalidArgs:
    """Test error handling for invalid arguments."""

    def test_missing_snapshot_name_for_restore(self, mock_env):
        """restore without snapshot name → error."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible"], env)
        assert result.returncode != 0
        assert "Usage" in result.stderr

    def test_missing_snapshot_name_for_delete(self, mock_env):
        """delete without snapshot name → error."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible"], env)
        assert result.returncode != 0
        assert "Usage" in result.stderr

    def test_unknown_subcommand(self, mock_env):
        """Unknown subcommand → error with hint."""
        env, _ = mock_env
        result = run_snap(["banana"], env)
        assert result.returncode != 0
        assert "Unknown command" in result.stderr

    def test_no_args_shows_usage(self, mock_env):
        """No arguments → shows usage (exit 0)."""
        env, _ = mock_env
        result = run_snap([], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout


class TestSnapProjectResolution:
    """Test instance-to-project resolution logic."""

    def test_instance_found_in_non_default_project(self, mock_env):
        """Instance dev-workspace found in 'work' project → correct --project flag."""
        env, log = mock_env
        result = run_snap(["create", "dev-workspace"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot create dev-workspace" in c and "--project work" in c
            for c in cmds
        )

    def test_instance_not_found_gives_error(self, mock_env):
        """Instance not in any project → clear error message."""
        env, _ = mock_env
        result = run_snap(["create", "nonexistent-instance"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_self_resolves_to_hostname(self, mock_env):
        """'self' keyword resolves to HOSTNAME env var."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["create", "self", "test-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot create admin-ansible test-snap" in c
            for c in cmds
        )

    def test_self_delete_resolves_hostname(self, mock_env):
        """'self' keyword works with delete subcommand."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["delete", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot delete dev-workspace snap1 --project work" in c
            for c in cmds
        )

    def test_self_list_resolves_hostname(self, mock_env):
        """'self' keyword works with list subcommand."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["list", "self"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("admin-ansible" in c for c in cmds)


# ── help flag variants ───────────────────────────────────────


class TestSnapHelpVariants:
    """Test different ways to invoke help."""

    def test_dash_h(self, mock_env):
        """-h shows usage."""
        env, _ = mock_env
        result = run_snap(["-h"], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_double_dash_help(self, mock_env):
        """--help shows usage."""
        env, _ = mock_env
        result = run_snap(["--help"], env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_lists_all_commands(self, mock_env):
        """Help output lists all subcommands."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        for cmd in ["create", "restore", "list", "delete"]:
            assert cmd in result.stdout


# ── auto-generated snapshot name ─────────────────────────────


class TestSnapAutoName:
    """Test auto-generated snapshot name format."""

    def test_auto_name_format(self, mock_env):
        """Auto-generated name starts with 'snap-' and has date pattern."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        # Find the snapshot create command
        snap_cmds = [c for c in cmds if "snapshot create admin-ansible" in c]
        assert len(snap_cmds) == 1
        # Name should be snap-YYYYMMDD-HHMMSS
        import re
        assert re.search(r"snap-\d{8}-\d{6}", snap_cmds[0])


# ── non-self restore (no warning) ────────────────────────────


class TestSnapNonSelfRestore:
    """Test that non-self restore doesn't show self-restore warning."""

    def test_non_self_restore_no_warning(self, mock_env):
        """Restoring a different instance doesn't show WARNING."""
        env, log = mock_env
        env["HOSTNAME"] = "other-machine"
        result = run_snap(["restore", "admin-ansible", "snap1"], env)
        assert result.returncode == 0
        # No self-restore warning
        assert "WARNING" not in result.stdout
        assert "terminate" not in result.stdout.lower()

    def test_non_self_restore_no_confirmation(self, mock_env):
        """Restoring a different instance doesn't need confirmation."""
        env, log = mock_env
        env["HOSTNAME"] = "other-machine"
        result = run_snap(["restore", "dev-workspace", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore dev-workspace snap1" in c for c in cmds)


# ── create output messages ───────────────────────────────────


class TestSnapCreateOutput:
    """Test output messages during snapshot creation."""

    def test_create_shows_instance_name(self, mock_env):
        """Create output includes the instance name."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "mysnap"], env)
        assert "admin-ansible" in result.stdout

    def test_create_shows_snapshot_name(self, mock_env):
        """Create output includes the snapshot name."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "mysnap"], env)
        assert "mysnap" in result.stdout

    def test_create_shows_project(self, mock_env):
        """Create output includes the resolved project."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "mysnap"], env)
        assert "admin" in result.stdout


# ── script structure ─────────────────────────────────────────


class TestScriptStructure:
    """Tests for script file properties and structure."""

    def test_script_exists(self):
        """snap.sh exists at the expected path."""
        assert SNAP_SH.exists()

    def test_script_is_file(self):
        """snap.sh is a regular file, not a directory."""
        assert SNAP_SH.is_file()

    def test_script_has_bash_shebang(self):
        """snap.sh starts with a bash shebang line."""
        content = SNAP_SH.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_script_has_set_euo_pipefail(self):
        """snap.sh uses strict error handling."""
        content = SNAP_SH.read_text()
        assert "set -euo pipefail" in content

    def test_script_defines_die_function(self):
        """snap.sh defines a die() error function."""
        content = SNAP_SH.read_text()
        assert "die()" in content

    def test_script_defines_check_incus(self):
        """snap.sh defines a check_incus() function."""
        content = SNAP_SH.read_text()
        assert "check_incus()" in content

    def test_script_defines_resolve_instance(self):
        """snap.sh defines a resolve_instance() function."""
        content = SNAP_SH.read_text()
        assert "resolve_instance()" in content

    def test_script_defines_find_project(self):
        """snap.sh defines a find_project() function."""
        content = SNAP_SH.read_text()
        assert "find_project()" in content

    def test_script_defines_default_snap_name(self):
        """snap.sh defines a default_snap_name() function."""
        content = SNAP_SH.read_text()
        assert "default_snap_name()" in content

    def test_script_defines_all_cmd_functions(self):
        """snap.sh defines cmd_create, cmd_restore, cmd_list, cmd_delete."""
        content = SNAP_SH.read_text()
        for fn in ["cmd_create", "cmd_restore", "cmd_list", "cmd_delete"]:
            assert f"{fn}()" in content

    def test_script_defines_usage_function(self):
        """snap.sh defines a usage() function."""
        content = SNAP_SH.read_text()
        assert "usage()" in content

    def test_script_has_case_statement(self):
        """snap.sh dispatches commands via case statement."""
        content = SNAP_SH.read_text()
        assert 'case "$1" in' in content

    def test_script_is_not_empty(self):
        """snap.sh has meaningful content (more than 50 lines)."""
        content = SNAP_SH.read_text()
        lines = content.splitlines()
        assert len(lines) > 50


# ── die() error function ─────────────────────────────────────


class TestDieFunction:
    """Tests for the die() error function behavior."""

    def test_error_prefix_on_unknown_command(self, mock_env):
        """Unknown command error has 'ERROR:' prefix."""
        env, _ = mock_env
        result = run_snap(["nonexistent_cmd"], env)
        assert result.returncode != 0
        assert "ERROR:" in result.stderr

    def test_error_to_stderr(self, mock_env):
        """Error messages from die() go to stderr, not stdout."""
        env, _ = mock_env
        result = run_snap(["nonexistent_cmd"], env)
        assert "ERROR:" in result.stderr
        assert "ERROR:" not in result.stdout

    def test_create_missing_args_error_prefix(self, mock_env):
        """Create with missing args shows ERROR: prefix."""
        env, _ = mock_env
        result = run_snap(["create"], env)
        assert "ERROR:" in result.stderr

    def test_restore_missing_args_error_prefix(self, mock_env):
        """Restore with missing args shows ERROR: prefix."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible"], env)
        assert "ERROR:" in result.stderr

    def test_delete_missing_args_error_prefix(self, mock_env):
        """Delete with missing args shows ERROR: prefix."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible"], env)
        assert "ERROR:" in result.stderr

    def test_not_found_error_prefix(self, mock_env):
        """Instance not found shows ERROR: prefix."""
        env, _ = mock_env
        result = run_snap(["create", "ghost-machine", "s1"], env)
        assert "ERROR:" in result.stderr


# ── check_incus error message ─────────────────────────────────


class TestCheckIncusMessage:
    """Tests for the check_incus() error message."""

    def test_incus_failure_mentions_daemon(self, tmp_path):
        """When incus fails, error mentions 'Incus daemon'."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        # incus that always fails
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        # need python3 accessible
        import shutil
        py3 = shutil.which("python3")
        if py3:
            (mock_bin / "python3").symlink_to(py3)
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)
        # need date for default_snap_name
        date_path = shutil.which("date")
        if date_path:
            (mock_bin / "date").symlink_to(date_path)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_snap(["create", "test", "snap1"], env)
        assert result.returncode != 0
        assert "Incus daemon" in result.stderr or "Cannot connect" in result.stderr

    def test_incus_failure_mentions_socket_access(self, tmp_path):
        """When incus fails, error mentions 'socket access'."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        import shutil
        py3 = shutil.which("python3")
        if py3:
            (mock_bin / "python3").symlink_to(py3)
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)
        date_path = shutil.which("date")
        if date_path:
            (mock_bin / "date").symlink_to(date_path)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_snap(["create", "test", "snap1"], env)
        assert result.returncode != 0
        assert "socket access" in result.stderr


# ── usage / help content ─────────────────────────────────────


class TestUsageContent:
    """Tests for detailed help output content."""

    def test_help_contains_examples(self, mock_env):
        """Help output contains an 'Examples' section."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "Examples" in result.stdout

    def test_help_mentions_self_keyword(self, mock_env):
        """Help output explains the 'self' keyword."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "self" in result.stdout

    def test_help_mentions_default_snap_name_format(self, mock_env):
        """Help output mentions the default snapshot name format."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "snap-YYYYMMDD-HHMMSS" in result.stdout

    def test_help_describes_create_command(self, mock_env):
        """Help output has a description line for 'create'."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "create" in result.stdout
        assert "Create a snapshot" in result.stdout

    def test_help_describes_restore_command(self, mock_env):
        """Help output has a description line for 'restore'."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "restore" in result.stdout
        assert "Restore a snapshot" in result.stdout

    def test_help_describes_list_command(self, mock_env):
        """Help output has a description line for 'list'."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "List snapshots" in result.stdout

    def test_help_describes_delete_command(self, mock_env):
        """Help output has a description line for 'delete'."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "Delete a snapshot" in result.stdout

    def test_help_describes_help_command(self, mock_env):
        """Help output has a description line for 'help'."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "Show this help" in result.stdout

    def test_help_mentions_force_flag(self, mock_env):
        """Help output mentions --force for restore."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "--force" in result.stdout

    def test_help_example_create_admin(self, mock_env):
        """Help output has example: snap.sh create admin-ansible."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "snap.sh create admin-ansible" in result.stdout

    def test_help_example_create_self(self, mock_env):
        """Help output has example: snap.sh create self my-checkpoint."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "snap.sh create self my-checkpoint" in result.stdout

    def test_help_example_restore(self, mock_env):
        """Help output has example: snap.sh restore admin-ansible snap-..."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "snap.sh restore admin-ansible" in result.stdout

    def test_help_example_list(self, mock_env):
        """Help output has example: snap.sh list."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "snap.sh list\n" in result.stdout or "snap.sh list" in result.stdout

    def test_help_example_list_self(self, mock_env):
        """Help output has example: snap.sh list self."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "snap.sh list self" in result.stdout


# ── unknown command details ──────────────────────────────────


class TestUnknownCommandDetails:
    """Tests for the unknown command error message details."""

    def test_unknown_command_includes_bad_name(self, mock_env):
        """Unknown command error includes the bad command name."""
        env, _ = mock_env
        result = run_snap(["foobar"], env)
        assert "foobar" in result.stderr

    def test_unknown_command_suggests_help(self, mock_env):
        """Unknown command error suggests running help."""
        env, _ = mock_env
        result = run_snap(["foobar"], env)
        assert "help" in result.stderr

    def test_unknown_command_different_names(self, mock_env):
        """Different unknown commands show their own name."""
        env, _ = mock_env
        for cmd in ["snapshot", "snap", "rollback", "undo", "purge"]:
            result = run_snap([cmd], env)
            assert result.returncode != 0
            assert cmd in result.stderr


# ── create output messages ───────────────────────────────────


class TestCreateOutputDetails:
    """Detailed tests for create command output messages."""

    def test_create_shows_creating_message(self, mock_env):
        """Create output starts with 'Creating snapshot' message."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "snap1"], env)
        assert "Creating snapshot" in result.stdout

    def test_create_shows_done_with_slash(self, mock_env):
        """Create output ends with 'Done: instance/snap' format."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "snap1"], env)
        assert "Done: admin-ansible/snap1" in result.stdout

    def test_create_shows_project_in_parentheses(self, mock_env):
        """Create output includes '(project: <name>)' format."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "snap1"], env)
        assert "(project: admin)" in result.stdout

    def test_create_for_work_project(self, mock_env):
        """Create output shows correct project for work domain."""
        env, _ = mock_env
        result = run_snap(["create", "dev-workspace", "snap1"], env)
        assert "(project: work)" in result.stdout
        assert "Done: dev-workspace/snap1" in result.stdout

    def test_create_usage_error_message(self, mock_env):
        """Create missing args shows specific usage message."""
        env, _ = mock_env
        result = run_snap(["create"], env)
        assert "Usage: snap.sh create" in result.stderr

    def test_create_auto_name_shown_in_done(self, mock_env):
        """Auto-generated snap name appears in the Done message."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible"], env)
        assert "Done: admin-ansible/snap-" in result.stdout


# ── restore output messages ──────────────────────────────────


class TestRestoreOutputDetails:
    """Detailed tests for restore command output messages."""

    def test_restore_shows_restoring_message(self, mock_env):
        """Restore output shows 'Restoring ... to snapshot' message."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible", "snap1"], env)
        assert "Restoring admin-ansible to snapshot" in result.stdout

    def test_restore_shows_snap_name_in_message(self, mock_env):
        """Restore output includes the snapshot name in single quotes."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible", "snap1"], env)
        assert "'snap1'" in result.stdout

    def test_restore_shows_project(self, mock_env):
        """Restore output includes project name."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible", "snap1"], env)
        assert "(project: admin)" in result.stdout

    def test_restore_shows_done(self, mock_env):
        """Restore output ends with 'Done.'."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible", "snap1"], env)
        assert "Done." in result.stdout

    def test_restore_usage_error_message(self, mock_env):
        """Restore missing args shows specific usage message."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible"], env)
        assert "Usage: snap.sh restore" in result.stderr

    def test_restore_usage_mentions_force(self, mock_env):
        """Restore usage error mentions --force."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible"], env)
        assert "--force" in result.stderr


# ── delete output messages ───────────────────────────────────


class TestDeleteOutputDetails:
    """Detailed tests for delete command output messages."""

    def test_delete_shows_deleting_message(self, mock_env):
        """Delete output shows 'Deleting snapshot' message."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible", "snap1"], env)
        assert "Deleting snapshot" in result.stdout

    def test_delete_shows_snap_name_in_message(self, mock_env):
        """Delete output includes the snapshot name in single quotes."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible", "snap1"], env)
        assert "'snap1'" in result.stdout

    def test_delete_shows_project(self, mock_env):
        """Delete output includes project name."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible", "snap1"], env)
        assert "(project: admin)" in result.stdout

    def test_delete_shows_done(self, mock_env):
        """Delete output ends with 'Done.'."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible", "snap1"], env)
        assert "Done." in result.stdout

    def test_delete_usage_error_message(self, mock_env):
        """Delete missing args shows specific usage message."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible"], env)
        assert "Usage: snap.sh delete" in result.stderr

    def test_delete_for_work_project(self, mock_env):
        """Delete uses correct project for work domain."""
        env, _ = mock_env
        result = run_snap(["delete", "dev-workspace", "snap1"], env)
        assert "(project: work)" in result.stdout


# ── force flag behavior ──────────────────────────────────────


class TestForceFlag:
    """Tests for the --force flag in restore."""

    def test_force_skips_warning_entirely(self, mock_env):
        """Force flag suppresses self-restore WARNING output."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "--force", "self", "snap1"], env)
        assert result.returncode == 0
        assert "WARNING" not in result.stdout

    def test_force_skips_confirmation_prompt(self, mock_env):
        """Force flag does not ask for confirmation."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "--force", "self", "snap1"], env)
        assert result.returncode == 0
        assert "Type 'yes'" not in result.stdout

    def test_force_with_non_self_is_harmless(self, mock_env):
        """Force flag on non-self restore is accepted and works."""
        env, log = mock_env
        env["HOSTNAME"] = "other-machine"
        result = run_snap(["restore", "--force", "admin-ansible", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore admin-ansible snap1" in c for c in cmds)

    def test_force_after_instance_is_not_recognized(self, mock_env):
        """--force must come before the instance name to be recognized."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        # When --force is after instance, it is treated as part of args
        # and instance becomes "self", snap becomes "--force", which fails
        result = run_snap(["restore", "self", "--force", "snap1"], env)
        # The script should either fail or not recognize --force as a flag
        # Since "self" is instance, "--force" becomes snap name, "snap1" is extra
        # The mock incus will try to restore with snap name "--force"
        # At minimum, check it doesn't skip the warning
        if result.returncode == 0:
            # If it succeeds, verify WARNING was shown (--force not parsed)
            assert "WARNING" in result.stdout or "terminate" in result.stdout
        # else: it fails, which is also acceptable

    def test_force_resolves_self_correctly(self, mock_env):
        """Force + self resolves self to hostname."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["restore", "--force", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot restore dev-workspace snap1 --project work" in c
            for c in cmds
        )


# ── self-restore warning details ─────────────────────────────


class TestSelfRestoreWarningDetails:
    """Detailed tests for the self-restore warning message content."""

    def test_warning_mentions_terminate(self, mock_env):
        """Self-restore warning mentions session termination."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="no\n")
        assert "terminate" in result.stdout.lower()

    def test_warning_mentions_reconnect(self, mock_env):
        """Self-restore warning mentions reconnecting."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="no\n")
        assert "reconnect" in result.stdout.lower()

    def test_warning_only_yes_is_accepted(self, mock_env):
        """Only exact 'yes' input passes the self-restore confirmation."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        # 'yes' succeeds
        r_yes = run_snap(["restore", "self", "snap1"], env, input_text="yes\n")
        assert r_yes.returncode == 0
        # anything else fails
        r_no = run_snap(["restore", "self", "snap1"], env, input_text="no\n")
        assert r_no.returncode != 0

    def test_eof_input_aborts(self, mock_env):
        """Self-restore with EOF (no input) aborts."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="")
        assert result.returncode != 0

    def test_empty_line_aborts(self, mock_env):
        """Self-restore with just Enter (empty line) aborts."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="\n")
        assert result.returncode != 0

    def test_yes_uppercase_aborts(self, mock_env):
        """Self-restore with 'YES' (uppercase) aborts — must be lowercase."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="YES\n")
        assert result.returncode != 0

    def test_yes_with_spaces_succeeds(self, mock_env):
        """Self-restore with ' yes ' succeeds — bash read strips whitespace."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text=" yes \n")
        # bash read strips leading/trailing whitespace by default
        assert result.returncode == 0

    def test_y_alone_aborts(self, mock_env):
        """Self-restore with just 'y' (not 'yes') aborts."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="y\n")
        assert result.returncode != 0

    def test_self_restore_yes_does_not_show_aborted(self, mock_env):
        """Self-restore confirmed with 'yes' does not show 'Aborted'."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "snap1"], env, input_text="yes\n")
        assert result.returncode == 0
        assert "Aborted" not in result.stdout
        assert "Aborted" not in result.stderr


# ── list command details ─────────────────────────────────────


class TestListDetails:
    """Detailed tests for the list command."""

    def test_list_single_shows_header(self, mock_env):
        """List for single instance shows 'Snapshots for' header."""
        env, _ = mock_env
        result = run_snap(["list", "admin-ansible"], env)
        assert "Snapshots for admin-ansible" in result.stdout

    def test_list_single_shows_project_in_header(self, mock_env):
        """List for single instance includes project in header."""
        env, _ = mock_env
        result = run_snap(["list", "admin-ansible"], env)
        assert "(project: admin)" in result.stdout

    def test_list_single_uses_format_table(self, mock_env):
        """List for single instance passes --format table to incus."""
        env, log = mock_env
        run_snap(["list", "admin-ansible"], env)
        cmds = read_log(log)
        assert any("--format table" in c for c in cmds)

    def test_list_all_shows_separator_per_instance(self, mock_env):
        """List all shows '===' separator for each instance."""
        env, _ = mock_env
        result = run_snap(["list"], env)
        assert "===" in result.stdout

    def test_list_all_shows_admin_ansible_separator(self, mock_env):
        """List all includes admin-ansible in separator."""
        env, _ = mock_env
        result = run_snap(["list"], env)
        assert "=== admin-ansible" in result.stdout

    def test_list_all_shows_dev_workspace_separator(self, mock_env):
        """List all includes dev-workspace in separator."""
        env, _ = mock_env
        result = run_snap(["list"], env)
        assert "=== dev-workspace" in result.stdout

    def test_list_all_uses_json_for_discovery(self, mock_env):
        """List all queries incus with --format json for instance discovery."""
        env, log = mock_env
        run_snap(["list"], env)
        cmds = read_log(log)
        assert any("--all-projects" in c and "--format json" in c for c in cmds)

    def test_list_work_project(self, mock_env):
        """List for dev-workspace shows work project."""
        env, _ = mock_env
        result = run_snap(["list", "dev-workspace"], env)
        assert "(project: work)" in result.stdout

    def test_list_uses_project_flag(self, mock_env):
        """List for a specific instance uses --project flag."""
        env, log = mock_env
        run_snap(["list", "admin-ansible"], env)
        cmds = read_log(log)
        assert any("--project admin" in c for c in cmds)


# ── incus command structure ──────────────────────────────────


class TestIncusCommandStructure:
    """Tests verifying the exact incus commands issued."""

    def test_create_issues_snapshot_create(self, mock_env):
        """Create issues 'incus snapshot create' command."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        assert any(c.startswith("snapshot create") for c in cmds)

    def test_restore_issues_snapshot_restore(self, mock_env):
        """Restore issues 'incus snapshot restore' command."""
        env, log = mock_env
        run_snap(["restore", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        assert any(c.startswith("snapshot restore") for c in cmds)

    def test_delete_issues_snapshot_delete(self, mock_env):
        """Delete issues 'incus snapshot delete' command."""
        env, log = mock_env
        run_snap(["delete", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        assert any(c.startswith("snapshot delete") for c in cmds)

    def test_list_single_issues_snapshot_list(self, mock_env):
        """List single instance issues 'incus snapshot list' command."""
        env, log = mock_env
        run_snap(["list", "admin-ansible"], env)
        cmds = read_log(log)
        assert any(c.startswith("snapshot list") for c in cmds)

    def test_check_incus_issues_project_list(self, mock_env):
        """Pre-flight check issues 'incus project list' command."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        assert any("project list" in c for c in cmds)

    def test_find_project_issues_list_all_projects(self, mock_env):
        """Project resolution issues 'incus list --all-projects'."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        assert any("list --all-projects --format json" in c for c in cmds)

    def test_create_passes_project_flag(self, mock_env):
        """Create passes --project to incus."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        snap_cmds = [c for c in cmds if "snapshot create" in c]
        assert len(snap_cmds) == 1
        assert "--project admin" in snap_cmds[0]

    def test_restore_passes_project_flag(self, mock_env):
        """Restore passes --project to incus."""
        env, log = mock_env
        run_snap(["restore", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        snap_cmds = [c for c in cmds if "snapshot restore" in c]
        assert len(snap_cmds) == 1
        assert "--project admin" in snap_cmds[0]

    def test_delete_passes_project_flag(self, mock_env):
        """Delete passes --project to incus."""
        env, log = mock_env
        run_snap(["delete", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        snap_cmds = [c for c in cmds if "snapshot delete" in c]
        assert len(snap_cmds) == 1
        assert "--project admin" in snap_cmds[0]


# ── snapshot naming conventions ──────────────────────────────


class TestSnapshotNaming:
    """Tests for snapshot name handling and conventions."""

    def test_name_with_only_numbers(self, mock_env):
        """Numeric-only snapshot names are accepted."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "12345"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("12345" in c for c in cmds)

    def test_name_with_hyphens(self, mock_env):
        """Snapshot names with hyphens are accepted."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "pre-update-snap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("pre-update-snap" in c for c in cmds)

    def test_name_with_underscores(self, mock_env):
        """Snapshot names with underscores are accepted."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "before_upgrade"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("before_upgrade" in c for c in cmds)

    def test_name_with_dots(self, mock_env):
        """Snapshot names with dots are accepted."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "v1.2.3"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("v1.2.3" in c for c in cmds)

    def test_name_preserved_in_restore(self, mock_env):
        """Snapshot name is passed verbatim to incus restore."""
        env, log = mock_env
        run_snap(["restore", "admin-ansible", "my-exact-snap-name"], env)
        cmds = read_log(log)
        assert any("my-exact-snap-name" in c for c in cmds)

    def test_name_preserved_in_delete(self, mock_env):
        """Snapshot name is passed verbatim to incus delete."""
        env, log = mock_env
        run_snap(["delete", "admin-ansible", "my-exact-snap-name"], env)
        cmds = read_log(log)
        assert any("my-exact-snap-name" in c for c in cmds)

    def test_auto_name_starts_with_snap_prefix(self, mock_env):
        """Auto-generated name starts with 'snap-'."""
        env, log = mock_env
        run_snap(["create", "admin-ansible"], env)
        cmds = read_log(log)
        snap_cmds = [c for c in cmds if "snapshot create admin-ansible" in c]
        assert len(snap_cmds) == 1
        # Log format: "snapshot create admin-ansible snap-YYYYMMDD-HHMMSS --project admin"
        # Split and find the token after the instance name
        parts = snap_cmds[0].split()
        # parts: [snapshot, create, admin-ansible, snap-..., --project, admin]
        snap_name = parts[3]
        assert snap_name.startswith("snap-")

    def test_auto_name_has_date_component(self, mock_env):
        """Auto-generated name contains 8-digit date component."""
        import re
        env, log = mock_env
        run_snap(["create", "admin-ansible"], env)
        cmds = read_log(log)
        snap_cmds = [c for c in cmds if "snapshot create admin-ansible" in c]
        assert re.search(r"snap-\d{8}", snap_cmds[0])

    def test_auto_name_has_time_component(self, mock_env):
        """Auto-generated name contains 6-digit time component."""
        import re
        env, log = mock_env
        run_snap(["create", "admin-ansible"], env)
        cmds = read_log(log)
        snap_cmds = [c for c in cmds if "snapshot create admin-ansible" in c]
        assert re.search(r"snap-\d{8}-\d{6}", snap_cmds[0])


# ── self keyword with all commands ───────────────────────────


class TestSelfKeywordAllCommands:
    """Tests for the 'self' keyword across all subcommands."""

    def test_self_create_with_auto_name(self, mock_env):
        """Self + create + auto name works."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["create", "self"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot create admin-ansible snap-" in c
            and "--project admin" in c
            for c in cmds
        )

    def test_self_create_with_explicit_name(self, mock_env):
        """Self + create + explicit name works."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["create", "self", "mysnap"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot create dev-workspace mysnap --project work" in c
            for c in cmds
        )

    def test_self_restore_resolves(self, mock_env):
        """Self + restore resolves HOSTNAME."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["restore", "--force", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore dev-workspace snap1" in c for c in cmds)

    def test_self_delete_resolves(self, mock_env):
        """Self + delete resolves HOSTNAME."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["delete", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any(
            "snapshot delete admin-ansible snap1 --project admin" in c
            for c in cmds
        )

    def test_self_list_resolves(self, mock_env):
        """Self + list resolves HOSTNAME."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["list", "self"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot list dev-workspace" in c for c in cmds)

    def test_self_not_found_for_each_command(self, mock_env):
        """Self with unknown HOSTNAME errors for every command."""
        env, _ = mock_env
        env["HOSTNAME"] = "nonexistent"
        for cmd_args in [
            ["create", "self", "snap1"],
            ["restore", "self", "snap1"],
            ["delete", "self", "snap1"],
            ["list", "self"],
        ]:
            result = run_snap(cmd_args, env)
            assert result.returncode != 0, f"Expected failure for: {cmd_args}"
            assert "not found" in result.stderr.lower(), (
                f"Expected 'not found' in stderr for: {cmd_args}"
            )


# ── project resolution correctness ──────────────────────────


class TestProjectResolutionCorrectness:
    """Tests verifying project resolution produces correct --project value."""

    def test_admin_instance_gets_admin_project(self, mock_env):
        """admin-ansible resolves to --project admin."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        assert any("--project admin" in c and "admin-ansible" in c for c in cmds)

    def test_work_instance_gets_work_project(self, mock_env):
        """dev-workspace resolves to --project work."""
        env, log = mock_env
        run_snap(["create", "dev-workspace", "s1"], env)
        cmds = read_log(log)
        assert any("--project work" in c and "dev-workspace" in c for c in cmds)

    def test_resolution_consistent_across_create_delete(self, mock_env):
        """Same instance resolves to same project for create and delete."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        run_snap(["delete", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        create_cmds = [c for c in cmds if "snapshot create" in c]
        delete_cmds = [c for c in cmds if "snapshot delete" in c]
        assert "--project admin" in create_cmds[0]
        assert "--project admin" in delete_cmds[0]

    def test_resolution_consistent_across_create_restore(self, mock_env):
        """Same instance resolves to same project for create and restore."""
        env, log = mock_env
        run_snap(["create", "dev-workspace", "s1"], env)
        run_snap(["restore", "dev-workspace", "s1"], env)
        cmds = read_log(log)
        create_cmds = [c for c in cmds if "snapshot create" in c]
        restore_cmds = [c for c in cmds if "snapshot restore" in c]
        assert "--project work" in create_cmds[0]
        assert "--project work" in restore_cmds[0]

    def test_not_found_error_includes_instance_name(self, mock_env):
        """Instance not-found error includes the instance name."""
        env, _ = mock_env
        result = run_snap(["create", "this-does-not-exist", "s1"], env)
        assert result.returncode != 0
        assert "this-does-not-exist" in result.stderr


# ── exit codes ───────────────────────────────────────────────


class TestExitCodes:
    """Tests verifying correct exit codes for various scenarios."""

    def test_successful_create_exits_0(self, mock_env):
        """Successful create exits with code 0."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "s1"], env)
        assert result.returncode == 0

    def test_successful_restore_exits_0(self, mock_env):
        """Successful restore exits with code 0."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible", "s1"], env)
        assert result.returncode == 0

    def test_successful_delete_exits_0(self, mock_env):
        """Successful delete exits with code 0."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible", "s1"], env)
        assert result.returncode == 0

    def test_successful_list_exits_0(self, mock_env):
        """Successful list exits with code 0."""
        env, _ = mock_env
        result = run_snap(["list", "admin-ansible"], env)
        assert result.returncode == 0

    def test_successful_list_all_exits_0(self, mock_env):
        """Successful list all exits with code 0."""
        env, _ = mock_env
        result = run_snap(["list"], env)
        assert result.returncode == 0

    def test_successful_help_exits_0(self, mock_env):
        """Help exits with code 0."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert result.returncode == 0

    def test_unknown_command_exits_nonzero(self, mock_env):
        """Unknown command exits with non-zero code."""
        env, _ = mock_env
        result = run_snap(["invalid"], env)
        assert result.returncode != 0

    def test_missing_instance_exits_nonzero(self, mock_env):
        """Missing instance for create exits with non-zero code."""
        env, _ = mock_env
        result = run_snap(["create"], env)
        assert result.returncode != 0

    def test_not_found_instance_exits_nonzero(self, mock_env):
        """Instance not found exits with non-zero code."""
        env, _ = mock_env
        result = run_snap(["create", "ghost", "s1"], env)
        assert result.returncode != 0

    def test_aborted_restore_exits_nonzero(self, mock_env):
        """Aborted self-restore exits with non-zero code."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "s1"], env, input_text="no\n")
        assert result.returncode != 0

    def test_no_args_exits_0(self, mock_env):
        """No arguments exits with code 0 (shows usage)."""
        env, _ = mock_env
        result = run_snap([], env)
        assert result.returncode == 0


# ── self detection edge cases ────────────────────────────────


class TestSelfDetectionEdgeCases:
    """Edge cases for the 'self' keyword resolution."""

    def test_self_is_case_sensitive(self, mock_env):
        """'Self' (capitalized) is NOT treated as the self keyword."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["create", "Self", "snap1"], env)
        # "Self" should be treated as an instance name, which won't be found
        assert result.returncode != 0

    def test_self_uppercase_is_not_keyword(self, mock_env):
        """'SELF' (all caps) is NOT treated as the self keyword."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["create", "SELF", "snap1"], env)
        assert result.returncode != 0

    def test_self_with_hostname_matching_first_instance(self, mock_env):
        """Self resolves to first instance when hostname matches."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["create", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("admin-ansible" in c and "--project admin" in c for c in cmds)

    def test_self_with_hostname_matching_second_instance(self, mock_env):
        """Self resolves to second instance when hostname matches."""
        env, log = mock_env
        env["HOSTNAME"] = "dev-workspace"
        result = run_snap(["create", "self", "snap1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("dev-workspace" in c and "--project work" in c for c in cmds)


# ── multiple instances in mock ───────────────────────────────


class TestMultipleInstances:
    """Tests verifying both mock instances are properly handled."""

    def test_create_each_instance(self, mock_env):
        """Create works for both mock instances."""
        env, log = mock_env
        r1 = run_snap(["create", "admin-ansible", "s1"], env)
        r2 = run_snap(["create", "dev-workspace", "s2"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0
        cmds = read_log(log)
        assert any("admin-ansible" in c and "snapshot create" in c for c in cmds)
        assert any("dev-workspace" in c and "snapshot create" in c for c in cmds)

    def test_delete_each_instance(self, mock_env):
        """Delete works for both mock instances."""
        env, log = mock_env
        r1 = run_snap(["delete", "admin-ansible", "s1"], env)
        r2 = run_snap(["delete", "dev-workspace", "s2"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_restore_each_instance(self, mock_env):
        """Restore works for both mock instances."""
        env, log = mock_env
        r1 = run_snap(["restore", "admin-ansible", "s1"], env)
        r2 = run_snap(["restore", "dev-workspace", "s2"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_list_each_instance(self, mock_env):
        """List works for both mock instances individually."""
        env, _ = mock_env
        r1 = run_snap(["list", "admin-ansible"], env)
        r2 = run_snap(["list", "dev-workspace"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_different_instances_different_projects(self, mock_env):
        """Different instances use their correct projects."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        run_snap(["create", "dev-workspace", "s2"], env)
        cmds = read_log(log)
        admin_cmds = [c for c in cmds if "admin-ansible" in c and "snapshot create" in c]
        work_cmds = [c for c in cmds if "dev-workspace" in c and "snapshot create" in c]
        assert "--project admin" in admin_cmds[0]
        assert "--project work" in work_cmds[0]


# ── non-self restore does not trigger safety check ───────────


class TestNonSelfNoSafetyCheck:
    """Tests that non-self restore never triggers the safety check."""

    def test_different_hostname_no_warning(self, mock_env):
        """Restoring different instance with set HOSTNAME shows no warning."""
        env, _ = mock_env
        env["HOSTNAME"] = "completely-different"
        result = run_snap(["restore", "admin-ansible", "s1"], env)
        assert result.returncode == 0
        assert "WARNING" not in result.stdout
        assert "terminate" not in result.stdout.lower()

    def test_no_hostname_restoring_named_instance(self, mock_env):
        """Restoring a named instance (not self) without HOSTNAME works."""
        env, _ = mock_env
        # HOSTNAME might be set by the OS; set it to something unrelated
        env["HOSTNAME"] = "unrelated"
        result = run_snap(["restore", "dev-workspace", "s1"], env)
        assert result.returncode == 0
        assert "WARNING" not in result.stdout

    def test_restore_other_instance_no_input_needed(self, mock_env):
        """Restoring another instance requires no stdin input."""
        env, log = mock_env
        env["HOSTNAME"] = "admin-ansible"
        # Restore dev-workspace (different from HOSTNAME)
        result = run_snap(["restore", "dev-workspace", "s1"], env)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snapshot restore dev-workspace s1" in c for c in cmds)


# ── combined workflow scenarios ──────────────────────────────


class TestWorkflowScenarios:
    """Tests for realistic multi-step workflow scenarios."""

    def test_create_then_restore(self, mock_env):
        """Create then restore the same snapshot."""
        env, log = mock_env
        r1 = run_snap(["create", "admin-ansible", "checkpoint"], env)
        assert r1.returncode == 0
        r2 = run_snap(["restore", "admin-ansible", "checkpoint"], env)
        assert r2.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create admin-ansible checkpoint" in c for c in cmds)
        assert any("snapshot restore admin-ansible checkpoint" in c for c in cmds)

    def test_create_then_delete(self, mock_env):
        """Create then delete the same snapshot."""
        env, log = mock_env
        r1 = run_snap(["create", "dev-workspace", "temp-snap"], env)
        assert r1.returncode == 0
        r2 = run_snap(["delete", "dev-workspace", "temp-snap"], env)
        assert r2.returncode == 0
        cmds = read_log(log)
        assert any("snapshot create dev-workspace temp-snap" in c for c in cmds)
        assert any("snapshot delete dev-workspace temp-snap" in c for c in cmds)

    def test_list_then_create(self, mock_env):
        """List then create — both succeed."""
        env, _ = mock_env
        r1 = run_snap(["list", "admin-ansible"], env)
        r2 = run_snap(["create", "admin-ansible", "new-snap"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_create_multiple_snapshots(self, mock_env):
        """Create multiple snapshots for same instance."""
        env, log = mock_env
        r1 = run_snap(["create", "admin-ansible", "snap-a"], env)
        r2 = run_snap(["create", "admin-ansible", "snap-b"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0
        cmds = read_log(log)
        assert any("snap-a" in c for c in cmds)
        assert any("snap-b" in c for c in cmds)


# ── stderr vs stdout separation ──────────────────────────────


class TestOutputStreams:
    """Tests verifying correct output to stdout vs stderr."""

    def test_help_to_stdout(self, mock_env):
        """Help output goes to stdout."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert "Usage" in result.stdout
        assert "Usage" not in result.stderr

    def test_unknown_command_to_stderr(self, mock_env):
        """Unknown command error goes to stderr."""
        env, _ = mock_env
        result = run_snap(["bad"], env)
        assert "ERROR:" in result.stderr

    def test_create_progress_to_stdout(self, mock_env):
        """Create progress messages go to stdout."""
        env, _ = mock_env
        result = run_snap(["create", "admin-ansible", "s1"], env)
        assert "Creating snapshot" in result.stdout
        assert "Done:" in result.stdout

    def test_restore_progress_to_stdout(self, mock_env):
        """Restore progress messages go to stdout."""
        env, _ = mock_env
        result = run_snap(["restore", "admin-ansible", "s1"], env)
        assert "Restoring" in result.stdout
        assert "Done." in result.stdout

    def test_delete_progress_to_stdout(self, mock_env):
        """Delete progress messages go to stdout."""
        env, _ = mock_env
        result = run_snap(["delete", "admin-ansible", "s1"], env)
        assert "Deleting snapshot" in result.stdout
        assert "Done." in result.stdout

    def test_aborted_message_to_stderr(self, mock_env):
        """Aborted message goes to stderr."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["restore", "self", "s1"], env, input_text="no\n")
        assert "Aborted" in result.stderr

    def test_not_found_error_to_stderr(self, mock_env):
        """Instance not found error goes to stderr."""
        env, _ = mock_env
        result = run_snap(["create", "ghost", "s1"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()
        # Ensure the error is not on stdout
        assert "not found" not in result.stdout.lower()

    def test_missing_args_to_stderr(self, mock_env):
        """Missing args usage error goes to stderr."""
        env, _ = mock_env
        result = run_snap(["create"], env)
        assert "ERROR:" in result.stderr
        assert "Usage:" in result.stderr


# ── mock fixture behavior ────────────────────────────────────


class TestMockFixtureIntegrity:
    """Tests verifying the mock fixture behaves correctly."""

    def test_log_file_created(self, mock_env):
        """Running any command creates a log file."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        assert log.exists()

    def test_log_file_accumulates(self, mock_env):
        """Multiple commands accumulate in the same log file."""
        env, log = mock_env
        run_snap(["create", "admin-ansible", "s1"], env)
        run_snap(["delete", "admin-ansible", "s1"], env)
        cmds = read_log(log)
        # At minimum: project list + list all-projects + snapshot create (x2 sequences)
        assert len(cmds) >= 4

    def test_mock_returns_both_instances(self, mock_env):
        """Mock incus returns both instances in list output."""
        env, _ = mock_env
        # Both instances should be found
        r1 = run_snap(["list", "admin-ansible"], env)
        r2 = run_snap(["list", "dev-workspace"], env)
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_mock_handles_unknown_command(self, mock_env):
        """Mock incus returns error for unhandled commands."""
        env, log = mock_env
        # The help command doesn't call incus at all,
        # so we just verify the mock doesn't interfere
        result = run_snap(["help"], env)
        assert result.returncode == 0


# ── additional edge cases ────────────────────────────────────


class TestAdditionalEdgeCases:
    """Additional edge cases not covered elsewhere."""

    def test_extra_args_after_snap_name_create(self, mock_env):
        """Extra args after snap name in create are ignored."""
        env, log = mock_env
        result = run_snap(["create", "admin-ansible", "snap1", "extra"], env)
        # The script uses $2 for snap name; extra args are silently ignored
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("snap1" in c for c in cmds)

    def test_restore_no_args(self, mock_env):
        """Restore with no args (just 'restore') errors."""
        env, _ = mock_env
        result = run_snap(["restore"], env)
        assert result.returncode != 0

    def test_delete_no_args(self, mock_env):
        """Delete with no args (just 'delete') errors."""
        env, _ = mock_env
        result = run_snap(["delete"], env)
        assert result.returncode != 0

    def test_create_does_not_prompt(self, mock_env):
        """Create never prompts for confirmation."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["create", "self", "snap1"], env)
        assert result.returncode == 0
        assert "Type 'yes'" not in result.stdout

    def test_delete_does_not_prompt(self, mock_env):
        """Delete never prompts for confirmation."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["delete", "self", "snap1"], env)
        assert result.returncode == 0
        assert "Type 'yes'" not in result.stdout

    def test_list_does_not_prompt(self, mock_env):
        """List never prompts for confirmation."""
        env, _ = mock_env
        env["HOSTNAME"] = "admin-ansible"
        result = run_snap(["list", "self"], env)
        assert result.returncode == 0
        assert "Type 'yes'" not in result.stdout

    def test_help_has_no_errors(self, mock_env):
        """Help produces no stderr output."""
        env, _ = mock_env
        result = run_snap(["help"], env)
        assert result.stderr == ""

    def test_no_args_has_no_errors(self, mock_env):
        """No args produces no stderr output."""
        env, _ = mock_env
        result = run_snap([], env)
        assert result.stderr == ""

    def test_restore_with_force_no_args(self, mock_env):
        """Restore with only --force and no instance/snap errors."""
        env, _ = mock_env
        result = run_snap(["restore", "--force"], env)
        assert result.returncode != 0
        assert "Usage" in result.stderr
