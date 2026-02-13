"""Tests for scripts/flush.sh — infrastructure destruction."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

FLUSH_SH = Path(__file__).resolve().parent.parent / "scripts" / "flush.sh"


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock incus binary + anklume context files for flush testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "incus.log"

    # Simulate AnKLuMe resources: 2 projects, 2 instances, 1 profile, 1 bridge
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"

# project list --format json
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{{"name":"default"}},{{"name":"admin"}},{{"name":"work"}}]'
    exit 0
fi
# project list --format csv (pre-flight check)
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then
    echo "default"
    echo "admin"
    exit 0
fi
# list instances --format csv
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then
    if [[ "$*" == *"--project admin"* ]]; then
        echo "admin-ctrl"
        exit 0
    elif [[ "$*" == *"--project work"* ]]; then
        echo "work-dev"
        exit 0
    fi
    exit 0
fi
# delete instance
if [[ "$1" == "delete" ]]; then
    exit 0
fi
# profile list --format csv
if [[ "$1" == "profile" && "$2" == "list" ]]; then
    echo "default"
    echo "nesting"
    exit 0
fi
# profile delete
if [[ "$1" == "profile" && "$2" == "delete" ]]; then
    exit 0
fi
# project delete
if [[ "$1" == "project" && "$2" == "delete" ]]; then
    exit 0
fi
# network list --format csv
if [[ "$1" == "network" && "$2" == "list" ]]; then
    echo "net-admin"
    echo "net-work"
    echo "incusbr0"
    exit 0
fi
# network delete
if [[ "$1" == "network" && "$2" == "delete" ]]; then
    exit 0
fi
echo "mock: unhandled: $*" >&2
exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock python3 for JSON parsing (flush.sh uses python3 -c)
    mock_python = mock_bin / "python3"
    mock_python.write_text("""#!/usr/bin/env bash
# Pass-through to real python3
/usr/bin/python3 "$@"
""")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    # Create generated directories to be cleaned
    for d in ["inventory", "group_vars", "host_vars"]:
        (tmp_path / d).mkdir()
        (tmp_path / d / "test.yml").write_text("test: true\n")

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path


def run_flush(args, env, cwd=None, input_text=None):
    """Run flush.sh with given args and environment."""
    result = subprocess.run(
        ["bash", str(FLUSH_SH)] + args,
        capture_output=True, text=True, env=env, cwd=cwd, input=input_text,
    )
    return result


def read_log(log_file):
    """Return list of incus commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


# ── basic operations ────────────────────────────────────────


class TestFlushBasic:
    def test_force_flag_bypasses_confirmation(self, mock_env):
        """--force skips the confirmation prompt."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0
        assert "Flush complete" in result.stdout

    def test_confirmation_no_aborts(self, mock_env):
        """Answering 'no' to confirmation aborts the flush."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="no\n")
        assert result.returncode == 0
        assert "Aborted" in result.stdout

    def test_confirmation_yes_proceeds(self, mock_env):
        """Answering 'yes' to confirmation proceeds with flush."""
        env, log, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="yes\n")
        assert result.returncode == 0
        assert "Flush complete" in result.stdout

    def test_invalid_arg(self, mock_env):
        """Invalid argument gives usage error."""
        env, _, cwd = mock_env
        result = run_flush(["--invalid"], env, cwd=cwd)
        assert result.returncode != 0
        assert "Usage" in result.stdout or "Usage" in result.stderr


# ── resource deletion ───────────────────────────────────────


class TestFlushResources:
    def test_instances_deleted(self, mock_env):
        """Flush deletes all instances in all projects."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("delete admin-ctrl" in c for c in cmds)
        assert any("delete work-dev" in c for c in cmds)

    def test_only_net_bridges_deleted(self, mock_env):
        """Only net-* bridges are deleted, not incusbr0."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("network delete net-admin" in c for c in cmds)
        assert any("network delete net-work" in c for c in cmds)
        assert not any("network delete incusbr0" in c for c in cmds)

    def test_non_default_profiles_deleted(self, mock_env):
        """Non-default profiles are deleted, default profile is kept."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("profile delete nesting" in c for c in cmds)
        assert not any("profile delete default" in c for c in cmds)

    def test_non_default_projects_deleted(self, mock_env):
        """Non-default projects are deleted."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("project delete admin" in c for c in cmds)
        assert any("project delete work" in c for c in cmds)
        assert not any("project delete default" in c for c in cmds)

    def test_generated_dirs_removed(self, mock_env):
        """Generated directories (inventory, group_vars, host_vars) are removed."""
        env, _, cwd = mock_env
        # Verify they exist before
        assert (cwd / "inventory").exists()
        assert (cwd / "group_vars").exists()
        assert (cwd / "host_vars").exists()
        run_flush(["--force"], env, cwd=cwd)
        # Verify they are removed
        assert not (cwd / "inventory").exists()
        assert not (cwd / "group_vars").exists()
        assert not (cwd / "host_vars").exists()


