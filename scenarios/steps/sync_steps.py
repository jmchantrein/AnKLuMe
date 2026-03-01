"""Sync step definitions — file generation, managed sections, inventory.

Steps related to `anklume sync`: loading infra.yml, generating files,
verifying managed sections, checking inventory and host_vars output.
"""

import re
import shutil

import yaml
from behave import given, then, when

from scenarios.support import PROTECTED_DIRS


@given('infra.yml from "{example}"')
def load_infra_from_example(context, example):
    """Copy an example infra.yml into place."""
    src = context.sandbox.project_dir / "examples" / example / "infra.yml"
    if not src.exists():
        src = context.sandbox.project_dir / "examples" / f"{example}.infra.yml"
    assert src.exists(), f"Example not found: {src}"
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(src.read_text())


@given("infra.yml exists but no inventory files")
def infra_without_inventory(context):
    """Ensure infra.yml exists but inventory/ is empty."""
    sandbox = context.sandbox
    infra_path = sandbox.project_dir / "infra.yml"
    if not infra_path.exists():
        example = sandbox.project_dir / "examples" / "student-sysadmin" / "infra.yml"
        if example.exists():
            infra_path.write_text(example.read_text())
    inv_dir = sandbox.project_dir / "inventory"
    if inv_dir.exists():
        stash = sandbox.project_dir / ".scenario-stash-inventory"
        stash.mkdir(exist_ok=True)
        for f in inv_dir.glob("*.yml"):
            shutil.move(str(f), str(stash / f.name))


@given('infra.yml with managed section content in "{filename}"')
def infra_with_managed_content(context, filename):
    """Verify a generated file with managed sections exists."""
    path = context.sandbox.project_dir / filename
    assert path.exists(), f"File not found: {path}"


@given("no generated files exist")
def no_generated_files(context):
    """Remove all generated Ansible files."""
    for dirname in PROTECTED_DIRS:
        d = context.sandbox.project_dir / dirname
        if d.exists():
            shutil.rmtree(d)


@when('I add a domain "{domain}" to infra.yml')
def add_domain_to_infra(context, domain):
    """Add a new domain to the current infra.yml."""
    infra = context.sandbox.load_infra()
    infra.setdefault("domains", {})[domain] = {
        "trust_level": "semi-trusted",
        "machines": {
            f"{domain}-test": {
                "type": "lxc",
            }
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@when('I edit the managed section in "{filename}"')
def edit_managed_section(context, filename):
    """Modify content inside a managed section."""
    path = context.sandbox.project_dir / filename
    content = path.read_text()
    if "=== MANAGED" in content:
        content = content.replace(
            "# === END MANAGED ===",
            "# SCENARIO-INJECTED: this will be overwritten\n# === END MANAGED ===",
        )
        path.write_text(content)


@then("inventory files exist for all domains")
def check_inventory_files(context):
    infra = context.sandbox.load_infra()
    for domain in infra.get("domains", {}):
        inv = context.sandbox.project_dir / "inventory" / f"{domain}.yml"
        assert inv.exists(), f"Missing inventory file: {inv}"


@then('file "{path}" exists')
def check_file_exists(context, path):
    full = context.sandbox.project_dir / path
    assert full.exists(), f"File not found: {full}"


@then('file "{path}" does not exist')
def check_file_not_exists(context, path):
    full = context.sandbox.project_dir / path
    assert not full.exists(), f"File should not exist: {full}"


@then('the managed section in "{filename}" is unchanged')
def check_managed_unchanged(context, filename):
    """Verify managed section does not contain injected content."""
    path = context.sandbox.project_dir / filename
    content = path.read_text()
    assert "SCENARIO-INJECTED" not in content, (
        "Managed section still contains injected content after sync"
    )


@then("generated host_vars contain valid IPs")
def check_host_vars_ips(context):
    """Verify all generated host_vars files contain valid IP addresses."""
    ip_pattern = re.compile(r"^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    host_vars_dir = context.sandbox.project_dir / "host_vars"
    assert host_vars_dir.exists(), "host_vars directory not found"
    found_any = False
    for f in host_vars_dir.glob("*.yml"):
        content = yaml.safe_load(f.read_text())
        if not content:
            continue
        ip = content.get("ansible_host") or content.get("instance_ip")
        if ip:
            found_any = True
            assert ip_pattern.match(ip), f"Invalid IP in {f.name}: {ip}"
    assert found_any, "No host_vars files contain IP addresses"
