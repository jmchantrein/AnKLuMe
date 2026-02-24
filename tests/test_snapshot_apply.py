"""Tests for scripts/snapshot-apply.sh — pre-apply snapshot management."""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import read_log

SNAPSHOT_APPLY_SH = Path(__file__).resolve().parent.parent / "scripts" / "snapshot-apply.sh"


@pytest.fixture()
def mock_env(tmp_path):
    """Create mock incus, ansible-inventory, and python3 binaries.

    The mock incus tracks created snapshots in a sidecar directory so that
    rollback tests can verify snapshot existence realistically.
    """
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "incus.log"
    snap_track = tmp_path / "snap-track"
    snap_track.mkdir()

    # ── Mock incus ───────────────────────────────────────────
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
SNAP_TRACK="{snap_track}"

if [[ "$1" == "info" ]]; then
    exit 0
fi
if [[ "$1" == "snapshot" && "$2" == "create" ]]; then
    instance="$3"
    snap_name="$4"
    echo "$snap_name" >> "$SNAP_TRACK/$instance.snaps"
    exit 0
fi
if [[ "$1" == "snapshot" && "$2" == "list" ]]; then
    instance="$3"
    track_file="$SNAP_TRACK/$instance.snaps"
    if [[ -f "$track_file" ]]; then
        echo -n "["
        first=true
        while IFS= read -r name; do
            [[ -z "$name" ]] && continue
            if $first; then first=false; else echo -n ","; fi
            printf '{{"name":"%s"}}' "$name"
        done < "$track_file"
        echo "]"
    else
        echo "[]"
    fi
    exit 0
fi
if [[ "$1" == "snapshot" && "$2" == "restore" ]]; then
    exit 0
fi
if [[ "$1" == "snapshot" && "$2" == "delete" ]]; then
    instance="$3"
    snap_name="$4"
    track_file="$SNAP_TRACK/$instance.snaps"
    if [[ -f "$track_file" ]]; then
        grep -v "^${{snap_name}}$" "$track_file" > "${{track_file}}.tmp" 2>/dev/null || true
        mv "${{track_file}}.tmp" "$track_file"
    fi
    exit 0
