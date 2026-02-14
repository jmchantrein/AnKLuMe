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


# ── Static script content analysis ────────────────────────────────


class TestAiSwitchScriptStructure:
    """Verify the ai-switch.sh script structure and content (static analysis)."""

    def test_shebang_line(self):
        """Script starts with #!/usr/bin/env bash."""
        content = AI_SWITCH_SH.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_strict_mode(self):
        """Script enables strict bash mode (set -euo pipefail)."""
        content = AI_SWITCH_SH.read_text()
        assert "set -euo pipefail" in content

    def test_die_function_defined(self):
        """Script defines die() function for error handling."""
        content = AI_SWITCH_SH.read_text()
        assert "die()" in content
        assert "exit 1" in content

    def test_info_function_defined(self):
        """Script defines info() function for informational messages."""
        content = AI_SWITCH_SH.read_text()
        assert "info()" in content

    def test_warn_function_defined(self):
        """Script defines warn() function for warnings."""
        content = AI_SWITCH_SH.read_text()
        assert "warn()" in content

    def test_usage_function_defined(self):
        """Script defines usage() function."""
        content = AI_SWITCH_SH.read_text()
        assert "usage()" in content

    def test_domain_exists_function_defined(self):
        """Script defines domain_exists() validation function."""
        content = AI_SWITCH_SH.read_text()
        assert "domain_exists()" in content

    def test_default_flush_vram_true(self):
        """Default FLUSH_VRAM is true."""
        content = AI_SWITCH_SH.read_text()
        assert "FLUSH_VRAM=true" in content

    def test_default_dry_run_false(self):
        """Default DRY_RUN is false."""
        content = AI_SWITCH_SH.read_text()
        assert "DRY_RUN=false" in content

    def test_default_state_file_path(self):
        """Default STATE_FILE is /opt/anklume/ai-access-current."""
        content = AI_SWITCH_SH.read_text()
        assert 'STATE_FILE="/opt/anklume/ai-access-current"' in content

    def test_default_log_dir_path(self):
        """Default LOG_DIR is /var/log/anklume."""
        content = AI_SWITCH_SH.read_text()
        assert 'LOG_DIR="/var/log/anklume"' in content

    def test_log_file_derived_from_log_dir(self):
        """LOG_FILE is derived from LOG_DIR."""
        content = AI_SWITCH_SH.read_text()
        assert 'LOG_FILE="$LOG_DIR/ai-switch.log"' in content

    def test_ai_project_set_to_ai_tools(self):
        """AI_PROJECT is set to 'ai-tools'."""
        content = AI_SWITCH_SH.read_text()
        assert 'AI_PROJECT="ai-tools"' in content

    def test_services_list_ollama(self):
        """Script stops/starts ollama service."""
        content = AI_SWITCH_SH.read_text()
        assert "ollama" in content
        assert "systemctl stop" in content
        assert "systemctl start" in content

    def test_services_list_speaches(self):
        """Script stops/starts speaches service."""
        content = AI_SWITCH_SH.read_text()
        assert "speaches" in content

    def test_services_loop_pattern(self):
        """Script uses a for loop over services (ollama speaches)."""
        content = AI_SWITCH_SH.read_text()
        assert "for service in ollama speaches; do" in content

    def test_nvidia_smi_query_compute_apps(self):
        """VRAM flush queries GPU compute apps via nvidia-smi."""
        content = AI_SWITCH_SH.read_text()
        assert "--query-compute-apps=pid" in content

    def test_nvidia_smi_gpu_reset(self):
        """VRAM flush attempts GPU reset via nvidia-smi."""
        content = AI_SWITCH_SH.read_text()
        assert "--gpu-reset" in content

    def test_script_is_executable(self):
        """Script file has executable permission."""
        assert os.access(AI_SWITCH_SH, os.X_OK)

    def test_project_dir_resolution(self):
        """Script resolves PROJECT_DIR from script location."""
        content = AI_SWITCH_SH.read_text()
        assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content
        assert 'PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"' in content

    def test_mkdir_before_state_file(self):
        """Script creates parent directory of STATE_FILE."""
        content = AI_SWITCH_SH.read_text()
        assert 'mkdir -p "$(dirname "$STATE_FILE")"' in content

    def test_mkdir_before_log(self):
        """Script creates LOG_DIR before writing log."""
        content = AI_SWITCH_SH.read_text()
        assert 'mkdir -p "$LOG_DIR"' in content


