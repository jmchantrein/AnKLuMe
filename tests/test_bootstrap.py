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


# ── snapshot flag parsing ──────────────────────────────────


class TestBootstrapSnapshot:
    def test_snapshot_requires_type_argument(self):
        """--snapshot without TYPE argument gives an error."""
        result = run_bootstrap(["--dev", "--snapshot"], os.environ.copy())
        # --snapshot tries to shift 2 args; missing TYPE causes bash error
        assert result.returncode != 0

    def test_snapshot_btrfs_accepted(self, mock_env):
        """--snapshot btrfs is parsed and reported."""
        env, log, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "btrfs"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "btrfs" in result.stdout

    def test_snapshot_zfs_accepted(self, mock_env):
        """--snapshot zfs is parsed and reported."""
        env, log, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "zfs"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "zfs" in result.stdout

    def test_snapshot_snapper_accepted(self, mock_env):
        """--snapshot snapper is parsed and reported."""
        env, log, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "snapper"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "snapper" in result.stdout

    def test_snapshot_unknown_type_warns(self, mock_env):
        """--snapshot with unknown type produces a warning but continues."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "lvm"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "WARNING" in result.stdout
        assert "lvm" in result.stdout


# ── import flag parsing ────────────────────────────────────


class TestBootstrapImport:
    def test_import_flag_parsed(self, mock_env):
        """--import flag is parsed and triggers import section."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--import"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        # The import section looks for scripts/import-infra.sh
        # Since it does not exist in tmp_path, it warns
        assert "import" in result.stdout.lower()

    def test_import_without_script_warns(self, mock_env):
        """--import warns when scripts/import-infra.sh does not exist."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--import"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "WARNING" in result.stdout or "not found" in result.stdout.lower()


# ── YOLO flag ──────────────────────────────────────────────


class TestBootstrapYolo:
    def test_yolo_flag_sets_true(self, mock_env):
        """--YOLO sets yolo=true in context files."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev", "--YOLO"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "yolo").exists()
        assert (etc / "yolo").read_text().strip() == "true"

    def test_no_yolo_flag_sets_false(self, mock_env):
        """Without --YOLO, yolo is false in context files."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "yolo").exists()
        assert (etc / "yolo").read_text().strip() == "false"

    def test_prod_yolo_combined(self, mock_env):
        """--prod --YOLO sets yolo=true and completes successfully."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(
            ["--prod", "--YOLO"], env, script=script, cwd=cwd, input_text="n\n",
        )
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"
        assert "yolo=true" in result.stdout.lower() or "yolo=True" in result.stdout


# ── missing mode ───────────────────────────────────────────


