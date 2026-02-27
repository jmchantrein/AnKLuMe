"""Tests for the GUI automation stack (scripts/lib/).

Tests all 4 layers:
- Layer 0: QMPClient, SerialConsole (unit tests with mocks)
- Layer 1: VMController VNC integration (unit tests with mocks)
- Layer 2: screen_analysis (unit tests, some need Pillow)
- Layer 3: VisionAgent (unit tests with mocked HTTP)

Tests are written from the spec (plan), not from the implementation.
Optional dependencies use pytest.mark.skipif with import checks.
"""

import base64
import importlib.util
import json
import os
import shutil
import socket
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Availability checks for optional deps ──

_HAS_PILLOW = shutil.which("python3") is not None  # Pillow is always available in our env
try:
    from PIL import Image
    _HAS_PILLOW = True
except ImportError:
    _HAS_PILLOW = False

_HAS_OPENCV = importlib.util.find_spec("cv2") is not None

_HAS_TESSERACT = (
    importlib.util.find_spec("pytesseract") is not None
    and shutil.which("tesseract") is not None
)


# ═══════════════════════════════════════════════════════════════════
# Layer 0: QMPClient tests
# ═══════════════════════════════════════════════════════════════════


class TestQMPClient:
    """Unit tests for QMPClient with a mock Unix socket server."""

    def test_import(self):
        """QMPClient and QMPError are importable."""
        from scripts.lib.qmp_client import QMPClient, QMPError
        assert QMPClient is not None
        assert issubclass(QMPError, Exception)

    def test_context_manager_protocol(self):
        """QMPClient implements __enter__ and __exit__."""
        from scripts.lib.qmp_client import QMPClient
        client = QMPClient("/nonexistent")
        assert hasattr(client, "__enter__")
        assert hasattr(client, "__exit__")

    def test_connect_nonexistent_socket_raises(self):
        """Connecting to a non-existent socket raises QMPError."""
        from scripts.lib.qmp_client import QMPClient, QMPError
        client = QMPClient("/tmp/nonexistent-qmp-test.sock", timeout=1)
        with pytest.raises(QMPError, match="Cannot connect"):
            client.connect()

    def test_send_without_connect_raises(self):
        """Sending without connecting raises QMPError."""
        from scripts.lib.qmp_client import QMPClient, QMPError
        client = QMPClient("/tmp/nonexistent.sock")
        with pytest.raises(QMPError, match="Not connected"):
            client._send({"execute": "test"})

    def test_recv_without_connect_raises(self):
        """Receiving without connecting raises QMPError."""
        from scripts.lib.qmp_client import QMPClient, QMPError
        client = QMPClient("/tmp/nonexistent.sock")
        with pytest.raises(QMPError, match="Not connected"):
            client._recv()

    def test_close_without_connect_is_safe(self):
        """Closing without connecting does not raise."""
        from scripts.lib.qmp_client import QMPClient
        client = QMPClient("/tmp/nonexistent.sock")
        client.close()  # Should not raise

    def test_close_sets_sock_to_none(self):
        """After close(), _sock is None."""
        from scripts.lib.qmp_client import QMPClient
        client = QMPClient("/tmp/nonexistent.sock")
        client._sock = MagicMock()
        client.close()
        assert client._sock is None

    def test_connect_and_negotiate(self, tmp_path):
        """QMPClient connects and negotiates capabilities with a mock server."""
        from scripts.lib.qmp_client import QMPClient

        sock_path = str(tmp_path / "test-qmp.sock")
        server = _MockQMPServer(sock_path)
        server.start()
        try:
            client = QMPClient(sock_path, timeout=5)
            client.connect()
            assert client._sock is not None
            client.close()
        finally:
            server.stop()

    def test_screendump_png_sends_correct_command(self, tmp_path):
        """screendump(fmt='png') sends the correct QMP command."""
        from scripts.lib.qmp_client import QMPClient

        sock_path = str(tmp_path / "test-qmp.sock")
        server = _MockQMPServer(sock_path)
        server.start()
        try:
            client = QMPClient(sock_path, timeout=5)
            client.connect()
            resp = client.screendump("/tmp/test.png", fmt="png")
            assert "return" in resp
            # Verify the server received a screendump command
            assert any("screendump" in json.dumps(cmd) for cmd in server.received_commands)
            client.close()
        finally:
            server.stop()

    def test_send_key_sends_correct_command(self, tmp_path):
        """send_key() sends qcode in the expected format."""
        from scripts.lib.qmp_client import QMPClient

        sock_path = str(tmp_path / "test-qmp.sock")
        server = _MockQMPServer(sock_path)
        server.start()
        try:
            client = QMPClient(sock_path, timeout=5)
            client.connect()
            resp = client.send_key("ret")
            assert "return" in resp
            # Find the send-key command
            key_cmds = [c for c in server.received_commands if c.get("execute") == "send-key"]
            assert len(key_cmds) == 1
            assert key_cmds[0]["arguments"]["keys"][0]["data"] == "ret"
            client.close()
        finally:
            server.stop()

    def test_send_key_combo_multiple_keys(self, tmp_path):
        """send_key_combo() sends multiple keys in one command."""
        from scripts.lib.qmp_client import QMPClient

        sock_path = str(tmp_path / "test-qmp.sock")
        server = _MockQMPServer(sock_path)
        server.start()
        try:
            client = QMPClient(sock_path, timeout=5)
            client.connect()
            client.send_key_combo("ctrl", "alt", "delete")
            key_cmds = [c for c in server.received_commands if c.get("execute") == "send-key"]
            assert len(key_cmds) == 1
            keys = key_cmds[0]["arguments"]["keys"]
            assert len(keys) == 3
            assert [k["data"] for k in keys] == ["ctrl", "alt", "delete"]
            client.close()
        finally:
            server.stop()

    def test_powerdown_does_not_raise(self, tmp_path):
        """powerdown() sends command and suppresses recv errors."""
        from scripts.lib.qmp_client import QMPClient

        sock_path = str(tmp_path / "test-qmp.sock")
        server = _MockQMPServer(sock_path)
        server.start()
        try:
            client = QMPClient(sock_path, timeout=5)
            client.connect()
            client.powerdown()  # Should not raise
            client.close()
        finally:
            server.stop()

    def test_quit_does_not_raise(self, tmp_path):
        """quit() sends command and suppresses recv errors."""
        from scripts.lib.qmp_client import QMPClient

        sock_path = str(tmp_path / "test-qmp.sock")
        server = _MockQMPServer(sock_path)
        server.start()
        try:
            client = QMPClient(sock_path, timeout=5)
            client.connect()
            client.quit()  # Should not raise
            client.close()
        finally:
            server.stop()