class TestAiSwitchUsageContent:
    """Verify usage/help text content."""

    def test_usage_mentions_domain_option(self):
        """Usage text describes --domain option."""
        content = AI_SWITCH_SH.read_text()
        assert "--domain <name>" in content

    def test_usage_mentions_no_flush(self):
        """Usage text describes --no-flush option."""
        content = AI_SWITCH_SH.read_text()
        assert "--no-flush" in content

    def test_usage_mentions_dry_run(self):
        """Usage text describes --dry-run option."""
        content = AI_SWITCH_SH.read_text()
        assert "--dry-run" in content

    def test_usage_mentions_help(self):
        """Usage text describes -h/--help option."""
        content = AI_SWITCH_SH.read_text()
        assert "-h, --help" in content

    def test_usage_contains_example(self):
        """Usage text contains an example command."""
        content = AI_SWITCH_SH.read_text()
        assert "Example:" in content
        assert "ai-switch.sh --domain pro" in content

    def test_usage_describes_exclusive_access(self):
        """Usage text explains exclusive access concept."""
        content = AI_SWITCH_SH.read_text()
        assert "Only one domain can access ai-tools at a time" in content

    def test_help_output_contains_all_options(self, switch_env):
        """--help output contains all documented options."""
        env, _, cwd, script = switch_env
        result = run_switch(["--help"], env, cwd, script=script)
        assert "--domain" in result.stdout
        assert "--no-flush" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--help" in result.stdout

    def test_help_exit_code_zero(self, switch_env):
        """-h exits with code 0."""
        env, _, cwd, script = switch_env
        result = run_switch(["-h"], env, cwd, script=script)
        assert result.returncode == 0

    def test_short_help_flag(self, switch_env):
        """-h short flag shows usage (same as --help)."""
        env, _, cwd, script = switch_env
        result = run_switch(["-h"], env, cwd, script=script)
        assert "Usage" in result.stdout


# ── Error message format tests ─────────────────────────────────────


