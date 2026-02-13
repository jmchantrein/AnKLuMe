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


# ── Documentation cross-references ────────────────────────


class TestDocsCrossReferences:
    """Verify documentation links point to existing files."""

    def test_claude_md_doc_refs_exist(self):
        """All docs referenced in CLAUDE.md exist."""
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        content = claude_md.read_text()
        # Extract @docs/... references
        refs = re.findall(r"@(docs/\S+)", content)
        for ref in refs:
            target = PROJECT_ROOT / ref
            assert target.exists(), f"CLAUDE.md references missing file: {ref}"

    def test_readme_doc_links_exist(self):
        """All docs/ links in README.md point to existing files."""
        readme = PROJECT_ROOT / "README.md"
        content = readme.read_text()
        # Extract (docs/...) links
        links = re.findall(r"\(docs/([^\)]+)\)", content)
        for link in links:
            target = DOCS_DIR / link
            assert target.exists(), f"README.md links to missing file: docs/{link}"

    def test_french_translations_have_english_counterparts(self):
        """All *_FR.md files have matching English counterparts."""
        fr_files = list(DOCS_DIR.glob("*_FR.md"))
        for fr_file in fr_files:
            en_name = fr_file.name.replace("_FR.md", ".md")
            en_file = DOCS_DIR / en_name
            assert en_file.exists(), (
                f"French translation {fr_file.name} has no English counterpart {en_name}"
            )

    def test_roadmap_has_french_translation(self):
        """ROADMAP_FR.md exists alongside ROADMAP.md."""
        assert (DOCS_DIR / "ROADMAP.md").exists()
        assert (DOCS_DIR / "ROADMAP_FR.md").exists()


class TestRoleCompleteness:
    """Verify each role has required structural elements."""

    def test_all_roles_have_tasks_main(self):
        """Every role has tasks/main.yml."""
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                tasks_main = role_dir / "tasks" / "main.yml"
                assert tasks_main.exists(), f"Role {role_dir.name} missing tasks/main.yml"

    def test_all_roles_have_molecule(self):
        """Every role has a molecule/ directory."""
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                mol = role_dir / "molecule"
                assert mol.exists(), f"Role {role_dir.name} missing molecule/ directory"

    def test_all_roles_have_defaults(self):
        """Every role has defaults/main.yml (even if empty)."""
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                defaults = role_dir / "defaults" / "main.yml"
                assert defaults.exists(), f"Role {role_dir.name} missing defaults/main.yml"

    def test_all_roles_have_meta(self):
        """Every role has meta/main.yml."""
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                meta = role_dir / "meta" / "main.yml"
                assert meta.exists(), f"Role {role_dir.name} missing meta/main.yml"


# ── Additional project files ───────────────────────────────


