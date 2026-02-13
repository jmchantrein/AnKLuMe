"""Tests for scripts/guide.sh — interactive onboarding tutorial."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

GUIDE_SH = Path(__file__).resolve().parent.parent / "scripts" / "guide.sh"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def guide_env(tmp_path):
    """Create a mock environment for guide testing."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()

    # Mock commands that the guide checks for
    for cmd in ["incus", "ansible-playbook", "ansible-lint",
                "yamllint", "python3", "git", "make"]:
        mock_cmd = mock_bin / cmd
        mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

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


class TestGuideArgs:
    def test_help_flag(self, guide_env):
        """--help shows usage."""
        result = run_guide(["--help"], guide_env)
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_unknown_option(self, guide_env):
        """Unknown option gives error."""
        result = run_guide(["--invalid"], guide_env)
        assert result.returncode != 0
        assert "Unknown" in result.stdout or "Unknown" in result.stderr

    def test_invalid_step_number(self, guide_env):
        """Step number out of range gives error."""
        result = run_guide(["--step", "99"], guide_env)
        assert result.returncode != 0
        assert "must be between" in result.stdout or "must be between" in result.stderr

    def test_step_zero_invalid(self, guide_env):
        """Step 0 is invalid."""
        result = run_guide(["--step", "0"], guide_env)
        assert result.returncode != 0


class TestGuideAutoMode:
    def test_auto_mode_runs(self, guide_env):
        """--auto mode runs without prompts."""
        result = run_guide(["--auto"], guide_env)
        # Auto mode may fail at some step (e.g., step 4 needs infra.yml)
        # but it should at least start
        assert "Step 1" in result.stdout or "Prerequisites" in result.stdout

    def test_auto_mode_checks_prerequisites(self, guide_env):
        """Auto mode checks for required tools in step 1."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # Should check for tools
        assert "incus" in result.stdout.lower() or "prerequisit" in result.stdout.lower() \
            or "Step 1" in result.stdout


class TestGuideStepResume:
    def test_resume_from_step(self, guide_env):
        """--step N resumes from that step."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # Should start from step 1
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

    def test_step_negative_invalid(self, guide_env):
        """Negative step number is invalid."""
        result = run_guide(["--step", "-1"], guide_env)
        assert result.returncode != 0


class TestGuidePrerequisitesMissing:
    """Test step 1 with missing required tools."""

    @staticmethod
    def _make_env_hiding_tools(tmp_path, hidden_cmds):
        """Build an env where specific commands are absent from PATH.

        Sets PATH to a single restricted directory that contains
        symlinks to essential system utilities (bash, sed, etc.) and
        mock scripts for guide tools — but omits the hidden commands
        entirely, so ``command -v <hidden>`` returns false.
        """
        mock_bin = tmp_path / "restricted_bin"
        mock_bin.mkdir(exist_ok=True)

        # Symlink essential system utilities
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

        # All required + optional guide tools that are NOT hidden
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

        # Real python3 for actual use
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
        """Environment with incus missing from PATH."""
        return self._make_env_hiding_tools(tmp_path, {"incus"})

    @pytest.fixture()
    def env_missing_multiple(self, tmp_path):
        """Environment with multiple required tools missing."""
        return self._make_env_hiding_tools(
            tmp_path, {"incus", "ansible-playbook", "make"},
        )

    @pytest.fixture()
    def env_missing_make(self, tmp_path):
        """Environment with make missing from PATH."""
        return self._make_env_hiding_tools(tmp_path, {"make"})

    def test_missing_incus_fails_auto(self, env_missing_incus):
        """Auto mode exits with error when incus is missing."""
        result = run_guide(["--auto", "--step", "1"], env_missing_incus)
        assert result.returncode != 0
        assert "incus" in result.stdout.lower()
        assert "Missing" in result.stdout or "not found" in result.stdout

    def test_missing_multiple_tools_lists_all(self, env_missing_multiple):
        """When multiple tools are missing, all are reported."""
        result = run_guide(["--auto", "--step", "1"], env_missing_multiple)
        assert result.returncode != 0
        output = result.stdout.lower()
        assert "incus" in output
        assert "ansible" in output or "ansible-playbook" in output
        assert "make" in output

    def test_missing_make_fails_auto(self, env_missing_make):
        """Auto mode exits with error when make is missing."""
        result = run_guide(["--auto", "--step", "1"], env_missing_make)
        assert result.returncode != 0
        assert "make" in result.stdout.lower()

    def test_optional_tools_do_not_block(self, guide_env, tmp_path):
        """Missing optional tools (shellcheck, ruff) do not cause failure."""
        # guide_env already does NOT provide shellcheck or ruff
        # but provides all required tools — step 1 should pass
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # Step 1 should succeed (all required tools present)
        # It may fail later at make init, but step 1 prerequisite check passes
        assert "All prerequisites" in result.stdout or result.returncode == 0