class TestAiSwitchErrorMessages:
    """Verify error messages format and content."""

    def test_error_prefix_format(self):
        """die() outputs 'ERROR:' prefix to stderr."""
        content = AI_SWITCH_SH.read_text()
        assert '"ERROR: $*"' in content

    def test_info_prefix_format(self):
        """info() outputs 'INFO:' prefix to stdout."""
        content = AI_SWITCH_SH.read_text()
        assert '"INFO: $*"' in content

    def test_warn_prefix_format(self):
        """warn() outputs 'WARNING:' prefix to stderr."""
        content = AI_SWITCH_SH.read_text()
        assert '"WARNING: $*"' in content

    def test_missing_domain_error_mentions_help(self, switch_env):
        """Missing domain error message mentions --help."""
        env, _, cwd, script = switch_env
        result = run_switch([], env, cwd, script=script)
        assert result.returncode != 0
        assert "--help" in result.stderr

    def test_unknown_domain_error_includes_domain_name(self, switch_env):
        """Error for unknown domain includes the domain name."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "bogus", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0
        assert "bogus" in result.stderr

    def test_unknown_argument_error_includes_argument(self, switch_env):
        """Error for unknown argument includes the bad argument name."""
        env, _, cwd, script = switch_env
        result = run_switch(["--foobar"], env, cwd, script=script)
        assert result.returncode != 0
        assert "--foobar" in result.stderr

    def test_ai_tools_self_switch_error_message(self, switch_env):
        """Cannot switch to ai-tools error is descriptive."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "ai-tools", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0
        assert "Cannot" in result.stderr

    def test_domain_requires_value_error(self, switch_env):
        """--domain without a value shows error."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain"], env, cwd, script=script)
        assert result.returncode != 0
        assert "requires" in result.stderr.lower() or result.returncode != 0

    def test_error_messages_go_to_stderr(self, switch_env):
        """Error output goes to stderr, not stdout."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "nonexistent", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0
        assert result.stderr.strip() != ""

    def test_info_messages_go_to_stdout(self, switch_env):
        """Informational output goes to stdout."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
        assert "INFO:" in result.stdout

    def test_warn_messages_go_to_stderr(self):
        """warn() function writes to stderr (>&2)."""
        content = AI_SWITCH_SH.read_text()
        # warn uses >&2
        assert ">&2" in content


# ── Flag parsing edge cases ────────────────────────────────────────


class TestAiSwitchFlagParsing:
    """Test argument parsing edge cases."""

    def test_all_three_flags_together(self, switch_env):
        """--domain, --dry-run, --no-flush all accepted together."""
        env, _, cwd, script = switch_env
        result = run_switch(
            ["--domain", "pro", "--dry-run", "--no-flush"], env, cwd, script=script,
        )
        assert result.returncode == 0

    def test_flags_order_independence_dry_first(self, switch_env):
        """Flags work regardless of order (--dry-run before --domain)."""
        env, _, cwd, script = switch_env
        result = run_switch(
            ["--dry-run", "--domain", "pro"], env, cwd, script=script,
        )
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout

    def test_flags_order_independence_no_flush_first(self, switch_env):
        """Flags work regardless of order (--no-flush before --domain)."""
        env, _, cwd, script = switch_env
        result = run_switch(
            ["--no-flush", "--domain", "perso", "--dry-run"], env, cwd, script=script,
        )
        assert result.returncode == 0

    def test_domain_as_last_argument(self, switch_env):
        """--domain as the last pair of arguments works."""
        env, _, cwd, script = switch_env
        result = run_switch(
            ["--dry-run", "--no-flush", "--domain", "perso"], env, cwd, script=script,
        )
        assert result.returncode == 0

    def test_double_domain_uses_last(self, switch_env):
        """If --domain is specified twice, the last value wins."""
        env, _, cwd, script = switch_env
        result = run_switch(
            ["--domain", "pro", "--domain", "perso", "--dry-run"], env, cwd, script=script,
        )
        assert result.returncode == 0
        # The output should reference perso (the last one)
        assert "perso" in result.stdout


# ── Dry-run output details ─────────────────────────────────────────


class TestAiSwitchDryRunOutput:
    """Detailed dry-run output content verification."""

    def test_dry_run_prefix_in_output(self, switch_env):
        """Dry-run output lines contain [DRY-RUN] prefix."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert "[DRY-RUN]" in result.stdout

    def test_dry_run_shows_target_domain(self, switch_env):
        """Dry-run output shows the target domain."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "perso", "--dry-run"], env, cwd, script=script)
        assert "perso" in result.stdout

    def test_dry_run_shows_source_none(self, switch_env):
        """Dry-run shows '<none>' when no previous state exists."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert "<none>" in result.stdout

    def test_dry_run_shows_source_domain(self, switch_env):
        """Dry-run shows previous domain when state file exists."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "perso", "--dry-run"], env, cwd, script=script)
        assert "pro" in result.stdout
        assert "perso" in result.stdout

    def test_dry_run_shows_flush_enabled(self, switch_env):
        """Dry-run output indicates VRAM flush status (enabled)."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert "flush" in result.stdout.lower()
        assert "enabled" in result.stdout.lower()

    def test_dry_run_shows_flush_skipped(self, switch_env):
        """Dry-run output indicates VRAM flush status (skipped)."""
        env, _, cwd, script = switch_env
        result = run_switch(
            ["--domain", "pro", "--dry-run", "--no-flush"], env, cwd, script=script,
        )
        assert "skipped" in result.stdout.lower()

    def test_dry_run_no_changes_message(self, switch_env):
        """Dry-run prints 'No changes made' message."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert "No changes made" in result.stdout

    def test_dry_run_does_not_call_incus_exec(self, switch_env):
        """Dry-run does not invoke incus exec (no service operations)."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
        if log_file.exists():
            log_content = log_file.read_text()
            assert "systemctl" not in log_content

    def test_dry_run_does_not_call_ansible(self, switch_env):
        """Dry-run does not invoke ansible-playbook."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0
        if log_file.exists():
            log_content = log_file.read_text()
            assert "ansible-playbook" not in log_content


# ── nftables update pattern tests ──────────────────────────────────


class TestAiSwitchNftablesUpdate:
    """Verify nftables update details during switch."""

    def test_ansible_called_with_site_yml(self, switch_env):
        """ansible-playbook is called with site.yml."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "site.yml" in log_content

    def test_override_contains_to_bridge_ai_tools(self, switch_env):
        """nftables override references net-ai-tools as destination."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "net-ai-tools" in log_content

    def test_override_contains_from_bridge_target_domain(self, switch_env):
        """nftables override references the target domain's bridge."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "net-perso" in log_content

    def test_override_contains_ports_all(self, switch_env):
        """nftables override specifies ports: all."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        # The JSON override should have "ports":"all"
        assert '"ports":"all"' in log_content or '"ports": "all"' in log_content

    def test_override_contains_protocol_tcp(self, switch_env):
        """nftables override specifies protocol: tcp."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert '"protocol":"tcp"' in log_content or '"protocol": "tcp"' in log_content

    def test_override_json_structure(self):
        """Script passes a proper JSON structure for ai_override."""
        content = AI_SWITCH_SH.read_text()
        # The override is a JSON dict with from_bridge, to_bridge, ports, protocol
        assert "from_bridge" in content
        assert "to_bridge" in content
        assert "ports" in content
        assert "protocol" in content

    def test_bridge_naming_pattern(self):
        """Script uses 'net-<domain>' naming convention for bridges."""
        content = AI_SWITCH_SH.read_text()
        assert "net-${DOMAIN}" in content or "net-$DOMAIN" in content
        assert "net-ai-tools" in content


