#!/usr/bin/env python3
"""QEMU headless screenshot and keyboard control via QMP.

Boot an ISO in QEMU, take screenshots of the GRUB menu, navigate
entries, and capture results. Uses QMP (QEMU Machine Protocol) over
a Unix socket — no GUI, no VNC, no extra dependencies.

Usage:
    python3 scripts/qemu-screenshot.py <ISO_PATH> [--output-dir DIR]
    python3 scripts/qemu-screenshot.py images/anklume-arch.iso
    python3 scripts/qemu-screenshot.py images/anklume-debian.iso --output-dir /tmp/grub-test
"""

import json
import os
import socket
import subprocess
import sys
import time

# ── Configuration ──
QMP_SOCK = "/tmp/anklume-qmp-screenshot.sock"
MEMORY = "2048"
CPUS = "2"
GRUB_WAIT = 8  # seconds to wait for GRUB menu to appear


class QMPClient:
    """Minimal QMP client over Unix socket."""

    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.sock = None

    def connect(self):
        """Connect to QMP socket and negotiate capabilities."""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(self.sock_path)
        # Read greeting
        self._recv()
        # Negotiate capabilities
        self._send({"execute": "qmp_capabilities"})
        resp = self._recv()
        if "return" not in resp:
            raise RuntimeError(f"QMP capabilities failed: {resp}")

    def _send(self, cmd):
        """Send a QMP command."""
        data = json.dumps(cmd).encode() + b"\n"
        self.sock.sendall(data)

    def _recv(self):
        """Receive a QMP response (may include events before the actual response)."""
        buf = b""
        while True:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            # Try to parse complete JSON objects
            for line in buf.split(b"\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # Skip QMP events, return actual responses
                    if "return" in obj or "error" in obj or "QMP" in obj:
                        return obj
                except json.JSONDecodeError:
                    continue
            # If we got data but no valid JSON yet, keep reading
            if len(buf) > 65536:
                break
        return json.loads(buf.strip().split(b"\n")[-1])

    def screendump(self, filename):
        """Take a screenshot (PPM format)."""
        self._send({
            "execute": "screendump",
            "arguments": {"filename": filename}
        })
        return self._recv()

    def send_key(self, qcode, hold_time=100):
        """Send a single key press."""
        self._send({
            "execute": "send-key",
            "arguments": {
                "keys": [{"type": "qcode", "data": qcode}],
                "hold-time": hold_time
            }
        })
        return self._recv()

    def powerdown(self):
        """Gracefully shut down the VM."""
        self._send({"execute": "system_powerdown"})
        try:
            return self._recv()
        except Exception:
            pass

    def quit(self):
        """Force quit QEMU."""
        self._send({"execute": "quit"})
        try:
            return self._recv()
        except Exception:
            pass

    def close(self):
        """Close the socket."""
        if self.sock:
            self.sock.close()


def ppm_to_png(ppm_path, png_path):
    """Convert PPM to PNG using ImageMagick."""
    subprocess.run(
        ["convert", ppm_path, png_path],
        check=True, capture_output=True,
    )
    os.unlink(ppm_path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="QEMU GRUB screenshot tool")
    parser.add_argument("iso", help="Path to ISO file")
    parser.add_argument("--output-dir", default="/tmp/anklume-grub-screenshots",
                        help="Output directory for screenshots")
    parser.add_argument("--grub-wait", type=int, default=GRUB_WAIT,
                        help="Seconds to wait for GRUB (default: 8)")
    args = parser.parse_args()

    iso = os.path.abspath(args.iso)
    if not os.path.isfile(iso):
        print(f"[FAIL] ISO not found: {iso}")
        sys.exit(1)

    iso_name = os.path.basename(iso).replace(".iso", "")
    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    # Clean up stale socket
    if os.path.exists(QMP_SOCK):
        os.unlink(QMP_SOCK)

    # OVMF firmware
    ovmf_code = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
    ovmf_vars_src = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"
    ovmf_vars = "/tmp/anklume-screenshot-ovmf-vars.fd"

    if not os.path.isfile(ovmf_code):
        print(f"[FAIL] OVMF not found: {ovmf_code}")
        sys.exit(1)
    subprocess.run(["cp", ovmf_vars_src, ovmf_vars], check=True)

    # Launch QEMU headlessly
    qemu_cmd = [
        "qemu-system-x86_64",
        "-m", MEMORY, "-smp", CPUS, "-enable-kvm",
        "-drive", f"if=pflash,format=raw,readonly=on,file={ovmf_code}",
        "-drive", f"if=pflash,format=raw,file={ovmf_vars}",
        "-cdrom", iso,
        "-boot", "d",
        "-display", "none",
        "-vga", "std",
        "-qmp", f"unix:{QMP_SOCK},server,nowait",
        "-no-reboot",
    ]

    print(f"[INFO] Booting {os.path.basename(iso)} in QEMU (headless)...")
    proc = subprocess.Popen(qemu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for QMP socket
    for _ in range(30):
        if os.path.exists(QMP_SOCK):
            break
        time.sleep(0.5)
    else:
        print("[FAIL] QMP socket not created")
        proc.kill()
        sys.exit(1)

    qmp = QMPClient(QMP_SOCK)
    screenshots = []

    try:
        qmp.connect()
        print("[INFO] QMP connected")

        # Wait for GRUB menu to appear, then immediately send a key to stop
        # the countdown timer (GRUB timeout=5s, we need to interrupt it)
        print(f"[INFO] Waiting {args.grub_wait}s for GRUB, sending keys to stop countdown...")
        time.sleep(2)
        # Send arrow down then up to stop countdown without changing selection
        for t in range(args.grub_wait - 2):
            try:
                qmp.send_key("down")
                time.sleep(0.3)
                qmp.send_key("up")
                time.sleep(0.7)
            except Exception:
                time.sleep(1)
        time.sleep(1)

        # Screenshot 1: Initial GRUB menu (default selection)
        ppm = f"/tmp/{iso_name}-grub-initial.ppm"
        png = os.path.join(out_dir, f"{iso_name}-grub-initial.png")
        qmp.screendump(ppm)
        time.sleep(0.5)
        ppm_to_png(ppm, png)
        screenshots.append(png)
        print(f"[ OK ] Screenshot: {png}")

        # Navigate down through each entry and screenshot
        for i in range(1, 8):
            qmp.send_key("down")
            time.sleep(0.5)

            ppm = f"/tmp/{iso_name}-grub-entry{i}.ppm"
            png = os.path.join(out_dir, f"{iso_name}-grub-entry{i}.png")
            qmp.screendump(ppm)
            time.sleep(0.3)
            ppm_to_png(ppm, png)
            screenshots.append(png)
            print(f"[ OK ] Screenshot (entry {i}): {png}")

        # Try entering submenu (press Enter on it, then screenshot)
        # First go back up to find the submenu entry
        # The submenu should be entry index 4 (0-indexed) = 5th item
        # Let's navigate to it: we're at entry 7, go back up
        for _ in range(7):
            qmp.send_key("up")
            time.sleep(0.3)

        # Go down to entry 4 (submenu)
        for _ in range(4):
            qmp.send_key("down")
            time.sleep(0.3)

        ppm = f"/tmp/{iso_name}-grub-submenu-selected.ppm"
        png = os.path.join(out_dir, f"{iso_name}-grub-submenu-selected.png")
        qmp.screendump(ppm)
        time.sleep(0.3)
        ppm_to_png(ppm, png)
        screenshots.append(png)
        print(f"[ OK ] Screenshot (submenu selected): {png}")

        # Enter the submenu
        qmp.send_key("ret")
        time.sleep(1)

        ppm = f"/tmp/{iso_name}-grub-submenu-inside.ppm"
        png = os.path.join(out_dir, f"{iso_name}-grub-submenu-inside.png")
        qmp.screendump(ppm)
        time.sleep(0.3)
        ppm_to_png(ppm, png)
        screenshots.append(png)
        print(f"[ OK ] Screenshot (inside submenu): {png}")

        # Navigate submenu entries
        for i in range(1, 4):
            qmp.send_key("down")
            time.sleep(0.5)
            ppm = f"/tmp/{iso_name}-grub-submenu-entry{i}.ppm"
            png = os.path.join(out_dir, f"{iso_name}-grub-submenu-entry{i}.png")
            qmp.screendump(ppm)
            time.sleep(0.3)
            ppm_to_png(ppm, png)
            screenshots.append(png)
            print(f"[ OK ] Screenshot (submenu entry {i}): {png}")

        print(f"\n[INFO] All screenshots saved to {out_dir}/")
        print(f"[INFO] Total: {len(screenshots)} screenshots")

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Shutdown
        print("[INFO] Shutting down QEMU...")
        try:
            qmp.quit()
        except Exception:
            pass
        qmp.close()
        time.sleep(1)
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        # Cleanup
        if os.path.exists(QMP_SOCK):
            os.unlink(QMP_SOCK)
        if os.path.exists(ovmf_vars):
            os.unlink(ovmf_vars)

    print("\n[DONE] Screenshots:")
    for s in screenshots:
        print(f"  {s}")


if __name__ == "__main__":
    main()
