"""Tests for host resource monitoring."""

import json
from unittest.mock import MagicMock, patch


class TestCollectCPU:
    """Test CPU collection from /proc/stat."""

    def test_returns_float(self):
        from scripts.host_resources import collect_cpu

        result = collect_cpu()
        if result is not None:
            assert isinstance(result, float)
            assert 0 <= result <= 100

    def test_cpu_count(self):
        from scripts.host_resources import collect_cpu_count

        count = collect_cpu_count()
        assert isinstance(count, int)
        assert count > 0


class TestCollectMemory:
    """Test RAM collection from /proc/meminfo."""

    def test_returns_dict(self):
        from scripts.host_resources import collect_memory

        result = collect_memory()
        if result is not None:
            assert "total" in result
            assert "used" in result
            assert "percent" in result
            assert result["total"] > 0
            assert 0 <= result["percent"] <= 100

    def test_used_less_than_total(self):
        from scripts.host_resources import collect_memory

        result = collect_memory()
        if result is not None:
            assert result["used"] <= result["total"]


class TestCollectDisk:
    """Test disk collection via os.statvfs."""

    def test_returns_dict(self):
        from scripts.host_resources import collect_disk

        result = collect_disk("/")
        assert result is not None
        assert "total" in result
        assert "used" in result
        assert "free" in result
        assert "percent" in result
        assert result["total"] > 0

    def test_used_plus_free_approx_total(self):
        from scripts.host_resources import collect_disk

        result = collect_disk("/")
        if result is not None:
            # used + free should be approximately total
            assert result["used"] + result["free"] <= result["total"] * 1.01

    def test_invalid_path_returns_none(self):
        from scripts.host_resources import collect_disk

        result = collect_disk("/nonexistent/path/that/doesnt/exist")
        assert result is None


