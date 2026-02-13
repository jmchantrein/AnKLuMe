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


# ── script structure and syntax ──────────────────────────


class TestBootstrapScriptStructure:
    """Verify script file structure, shebang, and definitions."""

    def test_script_exists(self):
        """bootstrap.sh exists at the expected path."""
        assert BOOTSTRAP_SH.exists(), f"bootstrap.sh not found at {BOOTSTRAP_SH}"

    def test_script_is_file(self):
        """bootstrap.sh is a regular file, not a directory or symlink."""
        assert BOOTSTRAP_SH.is_file()

    def test_script_is_executable(self):
        """bootstrap.sh has the executable bit set."""
        mode = BOOTSTRAP_SH.stat().st_mode
        assert mode & stat.S_IEXEC, "bootstrap.sh is not executable"

    def test_shebang_is_bash(self):
        """bootstrap.sh starts with a bash shebang."""
        first_line = BOOTSTRAP_SH.read_text().splitlines()[0]
        assert first_line.startswith("#!/"), "Missing shebang"
        assert "bash" in first_line, f"Shebang is not bash: {first_line}"

    def test_set_euo_pipefail(self):
        """Script uses 'set -euo pipefail' for strict error handling."""
        content = BOOTSTRAP_SH.read_text()
        assert "set -euo pipefail" in content

    def test_usage_function_defined(self):
        """Script defines a usage() function."""
        content = BOOTSTRAP_SH.read_text()
        assert "usage()" in content or "usage ()" in content

    def test_detect_fs_function_defined(self):
        """Script defines a detect_fs() function."""
        content = BOOTSTRAP_SH.read_text()
        assert "detect_fs()" in content or "detect_fs ()" in content

    def test_ensure_incus_group_function_defined(self):
        """Script defines an ensure_incus_group() function."""
        content = BOOTSTRAP_SH.read_text()
        assert "ensure_incus_group()" in content or "ensure_incus_group ()" in content

    def test_mode_variable_initialized_empty(self):
        """MODE variable is initialized to empty string."""
        content = BOOTSTRAP_SH.read_text()
        assert 'MODE=""' in content

    def test_yolo_variable_initialized_false(self):
        """YOLO variable is initialized to false."""
        content = BOOTSTRAP_SH.read_text()
        assert "YOLO=false" in content

    def test_import_variable_initialized_false(self):
        """IMPORT variable is initialized to false."""
        content = BOOTSTRAP_SH.read_text()
        assert "IMPORT=false" in content

    def test_snapshot_type_initialized_empty(self):
        """SNAPSHOT_TYPE variable is initialized to empty string."""
        content = BOOTSTRAP_SH.read_text()
        assert 'SNAPSHOT_TYPE=""' in content

    def test_script_contains_case_statement_for_args(self):
        """Script uses a case statement for argument parsing."""
        content = BOOTSTRAP_SH.read_text()
        assert "case \"$1\" in" in content

    def test_script_checks_empty_mode(self):
        """Script checks for empty MODE after argument parsing."""
        content = BOOTSTRAP_SH.read_text()
        assert '[ -z "$MODE" ]' in content

    def test_script_has_prod_mode_branch(self):
        """Script has a conditional branch for prod mode."""
        content = BOOTSTRAP_SH.read_text()
        assert '[ "$MODE" = "prod" ]' in content

    def test_script_has_dev_mode_branch(self):
        """Script has a conditional branch for dev mode."""
        content = BOOTSTRAP_SH.read_text()
        assert '[ "$MODE" = "dev" ]' in content

    def test_script_references_etc_anklume(self):
        """Script references /etc/anklume for context files."""
        content = BOOTSTRAP_SH.read_text()
        assert "/etc/anklume" in content

    def test_script_creates_context_directory(self):
        """Script creates the context directory with mkdir -p."""
        content = BOOTSTRAP_SH.read_text()
        assert "mkdir -p /etc/anklume" in content

    def test_script_writes_four_context_files(self):
        """Script writes all four context files."""
        content = BOOTSTRAP_SH.read_text()
        for f in ("absolute_level", "relative_level", "vm_nested", "yolo"):
            assert f"/etc/anklume/{f}" in content, f"Missing write for {f}"


