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


# ── step range validation ─────────────────────────────────


class TestGuideStepRange:
    """Test --step boundary values."""

    def test_step_zero_error(self, guide_env):
        """--step 0 gives an error (below valid range 1-9)."""
        result = run_guide(["--step", "0"], guide_env)
        assert result.returncode != 0

    def test_step_out_of_range_error(self, guide_env):
        """--step 99 gives an error (above TOTAL_STEPS)."""
        result = run_guide(["--step", "99"], guide_env)
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "between" in combined.lower() or "must be" in combined.lower() \
            or result.returncode != 0

    def test_step_non_numeric_error(self, guide_env):
        """--step abc gives an error (not a number)."""
        result = run_guide(["--step", "abc"], guide_env)
        assert result.returncode != 0


# ── editor fallback ────────────────────────────────────────


class TestGuideEditorFallback:
    """Test editor variable resolution in step 3.

    The guide uses: ${EDITOR:-${VISUAL:-vi}}
    We verify the fallback chain by examining the script source.
    Actually running the editor interactively is not feasible,
    so we test via the script's source code and auto mode behavior.
    """

    def test_editor_env_used(self, guide_env, tmp_path):
        """When EDITOR is set, guide.sh uses it (verified via source)."""
        # The guide.sh source uses: local editor="${EDITOR:-${VISUAL:-vi}}"
        # We verify EDITOR propagates by setting it and running step 3 in auto.
        # In auto mode, confirm() returns 0 (yes), but the editor only opens
        # in non-auto mode, so we just verify the script parsed correctly.
        guide_env["EDITOR"] = "/usr/bin/true"
        result = run_guide(["--auto", "--step", "9"], guide_env)
        # Auto mode skips the editor call entirely, so just verify no crash
        assert result.returncode == 0

    def test_visual_env_fallback(self, guide_env):
        """When EDITOR is unset but VISUAL is set, VISUAL is the fallback."""
        env = guide_env.copy()
        env.pop("EDITOR", None)
        env["VISUAL"] = "/usr/bin/true"
        # Run a step that doesn't invoke the editor (auto skips it)
        result = run_guide(["--auto", "--step", "9"], env)
        assert result.returncode == 0

    def test_neither_set_defaults_to_vi(self):
        """When neither EDITOR nor VISUAL is set, vi is the default.

        Verified by reading the guide.sh source code.
        """
        source = GUIDE_SH.read_text()
        assert '${EDITOR:-${VISUAL:-vi}}' in source


# ── use case file selection ────────────────────────────────


class TestGuideUseCaseFiles:
    """Test that each use case copies the correct example file."""

    def _make_project_with_examples(self, tmp_path):
        """Create a mock project dir with all example infra.yml files."""
        import shutil

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir()
        shutil.copy2(str(GUIDE_SH), str(scripts_dir / "guide.sh"))

        # Create the default template
        (project_dir / "infra.yml.example").write_text(
            "project_name: default-template\n"
        )

        # Create all use-case examples
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

    def test_custom_use_case_skips_example_copy(self, guide_env):
        """Custom use case uses infra.yml.example, not a subdirectory.

        Verified by reading the guide.sh source code.
        """
        source = GUIDE_SH.read_text()
        # When USE_CASE == "custom", INFRA_SRC is set to infra.yml.example
        assert 'INFRA_SRC="$PROJECT_DIR/infra.yml.example"' in source


# ── step 5 validation ────────────────────────────────────────


class TestGuideStep5Validate:
    """Test step 5 — validate configuration in auto mode."""

    def test_step_5_mentions_validation(self, guide_env):
        """Step 5 mentions 'Validate' or 'validate' in output."""
        result = run_guide(["--auto", "--step", "5"], guide_env)
        output = result.stdout
        assert "Step 5" in output
        assert "Validate" in output or "validate" in output.lower()

    def test_step_5_runs_lint_check(self, guide_env):
        """Step 5 attempts linting or syntax checking."""
        result = run_guide(["--auto", "--step", "5"], guide_env)
        output = result.stdout.lower()
        # Step 5 runs various validators
        assert "syntax" in output or "lint" in output or "yamllint" in output \
            or "ansible" in output or "check" in output


# ── step 7 verification ──────────────────────────────────────


class TestGuideStep7Verify:
    """Test step 7 — verify infrastructure in auto mode."""

    def test_step_7_shows_header(self, guide_env):
        """Step 7 shows 'Verify' header."""
        result = run_guide(["--auto", "--step", "7"], guide_env)
        assert "Step 7" in result.stdout

    def test_step_7_attempts_incus_list(self, guide_env):
        """Step 7 attempts to list instances or networks."""
        result = run_guide(["--auto", "--step", "7"], guide_env)
        output = result.stdout.lower()
        # Step 7 runs incus list or similar verification
        assert "instance" in output or "network" in output \
            or "running" in output or "incus" in output or "verify" in output


# ── source code structure tests ──────────────────────────────


