"""Central VM orchestrator integrating QMP, VNC, and serial console.

Builds and manages a QEMU VM with optional VNC for mouse support.
Gracefully degrades: VNC disconnect → QMP-only, missing vncdotool → no mouse.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import time
from typing import Any

from scripts.lib.qmp_client import QMPClient, QMPError
from scripts.lib.serial_console import SerialConsole

log = logging.getLogger(__name__)

# Default OVMF paths (Arch/Debian)
_OVMF_PATHS = [
    "/usr/share/edk2/x64/OVMF_CODE.4m.fd",
    "/usr/share/OVMF/OVMF_CODE.fd",
    "/usr/share/edk2-ovmf/x64/OVMF_CODE.fd",
]
_OVMF_VARS_PATHS = [
    "/usr/share/edk2/x64/OVMF_VARS.4m.fd",
    "/usr/share/OVMF/OVMF_VARS.fd",
    "/usr/share/edk2-ovmf/x64/OVMF_VARS.fd",
]


class VNCNotAvailableError(Exception):
    """Raised when a mouse operation is requested but VNC is not connected."""


class VMController:
    """Context-managed QEMU VM with QMP + optional VNC + serial."""

    def __init__(
        self,
        iso_path: str,
        *,
        memory: str = "4096",
        cpus: str = "2",
        resolution: str = "1024x768",
        display: str = "none",
        vnc_enabled: bool = False,
        vnc_display: int = 50,
        qmp_sock: str = "/tmp/anklume-vm-qmp.sock",
        boot_timeout: int = 300,
        root_password: str = "anklume",
    ) -> None:
        self.iso_path = os.path.abspath(iso_path)
        self.memory = memory
        self.cpus = cpus
        self.resolution = resolution
        self.display = display
        self.vnc_enabled = vnc_enabled
        self.vnc_display = vnc_display
        self.qmp_sock = qmp_sock
        self.boot_timeout = boot_timeout
        self.root_password = root_password

        self._proc: subprocess.Popen[bytes] | None = None
        self._qmp: QMPClient | None = None
        self._vnc_client: Any = None
        self._serial: SerialConsole | None = None
        self._pexpect_child: Any = None
        self._ovmf_vars_copy: str | None = None

    def __enter__(self) -> VMController:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cleanup()

    @property
    def qmp(self) -> QMPClient:
        """Access the QMP client (always available after start)."""
        if self._qmp is None:
            msg = "VM not started"
            raise QMPError(msg)
        return self._qmp

    @property
    def serial(self) -> SerialConsole:
        """Access the serial console."""
        if self._serial is None:
            msg = "Serial console not available"
            raise RuntimeError(msg)
        return self._serial

    @property
    def vnc_connected(self) -> bool:
        """Whether VNC client is connected."""
        return self._vnc_client is not None

    def start(self) -> None:
        """Launch QEMU, connect QMP, optionally connect VNC."""
        import pexpect

        if os.path.exists(self.qmp_sock):
            os.unlink(self.qmp_sock)

        ovmf_code = self._find_firmware(_OVMF_PATHS, "OVMF_CODE")
        ovmf_vars_src = self._find_firmware(_OVMF_VARS_PATHS, "OVMF_VARS")
        self._ovmf_vars_copy = "/tmp/anklume-vm-ovmf-vars.fd"
        subprocess.run(["cp", ovmf_vars_src, self._ovmf_vars_copy], check=True)

        qemu_cmd = self._build_qemu_cmd(ovmf_code)
        log.info("Starting QEMU: %s", " ".join(qemu_cmd))

        self._pexpect_child = pexpect.spawn(
            "/bin/bash", ["-c", " ".join(qemu_cmd)],
            timeout=self.boot_timeout,
            encoding=None,
            maxread=8192,
        )
        self._serial = SerialConsole(
            self._pexpect_child,
            root_password=self.root_password,
        )

        # Wait for QMP socket
        self._wait_for_socket(self.qmp_sock, timeout=15)
        self._qmp = QMPClient(self.qmp_sock)
        self._qmp.connect()
        log.info("QMP connected")

        # Connect VNC if enabled
        if self.vnc_enabled:
            self._connect_vnc()

    def _build_qemu_cmd(self, ovmf_code: str) -> list[str]:
        """Build the QEMU command line."""
        res_w, res_h = self.resolution.split("x")
        cmd = [
            "qemu-system-x86_64",
            "-m", self.memory,
            "-smp", self.cpus,
            "-enable-kvm",
            "-drive", f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
            "-drive", f"if=pflash,format=raw,file={self._ovmf_vars_copy}",
            "-cdrom", self.iso_path,
            "-boot", "d",
            "-display", self.display,
            "-device", f"virtio-vga,xres={res_w},yres={res_h}",
            "-serial", "mon:stdio",
            "-qmp", f"unix:{self.qmp_sock},server,nowait",
            "-no-reboot",
        ]

        if self.vnc_enabled:
            cmd.extend([
                "-vnc", f"localhost:{self.vnc_display}",
                "-device", "usb-ehci",
                "-device", "usb-tablet",  # Absolute mouse positioning
            ])

        return cmd

    def _connect_vnc(self) -> None:
        """Connect vncdotool to the QEMU VNC server with backoff."""
        try:
            from vncdotool import api as vnc_api
        except ImportError:
            log.warning("vncdotool not installed — VNC mouse unavailable")
            return

        vnc_port = 5900 + self.vnc_display
        for attempt in range(10):
            try:
                self._vnc_client = vnc_api.connect(f"localhost::{vnc_port}")
                log.info("VNC connected on port %d", vnc_port)
                return
            except Exception:
                wait = 0.5 * (attempt + 1)
                log.debug("VNC connect attempt %d failed, retry in %.1fs", attempt + 1, wait)
                time.sleep(wait)

        log.warning("VNC connection failed after 10 attempts — mouse unavailable")

    def capture_screen(self, filename: str, source: str = "auto") -> str:
        """Capture a screenshot.

        Args:
            filename: Output PNG path.
            source: "vnc", "qmp", or "auto" (VNC preferred, QMP fallback).

        Returns the actual path written.
        """
        if source == "auto":
            source = "vnc" if self.vnc_connected else "qmp"

        if source == "vnc" and self.vnc_connected:
            try:
                self._vnc_client.captureScreen(filename)
                return filename
            except Exception:
                log.warning("VNC capture failed, falling back to QMP")

        self.qmp.screendump(filename)
        time.sleep(0.5)  # Let QEMU write the file
        return filename

    def mouse_click(self, x: int, y: int, button: int = 1) -> None:
        """Click at absolute coordinates via VNC."""
        if not self.vnc_connected:
            raise VNCNotAvailableError("Mouse requires VNC connection")
        self._vnc_client.mouseMove(x, y)
        time.sleep(0.1)
        self._vnc_client.mousePress(button)

    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to absolute coordinates via VNC."""
        if not self.vnc_connected:
            raise VNCNotAvailableError("Mouse requires VNC connection")
        self._vnc_client.mouseMove(x, y)

    def mouse_drag(self, x1: int, y1: int, x2: int, y2: int, button: int = 1) -> None:
        """Drag from (x1,y1) to (x2,y2) via VNC."""
        if not self.vnc_connected:
            raise VNCNotAvailableError("Mouse requires VNC connection")
        self._vnc_client.mouseMove(x1, y1)
        time.sleep(0.1)
        self._vnc_client.mouseDown(button)
        time.sleep(0.1)
        self._vnc_client.mouseMove(x2, y2)
        time.sleep(0.1)
        self._vnc_client.mouseUp(button)

    def click_proportional(self, x_pct: float, y_pct: float, button: int = 1) -> None:
        """Click at resolution-independent proportional coordinates (0.0-1.0)."""
        res_w, res_h = (int(v) for v in self.resolution.split("x"))
        x = int(x_pct * res_w)
        y = int(y_pct * res_h)
        self.mouse_click(x, y, button)

    def type_text(self, text: str) -> None:
        """Type text. Uses VNC if available, serial fallback."""
        if self.vnc_connected:
            self._vnc_client.type(text)
        else:
            for char in text:
                self.qmp.send_key(char)
                time.sleep(0.05)

    def send_keys(self, *qcodes: str) -> None:
        """Send key combination. VNC preferred, QMP fallback."""
        if len(qcodes) == 1:
            if self.vnc_connected:
                self._vnc_client.keyPress(qcodes[0])
            else:
                self.qmp.send_key(qcodes[0])
        else:
            self.qmp.send_key_combo(*qcodes)

    def shutdown(self, timeout: int = 30) -> None:
        """Graceful ACPI shutdown with timeout."""
        import pexpect

        if self._qmp:
            self._qmp.powerdown()
        if self._pexpect_child:
            try:
                self._pexpect_child.expect(pexpect.EOF, timeout=timeout)
            except pexpect.TIMEOUT:
                self._pexpect_child.terminate(force=True)

    def cleanup(self) -> None:
        """Force cleanup all resources."""
        if self._vnc_client:
            with contextlib.suppress(Exception):
                self._vnc_client.disconnect()
            self._vnc_client = None

        if self._qmp:
            with contextlib.suppress(QMPError, OSError):
                self._qmp.quit()
            self._qmp.close()
            self._qmp = None

        if self._pexpect_child:
            with contextlib.suppress(Exception):
                self._pexpect_child.terminate(force=True)
            self._pexpect_child = None

        for path in [self.qmp_sock, self._ovmf_vars_copy]:
            if path and os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.unlink(path)

    @staticmethod
    def _find_firmware(paths: list[str], name: str) -> str:
        """Find the first existing firmware file."""
        for p in paths:
            if os.path.isfile(p):
                return p
        msg = f"{name} firmware not found. Searched: {paths}"
        raise FileNotFoundError(msg)

    @staticmethod
    def _wait_for_socket(path: str, timeout: int = 15) -> None:
        """Poll for a Unix socket to appear."""
        for _ in range(timeout * 2):
            if os.path.exists(path):
                return
            time.sleep(0.5)
        msg = f"Socket {path} not created within {timeout}s"
        raise TimeoutError(msg)
