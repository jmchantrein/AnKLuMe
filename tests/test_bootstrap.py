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


# ── dev mode ──────────────────────────────────────────────


class TestBootstrapDev:
    def test_dev_mode_completes(self, mock_env):
        """--dev completes successfully with mock Incus."""
        env, _, cwd, script, _ = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert "Bootstrap complete" in result.stdout

    def test_dev_mode_creates_context_files(self, mock_env):
        """--dev creates all four context files with correct values."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").exists()
        assert (etc / "relative_level").exists()
        assert (etc / "vm_nested").exists()
        assert (etc / "yolo").exists()
        assert (etc / "absolute_level").read_text().strip() == "0"
        assert (etc / "vm_nested").read_text().strip() == "false"


# ── prod mode ─────────────────────────────────────────────


class TestBootstrapProd:
    def test_prod_mode_completes(self, mock_env):
        """--prod completes with mock Incus already initialized."""
        env, _, cwd, script, _ = mock_env
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


# ── nesting level propagation ─────────────────────────────


class TestBootstrapNesting:
    def test_nested_in_vm_sets_vm_nested(self, mock_env):
        """When systemd-detect-virt returns kvm, vm_nested is true."""
        env, _, cwd, _, etc = mock_env
        patched = cwd / "bootstrap_kvm.sh"
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

    def test_parent_level_incremented(self, mock_env):
        """When parent has absolute_level, child increments it."""
        env, _, cwd, _, etc = mock_env
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


# ── relative level behavior ───────────────────────────────


class TestBootstrapRelativeLevel:
    def test_fresh_install_relative_level_zero(self, mock_env):
        """Fresh install without parent context sets relative_level=0."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "relative_level").read_text().strip() == "0"

    def test_relative_level_increments_in_container(self, mock_env):
        """Relative level increments when nested inside a container (non-VM)."""
        env, _, cwd, _, etc = mock_env
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("1")
        (etc / "relative_level").write_text("1")
        (etc / "vm_nested").write_text("false")

        patched = cwd / "bootstrap_rel.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

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
        etc.mkdir(exist_ok=True)
        (etc / "absolute_level").write_text("2")
        (etc / "relative_level").write_text("3")
        (etc / "vm_nested").write_text("false")

        patched = cwd / "bootstrap_vm.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(original.replace("/etc/anklume", str(etc)))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

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


# ── vm_nested propagation ─────────────────────────────────


class TestBootstrapVmNestedPropagation:
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


# ── deep nesting levels ───────────────────────────────────


class TestBootstrapDeepNesting:
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

    def test_both_levels_start_at_zero(self, mock_env):
        """Without parent context, both levels start at 0."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "absolute_level").read_text().strip() == "0"
        assert (etc / "relative_level").read_text().strip() == "0"


# ── filesystem detection ──────────────────────────────────


class TestBootstrapDetectFs:
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

    def test_ext4_maps_to_dir(self, tmp_path):
        """ext4 filesystem maps to 'dir' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "ext4")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: dir" in result.stdout

    def test_btrfs_maps_to_btrfs(self, tmp_path):
        """btrfs filesystem maps to 'btrfs' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "btrfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: btrfs" in result.stdout

    def test_zfs_maps_to_zfs(self, tmp_path):
        """ZFS filesystem maps to 'zfs' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "zfs")
        result = run_bootstrap(["--prod"], env, script=script, cwd=tmp_path)
        assert result.returncode == 0
        assert "Detected filesystem: zfs" in result.stdout


# ── context directory creation ─────────────────────────────


class TestBootstrapContextDirectory:
    def test_etc_anklume_directory_created(self, mock_env):
        """Bootstrap creates the context directory."""
        import shutil

        env, _, cwd, script, etc = mock_env
        if etc.exists():
            shutil.rmtree(etc)
        result = run_bootstrap(["--dev"], env, script=script, cwd=cwd)
        assert result.returncode == 0
        assert etc.exists()
        assert etc.is_dir()


# ── dev mode without incus ────────────────────────────────


class TestBootstrapNoIncus:
    def test_dev_without_incus_fails(self, tmp_path):
        """--dev fails if incus is not installed."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_virt = mock_bin / "systemd-detect-virt"
        mock_virt.write_text("#!/usr/bin/env bash\necho none\n")
        mock_virt.chmod(mock_virt.stat().st_mode | stat.S_IEXEC)
        mock_python = mock_bin / "python3"
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

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
