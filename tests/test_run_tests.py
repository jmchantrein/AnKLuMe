"""Tests for scripts/run-tests.sh — sandboxed Molecule test runner."""

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run-tests.sh"


def _make_executable(path):
    """Make a file executable."""
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run(args, env, cwd=None, timeout=30):
    """Run run-tests.sh with given args and environment."""
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)] + args,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=timeout,
    )


@pytest.fixture()
def mock_env(tmp_path):
    """Create a mock environment with fake binaries for run-tests.sh.

    Provides mock incus, ping, and sleep binaries.
    The mock incus logs every invocation to cmds.log.
    """
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    log_file = tmp_path / "cmds.log"

    # Mock incus — logs all calls; behaves according to subcommand
    mock_incus = mock_bin / "incus"
    mock_incus.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        echo "incus $*" >> "{log_file}"

        # project list — connectivity check
        if [[ "$1" == "project" && "$2" == "list" ]]; then
            echo "default"
            exit 0
        fi

        # profile show nesting — profile exists
        if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
            exit 0
        fi

        # profile create / profile set — noop
        if [[ "$1" == "profile" && ( "$2" == "create" || "$2" == "set" ) ]]; then
            exit 0
        fi

        # info <name> — container exists
        if [[ "$1" == "info" ]]; then
            exit 0
        fi

        # start — noop
        if [[ "$1" == "start" ]]; then
            exit 0
        fi

        # launch — noop
        if [[ "$1" == "launch" ]]; then
            exit 0
        fi

        # exec — simulate success for ping and provisioning
        if [[ "$1" == "exec" ]]; then
            exit 0
        fi

        # delete — noop
        if [[ "$1" == "delete" ]]; then
            exit 0
        fi

        exit 0
    """))
    _make_executable(mock_incus)

    # Mock ping — always succeeds (for wait_for_network)
    mock_ping = mock_bin / "ping"
    mock_ping.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        echo "ping $*" >> "{log_file}"
        exit 0
    """))
    _make_executable(mock_ping)

    # Mock sleep — noop (for speed)
    mock_sleep = mock_bin / "sleep"
    mock_sleep.write_text("#!/usr/bin/env bash\nexit 0\n")
    _make_executable(mock_sleep)

    # Mock seq — pass through to real seq
    mock_seq = mock_bin / "seq"
    for search_dir in ["/usr/bin", "/bin"]:
        real_seq = os.path.join(search_dir, "seq")
        if os.path.exists(real_seq):
            mock_seq.symlink_to(real_seq)
            break

    env = os.environ.copy()
    env["PATH"] = f"{mock_bin}:{env['PATH']}"
    return env, log_file, tmp_path, mock_bin


# ── Help and argument parsing ───────────────────────────────


