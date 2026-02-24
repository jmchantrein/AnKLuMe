"""Tests for scripts/bootstrap.sh — system initialization."""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

BOOTSTRAP_SH = Path(__file__).resolve().parent.parent / "scripts" / "bootstrap.sh"


def _patch_bootstrap_content(original, etc_dir, tmp_path):
    """Patch bootstrap.sh content to redirect system paths to tmp directories.

    Replaces /etc/anklume and /srv/anklume so the script does not require
    root access (which fails in CI environments).
    """
    srv_dir = tmp_path / "srv_anklume"
    srv_dir.mkdir(exist_ok=True)
    content = original.replace("/etc/anklume", str(etc_dir))
    return content.replace("/srv/anklume", str(srv_dir))


def _make_patched_bootstrap(tmp_path):
    """Create a patched bootstrap.sh that writes to tmp instead of /etc/anklume."""
    etc_anklume = tmp_path / "etc_anklume"
    etc_anklume.mkdir(exist_ok=True)
    patched = tmp_path / "bootstrap_patched.sh"
    original = BOOTSTRAP_SH.read_text()
    patched.write_text(_patch_bootstrap_content(original, etc_anklume, tmp_path))
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

    # Mock incus (handles all commands bootstrap uses)
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(f"""#!/usr/bin/env bash
echo "incus $@" >> "{log_file}"
if [[ "$1" == "info" ]]; then
    if [[ -n "$2" ]]; then
        echo "Status: RUNNING"
    fi
    exit 0
fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then
    exit 0
fi
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "default"
    exit 0
fi
if [[ "$1" == "launch" ]]; then
    exit 0
fi
if [[ "$1" == "start" ]]; then
    exit 0
fi
if [[ "$1" == "list" ]]; then
    echo "10.100.0.10"
    exit 0
fi
if [[ "$1" == "config" ]]; then
    if [[ "$2" == "device" && "$3" == "show" ]]; then
        echo "incus-socket:"
        echo "anklume-repo:"
        exit 0
    fi
    exit 0
fi
if [[ "$1" == "exec" ]]; then
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
        result = run_bootstrap(
            ["--prod", "--skip-apply", "--no-gpu", "--yes"],
            env, script=script, cwd=cwd,
        )
        assert result.returncode == 0
        assert "Bootstrap complete" in result.stdout

    def test_prod_with_yolo(self, mock_env):
        """--prod --YOLO sets yolo flag."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(
            ["--prod", "--YOLO", "--skip-apply", "--no-gpu", "--yes"],
            env, script=script, cwd=cwd,
        )
        assert result.returncode == 0
        assert (etc / "yolo").read_text().strip() == "true"

    def test_prod_context_values(self, mock_env):
        """--prod creates correct context."""
        env, _, cwd, script, etc = mock_env
        result = run_bootstrap(
            ["--prod", "--skip-apply", "--no-gpu", "--yes"],
            env, script=script, cwd=cwd,
        )
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
        patched.write_text(
            _patch_bootstrap_content(original, etc_anklume, tmp_path)
        )
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        result = run_bootstrap(["--dev"], env, script=patched, cwd=cwd)
        assert result.returncode == 0
        assert (etc / "vm_nested").read_text().strip() == "false"

    def test_vm_nested_set_true_by_kvm_even_without_parent(self, mock_env):
        """vm_nested becomes true via kvm detection even without parent context."""
        env, _, cwd, _, etc = mock_env

        patched = cwd / "bootstrap_kvm_fresh.sh"
        original = BOOTSTRAP_SH.read_text()
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
        patched.write_text(_patch_bootstrap_content(original, etc, cwd))
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
if [[ "$1" == "info" ]]; then
    if [[ -z "$2" ]]; then exit 1; fi
    echo "Status: RUNNING"
    exit 0
fi
if [[ "$1" == "admin" && "$2" == "init" ]]; then exit 0; fi
if [[ "$1" == "launch" ]]; then exit 0; fi
if [[ "$1" == "start" ]]; then exit 0; fi
if [[ "$1" == "list" ]]; then echo "10.100.0.10"; exit 0; fi
if [[ "$1" == "config" ]]; then
    if [[ "$2" == "device" && "$3" == "show" ]]; then
        echo "incus-socket:"
        echo "anklume-repo:"
        exit 0
    fi
    exit 0
