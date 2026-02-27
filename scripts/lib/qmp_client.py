"""QMP (QEMU Machine Protocol) client for headless VM control.

Provides screenshot capture, keyboard input, and VM lifecycle management
over a Unix socket. Refactored from scripts/qemu-screenshot.py.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
from typing import Any


class QMPError(Exception):
    """QMP protocol or communication error."""


class QMPClient:
    """Minimal QMP client over Unix socket with context manager support."""

    def __init__(self, sock_path: str, timeout: float = 10) -> None:
        self.sock_path = sock_path
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def __enter__(self) -> QMPClient:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self) -> None:
        """Connect to QMP socket and negotiate capabilities."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        try:
            self._sock.connect(self.sock_path)
        except (OSError, ConnectionRefusedError) as e:
            msg = f"Cannot connect to QMP socket {self.sock_path}: {e}"
            raise QMPError(msg) from e
        self._recv()  # greeting
        self._send({"execute": "qmp_capabilities"})
        resp = self._recv()
        if "return" not in resp:
            msg = f"QMP capabilities negotiation failed: {resp}"
            raise QMPError(msg)

    def _send(self, cmd: dict[str, Any]) -> None:
        """Send a QMP command."""
        if not self._sock:
            msg = "Not connected"
            raise QMPError(msg)
        data = json.dumps(cmd).encode() + b"\n"
        self._sock.sendall(data)

    def _recv(self) -> dict[str, Any]:
        """Receive a QMP response, skipping events."""
        if not self._sock:
            msg = "Not connected"
            raise QMPError(msg)
        buf = b""
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            for line in buf.split(b"\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "return" in obj or "error" in obj or "QMP" in obj:
                        return obj
                except json.JSONDecodeError:
                    continue
            if len(buf) > 65536:
                break
        try:
            return json.loads(buf.strip().split(b"\n")[-1])
        except (json.JSONDecodeError, IndexError) as e:
            msg = f"Failed to parse QMP response: {buf[:200]!r}"
            raise QMPError(msg) from e

    def screendump(self, filename: str, fmt: str = "png") -> dict[str, Any]:
        """Take a screenshot. Supports 'png' and 'ppm' formats.

        For PPM format, if ImageMagick is available the file is auto-converted
        to PNG (original PPM deleted). Returns the QMP response.
        """
        if fmt == "png":
            self._send({
                "execute": "screendump",
                "arguments": {"filename": filename, "format": "png"},
            })
            return self._recv()

        # PPM mode (legacy QEMU without PNG support)
        ppm_path = filename.rsplit(".", 1)[0] + ".ppm" if filename.endswith(".png") else filename
        self._send({
            "execute": "screendump",
            "arguments": {"filename": ppm_path},
        })
        resp = self._recv()

        # Auto-convert PPM → PNG if target was .png
        if filename.endswith(".png") and ppm_path != filename and os.path.isfile(ppm_path):
            try:
                subprocess.run(
                    ["convert", ppm_path, filename],
                    check=True, capture_output=True,
                )
                os.unlink(ppm_path)
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass  # Keep PPM if ImageMagick unavailable
        return resp

    def send_key(self, qcode: str, hold_time: int = 100) -> dict[str, Any]:
        """Send a single key press."""
        self._send({
            "execute": "send-key",
            "arguments": {
                "keys": [{"type": "qcode", "data": qcode}],
                "hold-time": hold_time,
            },
        })
        return self._recv()

    def send_key_combo(self, *qcodes: str, hold_time: int = 100) -> dict[str, Any]:
        """Send a multi-key combination (e.g., ctrl+alt+del)."""
        keys = [{"type": "qcode", "data": k} for k in qcodes]
        self._send({
            "execute": "send-key",
            "arguments": {"keys": keys, "hold-time": hold_time},
        })
        return self._recv()

    def powerdown(self) -> None:
        """Gracefully shut down the VM (ACPI power button)."""
        self._send({"execute": "system_powerdown"})
        with contextlib.suppress(QMPError, OSError):
            self._recv()

    def quit(self) -> None:
        """Force quit QEMU immediately."""
        self._send({"execute": "quit"})
        with contextlib.suppress(QMPError, OSError):
            self._recv()

    def close(self) -> None:
        """Close the socket connection."""
        if self._sock:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
