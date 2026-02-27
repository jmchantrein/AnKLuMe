"""GUI automation stack for headless QEMU testing.

4-layer architecture:
- Layer 0: QEMU + KVM + QMP + serial (vm_controller, qmp_client, serial_console)
- Layer 1: VNC mouse/keyboard (vm_controller with vncdotool)
- Layer 2: OpenCV + Tesseract OCR (screen_analysis)
- Layer 3: Ollama vision model (vision_agent)

All layers degrade gracefully — missing dependencies = skip, not crash.
"""

from scripts.lib.qmp_client import QMPClient, QMPError
from scripts.lib.screen_analysis import (
    find_text_on_screen,
    images_match,
    is_not_black_screen,
    screen_has_text_content,
    wait_for_stable_screen,
)
from scripts.lib.serial_console import SerialConsole
from scripts.lib.vision_agent import GpuStatus, VisionAgent
from scripts.lib.vm_controller import VMController, VNCNotAvailableError

__all__ = [
    "GpuStatus",
    "QMPClient",
    "QMPError",
    "SerialConsole",
    "VMController",
    "VNCNotAvailableError",
    "VisionAgent",
    "find_text_on_screen",
    "images_match",
    "is_not_black_screen",
    "screen_has_text_content",
    "wait_for_stable_screen",
]
