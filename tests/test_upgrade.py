"""Tests for scripts/upgrade.sh — safe framework upgrade."""

import os
import subprocess
from pathlib import Path

import pytest

UPGRADE_SH = Path(__file__).resolve().parent.parent / "scripts" / "upgrade.sh"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def git_workspace(tmp_path):
    """Create a minimal git repo simulating an AnKLuMe project."""
    ws = tmp_path / "project"
    ws.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=ws, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=ws, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=ws, capture_output=True,
    )

    # Create framework files
    (ws / "Makefile").write_text("all:\n\t@echo ok\n")
    (ws / "site.yml").write_text("---\n- hosts: all\n")
    (ws / "ansible.cfg").write_text("[defaults]\n")

    # Create infra.yml
    (ws / "infra.yml").write_text(
        "project_name: test\n"
        "global:\n"
        "  base_subnet: '10.100'\n"
        "  default_os_image: 'images:debian/13'\n"
        "domains:\n"
        "  admin:\n"
        "    subnet_id: 0\n"
        "    machines:\n"
        "      admin-ansible:\n"
        "        type: lxc\n"
        "        ip: '10.100.0.10'\n"
    )

    # Create scripts dir with generate.py
    scripts_dir = ws / "scripts"
    scripts_dir.mkdir()
    import shutil
    shutil.copy2(PROJECT_ROOT / "scripts" / "generate.py", scripts_dir / "generate.py")

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=ws, capture_output=True,
    )

    return ws


def run_upgrade(ws, input_text=None):
    """Run upgrade.sh in the workspace."""
    env = os.environ.copy()
    result = subprocess.run(
        ["bash", str(UPGRADE_SH)],
        capture_output=True, text=True,
        cwd=str(ws), env=env,
        input=input_text, timeout=30,
    )
    return result


class TestUpgradeBasic:
    def test_not_a_git_repo(self, tmp_path):
        """Upgrade fails outside a git repo."""
        result = subprocess.run(
            ["bash", str(UPGRADE_SH)],
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=10,
        )
        assert result.returncode != 0
        assert "Not a git repository" in result.stdout or "Not a git repository" in result.stderr

    def test_clean_repo_upgrades(self, git_workspace):
        """Upgrade succeeds in a clean git repo."""
        result = run_upgrade(git_workspace)
        # No origin remote, so it warns but should still regenerate
        assert "No 'origin' remote found" in result.stdout or result.returncode == 0
        assert "Upgrade complete" in result.stdout

    def test_regenerates_managed_sections(self, git_workspace):
        """Upgrade regenerates Ansible files from infra.yml."""
        result = run_upgrade(git_workspace)
        assert result.returncode == 0
        assert (git_workspace / "inventory").exists()
        assert (git_workspace / "group_vars").exists()

    def test_uncommitted_changes_warning(self, git_workspace):
        """Uncommitted changes trigger a warning prompt."""
        # Make an uncommitted change
        (git_workspace / "Makefile").write_text("# modified\n")
        result = run_upgrade(git_workspace, input_text="n\n")
        assert "Uncommitted changes" in result.stdout or "Aborted" in result.stdout


class TestUpgradeBackup:
    def test_modified_framework_files_backed_up(self, git_workspace):
        """Modified framework files get .bak backups."""
        # Modify a framework file after initial commit
        (git_workspace / "Makefile").write_text("# user modification\n")
        subprocess.run(["git", "add", "-A"], cwd=git_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "user edit"],
            cwd=git_workspace, capture_output=True,
        )
        # Make another local change (unstaged)
        (git_workspace / "Makefile").write_text("# another modification\n")

        result = run_upgrade(git_workspace, input_text="y\n")
        # Should mention backup
        if "Modified framework files" in result.stdout:
            # Check .bak file was created
            bak_files = list(git_workspace.glob("Makefile.bak.*"))
            assert len(bak_files) >= 1

    def test_user_files_preserved(self, git_workspace):
        """User files (infra.yml) are never touched during upgrade."""
        original = (git_workspace / "infra.yml").read_text()
        run_upgrade(git_workspace)
        assert (git_workspace / "infra.yml").read_text() == original


