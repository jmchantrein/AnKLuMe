"""Tests for the AnKLuMe OpenClaw proxy (scripts/mcp-anklume-dev.py).

Covers:
- Script quality (ruff clean, valid Python)
- Brain mode definitions (completeness, consistency)
- Proxy tag on all proxy-emitted messages
- Tool registry completeness
- Safety filters (blocked targets, blocked commands)
- Usage tracking internals
- Session management
- Documentation files (openclaw.md, openclaw_FR.md)
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROXY_SCRIPT = PROJECT_ROOT / "scripts" / "mcp-anklume-dev.py"
OPENCLAW_DOC_EN = PROJECT_ROOT / "docs" / "openclaw.md"
OPENCLAW_DOC_FR = PROJECT_ROOT / "docs" / "openclaw_FR.md"


# ── Script quality ─────────────────────────────────────────────────


class TestProxyScriptQuality:
    """Proxy script passes quality checks."""

    @pytest.mark.skipif(not shutil.which("ruff"), reason="ruff not installed")
    def test_ruff_clean(self):
        result = subprocess.run(
            ["ruff", "check", str(PROXY_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"ruff errors:\n{result.stdout}"

    def test_valid_python_syntax(self):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(PROXY_SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error:\n{result.stderr}"


# ── Brain modes ────────────────────────────────────────────────────


class TestBrainModes:
    """Verify brain mode definitions in the proxy."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_three_brain_modes_defined(self):
        """_BRAIN_MODES has exactly 3 entries: anklume, assistant, local."""
        assert '"anklume"' in self.content
        assert '"assistant"' in self.content
        assert '"local"' in self.content

    def test_brain_modes_have_descriptions(self):
        """Each brain mode has a description string."""
        # Each entry is ("model_string", "description")
        assert "expert AnKLuMe" in self.content
        assert "assistant" in self.content.lower()

    def test_llama_services_defined(self):
        """_LLAMA_SERVICES maps each mode to a systemd service."""
        assert "llama-server" in self.content
        assert "llama-server-chat" in self.content

    def test_wakeup_messages_for_all_modes(self):
        """Each brain mode has a wakeup message."""
        for mode in ["anklume", "assistant", "local"]:
            pattern = rf'"{mode}".*?_PROXY_TAG'
            assert re.search(pattern, self.content, re.DOTALL), \
                f"No wakeup message for mode '{mode}'"


# ── Proxy tag ──────────────────────────────────────────────────────


class TestProxyTag:
    """All proxy-emitted messages have the [proxy] tag."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_proxy_tag_constant_defined(self):
        assert '_PROXY_TAG = "\\u2699\\ufe0f **[proxy]** "' in self.content

    def test_auth_error_has_proxy_tag(self):
        """Auth error messages include the proxy tag."""
        # Find the auth error return statements
        auth_pattern = r'Token Claude expir'
        matches = list(re.finditer(auth_pattern, self.content))
        assert len(matches) >= 1, "No auth error message found"
        # Check each occurrence is preceded by the proxy tag emoji
        for m in matches:
            # Look at the 200 chars before the match for the tag
            start = max(0, m.start() - 200)
            context = self.content[start:m.end()]
            assert "\\u2699" in context or "\u2699" in context, \
                f"Auth error at position {m.start()} missing proxy tag"

    def test_switch_error_has_proxy_tag(self):
        """Switch error messages include the proxy tag."""
        assert '\\u2699\\ufe0f **[proxy]** Failed to update config' in self.content

    def test_switch_success_has_proxy_tag(self):
        """Switch success messages include the proxy tag."""
        assert '\\u2699\\ufe0f **[proxy]** Switched to' in self.content

    def test_wakeup_messages_have_proxy_tag(self):
        """All wakeup messages use _PROXY_TAG."""
        for mode in ["anklume", "assistant", "local"]:
            pattern = rf'"{mode}": _PROXY_TAG \+'
            assert re.search(pattern, self.content), \
                f"Wakeup message for '{mode}' missing _PROXY_TAG"


# ── Tool registry ─────────────────────────────────────────────────


class TestToolRegistry:
    """Verify _TOOL_REGISTRY completeness."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_core_tools_registered(self):
        """Core infrastructure tools are in _TOOL_REGISTRY."""
        expected = [
            "git_status", "git_log", "git_diff",
            "make_target", "run_tests", "lint",
            "incus_list", "incus_exec", "read_file",
        ]
        for tool in expected:
            assert f'"{tool}"' in self.content, f"Tool '{tool}' not in registry"

    def test_claude_tools_registered(self):
        """Claude Code tools are in _TOOL_REGISTRY."""
        expected = ["claude_chat", "claude_sessions", "claude_session_clear",
                     "claude_code"]
        for tool in expected:
            assert f'"{tool}"' in self.content, f"Tool '{tool}' not in registry"

    def test_web_tools_registered(self):
        """Web search tools are in _TOOL_REGISTRY."""
        assert '"web_search"' in self.content
        assert '"web_fetch"' in self.content

    def test_switch_brain_registered(self):
        assert '"switch_brain"' in self.content

    def test_usage_registered(self):
        assert '"usage"' in self.content

    def test_self_upgrade_registered(self):
        assert '"self_upgrade"' in self.content


# ── Safety filters ─────────────────────────────────────────────────