# ═══════════════════════════════════════════════════════════════════
# Layer 0: SerialConsole tests
# ═══════════════════════════════════════════════════════════════════


class TestSerialConsole:
    """Unit tests for SerialConsole with mock pexpect child."""

    def test_import(self):
        """SerialConsole is importable."""
        from scripts.lib.serial_console import SerialConsole
        assert SerialConsole is not None

    def test_init_defaults(self):
        """Default password and timeout are set correctly."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        console = SerialConsole(mock_child)
        assert console.root_password == "anklume"
        assert console.cmd_timeout == 15
        assert console._cmd_seq == 0

    def test_init_custom_params(self):
        """Custom password and timeout are stored."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        console = SerialConsole(mock_child, root_password="secret", cmd_timeout=30)
        assert console.root_password == "secret"
        assert console.cmd_timeout == 30

    def test_run_cmd_increments_seq(self):
        """Each run_cmd() call uses a unique ENDMARK sequence number."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        mock_child.before = b"some output\nENDMARK0001"
        console = SerialConsole(mock_child)

        console.run_cmd("echo hello")
        assert console._cmd_seq == 1

        mock_child.before = b"some output\nENDMARK0002"
        console.run_cmd("echo world")
        assert console._cmd_seq == 2

    def test_run_cmd_sends_command_with_marker(self):
        """run_cmd() appends '; echo ENDMARKNNNN' to the command."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        mock_child.before = b"output line\n"
        console = SerialConsole(mock_child)

        console.run_cmd("uname -r")
        sent = mock_child.sendline.call_args[0][0]
        assert sent == "uname -r; echo ENDMARK0001"

    def test_run_cmd_strips_echoed_command(self):
        """run_cmd() removes the echoed command line from output."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        # Simulate: echoed command, then actual output, then marker noise
        mock_child.before = b"uname -r; echo ENDMARK0001\n6.18.12-2-cachyos-lts\nroot@host:~# "
        console = SerialConsole(mock_child)

        result = console.run_cmd("uname -r")
        assert "6.18.12-2-cachyos-lts" in result
        assert "ENDMARK" not in result
        assert "root@" not in result

    def test_run_check_returns_true_for_pass(self):
        """run_check() returns True when output contains PASS."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        mock_child.before = b"PASS\n"
        console = SerialConsole(mock_child)

        assert console.run_check("echo PASS") is True

    def test_run_check_returns_false_for_fail(self):
        """run_check() returns False when output contains FAIL."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        mock_child.before = b"FAIL\n"
        console = SerialConsole(mock_child)

        assert console.run_check("echo FAIL") is False

    def test_wait_for_login_returns_true_on_login(self):
        """wait_for_login() returns True when 'login:' is matched."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        mock_child.expect.return_value = 0  # Index 0 = login: matched
        console = SerialConsole(mock_child)

        assert console.wait_for_login(timeout=5) is True

    def test_wait_for_login_returns_false_on_timeout(self):
        """wait_for_login() returns False on timeout."""
        from scripts.lib.serial_console import SerialConsole
        mock_child = MagicMock()
        mock_child.expect.return_value = 1  # Index 1 = TIMEOUT
        console = SerialConsole(mock_child)

        assert console.wait_for_login(timeout=5) is False


# ═══════════════════════════════════════════════════════════════════
# Layer 2: screen_analysis tests
# ═══════════════════════════════════════════════════════════════════


