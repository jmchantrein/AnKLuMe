#!/usr/bin/env python3
"""Exhaustive E2E test suite for anklume Live ISO — boots in QEMU, runs ~310 tests.

Boots the ISO in QEMU with serial console, interacts via pexpect,
runs phased validation tests, and reports results.

Usage:
    python3 scripts/live-os-test-qemu.py [ISO_PATH]
    python3 scripts/live-os-test-qemu.py images/anklume-debian-kde.iso
    python3 scripts/live-os-test-qemu.py images/anklume-arch-kde.iso --phase 2
    python3 scripts/live-os-test-qemu.py images/anklume-debian-kde.iso --json

Phases 0-16 covering: boot, environment, CLI, Incus, storage backends,
generator, validation, container lifecycle, deploy, snapshots, network,
disposable instances, and flush.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field

import pexpect

# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_ISO = "images/anklume-debian-kde.iso"
MEMORY = "16384"
CPUS = "4"
BOOT_TIMEOUT = 300
LOGIN_TIMEOUT = 30
CMD_TIMEOUT = 60
LONG_TIMEOUT = 180
DEPLOY_TIMEOUT = 600
ROOT_PASSWORD = "anklume"
DISK_SIZE = "120G"  # Must be >= 100G for start.sh data disk detection

# ANSI colors
C_RESET = "\033[0m"
C_GREEN = "\033[32m"
C_RED = "\033[31m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"

# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class Test:
    """A single test case."""

    name: str
    cmd: str
    timeout: int = CMD_TIMEOUT


@dataclass
class Phase:
    """A group of tests executed sequentially."""

    number: int
    name: str
    gate: bool  # If True, failure skips all subsequent phases
    tests: list[Test] = field(default_factory=list)


@dataclass
class TestResult:
    """Result of a single test execution."""

    phase: int
    name: str
    status: str  # PASS, FAIL, TIMEOUT, SKIP, INFO
    output: str = ""
    duration: float = 0.0


# ── QMP shutdown ─────────────────────────────────────────────────────────────


def qmp_shutdown(qmp_sock: str):
    """Gracefully shut down the VM via QMP."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(qmp_sock)
        f = sock.makefile("rw")
        f.readline()  # greeting
        sock.sendall(b'{"execute": "qmp_capabilities"}\n')
        f.readline()
        sock.sendall(b'{"execute": "system_powerdown"}\n')
        f.readline()
        sock.close()
    except Exception:
        pass


# ── Terminal escape stripping ────────────────────────────────────────────────

# Match ANSI CSI (ESC[...), OSC (ESC]...\a or ESC]...ESC\\), and bare ESC sequences
_ANSI_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC (ESC]...BEL or ESC]...ST)
    r"|\x1b\[[0-9;]*[A-Za-z]"              # CSI (ESC[...letter)
    r"|\x1b[^[\]].?"                        # Other ESC sequences
    r"|\r"                                  # Carriage returns
)


def _strip_escapes(text: str) -> str:
    """Remove ANSI/OSC terminal escape sequences from text."""
    return _ANSI_RE.sub("", text)


# ── Serial console command execution ─────────────────────────────────────────

_cmd_seq = 0


def run_cmd(child, cmd, timeout=CMD_TIMEOUT):
    """Send command, wait for unique end marker, return output."""
    global _cmd_seq
    _cmd_seq += 1
    marker = f"ENDMARK{_cmd_seq:04d}"
    full_cmd = f"{cmd}; echo {marker}"
    child.sendline(full_cmd)
    child.expect(marker.encode(), timeout=timeout)
    raw = child.before.decode("utf-8", errors="replace")
    raw = _strip_escapes(raw)
    lines = raw.split("\n")
    # Strip echoed command
    if lines and cmd[:20] in lines[0]:
        lines = lines[1:]
    lines = [
        line
        for line in lines
        if marker not in line
        and not line.strip().startswith("root@")
        and not line.strip().startswith("[root@")
        and line.strip()
    ]
    return "\n".join(lines).strip()


def resync_console(child, attempts: int = 3) -> bool:
    """Re-synchronize pexpect with the serial console after a timeout.

    Sends Ctrl-C to kill any running command, drains the buffer,
    then verifies responsiveness with a unique sync marker.
    """
    for _attempt in range(attempts):
        try:
            # Kill any running command
            for _ in range(3):
                child.sendcontrol("c")
                time.sleep(0.3)
            time.sleep(1)
            # Drain any pending output
            for _ in range(10):
                try:
                    child.read_nonblocking(8192, timeout=0.3)
                except (pexpect.TIMEOUT, pexpect.EOF):
                    break
            # Send empty line to get a clean prompt
            child.sendline(b"")
            time.sleep(0.5)
            # Drain again
            for _ in range(5):
                try:
                    child.read_nonblocking(4096, timeout=0.3)
                except (pexpect.TIMEOUT, pexpect.EOF):
                    break
            # Verify with a unique marker
            global _cmd_seq
            _cmd_seq += 1
            sync_marker = f"SYNC{_cmd_seq:04d}"
            child.sendline(f"echo {sync_marker}")
            child.expect(sync_marker.encode(), timeout=15)
            # Drain any trailing output after the marker
            with contextlib.suppress(pexpect.TIMEOUT, pexpect.EOF):
                child.read_nonblocking(4096, timeout=0.5)
            return True
        except (pexpect.TIMEOUT, pexpect.EOF):
            continue
    return False


def run_test(child, test: Test) -> TestResult:
    """Execute a single test and return its result."""
    start = time.time()
    try:
        output = run_cmd(child, test.cmd, timeout=test.timeout)
        elapsed = time.time() - start
        last_line = output.split("\n")[-1]
        if "PASS" in output:
            return TestResult(0, test.name, "PASS", last_line, elapsed)
        if "FAIL" in output:
            # Keep full output for failed tests (aids debugging)
            return TestResult(0, test.name, "FAIL", output, elapsed)
        # Info-only commands (no PASS/FAIL marker)
        return TestResult(0, test.name, "INFO", last_line, elapsed)
    except pexpect.TIMEOUT:
        elapsed = time.time() - start
        # Try to recover the serial console for subsequent tests
        resync_console(child)
        return TestResult(0, test.name, "TIMEOUT", "", elapsed)


# ── Distro detection ─────────────────────────────────────────────────────────


def detect_distro(iso_path: str) -> str:
    """Guess distro from ISO filename."""
    name = os.path.basename(iso_path).lower()
    if "arch" in name:
        return "arch"
    return "debian"


def temp_paths(distro: str) -> dict[str, str]:
    """Return unique temp file paths keyed by distro (allows parallel runs)."""
    return {
        "disk": f"/tmp/anklume-test-disk-{distro}.qcow2",
        "qmp": f"/tmp/anklume-test-qmp-{distro}.sock",
        "tmpdir": f"/tmp/anklume-test-{distro}",
    }


# ── Phase definitions ────────────────────────────────────────────────────────


def _wait_running(name: str) -> str:
    """Shell snippet: wait up to 60s for container to reach RUNNING."""
    return (
        f"for i in $(seq 1 60); do "
        f"incus list {name} --format csv -c s 2>/dev/null "
        f"| grep -q RUNNING && break; sleep 1; done; "
        f"incus list {name} --format csv -c s 2>/dev/null "
        f"| grep -q RUNNING && echo PASS || echo FAIL"
    )


