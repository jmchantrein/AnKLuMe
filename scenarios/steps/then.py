"""Then step definitions for anklume E2E scenario tests."""

import json
import re

import yaml
from behave import then


@then("exit code is 0")
def check_exit_zero(context):
    assert context.sandbox.last_result.returncode == 0, (
        f"Expected exit 0, got {context.sandbox.last_result.returncode}\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )


@then("exit code is non-zero")
def check_exit_nonzero(context):
    assert context.sandbox.last_result.returncode != 0, (
        f"Expected non-zero exit, got 0\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}"
    )


@then('output contains "{text}"')
def check_output_contains(context, text):
    combined = context.sandbox.last_result.stdout + context.sandbox.last_result.stderr
    assert text in combined, (
        f"Expected '{text}' in output, not found.\n"
        f"stdout: {context.sandbox.last_result.stdout[:500]}\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )


@then('stderr contains "{text}"')
def check_stderr_contains(context, text):
    assert text in context.sandbox.last_result.stderr, (
        f"Expected '{text}' in stderr, not found.\n"
        f"stderr: {context.sandbox.last_result.stderr[:500]}"
    )


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


@then("all declared instances are running")
def check_all_running(context):
    for name, _domain in context.sandbox.all_declared_instances():
        assert context.sandbox.instance_running(name), f"Instance {name} is not running"


@then('instance "{name}" is running in project "{project}"')
def check_instance_running(context, name, project):
    result = context.sandbox.run(
        f"incus list --project {project} --format json 2>/dev/null"
    )
    assert result.returncode == 0
    instances = json.loads(result.stdout)
    running = [i for i in instances if i["name"] == name and i["status"] == "Running"]
    assert running, f"Instance {name} not running in project {project}"


@then("intra-domain connectivity works")
def check_intra_domain(context):
    infra = context.sandbox.load_infra()
    for domain_name, domain in infra.get("domains", {}).items():
        machines = list(domain.get("machines", {}).items())
        if len(machines) < 2:
            continue
        src_name = machines[0][0]
        dst_ip = machines[1][1].get("ip", "")
        if dst_ip:
            result = context.sandbox.run(
                f"incus exec {src_name} --project {domain_name} -- "
                f"ping -c1 -W2 {dst_ip} 2>/dev/null"
            )
            assert result.returncode == 0, (
                f"Intra-domain ping failed: {src_name} -> {dst_ip}"
            )


@then("inter-domain connectivity is blocked")
def check_inter_domain_blocked(context):
    for src, dst, dst_ip in context.sandbox.cross_domain_pairs():
        result = context.sandbox.run(
            f"incus exec {src} -- ping -c1 -W2 {dst_ip} 2>/dev/null"
        )
        assert result.returncode != 0, (
            f"Inter-domain ping should fail: {src} -> {dst} ({dst_ip})"
        )


@then("no Incus resources were created")
def check_no_resources(context):
    """Verify no new Incus projects/instances were created by the failed command."""
    result = context.sandbox.run("incus project list --format json 2>/dev/null")
    if result.returncode == 0:
        try:
            projects = json.loads(result.stdout)
            scenario_projects = [
                p for p in projects if "scenario" in p.get("name", "")
            ]
            assert not scenario_projects, (
                f"Unexpected projects created: {scenario_projects}"
            )
        except (json.JSONDecodeError, TypeError):
            pass


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
            assert ip_pattern.match(ip), (
                f"Invalid IP in {f.name}: {ip}"
            )
    assert found_any, "No host_vars files contain IP addresses"