fi
if [[ "$1" == "exec" ]]; then exit 0; fi
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
        patched.write_text(
            _patch_bootstrap_content(original, etc_anklume, tmp_path)
        )
        patched.chmod(patched.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        return env, patched, etc_anklume

    def test_ext4_maps_to_dir(self, tmp_path):
        """ext4 filesystem maps to 'dir' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "ext4")
        result = run_bootstrap(
            ["--prod", "--skip-apply", "--no-gpu", "--yes"],
            env, script=script, cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "Detected filesystem: dir" in result.stdout

    def test_btrfs_maps_to_btrfs(self, tmp_path):
        """btrfs filesystem maps to 'btrfs' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "btrfs")
        result = run_bootstrap(
            ["--prod", "--skip-apply", "--no-gpu", "--yes"],
            env, script=script, cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "Detected filesystem: btrfs" in result.stdout

    def test_zfs_maps_to_zfs(self, tmp_path):
        """ZFS filesystem maps to 'zfs' storage backend."""
        env, script, _ = self._make_fs_env(tmp_path, "zfs")
        result = run_bootstrap(
            ["--prod", "--skip-apply", "--no-gpu", "--yes"],
            env, script=script, cwd=tmp_path,
        )
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

        # Symlink essential coreutils needed by bootstrap (dirname, cd, etc.)
        for tool in ["dirname", "cat", "mkdir", "echo", "id", "getent",
                      "whoami", "grep", "awk", "tail", "cut"]:
            tool_path = f"/usr/bin/{tool}"
            if not os.path.exists(tool_path):
                tool_path = f"/bin/{tool}"
            if os.path.exists(tool_path):
                target = mock_bin / tool
                if not target.exists():
                    target.symlink_to(tool_path)

        patched, _ = _make_patched_bootstrap(tmp_path)

        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        result = run_bootstrap(["--dev"], env, script=patched, cwd=tmp_path)
        assert result.returncode != 0
        assert "not installed" in result.stderr or "not installed" in result.stdout \
            or "not found" in result.stderr \
            or "commande introuvable" in result.stderr


# ── Phase 23: new feature tests ──────────────────────────

EXPORT_DESKTOPS_SH = Path(__file__).resolve().parent.parent / "host" / "desktop" / "export-desktops.sh"
DOMAIN_MENU_SH = Path(__file__).resolve().parent.parent / "host" / "desktop" / "domain-menu.sh"


class TestShellSyntax:
    """All shell scripts must pass bash -n."""

    @pytest.mark.parametrize("script", [
        BOOTSTRAP_SH,
        EXPORT_DESKTOPS_SH,
        DOMAIN_MENU_SH,
    ])
    def test_syntax(self, script):
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error in {script.name}:\n{result.stderr}"


class TestBootstrapPhase23Structure:
    """Verify Phase 23 additions to bootstrap.sh."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_main_function_exists(self):
        assert re.search(r'^main\(\)\s*\{', self.content, re.MULTILINE), \
            "Script must have a main() function"

    def test_main_called_at_end(self):
        lines = [line.strip() for line in self.content.strip().splitlines()
                 if line.strip() and not line.strip().startswith('#')]
        assert lines[-1] == 'main "$@"', 'Script must end with: main "$@"'

    def test_detect_distro_function(self):
        assert re.search(r'^detect_distro\(\)', self.content, re.MULTILINE)

    def test_create_container_function(self):
        assert re.search(r'^create_container\(\)', self.content, re.MULTILINE)

    def test_setup_container_devices_function(self):
        assert re.search(r'^setup_container_devices\(\)', self.content, re.MULTILINE)

    def test_provision_container_function(self):
        assert re.search(r'^provision_container\(\)', self.content, re.MULTILINE)

    def test_first_apply_function(self):
        assert re.search(r'^first_apply\(\)', self.content, re.MULTILINE)

    def test_setup_host_networking_function(self):
        assert re.search(r'^setup_host_networking\(\)', self.content, re.MULTILINE)

    def test_detect_gpu_function(self):
        assert re.search(r'^detect_gpu\(\)', self.content, re.MULTILINE)

    def test_setup_boot_services_function(self):
        assert re.search(r'^setup_boot_services\(\)', self.content, re.MULTILINE)

    def test_skip_apply_flag(self):
        assert "--skip-apply" in self.content
        assert "SKIP_APPLY" in self.content

    def test_no_gpu_flag(self):
        assert "--no-gpu" in self.content
        assert "NO_GPU" in self.content

    def test_yes_flag(self):
        assert "--yes" in self.content
        assert "NON_INTERACTIVE" in self.content


class TestDistroDetection:
    """Verify detect_distro covers required distributions."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_supported_distros(self):
        for distro in ["cachyos", "arch", "debian", "ubuntu", "fedora"]:
            assert distro in self.content, f"Missing distro: {distro}"

    def test_package_managers(self):
        for pm in ["pacman", "apt", "dnf"]:
            assert pm in self.content, f"Missing package manager: {pm}"

    def test_reads_os_release(self):
        assert "/etc/os-release" in self.content

    def test_id_like_fallback(self):
        assert "ID_LIKE" in self.content


class TestContainerCreationPhase23:
    """Verify container creation and device setup."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_container_creation_idempotent(self):
        assert "already exists" in self.content

    def test_socket_proxy_device(self):
        assert "incus-socket" in self.content
        assert "unix:/var/lib/incus/unix.socket" in self.content

    def test_bind_mount_device(self):
        assert "anklume-repo" in self.content
        assert "/root/anklume" in self.content

    def test_idempotent_devices(self):
        assert self.content.count("anklume-repo") >= 2  # check + add
        assert self.content.count("incus-socket") >= 2


class TestHostNetworkingPhase23:
    """Verify host networking setup."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_ip_forwarding(self):
        assert "net.ipv4.ip_forward=1" in self.content
        assert "99-anklume.conf" in self.content

    def test_dhcp_checksum_fix(self):
        assert "CHECKSUM" in self.content
        assert "checksum-fill" in self.content

    def test_dhcp_fix_distro_gated(self):
        """DHCP checksum fix should only apply on arch/cachyos."""
        assert re.search(r'(cachyos|arch).*CHECKSUM', self.content, re.DOTALL)


class TestGPUDetection:
    """Verify GPU detection and AI offering."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_nvidia_smi(self):
        assert "nvidia-smi" in self.content

    def test_lspci_fallback(self):
        assert "lspci" in self.content

    def test_vram_reporting(self):
        assert "memory.total" in self.content

    def test_ai_tools_prompt(self):
        assert "AI-tools" in self.content


class TestFirstApply:
    """Verify first apply integration."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_make_sync_and_apply(self):
        assert "make sync && make apply" in self.content

    def test_skip_apply_flag(self):
        assert "SKIP_APPLY" in self.content


class TestBootServices:
    """Verify boot services integration."""

    @classmethod
    def setup_class(cls):
        cls.content = BOOTSTRAP_SH.read_text()

    def test_calls_setup_boot_services(self):
        assert "setup-boot-services.sh" in self.content


class TestExportDesktopsScript:
    """Verify host/desktop/export-desktops.sh."""

    @classmethod
    def setup_class(cls):
        cls.content = EXPORT_DESKTOPS_SH.read_text()

    def test_exists(self):
        assert EXPORT_DESKTOPS_SH.is_file()

    def test_shebang(self):
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_remove_flag(self):
        assert "--remove" in self.content

    def test_installs_to_local_share(self):
        assert ".local/share/applications" in self.content

    def test_update_desktop_database(self):
        assert "update-desktop-database" in self.content

    def test_calls_desktop_config(self):
        assert "desktop_config.py" in self.content

    def test_idempotent_copy(self):
        assert "cp -f" in self.content

    def test_main_wrapper(self):
        lines = [line.strip() for line in self.content.strip().splitlines()
                 if line.strip() and not line.strip().startswith('#')]
        assert lines[-1] == 'main "$@"'


class TestDomainMenuScript:
    """Verify host/desktop/domain-menu.sh."""

    @classmethod
    def setup_class(cls):
        cls.content = DOMAIN_MENU_SH.read_text()

    def test_exists(self):
        assert DOMAIN_MENU_SH.is_file()

    def test_shebang(self):
        assert self.content.startswith("#!/usr/bin/env bash")

    def test_exec_flag(self):
        assert "--exec" in self.content

    def test_list_flag(self):
        assert "--list" in self.content

    def test_launchers(self):
        for launcher in ["fuzzel", "rofi", "dmenu"]:
            assert launcher in self.content, f"Missing launcher: {launcher}"

    def test_reads_infra_yml(self):
        assert "infra.yml" in self.content

    def test_trust_levels(self):
        for level in ["admin", "trusted", "semi-trusted", "untrusted", "disposable"]:
            assert level in self.content, f"Missing trust level: {level}"

    def test_fallback_no_launcher(self):
        assert '"none"' in self.content

    def test_main_wrapper(self):
        lines = [line.strip() for line in self.content.strip().splitlines()
                 if line.strip() and not line.strip().startswith('#')]
        assert lines[-1] == 'main "$@"'