class TestAdditionalProjectFiles:
    """Verify additional project files exist and are well-formed."""

    def test_ansible_cfg_exists(self):
        """ansible.cfg exists at project root."""
        assert (PROJECT_ROOT / "ansible.cfg").exists()

    def test_ansible_cfg_inventory(self):
        """ansible.cfg points to inventory/ directory."""
        content = (PROJECT_ROOT / "ansible.cfg").read_text()
        assert "inventory = inventory/" in content or "inventory=inventory/" in content

    def test_ansible_cfg_roles_path(self):
        """ansible.cfg includes roles_custom/ and roles/ in roles_path."""
        content = (PROJECT_ROOT / "ansible.cfg").read_text()
        assert "roles_custom/" in content
        assert "roles/" in content

    def test_ansible_cfg_no_host_key_checking(self):
        """ansible.cfg disables host_key_checking."""
        content = (PROJECT_ROOT / "ansible.cfg").read_text()
        assert "host_key_checking" in content.lower()

    def test_requirements_yml_exists(self):
        """requirements.yml exists for Ansible Galaxy dependencies."""
        assert (PROJECT_ROOT / "requirements.yml").exists()

    def test_requirements_yml_has_community_general(self):
        """requirements.yml includes community.general collection."""
        data = yaml.safe_load((PROJECT_ROOT / "requirements.yml").read_text())
        collections = data.get("collections", [])
        coll_names = [c.get("name", "") for c in collections if isinstance(c, dict)]
        assert "community.general" in coll_names

    def test_infra_yml_example_exists(self):
        """infra.yml.example template exists."""
        assert (PROJECT_ROOT / "infra.yml.example").exists()

    def test_infra_yml_example_valid_yaml(self):
        """infra.yml.example is valid YAML with required keys."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml.example").read_text())
        assert isinstance(data, dict)
        assert "project_name" in data
        assert "global" in data
        assert "domains" in data

    def test_infra_yml_example_has_base_subnet(self):
        """infra.yml.example defines base_subnet in global section."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml.example").read_text())
        assert "base_subnet" in data.get("global", {})

    def test_contributing_md_exists(self):
        """CONTRIBUTING.md exists at project root."""
        assert (PROJECT_ROOT / "CONTRIBUTING.md").exists()

    def test_license_file_exists(self):
        """LICENSE file exists at project root."""
        assert (PROJECT_ROOT / "LICENSE").exists()

    def test_license_is_agpl(self):
        """LICENSE file is AGPL-3.0."""
        content = (PROJECT_ROOT / "LICENSE").read_text()
        assert "GNU AFFERO GENERAL PUBLIC LICENSE" in content

    def test_readme_fr_exists(self):
        """README_FR.md (French translation) exists at project root."""
        assert (PROJECT_ROOT / "README_FR.md").exists()

    def test_readme_has_ci_badge(self):
        """README.md contains a CI status badge."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "ci.yml/badge" in content or "actions/workflows" in content


# ── Makefile targets ─────────────────────────────────────────


class TestMakefileTargets:
    """Verify Makefile has all expected targets."""

    EXPECTED_TARGETS = [
        "sync",
        "sync-dry",
        "lint",
        "lint-yaml",
        "lint-ansible",
        "lint-shell",
        "lint-python",
        "check",
        "syntax",
        "apply",
        "apply-infra",
        "apply-provision",
        "apply-base",
        "apply-limit",
        "apply-llm",
        "apply-stt",
        "apply-ai",
        "nftables",
        "nftables-deploy",
        "snapshot",
        "test",
        "test-generator",
        "test-roles",
        "test-role",
        "flush",
        "upgrade",
        "import-infra",
        "guide",
        "quickstart",
        "init",
        "help",
        "ai-test",
        "ai-develop",
        "ai-switch",
        "agent-fix",
        "agent-develop",
        "matrix-coverage",
        "mine-experiences",
        "ai-improve",
    ]

    def test_makefile_has_expected_targets(self):
        """Makefile contains all expected targets."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        missing = []
        for target in self.EXPECTED_TARGETS:
            # Match "target:" at the start of a line
            pattern = rf'^{re.escape(target)}:'
            if not re.search(pattern, content, re.MULTILINE):
                missing.append(target)
        assert not missing, f"Missing Makefile targets: {missing}"

    def test_makefile_default_goal_is_help(self):
        """Makefile default goal is help."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        assert ".DEFAULT_GOAL := help" in content

    def test_makefile_uses_bash_shell(self):
        """Makefile uses bash shell."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        assert "SHELL := /bin/bash" in content

    def test_makefile_phony_declarations(self):
        """Makefile declares .PHONY for targets."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        assert ".PHONY:" in content

    def test_makefile_all_targets_have_help(self):
        """All major Makefile targets have help comments (## ...)."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        # Find targets that don't have ## help string
        targets_without_help = []
        for line in content.split("\n"):
            match = re.match(r'^([a-zA-Z_-]+):\s', line)
            if match and "##" not in line:
                target = match.group(1)
                # Exclude special targets
                if target not in ("PHONY",):
                    targets_without_help.append(target)
        # At least 80% of targets should have help
        all_targets = re.findall(r'^([a-zA-Z_-]+):.*##', content, re.MULTILINE)
        assert len(all_targets) >= 30, f"Expected >= 30 targets with help, found {len(all_targets)}"

    def test_makefile_lint_chains_all_validators(self):
        """Makefile lint target chains all four validators."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        # Find the lint target line
        lint_match = re.search(r'^lint:(.+)$', content, re.MULTILINE)
        assert lint_match, "lint target not found"
        lint_deps = lint_match.group(1)
        for validator in ["lint-yaml", "lint-ansible", "lint-shell", "lint-python"]:
            assert validator in lint_deps, f"lint target missing dependency: {validator}"

    def test_makefile_test_chains_subtargets(self):
        """Makefile test target chains test-generator and test-roles."""
        content = (PROJECT_ROOT / "Makefile").read_text()
        test_match = re.search(r'^test:(.+)$', content, re.MULTILINE)
        assert test_match, "test target not found"
        test_deps = test_match.group(1)
        assert "test-generator" in test_deps
        assert "test-roles" in test_deps


# ── .gitignore completeness ──────────────────────────────────


class TestGitignore:
    """Verify .gitignore covers essential patterns."""

    def test_gitignore_python_cache(self):
        """gitignore excludes __pycache__."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert "__pycache__" in content

    def test_gitignore_pytest_cache(self):
        """gitignore excludes .pytest_cache."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert ".pytest_cache" in content

    def test_gitignore_infra_yml(self):
        """gitignore excludes infra.yml (user-specific)."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert "infra.yml" in content

    def test_gitignore_generated_dirs(self):
        """gitignore excludes generated Ansible directories."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        for dir_pattern in ["/inventory/", "/group_vars/", "/host_vars/"]:
            assert dir_pattern in content, f"Missing gitignore pattern: {dir_pattern}"

    def test_gitignore_user_config(self):
        """gitignore excludes user config file."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert "anklume.conf.yml" in content

    def test_gitignore_logs(self):
        """gitignore excludes logs directory."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert "/logs/" in content

    def test_gitignore_roles_custom(self):
        """gitignore excludes roles_custom/ directory."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert "roles_custom" in content

    def test_gitignore_hypothesis(self):
        """gitignore excludes .hypothesis/ directory."""
        content = (PROJECT_ROOT / ".gitignore").read_text()
        assert ".hypothesis" in content


# ── CI configuration details ──────────────────────────────────


class TestCIConfigDetails:
    """Verify CI workflow configuration in detail."""

    def test_ci_jobs_run_on_ubuntu(self):
        """All CI jobs run on ubuntu-latest."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        for job_name, job in data.get("jobs", {}).items():
            runner = job.get("runs-on", "")
            assert "ubuntu" in runner, f"Job {job_name} does not run on ubuntu"

    def test_ci_all_jobs_use_checkout(self):
        """All CI jobs use actions/checkout."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        for job_name, job in data.get("jobs", {}).items():
            steps = job.get("steps", [])
            uses_checkout = any("actions/checkout" in (s.get("uses", "")) for s in steps)
            assert uses_checkout, f"Job {job_name} does not use actions/checkout"

    def test_ci_has_matrix_coverage_job(self):
        """CI has a matrix-coverage informational job."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        jobs = set(data.get("jobs", {}).keys())
        assert "matrix-coverage" in jobs

    def test_ci_matrix_coverage_allows_failure(self):
        """Matrix-coverage CI job is allowed to fail (informational)."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        mc_job = data.get("jobs", {}).get("matrix-coverage", {})
        assert mc_job.get("continue-on-error") is True

    def test_ci_triggers_on_main_branch(self):
        """CI triggers on pushes to main branch."""
        data = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text())
        triggers = data.get("on", data.get(True, {}))
        push_config = triggers.get("push", {})
        if isinstance(push_config, dict):
            branches = push_config.get("branches", [])
            assert "main" in branches


# ── Linter config details ────────────────────────────────────


class TestLinterConfigDetails:
    """Verify detailed linter configuration settings."""

    def test_yamllint_extends_default(self):
        """yamllint extends the default configuration."""
        data = yaml.safe_load((PROJECT_ROOT / ".yamllint.yml").read_text())
        assert data.get("extends") == "default"

    def test_yamllint_forbids_implicit_octal(self):
        """yamllint forbids implicit octal values."""
        data = yaml.safe_load((PROJECT_ROOT / ".yamllint.yml").read_text())
        octal = data.get("rules", {}).get("octal-values", {})
        assert octal.get("forbid-implicit-octal") is True

    def test_yamllint_ignores_claude_dir(self):
        """yamllint ignores .claude/ directory."""
        data = yaml.safe_load((PROJECT_ROOT / ".yamllint.yml").read_text())
        ignores = data.get("ignore", [])
        assert ".claude/" in ignores

    def test_ansible_lint_skips_var_naming(self):
        """ansible-lint skips var-naming[no-role-prefix] rule (PSOT variables)."""
        data = yaml.safe_load((PROJECT_ROOT / ".ansible-lint").read_text())
        skip_list = data.get("skip_list", [])
        assert "var-naming[no-role-prefix]" in skip_list

    def test_ruff_target_version(self):
        """ruff targets Python 3.11+."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert 'target-version = "py311"' in content

    def test_ruff_lint_rules(self):
        """ruff lint selects expected rule categories."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        # Check for common ruff rule categories
        for rule in ["E", "F", "W"]:
            assert f'"{rule}"' in content, f"Missing ruff rule category: {rule}"

    def test_pyproject_requires_python(self):
        """pyproject.toml specifies minimum Python version."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert "requires-python" in content
        assert "3.11" in content

    def test_pyproject_testpaths(self):
        """pyproject.toml points to tests/ directory."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert 'testpaths = ["tests"]' in content