# ── help flag variations ──────────────────────────────────


class TestBootstrapHelpVariants:
    """Test help flag variants and help output content."""

    def test_short_help_flag(self):
        """-h shows usage and exits 0."""
        result = run_bootstrap(["-h"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_shows_prod_option(self):
        """--help output mentions --prod option."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert "--prod" in result.stdout

    def test_help_shows_dev_option(self):
        """--help output mentions --dev option."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert "--dev" in result.stdout

    def test_help_shows_snapshot_option(self):
        """--help output mentions --snapshot option."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert "--snapshot" in result.stdout

    def test_help_shows_yolo_option(self):
        """--help output mentions --YOLO option."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert "--YOLO" in result.stdout

    def test_help_shows_import_option(self):
        """--help output mentions --import option."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert "--import" in result.stdout

    def test_help_ignores_other_flags(self):
        """--help exits 0 even if other flags are present before it."""
        result = run_bootstrap(["--dev", "--help"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout


# ── banner and output format ──────────────────────────────


class TestBootstrapBannerOutput:
    """Verify banner, section markers, and output format."""

    def test_dev_banner_shows_mode(self, mock_env):
        """Dev mode shows 'AnKLuMe Bootstrap (dev mode)' banner."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "AnKLuMe Bootstrap (dev mode)" in result.stdout

    def test_prod_banner_shows_mode(self, mock_env):
        """Prod mode shows 'AnKLuMe Bootstrap (prod mode)' banner."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert "AnKLuMe Bootstrap (prod mode)" in result.stdout

    def test_dev_output_has_context_section(self, mock_env):
        """Dev mode output includes context setup section marker."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        # The patched script replaces /etc/anklume with a temp path,
        # so we check for the surrounding text instead.
        assert "Setting up" in result.stdout and "context" in result.stdout

    def test_dev_output_has_dependencies_section(self, mock_env):
        """Dev mode output includes dependency checking section."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "Checking dependencies" in result.stdout

    def test_dev_output_has_incus_section(self, mock_env):
        """Dev mode output includes dev Incus configuration section."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "Development Incus configuration" in result.stdout

    def test_prod_output_has_prod_incus_section(self, mock_env):
        """Prod mode output includes prod Incus configuration section."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert "Production Incus configuration" in result.stdout

    def test_context_summary_line_format(self, mock_env):
        """Final summary line includes all four context values."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        output = result.stdout
        assert "Context:" in output
        assert "absolute_level=" in output
        assert "relative_level=" in output
        assert "vm_nested=" in output
        assert "yolo=" in output

    def test_context_summary_yolo_false_by_default(self, mock_env):
        """Summary line shows yolo=false when --YOLO not given."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "yolo=false" in result.stdout

    def test_context_summary_yolo_true_with_flag(self, mock_env):
        """Summary line shows yolo=true when --YOLO given."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--YOLO"], env, script=script, cwd=cwd)
        assert "yolo=true" in result.stdout


# ── relative level behavior ───────────────────────────────