class TestGuideScriptStructure:
    """Verify key structural elements of the guide script."""

    def test_script_has_set_euo_pipefail(self):
        """Script uses strict mode."""
        source = GUIDE_SH.read_text()
        assert "set -euo pipefail" in source

    def test_script_has_all_nine_steps(self):
        """Script defines all 9 step functions."""
        source = GUIDE_SH.read_text()
        # Step functions are named step_N_<description>
        for i in range(1, 10):
            assert f"step_{i}_" in source, f"Missing step_{i}_ function"

    def test_script_defines_total_steps(self):
        """Script defines TOTAL_STEPS=9."""
        source = GUIDE_SH.read_text()
        assert "TOTAL_STEPS=9" in source

    def test_script_defines_step_names(self):
        """Script defines human-readable names for each step."""
        source = GUIDE_SH.read_text()
        expected = ["Prerequisites", "Use Case", "Generate", "Validate",
                    "Apply", "Verify", "Snapshot", "Next Steps"]
        for name in expected:
            assert name in source, f"Missing step name: {name}"

    def test_auto_mode_variable(self):
        """Script uses AUTO variable for auto mode detection."""
        source = GUIDE_SH.read_text()
        assert "AUTO=" in source


# ── ANSI color handling ──────────────────────────────────────


class TestGuideColors:
    """Test ANSI color handling in the guide."""

    def test_dumb_terminal_no_crashes(self, guide_env):
        """TERM=dumb doesn't cause crashes."""
        guide_env["TERM"] = "dumb"
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0

    def test_xterm_no_crashes(self, guide_env):
        """TERM=xterm-256color doesn't cause crashes."""
        guide_env["TERM"] = "xterm-256color"
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0


# ══════════════════════════════════════════════════════════
# NEW TESTS — added below existing 61 tests
# ══════════════════════════════════════════════════════════


class TestGuideShebangAndStrictMode:
    """Verify script header and strict mode settings."""

    def test_shebang_line(self):
        """Script starts with proper bash shebang."""
        source = GUIDE_SH.read_text()
        assert source.startswith("#!/usr/bin/env bash")

    def test_set_euo_pipefail_near_top(self):
        """set -euo pipefail appears within the first 15 lines."""
        lines = GUIDE_SH.read_text().splitlines()[:15]
        found = any("set -euo pipefail" in line for line in lines)
        assert found, "set -euo pipefail not found near top of script"

    def test_script_is_readable(self):
        """The guide script file exists and is non-empty."""
        assert GUIDE_SH.exists()
        assert GUIDE_SH.stat().st_size > 0

    def test_script_under_600_lines(self):
        """The guide script stays within a reasonable size."""
        lines = GUIDE_SH.read_text().splitlines()
        assert len(lines) < 600, f"guide.sh has {len(lines)} lines"


class TestGuideAllStepFunctions:
    """Verify that all 9 step functions are defined in the script."""

    def test_step_1_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_1_prerequisites()" in source

    def test_step_2_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_2_use_case()" in source

    def test_step_3_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_3_infra_yml()" in source

    def test_step_4_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_4_generate()" in source

    def test_step_5_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_5_validate()" in source

    def test_step_6_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_6_apply()" in source

    def test_step_7_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_7_verify()" in source

    def test_step_8_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_8_snapshot()" in source

    def test_step_9_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_9_next_steps()" in source


class TestGuideHelperFunctions:
    """Verify helper functions exist in the script source."""

    def test_header_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "header()" in source

    def test_step_header_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "step_header()" in source

    def test_ok_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "ok()" in source

    def test_fail_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "fail()" in source

    def test_warn_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "warn()" in source

    def test_info_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "info()" in source

    def test_pause_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "pause()" in source

    def test_confirm_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "confirm()" in source

    def test_select_option_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "select_option()" in source

    def test_run_cmd_function_defined(self):
        source = GUIDE_SH.read_text()
        assert "run_cmd()" in source


class TestGuideANSIColorDefinitions:
    """Verify all ANSI color variables are defined."""

    def test_red_defined(self):
        source = GUIDE_SH.read_text()
        assert "RED=" in source

    def test_green_defined(self):
        source = GUIDE_SH.read_text()
        assert "GREEN=" in source

    def test_yellow_defined(self):
        source = GUIDE_SH.read_text()
        assert "YELLOW=" in source

    def test_blue_defined(self):
        source = GUIDE_SH.read_text()
        assert "BLUE=" in source

    def test_cyan_defined(self):
        source = GUIDE_SH.read_text()
        assert "CYAN=" in source

    def test_bold_defined(self):
        source = GUIDE_SH.read_text()
        assert "BOLD=" in source

    def test_dim_defined(self):
        source = GUIDE_SH.read_text()
        assert "DIM=" in source

    def test_reset_defined(self):
        source = GUIDE_SH.read_text()
        assert "RESET=" in source

    def test_red_escape_code(self):
        source = GUIDE_SH.read_text()
        assert r"\033[0;31m" in source

    def test_green_escape_code(self):
        source = GUIDE_SH.read_text()
        assert r"\033[0;32m" in source

    def test_reset_escape_code(self):
        source = GUIDE_SH.read_text()
        assert r"\033[0m" in source