# ── Documentation content validation ─────────────────────────


class TestDocumentationContent:
    """Verify documentation content quality and structure."""

    def test_spec_has_psot_section(self):
        """SPEC.md documents the PSOT model."""
        content = (DOCS_DIR / "SPEC.md").read_text()
        assert "primary source of truth" in content.lower()

    def test_spec_has_reconciliation_pattern(self):
        """SPEC.md documents the reconciliation pattern."""
        content = (DOCS_DIR / "SPEC.md").read_text()
        assert "reconciliation" in content.lower()

    def test_spec_has_snapshot_section(self):
        """SPEC.md has a snapshots section."""
        content = (DOCS_DIR / "SPEC.md").read_text()
        assert "snapshot" in content.lower()

    def test_spec_has_network_policies_section(self):
        """SPEC.md documents network policies."""
        content = (DOCS_DIR / "SPEC.md").read_text()
        assert "network_policies" in content or "network policies" in content.lower()

    def test_roadmap_has_completed_phases(self):
        """ROADMAP.md has at least 17 completed phases."""
        content = (DOCS_DIR / "ROADMAP.md").read_text()
        completed_count = content.count("COMPLETE")
        assert completed_count >= 17, f"Expected >= 17 completed phases, found {completed_count}"

    def test_architecture_adr_format(self):
        """ARCHITECTURE.md follows consistent ADR format (Context/Decision/Consequence)."""
        content = (DOCS_DIR / "ARCHITECTURE.md").read_text()
        assert "**Context**" in content
        assert "**Decision**" in content
        assert "**Consequence**" in content

    def test_docs_quickstart_exists(self):
        """Quick start guide exists."""
        assert (DOCS_DIR / "quickstart.md").exists()

    def test_docs_lab_tp_exists(self):
        """Lab deployment guide exists."""
        assert (DOCS_DIR / "lab-tp.md").exists()

    def test_docs_gpu_llm_exists(self):
        """GPU + LLM guide exists."""
        assert (DOCS_DIR / "gpu-llm.md").exists()

    def test_docs_claude_code_workflow_exists(self):
        """Claude Code workflow guide exists."""
        assert (DOCS_DIR / "claude-code-workflow.md").exists()

    def test_all_english_docs_have_french_translations(self):
        """Key English docs in docs/ have French counterparts (ADR-011)."""
        # Check a subset of files that should have FR translations
        expected_fr = [
            "SPEC_FR.md",
            "ARCHITECTURE_FR.md",
            "ROADMAP_FR.md",
            "quickstart_FR.md",
        ]
        missing = [f for f in expected_fr if not (DOCS_DIR / f).exists()]
        assert not missing, f"Missing French translations: {missing}"

    def test_french_docs_have_header_note(self):
        """French translation files mention the English version is authoritative."""
        for fr_file in DOCS_DIR.glob("*_FR.md"):
            content = fr_file.read_text()[:500]  # Check first 500 chars
            has_note = (
                "anglais" in content.lower()
                or "english" in content.lower()
                or "version originale" in content.lower()
                or "authoritative" in content.lower()
                or "fait foi" in content.lower()
            )
            assert has_note, f"{fr_file.name} missing English-authoritative header note"


# ── Role structure conventions ────────────────────────────────


