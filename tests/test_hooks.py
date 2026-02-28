"""Tests for scripts/hooks/ — pre-commit and tmux-domain-switch hooks.

Covers: script existence, shellcheck, pre-commit IP blocking behavior,
tmux domain extraction logic, and state file creation.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = PROJECT_ROOT / "scripts" / "hooks"
PRE_COMMIT_HOOK = HOOKS_DIR / "pre-commit"
TMUX_HOOK = HOOKS_DIR / "tmux-domain-switch.sh"


# ── TestPreCommitHook ─────────────────────────────────────


class TestPreCommitHook:
    """Tests for the pre-commit hook that blocks personal infrastructure data."""

    def test_hook_exists(self):
        """pre-commit hook exists and is executable."""
        assert PRE_COMMIT_HOOK.exists()
        assert os.access(PRE_COMMIT_HOOK, os.X_OK)

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed",
    )
    def test_shellcheck(self):
        """pre-commit hook passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(PRE_COMMIT_HOOK)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"shellcheck errors:\n{result.stdout}\n{result.stderr}"
        )

    @staticmethod
    def _init_git_repo(repo_dir):
        """Initialize a git repo in repo_dir with an initial commit."""
        subprocess.run(
            ["git", "init", str(repo_dir)],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "config", "user.name", "Test"],
            capture_output=True, check=True,
        )
        # Create an initial commit so HEAD exists
        dummy = repo_dir / ".gitkeep"
        dummy.write_text("")
        subprocess.run(
            ["git", "-C", str(repo_dir), "add", ".gitkeep"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_dir), "commit", "-m", "init"],
            capture_output=True, check=True,
        )

    def test_blocks_private_ips(self, tmp_path):
        """Hook blocks commits containing non-whitelisted private IPs.

        A staged .py file containing 192.168.1.1 should cause exit 1.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        # Install our hook
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        # Stage a file with a private IP
        bad_file = repo / "config.py"
        bad_file.write_text('SERVER = "192.168.1.1"\n')
        subprocess.run(
            ["git", "-C", str(repo), "add", "config.py"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add config"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, (
            "Hook should have blocked commit with private IP 192.168.1.1"
        )
        assert "BLOCKED" in result.stdout or "BLOCKED" in result.stderr

    def test_blocks_172_private_ips(self, tmp_path):
        """Hook blocks 172.16-31.x.x private IPs."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        bad_file = repo / "network.py"
        bad_file.write_text('GATEWAY = "172.16.0.1"\n')
        subprocess.run(
            ["git", "-C", str(repo), "add", "network.py"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add network"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, (
            "Hook should have blocked commit with private IP 172.16.0.1"
        )

    def test_blocks_ten_dot_ips(self, tmp_path):
        """Hook blocks 10.x.x.x private IPs (outside 10.100.*) in non-exempt files."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        bad_file = repo / "server.py"
        bad_file.write_text('HOST = "10.50.1.5"\n')
        subprocess.run(
            ["git", "-C", str(repo), "add", "server.py"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add server"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, (
            "Hook should have blocked commit with private IP 10.50.1.5"
        )

    def test_allows_anklume_convention_ips_in_exempt_files(self, tmp_path):
        """Hook allows 10.100.x.x IPs in exempt file types (*.md, docs/, tests/).

        Exempt patterns: *.example, docs/*, tests/*, README*, *.md
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        # Markdown files are exempt from IP checking
        md_file = repo / "notes.md"
        md_file.write_text("The server is at 10.100.1.5\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "notes.md"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add docs"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"Hook should allow IPs in exempt .md files.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_allows_clean_files(self, tmp_path):
        """Hook allows commits of files containing no private IPs."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        clean_file = repo / "utils.py"
        clean_file.write_text(
            "def greet(name):\n"
            '    return f"Hello, {name}!"\n'
        )
        subprocess.run(
            ["git", "-C", str(repo), "add", "utils.py"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add utils"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f"Hook should allow clean files without IPs.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_blocks_infra_yml(self, tmp_path):
        """Hook blocks staging of infra.yml (user-specific file)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        infra = repo / "infra.yml"
        infra.write_text("project_name: myinfra\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "infra.yml"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add infra"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, (
            "Hook should block infra.yml as user-specific file"
        )
        assert "BLOCKED" in result.stdout or "BLOCKED" in result.stderr

    def test_blocks_generated_files(self, tmp_path):
        """Hook blocks staging of generated Ansible files (inventory/, group_vars/, host_vars/)."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        # Create and stage a group_vars file
        gv_dir = repo / "group_vars"
        gv_dir.mkdir()
        gv_file = gv_dir / "pro.yml"
        gv_file.write_text("domain_name: pro\n")
        subprocess.run(
            ["git", "-C", str(repo), "add", "group_vars/pro.yml"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "add group_vars"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, (
            "Hook should block generated group_vars files"
        )

    def test_no_verify_marker_bypasses(self, tmp_path):
        """Hook exits 0 immediately when .anklume-no-verify exists."""
        repo = tmp_path / "repo"
        repo.mkdir()
        self._init_git_repo(repo)

        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        shutil.copy2(PRE_COMMIT_HOOK, hooks_dir / "pre-commit")

        # Create bypass marker
        (repo / ".anklume-no-verify").write_text("")

        # Stage a file that would normally be blocked
        bad_file = repo / "config.py"
        bad_file.write_text('SERVER = "192.168.1.1"\n')
        subprocess.run(
            ["git", "-C", str(repo), "add", "config.py"],
            capture_output=True, check=True,
        )

        result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "bypass test"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, (
            f".anklume-no-verify should bypass all checks.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ── TestTmuxDomainSwitch ──────────────────────────────────


class TestTmuxDomainSwitch:
    """Tests for the tmux domain switch hook (clipboard purge on domain change)."""

    def test_hook_exists(self):
        """tmux-domain-switch.sh exists and is executable."""
        assert TMUX_HOOK.exists()
        assert os.access(TMUX_HOOK, os.X_OK)

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed",
    )
    def test_shellcheck(self):
        """tmux-domain-switch.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(TMUX_HOOK)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"shellcheck errors:\n{result.stdout}\n{result.stderr}"
        )

    def test_domain_extraction_logic(self):
        """The sed pattern correctly extracts domain from pane titles.

        Pattern: sed -n 's/^\\[\\([^]]*\\)\\].*/\\1/p'
        Expected: "[domain] machine" -> "domain"
        """
        test_cases = [
            ("[pro] pro-dev", "pro"),
            ("[ai-tools] gpu-server", "ai-tools"),
            ("[anklume] anklume-instance", "anklume"),
            ("[perso] perso-desktop", "perso"),
            ("[my-domain] my-domain-worker", "my-domain"),
            # No domain bracket -> empty output (no match)
            ("plain terminal title", ""),
            ("", ""),
            # Bracket not at start -> no match
            ("prefix [domain] machine", ""),
            # Multiple brackets -> first one extracted
            ("[first] [second] rest", "first"),
        ]
        for title, expected in test_cases:
            result = subprocess.run(
                ["sed", "-n", r"s/^\[\([^]]*\)\].*/\1/p"],
                input=title,
                capture_output=True, text=True, timeout=5,
            )
            assert result.stdout.strip() == expected, (
                f"sed pattern on '{title}': "
                f"expected '{expected}', got '{result.stdout.strip()}'"
            )

    def test_state_file_created(self, tmp_path):
        """Running the hook with a mocked tmux creates the state file.

        Mocks tmux to return a pane title with a domain bracket, then
        verifies that ~/.anklume/tmux-last-domain is created with the
        correct domain name.
        """
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        # Create a mock tmux that returns a pane title
        mock_tmux = mock_bin / "tmux"
        mock_tmux.write_text(
            '#!/usr/bin/env bash\n'
            'echo "[pro] pro-dev"\n'
        )
        mock_tmux.chmod(0o755)

        # Create a mock clipboard.sh (the script calls it on domain change)
        scripts_dir = tmp_path / "scripts_parent" / "scripts"
        scripts_dir.mkdir(parents=True)
        mock_clipboard = scripts_dir / "clipboard.sh"
        mock_clipboard.write_text("#!/usr/bin/env bash\nexit 0\n")
        mock_clipboard.chmod(0o755)

        # Create the hooks dir mimicking the script's SCRIPT_DIR logic
        # SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)" -> scripts/
        # Then it calls "${SCRIPT_DIR}/clipboard.sh"
        hooks_dir = scripts_dir / "hooks"
        hooks_dir.mkdir()
        shutil.copy2(TMUX_HOOK, hooks_dir / "tmux-domain-switch.sh")

        fake_home = tmp_path / "home"
        fake_home.mkdir()

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            ["bash", str(hooks_dir / "tmux-domain-switch.sh")],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
        assert result.returncode == 0, (
            f"Hook should exit 0.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        state_file = fake_home / ".anklume" / "tmux-last-domain"
        assert state_file.exists(), "State file ~/.anklume/tmux-last-domain should be created"
        assert state_file.read_text() == "pro", (
            f"State file should contain 'pro', got '{state_file.read_text()}'"
        )

    def test_no_domain_exits_cleanly(self, tmp_path):
        """Hook exits 0 when pane title has no domain bracket."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        # Mock tmux returning a title without domain brackets
        mock_tmux = mock_bin / "tmux"
        mock_tmux.write_text(
            '#!/usr/bin/env bash\n'
            'echo "plain terminal"\n'
        )
        mock_tmux.chmod(0o755)

        # Set up script directory structure
        scripts_dir = tmp_path / "scripts_parent" / "scripts"
        scripts_dir.mkdir(parents=True)
        hooks_dir = scripts_dir / "hooks"
        hooks_dir.mkdir()
        shutil.copy2(TMUX_HOOK, hooks_dir / "tmux-domain-switch.sh")

        fake_home = tmp_path / "home"
        fake_home.mkdir()

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            ["bash", str(hooks_dir / "tmux-domain-switch.sh")],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
        assert result.returncode == 0, (
            f"Hook should exit 0 when no domain detected.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        state_file = fake_home / ".anklume" / "tmux-last-domain"
        assert not state_file.exists(), (
            "State file should NOT be created when no domain is detected"
        )

    def test_clipboard_purge_on_domain_change(self, tmp_path):
        """Hook calls clipboard.sh purge when domain changes."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        # Mock tmux returning a new domain
        mock_tmux = mock_bin / "tmux"
        mock_tmux.write_text(
            '#!/usr/bin/env bash\n'
            'echo "[perso] perso-desktop"\n'
        )
        mock_tmux.chmod(0o755)

        # Set up script directory structure
        scripts_dir = tmp_path / "scripts_parent" / "scripts"
        scripts_dir.mkdir(parents=True)

        # Create clipboard.sh that logs its invocation
        log_file = tmp_path / "clipboard.log"
        mock_clipboard = scripts_dir / "clipboard.sh"
        mock_clipboard.write_text(
            '#!/usr/bin/env bash\n'
            f'echo "$1" >> "{log_file}"\n'
        )
        mock_clipboard.chmod(0o755)

        hooks_dir = scripts_dir / "hooks"
        hooks_dir.mkdir()
        shutil.copy2(TMUX_HOOK, hooks_dir / "tmux-domain-switch.sh")

        fake_home = tmp_path / "home"
        fake_home.mkdir()

        # Pre-set state file to a different domain to trigger the switch
        anklume_dir = fake_home / ".anklume"
        anklume_dir.mkdir()
        state_file = anklume_dir / "tmux-last-domain"
        state_file.write_text("pro")

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            ["bash", str(hooks_dir / "tmux-domain-switch.sh")],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
        assert result.returncode == 0, (
            f"Hook should exit 0.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Verify clipboard.sh was called with "purge"
        assert log_file.exists(), "clipboard.sh should have been called"
        log_content = log_file.read_text().strip()
        assert log_content == "purge", (
            f"clipboard.sh should be called with 'purge', got '{log_content}'"
        )

        # Verify state file updated to new domain
        assert state_file.read_text() == "perso"

    def test_no_purge_when_same_domain(self, tmp_path):
        """Hook does NOT call clipboard.sh when staying in the same domain."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()

        mock_tmux = mock_bin / "tmux"
        mock_tmux.write_text(
            '#!/usr/bin/env bash\n'
            'echo "[pro] pro-dev"\n'
        )
        mock_tmux.chmod(0o755)

        scripts_dir = tmp_path / "scripts_parent" / "scripts"
        scripts_dir.mkdir(parents=True)

        log_file = tmp_path / "clipboard.log"
        mock_clipboard = scripts_dir / "clipboard.sh"
        mock_clipboard.write_text(
            '#!/usr/bin/env bash\n'
            f'echo "$1" >> "{log_file}"\n'
        )
        mock_clipboard.chmod(0o755)

        hooks_dir = scripts_dir / "hooks"
        hooks_dir.mkdir()
        shutil.copy2(TMUX_HOOK, hooks_dir / "tmux-domain-switch.sh")

        fake_home = tmp_path / "home"
        fake_home.mkdir()

        # Pre-set state file to the SAME domain
        anklume_dir = fake_home / ".anklume"
        anklume_dir.mkdir()
        state_file = anklume_dir / "tmux-last-domain"
        state_file.write_text("pro")

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            ["bash", str(hooks_dir / "tmux-domain-switch.sh")],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
        assert result.returncode == 0

        # clipboard.sh should NOT have been called
        assert not log_file.exists(), (
            "clipboard.sh should not be called when domain hasn't changed"
        )