fi
echo "mock: unhandled command: $*" >&2
exit 1
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # ── Mock ansible-inventory ───────────────────────────────
    mock_ansible_inv = mock_bin / "ansible-inventory"
    mock_ansible_inv.write_text("""#!/usr/bin/env bash
cat << 'JSON'
{
  "_meta": {
    "hostvars": {
      "app-server": {"ansible_host": "10.100.1.10"},
      "web-frontend": {"ansible_host": "10.100.2.20"}
    }
  },
  "homelab": {
    "hosts": ["app-server"]
  },
  "webservers": {
    "hosts": ["web-frontend"]
  }
}
JSON
""")
    mock_ansible_inv.chmod(mock_ansible_inv.stat().st_mode | stat.S_IEXEC)

    # ── Mock python3 ─────────────────────────────────────────
    # Routes based on $2 (the -c code argument), not stdin.
    # Order matters: "import yaml" must be checked BEFORE "group = "
    # because get_instance_project code contains both "yaml" and
    # "group = f.split(...)" which would falsely match the group branch.
    mock_python3 = mock_bin / "python3"
    mock_python3.write_text("""#!/usr/bin/env bash
code="$2"

if echo "$code" | grep -q "hostvars"; then
    # get_running_instances (all hosts) — piped from ansible-inventory
    cat > /dev/null 2>&1 || true
    echo "app-server"
    echo "web-frontend"
elif echo "$code" | grep -q "import yaml"; then
    # get_instance_project — NOT piped, no stdin to drain
    echo "default"
elif echo "$code" | grep -q "group = '"; then
    # get_running_instances (filtered) — piped from ansible-inventory
    cat > /dev/null 2>&1 || true
    group_name=$(echo "$code" | grep "group = '" | head -1 | sed "s/.*group = '\\([^']*\\)'.*/\\1/")
    case "$group_name" in
        homelab) echo "app-server" ;;
        webservers) echo "web-frontend" ;;
        *) ;;
    esac
elif echo "$code" | grep -q "in names"; then
    # Snapshot existence check in rollback — piped from incus snapshot list
    snap_name=$(echo "$code" | sed -n "s/.*'\\([^']*\\)' in names.*/\\1/p" | head -1)
    json_input=$(cat)
    if echo "$json_input" | grep -q "\\"name\\":\\"${snap_name}\\""; then
        echo "yes"
    else
        echo "no"
    fi
else
    cat > /dev/null 2>&1 || true
fi
""")
    mock_python3.chmod(mock_python3.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["HOME"] = str(tmp_path)

    return env, log_file, snap_track


def run_snapshot_apply(args, env, cwd=None):
    """Run snapshot-apply.sh with given args and environment."""
    return subprocess.run(
        ["bash", str(SNAPSHOT_APPLY_SH)] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


def get_state_dir(env):
    """Derive the state directory path from HOME."""
    return Path(env["HOME"]) / ".anklume" / "pre-apply-snapshots"


# ── Usage ────────────────────────────────────────────────────


class TestUsage:
    def test_no_args_shows_usage(self, mock_env):
        """No arguments displays usage and exits 1."""
        env, _, _ = mock_env
        result = run_snapshot_apply([], env)
        assert result.returncode == 1
        combined = result.stdout + result.stderr
        assert "Usage:" in combined


# ── Create ───────────────────────────────────────────────────


class TestCreate:
    def test_create_all_instances(self, mock_env):
        """Create snapshots for every inventory instance."""
        env, log_file, _ = mock_env
        result = run_snapshot_apply(["create"], env)
        assert result.returncode == 0

        cmds = read_log(log_file)
        assert any("snapshot create" in c and "app-server" in c for c in cmds)
        assert any("snapshot create" in c and "web-frontend" in c for c in cmds)

        state = get_state_dir(env)
        assert (state / "latest").exists()
        assert (state / "history").exists()
        assert (state / "latest-scope").read_text().strip() == "all"

    def test_create_with_limit(self, mock_env):
        """Create snapshots only for instances in the specified group."""
        env, log_file, _ = mock_env
        result = run_snapshot_apply(["create", "--limit", "homelab"], env)
        assert result.returncode == 0

        state = get_state_dir(env)
        assert (state / "latest-scope").read_text().strip() == "homelab"

    def test_create_snapshot_name_format(self, mock_env):
        """Snapshot name follows pre-apply-YYYYMMDD-HHMMSS pattern."""
        env, log_file, _ = mock_env
        run_snapshot_apply(["create"], env)

        cmds = read_log(log_file)
        snap_cmd = next((c for c in cmds if "snapshot create" in c), None)
        assert snap_cmd is not None
        assert re.search(r"pre-apply-\d{8}-\d{6}", snap_cmd)

        state = get_state_dir(env)
        latest = (state / "latest").read_text().strip()
        assert re.match(r"^\d{8}-\d{6}$", latest)

    def test_create_appends_history(self, mock_env):
        """Multiple creates append to history file."""
        env, _, _ = mock_env

        run_snapshot_apply(["create"], env)
        run_snapshot_apply(["create"], env)

        state = get_state_dir(env)
        lines = [x for x in (state / "history").read_text().splitlines() if x.strip()]
        assert len(lines) >= 2

    def test_create_no_instances(self, tmp_path):
        """Create with empty inventory warns but returns 0."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        # ansible-inventory returning empty hosts
        ai = mock_bin / "ansible-inventory"
        ai.write_text('#!/usr/bin/env bash\necho \'{"_meta":{"hostvars":{}}}\'\n')
        ai.chmod(ai.stat().st_mode | stat.S_IEXEC)

        # python3 returning nothing (no hosts)
        py = mock_bin / "python3"
        py.write_text('#!/usr/bin/env bash\ncat > /dev/null 2>&1 || true\n')
        py.chmod(py.stat().st_mode | stat.S_IEXEC)

        incus = mock_bin / "incus"
        incus.write_text("#!/usr/bin/env bash\nexit 0\n")
        incus.chmod(incus.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(tmp_path)

        result = run_snapshot_apply(["create"], env)
        assert result.returncode == 0
        assert "No instances found" in result.stdout or "WARNING" in result.stderr


# ── Rollback ─────────────────────────────────────────────────


class TestRollback:
    def test_rollback_latest(self, mock_env):
        """Rollback restores the most recent pre-apply snapshot."""
        env, log_file, _ = mock_env

        run_snapshot_apply(["create"], env)

        # Clear log, keep state
        log_file.unlink(missing_ok=True)
        log_file.touch()

        result = run_snapshot_apply(["rollback"], env)
        assert result.returncode == 0

        cmds = read_log(log_file)
        assert any("snapshot restore" in c for c in cmds)

    def test_rollback_specific_timestamp(self, mock_env):
        """Rollback with explicit timestamp restores that snapshot."""
        env, log_file, _ = mock_env

        run_snapshot_apply(["create"], env)

        state = get_state_dir(env)
        ts = (state / "latest").read_text().strip()

        log_file.unlink(missing_ok=True)
        log_file.touch()

        result = run_snapshot_apply(["rollback", ts], env)
        assert result.returncode == 0

        cmds = read_log(log_file)
        expected = f"pre-apply-{ts}"
        assert any(expected in c and "snapshot restore" in c for c in cmds)

    def test_rollback_no_snapshots_fails(self, tmp_path):
        """Rollback without any prior snapshot exits with error."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        for name in ("incus", "ansible-inventory", "python3"):
            p = mock_bin / name
            p.write_text("#!/usr/bin/env bash\nexit 0\n")
            p.chmod(p.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(tmp_path)

        result = run_snapshot_apply(["rollback"], env)
        assert result.returncode != 0
        assert "No pre-apply snapshots found" in result.stderr

    def test_rollback_reads_latest_file(self, mock_env):
        """Rollback without timestamp uses the 'latest' state file."""
        env, log_file, _ = mock_env

        run_snapshot_apply(["create"], env)

        state = get_state_dir(env)
        ts = (state / "latest").read_text().strip()
        expected_snap = f"pre-apply-{ts}"

        log_file.unlink(missing_ok=True)
        log_file.touch()

        run_snapshot_apply(["rollback"], env)

        cmds = read_log(log_file)
        assert any(expected_snap in c for c in cmds)


# ── List ─────────────────────────────────────────────────────


class TestList:
    def test_list_with_history(self, mock_env):
        """List shows snapshot names and marks latest."""
        env, _, _ = mock_env

        run_snapshot_apply(["create"], env)

        result = run_snapshot_apply(["list"], env)
        assert result.returncode == 0
        assert "pre-apply-" in result.stdout
        assert "<-- latest" in result.stdout

    def test_list_no_history(self, tmp_path):
        """List with no history file shows (none)."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        incus = mock_bin / "incus"
        incus.write_text("#!/usr/bin/env bash\nexit 0\n")
        incus.chmod(incus.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(tmp_path)

        result = run_snapshot_apply(["list"], env)
        assert result.returncode == 0
        assert "(none)" in result.stdout

    def test_list_multiple_snapshots(self, mock_env):
        """List shows all snapshots with at least one marked latest."""
        env, _, _ = mock_env

        run_snapshot_apply(["create"], env)
        # Sleep 1s to guarantee distinct timestamps
        import time
        time.sleep(1.1)
        run_snapshot_apply(["create"], env)

        result = run_snapshot_apply(["list"], env)
        assert result.returncode == 0

        lines = [line for line in result.stdout.splitlines() if "pre-apply-" in line]
        assert len(lines) >= 2
        # Exactly 1 line marked latest (timestamps now differ)
        assert sum(1 for line in lines if "<-- latest" in line) == 1


# ── Cleanup ──────────────────────────────────────────────────


class TestCleanup:
    def test_cleanup_default_keep_3(self, mock_env):
        """Cleanup with default retention keeps exactly 3 snapshots."""
        env, log_file, _ = mock_env

        for _ in range(5):
            run_snapshot_apply(["create"], env)

        state = get_state_dir(env)
        before = len([x for x in (state / "history").read_text().splitlines() if x.strip()])
        assert before >= 5

        log_file.unlink(missing_ok=True)
        log_file.touch()

        result = run_snapshot_apply(["cleanup"], env)
        assert result.returncode == 0

        after = len([x for x in (state / "history").read_text().splitlines() if x.strip()])
        assert after == 3

        cmds = read_log(log_file)
        assert any("snapshot delete" in c for c in cmds)

    def test_cleanup_custom_keep(self, mock_env):
        """Cleanup with --keep N preserves exactly N snapshots."""
        env, _, _ = mock_env

        for _ in range(5):
            run_snapshot_apply(["create"], env)

        result = run_snapshot_apply(["cleanup", "--keep", "2"], env)
        assert result.returncode == 0

        state = get_state_dir(env)
        after = len([x for x in (state / "history").read_text().splitlines() if x.strip()])
        assert after == 2

    def test_cleanup_fewer_than_keep(self, mock_env):
        """Cleanup when count <= keep returns early without deleting."""
        env, log_file, _ = mock_env

        for _ in range(2):
            run_snapshot_apply(["create"], env)

        log_file.unlink(missing_ok=True)
        log_file.touch()

        result = run_snapshot_apply(["cleanup", "--keep", "5"], env)
        assert result.returncode == 0
        assert "keeping all" in result.stdout or "Only" in result.stdout

    def test_cleanup_no_history(self, tmp_path):
        """Cleanup with no history file is a no-op."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        incus = mock_bin / "incus"
        incus.write_text("#!/usr/bin/env bash\nexit 0\n")
        incus.chmod(incus.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(tmp_path)

        result = run_snapshot_apply(["cleanup"], env)
        assert result.returncode == 0
        assert "No pre-apply snapshots" in result.stdout


# ── State files ──────────────────────────────────────────────


class TestStateFiles:
    def test_latest_contains_timestamp(self, mock_env):
        """latest file contains YYYYMMDD-HHMMSS timestamp."""
        env, _, _ = mock_env
        run_snapshot_apply(["create"], env)

        state = get_state_dir(env)
        latest = (state / "latest").read_text().strip()
        assert re.match(r"^\d{8}-\d{6}$", latest)

    def test_history_contains_full_names(self, mock_env):
        """history file contains pre-apply-YYYYMMDD-HHMMSS entries."""
        env, _, _ = mock_env
        run_snapshot_apply(["create"], env)

        state = get_state_dir(env)
        for line in (state / "history").read_text().splitlines():
            if line.strip():
                assert re.match(r"^pre-apply-\d{8}-\d{6}$", line.strip())

    def test_scope_all_by_default(self, mock_env):
        """latest-scope is 'all' when no --limit is given."""
        env, _, _ = mock_env
        run_snapshot_apply(["create"], env)
        state = get_state_dir(env)
        assert (state / "latest-scope").read_text().strip() == "all"

    def test_scope_reflects_limit(self, mock_env):
        """latest-scope contains the group name when --limit is used."""
        env, _, _ = mock_env
        run_snapshot_apply(["create", "--limit", "homelab"], env)
        state = get_state_dir(env)
        assert (state / "latest-scope").read_text().strip() == "homelab"


# ── Error handling ───────────────────────────────────────────


class TestErrorHandling:
    def test_unknown_command(self, mock_env):
        """Unknown command shows usage and exits 1."""
        env, _, _ = mock_env
        result = run_snapshot_apply(["unknown"], env)
        assert result.returncode == 1
        combined = result.stdout + result.stderr
        assert "Usage:" in combined

    def test_create_limit_missing_value(self, mock_env):
        """--limit without a value fails."""
        env, _, _ = mock_env
        result = run_snapshot_apply(["create", "--limit"], env)
        assert result.returncode != 0

    def test_cleanup_keep_missing_value(self, mock_env):
        """--keep without a value fails."""
        env, _, _ = mock_env
        result = run_snapshot_apply(["cleanup", "--keep"], env)
        assert result.returncode != 0


# ── Integration ──────────────────────────────────────────────


class TestIntegration:
    def test_full_workflow(self, mock_env):
        """Full workflow: create → list → rollback → cleanup."""
        env, log_file, _ = mock_env

        # Create
        r_create = run_snapshot_apply(["create"], env)
        assert r_create.returncode == 0

        # List
        r_list = run_snapshot_apply(["list"], env)
        assert r_list.returncode == 0
        assert "pre-apply-" in r_list.stdout

        # Rollback
        log_file.unlink(missing_ok=True)
        log_file.touch()
        r_rollback = run_snapshot_apply(["rollback"], env)
        assert r_rollback.returncode == 0
        assert any("snapshot restore" in c for c in read_log(log_file))

        # Cleanup
        r_cleanup = run_snapshot_apply(["cleanup", "--keep", "1"], env)
        assert r_cleanup.returncode == 0

    def test_limit_scoping(self, mock_env):
        """--limit scopes snapshots and updates scope state."""
        env, _, _ = mock_env

        run_snapshot_apply(["create"], env)
        state = get_state_dir(env)
        assert (state / "latest-scope").read_text().strip() == "all"

        run_snapshot_apply(["create", "--limit", "homelab"], env)
        assert (state / "latest-scope").read_text().strip() == "homelab"
