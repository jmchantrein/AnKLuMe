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


# ── Script file properties ──────────────────────────────────


class TestRunTestsScriptProperties:
    """Tests for the script file itself."""

    def test_script_exists(self):
        """run-tests.sh exists at expected location."""
        assert SCRIPT_PATH.exists()

    def test_script_is_file(self):
        """run-tests.sh is a regular file."""
        assert SCRIPT_PATH.is_file()

    def test_script_is_executable(self):
        """run-tests.sh has executable permission."""
        assert os.access(SCRIPT_PATH, os.X_OK)

    def test_script_has_bash_shebang(self):
        """run-tests.sh starts with #!/usr/bin/env bash."""
        first_line = SCRIPT_PATH.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_script_uses_strict_mode(self):
        """run-tests.sh uses set -euo pipefail for safety."""
        content = SCRIPT_PATH.read_text()
        assert "set -euo pipefail" in content

    def test_script_defines_die_function(self):
        """run-tests.sh defines a die() error function."""
        content = SCRIPT_PATH.read_text()
        assert "die()" in content

    def test_script_defines_all_commands(self):
        """run-tests.sh defines cmd_create, cmd_test, cmd_destroy."""
        content = SCRIPT_PATH.read_text()
        assert "cmd_create()" in content
        assert "cmd_test()" in content
        assert "cmd_destroy()" in content

    def test_script_defines_helper_functions(self):
        """run-tests.sh defines helper functions."""
        content = SCRIPT_PATH.read_text()
        assert "check_incus_connectivity()" in content
        assert "ensure_nesting_profile()" in content
        assert "wait_for_network()" in content
        assert "provision_runner()" in content

    def test_script_defines_usage_function(self):
        """run-tests.sh defines a usage() function."""
        content = SCRIPT_PATH.read_text()
        assert "usage()" in content

    def test_script_has_case_statement(self):
        """run-tests.sh uses a case statement for command dispatch."""
        content = SCRIPT_PATH.read_text()
        assert 'case "$1" in' in content
        assert "esac" in content


# ── Default configuration values ─────────────────────────────


class TestRunTestsDefaults:
    """Tests for default configuration values."""

    def test_default_runner_name(self, mock_env):
        """Default runner name is 'anklume'."""
        env, log_file, tmp_path, _ = mock_env
        # Ensure ANKLUME_RUNNER_NAME is NOT set
        env.pop("ANKLUME_RUNNER_NAME", None)
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "anklume" in result.stdout
        log = log_file.read_text()
        assert "incus info anklume" in log

    def test_default_runner_image(self, mock_env):
        """Default runner image is images:debian/13."""
        content = SCRIPT_PATH.read_text()
        assert 'images:debian/13' in content

    def test_default_runner_project(self, mock_env):
        """Default runner project is 'default'."""
        env, log_file, tmp_path, _ = mock_env
        env.pop("ANKLUME_RUNNER_PROJECT", None)
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "--project default" in log

    def test_default_repo_branch(self):
        """Default repo branch is 'main'."""
        content = SCRIPT_PATH.read_text()
        assert 'REPO_BRANCH="${ANKLUME_RUNNER_REPO_BRANCH:-main}"' in content

    def test_default_max_wait(self):
        """MAX_WAIT defaults to 120 seconds."""
        content = SCRIPT_PATH.read_text()
        assert "MAX_WAIT=120" in content

    def test_default_repo_url(self):
        """Default repo URL points to the AnKLuMe GitHub repository."""
        content = SCRIPT_PATH.read_text()
        assert "github.com/jmchantrein/AnKLuMe.git" in content


# ── Die function behavior ────────────────────────────────────


class TestRunTestsDie:
    """Tests for the die() error function."""

    def test_die_prefix_format(self):
        """die() prefixes messages with 'ERROR:'."""
        result = _run(["notacommand"], os.environ.copy())
        assert result.stderr.startswith("ERROR:")

    def test_die_exits_nonzero(self):
        """die() causes non-zero exit."""
        result = _run(["notacommand"], os.environ.copy())
        assert result.returncode != 0

    def test_die_message_includes_input(self):
        """die() includes the invalid command in its message."""
        result = _run(["xyz123"], os.environ.copy())
        assert "xyz123" in result.stderr

    def test_die_nothing_on_stdout(self):
        """die() does not output to stdout on error."""
        result = _run(["notacommand"], os.environ.copy())
        # stdout should be empty or minimal — the error goes to stderr
        assert "ERROR" not in result.stdout


