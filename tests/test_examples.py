"""Tests for example infra.yml files."""
from pathlib import Path

import pytest
from generate import load_infra, validate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def discover_examples():
    """Find all example infra.yml files."""
    return sorted(EXAMPLES_DIR.glob("*/infra.yml"))


@pytest.mark.parametrize(
    "example_path",
    discover_examples(),
    ids=lambda p: p.parent.name,
)
class TestExampleValid:
    def test_validates(self, example_path):
        """Each example infra.yml must pass PSOT validation."""
        infra = load_infra(str(example_path))
        errors = validate(infra)
        assert not errors, f"Validation errors in {example_path}:\n" + "\n".join(errors)

    def test_has_required_keys(self, example_path):
        """Each example must have project_name, global, and domains."""
        infra = load_infra(str(example_path))
        for key in ("project_name", "global", "domains"):
            assert key in infra, f"Missing key '{key}' in {example_path}"

    def test_has_readme(self, example_path):
        """Each example directory must contain a README.md."""
        readme = example_path.parent / "README.md"
        assert readme.exists(), f"Missing README.md in {example_path.parent}"


def test_at_least_six_examples():
    """The examples directory must contain at least 6 examples."""
    examples = discover_examples()
    assert len(examples) >= 6, f"Expected >= 6 examples, found {len(examples)}"


class TestExampleSubnetUniqueness:
    """Verify each example has no internal subnet or name conflicts."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_unique_subnet_ids(self, example_path):
        """Each example has unique subnet_ids."""
        infra = load_infra(str(example_path))
        seen = {}
        for dname, domain in (infra.get("domains") or {}).items():
            sid = domain.get("subnet_id")
            if sid is not None:
                assert sid not in seen, (
                    f"Duplicate subnet_id {sid} in {example_path}: "
                    f"{dname} and {seen[sid]}"
                )
                seen[sid] = dname

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_unique_machine_names(self, example_path):
        """Each example has globally unique machine names."""
        infra = load_infra(str(example_path))
        seen = {}
        for dname, domain in (infra.get("domains") or {}).items():
            for mname in (domain.get("machines") or {}):
                assert mname not in seen, (
                    f"Duplicate machine name '{mname}' in {example_path}: "
                    f"domain {dname} and {seen[mname]}"
                )
                seen[mname] = dname

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_readme_is_non_empty(self, example_path):
        """Each example's README.md is non-empty."""
        readme = example_path.parent / "README.md"
        if readme.exists():
            content = readme.read_text().strip()
            assert len(content) > 10, f"README.md too short in {example_path.parent}"


class TestExampleGeneration:
    """Test that each example can be generated without error."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_generates_files_successfully(self, example_path, tmp_path):
        """Each example generates Ansible files without error."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        written = generate(infra, tmp_path)
        assert len(written) > 0, f"No files generated for {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_generates_all_yml(self, example_path, tmp_path):
        """Each example generates group_vars/all.yml."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        assert (tmp_path / "group_vars" / "all.yml").exists()

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_generates_inventory_per_domain(self, example_path, tmp_path):
        """Each example generates an inventory file per domain."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            assert (tmp_path / "inventory" / f"{dname}.yml").exists(), (
                f"Missing inventory/{dname}.yml for {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_generates_host_vars_per_machine(self, example_path, tmp_path):
        """Each example generates host_vars per machine."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for domain in (infra.get("domains") or {}).values():
            for mname in (domain.get("machines") or {}):
                assert (tmp_path / "host_vars" / f"{mname}.yml").exists(), (
                    f"Missing host_vars/{mname}.yml for {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_no_orphans_on_fresh_generation(self, example_path, tmp_path):
        """Freshly generated files produce no orphans."""
        from generate import detect_orphans, enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        orphans = detect_orphans(infra, tmp_path)
        assert orphans == [], (
            f"Orphans found in {example_path}: {[str(o[0]) for o in orphans]}"
        )


class TestExampleContent:
    """Verify example content properties."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_has_at_least_one_domain(self, example_path):
        """Each example has at least one domain."""
        infra = load_infra(str(example_path))
        domains = infra.get("domains") or {}
        assert len(domains) >= 1, f"No domains in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_has_base_subnet(self, example_path):
        """Each example has base_subnet in global."""
        infra = load_infra(str(example_path))
        g = infra.get("global", {})
        assert "base_subnet" in g, f"Missing base_subnet in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_ips_unique(self, example_path):
        """All IPs within an example are unique."""
        infra = load_infra(str(example_path))
        seen = {}
        for dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    assert ip not in seen, (
                        f"Duplicate IP {ip} in {example_path}: {mname} and {seen[ip]}"
                    )
                    seen[ip] = mname

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_managed_markers_in_generated_files(self, example_path, tmp_path):
        """All generated files contain managed section markers."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for f in tmp_path.rglob("*.yml"):
            content = f.read_text()
            assert "=== MANAGED BY infra.yml ===" in content, (
                f"Missing managed marker in {f}"
            )
            assert "=== END MANAGED ===" in content, (
                f"Missing end marker in {f}"
            )