class TestCollectGPU:
    """Test GPU collection with mocked incus exec."""

    def test_returns_none_without_gpu(self):
        from scripts.host_resources import collect_gpu

        with patch("scripts.host_resources.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            result = collect_gpu()
            assert result is None

    def test_returns_none_on_nonzero_exit(self):
        from scripts.host_resources import collect_gpu

        with patch("scripts.host_resources.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = collect_gpu()
            assert result is None

    def test_parses_nvidia_smi_output(self):
        from scripts.host_resources import collect_gpu

        with patch("scripts.host_resources.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="RTX PRO 5000, 21000, 24000, 3000, 62, 35\n",
            )
            result = collect_gpu()
            assert result is not None
            assert result["name"] == "RTX PRO 5000"
            assert result["vram_used"] == 21000
            assert result["vram_total"] == 24000
            assert result["vram_free"] == 3000
            assert result["temperature"] == 62
            assert result["utilization"] == 35
            assert result["vram_percent"] == round(21000 / 24000 * 100, 1)

    def test_returns_none_on_timeout(self):
        import subprocess

        from scripts.host_resources import collect_gpu

        with patch("scripts.host_resources.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)
            result = collect_gpu()
            assert result is None


class TestCollectOllamaModels:
    """Test Ollama model collection with mocked API."""

    def test_returns_empty_on_failure(self):
        from scripts.host_resources import collect_ollama_models

        with patch("scripts.host_resources.urllib.request.urlopen") as mock:
            mock.side_effect = Exception("connection refused")
            result = collect_ollama_models()
            assert result == []

    def test_parses_api_response(self):
        from scripts.host_resources import collect_ollama_models

        api_data = json.dumps({
            "models": [{
                "name": "qwen2.5-coder:32b",
                "size": 20_000_000_000,
                "size_vram": 19_200_000_000,
                "expires_at": "2026-03-02T12:00:00Z",
            }],
        }).encode()

        with patch("scripts.host_resources.urllib.request.urlopen") as mock:
            mock.return_value.__enter__ = lambda s: MagicMock(read=lambda: api_data)
            mock.return_value.__exit__ = lambda *a: None
            result = collect_ollama_models()
            assert len(result) == 1
            assert result[0]["name"] == "qwen2.5-coder:32b"
            assert result[0]["size_vram"] == 19_200_000_000

    def test_handles_empty_models(self):
        from scripts.host_resources import collect_ollama_models

        api_data = json.dumps({"models": []}).encode()

        with patch("scripts.host_resources.urllib.request.urlopen") as mock:
            mock.return_value.__enter__ = lambda s: MagicMock(read=lambda: api_data)
            mock.return_value.__exit__ = lambda *a: None
            result = collect_ollama_models()
            assert result == []

    def test_vram_percent_calculation(self):
        from scripts.host_resources import collect_ollama_models

        api_data = json.dumps({
            "models": [{
                "name": "test:7b",
                "size": 10_000,
                "size_vram": 8_000,
            }],
        }).encode()

        with patch("scripts.host_resources.urllib.request.urlopen") as mock:
            mock.return_value.__enter__ = lambda s: MagicMock(read=lambda: api_data)
            mock.return_value.__exit__ = lambda *a: None
            result = collect_ollama_models()
            assert result[0]["vram_percent"] == 80.0


class TestCollectAll:
    """Test the aggregate collection."""

    def test_returns_expected_keys(self):
        from scripts.host_resources import collect_all

        with patch("scripts.host_resources.collect_gpu", return_value=None), \
             patch("scripts.host_resources.collect_ollama_models", return_value=[]), \
             patch("scripts.host_resources.collect_ollama_connections", return_value={}):
            result = collect_all()
            assert "cpu_percent" in result
            assert "cpu_count" in result
            assert "memory" in result
            assert "disk" in result
            assert "gpu" in result
            assert "ollama_models" in result
            assert "ollama_connections" in result


class TestFormatting:
    """Test formatting helpers."""

    def test_fmt_bytes_gib(self):
        from scripts.host_resources import _fmt_bytes

        assert "GiB" in _fmt_bytes(2 * 1024 ** 3)

    def test_fmt_bytes_mib(self):
        from scripts.host_resources import _fmt_bytes

        assert "MiB" in _fmt_bytes(500 * 1024 ** 2)

    def test_fmt_bytes_none(self):
        from scripts.host_resources import _fmt_bytes

        assert _fmt_bytes(None) == "N/A"

    def test_fmt_mib_gib(self):
        from scripts.host_resources import _fmt_mib

        assert "GiB" in _fmt_mib(2048)

    def test_fmt_mib_mib(self):
        from scripts.host_resources import _fmt_mib

        assert "MiB" in _fmt_mib(500)

    def test_bar_length(self):
        from scripts.host_resources import _bar

        bar = _bar(50)
        assert len(bar) == 8

    def test_bar_empty(self):
        from scripts.host_resources import _bar

        bar = _bar(0)
        assert "\u2588" not in bar  # no filled blocks

    def test_bar_full(self):
        from scripts.host_resources import _bar

        bar = _bar(100)
        assert "\u2591" not in bar  # no empty blocks

    def test_bar_none(self):
        from scripts.host_resources import _bar

        bar = _bar(None)
        assert len(bar) == 8

    def test_render_tmux(self, capsys):
        from scripts.host_resources import render_tmux

        data = {
            "cpu_percent": 45.0,
            "memory": {"percent": 61.0},
            "gpu": {"vram_percent": 89.0, "temperature": 62},
            "ollama_models": [{"name": "qwen2.5:32b", "size_vram": 19 * 1024 ** 3}],
        }
        render_tmux(data)
        out = capsys.readouterr().out
        assert "CPU:45%" in out
        assert "RAM:61%" in out
        assert "VRAM:89%" in out
        assert "T:62" in out

    def test_render_tmux_no_gpu(self, capsys):
        from scripts.host_resources import render_tmux

        data = {
            "cpu_percent": 30.0,
            "memory": {"percent": 50.0},
            "gpu": None,
            "ollama_models": [],
        }
        render_tmux(data)
        out = capsys.readouterr().out
        assert "CPU:30%" in out
        assert "VRAM" not in out


class TestRenderDashboard:
    """Test HTML dashboard rendering."""

    def test_renders_html(self):
        from scripts.host_resources import render_dashboard_data

        data = {
            "cpu_percent": 45.0,
            "memory": {"percent": 61.0},
            "disk": {"percent": 35.0},
            "gpu": {"vram_percent": 89.0},
            "ollama_models": [{"name": "test:7b", "size_vram": 5 * 1024 ** 3}],
        }
        html = render_dashboard_data(data)
        assert "resource-widget" in html
        assert "CPU" in html
        assert "RAM" in html
        assert "VRAM" in html
        assert "test:7b" in html

    def test_renders_without_gpu(self):
        from scripts.host_resources import render_dashboard_data

        data = {
            "cpu_percent": 30.0,
            "memory": {"percent": 50.0},
            "disk": {"percent": 20.0},
            "gpu": None,
            "ollama_models": [],
        }
        html = render_dashboard_data(data)
        assert "CPU" in html
        assert "VRAM" not in html


class TestCLISystem:
    """Test CLI system commands."""

    def test_resources_command_exists(self):
        from scripts.cli.system import app

        callback_names = [
            cmd.callback.__name__ if cmd.callback else cmd.name
            for cmd in app.registered_commands
        ]
        assert "resources" in callback_names

    def test_system_app_name(self):
        from scripts.cli.system import app

        assert app.info.name == "system"

    def test_system_app_in_main(self):
        from scripts.cli import app

        group_names = []
        for grp in app.registered_groups:
            if grp.typer_instance and grp.typer_instance.info:
                group_names.append(grp.typer_instance.info.name)
        assert "system" in group_names