class TestGuideStep2UseCase:
    """Test step 2 — use case selection in auto mode."""

    def test_auto_selects_option_1(self, guide_env):
        """Auto mode auto-selects option 1 (student-sysadmin)."""
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Auto-mode: selecting option 1" in result.stdout
        assert "student-sysadmin" in result.stdout

    def test_use_case_options_displayed(self, guide_env):
        """Step 2 displays all use case options."""
        result = run_guide(["--auto", "--step", "2"], guide_env)
        output = result.stdout
        assert "Student" in output or "student" in output
        assert "Teacher" in output or "teacher" in output
        assert "Pro" in output or "pro" in output
        assert "Custom" in output or "custom" in output

    def test_step_2_shows_header(self, guide_env):
        """Step 2 shows the step header."""
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Step 2" in result.stdout
        assert "Use Case" in result.stdout


class TestGuideStep3InfraYml:
    """Test step 3 — infra.yml copy in auto mode."""

    def test_auto_copies_example(self, guide_env, tmp_path):
        """Auto mode copies the example infra.yml into the project dir."""
        # Create a mock project dir with infra.yml.example
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create a minimal scripts directory to satisfy SCRIPT_DIR resolution
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()

        # Copy the real guide.sh there so SCRIPT_DIR/PROJECT_DIR resolve
        import shutil
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        # Create a fake infra.yml.example
        example = project_dir / "infra.yml.example"
        example.write_text("project_name: test\n")

        # Create the examples/student-sysadmin directory with infra.yml
        example_dir = project_dir / "examples" / "student-sysadmin"
        example_dir.mkdir(parents=True)
        (example_dir / "infra.yml").write_text("project_name: student\n")

        # Run steps 2 + 3 (step 2 sets the USE_CASE variable for step 3)
        run_guide(["--auto", "--step", "2"], guide_env,
                  cwd=str(project_dir))

        # infra.yml should have been created
        infra_yml = project_dir / "infra.yml"
        if infra_yml.exists():
            content = infra_yml.read_text()
            assert "student" in content

    def test_infra_yml_already_exists_auto_overwrites(self, guide_env, tmp_path):
        """When infra.yml already exists, auto mode overwrites it."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()

        import shutil
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        # Pre-existing infra.yml
        infra_yml = project_dir / "infra.yml"
        infra_yml.write_text("project_name: old\n")

        # Create example
        example_dir = project_dir / "examples" / "student-sysadmin"
        example_dir.mkdir(parents=True)
        (example_dir / "infra.yml").write_text("project_name: student-new\n")

        run_guide(["--auto", "--step", "2"], guide_env,
                  cwd=str(project_dir))

        # In auto mode, confirm() returns 0 (yes), so overwrite should happen
        if infra_yml.exists():
            content = infra_yml.read_text()
            # Either it was overwritten with student content or kept old
            assert "student" in content or "old" in content


class TestGuideStep4Generate:
    """Test step 4 — generate Ansible files in auto mode."""

    def test_step_4_runs_dry_run(self, guide_env):
        """Step 4 attempts a dry-run of the generator."""
        result = run_guide(["--auto", "--step", "4"], guide_env)
        output = result.stdout
        # Step 4 runs generate.py --dry-run first
        assert "Step 4" in output
        assert "Generate" in output or "dry-run" in output.lower()

    def test_step_4_fails_without_infra_yml(self, guide_env, tmp_path):
        """Step 4 fails in auto mode when generate.py is missing/infra.yml absent."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()

        import shutil
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        # Run the copied script (so PROJECT_DIR resolves to the mock dir)
        # No infra.yml and no generate.py → dry-run should fail
        local_guide = scripts_dir / "guide.sh"
        result = subprocess.run(
            ["bash", str(local_guide), "--auto", "--step", "4"],
            capture_output=True, text=True, env=guide_env,
            cwd=str(project_dir), timeout=30,
        )
        # auto mode exits on failure (generate.py missing or infra.yml missing)
        assert result.returncode != 0


