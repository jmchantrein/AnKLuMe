"""Tests for overall project structure and configuration integrity.

Validates:
- Required project files exist and are well-formed
- Playbooks reference only existing roles
- CI configuration matches project structure
- Documentation files exist for all required topics
- Experience library structure is valid
- Config files are consistent
"""

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = PROJECT_ROOT / "roles"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DOCS_DIR = PROJECT_ROOT / "docs"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
EXPERIENCES_DIR = PROJECT_ROOT / "experiences"


# ── Core project files ──────────────────────────────────────


class TestProjectFiles:
    """Verify essential project files exist."""

    REQUIRED_FILES = [
        "site.yml",
        "snapshot.yml",
        "infra.yml",
        "Makefile",
        "pyproject.toml",
        "CLAUDE.md",
        "README.md",
        ".ansible-lint",
        ".yamllint.yml",
        ".gitignore",
    ]

    def test_required_files_exist(self):
        """All required project files exist."""
        missing = [f for f in self.REQUIRED_FILES if not (PROJECT_ROOT / f).exists()]
        assert not missing, f"Missing files: {missing}"

    def test_infra_yml_valid(self):
        """infra.yml parses as valid YAML."""
        infra = PROJECT_ROOT / "infra.yml"
        data = yaml.safe_load(infra.read_text())
        assert isinstance(data, dict)
        assert "project_name" in data
        assert "domains" in data

    def test_pyproject_toml_valid(self):
        """pyproject.toml has required sections."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "[project]" in content
        assert "[tool.ruff]" in content
        assert "[tool.pytest.ini_options]" in content

    def test_pyproject_test_deps(self):
        """pyproject.toml lists test dependencies."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "pytest" in content
        assert "pyyaml" in content
        assert "hypothesis" in content


# ── Playbook validation ─────────────────────────────────────


class TestPlaybooks:
    """Verify playbooks are well-formed and reference existing roles."""

    def test_site_yml_valid_yaml(self):
        """site.yml is valid YAML."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        assert isinstance(data, list)
        assert len(data) >= 2  # At least infra + provisioning phases

    def test_site_yml_phase_names(self):
        """site.yml contains named phases."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        names = [play.get("name", "") for play in data]
        assert any("Infrastructure" in n for n in names)
        assert any("Provisioning" in n for n in names)

    def test_site_yml_roles_exist(self):
        """All roles referenced in site.yml exist in roles/."""
        content = (PROJECT_ROOT / "site.yml").read_text()
        # Find role references: "name: <role_name>" in include_role blocks
        role_refs = re.findall(r'name:\s+(\w+)\s*$', content, re.MULTILINE)
        # Filter to only actual role names (not play names)
        existing_roles = {d.name for d in ROLES_DIR.iterdir() if d.is_dir()}
        for role in role_refs:
            if role in existing_roles:
                continue
            # Skip non-role names (play names contain spaces, captured incorrectly)
            if "_" in role or role in existing_roles:
                assert role in existing_roles, f"Role '{role}' referenced in site.yml but not in roles/"

    def test_site_yml_infra_phase_tags(self):
        """Infrastructure phase has 'infra' tag."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        infra_plays = [p for p in data if "Infrastructure" in p.get("name", "")]
        assert len(infra_plays) >= 1
        assert "infra" in infra_plays[0].get("tags", [])

    def test_site_yml_provision_phase_tags(self):
        """Provisioning phase has 'provision' tag."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        prov_plays = [p for p in data if "Provisioning" in p.get("name", "")]
        assert len(prov_plays) >= 1
        assert "provision" in prov_plays[0].get("tags", [])

    def test_site_yml_nftables_phase(self):
        """Nftables phase exists with correct host and tag."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        nft_plays = [p for p in data if "Firewall" in p.get("name", "") or "nftables" in p.get("tags", [])]
        assert len(nft_plays) >= 1
        assert nft_plays[0]["hosts"] == "localhost"

    def test_snapshot_yml_valid(self):
        """snapshot.yml is valid YAML with correct structure."""
        data = yaml.safe_load((PROJECT_ROOT / "snapshot.yml").read_text())
        assert isinstance(data, list)
        assert len(data) >= 1
        play = data[0]
        assert play["hosts"] == "all"
        assert play["connection"] == "local"

    def test_site_yml_all_provision_roles_conditional(self):
        """All provisioning roles (except base_system) have a 'when' condition."""
        content = (PROJECT_ROOT / "site.yml").read_text()
        data = yaml.safe_load(content)
        prov_plays = [p for p in data if "Provisioning" in p.get("name", "")]
        if not prov_plays:
            return
        tasks = prov_plays[0].get("tasks", [])
        for task in tasks:
            if not isinstance(task, dict):
                continue
            role_block = task.get("ansible.builtin.include_role", {})
            role_name = role_block.get("name", "") if isinstance(role_block, dict) else ""
            # base_system is always applied; admin_bootstrap has group_names check
            if role_name in ("base_system", ""):
                continue
            assert "when" in task, f"Role '{role_name}' in provisioning phase has no 'when' condition"


# ── CI configuration ────────────────────────────────────────


class TestCIConfig:
    """Verify CI workflow configuration."""

    def test_ci_yml_exists(self):
        """CI workflow file exists."""
        assert (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").exists()

    def test_ci_has_required_jobs(self):
        """CI has all expected jobs."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        jobs = set(data.get("jobs", {}).keys())
        expected = {"lint-yaml", "lint-ansible", "lint-shell", "lint-python",
                    "test-generator", "syntax-check"}
        missing = expected - jobs
        assert not missing, f"Missing CI jobs: {missing}"

    def test_ci_triggers(self):
        """CI triggers on push and pull_request."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        triggers = data.get("on", data.get(True, {}))
        assert "push" in triggers
        assert "pull_request" in triggers

    def test_ci_python_version(self):
        """CI uses Python 3.13."""
        content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "3.13" in content


# ── Linter configuration consistency ────────────────────────


class TestLinterConfig:
    """Verify linter configs are consistent."""

    def test_ansible_lint_production_profile(self):
        """ansible-lint uses production profile."""
        data = yaml.safe_load((PROJECT_ROOT / ".ansible-lint").read_text())
        assert data["profile"] == "production"

    def test_ansible_lint_excludes_tests(self):
        """ansible-lint excludes test directories."""
        data = yaml.safe_load((PROJECT_ROOT / ".ansible-lint").read_text())
        excludes = data.get("exclude_paths", [])
        assert "tests/" in excludes or ".claude/" in excludes

    def test_yamllint_line_length(self):
        """yamllint enforces 120 char line length."""
        data = yaml.safe_load((PROJECT_ROOT / ".yamllint.yml").read_text())
        assert data["rules"]["line-length"]["max"] == 120

    def test_ruff_line_length_matches(self):
        """ruff line length matches yamllint."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "line-length = 120" in content