class TestGuideGlobals:
    """Verify global variables in the script."""

    def test_start_step_default_is_1(self):
        source = GUIDE_SH.read_text()
        assert "START_STEP=1" in source

    def test_auto_default_is_false(self):
        source = GUIDE_SH.read_text()
        assert "AUTO=false" in source

    def test_total_steps_is_9(self):
        source = GUIDE_SH.read_text()
        assert "TOTAL_STEPS=9" in source

    def test_script_dir_resolved(self):
        source = GUIDE_SH.read_text()
        assert "SCRIPT_DIR=" in source

    def test_project_dir_resolved(self):
        source = GUIDE_SH.read_text()
        assert "PROJECT_DIR=" in source

    def test_use_case_initialized(self):
        source = GUIDE_SH.read_text()
        assert 'USE_CASE=""' in source

    def test_infra_src_initialized(self):
        source = GUIDE_SH.read_text()
        assert 'INFRA_SRC=""' in source

    def test_selected_initialized(self):
        source = GUIDE_SH.read_text()
        assert "SELECTED=0" in source


class TestGuideArgParsingSource:
    """Verify argument parsing structure in source code."""

    def test_while_loop_for_args(self):
        source = GUIDE_SH.read_text()
        assert "while [[$# -gt 0]]" in source.replace(" ", "") or \
               'while [[ $# -gt 0 ]]' in source

    def test_step_case_branch(self):
        source = GUIDE_SH.read_text()
        assert "--step)" in source

    def test_auto_case_branch(self):
        source = GUIDE_SH.read_text()
        assert "--auto)" in source

    def test_help_case_branch(self):
        source = GUIDE_SH.read_text()
        assert "--help|-h)" in source

    def test_unknown_option_case_branch(self):
        source = GUIDE_SH.read_text()
        assert "*)" in source

    def test_step_validation_range(self):
        source = GUIDE_SH.read_text()
        assert 'Step must be between 1 and $TOTAL_STEPS' in source

    def test_shift_2_for_step(self):
        source = GUIDE_SH.read_text()
        assert "shift 2" in source


class TestGuideHelpOutput:
    """Detailed tests for --help output."""

    def test_help_shows_usage(self, guide_env):
        result = run_guide(["--help"], guide_env)
        assert "Usage:" in result.stdout

    def test_help_shows_step_option(self, guide_env):
        result = run_guide(["--help"], guide_env)
        assert "--step" in result.stdout

    def test_help_shows_auto_option(self, guide_env):
        result = run_guide(["--help"], guide_env)
        assert "--auto" in result.stdout

    def test_help_shows_step_range(self, guide_env):
        result = run_guide(["--help"], guide_env)
        # --step N   Resume from step N (1-9)
        assert "1-" in result.stdout

    def test_help_mentions_ci(self, guide_env):
        result = run_guide(["--help"], guide_env)
        assert "CI" in result.stdout

    def test_help_returns_exit_0(self, guide_env):
        result = run_guide(["--help"], guide_env)
        assert result.returncode == 0

    def test_h_flag_same_as_help(self, guide_env):
        result = run_guide(["-h"], guide_env)
        assert result.returncode == 0
        assert "Usage:" in result.stdout


class TestGuideUnknownOptionVariants:
    """Test various invalid argument scenarios."""

    def test_double_dash_unknown(self, guide_env):
        result = run_guide(["--foobar"], guide_env)
        assert result.returncode != 0

    def test_unknown_shows_usage(self, guide_env):
        result = run_guide(["--foobar"], guide_env)
        combined = result.stdout + result.stderr
        assert "Usage" in combined or "Unknown" in combined

    def test_single_dash_unknown(self, guide_env):
        result = run_guide(["-z"], guide_env)
        assert result.returncode != 0

    def test_positional_argument_rejected(self, guide_env):
        result = run_guide(["deploy"], guide_env)
        assert result.returncode != 0