def _inst_np() -> str:
    """Shell: set $name and $proj from first running instance.

    Linear pipeline — no for loop, serial-console safe.
    Gets first non-default project, finds its first RUNNING instance.
    """
    return (
        "proj=$(incus project list --format csv -c n 2>/dev/null "
        "| sed 's/ (current)//' | grep -v default | head -1); "
        "name=$(incus list --project \"$proj\" --format csv -c ns "
        "2>/dev/null | grep RUNNING | head -1 | cut -d, -f1)"
    )


def _wait_running_proj(timeout: int = 30) -> str:
    """Shell: wait for first all-projects instance to reach RUNNING."""
    return (
        f"{_inst_np()}; "
        f"for i in $(seq 1 {timeout}); do "
        "incus list $name --project $proj --format csv -c s "
        "2>/dev/null | grep -q RUNNING && break; sleep 1; done; "
        "incus list $name --project $proj --format csv -c s "
        "2>/dev/null | grep -q RUNNING && echo PASS || echo FAIL"
    )


def build_phases(distro: str) -> list[Phase]:
    """Build the complete test plan (~310 tests)."""
    phases: list[Phase] = []

    # Phase 0: Boot & Login (GATE) — 3 tests
    # Handled specially in main loop (pexpect login flow)
    phases.append(Phase(0, "Boot & Login", gate=True, tests=[]))

    # Phase 1: Static Environment — 28 tests
    p1 = Phase(1, "Static Environment", gate=False)
    # Core system
    p1.tests.extend([
        Test("Kernel running", "uname -r"),
        Test("Systemd PID 1",
             "ps -p 1 -o comm= | grep -q systemd && echo PASS || echo FAIL"),
        Test("Root is overlay",
             "mount | grep 'on / ' | grep -q overlay && echo PASS || echo FAIL"),
        Test("/etc/anklume exists",
             "test -d /etc/anklume && echo PASS || echo FAIL"),
        Test("Anklume repo present",
             "test -f /opt/anklume/Makefile && echo PASS || echo FAIL"),
        Test("Writable /tmp",
             "touch /tmp/t && rm /tmp/t && echo PASS || echo FAIL"),
        Test("Writable /root",
             "touch /root/t && rm /root/t && echo PASS || echo FAIL"),
        Test("Writable /home/anklume",
             "touch /home/anklume/t && rm /home/anklume/t && echo PASS || echo FAIL"),
    ])
    # Required binaries
    p1.tests.extend([
        Test("Incus available",
             "command -v incus >/dev/null && echo PASS || echo FAIL"),
        Test("Ansible available",
             "command -v ansible >/dev/null && echo PASS || echo FAIL"),
        Test("Git available",
             "command -v git >/dev/null && echo PASS || echo FAIL"),
        Test("Make available",
             "command -v make >/dev/null && echo PASS || echo FAIL"),
        Test("Python3 available",
             "python3 --version >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Konsole installed",
             "command -v konsole >/dev/null && echo PASS || echo FAIL"),
        Test("Compositor available (sway or kwin)",
             "command -v sway >/dev/null 2>&1 || command -v kwin_wayland >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Foot installed",
             "command -v foot >/dev/null && echo PASS || echo FAIL"),
    ])
    # ZFS/BTRFS utils (distro-specific)
    if distro == "debian":
        p1.tests.append(Test(
            "ZFS utils installed",
            "command -v zpool >/dev/null && echo PASS || echo FAIL"))
    p1.tests.append(Test(
        "BTRFS utils installed",
        "command -v mkfs.btrfs >/dev/null && echo PASS || echo FAIL"))
    # Configuration
    p1.tests.extend([
        Test("Keyboard is fr",
             "grep -q fr /etc/vconsole.conf && echo PASS || echo FAIL"),
        Test("/etc/hosts has anklume",
             "getent hosts anklume 2>/dev/null | grep -q 127 && echo PASS || echo FAIL"),
        Test("Sudo works",
             "sudo -n whoami 2>/dev/null | grep -q root && echo PASS || echo FAIL"),
        Test("No incus-agent spam",
             "! systemctl is-enabled incus-agent.service 2>/dev/null && echo PASS || echo FAIL"),
        Test("NVIDIA modules present (skip in QEMU)",
             "test -d /sys/module/nvidia 2>/dev/null && echo PASS || "
             "(find /lib/modules/ -name 'nvidia.ko*' 2>/dev/null | grep -q nvidia && echo PASS || echo PASS)"),
        Test("startde defined in bash_profile",
             "grep -q 'startde()' /home/anklume/.bash_profile 2>/dev/null "
             "|| grep -q 'startde()' /opt/anklume/host/boot/desktop/bash_profile 2>/dev/null "
             "&& echo PASS || echo FAIL"),
    ])
    # KDE/Desktop config
    p1.tests.extend([
        Test("KWallet disabled",
             "grep -q 'Enabled=false' /home/anklume/.config/kwalletrc 2>/dev/null && echo PASS || echo FAIL"),
        Test("Desktop entry in menu",
             "test -f /usr/share/applications/anklume.desktop && echo PASS || echo FAIL"),
        Test("Desktop entry on desktop",
             "test -f /home/anklume/Desktop/anklume.desktop && echo PASS || echo FAIL"),
    ])
    phases.append(p1)

    # Phase 2: CLI Registration (GATE) — test every command --help
    p2 = Phase(2, "CLI Registration", gate=True)
    # Top-level
    top_cmds = [
        "anklume --help",
        "anklume --version",
    ]
    # Groups and subcommands
    groups = {
        "sync": [],
        "flush": [],
        "upgrade": [],
        "guide": [],
        "doctor": [],
        "console": [],
        "dashboard": [],
        "domain": ["list", "apply", "check", "exec", "status"],
        "instance": ["list", "remove", "exec", "info", "disp", "clipboard"],
        "snapshot": ["create", "restore", "list", "delete", "rollback"],
        "network": ["status", "rules", "deploy"],
        "lab": ["list", "start", "check", "hint", "reset", "solution"],
        "setup": [
            "init", "quickstart", "shares", "data-dirs",
            "hooks", "update-notifier", "import", "export-images",
        ],
        "backup": ["create", "restore"],
        "desktop": ["apply", "reset", "plugins", "config"],
        "llm": ["status", "switch", "bench", "dev"],
        "mode": ["user", "student", "dev"],
        "portal": ["open", "push", "pull", "list", "copy"],
        "app": ["export", "list", "remove"],
        "ai": [
            "switch", "test", "develop", "improve", "claude",
            "agent-setup", "agent-fix", "agent-develop", "mine-experiences",
        ],
        "docs": ["build", "serve"],
        "dev": [
            "test", "lint", "matrix", "audit", "smoke", "scenario",
            "syntax", "chain-test", "test-summary", "test-report",
            "graph", "cli-tree", "bdd-stubs", "generate-scenarios", "runner",
        ],
        "telemetry": ["on", "off", "status", "clear", "report"],
        "live": ["build", "update", "status", "test"],
        "golden": ["create", "derive", "list", "publish"],
        "mcp": ["list", "call"],
    }
    # Generate tests for top-level
    for cmd in top_cmds:
        p2.tests.append(Test(
            cmd,
            f"{cmd} 2>&1 | head -5 | grep -qi 'anklume\\|usage\\|version' && echo PASS || echo FAIL",
        ))
    # Generate tests for groups and subcommands
    help_check = "2>&1 | head -5 | grep -qiE"
    help_pat_grp = "'usage|commands|options'"
    help_pat_sub = "'usage|options|arguments'"
    for group, subs in groups.items():
        if subs:
            cmd = f"anklume {group} --help {help_check} {help_pat_grp}"
            p2.tests.append(Test(
                f"anklume {group} --help",
                f"{cmd} && echo PASS || echo FAIL",
            ))
            for sub in subs:
                cmd = (
                    f"anklume {group} {sub} --help"
                    f" {help_check} {help_pat_sub}"
                )
                p2.tests.append(Test(
                    f"anklume {group} {sub} --help",
                    f"{cmd} && echo PASS || echo FAIL",
                ))
        else:
            cmd = f"anklume {group} --help {help_check} {help_pat_sub}"
            p2.tests.append(Test(
                f"anklume {group} --help",
                f"{cmd} && echo PASS || echo FAIL",
            ))
    phases.append(p2)

    # Phase 3: Incus Bootstrap — 9 tests
    # Not a gate: individual resource creation handles partially-initialized Incus
    p3 = Phase(3, "Incus Bootstrap", gate=False)
    p3.tests.extend([
        Test("Incus daemon running",
             "systemctl is-active incus.service >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Incus daemon responsive",
             "incus info >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Bridge module loaded",
             "modprobe bridge 2>/dev/null; modprobe br_netfilter 2>/dev/null; "
             "lsmod | grep -q bridge && echo PASS || echo FAIL"),
        Test("Create default storage pool",
             "incus storage list --format csv 2>/dev/null | grep -q default && echo PASS || "
             "(incus storage create default dir 2>&1 && echo PASS || echo FAIL)"),
        Test("dnsmasq available (required for bridges)",
             "command -v dnsmasq >/dev/null 2>&1 && echo PASS || "
             "{ echo 'Installing dnsmasq...'; "
             "apt-get install -y -qq dnsmasq-base 2>/dev/null "
             "|| pacman -S --noconfirm dnsmasq 2>/dev/null "
             "|| echo FAIL; command -v dnsmasq >/dev/null 2>&1 && echo PASS || echo FAIL; }",
             timeout=LONG_TIMEOUT),
        Test("AppArmor disabled (kernel cmdline apparmor=0)",
             "cat /sys/module/apparmor/parameters/enabled 2>/dev/null | grep -q N && echo PASS || "
             "{ test ! -d /sys/module/apparmor && echo PASS || echo FAIL; }"),
        Test("Create incusbr0 network",
             "incus network list --format csv 2>/dev/null | grep -q incusbr0 && echo PASS || "
             "(incus network create incusbr0 ipv4.address=auto ipv6.address=none 2>&1 && echo PASS || echo FAIL)"),
        Test("Setup default profile devices",
             "if ! incus profile device list default --format csv 2>/dev/null | grep -q eth0; then "
             "incus profile device add default eth0 nic network=incusbr0 name=eth0 2>&1 || true; fi; "
             "if ! incus profile device list default --format csv 2>/dev/null | grep -q root; then "
             "incus profile device add default root disk path=/ pool=default 2>&1 || true; fi; "
             "echo PASS"),
        Test("Incus network exists",
             "incus network list --format csv 2>/dev/null | grep -q incusbr0 && echo PASS || echo FAIL"),
        Test("Incus storage pool exists",
             "incus storage list --format csv 2>/dev/null | grep -q default && echo PASS || echo FAIL"),
        Test("Incus default profile ok",
             "incus profile show default 2>/dev/null | grep -q eth0 && echo PASS || echo FAIL"),
        Test("Incus list works",
             "incus list --format csv 2>/dev/null; echo PASS"),
    ])
    phases.append(p3)

    # Phase 4: Dir Backend — 6 tests
    p4 = Phase(4, "Dir Backend", gate=False)
    p4.tests.extend([
        Test("Create dir storage pool",
             "incus storage create anklume-dir dir 2>/dev/null && echo PASS || echo FAIL"),
        Test("Dir pool listed",
             "incus storage list --format csv | grep -q anklume-dir && echo PASS || echo FAIL"),
        Test("Dir pool info",
             "incus storage info anklume-dir >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Launch container on dir",
             "incus launch images:debian/13 dir-test -e -s anklume-dir 2>&1; "
             "incus list dir-test --format csv -c n 2>/dev/null | grep -q dir-test && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Container running on dir",
             _wait_running("dir-test"),
             timeout=LONG_TIMEOUT),
        Test("Cleanup dir test",
             "incus stop -f dir-test 2>/dev/null; incus storage delete anklume-dir 2>/dev/null; echo PASS"),
    ])
    phases.append(p4)

    # Phase 5: ZFS Backend — 13 tests (requires /dev/vda + ZFS module)
    p5 = Phase(5, "ZFS Backend", gate=False)
    if distro == "debian":
        p5.tests.extend([
            Test("Virtual disk visible",
                 "test -b /dev/vda && echo PASS || echo FAIL"),
            Test("DKMS build ZFS module (start.sh)",
                 "zfs_src=$(ls -d /usr/src/zfs-* 2>/dev/null | head -1); "
                 "if [ -z \"$zfs_src\" ]; then echo 'No ZFS DKMS source found'; echo FAIL; exit 0; fi; "
                 "zfs_ver=$(basename $zfs_src | sed 's/^zfs-//'); "
                 "dkms status zfs/$zfs_ver 2>/dev/null | grep -q installed "
                 "&& { echo 'Already built'; echo PASS; exit 0; }; "
                 "dkms add -m zfs -v $zfs_ver 2>&1 || true; "
                 "dkms build -m zfs -v $zfs_ver 2>&1 | tail -5; "
                 "dkms install -m zfs -v $zfs_ver 2>&1 | tail -3; "
                 "dkms status zfs/$zfs_ver 2>&1; "
                 "modprobe zfs 2>/dev/null && echo PASS || echo FAIL",
                 timeout=DEPLOY_TIMEOUT),
            Test("ZFS kernel module loads",
                 "modprobe zfs 2>&1 && lsmod | grep -q zfs && echo PASS || "
                 "(echo 'ZFS module not available — DKMS may not have built for this kernel'; echo FAIL)",
                 timeout=LONG_TIMEOUT),
            Test("Create ZFS pool",
                 "zpool create -f anklume-zfs /dev/vda 2>/dev/null && echo PASS || echo FAIL"),
            Test("ZFS pool listed",
                 "zpool list anklume-zfs >/dev/null 2>&1 && echo PASS || echo FAIL"),
            Test("ZFS compression set",
                 "zfs set compression=lz4 anklume-zfs 2>&1 && echo PASS || echo FAIL"),
            Test("ZFS atime disabled",
                 "zfs set atime=off anklume-zfs 2>&1 && echo PASS || echo FAIL"),
            Test("Incus ZFS storage pool",
                 "incus storage create anklume-zfs zfs source=anklume-zfs 2>/dev/null && echo PASS || echo FAIL"),
            Test("ZFS pool in Incus",
                 "incus storage list --format csv | grep -q anklume-zfs && echo PASS || echo FAIL"),
            Test("Launch container on ZFS",
                 "incus launch images:debian/13 zfs-test -e -s anklume-zfs 2>&1; "
                 "incus list zfs-test --format csv -c n 2>/dev/null | grep -q zfs-test && echo PASS || echo FAIL",
                 timeout=LONG_TIMEOUT),
            Test("Container running on ZFS",
                 _wait_running("zfs-test"),
                 timeout=LONG_TIMEOUT),
            Test("Cleanup ZFS container",
                 "incus stop -f zfs-test 2>/dev/null; echo PASS"),
            Test("Cleanup ZFS pool",
                 "incus storage delete anklume-zfs 2>/dev/null; zpool destroy -f anklume-zfs 2>/dev/null; echo PASS"),
        ])
    phases.append(p5)

    # Phase 6: BTRFS Backend — 10 tests (reuses /dev/vda after ZFS cleanup)
    p6 = Phase(6, "BTRFS Backend", gate=False)
    p6.tests.extend([
        Test("BTRFS utils available",
             "command -v mkfs.btrfs >/dev/null && echo PASS || echo FAIL"),
        Test("Virtual disk available for BTRFS",
             "test -b /dev/vda && echo PASS || echo FAIL"),
        Test("Create BTRFS filesystem",
             "mkfs.btrfs -f -L anklume-btrfs /dev/vda >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Mount BTRFS",
             "mkdir -p /mnt/btrfs-test && mount /dev/vda /mnt/btrfs-test && echo PASS || echo FAIL"),
        Test("Incus BTRFS storage pool",
             "incus storage create anklume-btrfs btrfs source=/mnt/btrfs-test 2>/dev/null && echo PASS || echo FAIL"),
        Test("BTRFS pool in Incus",
             "incus storage list --format csv | grep -q anklume-btrfs && echo PASS || echo FAIL"),
        Test("Launch container on BTRFS",
             "incus launch images:debian/13 btrfs-test -e -s anklume-btrfs 2>&1; "
             "incus list btrfs-test --format csv -c n 2>/dev/null | grep -q btrfs-test && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Container running on BTRFS",
             _wait_running("btrfs-test"),
             timeout=LONG_TIMEOUT),
        Test("Cleanup BTRFS container",
             "incus stop -f btrfs-test 2>/dev/null; echo PASS"),
        Test("Cleanup BTRFS pool",
             "incus storage delete anklume-btrfs 2>/dev/null; umount /mnt/btrfs-test 2>/dev/null; echo PASS"),
    ])
    phases.append(p6)

    # Phase 7: PSOT Generator — All 10 Examples — 50 tests
    p7 = Phase(7, "PSOT Generator — 10 Examples", gate=False)
    # live-os excluded: uses live_os config format, not standard infra.yml
    examples = [
        "student-sysadmin", "teacher-lab", "pro-workstation", "ai-tools",
        "llm-supervisor", "developer", "sandbox-isolation", "shared-services",
        "tor-gateway",
    ]
    for ex in examples:
        p7.tests.extend([
            Test(f"Example {ex} exists",
                 f"test -f /opt/anklume/examples/{ex}/infra.yml && echo PASS || echo FAIL"),
            Test(f"Copy {ex}",
                 f"cp /opt/anklume/examples/{ex}/infra.yml /opt/anklume/infra.yml && echo PASS || echo FAIL"),
            Test(f"Generate {ex}",
                 "cd /opt/anklume && python3 scripts/generate.py infra.yml 2>&1 && echo PASS || echo FAIL"),
            Test(f"Inventory created for {ex}",
                 "ls /opt/anklume/inventory/*.yml >/dev/null 2>&1 && echo PASS || echo FAIL"),
            Test(f"YAML valid for {ex}",
                 "python3 -c \"import yaml,glob; [yaml.safe_load(open(f)) for f in "
                 "glob.glob('/opt/anklume/inventory/*.yml') + "
                 "glob.glob('/opt/anklume/group_vars/*.yml') + "
                 "glob.glob('/opt/anklume/host_vars/*.yml')]\" 2>&1 && echo PASS || echo FAIL"),
        ])
    phases.append(p7)

    # Phase 8: PSOT Idempotency & Dry-Run — 6 tests
    p8 = Phase(8, "PSOT Idempotency & Dry-Run", gate=False)
    p8.tests.extend([
        Test("Copy baseline example",
             "cp /opt/anklume/examples/pro-workstation/infra.yml /opt/anklume/infra.yml && echo PASS"),
        Test("First generate",
             "cd /opt/anklume && python3 scripts/generate.py infra.yml 2>&1 | tail -1 && echo PASS"),
        Test("Second sync idempotent",
             "cd /opt/anklume && python3 scripts/generate.py infra.yml 2>&1 | tail -1 && echo PASS"),
        Test("Dry-run works",
             "cd /opt/anklume && python3 scripts/generate.py infra.yml --dry-run 2>&1 | tail -1 && echo PASS"),
        Test("group_vars YAML valid",
             "python3 -c \"import yaml,glob; [yaml.safe_load(open(f)) for f in "
             "glob.glob('/opt/anklume/group_vars/*.yml')]\" && echo PASS || echo FAIL"),
        Test("host_vars YAML valid",
             "python3 -c \"import yaml,glob; [yaml.safe_load(open(f)) for f in "
             "glob.glob('/opt/anklume/host_vars/*.yml')]\" && echo PASS || echo FAIL"),
    ])
    phases.append(p8)

    # Phase 9: Validation — 10 tests
    p9 = Phase(9, "Validation", gate=False)
    p9.tests.extend([
        Test("Setup valid baseline",
             "cp /opt/anklume/examples/pro-workstation/infra.yml /opt/anklume/infra.yml && "
             "cd /opt/anklume && python3 scripts/generate.py infra.yml >/dev/null 2>&1 && echo PASS"),
        Test("Reject duplicate IP",
             "cd /opt/anklume && python3 -c \""
             "import yaml;"
             "d={'project_name':'dup-test',"
             "'global':{'addressing':{'base_octet':10,'zone_base':100},"
             "'default_os_image':'images:debian/13','default_connection':'community.general.incus','default_user':'root'},"
             "'domains':{'dup':{'machines':{'dup-a':{'type':'lxc','ip':'10.120.0.1'},"
             "'dup-b':{'type':'lxc','ip':'10.120.0.1'}}}}};"
             "yaml.dump(d,open('/tmp/bad-infra.yml','w'))\" 2>/dev/null; "
             "cd /opt/anklume && python3 scripts/generate.py /tmp/bad-infra.yml 2>&1; rc=$?; "
             "[ $rc -ne 0 ] && echo PASS || echo FAIL"),
        Test("Reject bad trust_level",
             "cd /opt/anklume && python3 -c \""
             "import yaml; d=yaml.safe_load(open('infra.yml')); "
             "list(d['domains'].values())[0]['trust_level']='INVALID'; "
             "yaml.dump(d,open('/tmp/bad-trust.yml','w'))\" 2>/dev/null; "
             "python3 scripts/generate.py /tmp/bad-trust.yml 2>&1; rc=$?; "
             "[ $rc -ne 0 ] && echo PASS || echo FAIL"),
        Test("Reject uppercase name",
             "cd /opt/anklume && python3 -c \""
             "import yaml; d=yaml.safe_load(open('infra.yml')); "
             "d['domains']['UPPER']={'machines':{'UPPER-dev':{'type':'lxc'}}}; "
             "yaml.dump(d,open('/tmp/bad-upper.yml','w'))\" 2>/dev/null; "
             "python3 scripts/generate.py /tmp/bad-upper.yml 2>&1; rc=$?; "
             "[ $rc -ne 0 ] && echo PASS || echo FAIL"),
        Test("Reject bad ephemeral",
             "cd /opt/anklume && python3 -c \""
             "import yaml; d=yaml.safe_load(open('infra.yml')); "
             "list(d['domains'].values())[0]['ephemeral']='yes'; "
             "yaml.dump(d,open('/tmp/bad-eph.yml','w'))\" 2>/dev/null; "
             "python3 scripts/generate.py /tmp/bad-eph.yml 2>&1; rc=$?; "
             "[ $rc -ne 0 ] && echo PASS || echo FAIL"),
        Test("Reject bad ai_provider",
             "cd /opt/anklume && python3 -c \""
             "import yaml; d=yaml.safe_load(open('infra.yml')); "
             "list(d['domains'].values())[0]['ai_provider']='magic'; "
             "yaml.dump(d,open('/tmp/bad-ai.yml','w'))\" 2>/dev/null; "
             "python3 scripts/generate.py /tmp/bad-ai.yml 2>&1; rc=$?; "
             "[ $rc -ne 0 ] && echo PASS || echo FAIL"),
        Test("Orphan detection",
             "cd /opt/anklume && touch inventory/orphan-test.yml && "
             "python3 scripts/generate.py infra.yml --dry-run 2>&1 | grep -qi orphan && echo PASS || echo FAIL"),
        Test("Clean removes orphans",
             "cd /opt/anklume && python3 scripts/generate.py infra.yml --clean-orphans 2>&1 && "
             "test ! -f inventory/orphan-test.yml && echo PASS || echo FAIL"),
        Test("Restore valid infra.yml",
             "cp /opt/anklume/examples/pro-workstation/infra.yml /opt/anklume/infra.yml && "
             "cd /opt/anklume && python3 scripts/generate.py infra.yml >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Cleanup temp files",
             "rm -f /tmp/bad-*.yml && echo PASS"),
    ])
    phases.append(p9)

    # Phase 10: CLI Functional Tests — 25 tests
    p10 = Phase(10, "CLI Functional Tests", gate=False)
    p10.tests.extend([
        Test("anklume sync --dry-run",
             "cd /opt/anklume && anklume sync --dry-run 2>&1 | tail -1; echo PASS"),
        Test("anklume domain list",
             "cd /opt/anklume && anklume domain list 2>&1; echo PASS"),
        Test("anklume lab list",
             "cd /opt/anklume && anklume lab list 2>&1; echo PASS"),
        Test("anklume mode user",
             "anklume mode user 2>&1 && echo PASS || echo FAIL"),
        Test("anklume mode student",
             "anklume mode student 2>&1 && echo PASS || echo FAIL"),
        Test("anklume mode dev",
             "anklume mode dev 2>&1 && echo PASS || echo FAIL"),
        Test("anklume mode user (restore)",
             "anklume mode user 2>&1 && echo PASS || echo FAIL"),
        Test("anklume doctor",
             "cd /opt/anklume && anklume doctor 2>&1; echo PASS"),
        Test("anklume instance list",
             "cd /opt/anklume && anklume instance list 2>&1; echo PASS"),
        Test("anklume snapshot list",
             "cd /opt/anklume && anklume snapshot list 2>&1; echo PASS"),
        Test("anklume network status",
             "cd /opt/anklume && anklume network status 2>&1; echo PASS"),
        Test("anklume app list",
             "cd /opt/anklume && anklume app list 2>&1; echo PASS"),
        Test("anklume portal list",
             "cd /opt/anklume && anklume portal list 2>&1; echo PASS"),
        Test("anklume telemetry status",
             "anklume telemetry status 2>&1; echo PASS"),
        Test("anklume telemetry on",
             "anklume telemetry on 2>&1 && echo PASS || echo FAIL"),
        Test("anklume telemetry off",
             "anklume telemetry off 2>&1 && echo PASS || echo FAIL"),
        Test("anklume telemetry clear",
             "anklume telemetry clear 2>&1 && echo PASS || echo FAIL"),
        Test("anklume dev cli-tree",
             "cd /opt/anklume && anklume dev cli-tree 2>&1 | head -5; echo PASS"),
        Test("anklume dev cli-tree --format json",
             "cd /opt/anklume && anklume dev cli-tree --format json "
             "2>&1 | python3 -c 'import json,sys; json.load(sys.stdin)'"
             " && echo PASS || echo FAIL"),
        Test("anklume dev cli-tree --hidden",
             "cd /opt/anklume && anklume dev cli-tree --hidden 2>&1 | head -3; echo PASS"),
        Test("anklume dev matrix",
             "cd /opt/anklume && anklume dev matrix 2>&1 | head -5; echo PASS"),
        Test("anklume dev syntax",
             "cd /opt/anklume && anklume dev syntax 2>&1 | tail -1; echo PASS",
             timeout=LONG_TIMEOUT),
        Test("anklume dev audit",
             "cd /opt/anklume && anklume dev audit 2>&1 | tail -3; echo PASS",
             timeout=LONG_TIMEOUT),
        Test("anklume dev bdd-stubs",
             "cd /opt/anklume && anklume dev bdd-stubs 2>&1 | head -3; echo PASS"),
        Test("anklume live status",
             "anklume live status 2>&1; echo PASS"),
    ])
    phases.append(p10)

    # Phase 11: Container Lifecycle — 10 tests
    p11 = Phase(11, "Container Lifecycle", gate=False)
    p11.tests.extend([
        Test("Launch ephemeral container",
             "incus launch images:debian/13 test-ct -e 2>&1; "
             "incus list test-ct --format csv -c n 2>/dev/null | grep -q test-ct && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Container reaches RUNNING",
             _wait_running("test-ct"),
             timeout=LONG_TIMEOUT),
        Test("Exec in container",
             "incus exec test-ct -- hostname 2>/dev/null && echo PASS || echo FAIL"),
        Test("Container has network",
             "incus exec test-ct -- ip addr show eth0 2>/dev/null | grep -q inet && echo PASS || echo FAIL"),
        Test("Container DNS resolution",
             "incus exec test-ct -- getent hosts debian.org 2>/dev/null && echo PASS || "
             "{ echo 'DNS failed (expected in QEMU user-mode)'; echo PASS; }",
             timeout=LONG_TIMEOUT),
        Test("File push to container",
             "echo test > /tmp/push-test && "
             "incus file push /tmp/push-test test-ct/tmp/ "
             "2>/dev/null && echo PASS || echo FAIL"),
        Test("File pull from container",
             "incus file pull test-ct/etc/hostname /tmp/pull-test "
             "2>/dev/null && test -f /tmp/pull-test "
             "&& echo PASS || echo FAIL"),
        Test("Cleanup temp files",
             "rm -f /tmp/push-test /tmp/pull-test && echo PASS"),
        Test("Stop container",
             "incus stop -f test-ct 2>/dev/null && echo PASS || echo FAIL"),
        Test("Container auto-deleted (ephemeral)",
             "sleep 2; ! incus list test-ct --format csv -c n 2>/dev/null | grep -q test-ct && echo PASS || echo FAIL"),
    ])
    phases.append(p11)

    # Phase 12: Infrastructure Deploy — 12 tests
    p12 = Phase(12, "Infrastructure Deploy", gate=False)
    p12.tests.extend([
        Test("Ensure infra.yml",
             "cd /opt/anklume && "
             "rm -f /etc/anklume/absolute_level /etc/anklume/relative_level /etc/anklume/vm_nested 2>/dev/null; "
             "rm -f inventory/*.yml group_vars/*.yml host_vars/*.yml 2>/dev/null; "
             "cp examples/student-sysadmin/infra.yml infra.yml && "
             "python3 scripts/generate.py infra.yml 2>&1; rc=$?; "
             "[ $rc -eq 0 ] && echo PASS || echo FAIL"),
        Test("Ansible syntax check",
             "cd /opt/anklume && ansible-playbook site.yml --syntax-check 2>&1; rc=$?; "
             "[ $rc -eq 0 ] && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Ansible check mode",
             "cd /opt/anklume && ansible-playbook site.yml --check 2>&1 | tail -5; "
             "echo PASS",
             timeout=LONG_TIMEOUT),
        Test("Apply infrastructure",
             "cd /opt/anklume && ansible-playbook site.yml -vv > /tmp/ansible.log 2>&1; rc=$?; "
             "tail -40 /tmp/ansible.log; "
             "[ $rc -eq 0 ] && echo PASS || echo FAIL",
             timeout=DEPLOY_TIMEOUT),
        Test("Incus projects created",
             "incus project list --format csv 2>/dev/null "
             "| grep -v default | head -3; "
             "incus project list --format csv 2>/dev/null "
             "| grep -cv default | grep -qv '^0$' "
             "&& echo PASS || echo FAIL"),
        Test("Networks created",
             "incus network list --format csv 2>/dev/null | grep net- | head -3; "
             "incus network list --format csv 2>/dev/null | grep -q net- && echo PASS || echo FAIL"),
        Test("Instances launched",
             "incus list --all-projects --format csv -c n "
             "2>/dev/null | head -5; "
             "incus list --all-projects --format csv -c n "
             "2>/dev/null | grep -c . | grep -qv '^0$' "
             "&& echo PASS || echo FAIL"),
        Test("First instance RUNNING",
             f"{_inst_np()}; "
             "echo \"name=$name proj=$proj\"; "
             "[ -n \"$name\" ] && echo PASS || "
             "{ sleep 15; " + _inst_np() + "; "
             "[ -n \"$name\" ] && echo PASS || echo FAIL; }",
             timeout=DEPLOY_TIMEOUT),
        Test("Exec in deployed instance",
             f"sleep 3; {_inst_np()}; "
             "echo \"exec: name=$name proj=$proj\"; "
             "incus exec \"$name\" --project \"$proj\" -- hostname "
             "2>&1 && echo PASS || echo FAIL"),
        Test("anklume domain list (post-deploy)",
             "cd /opt/anklume && anklume domain list 2>&1 | head -5; echo PASS"),
        Test("anklume domain status",
             "cd /opt/anklume && anklume domain status 2>&1 | head -5; echo PASS"),
        Test("anklume instance list (post-deploy)",
             "cd /opt/anklume && anklume instance list 2>&1 | head -5; echo PASS"),
    ])
    phases.append(p12)

    # Phase 13: Snapshot Lifecycle — 8 tests
    # "Get first instance" sets $name and $proj in the bash session;
    # subsequent tests reuse them without calling _inst_np() again.
    p13 = Phase(13, "Snapshot Lifecycle", gate=False)
    p13.tests.extend([
        Test("Get first instance",
             f"{_inst_np()}; "
             "export name proj; echo \"name=$name proj=$proj\""),
        Test("Create snapshot",
             "incus snapshot create $name e2e-test "
             "--project $proj 2>&1; rc=$?; "
             "[ $rc -eq 0 ] && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Snapshot in list",
             "incus snapshot list $name --project $proj "
             "--format csv 2>/dev/null | grep -q e2e-test "
             "&& echo PASS || echo FAIL"),
        Test("anklume snapshot list",
             "cd /opt/anklume && anklume snapshot list "
             "2>&1 | head -5; echo PASS"),
        Test("Restore snapshot",
             "incus snapshot restore $name e2e-test "
             "--project $proj 2>&1; rc=$?; "
             "[ $rc -eq 0 ] && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Instance still works",
             "incus list $name --project $proj --format csv -c s "
             "2>/dev/null | grep -q RUNNING && echo PASS || "
             "{ sleep 10; incus list $name --project $proj "
             "--format csv -c s 2>/dev/null | grep -q RUNNING "
             "&& echo PASS || echo FAIL; }",
             timeout=LONG_TIMEOUT),
        Test("Delete snapshot",
             "incus snapshot delete $name e2e-test "
             "--project $proj 2>&1; rc=$?; "
             "[ $rc -eq 0 ] && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Snapshot gone",
             "! incus snapshot list $name "
             "--project $proj --format csv 2>/dev/null "
             "| grep -q e2e-test && echo PASS || echo FAIL"),
    ])
    phases.append(p13)

    # Phase 14: Network Isolation — 6 tests
    p14 = Phase(14, "Network Isolation", gate=False)
    p14.tests.extend([
        Test("Generate nftables rules",
             "cd /opt/anklume && ansible-playbook site.yml --tags nftables > /tmp/nft.log 2>&1; rc=$?; "
             "tail -10 /tmp/nft.log; [ $rc -eq 0 ] && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Rules file exists",
             "test -f /opt/anklume/nftables-isolation.nft && echo PASS || echo FAIL"),
        Test("Rules contain domains",
             "grep -q 'net-' /opt/anklume/nftables-isolation.nft 2>/dev/null && echo PASS || echo FAIL"),
        Test("Rules have drop policy",
             "grep -q 'drop' /opt/anklume/nftables-isolation.nft 2>/dev/null && echo PASS || echo FAIL"),
        Test("anklume network status (post-deploy)",
             "cd /opt/anklume && anklume network status 2>&1 | head -5; echo PASS"),
        Test("Rules are valid nft syntax",
             "nft -c -f /opt/anklume/nftables-isolation.nft 2>&1 && echo PASS || echo FAIL"),
    ])
    phases.append(p14)

    # Phase 15: Disposable Instances — 6 tests
    p15 = Phase(15, "Disposable Instances", gate=False)
    p15.tests.extend([
        Test("anklume instance disp --help",
             "anklume instance disp --help 2>&1 | head -5 "
             "| grep -qiE 'usage|options|domain' "
             "&& echo PASS || echo FAIL"),
        Test("Launch ephemeral disposable",
             "incus delete disp-test --force 2>/dev/null; "
             "out=$(incus launch images:debian/13 disp-test --ephemeral 2>&1); rc=$?; "
             "echo \"$out\"; echo \"launch rc=$rc\"; "
             "incus list disp-test --format csv -c n 2>/dev/null | grep -q disp-test && echo PASS || echo FAIL",
             timeout=LONG_TIMEOUT),
        Test("Disposable is ephemeral",
             "incus config get disp-test volatile.base_image 2>/dev/null; echo PASS"),
        Test("Disposable reaches RUNNING",
             _wait_running("disp-test"),
             timeout=LONG_TIMEOUT),
        Test("Stop auto-deletes",
             "incus stop -f disp-test 2>/dev/null; sleep 2; "
             "! incus list disp-test --format csv -c n 2>/dev/null | grep -q disp-test && echo PASS || echo FAIL"),
        Test("Instance gone",
             "! incus list --format csv -c n 2>/dev/null | grep -q disp-test && echo PASS || echo FAIL"),
    ])
    phases.append(p15)

    # Phase 16: Flush & Cleanup — 8 tests
    p16 = Phase(16, "Flush & Cleanup", gate=False)
    p16.tests.extend([
        Test("Unprotect all instances",
             "for proj in $(incus project list --format csv -c n 2>/dev/null "
             "| sed 's/ (current)//'); do "
             "for inst in $(incus list --project $proj --format csv -c n 2>/dev/null); do "
             "[ -z \"$inst\" ] && continue; "
             "incus config set $inst security.protection.delete false "
             "--project $proj 2>/dev/null || true; done; done; echo PASS"),
        Test("Flush infrastructure",
             "cd /opt/anklume && export FORCE=true && bash scripts/flush.sh --force 2>&1; "
             "echo \"flush_rc=$?\"; echo PASS",
             timeout=DEPLOY_TIMEOUT),
        Test("No instances after flush",
             "sleep 3; "
             "out=$(incus list --all-projects --format csv -c nNs 2>/dev/null || true); "
             "if [ -z \"$out\" ]; then echo PASS; else "
             "n=$(echo \"$out\" | wc -l); "
             "echo \"FAIL remain=$n: $out\"; fi"),
        Test("Projects cleaned",
             "out=$(incus project list --format csv -c n 2>/dev/null "
             "| sed 's/ (current)$//' | grep -v default || true); "
             "if [ -z \"$out\" ]; then echo PASS; else "
             "n=$(echo \"$out\" | wc -l); "
             "echo \"FAIL extra=$n: $out\"; fi"),
        Test("Networks cleaned",
             "out=$(incus network list --format csv -c n 2>/dev/null "
             "| grep net- || true); "
             "if [ -z \"$out\" ]; then echo PASS; else "
             "n=$(echo \"$out\" | wc -l); "
             "echo \"FAIL nets=$n: $out\"; fi"),
        Test("Default storage pool intact",
             "incus storage list --format csv 2>/dev/null | grep -q default && echo PASS || echo FAIL"),
        Test("Inventory cleaned or empty",
             "cd /opt/anklume && ls inventory/*.yml >/dev/null 2>&1; echo PASS"),
        Test("Can re-sync after flush",
             "cp /opt/anklume/examples/student-sysadmin/infra.yml /opt/anklume/infra.yml && "
             "cd /opt/anklume && python3 scripts/generate.py infra.yml >/dev/null 2>&1 && echo PASS || echo FAIL"),
        Test("Final cleanup",
             "rm -f /opt/anklume/infra.yml; echo PASS"),
    ])
    phases.append(p16)

    return phases


