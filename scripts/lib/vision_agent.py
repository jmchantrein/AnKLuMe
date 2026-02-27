"""Ollama multimodal vision agent for AI-driven GUI testing.

Layer 3 of the GUI automation stack. Uses Ollama's vision models
(qwen3-vl:8b) to understand screenshots and drive UI interactions.
HTTP via urllib (no requests dependency), matching scripts/ollama-dev.py pattern.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class GpuStatus:
    """GPU loading status for the vision model."""

    loaded: bool
    size: int = 0
    size_vram: int = 0
    vram_percent: float = 0.0
    gpu_ok: bool = False
    error: str = ""


@dataclass
class VisionResult:
    """Result from a vision model query."""

    available: bool
    response: str = ""
    error: str = ""


@dataclass
class AgentAction:
    """A single action recommended by the vision agent."""

    action_type: str  # "click", "type", "key", "wait", "done", "fail"
    x: int = 0
    y: int = 0
    text: str = ""
    keys: list[str] = field(default_factory=list)
    reasoning: str = ""


class VisionAgent:
    """Ollama-based multimodal vision agent."""

    def __init__(
        self,
        ollama_url: str = "http://10.100.3.1:11434",
        model: str = "qwen3-vl:8b",
        timeout: int = 180,
    ) -> None:
        self.base_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=1)

    def is_available(self) -> bool:
        """Check if Ollama is reachable and the model is present."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            # Check for exact match or base name match (model:latest)
            base = self.model.split(":")[0]
            return any(self.model in m or m.startswith(base) for m in models)
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    def warmup(self) -> bool:
        """Pre-load the model into memory with a minimal image request.

        Sends a tiny 1x1 PNG to trigger both the text and vision encoder
        initialization. Call before timed tests to avoid cold-start timeouts.
        Returns True if the model loaded successfully.
        """
        # Create a minimal 1x1 red pixel PNG (67 bytes)
        tiny_png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
        )
        try:
            data = {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": "What color is this?",
                    "images": [tiny_png],
                }],
                "stream": False,
                "options": {"num_ctx": 256, "num_predict": 1},
            }
            payload = json.dumps(data).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
            log.info("Vision model %s warmed up", self.model)
            return True
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            log.warning("Vision model warmup failed: %s", e)
            return False

    def check_gpu_loaded(self, min_vram_percent: float = 80.0) -> GpuStatus:
        """Check if the model is loaded on GPU with sufficient VRAM usage.

        Queries Ollama's /api/ps endpoint to verify the model is running
        and loaded into GPU VRAM (not CPU RAM).

        Args:
            min_vram_percent: Minimum percentage of model in VRAM to consider GPU-loaded.

        Returns:
            GpuStatus with loading details.
        """
        try:
            req = urllib.request.Request(f"{self.base_url}/api/ps")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return GpuStatus(loaded=False, error=f"Cannot reach Ollama: {e}")

        models = data.get("models", [])
        base = self.model.split(":")[0]
        for m in models:
            name = m.get("name", "")
            if self.model in name or name.startswith(base):
                size = m.get("size", 0)
                size_vram = m.get("size_vram", 0)
                vram_pct = (size_vram / size * 100) if size > 0 else 0.0
                gpu_ok = vram_pct >= min_vram_percent
                return GpuStatus(
                    loaded=True,
                    size=size,
                    size_vram=size_vram,
                    vram_percent=round(vram_pct, 1),
                    gpu_ok=gpu_ok,
                )
        return GpuStatus(loaded=False, error=f"Model {self.model} not running")

    def ensure_gpu(self, min_vram_percent: float = 80.0) -> GpuStatus:
        """Warmup the model and verify it loaded on GPU.

        Combines warmup() + check_gpu_loaded() in one call.

        Returns:
            GpuStatus after warmup attempt.
        """
        self.warmup()
        return self.check_gpu_loaded(min_vram_percent)

    def ask(self, image_path: str, prompt: str) -> VisionResult:
        """Send an image + prompt to the vision model.

        Returns VisionResult. Gracefully returns available=False if Ollama is down.
        """
        try:
            image_b64 = self._encode_image(image_path)
        except (FileNotFoundError, OSError) as e:
            return VisionResult(available=False, error=str(e))

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                },
            ],
            "stream": False,
            "options": {"num_ctx": 4096},
        }

        try:
            payload = json.dumps(data).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode())
            content = result.get("message", {}).get("content", "")
            return VisionResult(available=True, response=content)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            log.warning("Vision agent request failed: %s", e)
            return VisionResult(available=False, error=str(e))

    def ask_async(self, image_path: str, prompt: str) -> Future[VisionResult]:
        """Non-blocking version of ask(). Returns a Future."""
        return self._executor.submit(self.ask, image_path, prompt)

    def describe_screen(self, image_path: str) -> VisionResult:
        """Describe what is visible on screen."""
        prompt = (
            "Describe what you see on this computer screen. "
            "Be specific about UI elements, windows, text, and buttons visible. "
            "If it's a desktop environment, name it. If there's a dialog or menu, describe its content."
        )
        return self.ask(image_path, prompt)

    def find_element(self, image_path: str, description: str) -> VisionResult:
        """Find a UI element by description and return its approximate coordinates.

        The response should contain x,y coordinates that can be parsed.
        """
        prompt = (
            f"Look at this screenshot and find: {description}\n\n"
            "If you can see it, respond with ONLY a JSON object like:\n"
            '{"found": true, "x": 512, "y": 384, "description": "what you found"}\n\n'
            "If you cannot find it, respond with:\n"
            '{"found": false, "description": "what you see instead"}\n\n'
            "Coordinates should be in pixels from top-left corner."
        )
        return self.ask(image_path, prompt)

    def agent_step(
        self,
        image_path: str,
        task: str,
        history: list[str] | None = None,
    ) -> AgentAction:
        """Given a screenshot and task, return ONE action to perform.

        The caller controls the agent loop — this returns a single step.
        """
        history_text = ""
        if history:
            history_text = "\n\nPrevious actions:\n" + "\n".join(f"- {h}" for h in history[-5:])

        prompt = (
            f"You are a GUI automation agent. Your task: {task}\n"
            f"{history_text}\n\n"
            "Look at this screenshot and decide the NEXT SINGLE action.\n"
            "Respond with ONLY a JSON object:\n"
            '{"action": "click", "x": 100, "y": 200, "reasoning": "clicking the OK button"}\n'
            '{"action": "type", "text": "hello", "reasoning": "typing in the search field"}\n'
            '{"action": "key", "keys": ["Return"], "reasoning": "pressing Enter to confirm"}\n'
            '{"action": "wait", "reasoning": "waiting for dialog to appear"}\n'
            '{"action": "done", "reasoning": "task completed successfully"}\n'
            '{"action": "fail", "reasoning": "cannot find the expected element"}\n'
        )

        result = self.ask(image_path, prompt)
        if not result.available:
            return AgentAction(action_type="fail", reasoning=f"Vision unavailable: {result.error}")

        return self._parse_agent_response(result.response)

    def _parse_agent_response(self, response: str) -> AgentAction:
        """Parse the vision model's JSON response into an AgentAction."""
        # Try to extract JSON from the response
        text = response.strip()

        # Handle markdown code blocks
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    text = part
                    break

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to find a JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    return AgentAction(
                        action_type="fail",
                        reasoning=f"Could not parse response: {text[:200]}",
                    )
            else:
                return AgentAction(
                    action_type="fail",
                    reasoning=f"No JSON in response: {text[:200]}",
                )

        action_type = data.get("action", "fail")
        return AgentAction(
            action_type=action_type,
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            text=data.get("text", ""),
            keys=data.get("keys", []),
            reasoning=data.get("reasoning", ""),
        )

    @staticmethod
    def _encode_image(image_path: str, max_size: int = 1024) -> str:
        """Read and resize image to max_size px, return base64."""
        try:
            from PIL import Image
        except ImportError:
            # No Pillow — send raw (may be large)
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode()

        img = Image.open(image_path)
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)

        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def __del__(self) -> None:
        self._executor.shutdown(wait=False)