# ── Logging format tests ──────────────────────────────────────────


class TestAiSwitchLogFormat:
    """Verify log file format details."""

    def test_log_contains_iso_timestamp(self, switch_env):
        """Log line starts with an ISO 8601 timestamp."""
        import re
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        # ISO 8601 date format: YYYY-MM-DDTHH:MM:SS+...
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", content)

    def test_log_uses_date_iso_format(self):
        """Script uses 'date -Is' for ISO timestamp."""
        content = AI_SWITCH_SH.read_text()
        assert "date -Is" in content

    def test_log_contains_switched_text(self, switch_env):
        """Log line contains 'switched ai-tools access:' text."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "switched ai-tools access:" in content

    def test_log_contains_arrow_transition(self, switch_env):
        """Log line contains '->' transition notation."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "-> 'pro'" in content

    def test_log_shows_none_for_first_switch(self, switch_env):
        """Log shows '<none>' when no previous state exists."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "perso"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "'<none>'" in content

    def test_log_shows_previous_domain(self, switch_env):
        """Log shows previous domain in transition when state exists."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        run_switch(["--domain", "perso"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        assert "'pro' -> 'perso'" in content

    def test_log_appends_with_redirect(self):
        """Script appends to log file using >> redirect."""
        content = AI_SWITCH_SH.read_text()
        assert '>> "$LOG_FILE"' in content

    def test_log_dir_created_before_write(self, switch_env):
        """LOG_DIR directory is created before writing log."""
        env, _, cwd, script = switch_env
        log_dir = cwd / "logs"
        assert not log_dir.exists()
        run_switch(["--domain", "pro"], env, cwd, script=script)
        assert log_dir.is_dir()


# ── Execution sequence tests ──────────────────────────────────────


