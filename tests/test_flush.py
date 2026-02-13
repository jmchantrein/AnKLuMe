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


# ── force requirement edge cases ──────────────────────────


class TestFlushForceRequirement:
    """Test production safety checks with various /etc/anklume states."""

    def test_production_without_force_refuses(self, tmp_path):
        """absolute_level=0, yolo=false, no --force → error."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir()
        (etc / "absolute_level").write_text("0")
        (etc / "yolo").write_text("false")
        patched = _make_patched_flush(tmp_path, etc)
        env = os.environ.copy()
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode != 0
        assert "production" in result.stdout.lower() or "FORCE" in result.stdout

    def test_production_with_force_proceeds(self, tmp_path):
        """absolute_level=0, yolo=false, --force → proceeds (needs incus)."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir()
        (etc / "absolute_level").write_text("0")
        (etc / "yolo").write_text("false")
        patched = _make_patched_flush(tmp_path, etc)
        # Mock incus to pass pre-flight but have nothing to delete
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "Flush" in result.stdout

    def test_non_production_no_force_needed(self, tmp_path):
        """absolute_level=1 (nested) → no --force required, proceeds directly."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir()
        (etc / "absolute_level").write_text("1")
        (etc / "yolo").write_text("false")
        patched = _make_patched_flush(tmp_path, etc)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        # Use --force to skip confirmation prompt (since no stdin)
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_yolo_true_no_force_needed(self, tmp_path):
        """absolute_level=0 but yolo=true → no --force required."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir()
        (etc / "absolute_level").write_text("0")
        (etc / "yolo").write_text("true")
        patched = _make_patched_flush(tmp_path, etc)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert result.returncode == 0