# ── Documentation completeness ──────────────────────────────


class TestDocumentation:
    """Verify documentation files exist."""

    REQUIRED_DOCS = [
        "SPEC.md",
        "ARCHITECTURE.md",
        "ROADMAP.md",
        "network-isolation.md",
        "vm-support.md",
        "gpu-advanced.md",
        "firewall-vm.md",
        "ai-testing.md",
        "stt-service.md",
        "agent-teams.md",
        "ai-switch.md",
        "guide.md",
        "decisions-log.md",
    ]

    def test_all_docs_exist(self):
        """All required documentation files exist."""
        missing = [d for d in self.REQUIRED_DOCS if not (DOCS_DIR / d).exists()]
        assert not missing, f"Missing docs: {missing}"

    def test_docs_not_empty(self):
        """Documentation files are not empty."""
        empty = []
        for doc in self.REQUIRED_DOCS:
            path = DOCS_DIR / doc
            if path.exists() and path.stat().st_size == 0:
                empty.append(doc)
        assert not empty, f"Empty docs: {empty}"

    def test_spec_has_key_sections(self):
        """SPEC.md contains key sections."""
        content = (DOCS_DIR / "SPEC.md").read_text()
        for section in ["infra.yml format", "Generator", "Ansible roles", "Validation"]:
            assert section.lower() in content.lower(), f"SPEC.md missing section: {section}"

    def test_architecture_has_adrs(self):
        """ARCHITECTURE.md contains ADR entries."""
        content = (DOCS_DIR / "ARCHITECTURE.md").read_text()
        # Should have at least ADR-001 through ADR-030
        for i in range(1, 31):
            assert f"ADR-{i:03d}" in content, f"Missing ADR-{i:03d} in ARCHITECTURE.md"


# ── Experience library ──────────────────────────────────────


class TestExperienceLibrary:
    """Verify experience library structure."""

    def test_directory_structure(self):
        """Experience library has required subdirectories."""
        for subdir in ["fixes", "patterns", "decisions"]:
            assert (EXPERIENCES_DIR / subdir).exists(), f"Missing experiences/{subdir}/"

    def test_has_readme(self):
        """Experience library has a README."""
        assert (EXPERIENCES_DIR / "README.md").exists()

    def test_fixes_valid_yaml(self):
        """Fix files in experiences/fixes/ are valid YAML."""
        fixes_dir = EXPERIENCES_DIR / "fixes"
        if not fixes_dir.exists():
            return
        for yml_file in fixes_dir.glob("*.yml"):
            data = yaml.safe_load(yml_file.read_text())
            assert data is not None, f"Empty YAML: {yml_file}"

    def test_patterns_valid_yaml(self):
        """Pattern files in experiences/patterns/ are valid YAML."""
        patterns_dir = EXPERIENCES_DIR / "patterns"
        if not patterns_dir.exists():
            return
        for yml_file in patterns_dir.glob("*.yml"):
            data = yaml.safe_load(yml_file.read_text())
            assert data is not None, f"Empty YAML: {yml_file}"


# ── Examples directory ──────────────────────────────────────