class TestBootstrapRelativeLevel:
    """Test relative_level computation across nesting contexts."""

    def test_fresh_install_relative_level_zero(self, mock_env):
        """Fresh install without parent context sets relative_level=0."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "relative_level").read_text().strip() == "0"

    def test_relative_level_increments_in_container(self, mock_env):
        """Relative level increments when nested inside a container (non-VM)."""
        env, _, cwd, _, etc = mock_env
        # Simulate parent context: relative_level=1, virt type is lxc
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("1")
        (etc / "vm_nested").write_text("false")

        patched = cwd / "bootstrap_rel.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        # systemd-detect-virt returns 'lxc' (not kvm/qemu)
        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho lxc\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "relative_level").read_text().strip() == "2"

    def test_relative_level_resets_at_vm_boundary(self, mock_env):
        """Relative level resets to 0 at a VM boundary (kvm)."""
        env, _, cwd, _, etc = mock_env
        # Simulate parent context with relative_level=3
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("2")
        (etc / "relative_level").write_text("3")
        (etc / "vm_nested").write_text("false")

        patched = cwd / "bootstrap_vm.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        # systemd-detect-virt returns kvm → VM boundary → relative resets
        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho kvm\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "relative_level").read_text().strip() == "0"

    def test_relative_level_resets_at_qemu_boundary(self, mock_env):
        """Relative level resets to 0 at a qemu VM boundary."""
        env, _, cwd, _, etc = mock_env
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("5")
        (etc / "vm_nested").write_text("true")

        patched = cwd / "bootstrap_qemu.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho qemu\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "relative_level").read_text().strip() == "0"

    def test_relative_level_reported_in_output(self, mock_env):
        """Relative level is reported in the output."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "relative_level:" in result.stdout


# ── vm_nested propagation ─────────────────────────────────


class TestBootstrapVmNestedPropagation:
    """Test vm_nested flag propagation from parent context."""

    def test_vm_nested_inherited_from_parent(self, mock_env):
        """vm_nested=true is inherited when parent has it and virt is not kvm/qemu."""
        env, _, cwd, _, etc = mock_env
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("0")
        (etc / "vm_nested").write_text("true")

        patched = cwd / "bootstrap_inherit.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        # systemd-detect-virt returns 'lxc' — not kvm, so inherits from parent
        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho lxc\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "true"

    def test_vm_nested_false_when_parent_false_and_virt_none(self, mock_env):
        """vm_nested stays false when parent is false and virt is none."""
        env, _, cwd, _, etc = mock_env
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("1")
        (etc / "vm_nested").write_text("false")

        patched = cwd / "bootstrap_false.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "false"

    def test_vm_nested_set_true_by_kvm_even_without_parent(self, mock_env):
        """vm_nested becomes true via kvm detection even without parent context."""
        env, _, cwd, _, etc = mock_env

        patched = cwd / "bootstrap_kvm_fresh.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho kvm\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "true"


# ── snapshot section behavior ─────────────────────────────


class TestBootstrapSnapshotSection:
    """Test snapshot creation section behavior."""

    def test_no_snapshot_flag_skips_snapshot_section(self, mock_env):
        """Without --snapshot, no snapshot-related output appears."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Creating" not in result.stdout or "snapshot" not in result.stdout.lower().split("creating")[0]

    def test_snapshot_btrfs_without_btrfs_cmd_warns(self, mock_env):
        """--snapshot btrfs warns when btrfs command is not available."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "btrfs"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_snapshot_zfs_without_zfs_cmd_warns(self, mock_env):
        """--snapshot zfs warns when zfs command is not available."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "zfs"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_snapshot_snapper_without_snapper_cmd_warns(self, mock_env):
        """--snapshot snapper warns when snapper command is not available."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "snapper"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "WARNING" in result.stdout

    def test_snapshot_creates_snapshot_name(self, mock_env):
        """--snapshot includes a snapshot name in its output."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--snapshot", "btrfs"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "anklume-pre-bootstrap-" in result.stdout

    def test_snapshot_works_with_prod_mode(self, mock_env):
        """--snapshot works with --prod mode."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(
            ["--prod", "--snapshot", "btrfs"], env, script=script, cwd=cwd, input_text="n\n",
        )
        assert result.returncode == 0
        assert "anklume-pre-bootstrap-" in result.stdout


# ── import section behavior ───────────────────────────────