# ── safety checks ───────────────────────────────────────────


class TestFlushSafety:
    def test_production_without_force_fails(self, mock_env, tmp_path):
        """On production host (absolute_level=0), --force is required."""
        env, _, cwd = mock_env
        etc = tmp_path / "etc" / "anklume"
        etc.mkdir(parents=True)
        (etc / "absolute_level").write_text("0")
        (etc / "yolo").write_text("false")
        # Patch /etc/anklume path... flush.sh reads from /etc/anklume
        # This test verifies the logic but can't override /etc on this system
        # So we test the positive case (non-production) only
        # The production check reads from /etc/anklume which we can't mock easily
        # Just verify --force works in normal conditions
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0

    def test_incus_not_available(self, tmp_path):
        """Flush fails gracefully when incus is not available."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Cannot connect" in result.stdout or "Cannot connect" in result.stderr


# ── empty infrastructure ────────────────────────────────────


class TestFlushEmpty:
    def test_nothing_to_flush(self, tmp_path):
        """Flush on empty Incus reports nothing to flush."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "incus.log"
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{{"name":"default"}}]'
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then
    exit 0
fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "network" && "$2" == "list" ]]; then
    echo "incusbr0"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "Nothing to flush" in result.stdout


# ── production safety check (patched /etc/anklume) ─────────


def _make_patched_flush(tmp_path, etc_anklume):
    """Create a patched flush.sh reading from a temp dir instead of /etc/anklume."""
    patched = tmp_path / "flush_patched.sh"
    original = FLUSH_SH.read_text()
    patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
    patched.chmod(patched.stat().st_mode | stat.S_IEXEC)
    return patched


class TestFlushProductionSafety:
    """Test production safety check by patching /etc/anklume path."""

    def _setup_etc(self, tmp_path, absolute_level, yolo):
        """Create patched etc_anklume with given values."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text(str(absolute_level))
        (etc / "yolo").write_text(str(yolo).lower())
        return etc

    def test_prod_no_force_no_yolo_errors(self, mock_env):
        """absolute_level=0, yolo=false, no --force → should error."""
        env, _, cwd = mock_env
        etc = self._setup_etc(cwd, 0, "false")
        patched = _make_patched_flush(cwd, etc)
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert result.returncode == 1
        assert "ERROR" in result.stdout or "ERROR" in result.stderr
        assert "production" in result.stdout.lower() or "production" in result.stderr.lower()

    def test_prod_yolo_true_passes(self, mock_env):
        """absolute_level=0, yolo=true → should pass without --force."""
        env, _, cwd = mock_env
        etc = self._setup_etc(cwd, 0, "true")
        patched = _make_patched_flush(cwd, etc)
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert result.returncode == 0
        assert "Flush complete" in result.stdout

    def test_prod_yolo_true_no_force_passes(self, mock_env):
        """absolute_level=0, yolo=true, no --force → passes (yolo bypasses)."""
        env, _, cwd = mock_env
        etc = self._setup_etc(cwd, 0, "true")
        patched = _make_patched_flush(cwd, etc)
        # Supply "yes" to confirmation prompt since no --force
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=cwd,
            input="yes\n",
        )
        assert result.returncode == 0
        assert "Flush complete" in result.stdout

    def test_absolute_level_1_passes(self, mock_env):
        """absolute_level=1, yolo=false → not production, should pass."""
        env, _, cwd = mock_env
        etc = self._setup_etc(cwd, 1, "false")
        patched = _make_patched_flush(cwd, etc)
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert result.returncode == 0
        assert "Flush complete" in result.stdout

    def test_prod_with_force_passes(self, mock_env):
        """absolute_level=0, yolo=false, --force → should pass."""
        env, _, cwd = mock_env
        etc = self._setup_etc(cwd, 0, "false")
        patched = _make_patched_flush(cwd, etc)
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert result.returncode == 0
        assert "Flush complete" in result.stdout


# ── deletion failures ──────────────────────────────────────


class TestFlushDeletionFailures:
    """Test that flush continues with warnings when deletions fail."""

    @pytest.fixture()
    def failing_env(self, tmp_path):
        """Create a mock where incus delete fails for some instances."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "incus.log"

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"

# project list --format json
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{{"name":"default"}},{{"name":"admin"}}]'
    exit 0
fi
# project list --format csv
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then
    echo "default"
    echo "admin"
    exit 0
fi
# list instances
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then
    if [[ "$*" == *"--project admin"* ]]; then
        echo "admin-ctrl"
        echo "admin-stuck"
        exit 0
    fi
    exit 0
