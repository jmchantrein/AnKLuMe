"""Property-based tests for the PSOT generator using Hypothesis."""

from generate import MANAGED_BEGIN, MANAGED_END, detect_orphans, generate, validate
from hypothesis import given, settings
from hypothesis import strategies as st


def domain_name_strategy():
    """Generate valid domain names (lowercase alphanumeric + hyphen, no leading/trailing hyphen)."""
    return st.from_regex(r"[a-z][a-z0-9-]{0,12}[a-z0-9]", fullmatch=True)


def subnet_id_strategy():
    """Generate valid subnet IDs (0-254)."""
    return st.integers(min_value=0, max_value=254)


def machine_name_strategy():
    """Generate valid machine names."""
    return st.from_regex(r"[a-z][a-z0-9-]{0,18}[a-z0-9]", fullmatch=True)


@st.composite
def valid_infra(draw):
    """Generate a valid infra.yml structure with 1-3 domains, each with 1-2 machines."""
    base_subnet = "10.100"
    num_domains = draw(st.integers(min_value=1, max_value=3))

    # Generate unique domain names and subnet IDs
    domain_names = draw(
        st.lists(domain_name_strategy(), min_size=num_domains, max_size=num_domains, unique=True)
    )
    subnet_ids = draw(
        st.lists(subnet_id_strategy(), min_size=num_domains, max_size=num_domains, unique=True)
    )

    domains = {}
    all_machine_names = set()
    all_ips = set()

    for _i, (dname, sid) in enumerate(zip(domain_names, subnet_ids, strict=True)):
        num_machines = draw(st.integers(min_value=1, max_value=2))
        machines = {}

        for _j in range(num_machines):
            # Generate unique machine name
            mname = draw(machine_name_strategy().filter(lambda n, existing=all_machine_names: n not in existing))
            all_machine_names.add(mname)

            # Generate unique host part for IP
            host_part = draw(st.integers(min_value=1, max_value=253).filter(
                lambda h, s=sid, used=all_ips: f"{base_subnet}.{s}.{h}" not in used
            ))
            ip = f"{base_subnet}.{sid}.{host_part}"
            all_ips.add(ip)

            mtype = draw(st.sampled_from(["lxc", "vm"]))
            machines[mname] = {
                "description": f"Machine {mname}",
                "type": mtype,
                "ip": ip,
            }

        domains[dname] = {
            "description": f"Domain {dname}",
            "subnet_id": sid,
            "machines": machines,
        }

    return {
        "project_name": "prop-test",
        "global": {
            "base_subnet": base_subnet,
            "default_os_image": "images:debian/13",
            "default_connection": "community.general.incus",
            "default_user": "root",
        },
        "domains": domains,
    }


