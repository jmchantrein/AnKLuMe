"""Tests for scripts/deploy-nftables.sh — nftables host deployment."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

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
        iifname "net-admin" oifname "net-admin" accept
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
    echo "admin"
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


def read_log(log_file):
    """Return list of commands from the log file."""
    if log_file.exists():
        return [line.strip() for line in log_file.read_text().splitlines() if line.strip()]
    return []


class TestDeployArgs:
    def test_help_flag(self, mock_env):
        """--help shows usage."""
        env, _, _, script = mock_env
        result = run_deploy(["--help"], env, script=script)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_option(self, mock_env):
        """Unknown option gives error."""
        env, _, _, script = mock_env
        result = run_deploy(["--invalid"], env, script=script)
        assert result.returncode != 0
        assert "Unknown" in result.stderr

    def test_source_requires_value(self, mock_env):
        """--source without value gives error."""
        env, _, _, script = mock_env
        result = run_deploy(["--source"], env, script=script)
        assert result.returncode != 0


class TestDeployDryRun:
    def test_dry_run_validates_without_installing(self, mock_env):
        """--dry-run validates syntax but does not install."""
        env, log, _, script = mock_env
        result = run_deploy(["--dry-run"], env, script=script)
        assert result.returncode == 0
        assert "Dry run" in result.stdout or "dry run" in result.stdout.lower()
        cmds = read_log(log)
        # Should validate (nft -c -f)
        assert any("nft -c" in c for c in cmds)
        # Should NOT install (no nft -f without -c)
        nft_apply = [c for c in cmds if c.startswith("nft -f")]
        assert len(nft_apply) == 0


class TestDeployExecution:
    def test_full_deploy_pulls_and_applies(self, mock_env):
        """Full deploy pulls rules, validates, and applies."""
        env, log, _, script = mock_env
        result = run_deploy([], env, script=script)
        assert result.returncode == 0
        assert "deployed successfully" in result.stdout
        cmds = read_log(log)
        # Should pull file from container
        assert any("file pull" in c for c in cmds)
        # Should validate
        assert any("nft -c" in c for c in cmds)

    def test_custom_source_container(self, mock_env):
        """--source changes the container name."""
        env, log, _, script = mock_env
        run_deploy(["--source", "my-admin"], env, script=script)
        cmds = read_log(log)
        assert any("my-admin" in c for c in cmds)


class TestDeployNoIncus:
    def test_no_incus_fails(self, tmp_path):
        """Deploy fails when Incus is not available."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)
        # Need mktemp
        for cmd in ["mktemp"]:
            real = f"/usr/bin/{cmd}"
            if os.path.exists(real):
                (mock_bin / cmd).symlink_to(real)
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy([], env, cwd=tmp_path)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr


class TestDeploySourceFlag:
    """Test --source flag behavior for custom container name."""

    def test_source_flag_sets_custom_container(self, mock_env):
        """--source flag changes the container name used for file pull."""
        env, log, _, script = mock_env
        result = run_deploy(["--source", "custom-admin"], env, script=script)
        assert result.returncode == 0
        cmds = read_log(log)
        # The incus info and file pull commands should reference custom-admin
        assert any("custom-admin" in c for c in cmds)
        # Should NOT reference the default admin-ansible name in info/pull
        info_cmds = [c for c in cmds if "info" in c]
        assert all("admin-ansible" not in c for c in info_cmds)

    def test_source_without_argument_gives_error(self, mock_env):
        """--source without an argument produces an error."""
        env, _, _, script = mock_env
        result = run_deploy(["--source"], env, script=script)
        assert result.returncode != 0
        assert "--source requires" in result.stderr or "requires" in result.stderr.lower()


class TestFindProjectFunction:
    """Test the find_project function behavior."""

    def test_container_found_in_admin_project(self, tmp_path):
        """find_project returns 'admin' when container is in admin project."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmds.log"

        rules_file = tmp_path / "mock-rules.nft"
        rules_file.write_text("table inet anklume { chain isolation { } }\n")

        # Mock incus that finds the container in admin project
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"

# project list --format csv (pre-flight)
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    echo "admin"
    exit 0
fi

# info with --project admin succeeds (container found in admin)
if [[ "$1" == "info" && "$3" == "--project" && "$4" == "admin" ]]; then
    exit 0
fi

# file pull (retrieve rules)
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    cp "{rules_file}" "$4"
    exit 0
fi

exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        # Mock nft
        mock_nft = mock_bin / "nft"
        mock_nft.write_text(f"""#!/usr/bin/env bash
