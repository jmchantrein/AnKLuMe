"""Screen analysis: image comparison, OCR, and template matching.

Layer 2 of the GUI automation stack. Refactored from existing image
helpers in live-os-test-graphical.py, extended with OpenCV template
matching and Tesseract OCR. All heavy dependencies are lazily imported.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class MatchResult:
    """Result of a template match operation."""

    found: bool
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    center_x: int = 0
    center_y: int = 0
    confidence: float = 0.0


# ── Image comparison (Pillow-based, from existing code) ──


def images_match(
    actual_path: str,
    reference_path: str,
    max_diff_percent: float = 2.0,
) -> tuple[bool | None, float | None, str | None]:
    """Compare two images. Returns (match, diff_percent, diff_path).

    Returns (None, None, None) if reference doesn't exist.
    Returns (True, 0.0, None) if Pillow/pixelmatch unavailable.
    """
    try:
        from PIL import Image
        from pixelmatch.contrib.PIL import pixelmatch as pm
    except ImportError:
        return True, 0.0, None

    if not os.path.isfile(reference_path):
        return None, None, None

    img1 = Image.open(actual_path).convert("RGBA")
    img2 = Image.open(reference_path).convert("RGBA")

    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

    width, height = img1.size
    diff_img = Image.new("RGBA", (width, height))
    num_diff = pm(img1, img2, output=diff_img, threshold=0.1, includeAA=False)
    total = width * height
    diff_percent = (num_diff / total) * 100

    diff_path = actual_path.replace(".png", "_diff.png")
    diff_img.save(diff_path)

    return diff_percent < max_diff_percent, diff_percent, diff_path


def is_not_black_screen(image_path: str, min_nonblack_permille: int = 10) -> bool:
    """Check if the screen has visible content (not all black).

    Threshold: 10 permille (1.0%) of pixels brighter than 5.
    """
    try:
        from PIL import Image
    except ImportError:
        return True
    img = Image.open(image_path).convert("L")
    pixels = img.tobytes()
    nonblack = sum(1 for p in pixels if p > 5)
    permille = int(nonblack * 1000 / len(pixels))
    return permille >= min_nonblack_permille


def screen_has_text_content(image_path: str, min_bright_percent: float = 5) -> bool:
    """Check if screen has text-like content (bright pixels on dark bg)."""
    try:
        from PIL import Image
    except ImportError:
        return True
    img = Image.open(image_path).convert("L")
    pixels = img.tobytes()
    bright = sum(1 for p in pixels if p > 128)
    return (bright / len(pixels)) * 100 > min_bright_percent


# ── Wait helpers ──


def wait_for_stable_screen(
    capture_fn: Callable[[str], Any],
    temp_dir: str,
    interval: float = 3,
    stable_count: int = 3,
    timeout: float = 120,
    threshold: float = 0.5,
) -> str | None:
    """Wait until consecutive screenshots match (screen stabilized).

    Args:
        capture_fn: Callable that takes a filename and saves a screenshot there.
        temp_dir: Directory for temporary comparison images.
        interval: Seconds between captures.
        stable_count: Number of consecutive matches required.
        timeout: Maximum seconds to wait.
        threshold: Maximum diff percent to consider "stable".

    Returns path to the final stable screenshot, or None on timeout.
    """
    start = time.time()
    prev_path = None
    consecutive = 0
    iteration = 0

    while time.time() - start < timeout:
        iteration += 1
        curr_path = os.path.join(temp_dir, f"stable_check_{iteration}.png")
        capture_fn(curr_path)
        time.sleep(0.5)

        if not os.path.exists(curr_path) or os.path.getsize(curr_path) < 100:
            time.sleep(interval)
            continue

        if prev_path and os.path.exists(prev_path):
            match, _diff_pct, _ = images_match(curr_path, prev_path, max_diff_percent=threshold)
            if match:
                consecutive += 1
                if consecutive >= stable_count:
                    return curr_path
            else:
                consecutive = 0

        prev_path = curr_path
        time.sleep(interval)

    return None


# ── OpenCV template matching ──


def _load_cv2() -> Any:
    """Lazily import OpenCV with a clear error message."""
    try:
        import cv2
    except ImportError:
        msg = "opencv-python-headless is required for template matching: pip install opencv-python-headless"
        raise ImportError(msg)  # noqa: B904
    return cv2


def find_template(
    screenshot: str,
    template: str,
    threshold: float = 0.8,
) -> MatchResult:
    """Find a template image within a screenshot.

    Args:
        screenshot: Path to the full screenshot image.
        template: Path to the template image to find.
        threshold: Minimum confidence (0.0-1.0).

    Returns MatchResult with position and confidence.
    """
    cv2 = _load_cv2()
    img = cv2.imread(screenshot, cv2.IMREAD_COLOR)
    tmpl = cv2.imread(template, cv2.IMREAD_COLOR)
    if img is None or tmpl is None:
        return MatchResult(found=False)

    result = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < threshold:
        return MatchResult(found=False, confidence=max_val)

    h, w = tmpl.shape[:2]
    x, y = max_loc
    return MatchResult(
        found=True,
        x=x, y=y, w=w, h=h,
        center_x=x + w // 2,
        center_y=y + h // 2,
        confidence=max_val,
    )


def find_all_templates(
    screenshot: str,
    template: str,
    threshold: float = 0.8,
) -> list[MatchResult]:
    """Find all occurrences of a template in a screenshot."""
    cv2 = _load_cv2()
    import numpy as np

    img = cv2.imread(screenshot, cv2.IMREAD_COLOR)
    tmpl = cv2.imread(template, cv2.IMREAD_COLOR)
    if img is None or tmpl is None:
        return []

    result = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)

    h, w = tmpl.shape[:2]
    matches = []
    used: list[tuple[int, int]] = []  # Deduplicate overlapping matches

    for pt in zip(locations[1], locations[0], strict=True):  # (x, y)
        x, y = int(pt[0]), int(pt[1])
        # Skip if too close to an existing match
        if any(abs(x - ux) < w // 2 and abs(y - uy) < h // 2 for ux, uy in used):
            continue
        used.append((x, y))
        conf = float(result[y, x])
        matches.append(MatchResult(
            found=True,
            x=x, y=y, w=w, h=h,
            center_x=x + w // 2,
            center_y=y + h // 2,
            confidence=conf,
        ))

    return sorted(matches, key=lambda m: m.confidence, reverse=True)


# ── Tesseract OCR ──


def _load_tesseract() -> Any:
    """Lazily import pytesseract with a clear error message."""
    try:
        import pytesseract
    except ImportError:
        msg = "pytesseract is required for OCR: pip install pytesseract (+ system tesseract-ocr)"
        raise ImportError(msg)  # noqa: B904
    return pytesseract


def ocr_full(image_path: str, lang: str = "eng") -> str:
    """Run OCR on the full image. Returns extracted text."""
    pytesseract = _load_tesseract()
    from PIL import Image

    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang=lang).strip()


def ocr_region(image_path: str, x: int, y: int, w: int, h: int, lang: str = "eng") -> str:
    """Run OCR on a cropped region of the image."""
    pytesseract = _load_tesseract()
    from PIL import Image

    img = Image.open(image_path)
    cropped = img.crop((x, y, x + w, y + h))
    return pytesseract.image_to_string(cropped, lang=lang).strip()


def find_text_on_screen(image_path: str, text: str, lang: str = "eng") -> tuple[bool, str]:
    """Check if text appears on screen via OCR.

    Returns (found, full_ocr_text).
    """
    full_text = ocr_full(image_path, lang=lang)
    return text.lower() in full_text.lower(), full_text