class TestAiSwitchExecutionSequence:
    """Verify the correct ordering of operations during a switch."""

    def test_stop_before_flush(self, switch_env):
        """Services are stopped before VRAM flush."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        lines = log_content.strip().split("\n")
        # Find first systemctl stop and first nvidia-smi
        first_stop = next((i for i, ln in enumerate(lines) if "systemctl stop" in ln), None)
        first_nvidia = next((i for i, ln in enumerate(lines) if "nvidia-smi" in ln), None)
        assert first_stop is not None, "Expected systemctl stop in log"
        assert first_nvidia is not None, "Expected nvidia-smi in log"
        assert first_stop < first_nvidia, "stop should come before flush"

    def test_flush_before_nftables(self, switch_env):
        """VRAM flush happens before nftables update."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        lines = log_content.strip().split("\n")
        first_nvidia = next((i for i, ln in enumerate(lines) if "nvidia-smi" in ln), None)
        first_ansible = next((i for i, ln in enumerate(lines) if "ansible-playbook" in ln), None)
        assert first_nvidia is not None, "Expected nvidia-smi in log"
        assert first_ansible is not None, "Expected ansible-playbook in log"
        assert first_nvidia < first_ansible, "flush should come before nftables"

    def test_nftables_before_restart(self, switch_env):
        """nftables update happens before service restart."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        lines = log_content.strip().split("\n")
        first_ansible = next((i for i, ln in enumerate(lines) if "ansible-playbook" in ln), None)
        # Find systemctl start AFTER the ansible call
        start_lines = [i for i, ln in enumerate(lines) if "systemctl start" in ln]
        assert first_ansible is not None, "Expected ansible-playbook in log"
        assert len(start_lines) > 0, "Expected systemctl start in log"
        assert start_lines[-1] > first_ansible, "restart should come after nftables"

    def test_project_list_is_first_incus_call(self, switch_env):
        """incus project list (daemon check) is the first incus call."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        lines = log_content.strip().split("\n")
        first_incus = next((i for i, ln in enumerate(lines) if ln.startswith("incus ")), None)
        assert first_incus is not None
        assert "project list" in lines[first_incus]


# ── VRAM flush details tests ──────────────────────────────────────