# ── Create subcommand edge cases ─────────────────────────────


class TestRunTestsCreateEdgeCases:
    """Additional edge cases for the create subcommand."""

    def test_create_launch_uses_profiles(self, mock_env):
        """create launch command uses default and nesting profiles."""
        env, log_file, tmp_path, mock_bin = mock_env
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
        launch_lines = [ln for ln in log.split("\n") if "incus launch" in ln]
        assert len(launch_lines) >= 1
        launch_line = launch_lines[0]
        assert "--profile default" in launch_line
        assert "--profile nesting" in launch_line

    def test_create_launch_uses_image(self, mock_env):
        """create launch command uses the configured image."""
        env, log_file, tmp_path, mock_bin = mock_env
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
        launch_lines = [ln for ln in log.split("\n") if "incus launch" in ln]
        assert len(launch_lines) >= 1
        assert "images:debian/13" in launch_lines[0]

    def test_create_launch_uses_project(self, mock_env):
        """create launch includes --project flag."""
        env, log_file, tmp_path, mock_bin = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "my-proj"
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
        launch_lines = [ln for ln in log.split("\n") if "incus launch" in ln]
        assert len(launch_lines) >= 1
        assert "--project my-proj" in launch_lines[0]

    def test_create_start_uses_project(self, mock_env):
        """create start (reuse) includes --project flag."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "reuse-proj"
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        start_lines = [ln for ln in log.split("\n") if "incus start" in ln]
        assert len(start_lines) >= 1
        assert "--project reuse-proj" in start_lines[0]

    def test_create_info_uses_project(self, mock_env):
        """create info check includes --project flag."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "info-proj"
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        info_lines = [ln for ln in log.split("\n") if "incus info" in ln]
        assert len(info_lines) >= 1
        assert "--project info-proj" in info_lines[0]

    def test_create_banner_shows_container_name(self, mock_env):
        """create banner shows the container name."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "banner-test"
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Creating runner container: banner-test" in result.stdout

    def test_create_ready_banner_shows_name(self, mock_env):
        """create completion banner shows the container name."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "ready-name"
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Runner ready-name ready" in result.stdout

    def test_create_connectivity_check_uses_format_csv(self, mock_env):
        """Connectivity check uses --format csv flag."""
        content = SCRIPT_PATH.read_text()
        assert "project list --format csv" in content

    def test_create_custom_image_on_launch(self, mock_env):
        """Custom image is passed to incus launch when creating new container."""
        env, log_file, tmp_path, mock_bin = mock_env
        env["ANKLUME_RUNNER_IMAGE"] = "images:alpine/3.20"
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
        launch_lines = [ln for ln in log.split("\n") if "incus launch" in ln]
        assert "images:alpine/3.20" in launch_lines[0]


# ── Destroy subcommand edge cases ────────────────────────────