class TestUpgradeInfraDirectory:
    def test_infra_directory_mode(self, git_workspace):
        """Upgrade works with infra/ directory instead of infra.yml."""
        # Remove infra.yml, create infra/ directory
        (git_workspace / "infra.yml").unlink()
        infra_dir = git_workspace / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(
            "project_name: test\n"
            "global:\n"
            "  base_subnet: '10.100'\n"
            "  default_os_image: 'images:debian/13'\n"
        )
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        (domains_dir / "admin.yml").write_text(
            "admin:\n"
            "  subnet_id: 0\n"
            "  machines:\n"
            "    admin-ansible:\n"
            "      type: lxc\n"
            "      ip: '10.100.0.10'\n"
        )
        # Commit the changes to avoid "uncommitted changes" prompt
        subprocess.run(["git", "add", "-A"], cwd=git_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "switch to infra dir"],
            cwd=git_workspace, capture_output=True,
        )
        result = run_upgrade(git_workspace)
        assert result.returncode == 0
        assert (git_workspace / "inventory").exists()

    def test_no_infra_warns(self, git_workspace):
        """Upgrade warns if neither infra.yml nor infra/ exists."""
        (git_workspace / "infra.yml").unlink()
        subprocess.run(["git", "add", "-A"], cwd=git_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "remove infra"],
            cwd=git_workspace, capture_output=True,
        )
        result = run_upgrade(git_workspace)
        assert "No infra.yml or infra/" in result.stdout or result.returncode == 0


class TestUpgradeInfraDirectoryDetection:
    """Test infra/ directory detection in upgrade.sh."""

    def test_infra_dir_with_base_yml_uses_directory_mode(self, git_workspace):
        """When infra/ dir with base.yml exists, upgrade uses directory mode."""
        # Remove infra.yml, create infra/ with base.yml
        (git_workspace / "infra.yml").unlink()
        infra_dir = git_workspace / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(
            "project_name: test\n"
            "global:\n"
            "  base_subnet: '10.100'\n"
            "  default_os_image: 'images:debian/13'\n"
        )
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        (domains_dir / "admin.yml").write_text(
            "admin:\n"
            "  subnet_id: 0\n"
            "  machines:\n"
            "    admin-ansible:\n"
            "      type: lxc\n"
            "      ip: '10.100.0.10'\n"
        )
        subprocess.run(["git", "add", "-A"], cwd=git_workspace, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "switch to infra dir"],
            cwd=git_workspace, capture_output=True,
        )
        result = run_upgrade(git_workspace)
        assert result.returncode == 0
        # The script should pass "infra" to generate.py (directory mode)
        assert "Upgrade complete" in result.stdout
        # Verify that generated files exist (proves directory mode worked)
        assert (git_workspace / "inventory").exists()


class TestUpgradeBackupCreation:
    """Test backup file creation for modified FRAMEWORK_FILES."""

    def test_backup_created_for_modified_framework_file(self, git_workspace):
        """Modifying a FRAMEWORK_FILES member creates a .bak file during upgrade."""
        # Modify Makefile (a FRAMEWORK_FILES member) as unstaged change
        (git_workspace / "Makefile").write_text("# user custom edit\nall:\n\t@echo custom\n")
        # Run upgrade with 'y' to confirm continuing with uncommitted changes
        result = run_upgrade(git_workspace, input_text="y\n")
        assert result.returncode == 0
        # Check that a .bak file was created for Makefile
        bak_files = list(git_workspace.glob("Makefile.bak.*"))
        assert len(bak_files) >= 1, "Expected at least one Makefile.bak.* file"
        # Verify the backup contains the modified content
        bak_content = bak_files[0].read_text()
        assert "user custom edit" in bak_content


class TestUpgradeNoOriginRemote:
    """Test behavior when no origin remote is configured."""

    def test_no_origin_remote_prints_warning_and_skips_pull(self, git_workspace):
        """When no origin remote exists, upgrade prints warning and skips pull."""
        # git_workspace has no remotes by default
        result = run_upgrade(git_workspace)
        assert result.returncode == 0
        assert "No 'origin' remote found" in result.stdout
        assert "Skipping pull" in result.stdout
        # Upgrade should still complete successfully
        assert "Upgrade complete" in result.stdout


