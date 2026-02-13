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


# ── New comprehensive test classes ─────────────────────────────────


class TestAiSwitchExecution:
    """Test the full switch cycle with mock binaries."""

    def test_full_switch_calls_incus_and_ansible(self, switch_env):
        """Full switch invokes incus (stop/start services) and ansible-playbook (nftables)."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        # incus should be called (project list, exec for stop/start, nvidia-smi)
        assert "incus" in log_content
        # ansible-playbook should be called for nftables update
        assert "ansible-playbook" in log_content

    def test_switch_calls_ansible_with_nftables_tag(self, switch_env):
        """Switch passes --tags nftables to ansible-playbook."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "--tags nftables" in log_content

    def test_switch_passes_ai_override_to_ansible(self, switch_env):
        """Switch passes incus_nftables_ai_override extra-var."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "incus_nftables_ai_override" in log_content
        # The override should reference the target domain bridge
        assert "net-pro" in log_content

    def test_switch_stops_and_starts_gpu_services(self, switch_env):
        """Switch stops GPU services before and restarts them after."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        # Should call systemctl stop and start for services
        assert "systemctl" in log_content

    def test_switch_to_different_domain_succeeds(self, switch_env):
        """Switching from one domain to another completes successfully."""
        env, log_file, cwd, script = switch_env
        # Set initial state
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        assert "successfully" in result.stdout.lower() or "switched" in result.stdout.lower()

    def test_switch_incus_project_list_check(self, switch_env):
        """Switch verifies Incus daemon accessibility via project list."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "project list" in log_content


class TestAiSwitchStateFile:
    """Verify /opt/anklume/ai-access-current is written correctly."""

    def test_state_file_created_after_switch(self, switch_env):
        """State file is created with the new domain name after switch."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        assert not state_file.exists()
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        assert state_file.exists()
        assert state_file.read_text().strip() == "pro"

    def test_state_file_updated_on_second_switch(self, switch_env):
        """State file is updated when switching to a different domain."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        assert state_file.read_text().strip() == "perso"

    def test_state_file_not_written_on_dry_run(self, switch_env):
        """State file is NOT created in dry-run mode."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
        assert not state_file.exists()

    def test_state_file_not_written_on_error(self, switch_env):
        """State file is NOT updated when domain is invalid."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "nonexistent"], env, cwd, script=script)
        assert result.returncode != 0
        assert state_file.read_text().strip() == "pro"

    def test_state_file_parent_dir_created(self, switch_env):
        """State file parent directory is created if missing."""
        env, _, cwd, script = switch_env
        # Re-patch state file to a nested path
        patched_switch = cwd / "scripts" / "ai-switch.sh"
        content = patched_switch.read_text()
        nested_state = cwd / "nested" / "deep" / "ai-access-current"
        content = content.replace(
            f'STATE_FILE="{cwd}/ai-access-current"',
            f'STATE_FILE="{nested_state}"',
        )
        patched_switch.write_text(content)
        result = run_switch(["--domain", "pro"], env, cwd, script=patched_switch)
        assert result.returncode == 0
        assert nested_state.exists()
        assert nested_state.read_text().strip() == "pro"


class TestAiSwitchLogging:
    """Verify log file appending."""

    def test_log_file_created_after_switch(self, switch_env):
        """Log file is created in LOG_DIR after a switch."""
        env, _, cwd, script = switch_env
        log_dir = cwd / "logs"
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        assert log_dir.is_dir()
        log_file = log_dir / "ai-switch.log"
        assert log_file.exists()

    def test_log_file_contains_switch_info(self, switch_env):
        """Log file contains domain switch information."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "pro" in content
        assert "switched" in content

    def test_log_file_appends_on_second_switch(self, switch_env):
        """Log file appends new entries (does not overwrite)."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        run_switch(["--domain", "perso"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        lines = [line for line in content.strip().split("\n") if line.strip()]
        assert len(lines) >= 2, f"Expected at least 2 log lines, got {len(lines)}"

    def test_log_file_contains_flush_status(self, switch_env):
        """Log file records whether VRAM flush was performed."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "flush=" in content

    def test_log_not_written_on_dry_run(self, switch_env):
        """Log file is NOT written in dry-run mode."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
        log_file = cwd / "logs" / "ai-switch.log"
        assert not log_file.exists()


class TestAiSwitchGpuFlush:
    """Mock nvidia-smi, test VRAM flush with --no-flush flag."""

    def test_flush_enabled_by_default(self, switch_env):
        """VRAM flush runs by default (without --no-flush)."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        output = result.stdout
        # Should mention flushing or VRAM
        assert "flush" in output.lower() or "vram" in output.lower()

    def test_flush_calls_nvidia_smi(self, switch_env):
        """VRAM flush invokes nvidia-smi via incus exec."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        # incus exec should reference nvidia-smi
        assert "nvidia-smi" in log_content

    def test_no_flush_skips_vram_operations(self, switch_env):
        """--no-flush skips VRAM flush operations."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--no-flush"], env, cwd, script=script)
        assert result.returncode == 0
        output = result.stdout
        # Should NOT mention VRAM flushing as active
        assert "Flushing VRAM" not in output
        # But should still complete
        assert "successfully" in output.lower() or "switched" in output.lower()

    def test_no_flush_still_stops_services(self, switch_env):
        """--no-flush still stops and restarts GPU services."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--no-flush"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        # Services should still be stopped/started even without flush
        assert "systemctl" in log_content

    def test_flush_log_records_true(self, switch_env):
        """Log records flush=true when flushing."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "flush=true" in content

    def test_no_flush_log_records_false(self, switch_env):
        """Log records flush=false when --no-flush is used."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro", "--no-flush"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "flush=false" in content


class TestAiSwitchAlreadyCurrent:
    """Test 'already at current domain' no-op path."""

    def test_same_domain_is_noop(self, switch_env):
        """Switching to the already-current domain exits early."""
        env, log_file, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        assert "already" in result.stdout.lower()

    def test_same_domain_does_not_call_incus_exec(self, switch_env):
        """No-op path does not call incus exec (no service stop/start)."""
        env, log_file, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        # The log_file should only contain the incus project list check
        # or no exec calls at all (the noop exits before incus exec)
        if log_file.exists():
            log_content = log_file.read_text()
            assert "systemctl stop" not in log_content
            assert "ansible-playbook" not in log_content

    def test_same_domain_does_not_update_state_file(self, switch_env):
        """No-op path does not rewrite the state file."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        mtime_before = state_file.stat().st_mtime
        import time
        time.sleep(0.05)
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        # State file should NOT be rewritten
        mtime_after = state_file.stat().st_mtime
        assert mtime_before == mtime_after

    def test_same_domain_does_not_write_log(self, switch_env):
        """No-op path does not append to the switch log."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_file = cwd / "logs" / "ai-switch.log"
        assert not log_file.exists()

    def test_different_domain_is_not_noop(self, switch_env):
        """Switching to a different domain from current proceeds normally."""
        env, log_file, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        assert "already" not in result.stdout.lower()
        assert state_file.read_text().strip() == "perso"