class TestAiSwitchFlushDetails:
    """Detailed VRAM flush behavior tests."""

    def test_flush_uses_xargs_kill(self):
        """VRAM flush pipes nvidia-smi output to xargs kill -9."""
        content = AI_SWITCH_SH.read_text()
        assert "xargs -r kill -9" in content

    def test_flush_executes_in_ai_container(self):
        """VRAM flush commands execute in ai-ollama container."""
        content = AI_SWITCH_SH.read_text()
        assert "incus exec ai-ollama" in content

    def test_flush_uses_ai_project(self):
        """VRAM flush uses the AI_PROJECT for incus exec."""
        content = AI_SWITCH_SH.read_text()
        assert '--project "$AI_PROJECT"' in content

    def test_no_flush_skips_nvidia_smi(self, switch_env):
        """--no-flush does not invoke nvidia-smi at all."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--no-flush"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "nvidia-smi" not in log_content

    def test_flush_reports_vram_flush_message(self, switch_env):
        """Flush outputs 'Flushing VRAM...' message."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        assert "Flushing VRAM" in result.stdout

    def test_flush_reports_completion(self, switch_env):
        """Flush outputs 'VRAM flush complete' message."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        assert "VRAM flush complete" in result.stdout

    def test_gpu_reset_failure_is_non_fatal(self):
        """GPU reset failure is non-fatal (uses || warn)."""
        content = AI_SWITCH_SH.read_text()
        assert "GPU reset not supported" in content
        assert "non-fatal" in content.lower()


# ── Infra source resolution tests ─────────────────────────────────


class TestAiSwitchInfraResolution:
    """Test infra.yml vs infra/ resolution logic."""

    def test_missing_infra_source_fails(self, switch_env):
        """Fails if neither infra.yml nor infra/ exists."""
        env, _, cwd, script = switch_env
        # Remove both potential sources
        infra_yml = cwd / "infra.yml"
        infra_dir = cwd / "infra"
        if infra_yml.exists():
            infra_yml.unlink()
        if infra_dir.exists():
            import shutil
            shutil.rmtree(infra_dir)
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0
        assert "infra" in result.stderr.lower()

    def test_infra_yml_preferred_over_nothing(self, switch_env):
        """infra.yml is used when present."""
        env, _, cwd, script = switch_env
        assert (cwd / "infra.yml").exists()
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0

    def test_infra_dir_works_with_all_domains(self, switch_env):
        """infra/ directory mode validates all domains correctly."""
        env, _, cwd, script = switch_env
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
        # All non-ai-tools domains should be valid targets
        for domain in ["pro", "perso", "admin"]:
            result = run_switch(["--domain", domain, "--dry-run"], env, cwd, script=script)
            assert result.returncode == 0, f"Domain '{domain}' should be valid"


# ── Stdout/stderr message content tests ────────────────────────────


class TestAiSwitchOutputMessages:
    """Verify stdout/stderr message content during operations."""

    def test_switching_info_message(self, switch_env):
        """Output shows 'Switching AI-tools access' during switch."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro", "--dry-run"], env, cwd, script=script)
        assert "Switching AI-tools access" in result.stdout

    def test_stopping_services_message(self, switch_env):
        """Output shows 'Stopping GPU services' during switch."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert "Stopping GPU services" in result.stdout

    def test_restarting_services_message(self, switch_env):
        """Output shows 'Restarting GPU services' during switch."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert "Restarting GPU services" in result.stdout

    def test_updating_nftables_message(self, switch_env):
        """Output shows 'Updating nftables rules' during switch."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert "Updating nftables rules" in result.stdout

    def test_success_message_includes_domain(self, switch_env):
        """Success message includes the target domain name."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        assert "perso" in result.stdout
        assert "successfully" in result.stdout.lower()

    def test_noop_message_includes_domain(self, switch_env):
        """No-op message includes the domain name."""
        env, _, cwd, script = switch_env
        state_file = cwd / "ai-access-current"
        state_file.write_text("pro")
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        assert "pro" in result.stdout

    def test_nftables_message_mentions_domains(self, switch_env):
        """nftables update message mentions both source and target."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        assert "perso" in result.stdout
        assert "ai-tools" in result.stdout


# ── Incus daemon connectivity tests ───────────────────────────────


class TestAiSwitchIncusDaemon:
    """Test Incus daemon pre-flight check."""

    def test_incus_daemon_check_runs_before_operations(self, switch_env):
        """Pre-flight Incus check is performed before any operations."""
        env, log_file, cwd, script = switch_env
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode == 0
        log_content = log_file.read_text()
        assert "project list" in log_content

    def test_incus_daemon_failure_blocks_switch(self, switch_env):
        """If incus daemon is unreachable, switch fails."""
        env, log_file, cwd, script = switch_env
        # Replace mock incus with one that fails on project list
        mock_bin = cwd.parent / "bin"
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "project" ]]; then
    exit 1
fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | 0o111)
        result = run_switch(["--domain", "pro"], env, cwd, script=script)
        assert result.returncode != 0
        assert "Incus daemon" in result.stderr or "Cannot connect" in result.stderr

    def test_incus_daemon_check_uses_csv_format(self):
        """Daemon check uses --format csv for minimal output."""
        content = AI_SWITCH_SH.read_text()
        assert "project list --format csv" in content


# ── Service stop/start detail tests ───────────────────────────────


class TestAiSwitchServiceManagement:
    """Verify service stop/start behavior."""

    def test_stops_ollama_service(self, switch_env):
        """Switch stops the ollama service."""
        env, log_file, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_content = log_file.read_text()
        assert "systemctl stop ollama" in log_content

    def test_stops_speaches_service(self, switch_env):
        """Switch stops the speaches service."""
        env, log_file, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_content = log_file.read_text()
        assert "systemctl stop speaches" in log_content

    def test_starts_ollama_service(self, switch_env):
        """Switch restarts the ollama service."""
        env, log_file, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_content = log_file.read_text()
        assert "systemctl start ollama" in log_content

    def test_starts_speaches_service(self, switch_env):
        """Switch restarts the speaches service."""
        env, log_file, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_content = log_file.read_text()
        assert "systemctl start speaches" in log_content

    def test_services_stopped_gracefully(self):
        """Service stop failures are non-fatal (uses || true)."""
        content = AI_SWITCH_SH.read_text()
        # Both stop and start loops use || true
        assert "2>/dev/null || true" in content

    def test_services_run_in_ai_project(self, switch_env):
        """Service operations target the ai-tools project."""
        env, log_file, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_content = log_file.read_text()
        assert "--project ai-tools" in log_content

    def test_services_run_on_ai_ollama(self, switch_env):
        """Service operations target the ai-ollama instance."""
        env, log_file, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        log_content = log_file.read_text()
        assert "ai-ollama" in log_content


# ── State file content detail tests ───────────────────────────────


class TestAiSwitchStateFileContent:
    """Detailed state file content verification."""

    def test_state_file_contains_only_domain_name(self, switch_env):
        """State file contains just the domain name and a newline."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        state_file = cwd / "ai-access-current"
        raw = state_file.read_text()
        assert raw == "pro\n"

    def test_state_file_read_by_subsequent_switch(self, switch_env):
        """State file from previous switch is read correctly."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        result = run_switch(["--domain", "perso"], env, cwd, script=script)
        assert result.returncode == 0
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        # Second switch should show 'pro' -> 'perso'
        assert "'pro' -> 'perso'" in content

    def test_state_file_overwritten_not_appended(self, switch_env):
        """State file is overwritten (not appended) on each switch."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        run_switch(["--domain", "perso"], env, cwd, script=script)
        state_file = cwd / "ai-access-current"
        raw = state_file.read_text()
        assert raw == "perso\n"
        assert "pro" not in raw