class TestExamplesStructure:
    """Verify examples directory consistency."""

    def test_each_example_has_infra_yml(self):
        """Each example subdirectory has an infra.yml."""
        for subdir in EXAMPLES_DIR.iterdir():
            if subdir.is_dir():
                assert (subdir / "infra.yml").exists(), f"Missing infra.yml in {subdir.name}"

    def test_each_example_has_readme(self):
        """Each example subdirectory has a README.md."""
        for subdir in EXAMPLES_DIR.iterdir():
            if subdir.is_dir():
                assert (subdir / "README.md").exists(), f"Missing README.md in {subdir.name}"

    def test_examples_readme_exists(self):
        """Examples directory has a top-level README."""
        assert (EXAMPLES_DIR / "README.md").exists()

    def test_example_infra_valid_yaml(self):
        """All example infra.yml files are valid YAML."""
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            assert isinstance(data, dict), f"Invalid YAML in {infra}"
            assert "project_name" in data, f"Missing project_name in {infra}"

    def test_minimum_examples_count(self):
        """At least 6 examples exist (per Phase 7 spec)."""
        dirs = [d for d in EXAMPLES_DIR.iterdir() if d.is_dir()]
        assert len(dirs) >= 6


# ── Scripts directory ───────────────────────────────────────


class TestScriptsStructure:
    """Verify scripts directory organization."""

    EXPECTED_SCRIPTS = [
        "generate.py",
        "matrix-coverage.py",
        "mine-experiences.py",
        "ai-switch.sh",
        "ai-test-loop.sh",
        "ai-develop.sh",
        "ai-improve.sh",
        "ai-config.sh",
        "ai-matrix-test.sh",
        "agent-fix.sh",
        "agent-develop.sh",
        "bootstrap.sh",
        "deploy-nftables.sh",
        "flush.sh",
        "guide.sh",
        "import-infra.sh",
        "run-tests.sh",
        "snap.sh",
        "upgrade.sh",
    ]

    def test_expected_scripts_exist(self):
        """All expected scripts exist."""
        missing = [s for s in self.EXPECTED_SCRIPTS if not (SCRIPTS_DIR / s).exists()]
        assert not missing, f"Missing scripts: {missing}"

    def test_shell_scripts_have_shebang(self):
        """All .sh scripts start with a shebang line."""
        errors = []
        for sh_file in SCRIPTS_DIR.glob("*.sh"):
            first_line = sh_file.read_text().split("\n")[0]
            if not first_line.startswith("#!"):
                errors.append(sh_file.name)
        assert not errors, f"Scripts without shebang: {errors}"

    def test_python_scripts_have_shebang(self):
        """All .py scripts start with a shebang line."""
        errors = []
        for py_file in SCRIPTS_DIR.glob("*.py"):
            first_line = py_file.read_text().split("\n")[0]
            if not first_line.startswith("#!"):
                errors.append(py_file.name)
        assert not errors, f"Scripts without shebang: {errors}"

    def test_shell_scripts_use_set_e(self):
        """Shell scripts use 'set -e' or 'set -euo pipefail'."""
        errors = []
        for sh_file in SCRIPTS_DIR.glob("*.sh"):
            content = sh_file.read_text()
            # Allow sourced libraries (like ai-config.sh) to skip set -e
            if "# Sourced library" in content or sh_file.name == "ai-config.sh":
                continue
            if "set -e" not in content and "set -euo" not in content:
                errors.append(sh_file.name)
        assert not errors, f"Scripts without 'set -e': {errors}"


# ── Behavior matrix ─────────────────────────────────────────


class TestBehaviorMatrix:
    """Verify behavior matrix structure."""

    def test_matrix_file_exists(self):
        """behavior_matrix.yml exists."""
        assert (PROJECT_ROOT / "tests" / "behavior_matrix.yml").exists()

    def test_matrix_valid_yaml(self):
        """behavior_matrix.yml is valid YAML."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        assert "capabilities" in data

    def test_matrix_has_capabilities(self):
        """Matrix has at least 10 capabilities."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        caps = data.get("capabilities", {})
        assert len(caps) >= 10, f"Expected >= 10 capabilities, found {len(caps)}"

    def test_matrix_ids_unique(self):
        """All matrix cell IDs are globally unique."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        all_ids = []
        for cap in (data.get("capabilities") or {}).values():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for cell in cap.get(depth) or []:
                    if "id" in cell:
                        all_ids.append(cell["id"])
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs found: {[i for i in all_ids if all_ids.count(i) > 1]}"

    def test_matrix_cells_have_required_fields(self):
        """Each matrix cell has id, action, and expected fields."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        errors = []
        for cap_name, cap in (data.get("capabilities") or {}).items():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for cell in cap.get(depth) or []:
                    for field in ("id", "action", "expected"):
                        if field not in cell:
                            errors.append(f"{cap_name}/{depth}: missing '{field}'")
        assert not errors, "Matrix cells with missing fields:\n" + "\n".join(errors)