class TestScreenAnalysis:
    """Unit tests for screen analysis functions."""

    def test_import(self):
        """All public functions are importable."""
        from scripts.lib.screen_analysis import (
            MatchResult,
        )
        assert MatchResult is not None

    def test_match_result_dataclass(self):
        """MatchResult has all expected fields."""
        from scripts.lib.screen_analysis import MatchResult
        m = MatchResult(found=True, x=10, y=20, w=100, h=50, center_x=60, center_y=45, confidence=0.95)
        assert m.found is True
        assert m.center_x == 60
        assert m.confidence == 0.95

    def test_match_result_defaults(self):
        """MatchResult defaults to not found with zero coords."""
        from scripts.lib.screen_analysis import MatchResult
        m = MatchResult(found=False)
        assert m.x == 0
        assert m.confidence == 0.0

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_is_not_black_screen_with_black_image(self, tmp_path):
        """A fully black image is detected as a black screen."""
        from scripts.lib.screen_analysis import is_not_black_screen
        img = Image.new("RGB", (100, 100), (0, 0, 0))
        path = str(tmp_path / "black.png")
        img.save(path)
        assert is_not_black_screen(path) is False

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_is_not_black_screen_with_white_image(self, tmp_path):
        """A white image is detected as having content."""
        from scripts.lib.screen_analysis import is_not_black_screen
        img = Image.new("RGB", (100, 100), (255, 255, 255))
        path = str(tmp_path / "white.png")
        img.save(path)
        assert is_not_black_screen(path) is True

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_screen_has_text_content_bright(self, tmp_path):
        """An image with many bright pixels is detected as having text content."""
        from scripts.lib.screen_analysis import screen_has_text_content
        img = Image.new("RGB", (100, 100), (200, 200, 200))
        path = str(tmp_path / "bright.png")
        img.save(path)
        assert screen_has_text_content(path) is True

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_screen_has_text_content_dark(self, tmp_path):
        """An image with no bright pixels is detected as having no text."""
        from scripts.lib.screen_analysis import screen_has_text_content
        img = Image.new("RGB", (100, 100), (10, 10, 10))
        path = str(tmp_path / "dark.png")
        img.save(path)
        assert screen_has_text_content(path) is False

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_images_match_identical(self, tmp_path):
        """Two identical images match with 0% diff."""
        from scripts.lib.screen_analysis import images_match
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        path1 = str(tmp_path / "img1.png")
        path2 = str(tmp_path / "img2.png")
        img.save(path1)
        img.save(path2)
        match, diff_pct, _ = images_match(path1, path2)
        assert match is True
        assert diff_pct == 0.0

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_images_match_different(self, tmp_path):
        """Two completely different images do not match."""
        from scripts.lib.screen_analysis import images_match
        img1 = Image.new("RGB", (100, 100), (0, 0, 0))
        img2 = Image.new("RGB", (100, 100), (255, 255, 255))
        path1 = str(tmp_path / "black.png")
        path2 = str(tmp_path / "white.png")
        img1.save(path1)
        img2.save(path2)
        match, diff_pct, diff_path = images_match(path1, path2)
        assert match is False
        assert diff_pct > 50.0
        assert diff_path is not None

    def test_images_match_missing_reference(self, tmp_path):
        """Missing reference image returns (None, None, None)."""
        from scripts.lib.screen_analysis import images_match
        actual = str(tmp_path / "actual.png")
        Path(actual).write_bytes(b"fake")
        match, diff_pct, diff_path = images_match(actual, "/nonexistent/ref.png")
        assert match is None
        assert diff_pct is None

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_wait_for_stable_screen_converges(self, tmp_path):
        """wait_for_stable_screen returns a path when captures stabilize."""
        from scripts.lib.screen_analysis import wait_for_stable_screen

        # Create a capture function that always saves the same image
        img = Image.new("RGB", (100, 100), (128, 128, 128))

        def capture_fn(path):
            img.save(path)

        result = wait_for_stable_screen(
            capture_fn=capture_fn,
            temp_dir=str(tmp_path),
            interval=0.1,
            stable_count=2,
            timeout=10,
        )
        assert result is not None
        assert os.path.exists(result)

    @pytest.mark.skipif(not _HAS_OPENCV, reason="OpenCV not available")
    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_find_template_exact_match(self, tmp_path):
        """find_template finds a template that exists in the screenshot."""
        # Create a screenshot with a textured background + a distinctive pattern
        import random

        from scripts.lib.screen_analysis import find_template
        random.seed(42)
        screenshot = Image.new("RGB", (200, 200))
        for x in range(200):
            for y in range(200):
                screenshot.putpixel((x, y), (random.randint(0, 50), random.randint(0, 50), random.randint(0, 50)))
        # Paint a distinctive checkerboard at (60, 60)
        for x in range(60, 90):
            for y in range(60, 90):
                color = (255, 0, 0) if (x + y) % 2 == 0 else (0, 255, 0)
                screenshot.putpixel((x, y), color)
        screenshot_path = str(tmp_path / "screen.png")
        screenshot.save(screenshot_path)

        # Create a template = the checkerboard pattern
        template = Image.new("RGB", (30, 30))
        for x in range(30):
            for y in range(30):
                color = (255, 0, 0) if ((x + 60) + (y + 60)) % 2 == 0 else (0, 255, 0)
                template.putpixel((x, y), color)
        template_path = str(tmp_path / "template.png")
        template.save(template_path)

        result = find_template(screenshot_path, template_path, threshold=0.8)
        assert result.found is True
        assert result.confidence > 0.8
        # Center should be near (75, 75) = (60+15, 60+15)
        assert 55 <= result.center_x <= 95
        assert 55 <= result.center_y <= 95

    @pytest.mark.skipif(not _HAS_OPENCV, reason="OpenCV not available")
    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_find_template_no_match(self, tmp_path):
        """find_template returns found=False when template is absent."""
        # Noisy background
        import random

        from scripts.lib.screen_analysis import find_template
        random.seed(99)
        screenshot = Image.new("RGB", (200, 200))
        for x in range(200):
            for y in range(200):
                screenshot.putpixel((x, y), (random.randint(0, 50), random.randint(0, 50), random.randint(0, 50)))
        screenshot_path = str(tmp_path / "screen.png")
        screenshot.save(screenshot_path)

        # Very distinctive checkerboard pattern NOT in the screenshot
        template = Image.new("RGB", (30, 30))
        for x in range(30):
            for y in range(30):
                color = (255, 255, 0) if (x + y) % 2 == 0 else (0, 0, 255)
                template.putpixel((x, y), color)
        template_path = str(tmp_path / "template.png")
        template.save(template_path)

        result = find_template(screenshot_path, template_path, threshold=0.95)
        assert result.found is False

    def test_find_template_missing_file(self, tmp_path):
        """find_template returns found=False for missing files."""
        from scripts.lib.screen_analysis import find_template
        result = find_template("/nonexistent.png", "/nonexistent2.png")
        assert result.found is False

    @pytest.mark.skipif(not _HAS_TESSERACT, reason="pytesseract/tesseract not available")
    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_ocr_full_readable_text(self, tmp_path):
        """ocr_full extracts text from a clean image with text."""
        from scripts.lib.screen_analysis import ocr_full

        # Create a white image with black text (large, readable)
        img = Image.new("RGB", (400, 100), (255, 255, 255))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 36)
        except OSError:
            font = ImageFont.load_default()
        draw.text((10, 20), "ANKLUME", fill=(0, 0, 0), font=font)
        path = str(tmp_path / "text.png")
        img.save(path)

        result = ocr_full(path)
        assert "ANKLUME" in result.upper()

    @pytest.mark.skipif(not _HAS_TESSERACT, reason="pytesseract/tesseract not available")
    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_find_text_on_screen(self, tmp_path):
        """find_text_on_screen returns (True, text) when text is found."""
        from scripts.lib.screen_analysis import find_text_on_screen

        img = Image.new("RGB", (400, 100), (255, 255, 255))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 36)
        except OSError:
            font = ImageFont.load_default()
        draw.text((10, 20), "HELLO WORLD", fill=(0, 0, 0), font=font)
        path = str(tmp_path / "text.png")
        img.save(path)

        found, full_text = find_text_on_screen(path, "hello")
        assert found is True
        assert "HELLO" in full_text.upper()


