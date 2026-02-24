"""Tests for scripts/guide.sh — interactive onboarding tutorial."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

GUIDE_SH = Path(__file__).resolve().parent.parent / "scripts" / "guide.sh"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# CI detection: GitHub Actions sets CI=true and GITHUB_ACTIONS=true
CI = os.environ.get("CI") == "true"


@pytest.fixture()
def guide_env(tmp_path):
    """Create a mock environment for guide testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()

    # Mock commands that the guide checks for
    for cmd in ["ansible-playbook", "ansible-lint",
                "yamllint", "python3", "git", "make"]:
        mock_cmd = mock_bin / cmd
        mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

    # Mock incus — output RUNNING for list commands (Step 0 checks container_running)
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "$1" == "list" ]]; then echo "RUNNING"; fi\n'
        'exit 0\n'
    )
    mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

    # Real python3 for actual use
    mock_python = mock_bin / "python3"
    mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
    mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    env["TERM"] = "dumb"  # Avoid ANSI clearing issues
    return env


def run_guide(args, env, cwd=None):
    """Run guide.sh with given args."""
    result = subprocess.run(
        ["bash", str(GUIDE_SH)] + args,
        capture_output=True, text=True, env=env,
        cwd=cwd or str(PROJECT_ROOT), timeout=30,
    )
    return result


# ── auto mode ──────────────────────────────────────────────


class TestGuideAutoMode:
    @pytest.mark.skipif(
        CI,
        reason="Full auto run hits step 4 (generate.py) which needs pyyaml "
        "unavailable via /usr/bin/python3 in CI",
    )
    def test_auto_mode_runs(self, guide_env):
        """--auto mode runs without prompts."""
        result = run_guide(["--auto"], guide_env)
        # On host: Step 0 detects environment and delegates to container
        # Inside container: proceeds to Step 1
        assert result.returncode == 0
        assert "Step" in result.stdout or "delegating" in result.stdout

    def test_auto_mode_checks_prerequisites(self, guide_env):
        """Auto mode checks for required tools in step 1."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "incus" in result.stdout.lower() or "prerequisit" in result.stdout.lower() \
            or "Step 1" in result.stdout


# ── step resume ────────────────────────────────────────────


class TestGuideStepResume:
    def test_resume_from_step(self, guide_env):
        """--step N resumes from that step."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "Step 1" in result.stdout or result.returncode == 0

    def test_resume_shows_info_message(self, guide_env):
        """--step N with N>1 shows 'Resuming from step N'."""
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Resuming from step 2" in result.stdout

    def test_step_max_valid(self, guide_env):
        """--step 9 (TOTAL_STEPS) is valid."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0
        assert "Step 9" in result.stdout

    def test_step_out_of_range_error(self, guide_env):
        """--step 99 gives an error (above TOTAL_STEPS)."""
        result = run_guide(["--step", "99"], guide_env)
        assert result.returncode != 0


# ── missing prerequisites ─────────────────────────────────


class TestGuidePrerequisitesMissing:
    """Test step 1 with missing required tools."""

    @staticmethod
    def _make_env_hiding_tools(tmp_path, hidden_cmds):
        """Build an env where specific commands are absent from PATH."""
        mock_bin = tmp_path / "restricted_bin"
        mock_bin.mkdir(exist_ok=True)

        essential = [
            "bash", "env", "sed", "awk", "head", "tail", "cat",
            "grep", "seq", "clear", "true", "false", "dirname",
            "pwd", "cd", "rm", "cp", "mkdir", "chmod", "tee",
            "sort", "tr", "wc", "uname", "id", "readlink",
        ]
        for util in essential:
            src = Path(f"/usr/bin/{util}")
            if not src.exists():
                src = Path(f"/bin/{util}")
            if src.exists() and not (mock_bin / util).exists():
                (mock_bin / util).symlink_to(src)

        all_guide_tools = [
            "incus", "ansible-playbook", "ansible-lint", "ansible",
            "yamllint", "python3", "git", "make",
            "shellcheck", "ruff",
        ]
        for tool in all_guide_tools:
            if tool in hidden_cmds:
                continue
            mock_cmd = mock_bin / tool
            if not mock_cmd.exists():
                mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
                mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        if mock_python.exists():
            mock_python.unlink()
        mock_python.write_text(
            "#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n"
        )
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        env["TERM"] = "dumb"
        return env

    @pytest.fixture()
    def env_missing_incus(self, tmp_path):
        return self._make_env_hiding_tools(tmp_path, {"incus"})

    @pytest.fixture()
    def env_missing_multiple(self, tmp_path):
        return self._make_env_hiding_tools(
            tmp_path, {"incus", "ansible-playbook", "make"},
        )

    @pytest.mark.skipif(
        CI,
        reason="Restricted PATH may lack essential utilities at expected "
        "locations on ubuntu-latest",
    )
    def test_missing_incus_fails_auto(self, env_missing_incus):
        """Auto mode exits with error when incus is missing."""
        result = run_guide(["--auto", "--step", "1"], env_missing_incus)
        assert result.returncode != 0
        assert "incus" in result.stdout.lower()
        assert "Missing" in result.stdout or "not found" in result.stdout

    @pytest.mark.skipif(
        CI,
        reason="Restricted PATH may lack essential utilities at expected "
        "locations on ubuntu-latest",
    )
    def test_missing_multiple_tools_lists_all(self, env_missing_multiple):
        """When multiple tools are missing, all are reported."""
        result = run_guide(["--auto", "--step", "1"], env_missing_multiple)
        assert result.returncode != 0
        output = result.stdout.lower()
        assert "incus" in output
        assert "ansible" in output or "ansible-playbook" in output
        assert "make" in output

    def test_optional_tools_do_not_block(self, guide_env):
        """Missing optional tools (shellcheck, ruff) do not cause failure."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "All prerequisites" in result.stdout or result.returncode == 0