class TestProperties:
    """Property-based tests for generator invariants."""

    @given(infra=valid_infra())
    @settings(max_examples=50)
    def test_validation_returns_list(self, infra):
        """validate() always returns a list (possibly empty for valid input)."""
        result = validate(infra)
        assert isinstance(result, list)

    @given(infra=valid_infra())
    @settings(max_examples=30)
    def test_valid_infra_passes_validation(self, infra):
        """Generated valid infra always passes validation."""
        errors = validate(infra)
        assert errors == [], f"Valid infra should not produce errors: {errors}"

    @given(infra=valid_infra())
    @settings(max_examples=30, deadline=10000)
    def test_idempotent_generation(self, infra, tmp_path_factory):
        """Generating twice produces identical output."""
        out = tmp_path_factory.mktemp("gen")
        generate(infra, out)
        first = {str(f.relative_to(out)): f.read_text() for f in out.rglob("*.yml")}
        generate(infra, out)
        second = {str(f.relative_to(out)): f.read_text() for f in out.rglob("*.yml")}
        assert first == second, "Second generation should match first"

    @given(infra=valid_infra())
    @settings(max_examples=30, deadline=10000)
    def test_no_duplicate_ips_in_output(self, infra, tmp_path_factory):
        """No two host_vars files contain the same instance_ip."""
        out = tmp_path_factory.mktemp("gen")
        generate(infra, out)
        ips = []
        hv_dir = out / "host_vars"
        if hv_dir.exists():
            for f in hv_dir.glob("*.yml"):
                text = f.read_text()
                for line in text.splitlines():
                    if line.strip().startswith("instance_ip:"):
                        ip = line.split(":", 1)[1].strip().strip('"').strip("'")
                        ips.append(ip)
        assert len(ips) == len(set(ips)), f"Duplicate IPs found: {ips}"

    @given(infra=valid_infra())
    @settings(max_examples=30, deadline=10000)
    def test_managed_markers_present(self, infra, tmp_path_factory):
        """All generated files contain managed section markers."""
        out = tmp_path_factory.mktemp("gen")
        generate(infra, out)
        for f in out.rglob("*.yml"):
            text = f.read_text()
            assert MANAGED_BEGIN in text, f"{f.name} missing MANAGED_BEGIN"
            assert MANAGED_END in text, f"{f.name} missing MANAGED_END"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_orphan_detection_consistency(self, infra, tmp_path_factory):
        """detect_orphans finds nothing immediately after generate."""
        out = tmp_path_factory.mktemp("gen")
        generate(infra, out)
        orphans = detect_orphans(infra, out)
        assert orphans == [], f"False positive orphans: {orphans}"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_all_domains_have_files(self, infra, tmp_path_factory):
        """Every domain produces inventory and group_vars files."""
        out = tmp_path_factory.mktemp("gen")
        generate(infra, out)
        for dname in infra.get("domains", {}):
            assert (out / "inventory" / f"{dname}.yml").exists(), f"Missing inventory/{dname}.yml"
            assert (out / "group_vars" / f"{dname}.yml").exists(), f"Missing group_vars/{dname}.yml"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_all_machines_have_host_vars(self, infra, tmp_path_factory):
        """Every machine produces a host_vars file."""
        out = tmp_path_factory.mktemp("gen")
        generate(infra, out)
        for domain in infra.get("domains", {}).values():
            for mname in domain.get("machines", {}):
                assert (out / "host_vars" / f"{mname}.yml").exists(), f"Missing host_vars/{mname}.yml"

    @given(
        infra=valid_infra(),
        bad_name=st.from_regex(r"[A-Z][A-Z0-9!@#]{1,5}", fullmatch=True),
    )
    @settings(max_examples=20)
    def test_invalid_domain_name_rejected(self, infra, bad_name):
        """Adding an invalid domain name causes validation error."""
        infra["domains"][bad_name] = {
            "description": "bad",
            "subnet_id": 250,
            "machines": {},
        }
        errors = validate(infra)
        assert any("invalid name" in e for e in errors)

    @given(infra=valid_infra())
    @settings(max_examples=30, deadline=10000)
    def test_gateway_always_254(self, infra, tmp_path_factory):
        """Every domain gateway is always .254 in the domain subnet."""
        out = tmp_path_factory.mktemp("gw")
        generate(infra, out)
        for dname, dconf in infra.get("domains", {}).items():
            gv = (out / "group_vars" / f"{dname}.yml").read_text()
            sid = dconf["subnet_id"]
            expected_gw = f"10.100.{sid}.254"
            assert expected_gw in gv, f"Gateway {expected_gw} not in {dname} group_vars"

    @given(infra=valid_infra())
    @settings(max_examples=30, deadline=10000)
    def test_subnet_cidr_matches_domain(self, infra, tmp_path_factory):
        """Every domain group_vars has a subnet CIDR matching base_subnet.subnet_id."""
        out = tmp_path_factory.mktemp("cidr")
        generate(infra, out)
        for dname, dconf in infra.get("domains", {}).items():
            gv = (out / "group_vars" / f"{dname}.yml").read_text()
            sid = dconf["subnet_id"]
            expected_subnet = f"10.100.{sid}.0/24"
            assert expected_subnet in gv, f"Subnet {expected_subnet} not in {dname} group_vars"

    @given(infra=valid_infra())
    @settings(max_examples=30, deadline=10000)
    def test_instance_type_in_host_vars(self, infra, tmp_path_factory):
        """Every machine host_vars contains instance_type matching the infra declaration."""
        out = tmp_path_factory.mktemp("type")
        generate(infra, out)
        for domain in infra.get("domains", {}).values():
            for mname, mconf in domain.get("machines", {}).items():
                hv = (out / "host_vars" / f"{mname}.yml").read_text()
                expected_type = mconf.get("type", "lxc")
                assert f"instance_type: {expected_type}" in hv, \
                    f"Expected instance_type: {expected_type} in {mname}.yml"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_no_ansible_connection_in_group_vars(self, infra, tmp_path_factory):
        """No group_vars file contains ansible_connection (ADR-015)."""
        out = tmp_path_factory.mktemp("conn")
        generate(infra, out)
        gv_dir = out / "group_vars"
        if gv_dir.exists():
            for f in gv_dir.glob("*.yml"):
                text = f.read_text()
                assert "ansible_connection:" not in text, \
                    f"ansible_connection found in {f.name} (violates ADR-015)"
                assert "ansible_user:" not in text, \
                    f"ansible_user found in {f.name} (violates ADR-015)"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_all_yml_contains_project_name(self, infra, tmp_path_factory):
        """group_vars/all.yml always contains the project_name."""
        out = tmp_path_factory.mktemp("proj")
        generate(infra, out)
        all_yml = (out / "group_vars" / "all.yml").read_text()
        assert infra["project_name"] in all_yml, "project_name missing from all.yml"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_ephemeral_inheritance(self, infra, tmp_path_factory):
        """Machines without explicit ephemeral inherit from domain."""
        import yaml as _yaml
        # Set domain ephemeral to True on first domain
        first_domain = next(iter(infra["domains"]))
        infra["domains"][first_domain]["ephemeral"] = True
        out = tmp_path_factory.mktemp("eph")
        generate(infra, out)
        for mname in infra["domains"][first_domain].get("machines", {}):
            hv = (out / "host_vars" / f"{mname}.yml").read_text()
            data = _yaml.safe_load(hv)
            assert data.get("instance_ephemeral") is True, \
                f"{mname} should inherit ephemeral=true from domain"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_machine_ephemeral_overrides_domain(self, infra, tmp_path_factory):
        """Machine-level ephemeral overrides domain-level."""
        import yaml as _yaml
        first_domain = next(iter(infra["domains"]))
        infra["domains"][first_domain]["ephemeral"] = True
        first_machine = next(iter(infra["domains"][first_domain]["machines"]))
        infra["domains"][first_domain]["machines"][first_machine]["ephemeral"] = False
        out = tmp_path_factory.mktemp("eph_override")
        generate(infra, out)
        hv = (out / "host_vars" / f"{first_machine}.yml").read_text()
        data = _yaml.safe_load(hv)
        assert data.get("instance_ephemeral") is False, \
            f"{first_machine} should override domain ephemeral with False"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_user_content_preserved_across_generations(self, infra, tmp_path_factory):
        """User content outside managed section is preserved on re-generation."""
        out = tmp_path_factory.mktemp("preserve")
        generate(infra, out)
        first_domain = next(iter(infra["domains"]))
        gv_file = out / "group_vars" / f"{first_domain}.yml"
        original = gv_file.read_text()
        user_content = "\n# User-added custom variable\nmy_custom_var: hello\n"
        gv_file.write_text(original + user_content)
        generate(infra, out)
        updated = gv_file.read_text()
        assert "my_custom_var: hello" in updated, "User content should be preserved"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_orphans_appear_after_domain_removal(self, infra, tmp_path_factory):
        """Removing a domain from infra causes its files to become orphans."""
        out = tmp_path_factory.mktemp("orphan")
        generate(infra, out)
        if len(infra["domains"]) < 2:
            return  # Need at least 2 domains for this test
        removed_domain = list(infra["domains"].keys())[-1]
        list(infra["domains"][removed_domain].get("machines", {}).keys())
        del infra["domains"][removed_domain]
        orphans = detect_orphans(infra, out)
        orphan_files = {str(f) for f, _ in orphans}
        assert any(removed_domain in f for f in orphan_files), \
            f"Removing {removed_domain} should create orphan files"


