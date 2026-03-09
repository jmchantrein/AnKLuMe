"""Tests unitaires — STT push-to-talk.

Teste la configuration, les dépendances, la génération de config Voxtype,
et le service systemd.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from anklume.cli._stt import (
    STT_HOST_DEPS,
    _generate_systemd_service,
    _generate_voxtype_config,
    check_stt_dependencies,
    get_stt_config,
)

HOST_STT_DIR = Path(__file__).parent.parent / "host" / "stt"


# ---------------------------------------------------------------------------
# Scripts existence (anciens scripts conservés pour référence)
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
# STT config
# ---------------------------------------------------------------------------


class TestSttConfig:
    def test_default_config(self):
        config = get_stt_config()
        assert config["model"] == "Systran/faster-whisper-medium"
        assert config["language"] == "fr"
        assert config["hotkey"] == "F23"
        assert config["xkb_layout"] == "fr"

    def test_config_from_env(self):
        env = {
            "STT_API_URL": "http://localhost:9000",
            "STT_MODEL": "Systran/faster-whisper-large-v3",
            "STT_LANGUAGE": "en",
            "STT_HOTKEY": "SCROLLLOCK",
            "STT_XKB_LAYOUT": "us",
        }
        with patch.dict("os.environ", env):
            config = get_stt_config()
        assert config["api_url"] == "http://localhost:9000"
        assert config["model"] == "Systran/faster-whisper-large-v3"
        assert config["language"] == "en"
        assert config["hotkey"] == "SCROLLLOCK"
        assert config["xkb_layout"] == "us"

    def test_partial_env_override(self):
        with patch.dict("os.environ", {"STT_LANGUAGE": "de"}):
            config = get_stt_config()
        assert config["language"] == "de"
        assert config["model"] == "Systran/faster-whisper-medium"


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
            return None if name == "voxtype" else f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=fake_which):
            missing = check_stt_dependencies()
        assert "voxtype" in missing

    def test_all_missing(self):
        with patch("shutil.which", return_value=None):
            missing = check_stt_dependencies()
        assert len(missing) == len(STT_HOST_DEPS)

    def test_dependencies_list_complete(self):
        assert "voxtype" in STT_HOST_DEPS
        assert "dotool" in STT_HOST_DEPS
        assert "pw-record" in STT_HOST_DEPS
        assert "notify-send" in STT_HOST_DEPS


# ---------------------------------------------------------------------------
# Voxtype config generation
# ---------------------------------------------------------------------------


class TestVoxtypeConfig:
    def test_generates_valid_toml(self):
        config = _generate_voxtype_config(
            endpoint="http://10.110.0.135:8000",
            model="Systran/faster-whisper-medium",
            language="fr",
            hotkey="F23",
        )
        assert "[hotkey]" in config
        assert "[whisper]" in config
        assert "[output]" in config
        assert 'mode = "remote"' in config

    def test_contains_endpoint(self):
        config = _generate_voxtype_config(
            endpoint="http://10.110.0.135:8000",
            model="Systran/faster-whisper-medium",
            language="fr",
            hotkey="F23",
        )
        assert "http://10.110.0.135:8000" in config

    def test_contains_model(self):
        config = _generate_voxtype_config(
            endpoint="http://10.110.0.135:8000",
            model="Systran/faster-whisper-large-v3",
            language="fr",
            hotkey="F23",
        )
        assert "Systran/faster-whisper-large-v3" in config

    def test_contains_language(self):
        config = _generate_voxtype_config(
            endpoint="http://x:8000",
            model="m",
            language="en",
            hotkey="F23",
        )
        assert 'language = "en"' in config

    def test_contains_hotkey(self):
        config = _generate_voxtype_config(
            endpoint="http://x:8000",
            model="m",
            language="fr",
            hotkey="SCROLLLOCK",
        )
        assert 'key = "SCROLLLOCK"' in config

    def test_uses_dotool_driver(self):
        config = _generate_voxtype_config(
            endpoint="http://x:8000",
            model="m",
            language="fr",
            hotkey="F23",
        )
        assert "dotool" in config

    def test_push_to_talk_mode(self):
        config = _generate_voxtype_config(
            endpoint="http://x:8000",
            model="m",
            language="fr",
            hotkey="F23",
        )
        assert 'mode = "push_to_talk"' in config


# ---------------------------------------------------------------------------
# Systemd service generation
# ---------------------------------------------------------------------------


class TestSystemdService:
    def test_generates_valid_unit(self):
        service = _generate_systemd_service("fr")
        assert "[Unit]" in service
        assert "[Service]" in service
        assert "[Install]" in service

    def test_contains_dotool_layout(self):
        service = _generate_systemd_service("fr")
        assert "DOTOOL_XKB_LAYOUT=fr" in service

    def test_contains_voxtype(self):
        service = _generate_systemd_service("fr")
        assert "voxtype" in service

    def test_starts_after_pipewire(self):
        service = _generate_systemd_service("fr")
        assert "pipewire" in service

    def test_different_layout(self):
        service = _generate_systemd_service("us")
        assert "DOTOOL_XKB_LAYOUT=us" in service


# ---------------------------------------------------------------------------
# Push-to-talk script content (ancien script, conservé)
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