# ── Validation edge cases ─────────────────────────────────────────


class TestAiSwitchValidationEdgeCases:
    """Edge cases for domain validation."""

    def test_admin_domain_accepted(self, switch_env):
        """admin domain is a valid target (not blocked like ai-tools)."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "admin", "--dry-run"], env, cwd, script=script)
        assert result.returncode == 0

    def test_all_non_ai_domains_accepted(self, switch_env):
        """All non-ai-tools domains from infra.yml are valid targets."""
        env, _, cwd, script = switch_env
        for domain in ["admin", "pro", "perso"]:
            result = run_switch(["--domain", domain, "--dry-run"], env, cwd, script=script)
            assert result.returncode == 0, f"Domain '{domain}' should be accepted"

    def test_case_sensitive_domain(self, switch_env):
        """Domain matching is case-sensitive (PRO != pro)."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "PRO", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0

    def test_empty_domain_value(self, switch_env):
        """Empty string as domain value is rejected."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0

    def test_domain_with_spaces_rejected(self, switch_env):
        """Domain with spaces is rejected."""
        env, _, cwd, script = switch_env
        result = run_switch(["--domain", "my domain", "--dry-run"], env, cwd, script=script)
        assert result.returncode != 0


# ── Script comments and documentation ─────────────────────────────


class TestAiSwitchScriptDocumentation:
    """Verify script contains proper inline documentation."""

    def test_script_has_usage_comment(self):
        """Script header contains usage comment."""
        content = AI_SWITCH_SH.read_text()
        lines = content.split("\n")
        # One of the first few lines should describe usage
        first_lines = "\n".join(lines[:5])
        assert "Usage" in first_lines or "ai-switch" in first_lines

    def test_step_comments_present(self):
        """Script has numbered step comments."""
        content = AI_SWITCH_SH.read_text()
        assert "Step 1" in content
        assert "Step 2" in content
        assert "Step 3" in content
        assert "Step 4" in content
        assert "Step 5" in content
        assert "Step 6" in content

    def test_step_1_is_stop_services(self):
        """Step 1 is about stopping GPU services."""
        content = AI_SWITCH_SH.read_text()
        assert "Step 1" in content
        # Find the step 1 comment
        idx = content.index("Step 1")
        step_context = content[idx:idx + 80]
        assert "Stop" in step_context or "stop" in step_context

    def test_step_2_is_flush_vram(self):
        """Step 2 is about flushing VRAM."""
        content = AI_SWITCH_SH.read_text()
        idx = content.index("Step 2")
        step_context = content[idx:idx + 80]
        assert "Flush" in step_context or "VRAM" in step_context

    def test_step_3_is_nftables(self):
        """Step 3 is about nftables update."""
        content = AI_SWITCH_SH.read_text()
        idx = content.index("Step 3")
        step_context = content[idx:idx + 80]
        assert "nftables" in step_context

    def test_step_4_is_restart(self):
        """Step 4 is about restarting services."""
        content = AI_SWITCH_SH.read_text()
        idx = content.index("Step 4")
        step_context = content[idx:idx + 80]
        assert "Restart" in step_context or "restart" in step_context

    def test_step_5_is_state(self):
        """Step 5 is about recording state."""
        content = AI_SWITCH_SH.read_text()
        idx = content.index("Step 5")
        step_context = content[idx:idx + 80]
        assert "state" in step_context.lower() or "Record" in step_context

    def test_step_6_is_log(self):
        """Step 6 is about logging."""
        content = AI_SWITCH_SH.read_text()
        idx = content.index("Step 6")
        step_context = content[idx:idx + 80]
        assert "Log" in step_context or "log" in step_context


# ── Multiple switch cycles ────────────────────────────────────────


class TestAiSwitchMultipleCycles:
    """Test multiple consecutive switches."""

    def test_three_consecutive_switches(self, switch_env):
        """Three consecutive switches all succeed."""
        env, _, cwd, script = switch_env
        for domain in ["pro", "perso", "admin"]:
            result = run_switch(["--domain", domain], env, cwd, script=script)
            assert result.returncode == 0, f"Switch to {domain} failed"

    def test_three_switches_correct_final_state(self, switch_env):
        """After three switches, state file reflects the last switch."""
        env, _, cwd, script = switch_env
        for domain in ["pro", "perso", "admin"]:
            run_switch(["--domain", domain], env, cwd, script=script)
        state_file = cwd / "ai-access-current"
        assert state_file.read_text().strip() == "admin"

    def test_three_switches_three_log_entries(self, switch_env):
        """Three switches produce three log entries."""
        env, _, cwd, script = switch_env
        for domain in ["pro", "perso", "admin"]:
            run_switch(["--domain", domain], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        content = log_file.read_text()
        entries = [ln for ln in content.strip().split("\n") if ln.strip()]
        assert len(entries) == 3

    def test_switch_back_and_forth(self, switch_env):
        """Switching back and forth between two domains works."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        run_switch(["--domain", "perso"], env, cwd, script=script)
        run_switch(["--domain", "pro"], env, cwd, script=script)
        state_file = cwd / "ai-access-current"
        assert state_file.read_text().strip() == "pro"

    def test_log_tracks_all_transitions(self, switch_env):
        """Log file tracks correct transitions across switches."""
        env, _, cwd, script = switch_env
        run_switch(["--domain", "pro"], env, cwd, script=script)
        run_switch(["--domain", "perso"], env, cwd, script=script)
        run_switch(["--domain", "admin"], env, cwd, script=script)
        log_file = cwd / "logs" / "ai-switch.log"
        lines = log_file.read_text().strip().split("\n")
        assert "'<none>' -> 'pro'" in lines[0]
        assert "'pro' -> 'perso'" in lines[1]
        assert "'perso' -> 'admin'" in lines[2]