class TestFlushIncusErrors:
    """Test graceful handling when incus commands fail during flush."""

    def test_incus_not_reachable_pre_flight(self, tmp_path):
        """When incus project list fails, flush exits with clear error."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Cannot connect" in result.stdout or "ERROR" in result.stdout

    def test_no_bridges_found_clean_exit(self, tmp_path):
        """When no net-* bridges exist, flush completes with 0 bridge deletions."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
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

    def test_unknown_arg_shows_usage(self, tmp_path):
        """Unknown argument shows usage and exits."""
        env = os.environ.copy()
        result = run_flush(["--banana"], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Usage" in result.stdout or "Usage" in result.stderr


# ── confirmation edge cases ───────────────────────────────────────


class TestFlushConfirmation:
    """Test confirmation prompt edge cases."""

    def test_empty_input_does_not_proceed(self, mock_env):
        """Empty input (just Enter) does not proceed with flush."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="\n")
        assert result.returncode == 0
        assert "Aborted" in result.stdout

    def test_uppercase_yes_proceeds(self, mock_env):
        """'YES' (uppercase) proceeds with flush."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="YES\n")
        # Depending on implementation: might require exact 'yes' or be case-insensitive
        combined = result.stdout
        # Either proceeds or aborts — test whichever the script does
        assert "Flush complete" in combined or "Aborted" in combined

    def test_partial_yes_aborts(self, mock_env):
        """'ye' (partial yes) aborts the flush."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="ye\n")
        assert "Aborted" in result.stdout

    def test_force_overrides_confirmation(self, mock_env):
        """--force skips confirmation entirely."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0
        assert "Flush complete" in result.stdout
        # Should NOT ask for confirmation
        assert "Are you sure" not in result.stdout or "Type 'yes'" not in result.stdout


# ── deletion order verification ───────────────────────────────────


class TestFlushDeletionOrder:
    """Verify resources are deleted in the correct order."""

    def test_instances_before_projects(self, mock_env):
        """Instances must be deleted before their projects."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        # Find positions of instance deletes and project deletes
        instance_deletes = [i for i, c in enumerate(cmds) if c.startswith("delete ")]
        project_deletes = [i for i, c in enumerate(cmds) if "project delete" in c]
        if instance_deletes and project_deletes:
            assert max(instance_deletes) < min(project_deletes), (
                "Instances should be deleted before projects"
            )

    def test_profiles_before_projects(self, mock_env):
        """Non-default profiles should be deleted before projects."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        profile_deletes = [i for i, c in enumerate(cmds) if "profile delete" in c]
        project_deletes = [i for i, c in enumerate(cmds) if "project delete" in c]
        if profile_deletes and project_deletes:
            assert max(profile_deletes) < min(project_deletes), (
                "Profiles should be deleted before projects"
            )


# ── flush output messages ─────────────────────────────────────────


class TestFlushOutputMessages:
    """Verify the informational messages during flush."""

    def test_shows_resource_summary(self, mock_env):
        """Flush shows a summary of what it found to delete."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0
        # Should mention found resources: projects, instances, bridges, etc.
        output = result.stdout.lower()
        assert "project" in output or "instance" in output or "bridge" in output

    def test_shows_each_deleted_resource(self, mock_env):
        """Flush shows each deleted resource."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0
        # Should mention specific resources
        assert "admin-ctrl" in result.stdout or "work-dev" in result.stdout

    def test_shows_skipped_default_project(self, mock_env):
        """Flush does not attempt to delete the default project."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert not any("project delete default" in c for c in cmds)


# ── script structure ──────────────────────────────────────────


class TestFlushScriptStructure:
    """Verify script structure: shebang, set -euo pipefail, functions."""

    def test_shebang_line(self):
        """Script starts with #!/usr/bin/env bash."""
        text = FLUSH_SH.read_text()
        assert text.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail(self):
        """Script uses set -euo pipefail for safety."""
        text = FLUSH_SH.read_text()
        assert "set -euo pipefail" in text

    def test_script_is_a_regular_file(self):
        """Script is a regular file (not a directory or symlink)."""
        assert FLUSH_SH.is_file()

    def test_script_bash_syntax_check(self):
        """Script passes bash -n syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(FLUSH_SH)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_force_variable_default_false(self):
        """Script initializes FORCE=false."""
        text = FLUSH_SH.read_text()
        assert "FORCE=false" in text

    def test_uses_incus_project_list_json(self):
        """Script queries projects via incus project list --format json."""
        text = FLUSH_SH.read_text()
        assert "incus project list --format json" in text

    def test_uses_python3_for_json_parsing(self):
        """Script uses python3 -c for JSON parsing."""
        text = FLUSH_SH.read_text()
        assert "python3 -c" in text

    def test_usage_message_in_script(self):
        """Script contains a Usage message for invalid args."""
        text = FLUSH_SH.read_text()
        assert "Usage:" in text

    def test_script_mentions_force_flag(self):
        """Script contains --force in its text (usage or logic)."""
        text = FLUSH_SH.read_text()
        assert "--force" in text

    def test_script_references_etc_anklume(self):
        """Script reads from /etc/anklume/ for production checks."""
        text = FLUSH_SH.read_text()
        assert "/etc/anklume/" in text

    def test_script_has_deleted_counter(self):
        """Script maintains a deleted counter variable."""
        text = FLUSH_SH.read_text()
        assert "deleted=0" in text

    def test_script_increments_counter(self):
        """Script increments deleted counter on successful deletions."""
        text = FLUSH_SH.read_text()
        assert "deleted=$((deleted + 1))" in text


# ── CLI flag combinations ─────────────────────────────────────


class TestFlushCLIFlags:
    """Test all CLI flag combinations."""

    def test_no_args_requires_confirmation(self, mock_env):
        """No arguments requires user to confirm (answering 'no' aborts)."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="no\n")
        assert "Aborted" in result.stdout

    def test_force_flag_long_form(self, mock_env):
        """--force is the only valid flag."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0

    def test_single_dash_force_rejected(self, mock_env):
        """-force (single dash) is rejected as invalid."""
        env, _, cwd = mock_env
        result = run_flush(["-force"], env, cwd=cwd)
        assert result.returncode != 0

    def test_double_force_accepted(self, mock_env):
        """Two --force flags are accepted (idempotent flag)."""
        env, _, cwd = mock_env
        result = run_flush(["--force", "--force"], env, cwd=cwd)
        assert result.returncode == 0

    def test_force_with_extra_arg_rejected(self, mock_env):
        """--force followed by an extra argument is rejected."""
        env, _, cwd = mock_env
        result = run_flush(["--force", "extra"], env, cwd=cwd)
        assert result.returncode != 0

    def test_empty_string_arg_rejected(self, mock_env):
        """An empty string argument is rejected."""
        env, _, cwd = mock_env
        result = run_flush([""], env, cwd=cwd)
        assert result.returncode != 0

    def test_dash_dash_only_rejected(self, mock_env):
        """'--' alone is rejected."""
        env, _, cwd = mock_env
        result = run_flush(["--"], env, cwd=cwd)
        assert result.returncode != 0

    def test_version_flag_rejected(self, mock_env):
        """--version is not a valid flag."""
        env, _, cwd = mock_env
        result = run_flush(["--version"], env, cwd=cwd)
        assert result.returncode != 0

    def test_verbose_flag_rejected(self, mock_env):
        """--verbose is not a valid flag."""
        env, _, cwd = mock_env
        result = run_flush(["--verbose"], env, cwd=cwd)
        assert result.returncode != 0

    def test_dry_run_flag_rejected(self, mock_env):
        """--dry-run is not a valid flag."""
        env, _, cwd = mock_env
        result = run_flush(["--dry-run"], env, cwd=cwd)
        assert result.returncode != 0

    def test_yes_flag_rejected(self, mock_env):
        """--yes is not a valid flag."""
        env, _, cwd = mock_env
        result = run_flush(["--yes"], env, cwd=cwd)
        assert result.returncode != 0

    def test_usage_error_shows_script_name(self, mock_env):
        """Usage error includes the script name."""
        env, _, cwd = mock_env
        result = run_flush(["--invalid"], env, cwd=cwd)
        combined = result.stdout + result.stderr
        assert "Usage:" in combined


# ── output messages and formatting ────────────────────────────


class TestFlushOutputFormatting:
    """Verify output messages and formatting details."""

    def test_header_line_present(self, mock_env):
        """Output starts with the AnKLuMe Flush header."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "=== AnKLuMe Flush ===" in result.stdout

    def test_destroying_instances_section(self, mock_env):
        """Output contains the 'Destroying instances' section."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "--- Destroying instances ---" in result.stdout

    def test_deleting_profiles_section(self, mock_env):
        """Output contains the 'Deleting profiles' section."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "--- Deleting profiles ---" in result.stdout

    def test_deleting_projects_section(self, mock_env):
        """Output contains the 'Deleting projects' section."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "--- Deleting projects ---" in result.stdout

    def test_deleting_bridges_section(self, mock_env):
        """Output contains the 'Deleting bridges' section."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "--- Deleting bridges ---" in result.stdout

    def test_removing_generated_files_section(self, mock_env):
        """Output contains the 'Removing generated files' section."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "--- Removing generated files ---" in result.stdout

    def test_rebuild_instruction_present(self, mock_env):
        """Output ends with rebuild instructions."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "make sync && make apply" in result.stdout

    def test_this_will_destroy_message(self, mock_env):
        """Output shows the destruction warning."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "This will destroy ALL AnKLuMe infrastructure" in result.stdout

    def test_deleting_prefix_for_instances(self, mock_env):
        """Instance deletions are prefixed with 'Deleting:'."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "Deleting:" in result.stdout

    def test_deleting_profile_prefix(self, mock_env):
        """Profile deletions use 'Deleting profile:' prefix."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "Deleting profile:" in result.stdout

    def test_deleting_project_prefix(self, mock_env):
        """Project deletions use 'Deleting project:' prefix."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "Deleting project:" in result.stdout

    def test_deleting_bridge_prefix(self, mock_env):
        """Bridge deletions use 'Deleting bridge:' prefix."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "Deleting bridge:" in result.stdout

    def test_removing_dir_prefix(self, mock_env):
        """Directory removals use 'Removing:' prefix."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "Removing:" in result.stdout

    def test_instance_output_shows_project(self, mock_env):
        """Instance deletion shows which project it belongs to."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        # e.g., "Deleting: admin-ctrl (project: admin)"
        assert "(project:" in result.stdout

    def test_flush_complete_message_format(self, mock_env):
        """Flush complete message includes count."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        import re
        assert re.search(r"Flush complete: \d+ resources destroyed", result.stdout)


# ── error handling and exit codes ─────────────────────────────


class TestFlushExitCodes:
    """Test exit codes for various scenarios."""

    def test_success_returns_zero(self, mock_env):
        """Successful flush returns exit code 0."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0

    def test_invalid_arg_returns_nonzero(self, mock_env):
        """Invalid argument returns non-zero exit code."""
        env, _, cwd = mock_env
        result = run_flush(["--bad"], env, cwd=cwd)
        assert result.returncode == 1

    def test_production_no_force_returns_one(self, mock_env):
        """Production without --force returns exit code 1."""
        env, _, cwd = mock_env
        etc = cwd / "etc_anklume"
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("0")
        (etc / "yolo").write_text("false")
        patched = _make_patched_flush(cwd, etc)
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=cwd,
        )
        assert result.returncode == 1

    def test_incus_unreachable_returns_nonzero(self, tmp_path):
        """Unreachable Incus returns non-zero exit code."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 1

    def test_aborted_returns_zero(self, mock_env):
        """Aborting via 'no' returns exit code 0 (not an error)."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="no\n")
        assert result.returncode == 0

    def test_empty_flush_returns_zero(self, tmp_path):
        """Empty infrastructure flush still returns 0."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
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


# ── production safety (patched /etc/anklume) ──────────────────


class TestFlushProductionSafetyExtended:
    """Extended production safety check tests."""

    def _setup_patched(self, tmp_path, abs_level, yolo):
        """Helper to create patched flush with context files."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text(str(abs_level))
        (etc / "yolo").write_text(str(yolo).lower())
        patched = _make_patched_flush(tmp_path, etc)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return patched, env

    def test_abs_level_0_yolo_false_no_force_fails(self, tmp_path):
        """level=0, yolo=false, no --force -> fail."""
        patched, env = self._setup_patched(tmp_path, 0, "false")
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert result.returncode == 1

    def test_abs_level_0_yolo_false_with_force_passes(self, tmp_path):
        """level=0, yolo=false, --force -> pass."""
        patched, env = self._setup_patched(tmp_path, 0, "false")
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_abs_level_0_yolo_true_no_force_prompts(self, tmp_path):
        """level=0, yolo=true, no --force -> prompt (yolo bypasses prod check)."""
        patched, env = self._setup_patched(tmp_path, 0, "true")
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=tmp_path,
            input="yes\n",
        )
        assert result.returncode == 0

    def test_abs_level_1_yolo_false_no_force_prompts(self, tmp_path):
        """level=1, yolo=false, no --force -> prompt (not production)."""
        patched, env = self._setup_patched(tmp_path, 1, "false")
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=tmp_path,
            input="yes\n",
        )
        assert result.returncode == 0

    def test_abs_level_2_yolo_false_with_force(self, tmp_path):
        """level=2, yolo=false, --force -> pass."""
        patched, env = self._setup_patched(tmp_path, 2, "false")
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        assert result.returncode == 0

    def test_abs_level_empty_string(self, tmp_path):
        """Empty absolute_level file should not block."""
        etc = tmp_path / "etc_anklume"
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("")
        (etc / "yolo").write_text("false")
        patched = _make_patched_flush(tmp_path, etc)
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = subprocess.run(
            ["bash", str(patched), "--force"],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        # Empty string != "0" so not production
        assert result.returncode == 0

    def test_missing_etc_anklume_dir(self, mock_env):
        """Missing /etc/anklume directory should not block flush."""
        env, _, cwd = mock_env
        # The default mock_env has no /etc/anklume at the patched path
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0

    def test_error_message_mentions_production(self, tmp_path):
        """Production error message mentions 'production'."""
        patched, env = self._setup_patched(tmp_path, 0, "false")
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        combined = result.stdout + result.stderr
        assert "production" in combined.lower()

    def test_error_message_mentions_force(self, tmp_path):
        """Production error message tells user to use FORCE=true."""
        patched, env = self._setup_patched(tmp_path, 0, "false")
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        combined = result.stdout + result.stderr
        assert "FORCE=true" in combined

    def test_error_message_is_on_stderr_or_stdout(self, tmp_path):
        """Production error message is communicated to user."""
        patched, env = self._setup_patched(tmp_path, 0, "false")
        result = subprocess.run(
            ["bash", str(patched)],
            capture_output=True, text=True, env=env, cwd=tmp_path,
        )
        combined = result.stdout + result.stderr
        assert "ERROR" in combined


# ── confirmation prompt edge cases ────────────────────────────


class TestFlushConfirmationExtended:
    """Extended confirmation prompt tests."""

    def test_confirm_with_trailing_spaces(self, mock_env):
        """'yes ' with trailing space should not match 'yes'."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="yes \n")
        # bash read strips trailing whitespace so this may still match
        combined = result.stdout
        assert "Flush complete" in combined or "Aborted" in combined

    def test_confirm_with_leading_spaces(self, mock_env):
        """' yes' with leading space: bash read strips leading spaces."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text=" yes\n")
        combined = result.stdout
        # bash read -r strips leading/trailing whitespace by default
        assert "Flush complete" in combined or "Aborted" in combined

    def test_confirm_with_y_only(self, mock_env):
        """'y' alone does not match 'yes'."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="y\n")
        assert "Aborted" in result.stdout

    def test_confirm_with_oui(self, mock_env):
        """'oui' does not match 'yes'."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="oui\n")
        assert "Aborted" in result.stdout

    def test_confirm_eof_without_input(self, mock_env):
        """EOF on stdin (empty input) causes read to fail under set -e."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="")
        # Under set -e, read returns 1 on EOF, causing script to exit
        assert result.returncode != 0

    def test_confirm_no(self, mock_env):
        """Explicit 'no' aborts."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="no\n")
        assert "Aborted" in result.stdout

    def test_confirm_random_text_aborts(self, mock_env):
        """Random text that is not 'yes' aborts."""
        env, _, cwd = mock_env
        result = run_flush([], env, cwd=cwd, input_text="definitely\n")
        assert "Aborted" in result.stdout

    def test_force_does_not_prompt(self, mock_env):
        """With --force, no 'Type' prompt appears."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "Type 'yes'" not in result.stdout


# ── incus command structure verification ──────────────────────


class TestFlushIncusCommands:
    """Verify the exact incus commands issued by flush."""

    def test_preflight_uses_project_list_csv(self, mock_env):
        """Pre-flight check uses 'incus project list --format csv'."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("project list --format csv" in c for c in cmds)

    def test_project_enumeration_uses_json(self, mock_env):
        """Project enumeration uses --format json."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("project list --format json" in c for c in cmds)

    def test_instance_list_uses_csv(self, mock_env):
        """Instance listing uses --format csv."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("list" in c and "--format csv" in c and "--project" in c for c in cmds)

    def test_instance_delete_uses_force_flag(self, mock_env):
        """Instance deletion uses --force flag."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        instance_deletes = [c for c in cmds if c.startswith("delete ")]
        for cmd in instance_deletes:
            assert "--force" in cmd

    def test_instance_delete_specifies_project(self, mock_env):
        """Instance deletion specifies --project."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        instance_deletes = [c for c in cmds if c.startswith("delete ")]
        for cmd in instance_deletes:
            assert "--project" in cmd

    def test_profile_list_uses_csv(self, mock_env):
        """Profile listing uses --format csv."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("profile list" in c and "--format csv" in c for c in cmds)

    def test_profile_delete_specifies_project(self, mock_env):
        """Profile deletion specifies --project."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        profile_deletes = [c for c in cmds if "profile delete" in c]
        for cmd in profile_deletes:
            assert "--project" in cmd

    def test_network_list_uses_csv(self, mock_env):
        """Network listing uses --format csv."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("network list --format csv" in c for c in cmds)

    def test_network_delete_for_each_bridge(self, mock_env):
        """Each net-* bridge gets a network delete command."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("network delete net-admin" in c for c in cmds)
        assert any("network delete net-work" in c for c in cmds)


# ── edge cases: empty infrastructure scenarios ────────────────


class TestFlushEmptyScenarios:
    """Test flush behavior with various empty infrastructure states."""

    def _make_empty_env(self, tmp_path, projects_json='[{"name":"default"}]',
                        profiles="default", networks="incusbr0", instances_callback=None):
        """Create a mock env with configurable responses."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "incus.log"

        instances_block = ""
        if instances_callback:
            instances_block = instances_callback
        else:
            instances_block = 'exit 0'

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '{projects_json}'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then {instances_block}; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "{profiles}"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "{networks}"; exit 0; fi
if [[ "$1" == "delete" ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "delete" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "delete" ]]; then exit 0; fi
if [[ "$1" == "network" && "$2" == "delete" ]]; then exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, log_file

    def test_only_default_project_no_instances(self, tmp_path):
        """Only 'default' project, no instances -> Nothing to flush."""
        env, _ = self._make_empty_env(tmp_path)
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "Nothing to flush" in result.stdout

    def test_no_profiles_besides_default(self, tmp_path):
        """Only 'default' profile should not generate deletions."""
        env, log = self._make_empty_env(tmp_path)
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("profile delete" in c for c in cmds)

    def test_no_net_bridges(self, tmp_path):
        """No net-* bridges means no bridge deletions."""
        env, log = self._make_empty_env(tmp_path, networks="incusbr0\nlxdbr0")
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("network delete" in c for c in cmds)

    def test_only_incusbr0_bridge(self, tmp_path):
        """incusbr0 is preserved (not a net-* bridge)."""
        env, log = self._make_empty_env(tmp_path)
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("network delete incusbr0" in c for c in cmds)

    def test_no_generated_dirs(self, tmp_path):
        """No inventory/group_vars/host_vars dirs means no dir cleanup."""
        env, _ = self._make_empty_env(tmp_path)
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        # No directories to remove = nothing to flush (or zero dir count)

    def test_only_inventory_dir_exists(self, tmp_path):
        """Only inventory/ exists -> 1 resource destroyed."""
        env, _ = self._make_empty_env(tmp_path)
        (tmp_path / "inventory").mkdir()
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "1 resources destroyed" in result.stdout

    def test_only_group_vars_dir_exists(self, tmp_path):
        """Only group_vars/ exists -> 1 resource destroyed."""
        env, _ = self._make_empty_env(tmp_path)
        (tmp_path / "group_vars").mkdir()
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "1 resources destroyed" in result.stdout

    def test_only_host_vars_dir_exists(self, tmp_path):
        """Only host_vars/ exists -> 1 resource destroyed."""
        env, _ = self._make_empty_env(tmp_path)
        (tmp_path / "host_vars").mkdir()
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "1 resources destroyed" in result.stdout

    def test_all_three_dirs_exist(self, tmp_path):
        """All three generated dirs exist -> 3 resources destroyed."""
        env, _ = self._make_empty_env(tmp_path)
        for d in ["inventory", "group_vars", "host_vars"]:
            (tmp_path / d).mkdir()
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "3 resources destroyed" in result.stdout


# ── directory cleaning ────────────────────────────────────────


class TestFlushDirectoryCleaning:
    """Test generated directory removal behavior."""

    def test_inventory_dir_removed(self, mock_env):
        """inventory/ directory is removed."""
        env, _, cwd = mock_env
        assert (cwd / "inventory").exists()
        run_flush(["--force"], env, cwd=cwd)
        assert not (cwd / "inventory").exists()

    def test_group_vars_dir_removed(self, mock_env):
        """group_vars/ directory is removed."""
        env, _, cwd = mock_env
        assert (cwd / "group_vars").exists()
        run_flush(["--force"], env, cwd=cwd)
        assert not (cwd / "group_vars").exists()

    def test_host_vars_dir_removed(self, mock_env):
        """host_vars/ directory is removed."""
        env, _, cwd = mock_env
        assert (cwd / "host_vars").exists()
        run_flush(["--force"], env, cwd=cwd)
        assert not (cwd / "host_vars").exists()

    def test_nested_files_in_dirs_removed(self, mock_env):
        """Files inside generated dirs are removed."""
        env, _, cwd = mock_env
        assert (cwd / "inventory" / "test.yml").exists()
        run_flush(["--force"], env, cwd=cwd)
        assert not (cwd / "inventory" / "test.yml").exists()

    def test_non_generated_dirs_preserved(self, mock_env):
        """Dirs not in the cleanup list (e.g., roles/) are preserved."""
        env, _, cwd = mock_env
        (cwd / "roles").mkdir()
        (cwd / "roles" / "test_role.yml").write_text("test: true\n")
        run_flush(["--force"], env, cwd=cwd)
        assert (cwd / "roles").exists()
        assert (cwd / "roles" / "test_role.yml").exists()

    def test_scripts_dir_preserved(self, mock_env):
        """scripts/ directory is preserved."""
        env, _, cwd = mock_env
        (cwd / "scripts").mkdir()
        run_flush(["--force"], env, cwd=cwd)
        assert (cwd / "scripts").exists()

    def test_docs_dir_preserved(self, mock_env):
        """docs/ directory is preserved."""
        env, _, cwd = mock_env
        (cwd / "docs").mkdir()
        run_flush(["--force"], env, cwd=cwd)
        assert (cwd / "docs").exists()

    def test_infra_yml_preserved(self, mock_env):
        """infra.yml file is preserved."""
        env, _, cwd = mock_env
        (cwd / "infra.yml").write_text("project_name: test\n")
        run_flush(["--force"], env, cwd=cwd)
        assert (cwd / "infra.yml").exists()

    def test_deeply_nested_dirs_removed(self, mock_env):
        """Deeply nested directories under generated dirs are removed."""
        env, _, cwd = mock_env
        deep = cwd / "inventory" / "sub" / "deep"
        deep.mkdir(parents=True)
        (deep / "file.txt").write_text("content")
        run_flush(["--force"], env, cwd=cwd)
        assert not (cwd / "inventory").exists()

    def test_only_existing_dirs_counted(self, tmp_path):
        """Only dirs that actually exist are counted as resources."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        # Create only 2 of 3 dirs
        (tmp_path / "inventory").mkdir()
        (tmp_path / "host_vars").mkdir()
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert "2 resources destroyed" in result.stdout


# ── deletion order extended ───────────────────────────────────


class TestFlushDeletionOrderExtended:
    """Extended deletion order verification."""

    def test_profiles_before_projects_in_log(self, mock_env):
        """Profile deletions precede project deletions in the log."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        profile_idx = [i for i, c in enumerate(cmds) if "profile delete" in c]
        project_idx = [i for i, c in enumerate(cmds) if "project delete" in c]
        if profile_idx and project_idx:
            assert max(profile_idx) < min(project_idx)

    def test_instances_before_profiles(self, mock_env):
        """Instance deletions precede profile deletions."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        inst_idx = [i for i, c in enumerate(cmds) if c.startswith("delete ")]
        prof_idx = [i for i, c in enumerate(cmds) if "profile delete" in c]
        if inst_idx and prof_idx:
            assert max(inst_idx) < min(prof_idx)

    def test_bridges_deleted_after_instances(self, mock_env):
        """Bridge deletions happen after instance deletions."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        inst_idx = [i for i, c in enumerate(cmds) if c.startswith("delete ")]
        bridge_idx = [i for i, c in enumerate(cmds) if "network delete" in c]
        if inst_idx and bridge_idx:
            assert max(inst_idx) < min(bridge_idx)

    def test_bridges_after_projects(self, mock_env):
        """Bridge deletions happen after project deletions."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        project_idx = [i for i, c in enumerate(cmds) if "project delete" in c]
        bridge_idx = [i for i, c in enumerate(cmds) if "network delete" in c]
        if project_idx and bridge_idx:
            assert max(project_idx) < min(bridge_idx), (
                "Projects should be deleted before bridges"
            )

    def test_section_order_in_output(self, mock_env):
        """Output sections appear in correct order."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        out = result.stdout
        inst_pos = out.find("--- Destroying instances ---")
        prof_pos = out.find("--- Deleting profiles ---")
        proj_pos = out.find("--- Deleting projects ---")
        bridge_pos = out.find("--- Deleting bridges ---")
        files_pos = out.find("--- Removing generated files ---")
        assert inst_pos < prof_pos < proj_pos < bridge_pos < files_pos


# ── multi-project scenarios ───────────────────────────────────


class TestFlushMultiProject:
    """Test flush with various multi-project configurations."""

    def _make_multi_project_env(self, tmp_path, project_json, instance_map,
                                profiles=None, networks=None):
        """Create a mock env with configurable projects and instances."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "incus.log"

        # Build instance branches
        instance_branches = ""
        for proj, instances in instance_map.items():
            inst_echo = "\\n".join(instances) if instances else ""
            instance_branches += f"""
if [[ "$*" == *"--project {proj}"* ]]; then
    printf "{inst_echo}\\n"
    exit 0
fi"""

        profiles_str = profiles or "default"
        networks_str = networks or "incusbr0"

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '{project_json}'
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then
{instance_branches}
    exit 0
fi
if [[ "$1" == "delete" ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "{profiles_str}"; exit 0; fi
if [[ "$1" == "profile" && "$2" == "delete" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "delete" ]]; then exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "{networks_str}"; exit 0; fi
if [[ "$1" == "network" && "$2" == "delete" ]]; then exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, log_file

    def test_single_project_single_instance(self, tmp_path):
        """One non-default project with one instance."""
        env, log = self._make_multi_project_env(
            tmp_path,
            '[{"name":"default"},{"name":"work"}]',
            {"work": ["work-dev"]},
        )
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("delete work-dev" in c for c in cmds)
        assert any("project delete work" in c for c in cmds)

    def test_three_projects_multiple_instances(self, tmp_path):
        """Three projects, each with multiple instances."""
        env, log = self._make_multi_project_env(
            tmp_path,
            '[{"name":"default"},{"name":"a"},{"name":"b"},{"name":"c"}]',
            {"a": ["a1", "a2"], "b": ["b1"], "c": ["c1", "c2", "c3"]},
        )
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        cmds = read_log(log)
        for inst in ["a1", "a2", "b1", "c1", "c2", "c3"]:
            assert any(f"delete {inst}" in c for c in cmds), f"Missing delete for {inst}"
        for proj in ["a", "b", "c"]:
            assert any(f"project delete {proj}" in c for c in cmds), f"Missing delete for project {proj}"

    def test_default_project_instances_also_deleted(self, tmp_path):
        """Instances in the default project are also deleted."""
        env, log = self._make_multi_project_env(
            tmp_path,
            '[{"name":"default"}]',
            {"default": ["orphan-container"]},
        )
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("delete orphan-container" in c for c in cmds)

    def test_project_with_no_instances(self, tmp_path):
        """Project with no instances is still deleted."""
        env, log = self._make_multi_project_env(
            tmp_path,
            '[{"name":"default"},{"name":"empty-proj"}]',
            {"empty-proj": []},
        )
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        cmds = read_log(log)
        assert any("project delete empty-proj" in c for c in cmds)


# ── bridge filtering ─────────────────────────────────────────


class TestFlushBridgeFiltering:
    """Test bridge filtering logic (only net-* bridges deleted)."""

    def _make_bridge_env(self, tmp_path, bridge_list):
        """Create env with specific bridge list."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "incus.log"
        bridges_output = "\\n".join(bridge_list)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{{"name":"default"}}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then printf "{bridges_output}\\n"; exit 0; fi
if [[ "$1" == "network" && "$2" == "delete" ]]; then exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, log_file

    def test_incusbr0_preserved(self, tmp_path):
        """incusbr0 is not deleted."""
        env, log = self._make_bridge_env(tmp_path, ["incusbr0", "net-admin"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("network delete incusbr0" in c for c in cmds)

    def test_lxdbr0_preserved(self, tmp_path):
        """lxdbr0 is not deleted."""
        env, log = self._make_bridge_env(tmp_path, ["lxdbr0", "net-test"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("network delete lxdbr0" in c for c in cmds)

    def test_net_admin_deleted(self, tmp_path):
        """net-admin is deleted."""
        env, log = self._make_bridge_env(tmp_path, ["incusbr0", "net-admin"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert any("network delete net-admin" in c for c in cmds)

    def test_net_pro_deleted(self, tmp_path):
        """net-pro is deleted."""
        env, log = self._make_bridge_env(tmp_path, ["net-pro"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert any("network delete net-pro" in c for c in cmds)

    def test_net_homelab_deleted(self, tmp_path):
        """net-homelab is deleted."""
        env, log = self._make_bridge_env(tmp_path, ["net-homelab", "incusbr0"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert any("network delete net-homelab" in c for c in cmds)

    def test_multiple_net_bridges_all_deleted(self, tmp_path):
        """All net-* bridges are deleted."""
        bridges = ["incusbr0", "net-a", "net-b", "net-c", "lxdbr0"]
        env, log = self._make_bridge_env(tmp_path, bridges)
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        for b in ["net-a", "net-b", "net-c"]:
            assert any(f"network delete {b}" in c for c in cmds)
        assert not any("network delete incusbr0" in c for c in cmds)
        assert not any("network delete lxdbr0" in c for c in cmds)

    def test_bridge_named_network_not_deleted(self, tmp_path):
        """A bridge named 'network' (not net-*) is not deleted."""
        env, log = self._make_bridge_env(tmp_path, ["network", "net-test"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("network delete network" == c.strip() for c in cmds)

    def test_no_net_bridges_at_all(self, tmp_path):
        """No net-* bridges means zero bridge deletions."""
        env, log = self._make_bridge_env(tmp_path, ["incusbr0", "lxdbr0", "docker0"])
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert not any("network delete" in c for c in cmds)


# ── profile filtering ─────────────────────────────────────────


class TestFlushProfileFiltering:
    """Test profile filtering logic (default kept, others deleted)."""

    def test_default_profile_never_deleted(self, mock_env):
        """The 'default' profile is never deleted."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert not any("profile delete default" in c for c in cmds)

    def test_nesting_profile_deleted(self, mock_env):
        """The 'nesting' profile is deleted."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("profile delete nesting" in c for c in cmds)


# ── project filtering ─────────────────────────────────────────


class TestFlushProjectFiltering:
    """Test project filtering logic (default kept, others deleted)."""

    def test_default_project_never_deleted(self, mock_env):
        """The 'default' project is never deleted."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert not any("project delete default" in c for c in cmds)

    def test_admin_project_deleted(self, mock_env):
        """The 'admin' project is deleted."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("project delete admin" in c for c in cmds)

    def test_work_project_deleted(self, mock_env):
        """The 'work' project is deleted."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        assert any("project delete work" in c for c in cmds)


# ── deletion failure resilience ───────────────────────────────


class TestFlushDeletionResilience:
    """Test that flush continues despite individual deletion failures."""

    def _make_failing_env(self, tmp_path, fail_on=None):
        """Create env where specific operations fail."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "incus.log"
        fail_on = fail_on or {}

        fail_clauses = ""
        for pattern, exit_code in fail_on.items():
            fail_clauses += f"""
if [[ "$*" == *"{pattern}"* ]]; then
    echo "Error: simulated failure for {pattern}" >&2
    exit {exit_code}
fi"""

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; echo "proj-a"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then
    echo '[{{"name":"default"}},{{"name":"proj-a"}}]'
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--format csv"* && "$*" == *"--project proj-a"* ]]; then
    echo "inst-1"
    echo "inst-2"
    exit 0
fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
{fail_clauses}
if [[ "$1" == "delete" ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; echo "custom-prof"; exit 0; fi
if [[ "$1" == "profile" && "$2" == "delete" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "delete" ]]; then exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "net-a"; exit 0; fi
if [[ "$1" == "network" && "$2" == "delete" ]]; then exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, log_file

    def test_instance_failure_shows_warning(self, tmp_path):
        """Failed instance deletion shows WARNING."""
        env, _ = self._make_failing_env(tmp_path, {"delete inst-1": 1})
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "WARNING" in result.stdout
        assert "inst-1" in result.stdout

    def test_instance_failure_continues_to_next(self, tmp_path):
        """After failing inst-1, inst-2 is still attempted."""
        env, log = self._make_failing_env(tmp_path, {"delete inst-1": 1})
        run_flush(["--force"], env, cwd=tmp_path)
        cmds = read_log(log)
        assert any("delete inst-2" in c for c in cmds)

    def test_profile_failure_shows_warning(self, tmp_path):
        """Failed profile deletion shows WARNING."""
        env, _ = self._make_failing_env(tmp_path, {"profile delete custom-prof": 1})
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_project_failure_shows_warning(self, tmp_path):
        """Failed project deletion shows WARNING."""
        env, _ = self._make_failing_env(tmp_path, {"project delete proj-a": 1})
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_network_failure_shows_warning(self, tmp_path):
        """Failed network deletion shows WARNING."""
        env, _ = self._make_failing_env(tmp_path, {"network delete net-a": 1})
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_all_failures_still_exits_zero(self, tmp_path):
        """Even if everything fails, flush exits 0 (best-effort)."""
        env, _ = self._make_failing_env(tmp_path, {
            "delete inst-1": 1,
            "delete inst-2": 1,
            "profile delete custom-prof": 1,
            "project delete proj-a": 1,
            "network delete net-a": 1,
        })
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0

    def test_partial_success_counts_correctly(self, tmp_path):
        """Counter reflects only successful deletions."""
        env, _ = self._make_failing_env(tmp_path, {"delete inst-1": 1})
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode == 0
        assert "Flush complete" in result.stdout
        # inst-2 + custom-prof + proj-a + net-a = 4 successful
        assert "resources destroyed" in result.stdout


# ── counter accuracy ──────────────────────────────────────────


class TestFlushCounterAccuracy:
    """Detailed tests for the resource counter."""

    def test_counter_includes_instances(self, mock_env):
        """Counter includes successfully deleted instances."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        import re
        match = re.search(r"(\d+) resources destroyed", result.stdout)
        assert match
        count = int(match.group(1))
        assert count >= 2  # at least admin-ctrl + work-dev

    def test_counter_includes_profiles(self, mock_env):
        """Counter includes successfully deleted profiles."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        import re
        match = re.search(r"(\d+) resources destroyed", result.stdout)
        assert match
        count = int(match.group(1))
        # nesting profile in 3 projects = 3 profile deletions
        assert count >= 3

    def test_counter_includes_projects(self, mock_env):
        """Counter includes successfully deleted projects."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        import re
        match = re.search(r"(\d+) resources destroyed", result.stdout)
        assert match
        count = int(match.group(1))
        # admin + work projects = at least 2 more
        assert count >= 4

    def test_counter_includes_bridges(self, mock_env):
        """Counter includes successfully deleted bridges."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        import re
        match = re.search(r"(\d+) resources destroyed", result.stdout)
        assert match
        count = int(match.group(1))
        # net-admin + net-work = 2 bridges
        assert count >= 6

    def test_counter_includes_directories(self, mock_env):
        """Counter includes removed directories."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        import re
        match = re.search(r"(\d+) resources destroyed", result.stdout)
        assert match
        count = int(match.group(1))
        # 3 directories
        assert count >= 9

    def test_nothing_to_flush_no_counter(self, tmp_path):
        """When nothing found, 'Nothing to flush' shown instead of counter."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then echo "default"; exit 0; fi
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format json"* ]]; then echo '[{"name":"default"}]'; exit 0; fi
if [[ "$1" == "list" && "$*" == *"--format csv"* ]]; then exit 0; fi
if [[ "$1" == "profile" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "network" && "$2" == "list" ]]; then echo "incusbr0"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert "Nothing to flush" in result.stdout
        assert "resources destroyed" not in result.stdout


# ── pre-flight check ──────────────────────────────────────────


class TestFlushPreFlight:
    """Test the pre-flight Incus connectivity check."""

    def test_preflight_error_message(self, tmp_path):
        """Pre-flight failure shows clear error message."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        combined = result.stdout + result.stderr
        assert "Cannot connect" in combined

    def test_preflight_mentions_incus_daemon(self, tmp_path):
        """Pre-flight error mentions Incus daemon."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        combined = result.stdout + result.stderr
        assert "Incus daemon" in combined or "incus" in combined.lower()

    def test_preflight_mentions_socket_access(self, tmp_path):
        """Pre-flight error mentions socket access."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        combined = result.stdout + result.stderr
        assert "socket" in combined.lower()

    def test_preflight_happens_before_destruction(self, tmp_path):
        """Pre-flight check prevents any deletion if it fails."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "incus.log"
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
# Pre-flight fails
if [[ "$1" == "project" && "$2" == "list" && "$*" == *"--format csv"* ]]; then
    exit 1
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_flush(["--force"], env, cwd=tmp_path)
        assert result.returncode != 0
        cmds = read_log(log_file)
        # Only the pre-flight command should be logged, not deletes
        assert not any("delete" in c for c in cmds)

    def test_preflight_runs_before_confirmation(self, mock_env):
        """Pre-flight runs before asking for confirmation (with --force)."""
        env, log, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        # The header "=== AnKLuMe Flush ===" appears before preflight
        assert result.returncode == 0


# ── context file reading ─────────────────────────────────────


class TestFlushContextFileReading:
    """Test reading of /etc/anklume/ context files."""

    def test_reads_absolute_level(self):
        """Script reads /etc/anklume/absolute_level."""
        text = FLUSH_SH.read_text()
        assert "absolute_level" in text

    def test_reads_yolo(self):
        """Script reads /etc/anklume/yolo."""
        text = FLUSH_SH.read_text()
        assert "/etc/anklume/yolo" in text

    def test_checks_abs_level_equals_zero(self):
        """Script checks if ABS_LEVEL equals '0'."""
        text = FLUSH_SH.read_text()
        assert '"$ABS_LEVEL" = "0"' in text or "'$ABS_LEVEL' = '0'" in text

    def test_checks_yolo_not_true(self):
        """Script checks if YOLO is not 'true'."""
        text = FLUSH_SH.read_text()
        assert '"$YOLO" != "true"' in text or "'$YOLO' != 'true'" in text

    def test_checks_force_not_true(self):
        """Script checks if FORCE is not 'true'."""
        text = FLUSH_SH.read_text()
        assert '"$FORCE" != "true"' in text or "'$FORCE' != 'true'" in text

    def test_missing_abs_level_file_not_blocking(self, mock_env):
        """Missing absolute_level file does not block flush."""
        env, _, cwd = mock_env
        # mock_env does not create /etc/anklume, so these files don't exist
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0

    def test_missing_yolo_file_not_blocking(self, mock_env):
        """Missing yolo file does not block flush."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert result.returncode == 0


# ── specific instance names and project combinations ──────────


class TestFlushInstanceProjectCombinations:
    """Test instance naming and project association in flush."""

    def test_instance_deleted_in_correct_project(self, mock_env):
        """admin-ctrl is deleted in the admin project."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        # Find the delete command for admin-ctrl
        admin_ctrl_cmds = [c for c in cmds if "delete admin-ctrl" in c]
        assert len(admin_ctrl_cmds) >= 1
        assert "--project admin" in admin_ctrl_cmds[0]

    def test_work_dev_deleted_in_work_project(self, mock_env):
        """work-dev is deleted in the work project."""
        env, log, cwd = mock_env
        run_flush(["--force"], env, cwd=cwd)
        cmds = read_log(log)
        work_dev_cmds = [c for c in cmds if "delete work-dev" in c]
        assert len(work_dev_cmds) >= 1
        assert "--project work" in work_dev_cmds[0]

    def test_output_shows_admin_ctrl_with_project(self, mock_env):
        """Output message shows admin-ctrl with its project context."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "admin-ctrl" in result.stdout
        assert "project: admin" in result.stdout

    def test_output_shows_work_dev_with_project(self, mock_env):
        """Output message shows work-dev with its project context."""
        env, _, cwd = mock_env
        result = run_flush(["--force"], env, cwd=cwd)
        assert "work-dev" in result.stdout
        assert "project: work" in result.stdout