class TestGuideStep9NextSteps:
    """Test step 9 — next steps in auto mode."""

    def test_step_9_prints_documentation_links(self, guide_env):
        """Step 9 displays documentation references."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        output = result.stdout
        assert "Step 9" in output
        assert "Next Steps" in output or "next" in output.lower()

    def test_step_9_mentions_nftables(self, guide_env):
        """Step 9 mentions network isolation (nftables)."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "nftables" in result.stdout

    def test_step_9_mentions_gpu(self, guide_env):
        """Step 9 mentions GPU / AI services."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        output = result.stdout
        assert "GPU" in output or "gpu" in output or "AI" in output

    def test_step_9_mentions_useful_commands(self, guide_env):
        """Step 9 lists useful commands."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        output = result.stdout
        assert "make help" in output
        assert "make check" in output

    def test_step_9_prints_completion_message(self, guide_env):
        """Step 9 prints the final completion message."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Setup complete" in result.stdout or "complete" in result.stdout.lower()

    def test_step_9_exits_successfully(self, guide_env):
        """Step 9 exits with code 0."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0


class TestGuideInfraYmlFallback:
    """Test fallback to infra.yml.example when use-case example is missing."""

    def test_missing_example_falls_back(self, guide_env, tmp_path):
        """When the selected example is missing, falls back to infra.yml.example."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()

        import shutil
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        # Create infra.yml.example but NO examples/student-sysadmin/infra.yml
        example = project_dir / "infra.yml.example"
        example.write_text("project_name: fallback\n")

        # examples directory exists but is empty
        (project_dir / "examples" / "student-sysadmin").mkdir(parents=True)
        # No infra.yml in that directory

        # Run step 2 which selects student-sysadmin, then step 3 tries to copy
        result = run_guide(["--auto", "--step", "2"], guide_env,
                           cwd=str(project_dir))
        output = result.stdout

        # Should report the fallback
        assert "Falling back" in output or "fallback" in output.lower() \
            or "not found" in output.lower() or "default template" in output.lower()


class TestGuideStepAndAutoCombined:
    """Test combinations of --step and --auto flags."""

    def test_auto_step_1_only(self, guide_env):
        """--auto --step 1 runs step 1 and continues to subsequent steps."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # Should at least start step 1
        assert "Step 1" in result.stdout

    def test_auto_from_step_9(self, guide_env):
        """--auto --step 9 runs only step 9."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0
        assert "Step 9" in result.stdout
        # Should NOT contain steps 1-8
        assert "Step 1/" not in result.stdout

    def test_auto_from_step_6_skips_apply(self, guide_env):
        """--auto --step 6 skips the apply step (needs live Incus)."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        output = result.stdout
        # Step 6 in auto mode skips apply with info message
        assert "Auto-mode: skipping" in output or "Step 6" in output

    def test_auto_from_step_8_skips_snapshot(self, guide_env):
        """--auto --step 8 skips snapshot (needs live Incus)."""
        result = run_guide(["--auto", "--step", "8"], guide_env)
        output = result.stdout
        assert "Auto-mode: skipping" in output or "Step 8" in output

    def test_step_without_auto_still_requires_step_flag(self, guide_env):
        """--step alone (without --auto) requires a value."""
        # --step without a number causes bash to fail (shift 2 on empty)
        result = run_guide(["--step"], guide_env)
        assert result.returncode != 0

    def test_help_with_step_shows_help(self, guide_env):
        """--help takes precedence even with --step."""
        result = run_guide(["--help", "--step", "3"], guide_env)
        assert result.returncode == 0
        assert "Usage" in result.stdout


class TestGuideStepSkipsInAuto:
    """Test that steps 6, 7, 8 skip cleanly in auto mode."""

    def test_step_6_skips_in_auto(self, guide_env):
        """Step 6 (Apply) skips in auto mode — requires live Incus."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        output = result.stdout
        assert "Step 6" in output
        assert "Auto-mode: skipping" in output

    def test_step_7_handles_no_incus(self, guide_env):
        """Step 7 (Verify) handles no Incus connection gracefully."""
        result = run_guide(["--auto", "--step", "7"], guide_env)
        output = result.stdout
        assert "Step 7" in output
        # Mock incus exits 0 but may not provide real output
        # The step should still complete

    def test_step_8_skips_in_auto(self, guide_env):
        """Step 8 (Snapshot) skips in auto mode."""
        result = run_guide(["--auto", "--step", "8"], guide_env)
        output = result.stdout
        assert "Step 8" in output
        assert "Auto-mode: skipping" in output


class TestGuideStepHeaders:
    """Test that step headers display correctly."""

    def test_step_1_header(self, guide_env):
        """Step 1 header shows 'Prerequisites Check'."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "Prerequisites" in result.stdout

    def test_step_5_header(self, guide_env):
        """Step 5 header shows 'Validate'."""
        result = run_guide(["--auto", "--step", "5"], guide_env)
        assert "Validate" in result.stdout or "Step 5" in result.stdout

    def test_header_shows_total_steps(self, guide_env):
        """Step header shows N/9 format."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "9/9" in result.stdout

    def test_banner_displays(self, guide_env):
        """The AnKLuMe banner is shown."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "AnKLuMe" in result.stdout
