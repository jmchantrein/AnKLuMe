"""Tests for scripts/update-check.sh — login update checker.

Covers: script existence, shellcheck, --help equivalent (no args),
non-git directory, fresh cache, stale cache, local==remote, local behind.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "update-check.sh"


class TestUpdateCheck:
    """Tests for update-check.sh behavior."""

    def test_script_exists(self):
        """update-check.sh exists and is executable."""
        assert SCRIPT.exists()
        assert os.access(SCRIPT, os.X_OK)

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed",
    )
    def test_shellcheck(self):
        """update-check.sh passes shellcheck."""
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(SCRIPT)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, (
            f"shellcheck errors:\n{result.stdout}\n{result.stderr}"
        )

    def test_non_git_directory_exits_zero(self, tmp_path):
        """Running against a non-git directory exits 0 silently."""
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), str(non_git_dir)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_fresh_cache_prints_cached_message(self, tmp_path):
        """When cache is fresh, prints cached message and does not fetch."""
        # Create a fake git repo so the script doesn't exit early
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init"], cwd=str(repo),
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, timeout=10,
            env={**os.environ, "GIT_AUTHOR_NAME": "test",
                 "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test",
                 "GIT_COMMITTER_EMAIL": "t@t"},
        )

        # Create a fresh cache file with a known message
        cache_dir = tmp_path / ".anklume"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "update-check-cache"
        cache_file.write_text("cached update message")
        # Touch to ensure it's fresh (just created = fresh)

        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), str(repo)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert "cached update message" in result.stdout

    def test_fresh_empty_cache_no_output(self, tmp_path):
        """When cache is fresh and empty, no output is produced."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(
            ["git", "init"], cwd=str(repo),
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, timeout=10,
            env={**os.environ, "GIT_AUTHOR_NAME": "test",
                 "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test",
                 "GIT_COMMITTER_EMAIL": "t@t"},
        )

        cache_dir = tmp_path / ".anklume"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "update-check-cache"
        cache_file.write_text("")  # Empty cache = up to date

        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), str(repo)],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_stale_cache_triggers_fetch(self, tmp_path):
        """When cache is stale (old mtime), the script attempts git fetch."""
        repo = tmp_path / "repo"
        repo.mkdir()
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(
            ["git", "init"], cwd=str(repo),
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, timeout=10, env=git_env,
        )
        # Add a non-existent remote so fetch will fail (network isolation)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             "https://invalid.example.com/no-such-repo.git"],
            capture_output=True, timeout=10,
        )

        # Create a stale cache file (mtime 2 hours ago)
        cache_dir = tmp_path / ".anklume"
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "update-check-cache"
        cache_file.write_text("old message")
        old_time = time.time() - 7200  # 2 hours ago
        os.utime(str(cache_file), (old_time, old_time))

        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), str(repo)],
            capture_output=True, text=True, env=env, timeout=15,
        )
        # Script exits 0 even when fetch fails (network unavailable path)
        assert result.returncode == 0
        # After a failed fetch, the cache should be cleared (empty)
        assert cache_file.read_text() == ""

    def test_local_equals_remote_empty_cache(self, tmp_path):
        """When local HEAD equals remote HEAD, cache is written empty."""
        repo = tmp_path / "repo"
        repo.mkdir()
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(
            ["git", "init", "--initial-branch=main"], cwd=str(repo),
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, timeout=10, env=git_env,
        )

        # Create a bare remote and push to it so local == remote
        remote_repo = tmp_path / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote_repo)],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             str(remote_repo)],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "push", "-u", "origin", "main"],
            capture_output=True, timeout=10, env=git_env,
        )

        # No cache file — force a fetch
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), str(repo)],
            capture_output=True, text=True, env=env, timeout=15,
        )
        assert result.returncode == 0
        cache_file = tmp_path / ".anklume" / "update-check-cache"
        assert cache_file.exists()
        # Cache should be empty (no updates)
        assert cache_file.read_text() == ""

    def test_local_behind_remote_shows_updates(self, tmp_path):
        """When local is behind remote, message says N update(s) available."""
        repo = tmp_path / "repo"
        repo.mkdir()
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(
            ["git", "init", "--initial-branch=main"], cwd=str(repo),
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"],
            capture_output=True, timeout=10, env=git_env,
        )

        # Create bare remote and push
        remote_repo = tmp_path / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main",
             str(remote_repo)],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             str(remote_repo)],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "-C", str(repo), "push", "-u", "origin", "main"],
            capture_output=True, timeout=10, env=git_env,
        )

        # Clone to a second repo, add commits, push
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", "-b", "main", str(remote_repo), str(clone)],
            capture_output=True, timeout=10, env=git_env,
        )
        for i in range(3):
            subprocess.run(
                ["git", "-C", str(clone), "commit",
                 "--allow-empty", "-m", f"update {i}"],
                capture_output=True, timeout=10, env=git_env,
            )
        subprocess.run(
            ["git", "-C", str(clone), "push", "origin", "main"],
            capture_output=True, timeout=10, env=git_env,
        )

        # Now repo is 3 commits behind origin/main
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(SCRIPT), str(repo)],
            capture_output=True, text=True, env=env, timeout=15,
        )
        assert result.returncode == 0
        assert "update(s) available" in result.stdout
        assert "3" in result.stdout
        # Cache file should also contain the message
        cache_file = tmp_path / ".anklume" / "update-check-cache"
        assert cache_file.exists()
        assert "update(s) available" in cache_file.read_text()