class TestAdditionalProperties:
    """Additional property-based tests for generator invariants."""

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_network_name_matches_domain(self, infra, tmp_path_factory):
        """Every group_vars has incus_network.name == 'net-{domain}'."""
        import yaml as _yaml
        out = tmp_path_factory.mktemp("netname")
        generate(infra, out)
        for dname in infra.get("domains", {}):
            gv_file = out / "group_vars" / f"{dname}.yml"
            data = _yaml.safe_load(gv_file.read_text())
            assert "incus_network" in data, f"{dname} group_vars missing incus_network"
            net_name = data["incus_network"]["name"]
            expected = f"net-{dname}"
            assert net_name == expected, \
                f"Expected incus_network.name={expected}, got {net_name} in {dname}"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_instance_name_in_host_vars(self, infra, tmp_path_factory):
        """Every host_vars has instance_name matching the filename."""
        import yaml as _yaml
        out = tmp_path_factory.mktemp("instname")
        generate(infra, out)
        for domain in infra.get("domains", {}).values():
            for mname in domain.get("machines", {}):
                hv_file = out / "host_vars" / f"{mname}.yml"
                data = _yaml.safe_load(hv_file.read_text())
                assert data.get("instance_name") == mname, \
                    f"Expected instance_name={mname}, got {data.get('instance_name')}"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_group_vars_all_has_global_settings(self, infra, tmp_path_factory):
        """group_vars/all.yml contains psot_default_connection and psot_default_user."""
        import yaml as _yaml
        out = tmp_path_factory.mktemp("allglobal")
        generate(infra, out)
        all_file = out / "group_vars" / "all.yml"
        data = _yaml.safe_load(all_file.read_text())
        expected_conn = infra["global"].get("default_connection")
        expected_user = infra["global"].get("default_user")
        if expected_conn is not None:
            assert data.get("psot_default_connection") == expected_conn, \
                f"Expected psot_default_connection={expected_conn}, got {data.get('psot_default_connection')}"
        if expected_user is not None:
            assert data.get("psot_default_user") == expected_user, \
                f"Expected psot_default_user={expected_user}, got {data.get('psot_default_user')}"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_domain_description_in_group_vars(self, infra, tmp_path_factory):
        """Domain descriptions appear in group_vars."""
        import yaml as _yaml
        out = tmp_path_factory.mktemp("domdesc")
        generate(infra, out)
        for dname, dconf in infra.get("domains", {}).items():
            gv_file = out / "group_vars" / f"{dname}.yml"
            data = _yaml.safe_load(gv_file.read_text())
            expected_desc = dconf.get("description", "")
            assert data.get("domain_description") == expected_desc, \
                f"Expected domain_description='{expected_desc}' in {dname}, " \
                f"got '{data.get('domain_description')}'"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_host_vars_instance_type_strict_format(self, infra, tmp_path_factory):
        """Every host_vars has instance_type as exactly 'lxc' or 'vm'."""
        import yaml as _yaml
        out = tmp_path_factory.mktemp("typefmt")
        generate(infra, out)
        for domain in infra.get("domains", {}).values():
            for mname, mconf in domain.get("machines", {}).items():
                hv_file = out / "host_vars" / f"{mname}.yml"
                data = _yaml.safe_load(hv_file.read_text())
                itype = data.get("instance_type")
                assert itype in ("lxc", "vm"), \
                    f"instance_type must be 'lxc' or 'vm', got '{itype}' in {mname}"
                assert itype == mconf.get("type", "lxc"), \
                    f"instance_type mismatch in {mname}: file={itype}, infra={mconf.get('type', 'lxc')}"

    @given(infra=valid_infra())
    @settings(max_examples=20)
    def test_duplicate_subnet_rejected(self, infra):
        """Adding the same subnet_id to two domains fails validation."""
        # Pick any existing domain's subnet_id and add a new domain with the same ID
        first_domain = next(iter(infra["domains"]))
        existing_sid = infra["domains"][first_domain]["subnet_id"]
        infra["domains"]["dup-subnet-test"] = {
            "description": "duplicate subnet test",
            "subnet_id": existing_sid,
            "machines": {},
        }
        errors = validate(infra)
        assert any("subnet_id" in e and str(existing_sid) in e for e in errors), \
            f"Duplicate subnet_id {existing_sid} should produce validation error, got: {errors}"

    @given(infra=valid_infra())
    @settings(max_examples=20)
    def test_duplicate_machine_name_rejected(self, infra):
        """Same machine name in two domains fails validation."""
        # Pick any existing machine name and add it in a different domain
        first_domain = next(iter(infra["domains"]))
        first_machine = next(iter(infra["domains"][first_domain]["machines"]))
        # Find a unique subnet_id and domain name
        used_sids = {d["subnet_id"] for d in infra["domains"].values()}
        new_sid = next(s for s in range(255) if s not in used_sids)
        infra["domains"]["dup-machine-test"] = {
            "description": "duplicate machine test",
            "subnet_id": new_sid,
            "machines": {
                first_machine: {
                    "description": "duplicate",
                    "type": "lxc",
                    "ip": f"10.100.{new_sid}.42",
                },
            },
        }
        errors = validate(infra)
        assert any("duplicate" in e.lower() and first_machine in e for e in errors), \
            f"Duplicate machine '{first_machine}' should produce validation error, got: {errors}"

    @given(infra=valid_infra())
    @settings(max_examples=20)
    def test_ip_outside_subnet_rejected(self, infra):
        """IP not matching subnet_id is rejected by validation."""
        first_domain = next(iter(infra["domains"]))
        sid = infra["domains"][first_domain]["subnet_id"]
        # Create a machine with an IP in a different subnet
        wrong_subnet = (sid + 1) % 255
        # Find a unique machine name
        all_machines = {m for d in infra["domains"].values() for m in d.get("machines", {})}
        new_name = "wrong-ip-test"
        while new_name in all_machines:
            new_name = new_name + "x"
        infra["domains"][first_domain]["machines"][new_name] = {
            "description": "wrong subnet IP",
            "type": "lxc",
            "ip": f"10.100.{wrong_subnet}.42",
        }
        errors = validate(infra)
        assert any("not in subnet" in e.lower() and new_name in e for e in errors), \
            f"IP in wrong subnet should produce validation error, got: {errors}"

    @given(infra=valid_infra())
    @settings(max_examples=20, deadline=10000)
    def test_roles_list_preserved_in_host_vars(self, infra, tmp_path_factory):
        """If roles specified, they appear in host_vars as instance_roles."""
        import yaml as _yaml
        # Set roles on the first machine of the first domain
        first_domain = next(iter(infra["domains"]))
        first_machine = next(iter(infra["domains"][first_domain]["machines"]))
        roles_list = ["base_system", "ollama_server"]
        infra["domains"][first_domain]["machines"][first_machine]["roles"] = roles_list
        out = tmp_path_factory.mktemp("roles")
        generate(infra, out)
        hv_file = out / "host_vars" / f"{first_machine}.yml"
        data = _yaml.safe_load(hv_file.read_text())
        assert data.get("instance_roles") == roles_list, \
            f"Expected instance_roles={roles_list}, got {data.get('instance_roles')}"
