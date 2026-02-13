"""Tests for scripts/ai-switch.sh — exclusive AI-tools access switching."""

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

AI_SWITCH_SH = Path(__file__).resolve().parent.parent / "scripts" / "ai-switch.sh"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def switch_env(tmp_path):
    """Create a mock environment for ai-switch testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Create a minimal infra.yml with ai-tools domain
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir()
    (project_dir / "infra.yml").write_text(yaml.dump({
        "project_name": "test",
        "global": {
            "base_subnet": "10.100",
            "default_os_image": "images:debian/13",
            "ai_access_policy": "exclusive",
            "ai_access_default": "pro",
        },
        "domains": {
            "admin": {"subnet_id": 0, "machines": {
                "admin-ansible": {"type": "lxc", "ip": "10.100.0.10"},
            }},
            "pro": {"subnet_id": 2, "machines": {
                "pro-dev": {"type": "lxc", "ip": "10.100.2.10"},
            }},
            "perso": {"subnet_id": 1, "machines": {
                "perso-desktop": {"type": "lxc", "ip": "10.100.1.10"},
            }},
            "ai-tools": {"subnet_id": 10, "machines": {
                "ai-ollama": {"type": "lxc", "ip": "10.100.10.10", "gpu": True},
            }},
        },
    }, sort_keys=False))

    # Mock python3
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    # Mock incus
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock ansible-playbook
    mock_ansible = mock_bin / "ansible-playbook"
    mock_ansible.write_text(f"""#!/usr/bin/env bash
echo "ansible-playbook $@" >> "{log_file}"
exit 0
""")
    mock_ansible.chmod(mock_ansible.stat().st_mode | stat.S_IEXEC)

    # Create a patched ai-switch.sh that uses our project dir
    patched_switch = scripts_dir / "ai-switch.sh"
    original = AI_SWITCH_SH.read_text()
    # Patch the PROJECT_DIR resolution to use our temp project
    patched = original.replace(
        'PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
        f'PROJECT_DIR="{project_dir}"',
    )
    # Also patch the state file and log paths to tmp
    patched = patched.replace(
        'STATE_FILE="/opt/anklume/ai-access-current"',
        f'STATE_FILE="{project_dir}/ai-access-current"',
    )
    patched = patched.replace(
        'LOG_DIR="/var/log/anklume"',
        f'LOG_DIR="{project_dir}/logs"',
    )
    patched_switch.write_text(patched)
    patched_switch.chmod(patched_switch.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, project_dir, patched_switch


def run_switch(args, env, project_dir, script=None):
    """Run ai-switch.sh relative to the project dir."""
    script_path = script or AI_SWITCH_SH
    result = subprocess.run(
        ["bash", str(script_path)] + args,
        capture_output=True, text=True, env=env,
        cwd=str(project_dir), timeout=15,
    )
    return result


class TestAiSwitchArgs:
    def test_help_flag(self, switch_env):
        """--help shows usage."""
        env, _, cwd, script = switch_env
        result = run_switch(["--help"], env, cwd, script=script)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_missing_domain(self, switch_env):
        """Missing --domain gives error."""
        env, _, cwd, script = switch_env
        result = run_switch([], env, cwd, script=script)
        assert result.returncode != 0
        assert "Missing" in result.stderr or "--domain" in result.stderr

    def test_domain_requires_value(self, switch_env):
        """--domain without value gives error."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain"], env, cwd, script=script)
        assert result.returncode != 0

    def test_unknown_option(self, switch_env):
        """Unknown option gives error."""
        env, _, cwd, script = switch_env
        result = run_switch(["--invalid"], env, cwd, script=script)
        assert result.returncode != 0


class TestAiSwitchDryRun:
    def test_dry_run_shows_plan(self, switch_env):
        """--dry-run shows what would happen without making changes."""
        env, log, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout or "Dry-run" in result.stdout

    def test_dry_run_with_no_flush(self, switch_env):
        """--dry-run --no-flush shows VRAM flush skipped."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "perso", "--dry-run", "--no-flush"], env, cwd, script=script)
        assert result.returncode == 0
        assert "skipped" in result.stdout.lower() or "DRY-RUN" in result.stdout


class TestAiSwitchValidation:
    def test_unknown_domain_rejected(self, switch_env):
        """Switching to unknown domain fails."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "nonexistent", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_ai_tools_self_switch_rejected(self, switch_env):
        """Cannot switch AI access to ai-tools itself."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "ai-tools", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0
        assert "ai-tools" in result.stderr

    def test_valid_domain_accepted(self, switch_env):
        """Switching to a valid domain succeeds (dry-run)."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "perso", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0

    def test_same_domain_noop(self, switch_env):
        """Switching to the current domain is a no-op."""
        env, _, cwd, script = switch_env
        # Create state file in patched location
        state_file = cwd / "ai-access-current"
        state_file.write_text("perso")
        result = run_switch(["--domain", "perso", "--dry-run"], env, cwd, script=script)
        # Should detect same domain and skip or report no-op
        assert result.returncode == 0


class TestAiSwitchInfraDirectory:
    def test_infra_directory_mode(self, switch_env):
        """ai-switch works with infra/ directory."""
        env, _, cwd, script = switch_env
        # Convert infra.yml to infra/ directory
        infra_data = yaml.safe_load((cwd / "infra.yml").read_text())
        (cwd / "infra.yml").unlink()
        infra_dir = cwd / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": infra_data["project_name"],
            "global": infra_data["global"],
        }, sort_keys=False))
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        for dname, dconf in infra_data["domains"].items():
            (domains_dir / f"{dname}.yml").write_text(
                yaml.dump({dname: dconf}, sort_keys=False),
            )
        result = run_switch(["--domain", "perso", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