echo "nft $@" >> "{log_file}"
exit 0
""")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

        # Mock python3
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        # Symlink standard tools
        for cmd in ["mkdir", "cp", "chmod", "wc", "cat", "mktemp"]:
            p = mock_bin / cmd
            if not p.exists():
                real = f"/usr/bin/{cmd}"
                if os.path.exists(real):
                    p.symlink_to(real)

        # Create patched deploy script
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
        assert "Found in project: admin" in result.stdout

    def test_multi_project_search_fallback(self, tmp_path):
        """When container not in admin project, searches all projects via JSON."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmds.log"

        rules_file = tmp_path / "mock-rules.nft"
        rules_file.write_text("table inet anklume { chain isolation { } }\n")

        # Mock incus: admin project lookup fails, but list --all-projects finds it
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"

# project list --format csv (pre-flight)
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    echo "admin"
    echo "custom"
    exit 0
fi

# info with --project admin FAILS (container not in admin)
if [[ "$1" == "info" && "$3" == "--project" && "$4" == "admin" ]]; then
    exit 1
fi

# info with --project custom succeeds (for file pull validation)
if [[ "$1" == "info" ]]; then
    exit 0
fi

# list --all-projects --format json returns container in 'custom' project
if [[ "$1" == "list" && "$2" == "--all-projects" ]]; then
    echo '[{{"name": "admin-ansible", "project": "custom"}}]'
    exit 0
fi

# file pull (retrieve rules)
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    cp "{rules_file}" "$4"
    exit 0
fi

exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        # Mock nft
        mock_nft = mock_bin / "nft"
        mock_nft.write_text(f"""#!/usr/bin/env bash
echo "nft $@" >> "{log_file}"
exit 0
""")
        mock_nft.chmod(mock_nft.stat().st_mode | stat.S_IEXEC)

        # Mock python3
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        # Symlink standard tools
        for cmd in ["mkdir", "cp", "chmod", "wc", "cat", "mktemp"]:
            p = mock_bin / cmd
            if not p.exists():
                real = f"/usr/bin/{cmd}"
                if os.path.exists(real):
                    p.symlink_to(real)

        # Create patched deploy script
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
        # Should have found the container in the 'custom' project
        assert "Found in project: custom" in result.stdout
        cmds = read_log(log_file)
        # Should have attempted admin project first, then fallen back
        assert any("--project admin" in c for c in cmds)


# ── Pull failure ──────────────────────────────────────────


class TestDeployFilePullFailure:
    """Test error handling when file pull from container fails."""

    def test_pull_failure_gives_clear_error(self, tmp_path):
        """When incus file pull fails, shows 'Did you run make nftables'."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmd.log"

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
# project list passes pre-flight
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
# info passes (container found)
if [[ "$1" == "info" ]]; then exit 0; fi
# file pull fails
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

        # Incus works, but nft validation fails
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    # Write some content to the dest file (3rd arg)
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


class TestDeployDryRunContent:
    """Test dry-run outputs the rules content."""

    def test_dry_run_prints_rules_content(self, tmp_path):
        """--dry-run should print the rules file content."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "cmd.log"

        rules_content = "table inet anklume { chain iso { type filter hook forward priority -1; } }"
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "file" && "$2" == "pull" ]]; then
    echo '{rules_content}' > "$3"
    exit 0
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
        for cmd in ["mktemp", "rm", "wc", "cat"]:
            p = mock_bin / cmd
            real = f"/usr/bin/{cmd}"
            if not p.exists() and os.path.exists(real):
                p.symlink_to(real)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = run_deploy(["--dry-run"], env)
        assert result.returncode == 0
        assert "NOT installed" in result.stdout
        assert "anklume" in result.stdout
