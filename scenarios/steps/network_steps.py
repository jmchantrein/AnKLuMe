"""Network step definitions — connectivity and isolation checks.

Steps for verifying intra-domain connectivity and inter-domain
isolation via nftables rules.
"""

from behave import then


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
