"""Then step definitions for anklume E2E scenario tests."""

import json

from pytest_bdd import parsers, then


@then("exit code is 0")
def check_exit_zero(sandbox):
    assert sandbox.last_result.returncode == 0, (
        f"Expected exit 0, got {sandbox.last_result.returncode}\n"
        f"stdout: {sandbox.last_result.stdout[:500]}\n"
        f"stderr: {sandbox.last_result.stderr[:500]}"
    )


@then("exit code is non-zero")
def check_exit_nonzero(sandbox):
    assert sandbox.last_result.returncode != 0, (
        f"Expected non-zero exit, got 0\n"
        f"stdout: {sandbox.last_result.stdout[:500]}"
    )


@then(parsers.parse('output contains "{text}"'))
def check_output_contains(sandbox, text):
    combined = sandbox.last_result.stdout + sandbox.last_result.stderr
    assert text in combined, (
        f"Expected '{text}' in output, not found.\n"
        f"stdout: {sandbox.last_result.stdout[:500]}\n"
        f"stderr: {sandbox.last_result.stderr[:500]}"
    )


@then(parsers.parse('stderr contains "{text}"'))
def check_stderr_contains(sandbox, text):
    assert text in sandbox.last_result.stderr, (
        f"Expected '{text}' in stderr, not found.\n"
        f"stderr: {sandbox.last_result.stderr[:500]}"
    )


@then("inventory files exist for all domains")
def check_inventory_files(sandbox):
    infra = sandbox.load_infra()
    for domain in infra.get("domains", {}):
        inv = sandbox.project_dir / "inventory" / f"{domain}.yml"
        assert inv.exists(), f"Missing inventory file: {inv}"


@then(parsers.parse('file "{path}" exists'))
def check_file_exists(sandbox, path):
    full = sandbox.project_dir / path
    assert full.exists(), f"File not found: {full}"


@then(parsers.parse('file "{path}" does not exist'))
def check_file_not_exists(sandbox, path):
    full = sandbox.project_dir / path
    assert not full.exists(), f"File should not exist: {full}"


@then("all declared instances are running")
def check_all_running(sandbox):
    for name, _domain in sandbox.all_declared_instances():
        assert sandbox.instance_running(name), f"Instance {name} is not running"


@then(parsers.parse('instance "{name}" is running in project "{project}"'))
def check_instance_running(sandbox, name, project):
    result = sandbox.run(
        f"incus list --project {project} --format json 2>/dev/null"
    )
    assert result.returncode == 0
    instances = json.loads(result.stdout)
    running = [i for i in instances if i["name"] == name and i["status"] == "Running"]
    assert running, f"Instance {name} not running in project {project}"


@then("intra-domain connectivity works")
def check_intra_domain(sandbox):
    infra = sandbox.load_infra()
    for domain_name, domain in infra.get("domains", {}).items():
        machines = list(domain.get("machines", {}).items())
        if len(machines) < 2:
            continue
        src_name = machines[0][0]
        dst_ip = machines[1][1].get("ip", "")
        if dst_ip:
            result = sandbox.run(
                f"incus exec {src_name} --project {domain_name} -- "
                f"ping -c1 -W2 {dst_ip} 2>/dev/null"
            )
            assert result.returncode == 0, (
                f"Intra-domain ping failed: {src_name} -> {dst_ip}"
            )


@then("inter-domain connectivity is blocked")
def check_inter_domain_blocked(sandbox):
    for src, dst, dst_ip in sandbox.cross_domain_pairs():
        result = sandbox.run(
            f"incus exec {src} -- ping -c1 -W2 {dst_ip} 2>/dev/null"
        )
        assert result.returncode != 0, (
            f"Inter-domain ping should fail: {src} -> {dst} ({dst_ip})"
        )


@then("no Incus resources were created")
def check_no_resources(sandbox):
    """Verify no new Incus projects/instances were created by the failed command."""
    result = sandbox.run("incus project list --format json 2>/dev/null")
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


@then(parsers.parse('the managed section in "{filename}" is unchanged'))
def check_managed_unchanged(sandbox, filename):
    """Verify managed section does not contain injected content."""
    path = sandbox.project_dir / filename
    content = path.read_text()
    assert "SCENARIO-INJECTED" not in content, (
        "Managed section still contains injected content after sync"
    )