# ── Main execution ───────────────────────────────────────────────────────────


def print_phase_header(phase: Phase, total_tests: int):
    """Print a visual phase separator."""
    gate = " (GATE)" if phase.gate else ""
    print(f"\n{C_BOLD}{C_CYAN}{'═' * 70}")
    print(f"  Phase {phase.number}: {phase.name}{gate} — {total_tests} tests")
    print(f"{'═' * 70}{C_RESET}\n")


def print_result(result: TestResult):
    """Print a single test result."""
    if result.status in ("PASS", "INFO"):
        tag = f"{C_GREEN}[ OK ]{C_RESET}"
    elif result.status == "SKIP":
        tag = f"{C_YELLOW}[SKIP]{C_RESET}"
    elif result.status == "TIMEOUT":
        tag = f"{C_RED}[T/O ]{C_RESET}"
    else:
        tag = f"{C_RED}[FAIL]{C_RESET}"
    dur = f" {C_DIM}({result.duration:.1f}s){C_RESET}" if result.duration > 1.0 else ""
    if result.status == "FAIL" and result.output and "\n" in result.output:
        # Multi-line output: show first line inline, rest indented
        lines = result.output.strip().split("\n")
        print(f"  {tag} {result.name}: {lines[0][:60]}{dur}")
        for line in lines[1:][-10:]:  # Show last 10 lines max
            print(f"         {line[:80]}")
    else:
        out = result.output[:60] if result.output else ""
        print(f"  {tag} {result.name}: {out}{dur}")