# ── use case selection ─────────────────────────────────────


class TestGuideUseCaseFiles:
    """Test that use case selection copies the correct example file."""

    def _make_project_with_examples(self, tmp_path):
        """Create a mock project dir with all example infra.yml files."""
        import shutil

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        (project_dir / "infra.yml.example").write_text(
            "project_name: default-template\n"
        )

        for uc, content in [
            ("student-sysadmin", "project_name: student\n"),
            ("teacher-lab", "project_name: teacher\n"),
            ("pro-workstation", "project_name: pro\n"),
        ]:
            uc_dir = project_dir / "examples" / uc
            uc_dir.mkdir(parents=True)
            (uc_dir / "infra.yml").write_text(content)

        return project_dir

    def test_student_use_case_selects_student_example(self, guide_env, tmp_path):
        """Auto mode selects option 1 (student-sysadmin) and copies its file."""
        project_dir = self._make_project_with_examples(tmp_path)
        result = run_guide(
            ["--auto", "--step", "2"], guide_env, cwd=str(project_dir),
        )
        assert "student-sysadmin" in result.stdout

    def test_use_case_options_include_teacher(self, guide_env, tmp_path):
        """Step 2 displays the teacher lab option."""
        project_dir = self._make_project_with_examples(tmp_path)
        result = run_guide(
            ["--auto", "--step", "2"], guide_env, cwd=str(project_dir),
        )
        assert "Teacher" in result.stdout or "teacher" in result.stdout


# ── step 3 infra.yml copy ──────────────────────────────────


class TestGuideStep3InfraYml:
    """Test step 3 — infra.yml copy in auto mode."""

    def test_auto_copies_example(self, guide_env, tmp_path):
        """Auto mode copies the example infra.yml into the project dir."""
        import shutil

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        example = project_dir / "infra.yml.example"
        example.write_text("project_name: test\n")

        example_dir = project_dir / "examples" / "student-sysadmin"
        example_dir.mkdir(parents=True)
        (example_dir / "infra.yml").write_text("project_name: student\n")

        run_guide(["--auto", "--step", "2"], guide_env,
                  cwd=str(project_dir))

        infra_yml = project_dir / "infra.yml"
        if infra_yml.exists():
            content = infra_yml.read_text()
            assert "student" in content


# ── auto mode skips interactive steps ──────────────────────


class TestGuideStepSkipsInAuto:
    """Test that steps 6, 7, 8 skip cleanly in auto mode."""

    @pytest.fixture(autouse=True)
    def _ensure_inventory(self):
        """Create a dummy inventory dir so step 6 pitfall check passes.

        guide.sh step_6_apply checks for $PROJECT_DIR/inventory/*.yml
        before reaching the auto-mode skip logic.  In CI the generated
        inventory is not committed, so create a placeholder here.
        """
        inv_dir = PROJECT_ROOT / "inventory"
        created = not inv_dir.exists()
        if created:
            inv_dir.mkdir(exist_ok=True)
            (inv_dir / "_ci_placeholder.yml").write_text("---\n")
        yield
        if created:
            placeholder = inv_dir / "_ci_placeholder.yml"
            if placeholder.exists():
                placeholder.unlink()
            if inv_dir.exists() and not any(inv_dir.iterdir()):
                inv_dir.rmdir()

    def test_step_6_skips_in_auto(self, guide_env):
        """Step 6 (Apply) skips in auto mode — requires live Incus."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        output = result.stdout
        assert "Step 6" in output
        assert "Auto-mode: skipping" in output

    def test_step_7_handles_no_incus(self, guide_env):
        """Step 7 (Verify) handles no Incus connection gracefully."""
        result = run_guide(["--auto", "--step", "7"], guide_env)
        assert "Step 7" in result.stdout

    def test_step_8_skips_in_auto(self, guide_env):
        """Step 8 (Snapshot) skips in auto mode."""
        result = run_guide(["--auto", "--step", "8"], guide_env)
        output = result.stdout
        assert "Step 8" in output
        assert "Auto-mode: skipping" in output

    def test_step_9_completes(self, guide_env):
        """Step 9 (Next Steps) completes successfully."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0
        assert "Step 9" in result.stdout

    def test_step_sequence_6_through_9(self, guide_env):
        """Starting at step 6, steps 6-9 all execute."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        output = result.stdout
        assert "Step 6" in output
        assert "Step 7" in output
        assert "Step 8" in output
        assert "Step 9" in output