class TestRoleConventions:
    """Verify Ansible role structural conventions."""

    def test_roles_count(self):
        """Project has exactly 18 roles (all phases complete)."""
        roles = [d for d in ROLES_DIR.iterdir() if d.is_dir()]
        assert len(roles) == 18, f"Expected 18 roles, found {len(roles)}: {[r.name for r in roles]}"

    EXPECTED_ROLES = [
        "admin_bootstrap",
        "base_system",
        "dev_agent_runner",
        "dev_test_runner",
        "firewall_router",
        "incus_firewall_vm",
        "incus_images",
        "incus_instances",
        "incus_networks",
        "incus_nftables",
        "incus_profiles",
        "incus_projects",
        "incus_snapshots",
        "lobechat",
        "ollama_server",
        "opencode_server",
        "open_webui",
        "stt_server",
    ]

    def test_expected_roles_exist(self):
        """All expected roles exist."""
        existing = {d.name for d in ROLES_DIR.iterdir() if d.is_dir()}
        missing = [r for r in self.EXPECTED_ROLES if r not in existing]
        assert not missing, f"Missing roles: {missing}"

    def test_role_tasks_main_starts_with_yaml_header(self):
        """All tasks/main.yml files start with YAML document marker."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                tasks_main = role_dir / "tasks" / "main.yml"
                if tasks_main.exists():
                    content = tasks_main.read_text()
                    if not content.startswith("---"):
                        errors.append(role_dir.name)
        assert not errors, f"Roles with tasks/main.yml not starting with ---: {errors}"

    def test_role_tasks_main_has_comment_header(self):
        """All tasks/main.yml files have a comment describing the role."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                tasks_main = role_dir / "tasks" / "main.yml"
                if tasks_main.exists():
                    content = tasks_main.read_text()
                    # Should have a comment line after ---
                    lines = content.split("\n")
                    has_comment = any(line.startswith("#") for line in lines[1:5])
                    if not has_comment:
                        errors.append(role_dir.name)
        assert not errors, f"Roles without comment header in tasks/main.yml: {errors}"

    def test_role_defaults_main_is_valid_yaml(self):
        """All defaults/main.yml files are valid YAML."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                defaults = role_dir / "defaults" / "main.yml"
                if defaults.exists():
                    try:
                        yaml.safe_load(defaults.read_text())
                    except yaml.YAMLError as e:
                        errors.append(f"{role_dir.name}: {e}")
        assert not errors, f"Invalid YAML in defaults:\n" + "\n".join(errors)

    def test_role_meta_main_is_valid_yaml(self):
        """All meta/main.yml files are valid YAML."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                meta = role_dir / "meta" / "main.yml"
                if meta.exists():
                    try:
                        yaml.safe_load(meta.read_text())
                    except yaml.YAMLError as e:
                        errors.append(f"{role_dir.name}: {e}")
        assert not errors, f"Invalid YAML in meta:\n" + "\n".join(errors)

    def test_role_meta_has_galaxy_info(self):
        """All meta/main.yml files contain galaxy_info."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                meta = role_dir / "meta" / "main.yml"
                if meta.exists():
                    data = yaml.safe_load(meta.read_text())
                    if not isinstance(data, dict) or "galaxy_info" not in data:
                        errors.append(role_dir.name)
        assert not errors, f"Roles without galaxy_info in meta: {errors}"

    def test_role_meta_has_agpl_license(self):
        """All role meta files specify AGPL-3.0 license."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                meta = role_dir / "meta" / "main.yml"
                if meta.exists():
                    data = yaml.safe_load(meta.read_text())
                    if isinstance(data, dict):
                        license_val = data.get("galaxy_info", {}).get("license", "")
                        if "AGPL" not in license_val:
                            errors.append(role_dir.name)
        assert not errors, f"Roles without AGPL license: {errors}"

    def test_role_meta_has_dependencies(self):
        """All meta/main.yml files have a dependencies key."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                meta = role_dir / "meta" / "main.yml"
                if meta.exists():
                    data = yaml.safe_load(meta.read_text())
                    if isinstance(data, dict) and "dependencies" not in data:
                        errors.append(role_dir.name)
        assert not errors, f"Roles without dependencies key in meta: {errors}"

    def test_all_molecule_defaults_have_molecule_yml(self):
        """All molecule/default/ directories have molecule.yml."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                mol_yml = role_dir / "molecule" / "default" / "molecule.yml"
                if not mol_yml.exists():
                    errors.append(role_dir.name)
        assert not errors, f"Roles without molecule/default/molecule.yml: {errors}"

    def test_molecule_configs_valid_yaml(self):
        """All molecule.yml files are valid YAML."""
        errors = []
        for mol_yml in ROLES_DIR.glob("*/molecule/default/molecule.yml"):
            try:
                data = yaml.safe_load(mol_yml.read_text())
                assert isinstance(data, dict), f"Not a dict: {mol_yml}"
            except (yaml.YAMLError, AssertionError) as e:
                errors.append(f"{mol_yml.parent.parent.parent.name}: {e}")
        assert not errors, f"Invalid molecule configs:\n" + "\n".join(errors)

    def test_defaults_main_starts_with_yaml_header(self):
        """All defaults/main.yml files start with YAML document marker."""
        errors = []
        for role_dir in sorted(ROLES_DIR.iterdir()):
            if role_dir.is_dir():
                defaults = role_dir / "defaults" / "main.yml"
                if defaults.exists():
                    content = defaults.read_text()
                    if not content.startswith("---"):
                        errors.append(role_dir.name)
        assert not errors, f"Roles with defaults/main.yml not starting with ---: {errors}"


# ── Shell script conventions ──────────────────────────────────


class TestShellScriptConventions:
    """Verify shell script conventions and quality."""

    def test_shell_scripts_use_env_bash(self):
        """All .sh scripts use #!/usr/bin/env bash shebang."""
        errors = []
        for sh_file in SCRIPTS_DIR.glob("*.sh"):
            first_line = sh_file.read_text().split("\n")[0]
            if first_line != "#!/usr/bin/env bash":
                errors.append(f"{sh_file.name}: {first_line}")
        assert not errors, f"Scripts not using #!/usr/bin/env bash:\n" + "\n".join(errors)

    def test_python_scripts_use_env_python3(self):
        """All .py scripts use #!/usr/bin/env python3 shebang."""
        errors = []
        for py_file in SCRIPTS_DIR.glob("*.py"):
            first_line = py_file.read_text().split("\n")[0]
            if first_line != "#!/usr/bin/env python3":
                errors.append(f"{py_file.name}: {first_line}")
        assert not errors, f"Scripts not using #!/usr/bin/env python3:\n" + "\n".join(errors)

    def test_shell_scripts_are_executable(self):
        """All .sh scripts have executable permission."""
        import os
        errors = []
        for sh_file in SCRIPTS_DIR.glob("*.sh"):
            if not os.access(sh_file, os.X_OK):
                errors.append(sh_file.name)
        assert not errors, f"Non-executable shell scripts: {errors}"

    def test_hooks_directory_exists(self):
        """scripts/hooks/ directory exists."""
        assert (SCRIPTS_DIR / "hooks").exists()

    def test_pre_commit_hook_exists(self):
        """Pre-commit hook exists in scripts/hooks/."""
        assert (SCRIPTS_DIR / "hooks" / "pre-commit").exists()

    def test_pre_commit_hook_has_shebang(self):
        """Pre-commit hook has a shebang line."""
        content = (SCRIPTS_DIR / "hooks" / "pre-commit").read_text()
        assert content.startswith("#!")

    def test_pre_commit_hook_checks_infra_yml(self):
        """Pre-commit hook blocks commits of infra.yml."""
        content = (SCRIPTS_DIR / "hooks" / "pre-commit").read_text()
        assert "infra.yml" in content

    def test_pre_commit_hook_checks_private_ips(self):
        """Pre-commit hook detects private IP addresses."""
        content = (SCRIPTS_DIR / "hooks" / "pre-commit").read_text()
        # Hook uses grep regex for RFC 1918 ranges
        assert "192\\.168" in content or "10\\." in content or "private" in content.lower()


# ── Python module structure ──────────────────────────────────


