"""Tests for anklume instance list — Rich table monitoring."""

import json
from unittest.mock import MagicMock, patch

import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner  # noqa: E402

from scripts.cli.instance import app  # noqa: E402

runner = CliRunner()

SAMPLE_INSTANCES = [
    {
        "name": "pro-dev",
        "type": "container",
        "status": "Running",
        "project": "pro",
        "state": {
            "cpu": {"usage": 5_000_000_000},
            "memory": {"usage": 536_870_912},
            "disk": {"root": {"usage": 2_147_483_648}},
            "network": {
                "eth0": {
                    "addresses": [
                        {"family": "inet", "address": "10.120.0.1", "scope": "global"},
                    ],
                },
            },
        },
        "expanded_devices": {
            "root": {"type": "disk"},
        },
    },
    {
        "name": "ai-gpu",
        "type": "container",
        "status": "Stopped",
        "project": "ai-tools",
        "state": {
            "cpu": {"usage": 0},
            "memory": {"usage": 0},
            "disk": {},
            "network": {},
        },
        "expanded_devices": {
            "root": {"type": "disk"},
            "gpu0": {"type": "gpu"},
        },
    },
]

SAMPLE_INFRA = {
    "domains": {
        "pro": {
            "trust_level": "trusted",
            "machines": {"pro-dev": {"type": "lxc"}},
        },
        "ai-tools": {
            "trust_level": "semi-trusted",
            "machines": {"ai-gpu": {"type": "lxc", "gpu": True}},
        },
    },
}


def _mock_run_cmd(args, *, capture=False, check=True, cwd=None):
    if capture and "incus" in args:
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = json.dumps(SAMPLE_INSTANCES)
        return mock
    return MagicMock(returncode=0)


class TestInstanceList:
    @patch("scripts.cli._instance_list.load_infra_safe", return_value=SAMPLE_INFRA)
    @patch("scripts.cli._instance_list.run_cmd", side_effect=_mock_run_cmd)
    def test_list_shows_table(self, mock_run, mock_infra):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        # Rich may truncate in narrow terminals: "pro-d…" or "pro-dev"
        assert "pro" in result.output
        assert "ai-gpu" in result.output or "ai-g" in result.output

    @patch("scripts.cli._instance_list.load_infra_safe", return_value=SAMPLE_INFRA)
    @patch("scripts.cli._instance_list.run_cmd", side_effect=_mock_run_cmd)
    def test_list_filter_domain(self, mock_run, mock_infra):
        result = runner.invoke(app, ["list", "--domain", "pro"])
        assert result.exit_code == 0
        assert "pro" in result.output
        # ai-gpu should be filtered out (no "ai-" prefix present)
        assert "ai-gpu" not in result.output and "ai-g" not in result.output

    @patch("scripts.cli._instance_list.load_infra_safe", return_value=SAMPLE_INFRA)
    @patch("scripts.cli._instance_list.run_cmd", side_effect=_mock_run_cmd)
    def test_list_sort_memory(self, mock_run, mock_infra):
        result = runner.invoke(app, ["list", "--sort", "memory"])
        assert result.exit_code == 0
        # pro-dev has memory=512M, ai-gpu has 0 → pro should appear first
        # Filter data rows (start with │) containing instance names
        lines = result.output.splitlines()
        data_lines = [line for line in lines if line.startswith("│") and ("pro" in line or "ai" in line)]
        assert len(data_lines) == 2
        assert "pro" in data_lines[0]

    @patch("scripts.cli._instance_list.load_infra_safe", return_value=SAMPLE_INFRA)
    @patch("scripts.cli._instance_list.run_cmd", side_effect=_mock_run_cmd)
    def test_list_shows_gpu(self, mock_run, mock_infra):
        result = runner.invoke(app, ["list"])
        assert "yes" in result.output  # GPU column for ai-gpu

    @patch("scripts.cli._instance_list.load_infra_safe", return_value=SAMPLE_INFRA)
    @patch("scripts.cli._instance_list.run_cmd", side_effect=_mock_run_cmd)
    def test_list_shows_ip(self, mock_run, mock_infra):
        result = runner.invoke(app, ["list"])
        # Rich may truncate IP: "10.1…" or full "10.120.0.1"
        assert "10.1" in result.output

    @patch("scripts.cli._instance_list.run_cmd")
    def test_list_empty(self, mock_run):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "[]"
        mock_run.return_value = mock
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No instances" in result.output


class TestFormatBytes:
    def test_bytes(self):
        from scripts.cli._helpers import format_bytes
        assert format_bytes(500) == "500B"

    def test_kib(self):
        from scripts.cli._helpers import format_bytes
        assert format_bytes(2048) == "2KiB"

    def test_mib(self):
        from scripts.cli._helpers import format_bytes
        assert format_bytes(536_870_912) == "512.0MiB"

    def test_gib(self):
        from scripts.cli._helpers import format_bytes
        assert format_bytes(2_147_483_648) == "2.0GiB"
