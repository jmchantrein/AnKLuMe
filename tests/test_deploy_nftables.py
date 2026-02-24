"""Tests for scripts/deploy-nftables.sh — nftables host deployment."""

import os
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import read_log

DEPLOY_SH = Path(__file__).resolve().parent.parent / "scripts" / "deploy-nftables.sh"


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock environment for deploy-nftables testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Create a fake rules file that incus file pull will "retrieve"
    rules_content = """table inet anklume {
    chain isolation {
        type filter hook forward priority -1; policy accept;
        ct state established,related accept
        ct state invalid drop
        iifname "net-anklume" oifname "net-anklume" accept
        iifname "net-work" oifname "net-work" accept
        drop
    }
}
"""
    rules_file = tmp_path / "mock-rules.nft"
    rules_file.write_text(rules_content)

    # Mock incus
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"

# project list --format csv (pre-flight)
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    echo "anklume"
    exit 0
fi

# info (find container)
if [[ "$1" == "info" ]]; then
    exit 0
fi

# file pull (retrieve rules)
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    # Copy our mock rules to the destination
    cp "{rules_file}" "$4"
    exit 0
fi

exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock nft (validate syntax)
    mock_nft = mock_bin / "nft"
    mock_nft.write_text(f"""#!/usr/bin/env bash
echo "nft $@" >> "{log_file}"
# -c = check mode (dry validation)
if [[ "$1" == "-c" ]]; then
    exit 0
fi
# -f = apply file
if [[ "$1" == "-f" ]]; then
    exit 0
fi
exit 0
""")
    mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

    # Mock python3
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    # Mock other tools
    for cmd in ["mkdir", "cp", "chmod", "wc", "cat", "mktemp"]:
        p = mock_bin / cmd
        if not p.exists():
            real = f"/usr/bin/{cmd}"
            if os.path.exists(real):
                p.symlink_to(real)

    # Create patched deploy script to avoid /etc writes
    patched_deploy = tmp_path / "deploy_patched.sh"
    original = DEPLOY_SH.read_text()
    patched_dest = tmp_path / "nftables.d"
    patched_dest.mkdir()
    patched = original.replace('/etc/nftables.d', str(patched_dest))
    patched_deploy.write_text(patched)
    patched_deploy.chmod(patched_deploy.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path, patched_deploy


def run_deploy(args, env, cwd=None, script=None):
    """Run deploy-nftables.sh with given args."""
    script_path = script or DEPLOY_SH
    result = subprocess.run(
        ["bash", str(script_path)] + args,
        capture_output=True, text=True, env=env, cwd=cwd, timeout=15,
    )
    return result


# ── Dry-run mode ────────────────────────────────────────────


class TestDeployDryRun:
    def test_dry_run_validates_without_installing(self, mock_env):
        """--dry-run validates syntax but does not install."""
        env, log, _, script = mock_env
        result = run_deploy(["--dry-run"], env, script=script)
        assert result.returncode == 0
        assert "Dry run" in result.stdout or "dry run" in result.stdout.lower()
        cmds = read_log(log)
        assert any("nft -c" in c for c in cmds)
        nft_apply = [c for c in cmds if c.startswith("nft -f")]
        assert len(nft_apply) == 0

    def test_dry_run_does_not_create_dest_file(self, mock_env):
        """Dry-run does NOT write rules to destination."""
        env, _, tmp, script = mock_env
        dest_dir = tmp / "nftables.d"
        for f in dest_dir.glob("*"):
            f.unlink()
        result = run_deploy(["--dry-run"], env, script=script)
        assert result.returncode == 0
        nft_files = list(dest_dir.glob("*.nft"))
        assert len(nft_files) == 0


# ── Full deploy ─────────────────────────────────────────────


class TestDeployExecution:
    def test_full_deploy_pulls_and_applies(self, mock_env):
        """Full deploy pulls rules, validates, and applies."""
        env, log, _, script = mock_env
        result = run_deploy([], env, script=script)
        assert result.returncode == 0
        assert "deployed successfully" in result.stdout
        cmds = read_log(log)
        assert any("file pull" in c for c in cmds)
        assert any("nft -c" in c for c in cmds)

    def test_full_deploy_creates_dest_file(self, mock_env):
        """Full deploy writes rules to the destination directory."""
        env, _, tmp, script = mock_env
        result = run_deploy([], env, script=script)
        assert result.returncode == 0
        dest_file = tmp / "nftables.d" / "anklume-isolation.nft"
        assert dest_file.exists()
        content = dest_file.read_text()
        assert "inet anklume" in content

    def test_custom_source_container(self, mock_env):
        """--source changes the container name."""
        env, log, _, script = mock_env
        run_deploy(["--source", "my-admin"], env, script=script)
        cmds = read_log(log)
        assert any("my-admin" in c for c in cmds)


# ── Command sequence ────────────────────────────────────────


class TestDeployCommandSequence:
    def test_validate_before_install(self, mock_env):
        """nft -c (validate) is called before nft -f (apply)."""
        env, log, _, script = mock_env
        result = run_deploy([], env, script=script)
        assert result.returncode == 0
        cmds = read_log(log)
        nft_cmds = [c for c in cmds if c.startswith("nft")]
        assert len(nft_cmds) >= 2
        assert "-c" in nft_cmds[0]
        assert "-f" in nft_cmds[1]

    def test_pull_before_validate(self, mock_env):
        """incus file pull is called before nft validation."""
        env, log, _, script = mock_env
        result = run_deploy([], env, script=script)
        assert result.returncode == 0
        cmds = read_log(log)
        pull_idx = next(i for i, c in enumerate(cmds) if "file pull" in c)
        nft_idx = next(i for i, c in enumerate(cmds) if c.startswith("nft"))
        assert pull_idx < nft_idx


# ── Project resolution ──────────────────────────────────────


class TestFindProjectFunction:
    def test_container_found_in_anklume_project(self, tmp_path):
        """find_project returns 'anklume' when container is in anklume project."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmds.log"

        rules_file = tmp_path / "mock-rules.nft"
        rules_file.write_text("table inet anklume { chain isolation { } }\n")

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    echo "anklume"
    exit 0
fi
if [[ "$1" == "info" && "$3" == "--project" && "$4" == "anklume" ]]; then
    exit 0
fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    cp "{rules_file}" "$4"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_nft = mock_bin / "nft"
        mock_nft.write_text(f"""#!/usr/bin/env bash
echo "nft $@" >> "{log_file}"
exit 0
""")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        for cmd in ["mkdir", "cp", "chmod", "wc", "cat", "mktemp"]:
            p = mock_bin / cmd
            if not p.exists():
                real = f"/usr/bin/{cmd}"
                if os.path.exists(real):
                    p.symlink_to(real)

        patched_deploy = tmp_path / "deploy_patched.sh"
        original = DEPLOY_SH.read_text()
        patched_dest = tmp_path / "nftables.d"
        patched_dest.mkdir()
        patched = original.replace('/etc/nftables.d', str(patched_dest))
        patched_deploy.write_text(patched)
        patched_deploy.chmod(patched_deploy.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"

        result = run_deploy([], env, script=patched_deploy)
        assert result.returncode == 0
        assert "Found in project: anklume" in result.stdout

    def test_multi_project_search_fallback(self, tmp_path):
        """When container not in anklume project, searches all projects via JSON."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmds.log"

        rules_file = tmp_path / "mock-rules.nft"
        rules_file.write_text("table inet anklume { chain isolation { } }\n")

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    echo "anklume"
    echo "custom"
    exit 0
fi
if [[ "$1" == "info" && "$3" == "--project" && "$4" == "anklume" ]]; then
    exit 1
fi
if [[ "$1" == "info" ]]; then
    exit 0
fi
if [[ "$1" == "list" && "$2" == "--all-projects" ]]; then
    echo '[{{"name": "anklume-instance", "project": "custom"}}]'
    exit 0
fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    cp "{rules_file}" "$4"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_nft = mock_bin / "nft"
        mock_nft.write_text(f"""#!/usr/bin/env bash
echo "nft $@" >> "{log_file}"
exit 0
""")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        for cmd in ["mkdir", "cp", "chmod", "wc", "cat", "mktemp"]:
            p = mock_bin / cmd
            if not p.exists():
                real = f"/usr/bin/{cmd}"
                if os.path.exists(real):
                    p.symlink_to(real)

        patched_deploy = tmp_path / "deploy_patched.sh"
        original = DEPLOY_SH.read_text()
        patched_dest = tmp_path / "nftables.d"
        patched_dest.mkdir()
        patched = original.replace('/etc/nftables.d', str(patched_dest))
        patched_deploy.write_text(patched)
        patched_deploy.chmod(patched_deploy.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"

        result = run_deploy([], env, script=patched_deploy)
        assert result.returncode == 0
        assert "Found in project: custom" in result.stdout


# ── Error handling ──────────────────────────────────────────


class TestDeployErrors:
    def test_no_incus_fails(self, tmp_path):
        """Deploy fails when Incus is not available."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        for cmd in ["mktemp"]:
            real = f"/usr/bin/{cmd}"
            if os.path.exists(real):
                (mock_bin / cmd).symlink_to(real)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr

    def test_pull_failure_gives_clear_error(self, tmp_path):
        """When incus file pull fails, shows helpful error."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmd.log"

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    echo "Error: file not found" >&2
    exit 1
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        for cmd in ["mktemp", "rm"]:
            p = mock_bin / cmd
            real = f"/usr/bin/{cmd}"
            if not p.exists() and os.path.exists(real):
                p.symlink_to(real)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env)
        assert result.returncode != 0
        assert "make nftables" in result.stderr or "Failed to pull" in result.stderr

    def test_syntax_validation_failure(self, tmp_path):
        """When nft -c -f fails, shows syntax validation error."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmd.log"

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    echo "table inet anklume {{}}" > "$3"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_nft = mock_bin / "nft"
        mock_nft.write_text("""#!/usr/bin/env bash
if [[ "$1" == "-c" ]]; then
    echo "Error: syntax error" >&2
    exit 1
fi
exit 0
""")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        for cmd in ["mktemp", "rm", "wc"]:
            p = mock_bin / cmd
            real = f"/usr/bin/{cmd}"
            if not p.exists() and os.path.exists(real):
                p.symlink_to(real)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env)
        assert result.returncode != 0
        assert "Syntax" in result.stderr or "syntax" in result.stderr.lower()

    def test_container_not_found_anywhere(self, tmp_path):
        """Container not found in any project gives clear error."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmd.log"

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 1; fi
if [[ "$1" == "list" && "$2" == "--all-projects" ]]; then
    echo '[]'
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        for cmd in ["mktemp", "rm"]:
            p = mock_bin / cmd
            real = f"/usr/bin/{cmd}"
            if not p.exists() and os.path.exists(real):
                p.symlink_to(real)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env)
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# ── Cleanup on failure ──────────────────────────────────────


