"""Tests for host resource rendering (tmux, dashboard, helpers)."""


class TestFormatting:
    """Test formatting helpers."""

    def test_fmt_mib_gib(self):
        from scripts.host_resources_render import _fmt_mib

        assert "GiB" in _fmt_mib(2048)

    def test_fmt_mib_mib(self):
        from scripts.host_resources_render import _fmt_mib

        assert "MiB" in _fmt_mib(500)

    def test_bar_length(self):
        from scripts.host_resources_render import _bar

        bar = _bar(50)
        assert len(bar) == 8

    def test_bar_empty(self):
        from scripts.host_resources_render import _bar

        bar = _bar(0)
        assert "\u2588" not in bar  # no filled blocks

    def test_bar_full(self):
        from scripts.host_resources_render import _bar

        bar = _bar(100)
        assert "\u2591" not in bar  # no empty blocks

    def test_bar_none(self):
        from scripts.host_resources_render import _bar

        bar = _bar(None)
        assert len(bar) == 8

    def test_render_tmux(self, capsys):
        from scripts.host_resources_render import render_tmux

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
        from scripts.host_resources_render import render_tmux

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
        from scripts.host_resources_render import render_dashboard_data

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
        from scripts.host_resources_render import render_dashboard_data

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
