"""Tests for the educational lab framework (Phase 30).

Validates lab.yml format, step structure, lab-runner CLI arguments,
and progress tracking.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LABS_DIR = PROJECT_ROOT / "labs"
LAB_RUNNER = PROJECT_ROOT / "scripts" / "lab-runner.sh"
SCHEMA_FILE = LABS_DIR / "lab-schema.yml"

VALID_DIFFICULTIES = {"beginner", "intermediate", "advanced"}
DURATION_PATTERN = re.compile(r"^[0-9]+[mh]$")
STEP_ID_PATTERN = re.compile(r"^[0-9]{2}$")


def load_schema():
    """Load the lab schema for validation."""
    with open(SCHEMA_FILE) as f:
        return yaml.safe_load(f)


def discover_labs():
    """Return list of (lab_dir, lab_yml_data) tuples."""
    labs = []
    for lab_dir in sorted(LABS_DIR.iterdir()):
        if lab_dir.is_dir() and (lab_dir / "lab.yml").exists():
            with open(lab_dir / "lab.yml") as f:
                data = yaml.safe_load(f)
            labs.append((lab_dir, data))
    return labs


# ── ED-001: lab.yml schema validation ───────────────────


class TestLabYmlSchema:
    """Matrix: ED-001 — Validate lab.yml files against schema."""

    def test_schema_file_exists(self):
        # Matrix: ED-001
        assert SCHEMA_FILE.exists(), "lab-schema.yml must exist"

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_required_fields_present(self, lab_dir, data):
        # Matrix: ED-001
        schema = load_schema()
        for field in schema["required_fields"]:
            assert field in data, (
                f"{lab_dir.name}/lab.yml missing required field: {field}"
            )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_difficulty_is_valid_enum(self, lab_dir, data):
        # Matrix: ED-001
        assert data["difficulty"] in VALID_DIFFICULTIES, (
            f"{lab_dir.name}: difficulty must be one of {VALID_DIFFICULTIES}"
        )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_duration_format(self, lab_dir, data):
        # Matrix: ED-001
        assert DURATION_PATTERN.match(data["duration"]), (
            f"{lab_dir.name}: duration must match pattern (e.g., 30m, 1h)"
        )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_objectives_is_nonempty_list(self, lab_dir, data):
        # Matrix: ED-001
        assert isinstance(data["objectives"], list), "objectives must be a list"
        assert len(data["objectives"]) > 0, "objectives must not be empty"


# ── ED-002: step structure validation ────────────────────


class TestStepStructure:
    """Matrix: ED-002 — Validate step definitions and files."""

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_steps_have_required_fields(self, lab_dir, data):
        # Matrix: ED-002
        for step in data["steps"]:
            assert "id" in step, f"{lab_dir.name}: step missing 'id'"
            assert "title" in step, f"{lab_dir.name}: step missing 'title'"
            assert "instruction_file" in step, (
                f"{lab_dir.name}: step missing 'instruction_file'"
            )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_step_ids_are_valid(self, lab_dir, data):
        # Matrix: ED-002
        for step in data["steps"]:
            assert STEP_ID_PATTERN.match(step["id"]), (
                f"{lab_dir.name}: step id '{step['id']}' must be 2-digit"
            )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_step_instruction_files_exist(self, lab_dir, data):
        # Matrix: ED-002
        for step in data["steps"]:
            fpath = lab_dir / step["instruction_file"]
            assert fpath.exists(), (
                f"{lab_dir.name}: instruction file '{step['instruction_file']}' "
                f"does not exist"
            )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_step_ids_are_sequential(self, lab_dir, data):
        # Matrix: ED-002
        ids = [int(s["id"]) for s in data["steps"]]
        expected = list(range(1, len(ids) + 1))
        assert ids == expected, (
            f"{lab_dir.name}: step IDs must be sequential starting at 01"
        )


# ── ED-003: lab-runner CLI argument parsing ──────────────


@pytest.fixture()
def lab_runner_env(tmp_path):
    """Create a mock environment for lab-runner testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()

    # Mock python3 to use real python
    mock_py = mock_bin / "python3"
    mock_py.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_py.chmod(mock_py.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["HOME"] = str(tmp_path / "home")
    os.makedirs(env["HOME"], exist_ok=True)
    return env


class TestLabRunnerCli:
    """Matrix: ED-003 — Lab-runner CLI argument parsing."""

    def test_list_command_succeeds(self, lab_runner_env):
        # Matrix: ED-003
        result = subprocess.run(
            ["bash", str(LAB_RUNNER), "list"],
            capture_output=True, text=True,
            env=lab_runner_env, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "Available Labs" in result.stdout

    def test_list_shows_all_labs(self, lab_runner_env):
        # Matrix: ED-003
        result = subprocess.run(
            ["bash", str(LAB_RUNNER), "list"],
            capture_output=True, text=True,
            env=lab_runner_env, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert "First Deployment" in result.stdout
        assert "Network Isolation" in result.stdout
        assert "Snapshots" in result.stdout

    def test_unknown_command_fails(self, lab_runner_env):
        # Matrix: ED-003
        result = subprocess.run(
            ["bash", str(LAB_RUNNER), "bogus"],
            capture_output=True, text=True,
            env=lab_runner_env, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0

    def test_start_without_lab_num_fails(self, lab_runner_env):
        # Matrix: ED-003
        result = subprocess.run(
            ["bash", str(LAB_RUNNER), "start"],
            capture_output=True, text=True,
            env=lab_runner_env, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0
        assert "Lab number required" in result.stderr

    def test_start_nonexistent_lab_fails(self, lab_runner_env):
        # Matrix: ED-003
        result = subprocess.run(
            ["bash", str(LAB_RUNNER), "start", "L=99"],
            capture_output=True, text=True,
            env=lab_runner_env, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode != 0
        assert "not found" in result.stderr


# ── ED-004: lab infra.yml validity ───────────────────────


class TestLabInfraYml:
    """Matrix: ED-004 — Lab infra.yml files are valid PSOT definitions."""

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_infra_yml_exists(self, lab_dir, data):
        # Matrix: ED-004
        infra = lab_dir / "infra.yml"
        assert infra.exists(), f"{lab_dir.name} must have infra.yml"

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_infra_yml_has_required_keys(self, lab_dir, data):
        # Matrix: ED-004
        with open(lab_dir / "infra.yml") as f:
            infra = yaml.safe_load(f)
        assert "project_name" in infra
        assert "domains" in infra
        assert isinstance(infra["domains"], dict)
        assert len(infra["domains"]) > 0

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_infra_yml_has_addressing(self, lab_dir, data):
        # Matrix: ED-004
        with open(lab_dir / "infra.yml") as f:
            infra = yaml.safe_load(f)
        g = infra.get("global", {})
        addr = g.get("addressing", {})
        assert addr.get("base_octet") == 10


# ── ED-005: solution files exist ─────────────────────────


class TestSolutionFiles:
    """Matrix: ED-005 — Each lab has a solution directory."""

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_solution_commands_exist(self, lab_dir, data):
        # Matrix: ED-005
        solution = lab_dir / "solution" / "commands.sh"
        assert solution.exists(), (
            f"{lab_dir.name} must have solution/commands.sh"
        )

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_solution_is_shell_script(self, lab_dir, data):
        # Matrix: ED-005
        solution = lab_dir / "solution" / "commands.sh"
        content = solution.read_text()
        assert content.startswith("#!/usr/bin/env bash"), (
            f"{lab_dir.name}/solution/commands.sh must have bash shebang"
        )


# ── Shell script quality ─────────────────────────────────


@pytest.mark.skipif(
    shutil.which("shellcheck") is None,
    reason="shellcheck not installed",
)
class TestShellQuality:
    """Validate lab shell scripts pass shellcheck."""

    def test_lab_runner_shellcheck(self):
        result = subprocess.run(
            ["shellcheck", "--severity=warning",
             str(LAB_RUNNER),
             str(PROJECT_ROOT / "scripts" / "lab-lib.sh")],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stderr}"

    @pytest.mark.parametrize(
        "lab_dir,data",
        discover_labs(),
        ids=[d.name for d, _ in discover_labs()],
    )
    def test_solution_scripts_shellcheck(self, lab_dir, data):
        solution = lab_dir / "solution" / "commands.sh"
        if solution.exists():
            result = subprocess.run(
                ["shellcheck", "--severity=warning", str(solution)],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, (
                f"shellcheck errors in {lab_dir.name}:\n{result.stderr}"
            )