class TestBootstrapMissingMode:
    def test_no_mode_gives_error(self):
        """Running without --prod or --dev gives an error message."""
        result = run_bootstrap([], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "ERROR" in combined or result.returncode != 0

    def test_no_mode_shows_usage(self):
        """Running without mode shows usage information."""
        result = run_bootstrap([], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "Usage" in combined or "Specify --prod or --dev" in combined

    def test_only_yolo_without_mode_errors(self):
        """--YOLO alone (without --prod or --dev) gives an error."""
        result = run_bootstrap(["--YOLO"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "ERROR" in combined or result.returncode != 0


# ── virtualization detection ───────────────────────────────


class TestBootstrapVirtDetection:
    def _make_virt_env(self, tmp_path, virt_output):
        """Create a mock env with a specific systemd-detect-virt output."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "cmds.log"

        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text(f"#!/usr/bin/env bash\necho \"{virt_output}\"\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        for cmd in ["ansible-playbook", "ansible-lint", "yamllint", "pip3"]:
            mock_cmd = mock_bin / cmd
            mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
            mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        etc_anklume = tmp_path / "etc_anklume"
        etc_anklume.mkdir(exist_ok=True)
        patched = tmp_path / "bootstrap_patched.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, patched, etc_anklume

    def test_none_virt_sets_vm_nested_false(self, tmp_path):
        """systemd-detect-virt returning 'none' sets vm_nested=false."""
        env, script, etc = self._make_virt_env(tmp_path, "none")
        result = run_bootstrap(["--dev"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "false"

    def test_kvm_virt_sets_vm_nested_true(self, tmp_path):
        """systemd-detect-virt returning 'kvm' sets vm_nested=true."""
        env, script, etc = self._make_virt_env(tmp_path, "kvm")
        result = run_bootstrap(["--dev"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "true"

    def test_qemu_virt_sets_vm_nested_true(self, tmp_path):
        """systemd-detect-virt returning 'qemu' sets vm_nested=true."""
        env, script, etc = self._make_virt_env(tmp_path, "qemu")
        result = run_bootstrap(["--dev"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "true"

    def test_lxc_virt_sets_vm_nested_false(self, tmp_path):
        """systemd-detect-virt returning 'lxc' (not kvm/qemu) sets vm_nested=false."""
        env, script, etc = self._make_virt_env(tmp_path, "lxc")
        result = run_bootstrap(["--dev"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "false"

    def test_virt_type_reported_in_output(self, tmp_path):
        """Detected virtualization type is printed in output."""
        env, script, etc = self._make_virt_env(tmp_path, "kvm")
        result = run_bootstrap(["--dev"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected virtualization: kvm" in result.stdout

    def test_no_systemd_detect_virt_defaults_to_none(self, tmp_path):
        """When systemd-detect-virt is not available, default to 'none'."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "cmds.log"

        # No systemd-detect-virt in PATH — only incus and other mocks
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then exit 0; fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        for cmd in ["ansible-playbook", "ansible-lint", "yamllint", "pip3"]:
            mock_cmd = mock_bin / cmd
            mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
            mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        etc_anklume = tmp_path / "etc_anklume"
        etc_anklume.mkdir(exist_ok=True)
        patched = tmp_path / "bootstrap_patched.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        # Use a PATH that excludes systemd-detect-virt but includes our mocks
        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}"

        # Need bash accessible
        bash_path = "/usr/bin/bash"
        if not os.path.exists(bash_path):
            bash_path = "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)

        # Also need common utilities (cat, mkdir, etc.)
        for util in ["cat", "mkdir", "echo", "id", "whoami", "getent", "df", "tail", "awk", "date"]:
            for search_dir in ["/usr/bin", "/bin"]:
                util_path = os.path.join(search_dir, util)
                if os.path.exists(util_path):
                    target = mock_bin / util
                    if not target.exists():
                        target.symlink_to(util_path)
                    break

        result = run_bootstrap(["--dev"], env, script=patched, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected virtualization: none" in result.stdout
        assert (etc_anklume / "vm_nested").read_text().strip() == "false"


# ── flag combinations ─────────────────────────────────────


class TestBootstrapFlagCombinations:
    """Test argument validation and flag combination edge cases."""

    def test_prod_and_dev_mutually_exclusive(self):
        """Passing both --prod and --dev uses whichever comes last (no error).

        The script parses flags sequentially so the last --prod/--dev wins.
        Both being present is not an error — the last one overwrites MODE.
        """
        result = run_bootstrap(["--prod", "--dev"], os.environ.copy())
        # The script does not error for conflicting flags; it uses the last.
        # It should either succeed (with a mode set) or fail for other reasons
        # (e.g. incus not installed), but never show "Specify --prod or --dev".
        combined = result.stdout + result.stderr
        assert "Specify --prod or --dev" not in combined

    def test_snapshot_alone_needs_mode(self):
        """--snapshot btrfs without --prod or --dev gives an error."""
        result = run_bootstrap(["--snapshot", "btrfs"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "ERROR" in combined or result.returncode != 0

    def test_import_standalone_needs_mode(self):
        """--import alone without a mode gives an error (mode is required)."""
        result = run_bootstrap(["--import"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "ERROR" in combined or result.returncode != 0

    def test_yolo_alone_needs_mode(self):
        """--YOLO alone without --prod or --dev gives an error."""
        result = run_bootstrap(["--YOLO"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "ERROR" in combined or result.returncode != 0

    def test_unknown_flag_gives_error(self):
        """An unknown flag like --foobar shows an error."""
        result = run_bootstrap(["--foobar"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "Unknown" in combined or result.returncode != 0


# ── prod mode detailed ────────────────────────────────────


class TestBootstrapProdMode:
    """Detailed tests for production mode behaviour."""

    def _make_prod_env(self, tmp_path, virt_output="none", incus_info_rc=0,
                       has_incus=True, fs_type="ext4"):
        """Create a full mock environment for prod mode testing."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "cmds.log"

        # Mock systemd-detect-virt
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text(
            f"#!/usr/bin/env bash\necho \"{virt_output}\"\n"
        )
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        if has_incus:
            # Mock incus
            mock_incus = mock_bin / "incus"
            mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then exit {incus_info_rc}; fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
exit 0
""")
            mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        # Mock df to control filesystem detection
        mock_df = mock_bin / "df"
        mock_df.write_text(f"""#!/usr/bin/env bash
if [[ "$1" == "-T" ]]; then
    echo "Filesystem     Type 1K-blocks    Used Available Use% Mounted on"
    echo "/dev/sda1      {fs_type}  104857600 52428800 52428800  50% /"
    exit 0
fi
/usr/bin/df "$@"
""")
        mock_df.chmod(mock_df.stat().st_mode | stat.S_IEXEC)

        for cmd in ["ansible-playbook", "ansible-lint", "yamllint", "pip3"]:
            mock_cmd = mock_bin / cmd
            if not mock_cmd.exists():
                mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
                mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        if mock_python.exists():
            mock_python.unlink()
        mock_python.write_text(
            "#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n"
        )
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        etc_anklume = tmp_path / "etc_anklume"
        etc_anklume.mkdir(exist_ok=True)
        patched = tmp_path / "bootstrap_patched.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, patched, etc_anklume, log_file

    def test_prod_filesystem_detection_ext4(self, tmp_path):
        """Prod mode with ext4 filesystem uses 'dir' storage backend."""
        # incus_info_rc=1 → "installed" branch where detect_fs runs unconditionally
        env, script, _, log = self._make_prod_env(
            tmp_path, fs_type="ext4", incus_info_rc=1,
        )
        result = run_bootstrap(
            ["--prod"], env, script=script, cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "Detected filesystem: dir" in result.stdout

    def test_prod_filesystem_detection_btrfs(self, tmp_path):
        """Prod mode with btrfs filesystem detects btrfs backend."""
        env, script, _, log = self._make_prod_env(
            tmp_path, fs_type="btrfs", incus_info_rc=1,
        )
        result = run_bootstrap(
            ["--prod"], env, script=script, cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "Detected filesystem: btrfs" in result.stdout

    def test_prod_incus_preseed_generation(self, tmp_path):
        """Prod mode reconfigure generates Incus preseed config."""
        # Use "installed" branch (incus_info_rc=1) to test storage configuration output
        env, script, _, log = self._make_prod_env(
            tmp_path, fs_type="btrfs", incus_info_rc=1,
        )
        result = run_bootstrap(
            ["--prod"], env, script=script, cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "storage" in result.stdout.lower()

    def test_prod_missing_incus_binary(self, tmp_path):
        """Prod mode without incus binary attempts install or errors."""
        env, script, _, _ = self._make_prod_env(
            tmp_path, has_incus=False,
        )
        result = run_bootstrap(
            ["--prod"], env, script=script, cwd=tmp_path,
        )
        # Without incus, prod mode tries to install it. Since apt-get/pacman
        # are not available in mock, it should error.
        combined = result.stdout + result.stderr
        assert result.returncode != 0 or "ERROR" in combined \
            or "Install" in combined or "not installed" in combined.lower()


# ── context file content format ───────────────────────────────────


class TestBootstrapContextFileFormat:
    """Verify the format of context files in /etc/anklume."""

    def test_context_files_are_single_values(self, mock_env):
        """Each context file contains a single value with no extra whitespace."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0

        for name in ("absolute_level", "relative_level", "vm_nested", "yolo"):
            f = etc / name
            assert f.exists(), f"Missing context file: {name}"
            content = f.read_text()
            # Should be a single line (content + optional trailing newline)
            lines = [l for l in content.splitlines() if l.strip()]
            assert len(lines) == 1, f"Expected 1 line in {name}, got {len(lines)}"

    def test_absolute_level_is_integer(self, mock_env):
        """absolute_level is a parseable integer."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        val = (etc / "absolute_level").read_text().strip()
        assert val.isdigit(), f"absolute_level '{val}' is not a digit"

    def test_relative_level_is_integer(self, mock_env):
        """relative_level is a parseable integer."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        val = (etc / "relative_level").read_text().strip()
        assert val.isdigit(), f"relative_level '{val}' is not a digit"

    def test_vm_nested_is_boolean_string(self, mock_env):
        """vm_nested is either 'true' or 'false'."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        val = (etc / "vm_nested").read_text().strip()
        assert val in ("true", "false"), f"vm_nested '{val}' not boolean"

    def test_yolo_is_boolean_string(self, mock_env):
        """yolo is either 'true' or 'false'."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        val = (etc / "yolo").read_text().strip()
        assert val in ("true", "false"), f"yolo '{val}' not boolean"


# ── output completeness ──────────────────────────────────────────


class TestBootstrapOutputCompleteness:
    """Verify bootstrap output covers all expected sections."""

    def test_dev_mode_reports_context(self, mock_env):
        """Dev mode reports all context values in output."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        output = result.stdout
        # Should report nesting context
        assert "absolute_level" in output
        assert "vm_nested" in output

    def test_dev_mode_shows_incus_status(self, mock_env):
        """Dev mode checks and reports Incus status."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        output = result.stdout.lower()
        assert "incus" in output

    def test_prod_mode_reports_filesystem(self, mock_env):
        """Prod mode reports detected filesystem type."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0
        output = result.stdout.lower()
        assert "filesystem" in output or "detected" in output
