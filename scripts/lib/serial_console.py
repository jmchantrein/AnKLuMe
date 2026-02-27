"""Serial console helper for QEMU guest interaction via pexpect.

Extracted from scripts/live-os-test-graphical.py. Provides login,
command execution, and systemd readiness detection over serial.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pexpect


class SerialConsole:
    """Wraps a pexpect child connected to QEMU serial console."""

    def __init__(
        self,
        child: pexpect.spawn,
        root_password: str = "anklume",
        cmd_timeout: int = 15,
    ) -> None:
        self.child = child
        self.root_password = root_password
        self.cmd_timeout = cmd_timeout
        self._cmd_seq = 0

    def wait_for_login(self, timeout: int = 300) -> bool:
        """Wait for 'login:' prompt. Returns True on success."""
        import pexpect as _pexpect

        idx = self.child.expect(
            [b"login:", _pexpect.TIMEOUT, _pexpect.EOF],
            timeout=timeout,
        )
        return idx == 0

    def login(self, user: str = "root", timeout: int = 30) -> None:
        """Log in via serial console."""
        import time

        time.sleep(0.5)
        self.child.sendline(user.encode())
        self.child.expect(b"assword:", timeout=timeout)
        time.sleep(0.3)
        self.child.sendline(self.root_password.encode())
        self.child.expect([b"#", b"\\$"], timeout=timeout)
        time.sleep(0.5)

    def setup_clean_output(self) -> None:
        """Disable bracketed paste, echo, and set TERM=dumb for clean output."""
        import time

        self.child.sendline(
            b"bind 'set enable-bracketed-paste off' 2>/dev/null; "
            b"stty -echo 2>/dev/null; export TERM=dumb"
        )
        self.child.expect([b"#", b"\\$"], timeout=self.cmd_timeout)
        time.sleep(0.3)

    def wait_for_systemd(self, timeout: int = 60) -> None:
        """Wait for systemd to reach a stable state."""
        import time

        self.child.sendline(
            b"systemctl is-system-running --wait 2>/dev/null; sleep 1; echo READY"
        )
        self.child.expect(b"READY", timeout=timeout)
        time.sleep(0.5)

    def run_cmd(self, cmd: str) -> str:
        """Send command, wait for unique ENDMARK, return cleaned output."""
        self._cmd_seq += 1
        marker = f"ENDMARK{self._cmd_seq:04d}"
        full_cmd = f"{cmd}; echo {marker}"
        self.child.sendline(full_cmd)
        self.child.expect(marker.encode(), timeout=self.cmd_timeout)
        raw = self.child.before.decode("utf-8", errors="replace")
        lines = raw.split("\n")
        # Strip the echoed command
        if lines and cmd[:20] in lines[0]:
            lines = lines[1:]
        lines = [
            line for line in lines
            if marker not in line
            and not line.strip().startswith("root@")
            and line.strip()
        ]
        return "\n".join(lines).strip()

    def run_check(self, cmd: str) -> bool:
        """Run a command that prints PASS/FAIL, return True if PASS."""
        output = self.run_cmd(cmd)
        return "PASS" in output