class TestDeployCleanup:
    def test_trap_cleanup_on_pull_failure(self, tmp_path):
        """When file pull fails, the trap cleans up the temp file."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmds.log"

        tmpfile_tracker = tmp_path / "tmpfile_path.txt"

        mock_mktemp = mock_bin / "mktemp"
        mock_mktemp.write_text(f"""#!/usr/bin/env bash
TMPF=$(/usr/bin/mktemp "$@")
echo "$TMPF" >> "{tmpfile_tracker}"
echo "$TMPF"
""")
        mock_mktemp.chmod(mock_mktemp.stat().st_mode | stat.S_IEXEC)

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    echo "Error: file not found" >&2
    exit 1
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_nft = mock_bin / "nft"
        mock_nft.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        for cmd in ["rm"]:
            p = mock_bin / cmd
            real = f"/usr/bin/{cmd}"
            if not p.exists() and os.path.exists(real):
                p.symlink_to(real)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env)
        assert result.returncode != 0

        if tmpfile_tracker.exists():
            for line in tmpfile_tracker.read_text().splitlines():
                tmpf = Path(line.strip())
                assert not tmpf.exists(), f"Temp file {tmpf} should have been cleaned up by trap"

    def test_trap_cleanup_on_syntax_failure(self, tmp_path):
        """When nft -c fails, the trap cleans up the temp file."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmds.log"

        tmpfile_tracker = tmp_path / "tmpfile_path.txt"

        mock_mktemp = mock_bin / "mktemp"
        mock_mktemp.write_text(f"""#!/usr/bin/env bash
TMPF=$(/usr/bin/mktemp "$@")
echo "$TMPF" >> "{tmpfile_tracker}"
echo "$TMPF"
""")
        mock_mktemp.chmod(mock_mktemp.stat().st_mode | stat.S_IEXEC)

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    echo "table inet anklume {{}}" > "$4"
    exit 0
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        mock_nft = mock_bin / "nft"
        mock_nft.write_text("""#!/usr/bin/env bash
if [[ "$1" == "-c" ]]; then
    echo "Error: syntax error" >&2
    exit 1
fi
exit 0
""")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        for cmd in ["rm", "wc"]:
            p = mock_bin / cmd
            real = f"/usr/bin/{cmd}"
            if not p.exists() and os.path.exists(real):
                p.symlink_to(real)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env)
        assert result.returncode != 0

        if tmpfile_tracker.exists():
            for line in tmpfile_tracker.read_text().splitlines():
                tmpf = Path(line.strip())
                assert not tmpf.exists(), f"Temp file {tmpf} should have been cleaned up by trap"