# ═══════════════════════════════════════════════════════════════════
# Layer 1+0: VMController tests (mocked, no QEMU needed)
# ═══════════════════════════════════════════════════════════════════


class TestVMController:
    """Unit tests for VMController with mocked dependencies."""

    def test_import(self):
        """VMController and VNCNotAvailableError are importable."""
        from scripts.lib.vm_controller import VMController, VNCNotAvailableError
        assert VMController is not None
        assert issubclass(VNCNotAvailableError, Exception)

    def test_context_manager_protocol(self):
        """VMController implements context manager."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/nonexistent.iso")
        assert hasattr(vm, "__enter__")
        assert hasattr(vm, "__exit__")

    def test_init_stores_config(self):
        """Constructor stores all configuration parameters."""
        from scripts.lib.vm_controller import VMController
        vm = VMController(
            "/tmp/test.iso",
            memory="8192",
            cpus="4",
            resolution="1920x1080",
            vnc_enabled=True,
            vnc_display=99,
        )
        assert vm.iso_path == "/tmp/test.iso"
        assert vm.memory == "8192"
        assert vm.cpus == "4"
        assert vm.resolution == "1920x1080"
        assert vm.vnc_enabled is True
        assert vm.vnc_display == 99

    def test_vnc_not_connected_initially(self):
        """VNC is not connected before start()."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        assert vm.vnc_connected is False

    def test_mouse_click_without_vnc_raises(self):
        """Mouse operations raise VNCNotAvailableError without VNC."""
        from scripts.lib.vm_controller import VMController, VNCNotAvailableError
        vm = VMController("/tmp/test.iso")
        with pytest.raises(VNCNotAvailableError):
            vm.mouse_click(100, 100)

    def test_mouse_move_without_vnc_raises(self):
        """mouse_move raises VNCNotAvailableError without VNC."""
        from scripts.lib.vm_controller import VMController, VNCNotAvailableError
        vm = VMController("/tmp/test.iso")
        with pytest.raises(VNCNotAvailableError):
            vm.mouse_move(100, 100)

    def test_mouse_drag_without_vnc_raises(self):
        """mouse_drag raises VNCNotAvailableError without VNC."""
        from scripts.lib.vm_controller import VMController, VNCNotAvailableError
        vm = VMController("/tmp/test.iso")
        with pytest.raises(VNCNotAvailableError):
            vm.mouse_drag(0, 0, 100, 100)

    def test_click_proportional_without_vnc_raises(self):
        """click_proportional raises VNCNotAvailableError without VNC."""
        from scripts.lib.vm_controller import VMController, VNCNotAvailableError
        vm = VMController("/tmp/test.iso")
        with pytest.raises(VNCNotAvailableError):
            vm.click_proportional(0.5, 0.5)

    def test_click_proportional_calculates_coords(self):
        """click_proportional converts percentages to pixel coordinates."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso", resolution="1024x768")
        vm._vnc_client = MagicMock()

        vm.click_proportional(0.5, 0.5)

        # Should call mouseMove(512, 384) then mousePress(1)
        vm._vnc_client.mouseMove.assert_called_once_with(512, 384)
        vm._vnc_client.mousePress.assert_called_once_with(1)

    def test_build_qemu_cmd_basic(self):
        """_build_qemu_cmd produces a valid command without VNC."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso", memory="2048", cpus="2")
        vm._ovmf_vars_copy = "/tmp/test-vars.fd"
        cmd = vm._build_qemu_cmd("/usr/share/edk2/x64/OVMF_CODE.4m.fd")
        assert "qemu-system-x86_64" in cmd
        assert "-m" in cmd
        assert "2048" in cmd
        assert "-vnc" not in cmd
        assert "usb-tablet" not in cmd

    def test_build_qemu_cmd_with_vnc(self):
        """_build_qemu_cmd adds VNC and USB tablet when VNC enabled."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso", vnc_enabled=True, vnc_display=50)
        vm._ovmf_vars_copy = "/tmp/test-vars.fd"
        cmd = vm._build_qemu_cmd("/usr/share/edk2/x64/OVMF_CODE.4m.fd")
        assert "-vnc" in cmd
        assert "localhost:50" in " ".join(cmd)
        assert "usb-tablet" in " ".join(cmd)

    def test_find_firmware_found(self, tmp_path):
        """_find_firmware returns path when file exists."""
        from scripts.lib.vm_controller import VMController
        fw = tmp_path / "OVMF_CODE.fd"
        fw.write_text("fake firmware")
        result = VMController._find_firmware([str(fw)], "OVMF_CODE")
        assert result == str(fw)

    def test_find_firmware_not_found(self):
        """_find_firmware raises FileNotFoundError when no path exists."""
        from scripts.lib.vm_controller import VMController
        with pytest.raises(FileNotFoundError, match="firmware not found"):
            VMController._find_firmware(["/nonexistent/a", "/nonexistent/b"], "OVMF")

    def test_cleanup_is_safe_without_start(self):
        """cleanup() does not raise when called without start()."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        vm.cleanup()  # Should not raise

    def test_qmp_property_raises_without_start(self):
        """Accessing .qmp before start() raises QMPError."""
        from scripts.lib.qmp_client import QMPError
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        with pytest.raises(QMPError, match="VM not started"):
            _ = vm.qmp

    def test_serial_property_raises_without_start(self):
        """Accessing .serial before start() raises RuntimeError."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        with pytest.raises(RuntimeError, match="Serial console not available"):
            _ = vm.serial

    def test_capture_screen_qmp_fallback(self):
        """capture_screen falls back to QMP when VNC not connected."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        vm._qmp = MagicMock()
        vm._qmp.screendump.return_value = {"return": {}}

        result = vm.capture_screen("/tmp/test.png", source="auto")
        assert result == "/tmp/test.png"
        vm._qmp.screendump.assert_called_once()

    def test_type_text_via_vnc(self):
        """type_text uses VNC when connected."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        vm._vnc_client = MagicMock()
        vm.type_text("hello")
        vm._vnc_client.type.assert_called_once_with("hello")

    def test_send_keys_single_via_vnc(self):
        """send_keys with one key uses VNC keyPress."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        vm._vnc_client = MagicMock()
        vm.send_keys("Return")
        vm._vnc_client.keyPress.assert_called_once_with("Return")

    def test_send_keys_combo_via_qmp(self):
        """send_keys with multiple keys uses QMP send_key_combo."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        vm._qmp = MagicMock()
        vm._qmp.send_key_combo.return_value = {"return": {}}
        vm.send_keys("ctrl", "c")
        vm._qmp.send_key_combo.assert_called_once_with("ctrl", "c")


# ═══════════════════════════════════════════════════════════════════
# Layer 3: VisionAgent tests (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════


class TestVisionAgent:
    """Unit tests for VisionAgent with mocked Ollama API."""

    def test_import(self):
        """VisionAgent, VisionResult, AgentAction are importable."""
        from scripts.lib.vision_agent import AgentAction, VisionAgent, VisionResult
        assert VisionAgent is not None
        assert VisionResult is not None
        assert AgentAction is not None

    def test_vision_result_dataclass(self):
        """VisionResult has expected fields."""
        from scripts.lib.vision_agent import VisionResult
        r = VisionResult(available=True, response="A desktop", error="")
        assert r.available is True
        assert r.response == "A desktop"

    def test_agent_action_dataclass(self):
        """AgentAction has expected fields with defaults."""
        from scripts.lib.vision_agent import AgentAction
        a = AgentAction(action_type="click", x=100, y=200, reasoning="click button")
        assert a.action_type == "click"
        assert a.x == 100
        assert a.keys == []

    def test_is_available_unreachable(self):
        """is_available returns False when Ollama is unreachable."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent(ollama_url="http://127.0.0.1:1", timeout=1)
        assert agent.is_available() is False

    def test_ask_file_not_found(self, tmp_path):
        """ask returns available=False for non-existent image."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        result = agent.ask("/nonexistent/image.png", "describe")
        assert result.available is False
        assert (
            "No such file" in result.error
            or "not found" in result.error.lower()
            or "FileNotFoundError" in result.error
        )

    def test_ask_ollama_unreachable(self, tmp_path):
        """ask returns available=False when Ollama is down."""
        from scripts.lib.vision_agent import VisionAgent

        # Create a tiny valid PNG
        img = Image.new("RGB", (10, 10), (0, 0, 0))
        path = str(tmp_path / "test.png")
        img.save(path)

        agent = VisionAgent(ollama_url="http://127.0.0.1:1", timeout=1)
        result = agent.ask(path, "describe this")
        assert result.available is False

    def test_parse_agent_response_valid_json(self):
        """_parse_agent_response parses clean JSON."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        action = agent._parse_agent_response('{"action": "click", "x": 100, "y": 200, "reasoning": "button"}')
        assert action.action_type == "click"
        assert action.x == 100
        assert action.y == 200
        assert action.reasoning == "button"

    def test_parse_agent_response_json_in_markdown(self):
        """_parse_agent_response extracts JSON from markdown code block."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        response = '```json\n{"action": "type", "text": "hello", "reasoning": "input"}\n```'
        action = agent._parse_agent_response(response)
        assert action.action_type == "type"
        assert action.text == "hello"

    def test_parse_agent_response_json_with_surrounding_text(self):
        """_parse_agent_response finds JSON embedded in text."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        response = 'I see a button. {"action": "click", "x": 50, "y": 60, "reasoning": "ok"} That is my answer.'
        action = agent._parse_agent_response(response)
        assert action.action_type == "click"
        assert action.x == 50

    def test_parse_agent_response_no_json(self):
        """_parse_agent_response returns fail action when no JSON found."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        action = agent._parse_agent_response("I don't know what to do")
        assert action.action_type == "fail"
        assert "No JSON" in action.reasoning

    def test_parse_agent_response_invalid_json(self):
        """_parse_agent_response returns fail for malformed JSON."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        action = agent._parse_agent_response('{"action": broken}')
        assert action.action_type == "fail"

    def test_parse_agent_response_all_action_types(self):
        """_parse_agent_response handles all valid action types."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        for action_type in ["click", "type", "key", "wait", "done", "fail"]:
            resp = json.dumps({"action": action_type, "reasoning": "test"})
            action = agent._parse_agent_response(resp)
            assert action.action_type == action_type

    def test_parse_agent_response_key_with_keys_list(self):
        """_parse_agent_response parses keys list for key action."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent()
        resp = '{"action": "key", "keys": ["Return", "Tab"], "reasoning": "confirm"}'
        action = agent._parse_agent_response(resp)
        assert action.keys == ["Return", "Tab"]

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_encode_image_resizes_large(self, tmp_path):
        """_encode_image resizes images larger than max_size."""
        from scripts.lib.vision_agent import VisionAgent
        img = Image.new("RGB", (2000, 2000), (128, 128, 128))
        path = str(tmp_path / "large.png")
        img.save(path)

        b64 = VisionAgent._encode_image(path, max_size=512)
        decoded = base64.b64decode(b64)
        # Re-open to check size
        import io
        resized = Image.open(io.BytesIO(decoded))
        assert max(resized.size) <= 512

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_encode_image_keeps_small(self, tmp_path):
        """_encode_image does not resize images smaller than max_size."""
        from scripts.lib.vision_agent import VisionAgent
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        path = str(tmp_path / "small.png")
        img.save(path)

        b64 = VisionAgent._encode_image(path, max_size=512)
        decoded = base64.b64decode(b64)
        import io
        result = Image.open(io.BytesIO(decoded))
        assert result.size == (100, 100)

    def test_agent_step_unavailable(self, tmp_path):
        """agent_step returns fail action when vision is unavailable."""
        from scripts.lib.vision_agent import VisionAgent
        if _HAS_PILLOW:
            img = Image.new("RGB", (10, 10), (0, 0, 0))
            path = str(tmp_path / "test.png")
            img.save(path)
        else:
            path = str(tmp_path / "test.png")
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        agent = VisionAgent(ollama_url="http://127.0.0.1:1", timeout=1)
        action = agent.agent_step(path, "find the terminal")
        assert action.action_type == "fail"
        assert "unavailable" in action.reasoning.lower()

    def test_ask_async_returns_future(self, tmp_path):
        """ask_async returns a Future object."""
        from concurrent.futures import Future

        from scripts.lib.vision_agent import VisionAgent
        if _HAS_PILLOW:
            img = Image.new("RGB", (10, 10), (0, 0, 0))
            path = str(tmp_path / "test.png")
            img.save(path)
        else:
            path = str(tmp_path / "test.png")
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        agent = VisionAgent(ollama_url="http://127.0.0.1:1", timeout=1)
        future = agent.ask_async(path, "describe")
        assert isinstance(future, Future)
        # Wait for completion (will be unavailable since port 1 is unreachable)
        result = future.result(timeout=10)
        assert result.available is False