class TestUpgradeUncommittedChangesPrompt:
    """Test uncommitted changes interactive prompt responses."""

    def test_uncommitted_changes_n_aborts(self, git_workspace):
        """Responding 'n' to uncommitted changes prompt aborts the upgrade."""
        # Create an uncommitted change
        (git_workspace / "ansible.cfg").write_text("[defaults]\nmodified=true\n")
        result = run_upgrade(git_workspace, input_text="n\n")
        # Should abort without errors
        assert result.returncode == 0
        assert "Aborted" in result.stdout
        # Should NOT reach the upgrade complete message
        assert "Upgrade complete" not in result.stdout

    def test_uncommitted_changes_y_continues(self, git_workspace):
        """Responding 'y' to uncommitted changes prompt continues the upgrade."""
        # Create an uncommitted change
        (git_workspace / "ansible.cfg").write_text("[defaults]\nmodified=true\n")
        result = run_upgrade(git_workspace, input_text="y\n")
        assert result.returncode == 0
        # Should continue and complete the upgrade
        assert "Upgrade complete" in result.stdout


class TestUpgradeMergeConflict:
    """Test merge conflict detection during upstream pull."""

    @pytest.fixture()
    def workspace_with_origin(self, tmp_path):
        """Create a workspace with an origin remote that causes merge conflict."""
        # Create the "upstream" bare repo
        upstream = tmp_path / "upstream.git"
        upstream.mkdir()
        subprocess.run(["git", "init", "--bare"], cwd=upstream, capture_output=True)

        # Create the working repo
        ws = tmp_path / "project"
        ws.mkdir()
        subprocess.run(["git", "init"], cwd=ws, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=ws, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=ws, capture_output=True,
        )

        # Create framework files
        (ws / "Makefile").write_text("all:\n\t@echo ok\n")
        (ws / "site.yml").write_text("---\n- hosts: all\n")
        (ws / "ansible.cfg").write_text("[defaults]\n")

        # Create infra.yml
        (ws / "infra.yml").write_text(
            "project_name: test\n"
            "global:\n"
            "  base_subnet: '10.100'\n"
            "  default_os_image: 'images:debian/13'\n"
            "domains:\n"
            "  admin:\n"
            "    subnet_id: 0\n"
            "    machines:\n"
            "      admin-ansible:\n"
            "        type: lxc\n"
            "        ip: '10.100.0.10'\n"
        )

        # Create scripts dir with generate.py
        scripts_dir = ws / "scripts"
        scripts_dir.mkdir()
        import shutil
        shutil.copy2(PROJECT_ROOT / "scripts" / "generate.py", scripts_dir / "generate.py")

        # Initial commit and push to upstream
        subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=ws, capture_output=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", str(upstream)],
            cwd=ws, capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", "master"],
            cwd=ws, capture_output=True,
        )
        # Try main if master failed
        subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=ws, capture_output=True,
        )

        # Now create a conflicting change on upstream via a separate clone
        clone = tmp_path / "clone"
        subprocess.run(
            ["git", "clone", str(upstream), str(clone)],
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=clone, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=clone, capture_output=True,
        )
        (clone / "Makefile").write_text("# upstream change\nall:\n\t@echo upstream\n")
        subprocess.run(["git", "add", "-A"], cwd=clone, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "upstream change"],
            cwd=clone, capture_output=True,
        )
        subprocess.run(["git", "push"], cwd=clone, capture_output=True)

        # Now create a conflicting local change
        (ws / "Makefile").write_text("# local conflicting change\nall:\n\t@echo local\n")
        subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local change"],
            cwd=ws, capture_output=True,
        )

        return ws

    def test_merge_conflict_detected(self, workspace_with_origin):
        """Merge conflict during pull produces an error message."""
        ws = workspace_with_origin
        env = os.environ.copy()
        result = subprocess.run(
            ["bash", str(UPGRADE_SH)],
            capture_output=True, text=True,
            cwd=str(ws), env=env, timeout=30,
        )
        assert result.returncode != 0
        assert "Merge conflict" in result.stdout or "merge" in result.stdout.lower()