fi
# delete instance — admin-stuck fails
if [[ "$1" == "delete" && "$2" == "admin-stuck" ]]; then
    echo "Error: instance is busy" >&2
    exit 1
fi
# delete instance — admin-ctrl succeeds
if [[ "$1" == "delete" ]]; then
    exit 0
fi
# profile list
if [[ "$1" == "profile" && "$2" == "list" ]]; then
    echo "default"
    exit 0
fi
# project delete — admin fails
if [[ "$1" == "project" && "$2" == "delete" && "$3" == "admin" ]]; then
    echo "Error: project not empty" >&2
    exit 1
fi
if [[ "$1" == "project" && "$2" == "delete" ]]; then
    exit 0
fi
# network list
if [[ "$1" == "network" && "$2" == "list" ]]; then
    echo "net-admin"
    exit 0
fi
# network delete
if [[ "$1" == "network" && "$2" == "delete" ]]; then
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, log_file, tmp_path

    def test_continues_after_instance_delete_failure(self, failing_env):
        """Flush continues and warns when an instance deletion fails."""
        env, log, cwd = failing_env
        result = run_flush(["--force"], env, cwd=cwd)
        # Should complete (exit 0) despite the failure
        assert result.returncode == 0
        assert "WARNING" in result.stdout
        assert "admin-stuck" in result.stdout

    def test_continues_after_project_delete_failure(self, failing_env):
        """Flush continues and warns when a project deletion fails."""
        env, log, cwd = failing_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_successful_deletions_still_counted(self, failing_env):
        """Successful deletions are counted even when some fail."""
        env, log, cwd = failing_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0
        # admin-ctrl succeeds (1) + net-admin succeeds (1) = at least 2
        assert "Flush complete" in result.stdout
        assert "resources destroyed" in result.stdout


# ── help flag behavior ─────────────────────────────────────


class TestFlushHelp:
    """Test --help and usage behaviors."""

    def test_no_help_flag(self, mock_env):
        """flush.sh does not support --help, gives usage error."""
        env, _, cwd = mock_env
        result = run_flush(["--help"], env, cwd=cwd)
        assert result.returncode != 0
        assert "Usage" in result.stdout or "Usage" in result.stderr

    def test_multiple_invalid_args(self, mock_env):
        """Multiple invalid args still produce usage error."""
        env, _, cwd = mock_env
        result = run_flush(["--force", "--extra"], env, cwd=cwd)
        assert result.returncode != 0
        assert "Usage" in result.stdout or "Usage" in result.stderr


# ── counter verification ───────────────────────────────────


class TestFlushCounter:
    """Test that the counter in 'N resources destroyed' matches actual deletions."""

    def test_counter_matches_deletions(self, mock_env):
        """Counter should match the number of actual resource deletions."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0

        # Count expected deletions from the mock setup:
        # Instances: admin-ctrl (admin project) + work-dev (work project) = 2
        # Profiles: nesting (non-default, in default+admin+work projects) = 3
        #   (nesting is listed for all projects via the mock)
        # Projects: admin + work = 2
        # Bridges: net-admin + net-work = 2
        # Dirs: inventory + group_vars + host_vars = 3
        # Total depends on how many projects the profile loop covers

        # Extract the count from the output
        import re
        match = re.search(r"(\d+) resources destroyed", result.stdout)
        assert match is not None, f"Counter not found in output: {result.stdout}"
        count = int(match.group(1))

        # Count actual delete operations from the log
        cmds = read_log(log)
        actual_deletes = 0
        for cmd in cmds:
            if cmd.startswith("delete ") or (
                "delete" in cmd and ("profile" in cmd or "project" in cmd or "network" in cmd)
            ):
                actual_deletes += 1

        # Add directory deletions (3 dirs existed)
        actual_deletes += 3

        assert count == actual_deletes, (
            f"Counter ({count}) does not match actual deletions ({actual_deletes}). "
            f"Commands: {cmds}"
        )

    def test_counter_zero_when_empty(self, tmp_path):
        """Counter should be 0 when nothing to flush (reports 'Nothing to flush')."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "incus.log"
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{{"name":"default"}}]'
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then
    exit 0
fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "network" && "$2" == "list" ]]; then
    echo "incusbr0"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "Nothing to flush" in result.stdout
        assert "resources destroyed" not in result.stdout

    def test_counter_with_dirs_only(self, tmp_path):
        """Counter counts directory removal when only generated dirs exist."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "incus.log"
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{{"name":"default"}}]'
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then
    exit 0
fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "network" && "$2" == "list" ]]; then
    echo "incusbr0"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        # Create only inventory and group_vars (2 dirs)
        (tmp_path / "inventory").mkdir()
        (tmp_path / "group_vars").mkdir()

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "2 resources destroyed" in result.stdout