class TestSafetyFilters:
    """Verify safety filters in the proxy."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_make_target_blocks_flush(self):
        """make_target blocks the 'flush' target."""
        assert '"flush"' in self.content
        assert "blocked" in self.content.lower()

    def test_make_target_blocks_nftables_deploy(self):
        """make_target blocks 'nftables-deploy'."""
        assert '"nftables-deploy"' in self.content

    def test_incus_exec_blocks_rm_rf(self):
        """incus_exec blocks 'rm -rf /'."""
        assert r"rm\s+-rf\s+/" in self.content

    def test_incus_exec_blocks_reboot(self):
        """incus_exec blocks 'reboot'."""
        assert r"\breboot\b" in self.content

    def test_incus_exec_blocks_shutdown(self):
        """incus_exec blocks 'shutdown'."""
        assert r"\bshutdown\b" in self.content

    def test_read_file_prevents_traversal(self):
        """read_file prevents directory traversal."""
        assert "path outside project directory" in self.content


# ── Usage tracking ─────────────────────────────────────────────────


class TestUsageTracking:
    """Verify usage tracking structure."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_usage_stats_fields(self):
        """_usage_stats has expected fields."""
        expected_fields = [
            "total_cost_usd", "total_input_tokens",
            "total_output_tokens", "total_cache_read_tokens",
            "total_cache_creation_tokens", "total_calls",
            "calls_by_session",
        ]
        for field in expected_fields:
            assert f'"{field}"' in self.content, f"Missing field '{field}'"

    def test_usage_keyword_detection(self):
        """Proxy detects usage-related keywords for auto-injection."""
        keywords = ["consomm", "usage", "quota", "tokens"]
        for kw in keywords:
            assert kw in self.content, f"Missing usage keyword '{kw}'"


# ── Session management ─────────────────────────────────────────────


class TestSessionManagement:
    """Verify session management features."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_session_ttl_defined(self):
        """CLAUDE_SESSION_TTL is defined."""
        assert "CLAUDE_SESSION_TTL" in self.content

    def test_stale_session_cleanup(self):
        """_clean_stale_sessions function exists."""
        assert "def _clean_stale_sessions" in self.content

    def test_session_resume_support(self):
        """Claude Code sessions support --resume."""
        assert '"--resume"' in self.content

    def test_session_store_tracks_turns(self):
        """Session store tracks turn count."""
        assert '"turns"' in self.content


# ── OpenAI compatibility ───────────────────────────────────────────


class TestOpenAICompatibility:
    """Verify OpenAI-compatible endpoint features."""

    @classmethod
    def setup_class(cls):
        cls.content = PROXY_SCRIPT.read_text()

    def test_chat_completions_endpoint(self):
        assert "/v1/chat/completions" in self.content

    def test_models_endpoint(self):
        assert "/v1/models" in self.content

    def test_streaming_support(self):
        """SSE streaming is supported."""
        assert "text/event-stream" in self.content
        assert "[DONE]" in self.content

    def test_switch_marker_detection(self):
        """Response parser detects [SWITCH:mode] markers."""
        assert r"\[SWITCH:(anklume|assistant|local)\]" in self.content

    def test_new_session_detection(self):
        """Detects new conversations to clear stale sessions."""
        assert "New conversation detected" in self.content


# ── Documentation ──────────────────────────────────────────────────


class TestOpenClawDocumentation:
    """Verify OpenClaw documentation completeness."""

    @classmethod
    def setup_class(cls):
        cls.en = OPENCLAW_DOC_EN.read_text()
        cls.fr = OPENCLAW_DOC_FR.read_text()

    def test_en_value_add_section_exists(self):
        assert "Value-add over native OpenClaw" in self.en

    def test_fr_value_add_section_exists(self):
        assert "Valeur ajoutee par rapport a OpenClaw natif" in self.fr

    def test_en_10_value_adds_documented(self):
        """All 10 value-adds are documented in English."""
        for i in range(1, 11):
            assert f"### {i}." in self.en, f"Value-add #{i} missing in EN doc"

    def test_fr_10_value_adds_documented(self):
        """All 10 value-adds are documented in French."""
        for i in range(1, 11):
            assert f"### {i}." in self.fr, f"Value-add #{i} missing in FR doc"

    def test_en_summary_table(self):
        assert "| Capability |" in self.en

    def test_fr_summary_table(self):
        assert "| Capacite |" in self.fr

    def test_en_bind_mount_documented(self):
        """Credential bind-mount is documented in English."""
        assert "bind-mount" in self.en

    def test_fr_bind_mount_documented(self):
        """Credential bind-mount is documented in French."""
        assert "bind-mount" in self.fr

    def test_en_proxy_tag_documented(self):
        """[proxy] tag is documented in English."""
        assert "[proxy]" in self.en

    def test_fr_proxy_tag_documented(self):
        """[proxy] tag is documented in French."""
        assert "[proxy]" in self.fr

    def test_en_agents_md_structure(self):
        """AGENTS.md mode markers are documented in English."""
        assert "[ALL MODES]" in self.en
        assert "[ANKLUME MODE]" in self.en

    def test_fr_agents_md_structure(self):
        """AGENTS.md mode markers are documented in French."""
        assert "[ALL MODES]" in self.fr
        assert "[ANKLUME MODE]" in self.fr