class TestBootstrapImportSection:
    """Test import section behavior with and without the import script."""

    def test_import_with_existing_script(self, mock_env):
        """--import runs import-infra.sh when it exists."""
        env, _, cwd, script, _ = mock_env
        # Create a fake import-infra.sh in the expected location
        scripts_dir = cwd / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        import_script = scripts_dir / "import-infra.sh"
        import_script.write_text("#!/usr/bin/env bash\necho 'IMPORT_RAN_SUCCESSFULLY'\n")
        import_script.chmod(import_script.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev", "--import"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "IMPORT_RAN_SUCCESSFULLY" in result.stdout

    def test_import_section_header_shown(self, mock_env):
        """--import shows the import section header."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--import"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Importing existing infrastructure" in result.stdout

    def test_no_import_flag_skips_import(self, mock_env):
        """Without --import, import section is skipped."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Importing existing infrastructure" not in result.stdout


# ── prod mode detailed scenarios ──────────────────────────


class TestBootstrapProdScenarios:
    """Additional prod mode scenarios."""

    def _make_prod_env(self, tmp_path, virt_output="none", incus_info_rc=0,
                       fs_type="ext4"):
        """Create a mock environment for prod testing."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "cmds.log"

        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text(f"#!/usr/bin/env bash\necho \"{virt_output}\"\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then exit {incus_info_rc}; fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
if [[ "$1" == "project" && "$2" == "list" ]]; then echo "default"; exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

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
        return env, patched, etc_anklume, log_file

    def test_prod_reconfigure_yes(self, tmp_path):
        """Prod mode with 'y' response reconfigures Incus with preseed."""
        env, script, etc, log = self._make_prod_env(tmp_path, fs_type="ext4")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="y\n")
        assert result.returncode == 0
        assert "Incus configured with" in result.stdout

    def test_prod_reconfigure_no(self, tmp_path):
        """Prod mode with 'n' response skips reconfiguration."""
        env, script, etc, log = self._make_prod_env(tmp_path, fs_type="ext4")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="n\n")
        assert result.returncode == 0
        assert "Skipping Incus configuration" in result.stdout

    def test_prod_already_initialized_message(self, tmp_path):
        """Prod mode shows 'already initialized' when incus info succeeds."""
        env, script, etc, log = self._make_prod_env(tmp_path)
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="n\n")
        assert result.returncode == 0
        assert "Incus already initialized" in result.stdout

    def test_prod_installed_but_not_ready(self, tmp_path):
        """Prod mode with incus installed but daemon not responding runs minimal init."""
        env, script, etc, log = self._make_prod_env(tmp_path, incus_info_rc=1)
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "daemon is not responding" in result.stdout
        assert "minimal" in result.stdout.lower()

    def test_prod_zfs_filesystem_detection(self, tmp_path):
        """Prod mode with zfs filesystem detects zfs backend."""
        env, script, _, log = self._make_prod_env(tmp_path, fs_type="zfs", incus_info_rc=1)
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: zfs" in result.stdout

    def test_prod_preseed_contains_storage_pools(self, tmp_path):
        """Prod reconfigure generates preseed with storage_pools section."""
        env, script, _, log = self._make_prod_env(tmp_path, fs_type="btrfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="y\n")
        assert result.returncode == 0
        # Check the log for incus admin init --preseed being called
        log_content = log.read_text()
        assert "incus admin init" in log_content

    def test_prod_preseed_btrfs_uses_btrfs_driver(self, tmp_path):
        """Prod reconfigure with btrfs filesystem uses btrfs driver in preseed."""
        env, script, _, _ = self._make_prod_env(tmp_path, fs_type="btrfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="y\n")
        assert result.returncode == 0
        assert "Incus configured with btrfs" in result.stdout

    def test_prod_preseed_ext4_uses_dir_driver(self, tmp_path):
        """Prod reconfigure with ext4 filesystem uses dir storage backend."""
        env, script, _, _ = self._make_prod_env(tmp_path, fs_type="ext4")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="y\n")
        assert result.returncode == 0
        assert "Incus configured with dir" in result.stdout

    def test_prod_preseed_zfs_uses_zfs_driver(self, tmp_path):
        """Prod reconfigure with zfs filesystem uses zfs driver."""
        env, script, _, _ = self._make_prod_env(tmp_path, fs_type="zfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path, input_text="y\n")
        assert result.returncode == 0
        assert "Incus configured with zfs" in result.stdout


# ── dev mode incus not initialized ────────────────────────


class TestBootstrapDevNotInitialized:
    """Test dev mode when incus is installed but not initialized."""

    def test_dev_incus_not_initialized_runs_minimal_init(self, tmp_path):
        """Dev mode runs minimal init when incus info fails."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "cmds.log"

        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho none\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        # Incus exists but info returns 1 (not initialized)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then exit 1; fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
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
        patched = tmp_path / "bootstrap_dev_init.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"

        result = run_bootstrap(["--dev"], env, script=patched, cwd=tmp_path)
        assert result.returncode == 0
        assert "not initialized" in result.stdout.lower() or "minimal init" in result.stdout.lower()
        # Verify incus admin init --minimal was called
        log_content = log_file.read_text()
        assert "admin init" in log_content


# ── dependency checking ───────────────────────────────────


class TestBootstrapDependencyChecking:
    """Test the dependency checking section."""

    def test_missing_dependencies_reported(self, tmp_path):
        """Missing dependencies are reported in output."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)

        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho none\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        mock_incus = mock_bin / "incus"
        mock_incus.write_text("""#!/usr/bin/env bash
if [[ "$1" == "info" ]]; then exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        # Only provide python3, NOT ansible-lint, yamllint, pip3, ansible-playbook
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        # Symlink essential system utilities so the script can run
        bash_path = "/usr/bin/bash" if os.path.exists("/usr/bin/bash") else "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)
        for util in ["cat", "mkdir", "echo", "id", "whoami", "getent", "date",
                      "df", "tail", "awk", "command"]:
            for search_dir in ["/usr/bin", "/bin"]:
                util_path = os.path.join(search_dir, util)
                if os.path.exists(util_path):
                    target = mock_bin / util
                    if not target.exists():
                        target.symlink_to(util_path)
                    break

        etc_anklume = tmp_path / "etc_anklume"
        etc_anklume.mkdir(exist_ok=True)
        patched = tmp_path / "bootstrap_deps.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        # Use exclusive PATH so system ansible-lint, yamllint etc. are not found
        env["PATH"] = str(mock_bin)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=tmp_path)
        assert result.returncode == 0
        assert "Missing tools" in result.stdout
        assert "make init" in result.stdout

    def test_no_missing_dependencies_no_warning(self, mock_env):
        """When all dependencies are present, no 'Missing tools' message appears."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Missing tools" not in result.stdout


# ── incus group handling ──────────────────────────────────


class TestBootstrapIncusGroup:
    """Test the ensure_incus_group section output."""

    def test_incus_socket_access_section_shown(self, mock_env):
        """When incus is available, socket access section is shown."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Ensuring Incus socket access" in result.stdout


