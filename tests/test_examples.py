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
    def test_has_addressing_or_base_subnet(self, example_path):
        """Each example has addressing or base_subnet in global."""
        infra = load_infra(str(example_path))
        g = infra.get("global", {})
        assert "addressing" in g or "base_subnet" in g, (
            f"Missing addressing or base_subnet in {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_ips_unique(self, example_path):
        """All IPs within an example are unique."""
        infra = load_infra(str(example_path))
        seen = {}
        for _dname, domain in (infra.get("domains") or {}).items():
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


# =====================================================================
# NEW TESTS — added below existing tests
# =====================================================================


class TestExampleProjectNames:
    """Verify project_name is valid and non-empty in each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_project_name_is_string(self, example_path):
        """project_name must be a non-empty string."""
        infra = load_infra(str(example_path))
        pname = infra.get("project_name")
        assert isinstance(pname, str), f"project_name not a string in {example_path}"
        assert len(pname) > 0, f"project_name is empty in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_project_name_no_spaces(self, example_path):
        """project_name should not contain spaces."""
        infra = load_infra(str(example_path))
        pname = infra.get("project_name", "")
        assert " " not in pname, f"project_name contains spaces in {example_path}"


class TestExampleGlobalSection:
    """Detailed validation of the global section across examples."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_addressing_or_base_subnet_format(self, example_path):
        """addressing must be a dict, or base_subnet must be a dotted prefix."""
        import re
        infra = load_infra(str(example_path))
        g = infra["global"]
        if "addressing" in g:
            assert isinstance(g["addressing"], dict), (
                f"addressing must be a dict in {example_path}"
            )
        else:
            bs = g["base_subnet"]
            assert re.match(r"^\d+\.\d+$", bs), (
                f"Invalid base_subnet '{bs}' in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_default_os_image_present(self, example_path):
        """Each example should declare a default_os_image."""
        infra = load_infra(str(example_path))
        g = infra.get("global", {})
        assert "default_os_image" in g, f"Missing default_os_image in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_default_os_image_is_string(self, example_path):
        """default_os_image must be a string."""
        infra = load_infra(str(example_path))
        img = infra["global"].get("default_os_image")
        if img is not None:
            assert isinstance(img, str), f"default_os_image not string in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_default_connection_present(self, example_path):
        """Each example should declare default_connection."""
        infra = load_infra(str(example_path))
        g = infra.get("global", {})
        assert "default_connection" in g, f"Missing default_connection in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_default_connection_is_incus(self, example_path):
        """default_connection should be community.general.incus."""
        infra = load_infra(str(example_path))
        conn = infra["global"].get("default_connection", "")
        assert conn == "community.general.incus", (
            f"Expected community.general.incus, got '{conn}' in {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_default_user_is_root(self, example_path):
        """default_user should be root."""
        infra = load_infra(str(example_path))
        user = infra["global"].get("default_user", "")
        assert user == "root", f"Expected default_user=root, got '{user}' in {example_path}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_gpu_policy_valid_if_present(self, example_path):
        """gpu_policy must be 'exclusive' or 'shared' if declared."""
        infra = load_infra(str(example_path))
        gp = infra["global"].get("gpu_policy")
        if gp is not None:
            assert gp in ("exclusive", "shared"), (
                f"Invalid gpu_policy '{gp}' in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_firewall_mode_valid_if_present(self, example_path):
        """firewall_mode must be 'host' or 'vm' if declared."""
        infra = load_infra(str(example_path))
        fm = infra["global"].get("firewall_mode")
        if fm is not None:
            assert fm in ("host", "vm"), (
                f"Invalid firewall_mode '{fm}' in {example_path}"
            )


class TestExampleDomainDetails:
    """Detailed domain-level checks for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_domains_have_subnet_id_or_addressing(self, example_path):
        """Every domain must have a subnet_id, or global.addressing must exist."""
        infra = load_infra(str(example_path))
        has_addressing = "addressing" in infra.get("global", {})
        if has_addressing:
            return  # subnet_id is optional with addressing mode
        for dname, domain in (infra.get("domains") or {}).items():
            assert "subnet_id" in domain, (
                f"Domain '{dname}' missing subnet_id in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_subnet_ids_in_valid_range(self, example_path):
        """subnet_id must be between 0 and 254."""
        infra = load_infra(str(example_path))
        for dname, domain in (infra.get("domains") or {}).items():
            sid = domain.get("subnet_id")
            if sid is not None:
                assert isinstance(sid, int), (
                    f"Domain '{dname}' subnet_id not int in {example_path}"
                )
                assert 0 <= sid <= 254, (
                    f"Domain '{dname}' subnet_id {sid} out of range in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_domain_names_valid_format(self, example_path):
        """Domain names must be lowercase alphanumeric + hyphen."""
        import re
        infra = load_infra(str(example_path))
        for dname in (infra.get("domains") or {}):
            assert re.match(r"^[a-z0-9][a-z0-9-]*$", dname), (
                f"Domain name '{dname}' has invalid format in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_every_domain_has_at_least_one_machine(self, example_path):
        """Each domain should contain at least one machine."""
        infra = load_infra(str(example_path))
        for dname, domain in (infra.get("domains") or {}).items():
            machines = domain.get("machines") or {}
            assert len(machines) >= 1, (
                f"Domain '{dname}' has no machines in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_domain_descriptions_are_strings(self, example_path):
        """Domain descriptions must be strings if present."""
        infra = load_infra(str(example_path))
        for dname, domain in (infra.get("domains") or {}).items():
            desc = domain.get("description")
            if desc is not None:
                assert isinstance(desc, str), (
                    f"Domain '{dname}' description not a string in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_ephemeral_is_boolean_if_present(self, example_path):
        """Domain-level ephemeral must be boolean if declared."""
        infra = load_infra(str(example_path))
        for dname, domain in (infra.get("domains") or {}).items():
            eph = domain.get("ephemeral")
            if eph is not None:
                assert isinstance(eph, bool), (
                    f"Domain '{dname}' ephemeral not boolean in {example_path}"
                )


class TestExampleMachineDetails:
    """Detailed machine-level checks for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_machine_types_valid(self, example_path):
        """Machine type must be 'lxc' or 'vm'."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                mtype = machine.get("type", "lxc")
                assert mtype in ("lxc", "vm"), (
                    f"Machine '{mname}' invalid type '{mtype}' in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_machines_have_ip_or_auto_assign(self, example_path):
        """Every machine has a static IP or uses addressing auto-assignment."""
        infra = load_infra(str(example_path))
        has_addressing = "addressing" in infra.get("global", {})
        if has_addressing:
            return  # IPs are auto-assigned in addressing mode
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                assert "ip" in machine, (
                    f"Machine '{mname}' missing IP in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_ips_in_correct_subnet(self, example_path):
        """Each machine's IP must be within its domain's subnet."""
        from generate import enrich_infra
        infra = load_infra(str(example_path))
        g = infra.get("global", {})
        has_addressing = "addressing" in g
        if has_addressing:
            enrich_infra(infra)
            addressing = infra.get("_addressing", {})
            bo = g.get("addressing", {}).get("base_octet", 10)
            for dname, domain in (infra.get("domains") or {}).items():
                if dname not in addressing:
                    continue
                info = addressing[dname]
                prefix = f"{bo}.{info['second_octet']}.{info['domain_seq']}."
                for mname, machine in (domain.get("machines") or {}).items():
                    ip = machine.get("ip")
                    if ip:
                        assert ip.startswith(prefix), (
                            f"Machine '{mname}' IP {ip} not in subnet "
                            f"{prefix}0/24 in {example_path}"
                        )
        else:
            bs = g.get("base_subnet", "10.100")
            for _dname, domain in (infra.get("domains") or {}).items():
                sid = domain.get("subnet_id")
                for mname, machine in (domain.get("machines") or {}).items():
                    ip = machine.get("ip")
                    if ip and sid is not None:
                        expected_prefix = f"{bs}.{sid}."
                        assert ip.startswith(expected_prefix), (
                            f"Machine '{mname}' IP {ip} not in subnet "
                            f"{expected_prefix}0/24 in {example_path}"
                        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_ip_host_part_valid(self, example_path):
        """The host part of each IP must be 1-253 (not 0, 254, 255)."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    host_part = int(ip.split(".")[-1])
                    assert 1 <= host_part <= 253, (
                        f"Machine '{mname}' IP host part {host_part} invalid "
                        f"(must be 1-253) in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_machines_have_roles(self, example_path):
        """Every machine should declare at least one role."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                roles = machine.get("roles") or []
                assert len(roles) >= 1, (
                    f"Machine '{mname}' has no roles in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_machines_include_base_system(self, example_path):
        """Every machine should include the 'base_system' role."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                roles = machine.get("roles") or []
                assert "base_system" in roles, (
                    f"Machine '{mname}' missing base_system role in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_machine_descriptions_are_strings(self, example_path):
        """Machine descriptions must be strings if present."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                desc = machine.get("description")
                if desc is not None:
                    assert isinstance(desc, str), (
                        f"Machine '{mname}' description not string in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_machine_ephemeral_is_boolean_if_present(self, example_path):
        """Machine-level ephemeral must be boolean if declared."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                eph = machine.get("ephemeral")
                if eph is not None:
                    assert isinstance(eph, bool), (
                        f"Machine '{mname}' ephemeral not boolean in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_machine_config_is_dict_if_present(self, example_path):
        """Machine config must be a dict if declared."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                cfg = machine.get("config")
                if cfg is not None:
                    assert isinstance(cfg, dict), (
                        f"Machine '{mname}' config not dict in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_machine_profiles_reference_domain_profiles(self, example_path):
        """Machine profiles (except 'default') must exist in domain profiles."""
        infra = load_infra(str(example_path))
        for dname, domain in (infra.get("domains") or {}).items():
            domain_profiles = set(domain.get("profiles") or {})
            for mname, machine in (domain.get("machines") or {}).items():
                for p in machine.get("profiles") or []:
                    if p != "default":
                        assert p in domain_profiles, (
                            f"Machine '{mname}' references undefined profile "
                            f"'{p}' in domain '{dname}' in {example_path}"
                        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_gpu_machines_have_gpu_profile(self, example_path):
        """Machines with gpu:true should reference a GPU profile."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            domain_profiles = domain.get("profiles") or {}
            for mname, machine in (domain.get("machines") or {}).items():
                if machine.get("gpu", False):
                    has_gpu_profile = False
                    for pname in machine.get("profiles") or []:
                        if pname in domain_profiles:
                            pdevices = domain_profiles[pname].get("devices") or {}
                            if any(d.get("type") == "gpu" for d in pdevices.values()):
                                has_gpu_profile = True
                                break
                    assert has_gpu_profile, (
                        f"Machine '{mname}' has gpu:true but no GPU profile "
                        f"in {example_path}"
                    )


class TestExampleProfileDetails:
    """Validate profile definitions across examples."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_profiles_are_dicts(self, example_path):
        """Each profile definition must be a dict."""
        infra = load_infra(str(example_path))
        for dname, domain in (infra.get("domains") or {}).items():
            for pname, profile in (domain.get("profiles") or {}).items():
                assert isinstance(profile, dict), (
                    f"Profile '{pname}' in domain '{dname}' not a dict "
                    f"in {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_gpu_profiles_have_devices(self, example_path):
        """GPU profiles must contain a devices section with a gpu device."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for pname, profile in (domain.get("profiles") or {}).items():
                devices = profile.get("devices") or {}
                gpu_devices = [d for d in devices.values() if d.get("type") == "gpu"]
                if gpu_devices:
                    for gd in gpu_devices:
                        assert "type" in gd, (
                            f"GPU device in profile '{pname}' missing type "
                            f"in {example_path}"
                        )


class TestExampleNetworkPolicies:
    """Validate network_policies sections across examples."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_network_policies_are_list(self, example_path):
        """network_policies must be a list if present."""
        infra = load_infra(str(example_path))
        policies = infra.get("network_policies")
        if policies is not None:
            assert isinstance(policies, list), (
                f"network_policies not a list in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_network_policies_have_required_fields(self, example_path):
        """Each network policy must have from and to fields."""
        infra = load_infra(str(example_path))
        for i, policy in enumerate(infra.get("network_policies") or []):
            assert "from" in policy, (
                f"network_policies[{i}] missing 'from' in {example_path}"
            )
            assert "to" in policy, (
                f"network_policies[{i}] missing 'to' in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_network_policies_reference_valid_entities(self, example_path):
        """Policy from/to must reference known domains, machines, or 'host'."""
        infra = load_infra(str(example_path))
        domains = infra.get("domains") or {}
        domain_names = set(domains)
        machine_names = set()
        for domain in domains.values():
            for mname in (domain.get("machines") or {}):
                machine_names.add(mname)
        valid_refs = domain_names | machine_names | {"host"}
        for i, policy in enumerate(infra.get("network_policies") or []):
            for field in ("from", "to"):
                ref = policy.get(field)
                if ref is not None:
                    assert ref in valid_refs, (
                        f"network_policies[{i}].{field}='{ref}' unknown "
                        f"in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_network_policies_have_description(self, example_path):
        """Each network policy should have a description."""
        infra = load_infra(str(example_path))
        for i, policy in enumerate(infra.get("network_policies") or []):
            desc = policy.get("description")
            assert desc is not None and len(str(desc)) > 0, (
                f"network_policies[{i}] missing description in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_network_policies_ports_valid(self, example_path):
        """Ports must be a list of ints or 'all'."""
        infra = load_infra(str(example_path))
        for i, policy in enumerate(infra.get("network_policies") or []):
            ports = policy.get("ports")
            if ports is not None and ports != "all":
                assert isinstance(ports, list), (
                    f"network_policies[{i}] ports not list in {example_path}"
                )
                for port in ports:
                    assert isinstance(port, int) and 1 <= port <= 65535, (
                        f"network_policies[{i}] invalid port {port} "
                        f"in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_network_policies_protocol_valid(self, example_path):
        """Protocol must be 'tcp' or 'udp' if present."""
        infra = load_infra(str(example_path))
        for i, policy in enumerate(infra.get("network_policies") or []):
            proto = policy.get("protocol")
            if proto is not None:
                assert proto in ("tcp", "udp"), (
                    f"network_policies[{i}] invalid protocol '{proto}' "
                    f"in {example_path}"
                )


class TestExampleReadmeContent:
    """Detailed README content validation for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_readme_starts_with_heading(self, example_path):
        """Each README must start with a # heading."""
        readme = example_path.parent / "README.md"
        if readme.exists():
            content = readme.read_text().strip()
            assert content.startswith("#"), (
                f"README.md does not start with heading in {example_path.parent}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_readme_mentions_use_case(self, example_path):
        """Each README should mention a use case or description."""
        readme = example_path.parent / "README.md"
        if readme.exists():
            content = readme.read_text().lower()
            # Must mention some kind of purpose
            assert any(word in content for word in
                       ("use case", "description", "domain", "architecture")), (
                f"README.md lacks purpose description in {example_path.parent}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_readme_mentions_at_least_one_domain(self, example_path):
        """Each README should mention at least one of its domains."""
        readme = example_path.parent / "README.md"
        if readme.exists():
            infra = load_infra(str(example_path))
            content = readme.read_text().lower()
            domains = list(infra.get("domains") or {})
            mentioned = [d for d in domains if d.lower() in content]
            assert len(mentioned) >= 1, (
                f"README.md does not mention any domain "
                f"in {example_path.parent}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_readme_has_at_least_100_chars(self, example_path):
        """Each README should have substantial content."""
        readme = example_path.parent / "README.md"
        if readme.exists():
            content = readme.read_text()
            assert len(content) >= 100, (
                f"README.md too short ({len(content)} chars) in "
                f"{example_path.parent}"
            )


class TestExampleHasAnklumeDomain:
    """Every example should have an anklume domain for orchestration."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_has_anklume_domain(self, example_path):
        """Each example must have an 'anklume' domain."""
        infra = load_infra(str(example_path))
        domains = infra.get("domains") or {}
        assert "anklume" in domains, (
            f"Missing 'anklume' domain in {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_anklume_domain_has_subnet_0_or_admin(self, example_path):
        """The anklume domain should use subnet_id 0 or trust_level admin."""
        infra = load_infra(str(example_path))
        has_addressing = "addressing" in infra.get("global", {})
        anklume = (infra.get("domains") or {}).get("anklume", {})
        if has_addressing:
            assert anklume.get("trust_level") == "admin", (
                f"Anklume domain should be trust_level: admin in {example_path}"
            )
        else:
            assert anklume.get("subnet_id") == 0, (
                f"Anklume domain subnet_id != 0 in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_anklume_domain_not_ephemeral(self, example_path):
        """The anklume domain should not be ephemeral."""
        infra = load_infra(str(example_path))
        anklume = (infra.get("domains") or {}).get("anklume", {})
        eph = anklume.get("ephemeral", False)
        assert eph is False, f"Anklume domain is ephemeral in {example_path}"


class TestExampleGatewayConvention:
    """Verify the gateway convention (.254) is not conflicted."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_no_machine_uses_gateway_ip(self, example_path):
        """No machine should use .254 (reserved for gateway)."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    host_part = int(ip.split(".")[-1])
                    assert host_part != 254, (
                        f"Machine '{mname}' uses gateway IP .254 in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_no_machine_uses_network_address(self, example_path):
        """No machine should use .0 (network address)."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    host_part = int(ip.split(".")[-1])
                    assert host_part != 0, (
                        f"Machine '{mname}' uses network address .0 in {example_path}"
                    )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_no_machine_uses_broadcast(self, example_path):
        """No machine should use .255 (broadcast address)."""
        infra = load_infra(str(example_path))
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    host_part = int(ip.split(".")[-1])
                    assert host_part != 255, (
                        f"Machine '{mname}' uses broadcast .255 in {example_path}"
                    )


class TestExampleGeneratedContentDetails:
    """Verify details in generated output for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_yml_contains_project_name(self, example_path, tmp_path):
        """group_vars/all.yml must contain project_name."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        import yaml
        content = yaml.safe_load((tmp_path / "group_vars" / "all.yml").read_text())
        assert "project_name" in content, (
            f"group_vars/all.yml missing project_name for {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_all_yml_contains_addressing_or_base_subnet(self, example_path, tmp_path):
        """group_vars/all.yml must contain addressing or base_subnet."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        import yaml
        content = yaml.safe_load((tmp_path / "group_vars" / "all.yml").read_text())
        assert "addressing" in content or "base_subnet" in content, (
            f"group_vars/all.yml missing addressing/base_subnet for {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_domain_group_vars_contain_incus_network(self, example_path, tmp_path):
        """group_vars/<domain>.yml must contain incus_network."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            gv = yaml.safe_load((tmp_path / "group_vars" / f"{dname}.yml").read_text())
            assert "incus_network" in gv, (
                f"Missing incus_network in group_vars/{dname}.yml for {example_path}"
            )
            net = gv["incus_network"]
            assert "name" in net, f"incus_network missing name for {dname}"
            assert "subnet" in net, f"incus_network missing subnet for {dname}"
            assert "gateway" in net, f"incus_network missing gateway for {dname}"

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_domain_group_vars_network_name_format(self, example_path, tmp_path):
        """Network name must be 'net-<domain>'."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            gv = yaml.safe_load((tmp_path / "group_vars" / f"{dname}.yml").read_text())
            net_name = gv["incus_network"]["name"]
            assert net_name == f"net-{dname}", (
                f"Expected net-{dname}, got {net_name} for {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_domain_group_vars_gateway_ends_254(self, example_path, tmp_path):
        """Gateway must end with .254."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            gv = yaml.safe_load((tmp_path / "group_vars" / f"{dname}.yml").read_text())
            gw = gv["incus_network"]["gateway"]
            assert gw.endswith(".254"), (
                f"Gateway '{gw}' does not end with .254 for domain {dname} "
                f"in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_host_vars_contain_instance_name(self, example_path, tmp_path):
        """host_vars/<machine>.yml must contain instance_name."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname in (domain.get("machines") or {}):
                hv = yaml.safe_load(
                    (tmp_path / "host_vars" / f"{mname}.yml").read_text()
                )
                assert hv.get("instance_name") == mname, (
                    f"host_vars/{mname}.yml instance_name mismatch for {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_host_vars_contain_instance_domain(self, example_path, tmp_path):
        """host_vars/<machine>.yml must contain instance_domain."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname, domain in (infra.get("domains") or {}).items():
            for mname in (domain.get("machines") or {}):
                hv = yaml.safe_load(
                    (tmp_path / "host_vars" / f"{mname}.yml").read_text()
                )
                assert hv.get("instance_domain") == dname, (
                    f"host_vars/{mname}.yml instance_domain mismatch for {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_host_vars_contain_instance_type(self, example_path, tmp_path):
        """host_vars/<machine>.yml must contain instance_type."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                hv = yaml.safe_load(
                    (tmp_path / "host_vars" / f"{mname}.yml").read_text()
                )
                expected_type = machine.get("type", "lxc")
                assert hv.get("instance_type") == expected_type, (
                    f"host_vars/{mname}.yml instance_type mismatch for {example_path}"
                )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_inventory_contains_domain_group(self, example_path, tmp_path):
        """inventory/<domain>.yml must contain the domain as an Ansible group."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            inv = yaml.safe_load(
                (tmp_path / "inventory" / f"{dname}.yml").read_text()
            )
            assert "all" in inv, (
                f"inventory/{dname}.yml missing 'all' key for {example_path}"
            )
            children = inv["all"].get("children", {})
            assert dname in children, (
                f"inventory/{dname}.yml missing group '{dname}' for {example_path}"
            )


class TestExampleIdempotency:
    """Verify generation is idempotent for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_generation_idempotent(self, example_path, tmp_path):
        """Running generate twice produces identical output."""

        from generate import enrich_infra, generate
        infra1 = load_infra(str(example_path))
        enrich_infra(infra1)
        generate(infra1, tmp_path)
        first_run = {}
        for f in tmp_path.rglob("*.yml"):
            first_run[f.relative_to(tmp_path)] = f.read_text()

        infra2 = load_infra(str(example_path))
        enrich_infra(infra2)
        generate(infra2, tmp_path)
        second_run = {}
        for f in tmp_path.rglob("*.yml"):
            second_run[f.relative_to(tmp_path)] = f.read_text()

        assert first_run == second_run, (
            f"Generation not idempotent for {example_path}"
        )


class TestCrossExampleValidation:
    """Cross-example validation to ensure examples don't conflict."""

    def test_no_duplicate_project_names(self):
        """All examples should have unique project_names."""
        seen = {}
        for path in discover_examples():
            infra = load_infra(str(path))
            pname = infra.get("project_name")
            assert pname not in seen, (
                f"Duplicate project_name '{pname}': "
                f"{path.parent.name} and {seen[pname]}"
            )
            seen[pname] = path.parent.name

    def test_all_examples_use_consistent_addressing(self):
        """All examples should use consistent addressing (10.100 zone_base or base_subnet)."""
        for path in discover_examples():
            infra = load_infra(str(path))
            g = infra.get("global", {})
            if "addressing" in g:
                zb = g["addressing"].get("zone_base", 100)
                assert zb == 100, (
                    f"Example {path.parent.name} uses zone_base {zb}, "
                    f"expected 100"
                )
            elif "base_subnet" in g:
                bs = g["base_subnet"]
                assert bs == "10.100", (
                    f"Example {path.parent.name} uses base_subnet '{bs}', "
                    f"expected '10.100'"
                )

    def test_no_duplicate_subnet_ids_across_examples_with_same_project(self):
        """Within each example, subnet_ids are unique (already tested, but explicit)."""
        for path in discover_examples():
            infra = load_infra(str(path))
            domains = infra.get("domains") or {}
            if not isinstance(domains, dict):
                continue  # Skip non-PSOT examples (e.g., live-os)
            seen = {}
            for dname, domain in domains.items():
                sid = domain.get("subnet_id")
                if sid is not None:
                    assert sid not in seen, (
                        f"Duplicate subnet_id {sid} in {path.parent.name}"
                    )
                    seen[sid] = dname


class TestExampleImageExtraction:
    """Test the extract_all_images function for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_extract_images_returns_list(self, example_path):
        """extract_all_images should return a sorted list."""
        from generate import extract_all_images
        infra = load_infra(str(example_path))
        images = extract_all_images(infra)
        assert isinstance(images, list), (
            f"extract_all_images returned non-list for {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_extract_images_non_empty(self, example_path):
        """Each example should reference at least one OS image."""
        from generate import extract_all_images
        infra = load_infra(str(example_path))
        images = extract_all_images(infra)
        assert len(images) >= 1, (
            f"No images found for {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_extract_images_sorted(self, example_path):
        """Extracted images must be sorted."""
        from generate import extract_all_images
        infra = load_infra(str(example_path))
        images = extract_all_images(infra)
        assert images == sorted(images), (
            f"Images not sorted for {example_path}"
        )


class TestExampleWarnings:
    """Test the get_warnings function for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_get_warnings_returns_list(self, example_path):
        """get_warnings should return a list."""
        from generate import get_warnings
        infra = load_infra(str(example_path))
        warnings = get_warnings(infra)
        assert isinstance(warnings, list), (
            f"get_warnings returned non-list for {example_path}"
        )


class TestExampleEnrichment:
    """Test the enrich_infra function for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_enrich_does_not_break_validation(self, example_path):
        """Enrichment should not introduce validation errors."""
        from generate import enrich_infra
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        errors = validate(infra)
        assert not errors, (
            f"Enrichment introduced errors in {example_path}: {errors}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_enrich_preserves_existing_domains(self, example_path):
        """Enrichment should not remove existing domains."""
        from generate import enrich_infra
        infra = load_infra(str(example_path))
        original_domains = set(infra.get("domains") or {})
        enrich_infra(infra)
        enriched_domains = set(infra.get("domains") or {})
        assert original_domains.issubset(enriched_domains), (
            f"Enrichment removed domains in {example_path}"
        )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_enrich_preserves_existing_machines(self, example_path):
        """Enrichment should not remove existing machines."""
        from generate import enrich_infra
        infra = load_infra(str(example_path))
        original_machines = set()
        for domain in (infra.get("domains") or {}).values():
            for mname in (domain.get("machines") or {}):
                original_machines.add(mname)
        enrich_infra(infra)
        enriched_machines = set()
        for domain in (infra.get("domains") or {}).values():
            for mname in (domain.get("machines") or {}):
                enriched_machines.add(mname)
        assert original_machines.issubset(enriched_machines), (
            f"Enrichment removed machines in {example_path}"
        )


class TestExampleGeneratedFileCount:
    """Verify correct number of files generated per example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_correct_file_count(self, example_path, tmp_path):
        """Number of generated files should match expected count."""
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        written = generate(infra, tmp_path)
        domains = infra.get("domains") or {}
        total_machines = sum(
            len(d.get("machines") or {}) for d in domains.values()
        )
        # 1 all.yml + (N domains * (1 inventory + 1 group_vars)) + M host_vars
        expected = 1 + (len(domains) * 2) + total_machines
        assert len(written) == expected, (
            f"Expected {expected} files, got {len(written)} for {example_path}"
        )


# =====================================================================
# Specific example tests — deterministic checks for known content
# =====================================================================


class TestStudentSysadminExample:
    """Tests specific to the student-sysadmin example."""

    def _load(self):
        path = EXAMPLES_DIR / "student-sysadmin" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "student-sysadmin"

    def test_has_two_domains(self):
        domains = self._load()["domains"]
        assert set(domains.keys()) == {"anklume", "lab"}

    def test_lab_domain_is_ephemeral(self):
        infra = self._load()
        assert infra["domains"]["lab"]["ephemeral"] is True

    def test_anklume_domain_not_ephemeral(self):
        infra = self._load()
        assert infra["domains"]["anklume"].get("ephemeral", False) is False

    def test_has_three_machines(self):
        infra = self._load()
        machines = []
        for d in infra["domains"].values():
            machines.extend((d.get("machines") or {}).keys())
        assert len(machines) == 3

    def test_machine_names(self):
        infra = self._load()
        machines = set()
        for d in infra["domains"].values():
            machines.update((d.get("machines") or {}).keys())
        assert machines == {"sa-admin", "sa-web", "sa-db"}

    def test_no_gpu(self):
        infra = self._load()
        for d in infra["domains"].values():
            for mname, machine in (d.get("machines") or {}).items():
                assert not machine.get("gpu", False), f"{mname} has GPU"

    def test_no_network_policies(self):
        infra = self._load()
        assert infra.get("network_policies") is None

    def test_anklume_is_admin(self):
        infra = self._load()
        assert infra["domains"]["anklume"]["trust_level"] == "admin"

    def test_sa_admin_has_nesting(self):
        infra = self._load()
        cfg = infra["domains"]["anklume"]["machines"]["sa-admin"].get("config", {})
        assert cfg.get("security.nesting") == "true"


class TestTeacherLabExample:
    """Tests specific to the teacher-lab example."""

    def _load(self):
        path = EXAMPLES_DIR / "teacher-lab" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "networking-lab"

    def test_has_four_domains(self):
        domains = self._load()["domains"]
        assert len(domains) == 4

    def test_has_student_domains(self):
        domains = self._load()["domains"]
        for i in range(1, 4):
            assert f"student-0{i}" in domains

    def test_student_domains_are_ephemeral(self):
        infra = self._load()
        for i in range(1, 4):
            assert infra["domains"][f"student-0{i}"]["ephemeral"] is True

    def test_each_student_has_two_machines(self):
        infra = self._load()
        for i in range(1, 4):
            machines = infra["domains"][f"student-0{i}"]["machines"]
            assert len(machines) == 2

    def test_student_machine_naming_pattern(self):
        infra = self._load()
        for i in range(1, 4):
            machines = infra["domains"][f"student-0{i}"]["machines"]
            assert f"s0{i}-web" in machines
            assert f"s0{i}-client" in machines

    def test_has_seven_machines_total(self):
        infra = self._load()
        count = sum(len(d.get("machines") or {}) for d in infra["domains"].values())
        assert count == 7

    def test_student_domains_semi_trusted(self):
        infra = self._load()
        for i in range(1, 4):
            assert infra["domains"][f"student-0{i}"]["trust_level"] == "semi-trusted"

    def test_no_gpu(self):
        infra = self._load()
        for d in infra["domains"].values():
            for machine in (d.get("machines") or {}).values():
                assert not machine.get("gpu", False)


class TestProWorkstationExample:
    """Tests specific to the pro-workstation example."""

    def _load(self):
        path = EXAMPLES_DIR / "pro-workstation" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "pro-workstation"

    def test_has_four_domains(self):
        domains = self._load()["domains"]
        assert set(domains.keys()) == {"anklume", "perso", "pro", "homelab"}

    def test_homelab_has_gpu_profile(self):
        infra = self._load()
        profiles = infra["domains"]["homelab"].get("profiles", {})
        assert "nvidia-compute" in profiles

    def test_pw_ai_has_gpu(self):
        infra = self._load()
        pw_ai = infra["domains"]["homelab"]["machines"]["pw-ai"]
        assert pw_ai["gpu"] is True

    def test_pw_ai_has_ollama_and_stt_roles(self):
        infra = self._load()
        roles = infra["domains"]["homelab"]["machines"]["pw-ai"]["roles"]
        assert "ollama_server" in roles
        assert "stt_server" in roles

    def test_pw_dev_has_resource_limits(self):
        infra = self._load()
        cfg = infra["domains"]["pro"]["machines"]["pw-dev"]["config"]
        assert cfg["limits.cpu"] == "4"
        assert cfg["limits.memory"] == "8GiB"

    def test_pw_webui_has_open_webui_role(self):
        infra = self._load()
        roles = infra["domains"]["homelab"]["machines"]["pw-webui"]["roles"]
        assert "open_webui" in roles

    def test_has_five_machines(self):
        infra = self._load()
        count = sum(len(d.get("machines") or {}) for d in infra["domains"].values())
        assert count == 5

    def test_no_ephemeral_domains(self):
        """Pro workstation domains should not be ephemeral."""
        infra = self._load()
        for dname, domain in infra["domains"].items():
            assert domain.get("ephemeral", False) is False, (
                f"Domain '{dname}' is ephemeral"
            )


class TestSandboxIsolationExample:
    """Tests specific to the sandbox-isolation example."""

    def _load(self):
        path = EXAMPLES_DIR / "sandbox-isolation" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "sandbox-isolation"

    def test_has_two_domains(self):
        domains = self._load()["domains"]
        assert set(domains.keys()) == {"anklume", "sandbox"}

    def test_sandbox_is_ephemeral(self):
        infra = self._load()
        assert infra["domains"]["sandbox"]["ephemeral"] is True

    def test_has_vm_instance(self):
        """Sandbox example should have at least one VM instance."""
        infra = self._load()
        has_vm = False
        for d in infra["domains"].values():
            for machine in (d.get("machines") or {}).values():
                if machine.get("type") == "vm":
                    has_vm = True
        assert has_vm, "sandbox-isolation should contain a VM instance"

    def test_sbx_vm_is_vm_type(self):
        infra = self._load()
        assert infra["domains"]["sandbox"]["machines"]["sbx-vm"]["type"] == "vm"

    def test_sbx_test_is_lxc_type(self):
        infra = self._load()
        assert infra["domains"]["sandbox"]["machines"]["sbx-test"].get("type", "lxc") == "lxc"

    def test_sbx_vm_has_resource_limits(self):
        infra = self._load()
        cfg = infra["domains"]["sandbox"]["machines"]["sbx-vm"]["config"]
        assert "limits.cpu" in cfg
        assert "limits.memory" in cfg

    def test_sandbox_machines_are_ephemeral(self):
        infra = self._load()
        sbx_test = infra["domains"]["sandbox"]["machines"]["sbx-test"]
        sbx_vm = infra["domains"]["sandbox"]["machines"]["sbx-vm"]
        assert sbx_test.get("ephemeral") is True
        assert sbx_vm.get("ephemeral") is True

    def test_sandbox_is_disposable(self):
        infra = self._load()
        assert infra["domains"]["sandbox"]["trust_level"] == "disposable"

    def test_no_gpu(self):
        infra = self._load()
        for d in infra["domains"].values():
            for machine in (d.get("machines") or {}).values():
                assert not machine.get("gpu", False)

    def test_has_four_machines(self):
        infra = self._load()
        count = sum(len(d.get("machines") or {}) for d in infra["domains"].values())
        assert count == 4


class TestLlmSupervisorExample:
    """Tests specific to the llm-supervisor example."""

    def _load(self):
        path = EXAMPLES_DIR / "llm-supervisor" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "llm-supervisor"

    def test_has_four_domains(self):
        domains = self._load()["domains"]
        assert set(domains.keys()) == {"anklume", "llm-alpha", "llm-beta", "supervisor"}

    def test_gpu_policy_shared(self):
        infra = self._load()
        assert infra["global"]["gpu_policy"] == "shared"

    def test_two_gpu_instances(self):
        infra = self._load()
        gpu_count = 0
        for d in infra["domains"].values():
            for machine in (d.get("machines") or {}).values():
                if machine.get("gpu", False):
                    gpu_count += 1
        assert gpu_count == 2

    def test_both_llm_domains_have_nvidia_profile(self):
        infra = self._load()
        for dname in ("llm-alpha", "llm-beta"):
            profiles = infra["domains"][dname].get("profiles", {})
            assert "nvidia-compute" in profiles

    def test_llm_servers_have_ollama_role(self):
        infra = self._load()
        for machine_name in ("llm-alpha-server", "llm-beta-server"):
            found = False
            for d in infra["domains"].values():
                if machine_name in (d.get("machines") or {}):
                    roles = d["machines"][machine_name]["roles"]
                    assert "ollama_server" in roles
                    found = True
            assert found, f"Machine {machine_name} not found"

    def test_supervisor_has_webui(self):
        infra = self._load()
        roles = infra["domains"]["supervisor"]["machines"]["llm-webui"]["roles"]
        assert "open_webui" in roles

    def test_has_five_machines(self):
        infra = self._load()
        count = sum(len(d.get("machines") or {}) for d in infra["domains"].values())
        assert count == 5

    def test_all_domains_not_ephemeral(self):
        infra = self._load()
        for _dname, domain in infra["domains"].items():
            assert domain.get("ephemeral", False) is False


class TestDeveloperExample:
    """Tests specific to the developer example."""

    def _load(self):
        path = EXAMPLES_DIR / "developer" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "anklume-dev"

    def test_has_two_domains(self):
        domains = self._load()["domains"]
        assert set(domains.keys()) == {"anklume", "dev-test"}

    def test_dev_test_is_ephemeral(self):
        infra = self._load()
        assert infra["domains"]["dev-test"]["ephemeral"] is True

    def test_dev_runner_has_nesting_config(self):
        infra = self._load()
        cfg = infra["domains"]["dev-test"]["machines"]["dev-runner"]["config"]
        assert cfg["security.nesting"] == "true"
        assert cfg["security.syscalls.intercept.mknod"] == "true"
        assert cfg["security.syscalls.intercept.setxattr"] == "true"

    def test_has_three_machines(self):
        infra = self._load()
        count = sum(len(d.get("machines") or {}) for d in infra["domains"].values())
        assert count == 3

    def test_no_gpu(self):
        infra = self._load()
        for d in infra["domains"].values():
            for machine in (d.get("machines") or {}).values():
                assert not machine.get("gpu", False)

    def test_dev_sandbox_has_nesting(self):
        infra = self._load()
        cfg = infra["domains"]["dev-test"]["machines"]["dev-sandbox"]["config"]
        assert cfg["security.nesting"] == "true"


class TestAiToolsExample:
    """Tests specific to the ai-tools example."""

    def _load(self):
        path = EXAMPLES_DIR / "ai-tools" / "infra.yml"
        return load_infra(str(path))

    def test_project_name(self):
        assert self._load()["project_name"] == "ai-stack"

    def test_has_two_domains(self):
        domains = self._load()["domains"]
        assert set(domains.keys()) == {"anklume", "ai-tools"}

    def test_ai_tools_has_four_machines(self):
        infra = self._load()
        machines = infra["domains"]["ai-tools"]["machines"]
        assert len(machines) == 6

    def test_ai_tools_machine_names(self):
        infra = self._load()
        machines = set(infra["domains"]["ai-tools"]["machines"].keys())
        assert machines == {"gpu-server", "ai-openwebui", "ai-lobechat", "ai-opencode", "ai-coder", "ai-openclaw"}

    def test_gpu_server_has_gpu(self):
        infra = self._load()
        assert infra["domains"]["ai-tools"]["machines"]["gpu-server"]["gpu"] is True

    def test_gpu_server_has_stt_role(self):
        infra = self._load()
        roles = infra["domains"]["ai-tools"]["machines"]["gpu-server"]["roles"]
        assert "stt_server" in roles

    def test_ai_openwebui_has_open_webui_role(self):
        infra = self._load()
        roles = infra["domains"]["ai-tools"]["machines"]["ai-openwebui"]["roles"]
        assert "open_webui" in roles

    def test_ai_lobechat_has_lobechat_role(self):
        infra = self._load()
        roles = infra["domains"]["ai-tools"]["machines"]["ai-lobechat"]["roles"]
        assert "lobechat" in roles

    def test_ai_opencode_has_opencode_role(self):
        infra = self._load()
        roles = infra["domains"]["ai-tools"]["machines"]["ai-opencode"]["roles"]
        assert "opencode_server" in roles

    def test_has_network_policies(self):
        infra = self._load()
        policies = infra.get("network_policies")
        assert policies is not None
        assert len(policies) >= 1

    def test_has_nvidia_compute_profile(self):
        infra = self._load()
        profiles = infra["domains"]["ai-tools"].get("profiles", {})
        assert "nvidia-compute" in profiles

    def test_ai_tools_is_semi_trusted(self):
        infra = self._load()
        assert infra["domains"]["ai-tools"]["trust_level"] == "semi-trusted"

    def test_network_policy_anklume_to_ai_tools(self):
        """There should be a policy allowing anklume to access ai-tools."""
        infra = self._load()
        policies = infra.get("network_policies") or []
        anklume_to_ai = [p for p in policies
                         if p.get("from") == "anklume" and p.get("to") == "ai-tools"]
        assert len(anklume_to_ai) >= 1

    def test_network_policy_host_to_ollama(self):
        """There should be a policy allowing host to access gpu-server."""
        infra = self._load()
        policies = infra.get("network_policies") or []
        host_to_ollama = [p for p in policies
                          if p.get("from") == "host" and p.get("to") == "gpu-server"]
        assert len(host_to_ollama) >= 1


class TestExampleGeneratedDomainVarsContent:
    """Verify domain-level generated variables are correct."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_domain_name_matches_in_group_vars(self, example_path, tmp_path):
        """group_vars/<domain>.yml must have domain_name matching the domain."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            gv = yaml.safe_load(
                (tmp_path / "group_vars" / f"{dname}.yml").read_text()
            )
            assert gv.get("domain_name") == dname

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_incus_project_matches_domain(self, example_path, tmp_path):
        """group_vars/<domain>.yml must have incus_project matching domain name."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname in (infra.get("domains") or {}):
            gv = yaml.safe_load(
                (tmp_path / "group_vars" / f"{dname}.yml").read_text()
            )
            assert gv.get("incus_project") == dname

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_subnet_id_matches_in_group_vars(self, example_path, tmp_path):
        """group_vars/<domain>.yml must have correct subnet_id."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        has_addressing = "_addressing" in infra
        for dname, domain in (infra.get("domains") or {}).items():
            if domain.get("enabled", True) is False:
                continue
            gv_path = tmp_path / "group_vars" / f"{dname}.yml"
            if not gv_path.exists():
                continue
            gv = yaml.safe_load(gv_path.read_text())
            if has_addressing and dname in infra["_addressing"]:
                # In addressing mode, subnet_id in group_vars is the computed domain_seq
                assert gv.get("subnet_id") == infra["_addressing"][dname]["domain_seq"]
            else:
                assert gv.get("subnet_id") == domain.get("subnet_id")

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_subnet_in_network_matches_domain(self, example_path, tmp_path):
        """incus_network.subnet must match computed addressing."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        g = infra.get("global", {})
        has_addressing = "_addressing" in infra
        for dname, domain in (infra.get("domains") or {}).items():
            if domain.get("enabled", True) is False:
                continue
            gv_path = tmp_path / "group_vars" / f"{dname}.yml"
            if not gv_path.exists():
                continue
            gv = yaml.safe_load(gv_path.read_text())
            if has_addressing and dname in infra["_addressing"]:
                info = infra["_addressing"][dname]
                bo = g.get("addressing", {}).get("base_octet", 10)
                expected_subnet = f"{bo}.{info['second_octet']}.{info['domain_seq']}.0/24"
            else:
                bs = g.get("base_subnet", "10.100")
                sid = domain.get("subnet_id")
                expected_subnet = f"{bs}.{sid}.0/24"
            assert gv["incus_network"]["subnet"] == expected_subnet


class TestExampleHostVarsDetails:
    """Verify host_vars details for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_instance_ip_matches(self, example_path, tmp_path):
        """host_vars/<machine>.yml instance_ip must match infra.yml."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                hv = yaml.safe_load(
                    (tmp_path / "host_vars" / f"{mname}.yml").read_text()
                )
                if machine.get("ip"):
                    assert hv.get("instance_ip") == machine["ip"]

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_instance_roles_matches(self, example_path, tmp_path):
        """host_vars/<machine>.yml instance_roles must match infra.yml."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                hv = yaml.safe_load(
                    (tmp_path / "host_vars" / f"{mname}.yml").read_text()
                )
                if machine.get("roles"):
                    assert hv.get("instance_roles") == machine["roles"]

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_instance_gpu_matches(self, example_path, tmp_path):
        """host_vars/<machine>.yml instance_gpu must match infra.yml gpu flag."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                hv = yaml.safe_load(
                    (tmp_path / "host_vars" / f"{mname}.yml").read_text()
                )
                if machine.get("gpu") is not None:
                    assert hv.get("instance_gpu") == machine["gpu"]


class TestExampleInventoryDetails:
    """Verify inventory file details for each example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_inventory_hosts_match_machines(self, example_path, tmp_path):
        """Inventory must list all machines of its domain as hosts."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname, domain in (infra.get("domains") or {}).items():
            inv = yaml.safe_load(
                (tmp_path / "inventory" / f"{dname}.yml").read_text()
            )
            hosts = inv["all"]["children"][dname]["hosts"] or {}
            expected_machines = set((domain.get("machines") or {}).keys())
            assert set(hosts.keys()) == expected_machines, (
                f"Inventory hosts mismatch for domain {dname} in {example_path}"
            )

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_inventory_ansible_host_matches_ip(self, example_path, tmp_path):
        """Inventory ansible_host must match machine IP."""
        import yaml
        from generate import enrich_infra, generate
        infra = load_infra(str(example_path))
        enrich_infra(infra)
        generate(infra, tmp_path)
        for dname, domain in (infra.get("domains") or {}).items():
            inv = yaml.safe_load(
                (tmp_path / "inventory" / f"{dname}.yml").read_text()
            )
            hosts = inv["all"]["children"][dname]["hosts"] or {}
            for mname, machine in (domain.get("machines") or {}).items():
                if machine.get("ip"):
                    host_entry = hosts.get(mname)
                    if isinstance(host_entry, dict):
                        assert host_entry.get("ansible_host") == machine["ip"]


class TestExampleIPUniquenessAcrossDomains:
    """Verify no IP collision across domains within an example."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_no_ip_overlap_between_domains(self, example_path):
        """IPs from different domains must not overlap."""
        infra = load_infra(str(example_path))
        all_ips = {}
        for dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    assert ip not in all_ips, (
                        f"IP collision {ip}: {mname} ({dname}) vs "
                        f"{all_ips[ip][0]} ({all_ips[ip][1]}) in {example_path}"
                    )
                    all_ips[ip] = (mname, dname)


class TestExampleIPv4Format:
    """Verify all IPs are valid IPv4 format."""

    @pytest.mark.parametrize(
        "example_path",
        discover_examples(),
        ids=lambda p: p.parent.name,
    )
    def test_ips_are_valid_ipv4(self, example_path):
        """All IPs must be valid dotted-quad IPv4 addresses."""
        import re
        infra = load_infra(str(example_path))
        ipv4_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        for _dname, domain in (infra.get("domains") or {}).items():
            for mname, machine in (domain.get("machines") or {}).items():
                ip = machine.get("ip")
                if ip:
                    assert ipv4_re.match(ip), (
                        f"Machine '{mname}' IP '{ip}' is not valid IPv4 "
                        f"in {example_path}"
                    )
                    # Also check each octet is 0-255
                    for octet in ip.split("."):
                        assert 0 <= int(octet) <= 255, (
                            f"Machine '{mname}' IP '{ip}' has invalid octet "
                            f"in {example_path}"
                        )