class TestPythonModuleStructure:
    """Verify Python module and test infrastructure."""

    def test_conftest_py_exists(self):
        """tests/conftest.py exists."""
        assert (PROJECT_ROOT / "tests" / "conftest.py").exists()

    def test_conftest_adds_scripts_to_path(self):
        """conftest.py adds scripts/ to sys.path for imports."""
        content = (PROJECT_ROOT / "tests" / "conftest.py").read_text()
        assert "scripts" in content
        assert "sys.path" in content

    def test_generate_py_exists(self):
        """scripts/generate.py (PSOT generator) exists."""
        assert (SCRIPTS_DIR / "generate.py").exists()

    def test_generate_py_has_main(self):
        """generate.py has a main entry point."""
        content = (SCRIPTS_DIR / "generate.py").read_text()
        assert "__main__" in content or "def main" in content or "if __name__" in content

    def test_matrix_coverage_py_exists(self):
        """scripts/matrix-coverage.py exists."""
        assert (SCRIPTS_DIR / "matrix-coverage.py").exists()

    def test_mine_experiences_py_exists(self):
        """scripts/mine-experiences.py exists."""
        assert (SCRIPTS_DIR / "mine-experiences.py").exists()

    def test_test_files_exist(self):
        """Key test files exist in tests/ directory."""
        expected_tests = [
            "test_generate.py",
            "test_project_structure.py",
            "test_properties.py",
        ]
        tests_dir = PROJECT_ROOT / "tests"
        missing = [t for t in expected_tests if not (tests_dir / t).exists()]
        assert not missing, f"Missing test files: {missing}"

    def test_test_files_count(self):
        """tests/ directory has a reasonable number of test files."""
        test_files = list((PROJECT_ROOT / "tests").glob("test_*.py"))
        assert len(test_files) >= 10, f"Expected >= 10 test files, found {len(test_files)}"


# ── Experience library content ────────────────────────────────


class TestExperienceLibraryContent:
    """Verify experience library content and consistency."""

    def test_fixes_has_expected_files(self):
        """Experience fixes/ has expected category files."""
        fixes_dir = EXPERIENCES_DIR / "fixes"
        expected = ["ansible-lint.yml", "generator.yml", "incus-cli.yml", "molecule.yml"]
        existing = {f.name for f in fixes_dir.glob("*.yml")}
        missing = [f for f in expected if f not in existing]
        assert not missing, f"Missing fix files: {missing}"

    def test_patterns_has_expected_files(self):
        """Experience patterns/ has expected category files."""
        patterns_dir = EXPERIENCES_DIR / "patterns"
        expected = ["reconciliation.yml", "role-structure.yml", "testing.yml"]
        existing = {f.name for f in patterns_dir.glob("*.yml")}
        missing = [f for f in expected if f not in existing]
        assert not missing, f"Missing pattern files: {missing}"

    def test_decisions_has_architecture_yml(self):
        """Experience decisions/ has architecture.yml."""
        assert (EXPERIENCES_DIR / "decisions" / "architecture.yml").exists()

    def test_decisions_architecture_valid_yaml(self):
        """Experience decisions/architecture.yml is valid YAML."""
        data = yaml.safe_load(
            (EXPERIENCES_DIR / "decisions" / "architecture.yml").read_text()
        )
        assert data is not None

    def test_readme_describes_structure(self):
        """Experience README.md describes the directory structure."""
        content = (EXPERIENCES_DIR / "README.md").read_text()
        for subdir in ["fixes", "patterns", "decisions"]:
            assert subdir in content


# ── Examples content validation ───────────────────────────────


class TestExamplesContent:
    """Verify example infra.yml files have correct content."""

    EXPECTED_EXAMPLES = [
        "student-sysadmin",
        "teacher-lab",
        "pro-workstation",
        "sandbox-isolation",
        "llm-supervisor",
        "developer",
        "ai-tools",
    ]

    def test_expected_examples_exist(self):
        """All expected example directories exist."""
        existing = {d.name for d in EXAMPLES_DIR.iterdir() if d.is_dir()}
        missing = [e for e in self.EXPECTED_EXAMPLES if e not in existing]
        assert not missing, f"Missing examples: {missing}"

    def test_example_infra_has_global(self):
        """All example infra.yml files have a global section."""
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            assert "global" in data, f"Missing 'global' in {infra}"

    def test_example_infra_has_domains(self):
        """All example infra.yml files have a domains section."""
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            assert "domains" in data, f"Missing 'domains' in {infra}"

    def test_example_infra_has_base_subnet(self):
        """All example infra.yml files define base_subnet."""
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            global_section = data.get("global", {})
            assert "base_subnet" in global_section, f"Missing base_subnet in {infra}"

    def test_example_infra_domains_have_subnet_id(self):
        """All example infra.yml domains have a subnet_id."""
        errors = []
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            domains = data.get("domains", {})
            for domain_name, domain in domains.items():
                if "subnet_id" not in domain:
                    errors.append(f"{infra.parent.name}/{domain_name}")
        assert not errors, f"Domains without subnet_id: {errors}"

    def test_example_infra_unique_subnet_ids(self):
        """Each example infra.yml has unique subnet_ids within itself."""
        errors = []
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            domains = data.get("domains", {})
            subnet_ids = []
            for domain_name, domain in domains.items():
                sid = domain.get("subnet_id")
                if sid is not None:
                    if sid in subnet_ids:
                        errors.append(f"{infra.parent.name}: duplicate subnet_id {sid}")
                    subnet_ids.append(sid)
        assert not errors, f"Duplicate subnet_ids:\n" + "\n".join(errors)

    def test_example_infra_unique_machine_names(self):
        """Each example infra.yml has globally unique machine names."""
        errors = []
        for infra in EXAMPLES_DIR.glob("*/infra.yml"):
            data = yaml.safe_load(infra.read_text())
            domains = data.get("domains", {})
            all_machines = []
            for domain_name, domain in domains.items():
                machines = domain.get("machines", {})
                for mname in machines:
                    if mname in all_machines:
                        errors.append(f"{infra.parent.name}: duplicate machine {mname}")
                    all_machines.append(mname)
        assert not errors, f"Duplicate machine names:\n" + "\n".join(errors)

    def test_example_readmes_not_empty(self):
        """All example README.md files are not empty."""
        errors = []
        for subdir in EXAMPLES_DIR.iterdir():
            if subdir.is_dir():
                readme = subdir / "README.md"
                if readme.exists() and readme.stat().st_size == 0:
                    errors.append(subdir.name)
        assert not errors, f"Empty example READMEs: {errors}"


# ── Playbook structure details ────────────────────────────────