# ── Python domain validation function tests ───────────────────────


class TestAiSwitchDomainValidation:
    """Test the domain_exists() Python inline function."""

    def test_domain_exists_uses_python3(self):
        """domain_exists() calls python3 for YAML parsing."""
        content = AI_SWITCH_SH.read_text()
        assert "python3 -c" in content

    def test_domain_exists_imports_yaml(self):
        """domain_exists() imports yaml module."""
        content = AI_SWITCH_SH.read_text()
        assert "import sys, yaml" in content or "import yaml" in content

    def test_domain_exists_handles_directory(self):
        """domain_exists() handles both file and directory infra sources."""
        content = AI_SWITCH_SH.read_text()
        assert "p.is_file()" in content
        assert "p.is_dir()" in content

    def test_domain_exists_checks_domains_key(self):
        """domain_exists() checks the 'domains' key in data."""
        content = AI_SWITCH_SH.read_text()
        assert "data.get('domains')" in content or "data['domains']" in content

    def test_domain_validation_before_ai_tools_check(self):
        """Domain existence is validated before the ai-tools self-switch check."""
        content = AI_SWITCH_SH.read_text()
        exists_pos = content.index("domain_exists")
        ai_tools_pos = content.index('"$DOMAIN" != "ai-tools"')
        assert exists_pos < ai_tools_pos