# ═══════════════════════════════════════════════════════════════════
# Package-level import tests
# ═══════════════════════════════════════════════════════════════════


class TestPackageImports:
    """Verify the scripts.lib package re-exports work correctly."""

    def test_package_import_all_classes(self):
        """All main classes are importable from scripts.lib."""
        from scripts.lib import (
            GpuStatus,
            QMPClient,
            QMPError,
            SerialConsole,
            VisionAgent,
            VMController,
            VNCNotAvailableError,
        )
        assert GpuStatus is not None
        assert QMPClient is not None
        assert QMPError is not None
        assert SerialConsole is not None
        assert VMController is not None
        assert VNCNotAvailableError is not None
        assert VisionAgent is not None

    def test_package_import_functions(self):
        """All public functions are importable from scripts.lib."""
        from scripts.lib import (
            find_text_on_screen,
            images_match,
            is_not_black_screen,
            screen_has_text_content,
            wait_for_stable_screen,
        )
        assert callable(images_match)
        assert callable(is_not_black_screen)
        assert callable(screen_has_text_content)
        assert callable(wait_for_stable_screen)
        assert callable(find_text_on_screen)


# ═══════════════════════════════════════════════════════════════════
# GPU enforcement tests
# ═══════════════════════════════════════════════════════════════════