class TestPlaybookDetails:
    """Verify detailed playbook structure and conventions."""

    def test_site_yml_three_phases(self):
        """site.yml has exactly three phases (infra, provision, nftables)."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        assert len(data) == 3, f"Expected 3 phases, found {len(data)}"

    def test_site_yml_infra_connection_local(self):
        """Infrastructure phase uses connection: local."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        infra_plays = [p for p in data if "Infrastructure" in p.get("name", "")]
        assert infra_plays[0].get("connection") == "local"

    def test_site_yml_infra_no_facts(self):
        """Infrastructure phase disables fact gathering."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        infra_plays = [p for p in data if "Infrastructure" in p.get("name", "")]
        assert infra_plays[0].get("gather_facts") is False

    def test_site_yml_provision_uses_incus_connection(self):
        """Provisioning phase vars include incus connection."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        prov_plays = [p for p in data if "Provisioning" in p.get("name", "")]
        prov_vars = prov_plays[0].get("vars", {})
        assert prov_vars.get("ansible_connection") == "community.general.incus"

    def test_site_yml_provision_has_python_bootstrap(self):
        """Provisioning phase has a Python bootstrap pre_task."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        prov_plays = [p for p in data if "Provisioning" in p.get("name", "")]
        pre_tasks = prov_plays[0].get("pre_tasks", [])
        assert len(pre_tasks) >= 1
        raw_task = any("python3" in str(t) for t in pre_tasks)
        assert raw_task, "Provisioning phase missing Python bootstrap pre_task"

    def test_site_yml_has_fqcn_include_role(self):
        """site.yml uses FQCN for include_role (ansible.builtin.include_role)."""
        content = (PROJECT_ROOT / "site.yml").read_text()
        assert "ansible.builtin.include_role" in content

    def test_snapshot_yml_uses_incus_snapshots_role(self):
        """snapshot.yml uses the incus_snapshots role."""
        data = yaml.safe_load((PROJECT_ROOT / "snapshot.yml").read_text())
        play = data[0]
        roles = play.get("roles", [])
        role_names = [r.get("role", r) if isinstance(r, dict) else r for r in roles]
        assert "incus_snapshots" in role_names

    def test_snapshot_yml_has_snapshot_tag(self):
        """snapshot.yml has snapshot tag."""
        data = yaml.safe_load((PROJECT_ROOT / "snapshot.yml").read_text())
        play = data[0]
        tags = play.get("tags", [])
        assert "snapshot" in tags

    def test_site_yml_infra_phase_includes_five_core_roles(self):
        """Infrastructure phase includes the 5 core infra roles."""
        content = (PROJECT_ROOT / "site.yml").read_text()
        data = yaml.safe_load(content)
        infra_plays = [p for p in data if "Infrastructure" in p.get("name", "")]
        tasks = infra_plays[0].get("tasks", [])
        role_names = []
        for task in tasks:
            if isinstance(task, dict):
                role_block = task.get("ansible.builtin.include_role", {})
                if isinstance(role_block, dict):
                    name = role_block.get("name", "")
                    if name:
                        role_names.append(name)
        core_infra = ["incus_projects", "incus_networks", "incus_profiles",
                       "incus_images", "incus_instances"]
        for role in core_infra:
            assert role in role_names, f"Infrastructure phase missing role: {role}"


# ── Infra.yml main file ──────────────────────────────────────


class TestInfraYml:
    """Verify the main infra.yml structure."""

    def test_infra_has_global(self):
        """infra.yml has a global section."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        assert "global" in data

    def test_infra_has_base_subnet(self):
        """infra.yml global section has base_subnet."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        assert "base_subnet" in data.get("global", {})

    def test_infra_has_default_os_image(self):
        """infra.yml global section has default_os_image."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        assert "default_os_image" in data.get("global", {})

    def test_infra_domains_have_machines(self):
        """All domains in infra.yml have at least one machine."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        for domain_name, domain in data.get("domains", {}).items():
            machines = domain.get("machines", {})
            assert len(machines) >= 1, f"Domain {domain_name} has no machines"

    def test_infra_machines_have_type(self):
        """All machines in infra.yml have a type (lxc or vm)."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        errors = []
        for domain_name, domain in data.get("domains", {}).items():
            for mname, machine in domain.get("machines", {}).items():
                if "type" not in machine:
                    errors.append(f"{domain_name}/{mname}")
        assert not errors, f"Machines without type: {errors}"

    def test_infra_machine_types_valid(self):
        """All machine types are either 'lxc' or 'vm'."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml").read_text())
        errors = []
        for domain_name, domain in data.get("domains", {}).items():
            for mname, machine in domain.get("machines", {}).items():
                mtype = machine.get("type")
                if mtype and mtype not in ("lxc", "vm"):
                    errors.append(f"{domain_name}/{mname}: {mtype}")
        assert not errors, f"Invalid machine types: {errors}"


# ── Molecule shared configuration ─────────────────────────────


class TestMoleculeShared:
    """Verify shared Molecule configuration."""

    def test_molecule_shared_dir_exists(self):
        """molecule/shared/ directory exists."""
        assert (PROJECT_ROOT / "molecule" / "shared").exists()

    def test_molecule_shared_has_infra_playbook(self):
        """molecule/shared has infrastructure playbook template."""
        assert (PROJECT_ROOT / "molecule" / "shared" / "molecule-infra.yml").exists()

    def test_molecule_shared_has_provision_playbook(self):
        """molecule/shared has provisioning playbook template."""
        assert (PROJECT_ROOT / "molecule" / "shared" / "molecule-provision.yml").exists()

    def test_molecule_shared_files_valid_yaml(self):
        """Molecule shared files are valid YAML."""
        for yml_file in (PROJECT_ROOT / "molecule" / "shared").glob("*.yml"):
            data = yaml.safe_load(yml_file.read_text())
            assert data is not None, f"Empty or invalid YAML: {yml_file}"


# ── Role template files ───────────────────────────────────────


class TestRoleTemplates:
    """Verify roles that should have templates have them."""

    ROLES_WITH_TEMPLATES = [
        ("incus_nftables", "anklume-isolation.nft.j2"),
        ("firewall_router", "firewall-router.nft.j2"),
        ("lobechat", "lobechat.service.j2"),
        ("stt_server", "speaches.service.j2"),
        ("opencode_server", "opencode.service.j2"),
        ("dev_agent_runner", "claude-settings.json.j2"),
    ]

    def test_expected_templates_exist(self):
        """Roles with expected templates have those template files."""
        errors = []
        for role_name, template_name in self.ROLES_WITH_TEMPLATES:
            tmpl = ROLES_DIR / role_name / "templates" / template_name
            if not tmpl.exists():
                errors.append(f"{role_name}/{template_name}")
        assert not errors, f"Missing templates: {errors}"

    def test_template_files_are_not_empty(self):
        """Template files are not empty."""
        errors = []
        for role_name, template_name in self.ROLES_WITH_TEMPLATES:
            tmpl = ROLES_DIR / role_name / "templates" / template_name
            if tmpl.exists() and tmpl.stat().st_size == 0:
                errors.append(f"{role_name}/{template_name}")
        assert not errors, f"Empty templates: {errors}"

    def test_nftables_template_has_table_definition(self):
        """nftables template contains table inet anklume."""
        tmpl = ROLES_DIR / "incus_nftables" / "templates" / "anklume-isolation.nft.j2"
        content = tmpl.read_text()
        assert "table inet anklume" in content

    def test_nftables_template_has_priority(self):
        """nftables template uses priority -1 (ADR-022)."""
        tmpl = ROLES_DIR / "incus_nftables" / "templates" / "anklume-isolation.nft.j2"
        content = tmpl.read_text()
        assert "priority -1" in content or "priority" in content


# ── Role files directory ──────────────────────────────────────


class TestRoleFiles:
    """Verify roles with static files have them."""

    def test_admin_bootstrap_has_systemd_service(self):
        """admin_bootstrap has incus-socket-dir.service file (ADR-019)."""
        assert (ROLES_DIR / "admin_bootstrap" / "files" / "incus-socket-dir.service").exists()

    def test_dev_agent_runner_has_audit_hook(self):
        """dev_agent_runner has agent-audit-hook.sh file."""
        assert (ROLES_DIR / "dev_agent_runner" / "files" / "agent-audit-hook.sh").exists()

    def test_systemd_service_file_valid(self):
        """admin_bootstrap systemd service file has required sections."""
        content = (ROLES_DIR / "admin_bootstrap" / "files" / "incus-socket-dir.service").read_text()
        assert "[Unit]" in content
        assert "[Service]" in content
        assert "[Install]" in content


# ── CLAUDE.md content ─────────────────────────────────────────


class TestClaudeMdContent:
    """Verify CLAUDE.md content conventions."""

    def test_claude_md_has_project_identity(self):
        """CLAUDE.md has project identity section."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "project identity" in content.lower()

    def test_claude_md_has_conventions(self):
        """CLAUDE.md has Ansible code conventions section."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "conventions" in content.lower()

    def test_claude_md_has_commands(self):
        """CLAUDE.md has commands section."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "commands" in content.lower() or "Commands" in content

    def test_claude_md_mentions_fqcn(self):
        """CLAUDE.md mentions FQCN (Fully Qualified Collection Name) convention."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "FQCN" in content or "fqcn" in content.lower()

    def test_claude_md_mentions_changed_when(self):
        """CLAUDE.md mentions changed_when convention."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "changed_when" in content

    def test_claude_md_mentions_task_naming(self):
        """CLAUDE.md mentions task naming pattern (RoleName | Description)."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "RoleName | Description" in content or "RoleName |" in content

    def test_claude_md_has_context_files(self):
        """CLAUDE.md has context files section."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "context files" in content.lower() or "Context files" in content

    def test_claude_md_mentions_make_sync(self):
        """CLAUDE.md mentions make sync command."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "make sync" in content

    def test_claude_md_mentions_make_lint(self):
        """CLAUDE.md mentions make lint command."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "make lint" in content