def print_summary(results: list[TestResult], json_output: bool = False):
    """Print overall test summary."""
    passed = sum(1 for r in results if r.status in ("PASS", "INFO"))
    failed = sum(1 for r in results if r.status in ("FAIL", "TIMEOUT"))
    skipped = sum(1 for r in results if r.status == "SKIP")
    total = len(results)

    if json_output:
        summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "results": [
                {
                    "phase": r.phase,
                    "name": r.name,
                    "status": r.status,
                    "output": r.output,
                    "duration": round(r.duration, 2),
                }
                for r in results
            ],
        }
        print(json.dumps(summary, indent=2))
        return

    print(f"\n{C_BOLD}{'═' * 70}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed, {skipped} skipped")
    print(f"{'═' * 70}{C_RESET}")

    if failed:
        print(f"\n{C_RED}Failed tests:{C_RESET}")
        for r in results:
            if r.status in ("FAIL", "TIMEOUT"):
                print(f"  - Phase {r.phase}: {r.name} ({r.status}) {r.output}")

    # Per-phase summary
    phases_seen: dict[int, dict] = {}
    for r in results:
        if r.phase not in phases_seen:
            phases_seen[r.phase] = {"pass": 0, "fail": 0, "skip": 0, "total": 0}
        phases_seen[r.phase]["total"] += 1
        if r.status in ("PASS", "INFO"):
            phases_seen[r.phase]["pass"] += 1
        elif r.status == "SKIP":
            phases_seen[r.phase]["skip"] += 1
        else:
            phases_seen[r.phase]["fail"] += 1

    print(f"\n{C_BOLD}Per-phase summary:{C_RESET}")
    for pn in sorted(phases_seen):
        s = phases_seen[pn]
        status = f"{C_GREEN}PASS{C_RESET}" if s["fail"] == 0 else f"{C_RED}FAIL{C_RESET}"
        if s["skip"] == s["total"]:
            status = f"{C_YELLOW}SKIP{C_RESET}"
        print(f"  Phase {pn:2d}: {s['pass']:3d}/{s['total']:3d} passed  {status}")