class TestGpuStatus:
    """Unit tests for GpuStatus dataclass and GPU check methods."""

    def test_gpu_status_import(self):
        """GpuStatus is importable from vision_agent."""
        from scripts.lib.vision_agent import GpuStatus
        assert GpuStatus is not None

    def test_gpu_status_defaults(self):
        """GpuStatus defaults to not loaded, no GPU."""
        from scripts.lib.vision_agent import GpuStatus
        status = GpuStatus(loaded=False)
        assert status.loaded is False
        assert status.size == 0
        assert status.size_vram == 0
        assert status.vram_percent == 0.0
        assert status.gpu_ok is False
        assert status.error == ""

    def test_gpu_status_full_gpu(self):
        """GpuStatus with 100% VRAM reports gpu_ok=True."""
        from scripts.lib.vision_agent import GpuStatus
        status = GpuStatus(
            loaded=True,
            size=5_000_000_000,
            size_vram=5_000_000_000,
            vram_percent=100.0,
            gpu_ok=True,
        )
        assert status.gpu_ok is True
        assert status.vram_percent == 100.0

    def test_gpu_status_partial_vram(self):
        """GpuStatus with low VRAM reports gpu_ok=False."""
        from scripts.lib.vision_agent import GpuStatus
        status = GpuStatus(
            loaded=True,
            size=5_000_000_000,
            size_vram=1_000_000_000,
            vram_percent=20.0,
            gpu_ok=False,
        )
        assert status.gpu_ok is False

    def test_check_gpu_loaded_unreachable(self):
        """check_gpu_loaded returns error when Ollama unreachable."""
        from scripts.lib.vision_agent import VisionAgent
        agent = VisionAgent(ollama_url="http://127.0.0.1:1", timeout=1)
        status = agent.check_gpu_loaded()
        assert status.loaded is False
        assert "Cannot reach" in status.error

    def test_check_gpu_loaded_with_mock_server(self, tmp_path):
        """check_gpu_loaded parses /api/ps response correctly."""
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from scripts.lib.vision_agent import VisionAgent

        ps_response = json.dumps({
            "models": [{
                "name": "qwen3-vl:8b",
                "size": 5_000_000_000,
                "size_vram": 4_500_000_000,
            }],
        })

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(ps_response.encode())

            def log_message(self, format, *args):  # noqa: A002
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        agent = VisionAgent(ollama_url=f"http://127.0.0.1:{port}", timeout=5)
        status = agent.check_gpu_loaded()
        server.server_close()

        assert status.loaded is True
        assert status.size == 5_000_000_000
        assert status.size_vram == 4_500_000_000
        assert status.vram_percent == 90.0
        assert status.gpu_ok is True

    def test_check_gpu_loaded_model_not_running(self, tmp_path):
        """check_gpu_loaded returns not loaded when model absent from /api/ps."""
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from scripts.lib.vision_agent import VisionAgent

        ps_response = json.dumps({"models": []})

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(ps_response.encode())

            def log_message(self, format, *args):  # noqa: A002
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        agent = VisionAgent(ollama_url=f"http://127.0.0.1:{port}", timeout=5)
        status = agent.check_gpu_loaded()
        server.server_close()

        assert status.loaded is False
        assert "not running" in status.error