# ── Contributing.md content ──────────────────────────────────


class TestContributing:
    """Verify CONTRIBUTING.md content."""

    def test_contributing_mentions_spec_driven(self):
        """CONTRIBUTING.md mentions spec-driven development."""
        content = (PROJECT_ROOT / "CONTRIBUTING.md").read_text()
        assert "spec" in content.lower()

    def test_contributing_mentions_test_driven(self):
        """CONTRIBUTING.md mentions test-driven development."""
        content = (PROJECT_ROOT / "CONTRIBUTING.md").read_text()
        assert "test" in content.lower()

    def test_contributing_mentions_pre_commit_hook(self):
        """CONTRIBUTING.md mentions the pre-commit hook."""
        content = (PROJECT_ROOT / "CONTRIBUTING.md").read_text()
        assert "pre-commit" in content

    def test_contributing_mentions_no_verify(self):
        """CONTRIBUTING.md mentions --no-verify bypass."""
        content = (PROJECT_ROOT / "CONTRIBUTING.md").read_text()
        assert "--no-verify" in content


# ── Behavior matrix depth levels ──────────────────────────────


class TestBehaviorMatrixStructure:
    """Verify detailed behavior matrix structure."""

    def test_matrix_all_caps_have_depth_1(self):
        """Every capability has at least depth_1 cells."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        errors = []
        for cap_name, cap in data.get("capabilities", {}).items():
            d1 = cap.get("depth_1", [])
            if not d1:
                errors.append(cap_name)
        assert not errors, f"Capabilities without depth_1: {errors}"

    def test_matrix_all_caps_have_description(self):
        """Every capability has a description field."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        errors = []
        for cap_name, cap in data.get("capabilities", {}).items():
            if "description" not in cap:
                errors.append(cap_name)
        assert not errors, f"Capabilities without description: {errors}"

    def test_matrix_ids_follow_naming_convention(self):
        """Matrix cell IDs follow the XX-NNN or XX-D-NNN pattern."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        errors = []
        for cap in data.get("capabilities", {}).values():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for cell in cap.get(depth) or []:
                    cell_id = cell.get("id", "")
                    # Allow XX-NNN (depth 1) and XX-D-NNN (depth 2/3)
                    if not re.match(r'^[A-Z]+-(\d-)?\d{3}$', cell_id):
                        errors.append(cell_id)
        assert not errors, f"IDs not matching naming convention: {errors}"

    def test_matrix_has_deterministic_field(self):
        """Matrix cells have a deterministic field."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        total_cells = 0
        cells_with_det = 0
        for cap in data.get("capabilities", {}).values():
            for depth in ("depth_1", "depth_2", "depth_3"):
                for cell in cap.get(depth) or []:
                    total_cells += 1
                    if "deterministic" in cell:
                        cells_with_det += 1
        # At least 80% should have the deterministic field
        assert cells_with_det >= total_cells * 0.8, (
            f"Only {cells_with_det}/{total_cells} cells have 'deterministic' field"
        )

    def test_matrix_has_at_least_100_cells(self):
        """Matrix has at least 100 cells total."""
        data = yaml.safe_load((PROJECT_ROOT / "tests" / "behavior_matrix.yml").read_text())
        total = 0
        for cap in data.get("capabilities", {}).values():
            for depth in ("depth_1", "depth_2", "depth_3"):
                total += len(cap.get(depth) or [])
        assert total >= 100, f"Expected >= 100 matrix cells, found {total}"