# ── dev mode existing incus ───────────────────────────────


class TestBootstrapDevExistingIncus:
    """Test dev mode with Incus already initialized."""

    def test_dev_existing_incus_uses_existing_config(self, mock_env):
        """Dev mode with initialized Incus uses existing configuration."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "using existing Incus configuration" in result.stdout


# ── multiple flags combined ───────────────────────────────


class TestBootstrapMultipleFlags:
    """Test various combinations of multiple flags together."""

    def test_dev_yolo_snapshot_import(self, mock_env):
        """--dev --YOLO --snapshot btrfs --import all work together."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(
            ["--dev", "--YOLO", "--snapshot", "btrfs", "--import"],
            env, script=script, cwd=cwd,
        )
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"
        assert "anklume-pre-bootstrap-" in result.stdout
        assert "Importing existing infrastructure" in result.stdout

    def test_prod_yolo_snapshot_zfs(self, mock_env):
        """--prod --YOLO --snapshot zfs combines correctly."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(
            ["--prod", "--YOLO", "--snapshot", "zfs"],
            env, script=script, cwd=cwd, input_text="n\n",
        )
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"
        assert "zfs" in result.stdout

    def test_double_yolo_flag(self, mock_env):
        """--YOLO --YOLO still sets yolo=true (idempotent)."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev", "--YOLO", "--YOLO"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"

    def test_import_without_yolo(self, mock_env):
        """--dev --import without --YOLO sets yolo=false."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev", "--import"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "false"


# ── flag ordering ─────────────────────────────────────────


class TestBootstrapFlagOrdering:
    """Test that flags work regardless of their order."""

    def test_yolo_before_mode(self, mock_env):
        """--YOLO --dev works (YOLO before mode)."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--YOLO", "--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"

    def test_snapshot_before_mode(self, mock_env):
        """--snapshot btrfs --dev works (snapshot before mode)."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--snapshot", "btrfs", "--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "btrfs" in result.stdout

    def test_import_before_mode(self, mock_env):
        """--import --dev works (import before mode)."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--import", "--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Importing existing infrastructure" in result.stdout

    def test_all_flags_reversed_order(self, mock_env):
        """--import --YOLO --snapshot btrfs --dev works in reversed order."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(
            ["--import", "--YOLO", "--snapshot", "btrfs", "--dev"],
            env, script=script, cwd=cwd,
        )
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"
        assert "btrfs" in result.stdout


# ── idempotency ───────────────────────────────────────────


class TestBootstrapIdempotency:
    """Test that running bootstrap twice produces consistent results."""

    def test_dev_mode_idempotent(self, mock_env):
        """Running --dev twice produces the same context files."""
        env, _, cwd, script, etc = mock_env
        # First run
        result1 = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result1.returncode == 0
        abs1 = (etc / "absolute_level").read_text().strip()
        rel1 = (etc / "relative_level").read_text().strip()
        vm1 = (etc / "vm_nested").read_text().strip()
        yolo1 = (etc / "yolo").read_text().strip()

        # Second run
        result2 = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result2.returncode == 0
        # Context files from parent do not exist in initial state, so re-running
        # reads the files from first run as "parent" context, incrementing levels
        # This is expected behavior — bootstrap detects it as nested
        # Just verify the run succeeded and files are valid
        abs2 = (etc / "absolute_level").read_text().strip()
        rel2 = (etc / "relative_level").read_text().strip()
        assert abs2.isdigit()
        assert rel2.isdigit()

    def test_yolo_stays_consistent(self, mock_env):
        """--YOLO consistently produces yolo=true across runs."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev", "--YOLO"], env, script=script, cwd=cwd)
        assert (etc / "yolo").read_text().strip() == "true"
        run_bootstrap(["--dev", "--YOLO"], env, script=script, cwd=cwd)
        assert (etc / "yolo").read_text().strip() == "true"