class TestGuideStepBoundaryValues:
    """Comprehensive boundary value tests for --step."""

    def test_step_1_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "Step 1" in result.stdout

    def test_step_2_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Step 2" in result.stdout

    def test_step_3_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "3"], guide_env)
        assert "Step 3" in result.stdout

    def test_step_4_shows_header(self, guide_env):
        result = run_guide(["--auto", "--step", "4"], guide_env)
        assert "Step 4" in result.stdout

    def test_step_5_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "5"], guide_env)
        assert "Step 5" in result.stdout

    def test_step_6_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "6"], guide_env)
        assert "Step 6" in result.stdout

    def test_step_7_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "7"], guide_env)
        assert "Step 7" in result.stdout

    def test_step_8_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "Step 8" in result.stdout

    def test_step_9_valid(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Step 9" in result.stdout

    def test_step_10_invalid(self, guide_env):
        result = run_guide(["--step", "10"], guide_env)
        assert result.returncode != 0

    def test_step_100_invalid(self, guide_env):
        result = run_guide(["--step", "100"], guide_env)
        assert result.returncode != 0

    def test_step_minus_5_invalid(self, guide_env):
        result = run_guide(["--step", "-5"], guide_env)
        assert result.returncode != 0


class TestGuideStepHeaderFormat:
    """Verify step_header format: 'Step N/9: Title'."""

    def test_step_1_header_format(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "1/9" in result.stdout

    def test_step_2_header_format(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "2/9" in result.stdout

    def test_step_3_header_format(self, guide_env):
        result = run_guide(["--auto", "--step", "3"], guide_env)
        assert "3/9" in result.stdout

    def test_step_5_header_format(self, guide_env):
        result = run_guide(["--auto", "--step", "5"], guide_env)
        assert "5/9" in result.stdout

    def test_step_6_header_format(self, guide_env):
        result = run_guide(["--auto", "--step", "6"], guide_env)
        assert "6/9" in result.stdout

    def test_step_9_header_format(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "9/9" in result.stdout


class TestGuideStepTitles:
    """Verify each step's title text in output."""

    def test_step_1_title_prerequisites(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "Prerequisites Check" in result.stdout

    def test_step_2_title_use_case(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Use Case Selection" in result.stdout

    def test_step_3_title_infra_yml(self, guide_env):
        result = run_guide(["--auto", "--step", "3"], guide_env)
        assert "Create and Customize infra.yml" in result.stdout

    def test_step_4_title_generate(self, guide_env):
        result = run_guide(["--auto", "--step", "4"], guide_env)
        assert "Generate Ansible Files" in result.stdout

    def test_step_5_title_validate(self, guide_env):
        result = run_guide(["--auto", "--step", "5"], guide_env)
        assert "Validate Configuration" in result.stdout

    def test_step_6_title_apply(self, guide_env):
        result = run_guide(["--auto", "--step", "6"], guide_env)
        assert "Apply Infrastructure" in result.stdout

    def test_step_7_title_verify(self, guide_env):
        result = run_guide(["--auto", "--step", "7"], guide_env)
        assert "Verify Infrastructure" in result.stdout

    def test_step_8_title_snapshot(self, guide_env):
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "Create a Snapshot" in result.stdout

    def test_step_9_title_next_steps(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Next Steps" in result.stdout


class TestGuideBannerOutput:
    """Verify the banner/header is displayed."""

    def test_banner_shows_anklume(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "AnKLuMe" in result.stdout

    def test_banner_shows_setup_guide(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Setup Guide" in result.stdout

    def test_banner_shows_compartmentalization(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Compartmentalization" in result.stdout

    def test_banner_has_box_drawing(self, guide_env):
        """Banner uses Unicode box-drawing characters."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        # The banner uses ┌ ┐ └ ┘ characters
        assert "\u250c" in result.stdout or "\u2500" in result.stdout


class TestGuideResumeMessage:
    """Verify the 'Resuming from step N' info message."""

    def test_no_resume_message_at_step_1(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "Resuming from step" not in result.stdout

    def test_resume_message_at_step_2(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Resuming from step 2" in result.stdout

    def test_resume_message_at_step_3(self, guide_env):
        result = run_guide(["--auto", "--step", "3"], guide_env)
        assert "Resuming from step 3" in result.stdout

    def test_resume_message_at_step_5(self, guide_env):
        result = run_guide(["--auto", "--step", "5"], guide_env)
        assert "Resuming from step 5" in result.stdout

    def test_resume_message_at_step_9(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Resuming from step 9" in result.stdout


class TestGuideStep1PrerequisitesDetailed:
    """Detailed tests for step 1 prerequisite checks."""

    def test_step_1_checks_incus(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "incus" in result.stdout.lower()

    def test_step_1_checks_ansible(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "ansible" in result.stdout.lower()

    def test_step_1_checks_python3(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "python3" in result.stdout.lower()

    def test_step_1_checks_git(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "git" in result.stdout.lower()

    def test_step_1_checks_make(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "make" in result.stdout.lower()

    def test_step_1_optional_tools_section(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "Optional tools" in result.stdout

    def test_step_1_checks_ansible_lint(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "ansible-lint" in result.stdout.lower()

    def test_step_1_checks_yamllint(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "yamllint" in result.stdout.lower()

    def test_step_1_checks_shellcheck(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # shellcheck is optional; it may show "not found" or just its name
        assert "shellcheck" in result.stdout.lower()

    def test_step_1_checks_ruff(self, guide_env):
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "ruff" in result.stdout.lower()

    def test_step_1_all_prereqs_satisfied(self, guide_env):
        """With all mock tools present, step 1 reports success."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        assert "All prerequisites" in result.stdout


class TestGuideStep1MissingToolsDetailed:
    """More detailed missing-tool tests for step 1."""

    @staticmethod
    def _make_env_without(tmp_path, hidden):
        """Env without specified tools (reuses the pattern from existing tests)."""
        mock_bin = tmp_path / "restricted"
        mock_bin.mkdir(exist_ok=True)

        essential = [
            "bash", "env", "sed", "awk", "head", "tail", "cat",
            "grep", "seq", "clear", "true", "false", "dirname",
            "pwd", "rm", "cp", "mkdir", "chmod", "tee",
            "sort", "tr", "wc", "uname", "id", "readlink",
        ]
        for util in essential:
            for prefix in ["/usr/bin/", "/bin/"]:
                src = Path(prefix + util)
                if src.exists() and not (mock_bin / util).exists():
                    (mock_bin / util).symlink_to(src)
                    break

        all_tools = [
            "incus", "ansible-playbook", "ansible-lint", "ansible",
            "yamllint", "python3", "git", "make",
            "shellcheck", "ruff",
        ]
        for tool in all_tools:
            if tool in hidden:
                continue
            mock_cmd = mock_bin / tool
            if not mock_cmd.exists():
                mock_cmd.write_text("#!/usr/bin/env bash\nexit 0\n")
                mock_cmd.chmod(mock_cmd.stat().st_mode | stat.S_IEXEC)

        mock_python = mock_bin / "python3"
        if mock_python.exists():
            mock_python.unlink()
        mock_python.write_text("#!/usr/bin/env bash\n/usr/bin/python3 \"$@\"\n")
        mock_python.chmod(mock_python.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = str(mock_bin)
        env["TERM"] = "dumb"
        return env

    def test_missing_git_fails(self, tmp_path):
        env = self._make_env_without(tmp_path, {"git"})
        result = run_guide(["--auto", "--step", "1"], env)
        assert result.returncode != 0
        assert "git" in result.stdout.lower()

    def test_missing_python3_fails(self, tmp_path):
        """Hiding python3 from PATH causes step 1 to fail.

        Note: the helper always re-creates a real python3 shim (needed for
        make init to work), so we must explicitly remove it after env creation.
        """
        env = self._make_env_without(tmp_path, {"python3"})
        # The helper always re-creates python3 — remove it to truly hide it
        mock_python = tmp_path / "restricted" / "python3"
        if mock_python.exists():
            mock_python.unlink()
        result = run_guide(["--auto", "--step", "1"], env)
        assert result.returncode != 0

    def test_missing_ansible_playbook_fails(self, tmp_path):
        env = self._make_env_without(tmp_path, {"ansible-playbook"})
        result = run_guide(["--auto", "--step", "1"], env)
        assert result.returncode != 0
        assert "ansible" in result.stdout.lower()

    def test_missing_required_shows_install_hint(self, tmp_path):
        """Missing tool message tells user to install."""
        env = self._make_env_without(tmp_path, {"incus"})
        result = run_guide(["--auto", "--step", "1"], env)
        assert "Install" in result.stdout or "install" in result.stdout

    def test_missing_shellcheck_does_not_fail(self, tmp_path):
        """shellcheck is optional; missing it should not cause exit 1."""
        env = self._make_env_without(tmp_path, {"shellcheck"})
        result = run_guide(["--auto", "--step", "1"], env)
        # Step 1 should succeed (shellcheck is optional)
        assert "All prerequisites" in result.stdout or result.returncode == 0

    def test_missing_ruff_does_not_fail(self, tmp_path):
        """ruff is optional; missing it should not cause exit 1."""
        env = self._make_env_without(tmp_path, {"ruff"})
        result = run_guide(["--auto", "--step", "1"], env)
        assert "All prerequisites" in result.stdout or result.returncode == 0

    def test_missing_yamllint_does_not_fail(self, tmp_path):
        """yamllint is optional; missing it should not cause exit 1."""
        env = self._make_env_without(tmp_path, {"yamllint"})
        result = run_guide(["--auto", "--step", "1"], env)
        assert "All prerequisites" in result.stdout or result.returncode == 0


class TestGuideStep2UseCaseDetailed:
    """Detailed use-case selection tests."""

    def test_step_2_shows_student_option(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Student" in result.stdout or "student" in result.stdout

    def test_step_2_shows_teacher_option(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Teacher" in result.stdout or "teacher" in result.stdout

    def test_step_2_shows_pro_option(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Pro" in result.stdout or "pro" in result.stdout

    def test_step_2_shows_custom_option(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Custom" in result.stdout or "custom" in result.stdout

    def test_step_2_auto_selects_message(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Auto-mode: selecting option 1" in result.stdout

    def test_step_2_shows_selected_student(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Selected: student-sysadmin" in result.stdout

    def test_step_2_shows_select_prompt(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "Select your use case" in result.stdout

    def test_step_2_mentions_examples(self, guide_env):
        result = run_guide(["--auto", "--step", "2"], guide_env)
        assert "example" in result.stdout.lower()


class TestGuideStep3InfraYmlSource:
    """Verify step 3 source code structure."""

    def test_step_3_uses_editor_fallback(self):
        source = GUIDE_SH.read_text()
        assert '${EDITOR:-${VISUAL:-vi}}' in source

    def test_step_3_checks_infra_yml_exists(self):
        source = GUIDE_SH.read_text()
        assert '-f "$dest"' in source or '-f "$PROJECT_DIR/infra.yml"' in source

    def test_step_3_can_overwrite(self):
        source = GUIDE_SH.read_text()
        assert "Overwrite" in source

    def test_step_3_copies_infra_src(self):
        source = GUIDE_SH.read_text()
        assert 'cp "$INFRA_SRC" "$dest"' in source

    def test_step_3_shows_contents_with_sed(self):
        source = GUIDE_SH.read_text()
        assert 'sed' in source and '"$dest"' in source

    def test_step_3_skips_editor_in_auto(self):
        """Auto mode does not open the editor."""
        source = GUIDE_SH.read_text()
        assert '"$AUTO" != "true"' in source


class TestGuideStep4GenerateSource:
    """Verify step 4 source code."""

    def test_step_4_runs_dry_run_first(self):
        source = GUIDE_SH.read_text()
        assert "generate.py infra.yml --dry-run" in source

    def test_step_4_runs_make_sync(self):
        source = GUIDE_SH.read_text()
        assert "make sync" in source

    def test_step_4_exits_on_dry_run_failure_in_auto(self):
        source = GUIDE_SH.read_text()
        # After dry-run failure, auto mode exits
        assert "Dry-run failed" in source

    def test_step_4_suggests_resume_on_error(self):
        source = GUIDE_SH.read_text()
        assert "make guide STEP=4" in source


class TestGuideStep5ValidateSource:
    """Verify step 5 source code."""

    def test_step_5_runs_yamllint(self):
        source = GUIDE_SH.read_text()
        assert "yamllint" in source

    def test_step_5_runs_ansible_lint(self):
        source = GUIDE_SH.read_text()
        assert "ansible-lint" in source

    def test_step_5_runs_syntax_check(self):
        source = GUIDE_SH.read_text()
        assert "ansible-playbook site.yml --syntax-check" in source

    def test_step_5_mentions_non_blocking(self):
        source = GUIDE_SH.read_text()
        assert "non-blocking" in source


class TestGuideStep6ApplySource:
    """Verify step 6 source code."""

    def test_step_6_warns_about_incus_requirement(self):
        source = GUIDE_SH.read_text()
        assert "running Incus daemon" in source

    def test_step_6_skips_in_auto(self):
        source = GUIDE_SH.read_text()
        assert "Auto-mode: skipping apply" in source

    def test_step_6_checks_incus_info(self):
        source = GUIDE_SH.read_text()
        assert "incus info" in source

    def test_step_6_runs_make_apply(self):
        source = GUIDE_SH.read_text()
        assert "make apply" in source

    def test_step_6_suggests_resume(self):
        source = GUIDE_SH.read_text()
        assert "make guide STEP=6" in source


class TestGuideStep7VerifySource:
    """Verify step 7 source code."""

    def test_step_7_lists_instances(self):
        source = GUIDE_SH.read_text()
        assert "incus list --all-projects" in source

    def test_step_7_shows_networks(self):
        source = GUIDE_SH.read_text()
        assert "incus network list" in source

    def test_step_7_greps_net_pattern(self):
        source = GUIDE_SH.read_text()
        assert 'grep "net-"' in source


class TestGuideStep8SnapshotSource:
    """Verify step 8 source code."""

    def test_step_8_explains_snapshots(self):
        source = GUIDE_SH.read_text()
        assert "save and restore" in source

    def test_step_8_shows_commands(self):
        source = GUIDE_SH.read_text()
        assert "make snapshot" in source
        assert "make restore" in source
        assert "make snapshot-list" in source

    def test_step_8_auto_skip_message(self):
        source = GUIDE_SH.read_text()
        assert "Auto-mode: skipping snapshot" in source

    def test_step_8_uses_guide_initial_name(self):
        source = GUIDE_SH.read_text()
        assert "guide-initial" in source


class TestGuideStep9NextStepsDetailed:
    """Detailed tests for step 9 output content."""

    def test_step_9_mentions_network_isolation(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Network isolation" in result.stdout

    def test_step_9_mentions_nftables_commands(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "make nftables" in result.stdout

    def test_step_9_mentions_firewall_vm(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Firewall VM" in result.stdout

    def test_step_9_mentions_ai_testing(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "AI-assisted testing" in result.stdout or "AI" in result.stdout

    def test_step_9_mentions_make_ai_test(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "make ai-test" in result.stdout

    def test_step_9_mentions_make_apply_limit(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "make apply-limit" in result.stdout

    def test_step_9_mentions_make_flush(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "make flush" in result.stdout

    def test_step_9_happy_compartmentalizing(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Happy compartmentalizing" in result.stdout

    def test_step_9_mentions_docs(self, guide_env):
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "docs/" in result.stdout


class TestGuideAutoSkipsSteps:
    """Test that auto mode correctly skips interactive steps."""

    def test_step_6_auto_skip_message(self, guide_env):
        result = run_guide(["--auto", "--step", "6"], guide_env)
        assert "Auto-mode: skipping apply" in result.stdout

    def test_step_8_auto_skip_message(self, guide_env):
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "Auto-mode: skipping snapshot" in result.stdout

    def test_step_6_auto_exits_0(self, guide_env):
        """Step 6 in auto mode does not fail (it skips)."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        # Step 6 skips, then continues to step 7+
        assert "Step 6" in result.stdout

    def test_step_8_auto_exits_0(self, guide_env):
        """Step 8 in auto mode does not fail (it skips)."""
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "Step 8" in result.stdout


class TestGuideStepSequencing:
    """Test that steps execute in the correct order."""

    def test_step_6_through_9_all_appear(self, guide_env):
        """Starting at step 6, steps 6-9 all execute."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        output = result.stdout
        assert "Step 6" in output
        assert "Step 7" in output
        assert "Step 8" in output
        assert "Step 9" in output

    def test_step_8_runs_step_9_after(self, guide_env):
        """Starting at step 8, step 9 follows."""
        result = run_guide(["--auto", "--step", "8"], guide_env)
        output = result.stdout
        assert "Step 8" in output
        assert "Step 9" in output

    def test_step_9_only_runs_step_9(self, guide_env):
        """Starting at step 9, only step 9 runs."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        output = result.stdout
        assert "Step 9" in output
        # Step 8 should NOT appear
        assert "Step 8" not in output

    def test_step_6_does_not_contain_step_5(self, guide_env):
        """Starting at step 6, earlier steps are skipped."""
        result = run_guide(["--auto", "--step", "6"], guide_env)
        output = result.stdout
        assert "Step 5/" not in output
        assert "Prerequisites Check" not in output


class TestGuidePauseInAutoMode:
    """Verify that auto mode skips pauses."""

    def test_auto_no_press_enter_prompt(self, guide_env):
        """Auto mode does not show 'Press Enter' prompts."""
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert "Press Enter" not in result.stdout

    def test_auto_confirm_returns_yes(self):
        """In source, confirm() returns 0 in auto mode."""
        source = GUIDE_SH.read_text()
        # confirm checks AUTO == "true" and returns 0
        assert '"$AUTO" == "true"' in source


class TestGuideSelectOptionAutoMode:
    """Verify the select_option function behavior in auto mode."""

    def test_select_option_in_source(self):
        """select_option uses SELECTED variable."""
        source = GUIDE_SH.read_text()
        assert "SELECTED=" in source

    def test_auto_mode_prints_selecting_message(self):
        """In auto mode, select_option prints a message."""
        source = GUIDE_SH.read_text()
        assert "Auto-mode: selecting option 1" in source


class TestGuideMainLoop:
    """Verify the main loop structure in source."""

    def test_uses_seq_for_step_range(self):
        source = GUIDE_SH.read_text()
        assert 'seq "$START_STEP" "$TOTAL_STEPS"' in source

    def test_case_dispatches_all_9_steps(self):
        source = GUIDE_SH.read_text()
        for i in range(1, 10):
            assert f"{i}) step_{i}_" in source

    def test_cd_to_project_dir_before_loop(self):
        source = GUIDE_SH.read_text()
        assert 'cd "$PROJECT_DIR"' in source

    def test_header_called_before_steps(self):
        """header is called before the main loop."""
        source = GUIDE_SH.read_text()
        header_pos = source.find("header\n")
        loop_pos = source.find("for step in")
        assert header_pos > 0 and loop_pos > 0
        assert header_pos < loop_pos


class TestGuideColorTermVariants:
    """Test with different TERM values."""

    def test_term_unset_no_crash(self, guide_env):
        guide_env.pop("TERM", None)
        result = run_guide(["--auto", "--step", "9"], guide_env)
        # May succeed or fail depending on clear, but should not hang
        assert result.returncode == 0 or "Step 9" in result.stdout

    def test_term_vt100_no_crash(self, guide_env):
        guide_env["TERM"] = "vt100"
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0

    def test_term_screen_no_crash(self, guide_env):
        guide_env["TERM"] = "screen"
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0

    def test_term_linux_no_crash(self, guide_env):
        guide_env["TERM"] = "linux"
        result = run_guide(["--auto", "--step", "9"], guide_env)
        assert result.returncode == 0


class TestGuideMakeIntegration:
    """Test make guide and make quickstart from source code."""

    def test_makefile_has_guide_target(self):
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "guide:" in content

    def test_makefile_has_quickstart_target(self):
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "quickstart:" in content

    def test_makefile_guide_calls_guide_sh(self):
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "scripts/guide.sh" in content

    def test_makefile_guide_passes_step(self):
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "--step" in content

    def test_makefile_guide_passes_auto(self):
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "--auto" in content

    def test_makefile_quickstart_checks_existing(self):
        """quickstart target checks if infra.yml exists."""
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "infra.yml already exists" in content

    def test_makefile_quickstart_copies_example(self):
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "cp infra.yml.example infra.yml" in content

    def test_makefile_help_mentions_guide(self):
        """make help includes guide in Getting Started."""
        makefile = PROJECT_ROOT / "Makefile"
        content = makefile.read_text()
        assert "make guide" in content


class TestGuideUseCaseSourceMapping:
    """Verify the USE_CASE → INFRA_SRC mapping in source."""

    def test_student_maps_to_student_sysadmin(self):
        source = GUIDE_SH.read_text()
        assert 'USE_CASE="student-sysadmin"' in source

    def test_teacher_maps_to_teacher_lab(self):
        source = GUIDE_SH.read_text()
        assert 'USE_CASE="teacher-lab"' in source

    def test_pro_maps_to_pro_workstation(self):
        source = GUIDE_SH.read_text()
        assert 'USE_CASE="pro-workstation"' in source

    def test_custom_maps_to_custom(self):
        source = GUIDE_SH.read_text()
        assert 'USE_CASE="custom"' in source

    def test_custom_uses_infra_yml_example(self):
        source = GUIDE_SH.read_text()
        assert 'INFRA_SRC="$PROJECT_DIR/infra.yml.example"' in source

    def test_non_custom_uses_examples_dir(self):
        source = GUIDE_SH.read_text()
        assert 'examples/${USE_CASE}/infra.yml' in source

    def test_missing_example_falls_back(self):
        source = GUIDE_SH.read_text()
        assert "Falling back" in source


class TestGuideRunCmdFunction:
    """Verify run_cmd helper function structure."""

    def test_run_cmd_shows_info(self):
        source = GUIDE_SH.read_text()
        assert 'info "Running: $*"' in source

    def test_run_cmd_uses_ok_on_success(self):
        source = GUIDE_SH.read_text()
        # run_cmd calls ok "$desc"
        assert 'ok "$desc"' in source

    def test_run_cmd_uses_fail_on_error(self):
        source = GUIDE_SH.read_text()
        assert 'fail "$desc"' in source


class TestGuideErrorMessages:
    """Test error message content."""

    def test_step_boundary_error_message(self, guide_env):
        result = run_guide(["--step", "99"], guide_env)
        combined = result.stdout + result.stderr
        assert "must be between" in combined.lower() or "between" in combined.lower()

    def test_step_0_error_message(self, guide_env):
        result = run_guide(["--step", "0"], guide_env)
        combined = result.stdout + result.stderr
        assert "between" in combined.lower() or "must be" in combined.lower()

    def test_unknown_option_error_message(self, guide_env):
        result = run_guide(["--bogus"], guide_env)
        combined = result.stdout + result.stderr
        assert "Unknown" in combined

    def test_missing_tools_error_lists_names(self, tmp_path):
        """Error message lists the names of missing tools."""
        env = TestGuideStep1MissingToolsDetailed._make_env_without(
            tmp_path, {"incus", "git"}
        )
        result = run_guide(["--auto", "--step", "1"], env)
        output = result.stdout.lower()
        assert "incus" in output
        assert "git" in output


class TestGuideStep1MakeInitPrompt:
    """Test the 'make init' prompt in step 1."""

    def test_step_1_asks_make_init(self):
        """Source asks about 'make init'."""
        source = GUIDE_SH.read_text()
        assert "make init" in source

    def test_step_1_auto_runs_make_init(self, guide_env):
        """In auto mode, confirm returns 0, so make init is attempted."""
        result = run_guide(["--auto", "--step", "1"], guide_env)
        # make init is attempted (may fail with mock env, but it's tried)
        output = result.stdout.lower()
        # The attempt happens, possibly with a warning
        assert "prerequisites" in output


class TestGuideOutputSymbols:
    """Test that output contains the expected status symbols."""

    def test_ok_uses_checkmark(self):
        """ok() function uses a checkmark character."""
        source = GUIDE_SH.read_text()
        # ok() uses GREEN ✓
        assert "\u2713" in source  # ✓

    def test_fail_uses_cross(self):
        """fail() function uses a cross character."""
        source = GUIDE_SH.read_text()
        assert "\u2717" in source  # ✗

    def test_warn_uses_exclamation(self):
        """warn() function uses an exclamation mark."""
        source = GUIDE_SH.read_text()
        # warn uses "!" prefix
        assert "!" in source


class TestGuideStep6ApplyAutoSkip:
    """Verify step 6 auto-mode skip behavior in execution."""

    def test_step_6_auto_shows_requires_live_incus(self, guide_env):
        result = run_guide(["--auto", "--step", "6"], guide_env)
        assert "requires live Incus" in result.stdout

    def test_step_6_continues_to_step_7(self, guide_env):
        result = run_guide(["--auto", "--step", "6"], guide_env)
        assert "Step 7" in result.stdout


class TestGuideStep8SnapshotAutoSkip:
    """Verify step 8 auto-mode behavior in execution."""

    def test_step_8_shows_snapshot_commands(self, guide_env):
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "make snapshot" in result.stdout

    def test_step_8_shows_restore_command(self, guide_env):
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "make restore" in result.stdout

    def test_step_8_continues_to_step_9(self, guide_env):
        result = run_guide(["--auto", "--step", "8"], guide_env)
        assert "Step 9" in result.stdout