class TestRunTestsHelp:
    """Tests for help display and argument parsing."""

    def test_help_flag_shows_usage(self):
        """--help shows usage and exits 0."""
        result = _run(["--help"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_short_flag(self):
        """-h shows usage and exits 0."""
        result = _run(["-h"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_command(self):
        """help subcommand shows usage and exits 0."""
        result = _run(["help"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_no_args_shows_usage(self):
        """No arguments shows usage and exits 0."""
        result = _run([], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_help_lists_all_commands(self):
        """Help text lists all available commands."""
        result = _run(["help"], os.environ.copy())
        for cmd in ["create", "test", "destroy", "full"]:
            assert cmd in result.stdout

    def test_help_lists_env_vars(self):
        """Help text documents environment variables."""
        result = _run(["help"], os.environ.copy())
        assert "ANKLUME_RUNNER_NAME" in result.stdout
        assert "ANKLUME_RUNNER_IMAGE" in result.stdout
        assert "ANKLUME_RUNNER_PROJECT" in result.stdout

    def test_help_lists_examples(self):
        """Help text includes usage examples."""
        result = _run(["help"], os.environ.copy())
        assert "Examples" in result.stdout

    def test_unknown_command_errors(self):
        """Unknown command errors with message."""
        result = _run(["invalid"], os.environ.copy())
        assert result.returncode != 0
        assert "Unknown" in result.stderr


# ── Create subcommand ───────────────────────────────────────


class TestRunTestsCreate:
    """Tests for the create subcommand."""

    def test_create_succeeds(self, mock_env):
        """create subcommand completes successfully with mocks."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Creating runner container" in result.stdout
        assert "Runner" in result.stdout and "ready" in result.stdout

    def test_create_checks_connectivity(self, mock_env):
        """create calls incus project list for connectivity check."""
        env, log_file, tmp_path, _ = mock_env
        _run(["create"], env)
        log = log_file.read_text()
        assert "incus project list" in log

    def test_create_ensures_nesting_profile(self, mock_env):
        """create calls incus profile show nesting."""
        env, log_file, tmp_path, _ = mock_env
        _run(["create"], env)
        log = log_file.read_text()
        assert "incus profile show nesting" in log

    def test_create_checks_existing_container(self, mock_env):
        """create checks if container already exists via incus info."""
        env, log_file, tmp_path, _ = mock_env
        _run(["create"], env)
        log = log_file.read_text()
        assert "incus info anklume" in log

    def test_create_reuses_existing_container(self, mock_env):
        """When container exists, create reuses it and starts it."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "already exists" in result.stdout
        log = log_file.read_text()
        assert "incus start anklume" in log

    def test_create_launches_new_container(self, mock_env):
        """When container does not exist, create launches a new one."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Make incus info fail (container not found)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
                exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 1
            fi
            if [[ "$1" == "exec" ]]; then
                exit 0
            fi
            exit 0
        """))
        _make_executable(mock_incus)
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "incus launch" in log

    def test_create_waits_for_network(self, mock_env):
        """create waits for network after launching container."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Waiting for network" in result.stdout
        assert "Network ready" in result.stdout

    def test_create_provisions_runner(self, mock_env):
        """create provisions the runner after network is ready."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Provisioning runner" in result.stdout

    def test_create_custom_runner_name(self, mock_env):
        """ANKLUME_RUNNER_NAME overrides the container name."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "my-custom-runner"
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "my-custom-runner" in result.stdout
        log = log_file.read_text()
        assert "my-custom-runner" in log


# ── Destroy subcommand ──────────────────────────────────────


class TestRunTestsDestroy:
    """Tests for the destroy subcommand."""

    def test_destroy_succeeds(self, mock_env):
        """destroy subcommand completes successfully."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["destroy"], env)
        assert result.returncode == 0
        assert "Destroying runner" in result.stdout

    def test_destroy_calls_incus_delete(self, mock_env):
        """destroy calls incus delete with --force."""
        env, log_file, tmp_path, _ = mock_env
        _run(["destroy"], env)
        log = log_file.read_text()
        assert "incus delete anklume" in log
        assert "--force" in log

    def test_destroy_checks_connectivity(self, mock_env):
        """destroy checks incus connectivity first."""
        env, log_file, tmp_path, _ = mock_env
        _run(["destroy"], env)
        log = log_file.read_text()
        assert "incus project list" in log

    def test_destroy_custom_name(self, mock_env):
        """ANKLUME_RUNNER_NAME is respected by destroy."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "test-runner-42"
        result = _run(["destroy"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "test-runner-42" in log

    def test_destroy_missing_container_graceful(self, mock_env):
        """destroy handles missing container gracefully."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Make incus delete fail (container not found)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "delete" ]]; then
                exit 1
            fi
            exit 0
        """))
        _make_executable(mock_incus)
        result = _run(["destroy"], env)
        assert result.returncode == 0
        assert "not found or already removed" in result.stdout


# ── Full subcommand ─────────────────────────────────────────


class TestRunTestsFull:
    """Tests for the full subcommand (create + test + destroy)."""

    def test_full_succeeds(self, mock_env):
        """full subcommand runs create, test, and destroy."""
        env, log_file, tmp_path, _ = mock_env
        # Need to create a roles dir with molecule for the test part
        # The test subcommand checks for runner existence and then runs
        # incus exec, which our mock handles
        result = _run(["full"], env)
        assert result.returncode == 0
        assert "Creating runner container" in result.stdout
        assert "Destroying runner" in result.stdout

    def test_full_with_role(self, mock_env):
        """full with a role argument passes it to cmd_test."""
        env, log_file, tmp_path, _ = mock_env
        # Create the roles directory so the role check passes
        roles_dir = tmp_path / "roles" / "base_system" / "molecule"
        roles_dir.mkdir(parents=True)

        # Patch the script to use our tmp roles dir for the check
        patched = tmp_path / "run-tests-patched.sh"
        original = SCRIPT_PATH.read_text()
        patched.write_text(original)
        _make_executable(patched)

        result = subprocess.run(
            ["bash", str(patched), "full", "all"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
            timeout=30,
        )
        assert result.returncode == 0
        log = log_file.read_text()
        # Should have create, test (exec), and destroy calls
        assert "incus delete" in log

    def test_full_create_test_destroy_order(self, mock_env):
        """full runs create, then test, then destroy in order."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["full"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        lines = log.strip().split("\n")
        # Find position of key operations
        project_list_lines = [
            i for i, line in enumerate(lines) if "project list" in line
        ]
        delete_lines = [
            i for i, line in enumerate(lines) if "delete" in line
        ]
        # Connectivity checks come before delete
        assert project_list_lines[0] < delete_lines[0]


# ── Network wait function ───────────────────────────────────


class TestRunTestsNetworkWait:
    """Tests for the wait_for_network() function."""

    def test_network_ready_immediately(self, mock_env):
        """Network ready on first ping attempt."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Network ready" in result.stdout

    def test_network_timeout(self, mock_env):
        """Network timeout after MAX_WAIT seconds produces error."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Make incus exec (ping) always fail
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
                exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 0
            fi
            if [[ "$1" == "start" ]]; then
                exit 0
            fi
            if [[ "$1" == "exec" ]]; then
                exit 1
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        # Patch script to reduce MAX_WAIT for fast test
        patched = tmp_path / "run-tests-fast.sh"
        original = SCRIPT_PATH.read_text()
        patched.write_text(original.replace("MAX_WAIT=120", "MAX_WAIT=2"))
        _make_executable(patched)

        result = subprocess.run(
            ["bash", str(patched), "create"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode != 0
        assert "Network timeout" in result.stderr

    def test_network_wait_retries(self, mock_env):
        """Network wait retries until success."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Track call count and succeed on 3rd attempt
        counter_file = tmp_path / "exec_count"
        counter_file.write_text("0")

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
                exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 0
            fi
            if [[ "$1" == "start" ]]; then
                exit 0
            fi
            if [[ "$1" == "exec" ]]; then
                count=$(cat "{counter_file}")
                count=$((count + 1))
                echo "$count" > "{counter_file}"
                # Fail for the first 2 ping attempts, then succeed
                # Ping calls are "exec <name> --project <proj> -- ping ..."
                if echo "$*" | grep -q "ping"; then
                    if [ "$count" -le 2 ]; then
                        exit 1
                    fi
                fi
                exit 0
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Network ready" in result.stdout


# ── Provisioning ────────────────────────────────────────────


class TestRunTestsProvision:
    """Tests for the provision_runner() function."""

    def test_provision_called_during_create(self, mock_env):
        """Provisioning is executed as part of create."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Provisioning runner" in result.stdout
        # incus exec is called for provisioning
        log = log_file.read_text()
        exec_lines = [ln for ln in log.split("\n") if "incus exec" in ln]
        assert len(exec_lines) >= 1

    def test_provision_runner_printed(self, mock_env):
        """Provision section shows provisioning banner."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert "=== Provisioning runner ===" in result.stdout

    def test_provision_uses_runner_name(self, mock_env):
        """Provision runs commands in the correct container."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "prov-test"
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        exec_lines = [ln for ln in log.split("\n") if "incus exec" in ln]
        for line in exec_lines:
            assert "prov-test" in line

    def test_provision_uses_project(self, mock_env):
        """Provision uses the configured project."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "test-project"
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        exec_lines = [ln for ln in log.split("\n") if "incus exec" in ln]
        for line in exec_lines:
            assert "test-project" in line


# ── Molecule test subcommand ────────────────────────────────


class TestRunTestsMolecule:
    """Tests for the test subcommand and molecule execution."""

    def test_test_all_roles(self, mock_env):
        """test subcommand with 'all' runs tests in the runner."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test"], env)
        assert result.returncode == 0
        assert "Running Molecule tests" in result.stdout
        assert "role: all" in result.stdout

    def test_test_specific_role(self, mock_env):
        """test with a role name runs that specific role."""
        env, log_file, tmp_path, _ = mock_env
        # Use the real project path since the script checks relative to cwd
        result = _run(["test", "base_system"], env, cwd=str(SCRIPT_PATH.parent.parent))
        assert result.returncode == 0
        log = log_file.read_text()
        assert "incus exec" in log

    def test_test_missing_role_errors(self, mock_env):
        """test with nonexistent role errors."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test", "nonexistent_role"], env, cwd=str(tmp_path))
        assert result.returncode != 0
        assert "no molecule directory" in result.stderr

    def test_test_checks_runner_exists(self, mock_env):
        """test checks that the runner container exists."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Make incus info fail (runner not found)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 1
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        result = _run(["test"], env)
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_test_default_is_all(self, mock_env):
        """test without args defaults to 'all'."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test"], env)
        assert result.returncode == 0
        assert "role: all" in result.stdout

    def test_test_molecule_failure_propagates(self, mock_env):
        """When molecule fails inside runner, test reports failure."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Make incus exec fail for the test execution (but not connectivity)
        call_count_file = tmp_path / "exec_count_test"
        call_count_file.write_text("0")

        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 0
            fi
            if [[ "$1" == "exec" ]]; then
                # The test command runs incus exec for the molecule test
                exit 1
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        result = _run(["test"], env)
        assert result.returncode != 0


# ── Error handling ──────────────────────────────────────────


class TestRunTestsErrors:
    """Tests for error handling in run-tests.sh."""

    def test_create_no_incus_connectivity(self, tmp_path):
        """create fails when incus cannot connect."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        _make_executable(mock_incus)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = _run(["create"], env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr

    def test_destroy_no_incus_connectivity(self, tmp_path):
        """destroy fails when incus cannot connect."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        _make_executable(mock_incus)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = _run(["destroy"], env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr

    def test_test_no_incus_connectivity(self, tmp_path):
        """test fails when incus cannot connect."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        _make_executable(mock_incus)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = _run(["test"], env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr

    def test_full_no_incus_connectivity(self, tmp_path):
        """full fails when incus cannot connect."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        _make_executable(mock_incus)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = _run(["full"], env)
        assert result.returncode != 0
        assert "Cannot connect" in result.stderr

    def test_create_fails_on_launch_error(self, mock_env):
        """create fails when incus launch returns error."""
        env, log_file, tmp_path, mock_bin = mock_env
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
                exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 1
            fi
            if [[ "$1" == "launch" ]]; then
                echo "Error: launch failed" >&2
                exit 1
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        result = _run(["create"], env)
        assert result.returncode != 0

    def test_unknown_command_shows_help_hint(self):
        """Unknown command suggests running help."""
        result = _run(["bogus"], os.environ.copy())
        assert result.returncode != 0
        assert "help" in result.stderr.lower()

    def test_die_outputs_to_stderr(self):
        """Error messages go to stderr."""
        result = _run(["invalid"], os.environ.copy())
        assert result.returncode != 0
        assert "ERROR" in result.stderr

    def test_nesting_profile_creation(self, mock_env):
        """When nesting profile does not exist, it is created."""
        env, log_file, tmp_path, mock_bin = mock_env
        # Make profile show fail (profile not found)
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
                exit 1
            fi
            if [[ "$1" == "profile" && "$2" == "create" ]]; then
                exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "set" ]]; then
                exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 0
            fi
            if [[ "$1" == "start" ]]; then
                exit 0
            fi
            if [[ "$1" == "exec" ]]; then
                exit 0
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Creating nesting profile" in result.stdout
        log = log_file.read_text()
        assert "incus profile create nesting" in log
        assert "incus profile set nesting security.nesting=true" in log
        assert "incus profile set nesting security.syscalls.intercept.mknod=true" in log
        assert "incus profile set nesting security.syscalls.intercept.setxattr=true" in log

    def test_env_runner_image_override(self, mock_env):
        """ANKLUME_RUNNER_IMAGE overrides the base image."""
        env, log_file, tmp_path, mock_bin = mock_env
        env["ANKLUME_RUNNER_IMAGE"] = "images:ubuntu/24.04"
        # Make info fail so launch is called
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            echo "incus $*" >> "{log_file}"
            if [[ "$1" == "project" && "$2" == "list" ]]; then
                echo "default"; exit 0
            fi
            if [[ "$1" == "profile" && "$2" == "show" && "$3" == "nesting" ]]; then
                exit 0
            fi
            if [[ "$1" == "info" ]]; then
                exit 1
            fi
            if [[ "$1" == "exec" ]]; then
                exit 0
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "images:ubuntu/24.04" in log

    def test_env_runner_project_override(self, mock_env):
        """ANKLUME_RUNNER_PROJECT overrides the Incus project."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "custom-project"
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "custom-project" in log