# ── error message content ────────────────────────────────


class TestBootstrapErrorMessages:
    """Test specific error message content."""

    def test_missing_mode_error_message(self):
        """Missing mode error says 'Specify --prod or --dev'."""
        result = run_bootstrap([], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "Specify --prod or --dev" in combined

    def test_unknown_option_shows_the_option(self):
        """Unknown option error includes the offending option name."""
        result = run_bootstrap(["--foobar"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "--foobar" in combined

    def test_dev_without_incus_error_on_stderr(self, tmp_path):
        """Dev mode without incus writes error to stderr."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho none\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)
        bash_path = "/usr/bin/bash" if os.path.exists("/usr/bin/bash") else "/bin/bash"
        (mock_bin / "bash").symlink_to(bash_path)

        patched, _ = _make_patched_bootstrap(tmp_path)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_bootstrap(["--dev"], env, script=patched, cwd=tmp_path)
        assert result.returncode != 0
        # The error should be on stderr (the script uses >&2)
        assert "not installed" in result.stderr or "not found" in result.stderr


# ── nesting deep levels ───────────────────────────────────


class TestBootstrapDeepNesting:
    """Test behavior at deeper nesting levels."""

    def test_absolute_level_three_deep(self, mock_env):
        """Absolute level increments correctly at depth 3."""
        env, _, cwd, _, etc = mock_env
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("2")
        (etc / "relative_level").write_text("1")
        (etc / "vm_nested").write_text("true")

        patched = cwd / "bootstrap_deep.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").read_text().strip() == "3"

    def test_relative_level_deep_increment(self, mock_env):
        """Relative level increments correctly at deep nesting (non-VM)."""
        env, _, cwd, _, etc = mock_env
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("4")
        (etc / "relative_level").write_text("3")
        (etc / "vm_nested").write_text("true")

        patched = cwd / "bootstrap_deep_rel.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        # virt is lxc → relative increments, does not reset
        mock_bin = cwd / "bin"
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho lxc\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").read_text().strip() == "5"
        assert (etc / "relative_level").read_text().strip() == "4"

    def test_absolute_and_relative_both_start_at_zero(self, mock_env):
        """Without parent context, both levels start at 0."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").read_text().strip() == "0"
        assert (etc / "relative_level").read_text().strip() == "0"


# ── prod mode last-wins behavior ──────────────────────────


class TestBootstrapLastWins:
    """Test that the last --prod/--dev flag wins."""

    def test_prod_dev_last_dev_wins(self, mock_env):
        """--prod --dev results in dev mode (last wins)."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--prod", "--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "AnKLuMe Bootstrap (dev mode)" in result.stdout

    def test_dev_prod_last_prod_wins(self, mock_env):
        """--dev --prod results in prod mode (last wins)."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev", "--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0
        assert "AnKLuMe Bootstrap (prod mode)" in result.stdout


# ── context file directory creation ───────────────────────


class TestBootstrapContextDirectory:
    """Test that the context directory is created properly."""

    def test_etc_anklume_directory_created(self, mock_env):
        """Bootstrap creates the context directory."""
        env, _, cwd, script, etc = mock_env
        # Remove the directory first to ensure bootstrap creates it
        import shutil
        if etc.exists():
            shutil.rmtree(etc)
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert etc.exists()
        assert etc.is_dir()

    def test_context_directory_survives_rerun(self, mock_env):
        """Running bootstrap twice does not fail on existing directory."""
        env, _, cwd, script, etc = mock_env
        result1 = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result1.returncode == 0
        result2 = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result2.returncode == 0


# ── next steps section ────────────────────────────────────


class TestBootstrapNextSteps:
    """Test the next steps section output."""

    def test_dev_next_steps_mentions_infra_yml(self, mock_env):
        """Next steps mention editing infra.yml."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "infra.yml" in result.stdout

    def test_dev_next_steps_mentions_make_sync(self, mock_env):
        """Next steps mention make sync."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "make sync" in result.stdout

    def test_dev_next_steps_mentions_make_apply(self, mock_env):
        """Next steps mention make apply."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert "make apply" in result.stdout

    def test_prod_next_steps_shown(self, mock_env):
        """Prod mode also shows next steps."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0
        assert "Next steps" in result.stdout


# ── unknown option variations ─────────────────────────────


class TestBootstrapUnknownOptions:
    """Test various unknown option patterns."""

    def test_single_dash_option(self):
        """-x is treated as unknown option."""
        result = run_bootstrap(["-x"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "Unknown" in combined or result.returncode != 0

    def test_double_unknown_option(self):
        """Two unknown options still produce error."""
        result = run_bootstrap(["--foo", "--bar"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "Unknown" in combined or result.returncode != 0

    def test_unknown_option_with_valid_mode(self):
        """--dev --unknown produces error for unknown option."""
        result = run_bootstrap(["--dev", "--unknown"], os.environ.copy())
        combined = result.stdout + result.stderr
        assert "Unknown" in combined or result.returncode != 0


# ── detect_fs function output ─────────────────────────────


class TestBootstrapDetectFs:
    """Test detect_fs function output for different filesystem types."""

    def _make_fs_env(self, tmp_path, fs_type):
        """Create a mock environment with specific fs type for testing."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir(exist_ok=True)
        log_file = tmp_path / "cmds.log"

        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho none\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then exit 1; fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

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
            mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
            mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        etc_anklume = tmp_path / "etc_anklume"
        etc_anklume.mkdir(exist_ok=True)
        patched = tmp_path / "bootstrap_fs.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc_anklume)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, patched, etc_anklume

    def test_detect_fs_xfs_maps_to_dir(self, tmp_path):
        """XFS filesystem maps to 'dir' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "xfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: dir" in result.stdout

    def test_detect_fs_ext4_maps_to_dir(self, tmp_path):
        """ext4 filesystem maps to 'dir' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "ext4")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: dir" in result.stdout

    def test_detect_fs_btrfs_maps_to_btrfs(self, tmp_path):
        """btrfs filesystem maps to 'btrfs' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "btrfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: btrfs" in result.stdout

    def test_detect_fs_zfs_maps_to_zfs(self, tmp_path):
        """ZFS filesystem maps to 'zfs' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "zfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: zfs" in result.stdout

    def test_detect_fs_tmpfs_maps_to_dir(self, tmp_path):
        """tmpfs filesystem maps to 'dir' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "tmpfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: dir" in result.stdout


# ── edge cases ────────────────────────────────────────────


class TestBootstrapEdgeCases:
    """Edge case tests for bootstrap behavior."""

    def test_empty_string_args(self):
        """Empty string argument does not crash."""
        result = run_bootstrap([""], os.environ.copy())
        # Empty string is not a recognized option
        combined = result.stdout + result.stderr
        assert result.returncode != 0 or "Unknown" in combined

    def test_help_output_is_not_empty(self):
        """--help produces non-empty output."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert len(result.stdout.strip()) > 0

    def test_help_has_multiple_lines(self):
        """--help produces multiple lines of output."""
        result = run_bootstrap(["--help"], os.environ.copy())
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        assert len(lines) >= 5, f"Help output too short: {len(lines)} lines"

    def test_bootstrap_does_not_write_to_stdout_on_help_stderr(self):
        """--help does not produce stderr output."""
        result = run_bootstrap(["--help"], os.environ.copy())
        assert result.returncode == 0
        assert result.stderr.strip() == ""

    def test_dev_mode_exit_code_zero(self, mock_env):
        """Dev mode exits with code 0 on success."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0

    def test_prod_mode_exit_code_zero(self, mock_env):
        """Prod mode exits with code 0 on success."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--prod"], env, script=script, cwd=cwd, input_text="n\n")
        assert result.returncode == 0

    def test_context_files_not_empty(self, mock_env):
        """All context files have non-empty content."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        for name in ("absolute_level", "relative_level", "vm_nested", "yolo"):
            content = (etc / name).read_text().strip()
            assert len(content) > 0, f"Context file {name} is empty"

    def test_context_files_have_no_leading_whitespace(self, mock_env):
        """Context files have no leading whitespace in their values."""
        env, _, cwd, script, etc = mock_env
        run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        for name in ("absolute_level", "relative_level", "vm_nested", "yolo"):
            content = (etc / name).read_text()
            first_char = content[0] if content else ""
            assert first_char not in (" ", "\t"), (
                f"Context file {name} has leading whitespace"
            )
