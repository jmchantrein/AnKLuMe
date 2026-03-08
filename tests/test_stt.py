"""Tests unitaires — STT push-to-talk (Phase 10d).

Teste les composants Python (azerty-type, streaming, CLI stt)
et la présence des scripts.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from anklume.cli._stt import (
    STT_DEPENDENCIES,
    check_stt_dependencies,
    get_stt_config,
)

HOST_STT_DIR = Path(__file__).parent.parent / "host" / "stt"


# ---------------------------------------------------------------------------
# Scripts existence
# ---------------------------------------------------------------------------


class TestScriptsExist:
    def test_push_to_talk_exists(self):
        assert (HOST_STT_DIR / "push-to-talk.sh").is_file()

    def test_push_to_talk_is_executable(self):
        script = HOST_STT_DIR / "push-to-talk.sh"
        assert script.stat().st_mode & 0o111

    def test_push_to_talk_has_shebang(self):
        content = (HOST_STT_DIR / "push-to-talk.sh").read_text()
        assert content.startswith("#!/")

    def test_push_to_talk_uses_pipefail(self):
        content = (HOST_STT_DIR / "push-to-talk.sh").read_text()
        assert "set -euo pipefail" in content

    def test_azerty_type_exists(self):
        assert (HOST_STT_DIR / "azerty-type.py").is_file()

    def test_streaming_exists(self):
        assert (HOST_STT_DIR / "streaming.py").is_file()


# ---------------------------------------------------------------------------
# Push-to-talk script content
# ---------------------------------------------------------------------------


_push_to_talk_content: str | None = None


def _get_push_to_talk() -> str:
    global _push_to_talk_content
    if _push_to_talk_content is None:
        _push_to_talk_content = (HOST_STT_DIR / "push-to-talk.sh").read_text()
    return _push_to_talk_content


class TestPushToTalkContent:
    def test_uses_pw_record(self):
        assert "pw-record" in _get_push_to_talk()

    def test_uses_curl_for_transcription(self):
        assert "curl" in _get_push_to_talk()

    def test_uses_notify_send(self):
        assert "notify-send" in _get_push_to_talk()

    def test_uses_wl_copy(self):
        assert "wl-copy" in _get_push_to_talk()

    def test_detects_terminal(self):
        assert "kdotool" in _get_push_to_talk()

    def test_cleans_temp_files(self):
        assert "trap" in _get_push_to_talk()

    def test_configurable_api_url(self):
        assert "STT_API_URL" in _get_push_to_talk()

    def test_configurable_language(self):
        assert "STT_LANGUAGE" in _get_push_to_talk()


# ---------------------------------------------------------------------------
# AZERTY type
# ---------------------------------------------------------------------------


_azerty_content: str | None = None


def _get_azerty() -> str:
    global _azerty_content
    if _azerty_content is None:
        _azerty_content = (HOST_STT_DIR / "azerty-type.py").read_text()
    return _azerty_content


class TestAzertyType:
    def test_has_main_function(self):
        content = _get_azerty()
        assert "def main" in content or "if __name__" in content

    def test_uses_wtype(self):
        assert "wtype" in _get_azerty()


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


_streaming_content: str | None = None


def _get_streaming() -> str:
    global _streaming_content
    if _streaming_content is None:
        _streaming_content = (HOST_STT_DIR / "streaming.py").read_text()
    return _streaming_content


class TestStreaming:
    def test_has_silence_detection(self):
        content = _get_streaming().lower()
        assert "rms" in content or "silence" in content

    def test_has_hallucination_filter(self):
        content = _get_streaming().lower()
        assert "hallucin" in content or "filter" in content

    def test_has_chunk_logic(self):
        assert "chunk" in _get_streaming().lower()


# ---------------------------------------------------------------------------
# STT config
# ---------------------------------------------------------------------------


class TestSttConfig:
    def test_default_config(self):
        config = get_stt_config()
        assert config["api_url"] == "http://10.100.3.1:8000"
        assert config["model"] == "base"
        assert config["language"] == "fr"

    def test_config_from_env(self):
        env = {
            "STT_API_URL": "http://localhost:9000",
            "STT_MODEL": "large-v3",
            "STT_LANGUAGE": "en",
        }
        with patch.dict("os.environ", env):
            config = get_stt_config()
        assert config["api_url"] == "http://localhost:9000"
        assert config["model"] == "large-v3"
        assert config["language"] == "en"

    def test_partial_env_override(self):
        with patch.dict("os.environ", {"STT_LANGUAGE": "de"}):
            config = get_stt_config()
        assert config["language"] == "de"
        assert config["api_url"] == "http://10.100.3.1:8000"


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------


class TestCheckDependencies:
    def test_all_present(self):
        with patch("shutil.which", return_value="/usr/bin/tool"):
            missing = check_stt_dependencies()
        assert missing == []

    def test_some_missing(self):
        def fake_which(name):
            return None if name == "wtype" else f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=fake_which):
            missing = check_stt_dependencies()
        assert "wtype" in missing

    def test_all_missing(self):
        with patch("shutil.which", return_value=None):
            missing = check_stt_dependencies()
        assert len(missing) == len(STT_DEPENDENCIES)

    def test_dependencies_list_complete(self):
        assert "pw-record" in STT_DEPENDENCIES
        assert "wtype" in STT_DEPENDENCIES
        assert "wl-copy" in STT_DEPENDENCIES
        assert "kdotool" in STT_DEPENDENCIES
        assert "jq" in STT_DEPENDENCIES
        assert "notify-send" in STT_DEPENDENCIES
