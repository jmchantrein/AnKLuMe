"""Tests for scripts/bootstrap.sh — system initialization."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

BOOTSTRAP_SH = Path(__file__).resolve().parent.parent / "scripts" / "bootstrap.sh"


def _make_patched_bootstrap(tmp_path):
    """Create a patched bootstrap.sh that writes to tmp instead of /etc/anklume."""
    etc_anklume = tmp_path / "etc_anklume"
    etc_anklume.mkdir(exist_ok=True)
    patched = tmp_path / "bootstrap_patched.sh"
    original = BOOTSTRAP_SH.read_text()
    patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
    patched.chmod(patched.stat().st_mode | stat.S_IEXEC)
    return patched, etc_anklume


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock environment for bootstrap testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Mock systemd-detect-virt
    mock_virt = mock_bin / "systemd-detect-virt"
    mock_virt.write_text(f'#!/usr/bin/env bash\necho "$@" >> "{log_file}"\necho "none"\n')
    mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

    # Mock incus (enough for bootstrap to pass)
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then
    exit 0
fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then
    exit 0
fi
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    exit 0
fi
exit 0
""")
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Mock other commands that bootstrap checks
    for cmd in ["ansible-playbook", "ansible-lint", "yamllint", "pip3"]:
        mock_cmd = mock_bin / cmd
        mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

    # Mock python3 to pass through
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    patched_bootstrap, etc_anklume = _make_patched_bootstrap(tmp_path)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path, patched_bootstrap, etc_anklume


def run_bootstrap(args, env, script=None, cwd=None, input_text=None):
    """Run bootstrap.sh with given args."""
    script_path = script or BOOTSTRAP_SH
    result = subprocess.run(
        ["bash", str(script_path)] + args,
        capture_output=True, text=True, env=env, cwd=cwd,
        input=input_text, timeout=30,
    )
    return result


# ── help and argument parsing ─────────────────────────────


class TestBootstrapArgs:
    def test_help_flag(self):
        """--help shows usage and exits 0."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_no_mode_shows_error(self):
        """Running without --prod or --dev shows error."""
        result = run_bootstrap([], os.environ.copy())
        assert result.returncode != 0 or "ERROR" in result.stdout

    def test_unknown_option(self):
        """Unknown option shows usage."""
        result = run_bootstrap(["--invalid"], os.environ.copy())
        assert result.returncode != 0 or "Unknown" in result.stdout


# ── dev mode ──────────────────────────────────────────────


class TestBootstrapDev:
    def test_dev_mode_completes(self, mock_env):
        """--dev completes successfully with mock Incus."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Bootstrap complete" in result.stdout

    def test_dev_mode_creates_context_files(self, mock_env):
        """--dev creates context files."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").exists()
        assert (etc / "relative_level").exists()
        assert (etc / "vm_nested").exists()
        assert (etc / "yolo").exists()
        assert (etc / "absolute_level").read_text().strip() == "0"
        assert (etc / "vm_nested").read_text().strip() == "false"

    def test_dev_mode_detects_virtualization(self, mock_env):
        """--dev detects virtualization type."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "Detected virtualization:" in result.stdout

    def test_dev_mode_shows_next_steps(self, mock_env):
        """--dev shows next steps after completion."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "Next steps" in result.stdout


# ── prod mode ─────────────────────────────────────────────


class TestBootstrapProd:
    def test_prod_mode_completes(self, mock_env):
        """--prod completes with mock Incus already initialized."""
        env, _, cwd, script, _ = mock_env
        # Incus mock returns 0 for info, so it's "already initialized"
        # We answer 'n' to the reconfigure prompt
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0
        assert "Bootstrap complete" in result.stdout

    def test_prod_with_yolo(self, mock_env):
        """--prod --YOLO sets yolo flag."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--prod", "--YOLO"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"

    def test_prod_context_values(self, mock_env):
        """--prod creates correct context."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0
        assert "absolute_level: 0" in result.stdout
        assert "vm_nested: false" in result.stdout


# ── nesting level propagation ─────────────────────────────


class TestBootstrapNesting:
    def test_nested_in_vm_sets_vm_nested(self, mock_env):
        """When systemd-detect-virt returns kvm, vm_nested is true."""
        env, _, cwd, _, etc = mock_env
        # Create a patched bootstrap with kvm detection
        patched = cwd / "bootstrap_kvm.sh"
        original = BOOTSTRAP_SH.read_text()
        # Patch both /etc/anklume and set virt detection to kvm
        patched_text = original.replace("/etc/anklume", str(etc))
        patched.write_text(patched_text)
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        # Override the virt detection mock to return kvm
        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho kvm\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "true"

    def test_parent_level_incremented(self, mock_env):
        """When parent has absolute_level, child increments it."""
        env, _, cwd, _, etc = mock_env
        # Simulate parent context
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("0")
        (etc / "vm_nested").write_text("true")

        patched = cwd / "bootstrap_nested.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").read_text().strip() == "2"


# ── dev mode without incus ────────────────────────────────


class TestBootstrapNoIncus:
    def test_dev_without_incus_fails(self, tmp_path):
        """--dev fails if incus is not installed."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        # Mock systemd-detect-virt only
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho none\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)
        # Mock python3
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        # Add bash to the mock bin
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)

        patched, _ = _make_patched_bootstrap(tmp_path)

        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_bootstrap(["--dev"], env, script=patched, cwd=tmp_path)
        assert result.returncode != 0
        assert "not installed" in result.stderr or "not installed" in result.stdout \
            or "not found" in result.stderr