class TestRunTestsDestroyEdgeCases:
    """Additional edge cases for the destroy subcommand."""

    def test_destroy_banner_shows_name(self, mock_env):
        """destroy banner shows the container name."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "destroy-banner"
        result = _run(["destroy"], env)
        assert result.returncode == 0
        assert "Destroying runner: destroy-banner" in result.stdout

    def test_destroy_uses_project_flag(self, mock_env):
        """destroy passes --project to incus delete."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "del-proj"
        _run(["destroy"], env)
        log = log_file.read_text()
        delete_lines = [ln for ln in log.split("\n") if "incus delete" in ln]
        assert len(delete_lines) >= 1
        assert "--project del-proj" in delete_lines[0]

    def test_destroy_force_flag(self, mock_env):
        """destroy uses --force flag on delete."""
        env, log_file, tmp_path, _ = mock_env
        _run(["destroy"], env)
        log = log_file.read_text()
        delete_lines = [ln for ln in log.split("\n") if "incus delete" in ln]
        assert "--force" in delete_lines[0]

    def test_destroy_returns_zero_on_success(self, mock_env):
        """destroy returns 0 on successful deletion."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["destroy"], env)
        assert result.returncode == 0

    def test_destroy_no_launch_or_exec_calls(self, mock_env):
        """destroy does not call launch or exec."""
        env, log_file, tmp_path, _ = mock_env
        _run(["destroy"], env)
        log = log_file.read_text()
        assert "incus launch" not in log
        assert "incus exec" not in log


# ── Test subcommand edge cases ───────────────────────────────


class TestRunTestsMoleculeEdgeCases:
    """Additional edge cases for the test subcommand."""

    def test_test_custom_runner_name(self, mock_env):
        """test uses custom runner name from ANKLUME_RUNNER_NAME."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "test-custom"
        result = _run(["test"], env)
        assert result.returncode == 0
        assert "test-custom" in result.stdout
        log = log_file.read_text()
        assert "test-custom" in log

    def test_test_custom_project(self, mock_env):
        """test uses custom project from ANKLUME_RUNNER_PROJECT."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "test-proj"
        result = _run(["test"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        exec_lines = [ln for ln in log.split("\n") if "incus exec" in ln]
        for line in exec_lines:
            assert "--project test-proj" in line

    def test_test_all_uses_exec(self, mock_env):
        """test 'all' executes commands via incus exec."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "incus exec" in log

    def test_test_banner_shows_role(self, mock_env):
        """test banner shows the role being tested."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test"], env)
        assert "role: all" in result.stdout

    def test_test_specific_role_uses_exec(self, mock_env):
        """test with specific role uses incus exec."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test", "base_system"], env,
                       cwd=str(SCRIPT_PATH.parent.parent))
        assert result.returncode == 0
        log = log_file.read_text()
        exec_lines = [ln for ln in log.split("\n") if "incus exec" in ln]
        assert len(exec_lines) >= 1

    def test_test_missing_role_stderr(self, mock_env):
        """test with nonexistent role writes error to stderr."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test", "ghost_role"], env, cwd=str(tmp_path))
        assert result.returncode != 0
        assert "ERROR" in result.stderr

    def test_test_connectivity_check_before_run(self, mock_env):
        """test checks incus connectivity before running tests."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        lines = log.strip().split("\n")
        project_list_pos = next(
            i for i, ln in enumerate(lines) if "project list" in ln
        )
        exec_pos = next(
            (i for i, ln in enumerate(lines) if "incus exec" in ln),
            len(lines),
        )
        assert project_list_pos < exec_pos

    def test_test_info_check_before_exec(self, mock_env):
        """test checks runner exists (info) before running exec."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        lines = log.strip().split("\n")
        info_pos = next(
            i for i, ln in enumerate(lines) if "incus info" in ln
        )
        exec_pos = next(
            (i for i, ln in enumerate(lines) if "incus exec" in ln),
            len(lines),
        )
        assert info_pos < exec_pos


# ── Full subcommand edge cases ───────────────────────────────


class TestRunTestsFullEdgeCases:
    """Additional edge cases for the full subcommand."""

    def test_full_without_role_defaults_to_all(self, mock_env):
        """full without a role argument defaults to 'all'."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["full"], env)
        assert result.returncode == 0
        assert "role: all" in result.stdout

    def test_full_exits_on_test_failure_with_set_e(self, mock_env):
        """full exits immediately on test failure due to set -e."""
        # Because the script uses set -e, if cmd_test fails (incus exec
        # returns non-zero), cmd_destroy is NOT called — bash exits.
        env, log_file, tmp_path, mock_bin = mock_env

        # Create a state tracker to distinguish create-phase exec calls
        # from test-phase exec calls.
        phase_file = tmp_path / "phase"
        phase_file.write_text("create")

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
            if [[ "$1" == "delete" ]]; then
                exit 0
            fi
            if [[ "$1" == "exec" ]]; then
                phase=$(cat "{phase_file}")
                if [[ "$phase" == "test" ]]; then
                    exit 1
                fi
                exit 0
            fi
            exit 0
        """))
        _make_executable(mock_incus)

        # Patch script: inject a phase marker between cmd_create and cmd_test
        patched = tmp_path / "run-tests-phase.sh"
        original = SCRIPT_PATH.read_text()
        patched.write_text(original.replace(
            "cmd_create; cmd_test",
            f'cmd_create; echo "test" > "{phase_file}"; cmd_test',
        ))
        _make_executable(patched)

        result = subprocess.run(
            ["bash", str(patched), "full"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        # set -e causes the script to exit on cmd_test failure
        assert result.returncode != 0
        log = log_file.read_text()
        # Destroy was NOT called because set -e exits before reaching it
        assert "incus delete" not in log

    def test_full_calls_create_first(self, mock_env):
        """full calls create before test."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["full"], env)
        assert result.returncode == 0
        # Creating appears before testing
        create_pos = result.stdout.find("Creating runner container")
        test_pos = result.stdout.find("Running Molecule tests")
        assert create_pos < test_pos

    def test_full_calls_destroy_last(self, mock_env):
        """full calls destroy after test."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["full"], env)
        assert result.returncode == 0
        test_pos = result.stdout.find("Running Molecule tests")
        destroy_pos = result.stdout.find("Destroying runner")
        assert test_pos < destroy_pos

    def test_full_custom_runner_name(self, mock_env):
        """full uses custom runner name throughout."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "full-custom"
        result = _run(["full"], env)
        assert result.returncode == 0
        assert "full-custom" in result.stdout
        log = log_file.read_text()
        # The name should appear in info, start/launch, exec, and delete
        assert "full-custom" in log

    def test_full_custom_project(self, mock_env):
        """full uses custom project throughout."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_PROJECT"] = "full-proj"
        result = _run(["full"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "full-proj" in log


# ── Nesting profile edge cases ───────────────────────────────


class TestRunTestsNestingProfile:
    """Tests for the ensure_nesting_profile() function."""

    def test_nesting_profile_exists_no_create(self, mock_env):
        """When nesting profile exists, it is not recreated."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        # profile show succeeds, so no create should be called
        assert "incus profile create nesting" not in log

    def test_nesting_profile_security_settings(self, mock_env):
        """Nesting profile sets all three security options."""
        env, log_file, tmp_path, mock_bin = mock_env
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
            if [[ "$1" == "profile" ]]; then
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
        log = log_file.read_text()
        assert "security.nesting=true" in log
        assert "security.syscalls.intercept.mknod=true" in log
        assert "security.syscalls.intercept.setxattr=true" in log

    def test_nesting_profile_created_before_launch(self, mock_env):
        """Nesting profile is ensured before launching container."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        lines = log.strip().split("\n")
        profile_pos = next(
            i for i, ln in enumerate(lines) if "profile show nesting" in ln
        )
        info_pos = next(
            i for i, ln in enumerate(lines) if "incus info" in ln
        )
        assert profile_pos < info_pos


# ── Wait for network edge cases ──────────────────────────────


class TestRunTestsNetworkWaitEdgeCases:
    """Additional edge cases for wait_for_network()."""

    def test_network_wait_pings_debian_host(self):
        """wait_for_network pings deb.debian.org."""
        content = SCRIPT_PATH.read_text()
        assert "deb.debian.org" in content

    def test_network_wait_uses_single_ping(self):
        """wait_for_network uses ping -c1 -W1."""
        content = SCRIPT_PATH.read_text()
        assert "ping -c1 -W1" in content

    def test_network_wait_outputs_waiting_message(self, mock_env):
        """wait_for_network prints 'Waiting for network' message."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create"], env)
        assert result.returncode == 0
        assert "Waiting for network connectivity" in result.stdout

    def test_network_timeout_includes_seconds(self, mock_env):
        """Network timeout message includes the timeout value."""
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

        patched = tmp_path / "run-tests-timeout.sh"
        original = SCRIPT_PATH.read_text()
        patched.write_text(original.replace("MAX_WAIT=120", "MAX_WAIT=3"))
        _make_executable(patched)

        result = subprocess.run(
            ["bash", str(patched), "create"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode != 0
        assert "3s" in result.stderr


# ── Provision edge cases ─────────────────────────────────────


class TestRunTestsProvisionEdgeCases:
    """Additional edge cases for provision_runner()."""

    def test_provision_installs_packages(self):
        """Provision installs required packages."""
        content = SCRIPT_PATH.read_text()
        for pkg in ["python3", "python3-pip", "python3-venv", "git", "make"]:
            assert pkg in content

    def test_provision_installs_incus(self):
        """Provision installs incus and incus-client."""
        content = SCRIPT_PATH.read_text()
        assert "incus incus-client" in content

    def test_provision_installs_molecule(self):
        """Provision installs molecule and test tools."""
        content = SCRIPT_PATH.read_text()
        assert "molecule" in content
        assert "ansible-lint" in content
        assert "yamllint" in content

    def test_provision_configures_git(self):
        """Provision configures git user and email."""
        content = SCRIPT_PATH.read_text()
        assert "git config --global user.name" in content
        assert "git config --global user.email" in content

    def test_provision_clones_repo(self):
        """Provision clones the repository."""
        content = SCRIPT_PATH.read_text()
        assert "git clone" in content

    def test_provision_sets_debian_frontend(self):
        """Provision sets DEBIAN_FRONTEND=noninteractive."""
        content = SCRIPT_PATH.read_text()
        assert "DEBIAN_FRONTEND=noninteractive" in content

    def test_provision_initializes_nested_incus(self):
        """Provision initializes nested Incus with preseed."""
        content = SCRIPT_PATH.read_text()
        assert "incus admin init --preseed" in content

    def test_provision_adds_images_remote(self):
        """Provision adds the images remote."""
        content = SCRIPT_PATH.read_text()
        assert "images.linuxcontainers.org" in content

    def test_provision_installs_community_general(self):
        """Provision installs ansible community.general collection."""
        content = SCRIPT_PATH.read_text()
        assert "community.general" in content

    def test_provision_completion_banner(self, mock_env):
        """Provision prints completion banner."""
        content = SCRIPT_PATH.read_text()
        assert "Runner provisioned" in content


# ── Help output details ──────────────────────────────────────


class TestRunTestsHelpDetails:
    """Detailed tests for help/usage output."""

    def test_help_shows_full_command(self):
        """Help shows the full subcommand 'full [role]'."""
        result = _run(["help"], os.environ.copy())
        assert "full" in result.stdout

    def test_help_documents_repo_url_env(self):
        """Help documents ANKLUME_RUNNER_REPO_URL."""
        result = _run(["help"], os.environ.copy())
        assert "ANKLUME_RUNNER_REPO_URL" in result.stdout

    def test_help_documents_repo_branch_env(self):
        """Help documents ANKLUME_RUNNER_REPO_BRANCH."""
        result = _run(["help"], os.environ.copy())
        assert "ANKLUME_RUNNER_REPO_BRANCH" in result.stdout

    def test_help_shows_test_role_syntax(self):
        """Help shows test [role] syntax."""
        result = _run(["help"], os.environ.copy())
        assert "test" in result.stdout
        assert "role" in result.stdout

    def test_help_shows_full_cycle_example(self):
        """Help shows full cycle example."""
        result = _run(["help"], os.environ.copy())
        assert "run-tests.sh full" in result.stdout

    def test_help_returns_zero(self):
        """All help forms return exit code 0."""
        for arg in ["-h", "--help", "help"]:
            result = _run([arg], os.environ.copy())
            assert result.returncode == 0, f"{arg} returned {result.returncode}"

    def test_help_nothing_on_stderr(self):
        """Help does not write to stderr."""
        result = _run(["help"], os.environ.copy())
        assert result.stderr == ""


# ── Unknown command edge cases ───────────────────────────────


class TestRunTestsUnknownCommands:
    """Tests for various unknown/invalid commands."""

    def test_numeric_command_errors(self):
        """Numeric string as command errors."""
        result = _run(["123"], os.environ.copy())
        assert result.returncode != 0
        assert "Unknown" in result.stderr

    def test_empty_like_command_errors(self):
        """Unusual command string errors properly."""
        result = _run(["--invalid-flag"], os.environ.copy())
        assert result.returncode != 0

    def test_multiple_args_first_unknown_errors(self):
        """First argument unknown errors even with valid second argument."""
        result = _run(["unknown", "create"], os.environ.copy())
        assert result.returncode != 0
        assert "Unknown" in result.stderr

    def test_unknown_command_mentions_help(self):
        """Unknown command output mentions 'help' for guidance."""
        result = _run(["blah"], os.environ.copy())
        assert result.returncode != 0
        assert "help" in result.stderr.lower()


# ── Environment variable combinations ────────────────────────


class TestRunTestsEnvCombinations:
    """Tests for combining multiple environment variable overrides."""

    def test_custom_name_and_project_create(self, mock_env):
        """Custom name + project both applied during create."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "combo-runner"
        env["ANKLUME_RUNNER_PROJECT"] = "combo-proj"
        result = _run(["create"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        info_lines = [ln for ln in log.split("\n") if "incus info" in ln]
        assert len(info_lines) >= 1
        assert "combo-runner" in info_lines[0]
        assert "--project combo-proj" in info_lines[0]

    def test_custom_name_and_project_destroy(self, mock_env):
        """Custom name + project both applied during destroy."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "combo-del"
        env["ANKLUME_RUNNER_PROJECT"] = "combo-delproj"
        result = _run(["destroy"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        delete_lines = [ln for ln in log.split("\n") if "incus delete" in ln]
        assert "combo-del" in delete_lines[0]
        assert "--project combo-delproj" in delete_lines[0]

    def test_custom_name_and_project_test(self, mock_env):
        """Custom name + project both applied during test."""
        env, log_file, tmp_path, _ = mock_env
        env["ANKLUME_RUNNER_NAME"] = "combo-test"
        env["ANKLUME_RUNNER_PROJECT"] = "combo-testproj"
        result = _run(["test"], env)
        assert result.returncode == 0
        log = log_file.read_text()
        assert "combo-test" in log
        assert "combo-testproj" in log

    def test_custom_name_project_and_image(self, mock_env):
        """Custom name + project + image all applied during launch."""
        env, log_file, tmp_path, mock_bin = mock_env
        env["ANKLUME_RUNNER_NAME"] = "triple"
        env["ANKLUME_RUNNER_PROJECT"] = "triproj"
        env["ANKLUME_RUNNER_IMAGE"] = "images:ubuntu/24.04"
        # Make info fail to trigger launch
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
        launch_lines = [ln for ln in log.split("\n") if "incus launch" in ln]
        assert len(launch_lines) >= 1
        assert "triple" in launch_lines[0]
        assert "--project triproj" in launch_lines[0]
        assert "images:ubuntu/24.04" in launch_lines[0]


# ── Provisioning script content ──────────────────────────────


class TestRunTestsProvisionContent:
    """Tests for provision_runner() script content sent to the container."""

    def test_provision_updates_apt(self):
        """Provision runs apt-get update."""
        content = SCRIPT_PATH.read_text()
        assert "apt-get update" in content

    def test_provision_installs_apt_packages_quietly(self):
        """Provision installs apt packages with -qq flag."""
        content = SCRIPT_PATH.read_text()
        assert "apt-get install -y -qq" in content

    def test_provision_pip_uses_break_system_packages(self):
        """Provision pip install uses --break-system-packages."""
        content = SCRIPT_PATH.read_text()
        assert "--break-system-packages" in content

    def test_provision_handles_existing_repo(self):
        """Provision handles both clone and update of repo."""
        content = SCRIPT_PATH.read_text()
        assert "git clone" in content
        assert "git fetch" in content
        assert "git pull" in content

    def test_provision_uses_repo_dir_variable(self):
        """Provision uses REPO_DIR for the repo path."""
        content = SCRIPT_PATH.read_text()
        assert 'REPO_DIR="/root/AnKLuMe"' in content

    def test_provision_incus_preseed_configures_network(self):
        """Provision preseed configures a network bridge."""
        content = SCRIPT_PATH.read_text()
        assert "incusbr0" in content
        assert "ipv4.nat" in content

    def test_provision_incus_preseed_configures_storage(self):
        """Provision preseed uses dir storage backend."""
        content = SCRIPT_PATH.read_text()
        assert "driver: dir" in content


# ── Molecule test content patterns ───────────────────────────


class TestRunTestsMoleculePatterns:
    """Tests for the molecule test execution patterns."""

    def test_test_all_iterates_roles(self):
        """test 'all' iterates over roles/*/molecule directories."""
        content = SCRIPT_PATH.read_text()
        assert "roles/*/molecule" in content

    def test_test_all_tracks_pass_fail(self):
        """test 'all' tracks passed and failed counts."""
        content = SCRIPT_PATH.read_text()
        assert "passed=" in content
        assert "failed=" in content

    def test_test_all_reports_results(self):
        """test 'all' outputs a results summary."""
        content = SCRIPT_PATH.read_text()
        assert "Results" in content
        assert "Passed:" in content
        assert "Failed:" in content

    def test_test_all_reports_failed_roles(self):
        """test 'all' reports which roles failed."""
        content = SCRIPT_PATH.read_text()
        assert "failed_roles" in content

    def test_test_all_exits_nonzero_on_failures(self):
        """test 'all' exits with non-zero if any role fails."""
        content = SCRIPT_PATH.read_text()
        # The inner script checks: [ $failed -eq 0 ] || exit 1
        assert "exit 1" in content

    def test_test_specific_role_checks_molecule_dir(self):
        """test with specific role checks for molecule directory."""
        content = SCRIPT_PATH.read_text()
        assert 'roles/${role}/molecule' in content

    def test_test_specific_role_runs_molecule_test(self):
        """test with specific role runs 'molecule test'."""
        content = SCRIPT_PATH.read_text()
        assert "molecule test" in content


# ── Connectivity check edge cases ────────────────────────────


class TestRunTestsConnectivity:
    """Tests for the check_incus_connectivity() function."""

    def test_connectivity_error_message(self, tmp_path):
        """Connectivity failure shows clear error message."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        _make_executable(mock_incus)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = _run(["create"], env)
        assert "Incus daemon" in result.stderr

    def test_connectivity_mentions_socket_access(self, tmp_path):
        """Connectivity error mentions socket access."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        mock_incus = mock_bin / "incus"
        mock_incus.write_text("#!/usr/bin/env bash\nexit 1\n")
        _make_executable(mock_incus)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        result = _run(["create"], env)
        assert "socket" in result.stderr.lower()

    def test_connectivity_check_runs_first(self, mock_env):
        """Connectivity check is the first incus call."""
        env, log_file, tmp_path, _ = mock_env
        _run(["create"], env)
        log = log_file.read_text()
        lines = log.strip().split("\n")
        assert "project list" in lines[0]


# ── Entry point argument handling ────────────────────────────


class TestRunTestsArgParsing:
    """Tests for the entry point case/argument handling."""

    def test_create_ignores_extra_args(self, mock_env):
        """create subcommand ignores extra arguments."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["create", "extra", "args"], env)
        assert result.returncode == 0

    def test_destroy_ignores_extra_args(self, mock_env):
        """destroy subcommand ignores extra arguments."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["destroy", "extra"], env)
        assert result.returncode == 0

    def test_test_accepts_role_arg(self, mock_env):
        """test subcommand accepts a role argument."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["test", "all"], env)
        assert result.returncode == 0
        assert "role: all" in result.stdout

    def test_full_accepts_role_arg(self, mock_env):
        """full subcommand accepts a role argument."""
        env, log_file, tmp_path, _ = mock_env
        result = _run(["full", "all"], env)
        assert result.returncode == 0
        assert "role: all" in result.stdout

    def test_help_flag_precedence(self):
        """--help works even before any other argument."""
        result = _run(["--help"], os.environ.copy())
        assert result.returncode == 0
        assert "Usage" in result.stdout


# ── Script structure ─────────────────────────────────────────


class TestRunTestsScriptStructure:
    """Tests for the overall structure of the script."""

    def test_script_has_configuration_section(self):
        """Script has a configuration section with defaults."""
        content = SCRIPT_PATH.read_text()
        assert "RUNNER_NAME=" in content
        assert "RUNNER_IMAGE=" in content
        assert "RUNNER_PROJECT=" in content
        assert "REPO_URL=" in content
        assert "REPO_BRANCH=" in content

    def test_script_env_vars_use_default_syntax(self):
        """Configuration uses bash ${VAR:-default} syntax."""
        content = SCRIPT_PATH.read_text()
        assert "${ANKLUME_RUNNER_NAME:-" in content
        assert "${ANKLUME_RUNNER_IMAGE:-" in content
        assert "${ANKLUME_RUNNER_PROJECT:-" in content

    def test_script_case_handles_all_commands(self):
        """Case statement handles create, test, destroy, full, help."""
        content = SCRIPT_PATH.read_text()
        for cmd in ["create)", "test)", "destroy)", "full)", "help)"]:
            assert cmd in content

    def test_script_case_has_wildcard_fallback(self):
        """Case statement has a wildcard (*) fallback for unknown commands."""
        content = SCRIPT_PATH.read_text()
        assert "*)" in content

    def test_full_calls_three_functions(self):
        """full command calls cmd_create, cmd_test, cmd_destroy."""
        content = SCRIPT_PATH.read_text()
        # The full line should reference all three
        assert "cmd_create; cmd_test" in content
        assert "cmd_test" in content
        assert "cmd_destroy" in content

    def test_test_shifts_args(self):
        """test command shifts args before calling cmd_test."""
        content = SCRIPT_PATH.read_text()
        # The case statement does: test) shift; cmd_test "${1:-all}" ;;
        assert 'shift; cmd_test' in content

    def test_full_shifts_args(self):
        """full command shifts args before calling functions."""
        content = SCRIPT_PATH.read_text()
        # The case statement does: full) shift; cmd_create; ...
        assert 'shift; cmd_create; cmd_test' in content