# ═══════════════════════════════════════════════════════════════════
# VMController display parameter tests
# ═══════════════════════════════════════════════════════════════════


class TestVMControllerDisplay:
    """Tests for the VMController display parameter."""

    def test_default_display_none(self):
        """Default display is 'none'."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        assert vm.display == "none"

    def test_display_gtk(self):
        """Display can be set to 'gtk'."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso", display="gtk")
        assert vm.display == "gtk"

    def test_build_qemu_cmd_uses_display(self):
        """_build_qemu_cmd uses the display parameter."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso", display="gtk")
        vm._ovmf_vars_copy = "/tmp/test-vars.fd"
        cmd = vm._build_qemu_cmd("/usr/share/edk2/x64/OVMF_CODE.4m.fd")
        idx = cmd.index("-display")
        assert cmd[idx + 1] == "gtk"

    def test_build_qemu_cmd_display_none(self):
        """_build_qemu_cmd uses 'none' by default."""
        from scripts.lib.vm_controller import VMController
        vm = VMController("/tmp/test.iso")
        vm._ovmf_vars_copy = "/tmp/test-vars.fd"
        cmd = vm._build_qemu_cmd("/usr/share/edk2/x64/OVMF_CODE.4m.fd")
        idx = cmd.index("-display")
        assert cmd[idx + 1] == "none"


# ═══════════════════════════════════════════════════════════════════
# Vision tests module tests
# ═══════════════════════════════════════════════════════════════════


class TestVisionTests:
    """Tests for the vision_tests module."""

    def test_import(self):
        """Vision tests module is importable."""
        from scripts.lib.vision_tests import run_vision_tests
        assert callable(run_vision_tests)

    def test_individual_tests_importable(self):
        """All individual test functions are importable."""
        from scripts.lib.vision_tests import (
            test_application_launcher,
            test_desktop_environment_type,
            test_desktop_layout,
            test_dialog_text_readable,
            test_dismiss_welcome,
            test_font_rendering,
            test_grub_distro_label,
            test_grub_menu_readable,
            test_icon_distinguishability,
            test_open_terminal,
            test_panel_clock_readable,
            test_system_tray,
            test_terminal_verification,
            test_wallpaper_rendering,
            test_welcome_center,
        )
        assert callable(test_grub_menu_readable)
        assert callable(test_grub_distro_label)
        assert callable(test_desktop_environment_type)
        assert callable(test_desktop_layout)
        assert callable(test_wallpaper_rendering)
        assert callable(test_system_tray)
        assert callable(test_application_launcher)
        assert callable(test_welcome_center)
        assert callable(test_dialog_text_readable)
        assert callable(test_panel_clock_readable)
        assert callable(test_dismiss_welcome)
        assert callable(test_open_terminal)
        assert callable(test_terminal_verification)
        assert callable(test_font_rendering)
        assert callable(test_icon_distinguishability)

    def test_assert_vision_with_mock(self):
        """_assert_vision correctly checks keywords in response."""
        from scripts.lib.vision_tests import _assert_vision

        results = []

        def mock_record(name, status, detail=""):
            results.append((name, status, detail))

        mock_vision = MagicMock()
        mock_vision.ask.return_value = MagicMock(
            available=True,
            response="This is a KDE Plasma desktop environment",
        )

        passed = _assert_vision(
            mock_vision, "/fake.png", "what DE?",
            ["kde", "plasma"], mock_record, "test",
        )
        assert passed is True
        assert results[-1][1] == "PASS"

    def test_assert_vision_no_match(self):
        """_assert_vision returns False when no keywords match."""
        from scripts.lib.vision_tests import _assert_vision

        results = []

        def mock_record(name, status, detail=""):
            results.append((name, status, detail))

        mock_vision = MagicMock()
        mock_vision.ask.return_value = MagicMock(
            available=True,
            response="I see a blue screen with nothing on it",
        )

        passed = _assert_vision(
            mock_vision, "/fake.png", "what DE?",
            ["kde", "plasma"], mock_record, "test",
        )
        assert passed is False
        assert results[-1][1] == "FAIL"

    def test_assert_vision_unavailable(self):
        """_assert_vision returns False when vision unavailable."""
        from scripts.lib.vision_tests import _assert_vision

        results = []

        def mock_record(name, status, detail=""):
            results.append((name, status, detail))

        mock_vision = MagicMock()
        mock_vision.ask.return_value = MagicMock(
            available=False,
            error="Connection refused",
        )

        passed = _assert_vision(
            mock_vision, "/fake.png", "what DE?",
            ["kde"], mock_record, "test",
        )
        assert passed is False
        assert results[-1][1] == "FAIL"

    def test_run_vision_tests_skips_grub_without_screenshot(self):
        """run_vision_tests skips GRUB tests when no screenshot provided."""
        from scripts.lib.vision_tests import run_vision_tests

        results = []

        def mock_record(name, status, detail=""):
            results.append((name, status, detail))

        mock_vision = MagicMock()
        mock_vision.ask.return_value = MagicMock(
            available=True,
            response="A KDE Plasma desktop with taskbar and clock at bottom",
        )

        mock_vm = MagicMock()
        mock_screenshot = MagicMock(return_value="/fake/desktop.png")

        run_vision_tests(
            mock_vision, mock_vm, mock_record, mock_screenshot,
            vnc_available=False,
            grub_screenshot=None,
            desktop_screenshot="/fake/desktop.png",
        )

        grub_results = [r for r in results if r[0].startswith("A")]
        assert all(r[1] == "SKIP" for r in grub_results)

    def test_run_vision_tests_skips_interactive_without_vnc(self):
        """run_vision_tests skips interactive tests when VNC unavailable."""
        from scripts.lib.vision_tests import run_vision_tests

        results = []

        def mock_record(name, status, detail=""):
            results.append((name, status, detail))

        mock_vision = MagicMock()
        mock_vision.ask.return_value = MagicMock(
            available=True,
            response="KDE Plasma desktop with panel clock icons launcher taskbar welcome",
        )

        run_vision_tests(
            mock_vision, MagicMock(), mock_record, MagicMock(return_value="/fake.png"),
            vnc_available=False,
            desktop_screenshot="/fake/desktop.png",
        )

        interactive_results = [r for r in results if r[0].startswith("E")]
        assert all(r[1] == "SKIP" for r in interactive_results)


# ═══════════════════════════════════════════════════════════════════
# Report generator tests
# ═══════════════════════════════════════════════════════════════════


class TestReportGenerator:
    """Tests for the HTML report generator."""

    def test_import(self):
        """generate_report is importable."""
        from scripts.lib.report_generator import generate_report
        assert callable(generate_report)

    @pytest.mark.skipif(not _HAS_PILLOW, reason="Pillow not available")
    def test_generate_report_creates_html(self, tmp_path):
        """generate_report creates an index.html file."""
        from scripts.lib.report_generator import generate_report

        # Create some fake screenshots
        for name in ["01_boot.png", "02_desktop.png"]:
            img = Image.new("RGB", (100, 100), (128, 128, 128))
            img.save(str(tmp_path / name))

        results = [
            ("Boot test", "PASS", "Booted OK"),
            ("Desktop test", "FAIL", "Black screen"),
            ("OCR test", "SKIP", "No tesseract"),
        ]

        report_path = generate_report(str(tmp_path), results, title="Test Report")
        assert os.path.exists(report_path)
        assert report_path.endswith("index.html")

        content = Path(report_path).read_text()
        assert "Test Report" in content
        assert "01_boot" in content
        assert "02_desktop" in content
        assert "Boot test" in content
        assert "PASS" in content
        assert "FAIL" in content

    def test_generate_report_empty(self, tmp_path):
        """generate_report works with no screenshots."""
        from scripts.lib.report_generator import generate_report

        report_path = generate_report(str(tmp_path), [], title="Empty")
        assert os.path.exists(report_path)
        content = Path(report_path).read_text()
        assert "Empty" in content
        assert "0 passed" in content

    def test_generate_report_escapes_html(self, tmp_path):
        """generate_report escapes HTML in test details."""
        from scripts.lib.report_generator import generate_report

        results = [("Test", "FAIL", "<script>alert('xss')</script>")]
        report_path = generate_report(str(tmp_path), results)
        content = Path(report_path).read_text()
        # The injected content must be escaped (the report's own <script> for JS viewer is OK)
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in content


# ═══════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════


class _MockQMPServer:
    """A minimal QMP server for testing QMPClient.

    Listens on a Unix socket, sends a QMP greeting, accepts commands,
    and replies with {"return": {}} for each.
    """

    def __init__(self, sock_path: str) -> None:
        self.sock_path = sock_path
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self.received_commands: list[dict] = []

    def start(self) -> None:
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.sock_path)
        self._server_sock.listen(1)
        self._server_sock.settimeout(5)
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            self._server_sock.close()
        if self._thread:
            self._thread.join(timeout=5)
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

    def _serve(self) -> None:
        try:
            conn, _ = self._server_sock.accept()
            conn.settimeout(5)
        except (TimeoutError, OSError):
            return

        # Send QMP greeting
        greeting = json.dumps({"QMP": {"version": {"qemu": {"micro": 0, "minor": 0, "major": 9}}}})
        conn.sendall(greeting.encode() + b"\n")

        while self._running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                for line in data.split(b"\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cmd = json.loads(line)
                        self.received_commands.append(cmd)
                        # Always respond with success
                        resp = json.dumps({"return": {}})
                        conn.sendall(resp.encode() + b"\n")
                    except json.JSONDecodeError:
                        continue
            except (TimeoutError, OSError):
                break

        conn.close()