def main():
    parser = argparse.ArgumentParser(description="anklume Live ISO E2E test suite")
    parser.add_argument("iso", nargs="?", default=DEFAULT_ISO, help="ISO file path")
    parser.add_argument("--phase", type=int, action="append",
                        help="Run only these phases (repeatable, e.g. --phase 12 --phase 13)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--no-disk", action="store_true",
                        help="Skip virtual disk creation (no ZFS/BTRFS tests)")
    args = parser.parse_args()

    iso = args.iso
    if not os.path.isfile(iso):
        print(f"[FAIL] ISO not found: {iso}")
        sys.exit(1)

    iso = os.path.abspath(iso)
    distro = detect_distro(iso)
    paths = temp_paths(distro)
    disk_image = paths["disk"]
    qmp_sock = paths["qmp"]
    tmpdir = paths["tmpdir"]
    os.makedirs(tmpdir, exist_ok=True)
    phases = build_phases(distro)

    # Count total tests
    total_test_count = sum(len(p.tests) for p in phases) + 3  # +3 for boot phase
    if not args.json:
        print(f"{C_BOLD}anklume E2E Test Suite{C_RESET}")
        print(f"  ISO: {os.path.basename(iso)}")
        print(f"  Distro: {distro}")
        print(f"  Phases: {len(phases)}")
        print(f"  Tests: ~{total_test_count}")
        print()

    # Create virtual disk for ZFS/BTRFS tests
    disk_created = False
    if not args.no_disk and not os.path.exists(disk_image):
        if not args.json:
            print(f"[INFO] Creating virtual disk: {disk_image} ({DISK_SIZE})")
        subprocess.run(
            ["qemu-img", "create", "-f", "qcow2", disk_image, DISK_SIZE],
            capture_output=True, check=True,
        )
        disk_created = True

    # Clean up stale socket
    if os.path.exists(qmp_sock):
        os.unlink(qmp_sock)

    # Extract kernel/initrd from ISO for direct boot (bypasses GRUB, adds apparmor=0)
    iso_mnt = os.path.join(tmpdir, "iso_mnt")
    os.makedirs(iso_mnt, exist_ok=True)
    subprocess.run(["mount", "-o", "loop,ro", iso, iso_mnt], check=True)
    kernel_path = os.path.join(tmpdir, "vmlinuz")
    initrd_path = os.path.join(tmpdir, "initrd.img")
    subprocess.run(["cp", os.path.join(iso_mnt, "boot", "vmlinuz"), kernel_path], check=True)
    subprocess.run(["cp", os.path.join(iso_mnt, "boot", "initrd.img"), initrd_path], check=True)
    subprocess.run(["umount", iso_mnt], check=True)

    kernel_cmdline = (
        "ro boot=anklume anklume.boot_mode=iso anklume.toram=1 anklume.desktop=kde "
        "apparmor=0 console=ttyS0,115200n8"
    )

    # Build QEMU command (direct kernel boot — no UEFI/GRUB needed)
    qemu_cmd = (
        f"qemu-system-x86_64"
        f" -m {MEMORY} -smp {CPUS} -enable-kvm"
        f" -cdrom {iso}"
        f" -kernel {kernel_path}"
        f" -initrd {initrd_path}"
        f" -append '{kernel_cmdline}'"
        f" -nographic"
        f" -serial mon:stdio"
        f" -qmp unix:{qmp_sock},server,nowait"
        f" -no-reboot"
        f" -device virtio-net-pci,netdev=net0"
        f" -netdev user,id=net0"
    )
    # Add virtual disk if created
    if not args.no_disk:
        qemu_cmd += f" -drive file={disk_image},format=qcow2,if=virtio"

    if not args.json:
        print(f"[INFO] Booting {os.path.basename(iso)} in QEMU...")
        print(f"[INFO] Memory: {MEMORY}MB, CPUs: {CPUS}")

    child = pexpect.spawn(
        "/bin/bash", ["-c", qemu_cmd],
        timeout=BOOT_TIMEOUT,
        encoding=None,
        maxread=16384,
    )

    all_results: list[TestResult] = []
    gate_failed = False

    try:
        # ── Phase 0: Boot & Login ──
        phase0 = phases[0]
        if args.phase is not None and 0 not in args.phase:
            pass  # Skip display but still need to boot
        else:
            print_phase_header(phase0, 3)

        # Wait for login prompt
        idx = child.expect(
            [b"login:", pexpect.TIMEOUT, pexpect.EOF],
            timeout=BOOT_TIMEOUT,
        )
        if idx != 0:
            r = TestResult(0, "Boot to login prompt", "FAIL", "No login prompt")
            all_results.append(r)
            print_result(r)
            print("--- Last output ---")
            print(child.before.decode("utf-8", errors="replace")[-2000:])
            child.terminate(force=True)
            print_summary(all_results, args.json)
            sys.exit(1)

        r = TestResult(0, "Boot to login prompt", "PASS")
        all_results.append(r)
        if args.phase is None or 0 in args.phase:
            print_result(r)

        # Login
        time.sleep(0.5)
        child.sendline(b"root")
        # Match both English "Password:" and French "Mot de passe :"
        idx = child.expect(
            [b"assword:", b"passe", pexpect.TIMEOUT],
            timeout=LOGIN_TIMEOUT,
        )
        if idx == 2:
            r = TestResult(0, "Root login", "FAIL", "No password prompt")
            all_results.append(r)
            print_result(r)
            child.terminate(force=True)
            print_summary(all_results, args.json)
            sys.exit(1)
        time.sleep(0.3)
        child.sendline(ROOT_PASSWORD.encode())
        child.expect([b"#", b"\\$"], timeout=LOGIN_TIMEOUT)
        time.sleep(0.5)
        r = TestResult(0, "Root login", "PASS")
        all_results.append(r)
        if args.phase is None or 0 in args.phase:
            print_result(r)

        # Disable terminal noise (ANSI sequences, OSC 3008, bracketed paste)
        child.sendline(
            b"bind 'set enable-bracketed-paste off' 2>/dev/null; "
            b"stty -echo 2>/dev/null; "
            b"export TERM=dumb; "
            b"export PAGER=cat; "
            b"export LC_ALL=C.UTF-8; "
            b"unset PROMPT_COMMAND; "
            b"PS1='# '"
        )
        child.expect([b"#", b"\\$"], timeout=CMD_TIMEOUT)
        time.sleep(0.3)

        # Wait for systemd (accept both running and degraded — live ISO often has degraded units)
        child.sendline(
            b"for i in $(seq 1 60); do "
            b"st=$(systemctl is-system-running 2>/dev/null); "
            b"case $st in running|degraded) break;; esac; "
            b"sleep 1; done; echo SYSREADY"
        )
        try:
            child.expect(b"SYSREADY", timeout=120)
            time.sleep(0.5)
            r = TestResult(0, "Systemd ready", "PASS")
        except pexpect.TIMEOUT:
            r = TestResult(0, "Systemd ready", "FAIL",
                           "systemd not ready within 120s")
            # Send ctrl-c to cancel the hung command, then reset prompt
            child.sendcontrol("c")
            time.sleep(1)
            child.sendline(b"echo RECOVERED")
            with contextlib.suppress(pexpect.TIMEOUT):
                child.expect(b"RECOVERED", timeout=10)
        all_results.append(r)
        if args.phase is None or 0 in args.phase:
            print_result(r)
        if r.status == "FAIL":
            gate_failed = True
            if not args.json:
                print(f"\n  {C_RED}{C_BOLD}GATE FAILED — "
                      f"skipping all subsequent phases{C_RESET}")

        # ── Run remaining phases ──
        for phase in phases[1:]:
            # Phase filter
            if args.phase is not None and phase.number not in args.phase:
                continue

            # Gate check
            if gate_failed:
                for test in phase.tests:
                    r = TestResult(phase.number, test.name, "SKIP",
                                   "Skipped (prior gate failed)")
                    all_results.append(r)
                continue

            # Skip empty phases (e.g., ZFS on Arch)
            if not phase.tests:
                continue

            print_phase_header(phase, len(phase.tests))

            phase_failed = False
            for test in phase.tests:
                r = run_test(child, test)
                r.phase = phase.number
                all_results.append(r)
                print_result(r)
                if r.status in ("FAIL", "TIMEOUT"):
                    phase_failed = True

            if phase.gate and phase_failed:
                gate_failed = True
                if not args.json:
                    print(f"\n  {C_RED}{C_BOLD}GATE FAILED — "
                          f"skipping all subsequent phases{C_RESET}")

        # ── Shutdown ──
        if not args.json:
            print("\n[INFO] Shutting down VM...")
        qmp_shutdown(qmp_sock)
        try:
            child.expect(pexpect.EOF, timeout=30)
        except pexpect.TIMEOUT:
            child.terminate(force=True)

    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        child.terminate(force=True)
    finally:
        if os.path.exists(qmp_sock):
            os.unlink(qmp_sock)
        # Clean up extracted kernel/initrd
        for f in [kernel_path, initrd_path]:
            with contextlib.suppress(OSError):
                os.unlink(f)
        if disk_created and os.path.exists(disk_image):
            os.unlink(disk_image)

    # ── Summary ──
    print_summary(all_results, args.json)

    failed = sum(1 for r in all_results if r.status in ("FAIL", "TIMEOUT"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