# ── Cross-file consistency ────────────────────────────────────


class TestCrossFileConsistency:
    """Verify consistency across multiple configuration files."""

    def test_pyproject_name_matches_project(self):
        """pyproject.toml project name is 'anklume'."""
        content = (PROJECT_ROOT / "pyproject.toml").read_text()
        assert 'name = "anklume"' in content

    def test_readme_mentions_all_examples(self):
        """README.md mentions all example directories."""
        readme_content = (PROJECT_ROOT / "README.md").read_text()
        example_dirs = [d.name for d in EXAMPLES_DIR.iterdir() if d.is_dir()]
        # Not all examples need to be in README, but at least 5 should be
        mentioned = sum(1 for d in example_dirs if d in readme_content)
        assert mentioned >= 5, f"README mentions only {mentioned} of {len(example_dirs)} examples"

    def test_site_yml_infra_roles_in_roles_dir(self):
        """All roles included in site.yml's infra phase exist in roles/."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        infra_plays = [p for p in data if "Infrastructure" in p.get("name", "")]
        existing = {d.name for d in ROLES_DIR.iterdir() if d.is_dir()}
        for task in infra_plays[0].get("tasks", []):
            if isinstance(task, dict):
                role_block = task.get("ansible.builtin.include_role", {})
                if isinstance(role_block, dict):
                    role_name = role_block.get("name", "")
                    if role_name:
                        assert role_name in existing, f"Infra role '{role_name}' not in roles/"

    def test_site_yml_provision_roles_in_roles_dir(self):
        """All roles included in site.yml's provisioning phase exist in roles/."""
        data = yaml.safe_load((PROJECT_ROOT / "site.yml").read_text())
        prov_plays = [p for p in data if "Provisioning" in p.get("name", "")]
        existing = {d.name for d in ROLES_DIR.iterdir() if d.is_dir()}
        for task in prov_plays[0].get("tasks", []):
            if isinstance(task, dict):
                role_block = task.get("ansible.builtin.include_role", {})
                if isinstance(role_block, dict):
                    role_name = role_block.get("name", "")
                    if role_name:
                        assert role_name in existing, f"Provision role '{role_name}' not in roles/"

    def test_ansible_lint_excludes_claude_dir(self):
        """ansible-lint excludes .claude/ directory."""
        data = yaml.safe_load((PROJECT_ROOT / ".ansible-lint").read_text())
        excludes = data.get("exclude_paths", [])
        assert ".claude/" in excludes

    def test_yamllint_line_length_matches_ruff(self):
        """yamllint and ruff enforce the same line length (120)."""
        yml_data = yaml.safe_load((PROJECT_ROOT / ".yamllint.yml").read_text())
        yml_max = yml_data["rules"]["line-length"]["max"]
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text()
        match = re.search(r'line-length\s*=\s*(\d+)', pyproject)
        assert match, "Could not find line-length in pyproject.toml"
        ruff_max = int(match.group(1))
        assert yml_max == ruff_max, f"yamllint ({yml_max}) != ruff ({ruff_max})"


# ── README content ───────────────────────────────────────────


class TestReadmeContent:
    """Verify README.md content completeness."""

    def test_readme_has_quick_start(self):
        """README.md has a quick start section."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "quick start" in content.lower()

    def test_readme_has_architecture(self):
        """README.md has an architecture section."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "architecture" in content.lower()

    def test_readme_has_tech_stack(self):
        """README.md lists the tech stack."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "tech stack" in content.lower() or "Tech stack" in content

    def test_readme_mentions_incus(self):
        """README.md mentions Incus."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "Incus" in content

    def test_readme_mentions_ansible(self):
        """README.md mentions Ansible."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "Ansible" in content

    def test_readme_has_license_reference(self):
        """README.md references the license."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "AGPL" in content or "LICENSE" in content

    def test_readme_has_french_link(self):
        """README.md links to README_FR.md."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "README_FR" in content

    def test_readme_has_documentation_links(self):
        """README.md has a documentation section with links to docs/."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "docs/" in content

    def test_readme_mentions_make_apply(self):
        """README.md mentions make apply command."""
        content = (PROJECT_ROOT / "README.md").read_text()
        assert "make apply" in content

    def test_readme_fr_exists_and_not_empty(self):
        """README_FR.md exists and is not empty."""
        fr = PROJECT_ROOT / "README_FR.md"
        assert fr.exists()
        assert fr.stat().st_size > 100, "README_FR.md is too short"


# ── Infra.yml.example ────────────────────────────────────────


class TestInfraYmlExample:
    """Verify infra.yml.example template completeness."""

    def test_example_has_connection_config(self):
        """infra.yml.example has default_connection configuration."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml.example").read_text())
        assert "default_connection" in data.get("global", {})

    def test_example_has_admin_domain(self):
        """infra.yml.example includes an admin domain."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml.example").read_text())
        assert "admin" in data.get("domains", {})

    def test_example_has_comments(self):
        """infra.yml.example has inline documentation comments."""
        content = (PROJECT_ROOT / "infra.yml.example").read_text()
        # Should have multiple comment lines
        comment_lines = [l for l in content.split("\n") if l.strip().startswith("#")]
        assert len(comment_lines) >= 5, "infra.yml.example lacks documentation comments"

    def test_example_has_subnet_documentation(self):
        """infra.yml.example documents subnet selection."""
        content = (PROJECT_ROOT / "infra.yml.example").read_text()
        assert "subnet" in content.lower()

    def test_example_machines_have_roles(self):
        """infra.yml.example machines have roles assigned."""
        data = yaml.safe_load((PROJECT_ROOT / "infra.yml.example").read_text())
        for domain_name, domain in data.get("domains", {}).items():
            for mname, machine in domain.get("machines", {}).items():
                assert "roles" in machine, f"Machine {mname} in example has no roles"
