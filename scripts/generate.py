#!/usr/bin/env python3
"""PSOT Generator — generates Ansible file tree from infra.yml."""

import argparse
import contextlib
import ipaddress
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

# Zone offsets for trust-level-aware addressing (ADR-038)
ZONE_OFFSETS = {
    "admin": 0,
    "trusted": 10,
    "semi-trusted": 20,
    "untrusted": 40,
    "disposable": 50,
}
DEFAULT_TRUST_LEVEL = "semi-trusted"

MANAGED_BEGIN = "# === MANAGED BY infra.yml ==="
MANAGED_END = "# === END MANAGED ==="
MANAGED_NOTICE = "# Do not edit this section — it will be overwritten by `make sync`"
MANAGED_RE = re.compile(re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END), re.DOTALL)


class _Dumper(yaml.SafeDumper):
    """YAML dumper: None as empty, preserves insertion order, proper list indent."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


_Dumper.add_representer(type(None), lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", ""))


def _yaml(data):
    return yaml.dump(data, Dumper=_Dumper, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _read_absolute_level():
    """Read /etc/anklume/absolute_level context file. Returns int or None."""
    try:
        return int(Path("/etc/anklume/absolute_level").read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _get_nesting_prefix(infra):
    """Compute nesting prefix string from infra config.

    Returns a prefix like "001-" if nesting_prefix is enabled (default),
    or "" if explicitly disabled.
    """
    g = infra.get("global", {})
    if not g.get("nesting_prefix", True):
        return ""
    level = _read_absolute_level()
    if level is None:
        return ""  # No context file = physical host, no prefix
    return f"{level:03d}-"


def _read_vm_nested():
    """Read /etc/anklume/vm_nested context file. Returns True/False/None."""
    try:
        return Path("/etc/anklume/vm_nested").read_text().strip().lower() == "true"
    except FileNotFoundError:
        return None


def _read_yolo():
    """Read /etc/anklume/yolo context file. Returns True if YOLO mode active."""
    try:
        return Path("/etc/anklume/yolo").read_text().strip().lower() == "true"
    except FileNotFoundError:
        return False


def _detect_host_subnets():
    """Detect network subnets on host interfaces via `ip -json addr show`.

    Returns a list of (interface_name, network) tuples where network is an
    ipaddress.IPv4Network. Returns empty list if detection fails.
    """
    try:
        result = subprocess.run(
            ["ip", "-json", "addr", "show"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []

    subnets = []
    for iface in data:
        ifname = iface.get("ifname", "")
        # Skip loopback and Incus bridges (net-*)
        if ifname == "lo" or ifname.startswith("net-"):
            continue
        for addr_info in iface.get("addr_info", []):
            if addr_info.get("family") != "inet":
                continue
            try:
                net = ipaddress.IPv4Network(
                    f"{addr_info['local']}/{addr_info['prefixlen']}", strict=False
                )
                subnets.append((ifname, net))
            except (KeyError, ValueError):
                continue
    return subnets


def _detect_host_resources():
    """Detect host CPU count and total memory.

    Tries 'incus info --resources --format json' first, then /proc fallback.
    Returns {"cpu": int, "memory_bytes": int} or None if detection fails.
    """
    try:
        result = subprocess.run(
            ["incus", "info", "--resources", "--format", "json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            cpu_total = data.get("cpu", {}).get("total", 0)
            mem_total = data.get("memory", {}).get("total", 0)
            if cpu_total > 0 and mem_total > 0:
                return {"cpu": cpu_total, "memory_bytes": mem_total}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # Fallback: /proc
    try:
        cpu_count = 0
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("processor"):
                    cpu_count += 1
        mem_bytes = 0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_bytes = int(line.split()[1]) * 1024
                    break
        if cpu_count > 0 and mem_bytes > 0:
            return {"cpu": cpu_count, "memory_bytes": mem_bytes}
    except (FileNotFoundError, ValueError, IndexError):
        pass

    return None


def _parse_memory_value(value):
    """Parse Incus memory string (e.g., '2GiB', '512MiB') to bytes."""
    value = str(value).strip()
    suffixes = {"GiB": 1024**3, "MiB": 1024**2, "KiB": 1024, "GB": 10**9, "MB": 10**6}
    for suffix, mult in suffixes.items():
        if value.endswith(suffix):
            try:
                return int(float(value[: -len(suffix)]) * mult)
            except ValueError:
                return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _format_memory(bytes_val):
    """Format bytes as Incus memory string (e.g., '2GiB', '512MiB')."""
    gib = bytes_val / (1024**3)
    if gib >= 1 and int(gib) == gib:
        return f"{int(gib)}GiB"
    mib = bytes_val / (1024**2)
    if mib >= 1:
        return f"{int(mib)}MiB"
    return str(bytes_val)


def _collect_gpu_instances(infra):
    """Collect machine names that have GPU access (direct flag or profile device)."""
    gpu_instances = []
    for domain in (infra.get("domains") or {}).values():
        domain_profiles = domain.get("profiles") or {}
        for mname, machine in (domain.get("machines") or {}).items():
            has_gpu = machine.get("gpu", False)
            if not has_gpu:
                for pname in machine.get("profiles") or []:
                    if pname in domain_profiles:
                        pdevices = domain_profiles[pname].get("devices") or {}
                        if any(d.get("type") == "gpu" for d in pdevices.values()):
                            has_gpu = True
                            break
            if has_gpu:
                gpu_instances.append(mname)
    return gpu_instances


def load_infra(path):
    """Load infra.yml (file) or infra/ (directory) and return parsed dict.

    Directory mode merges: base.yml + domains/*.yml + policies.yml.
    Auto-detects format based on whether path is a file or directory.
    """
    p = Path(path)

    if p.is_file():
        with open(p) as f:
            return yaml.safe_load(f)

    if p.is_dir():
        return _load_infra_dir(p)

    # Path does not exist — try both conventions
    yml_path = Path(str(p).removesuffix("/") + ".yml") if not str(p).endswith(".yml") else p
    dir_path = Path(str(p).removesuffix(".yml")) if str(p).endswith(".yml") else p

    if yml_path.is_file():
        with open(yml_path) as f:
            return yaml.safe_load(f)
    if dir_path.is_dir():
        return _load_infra_dir(dir_path)

    # Fall back to original behavior (will raise FileNotFoundError)
    with open(path) as f:
        return yaml.safe_load(f)


def _load_infra_dir(dirpath):
    """Load infra/ directory: base.yml + domains/*.yml + policies.yml."""
    dirpath = Path(dirpath)
    base_path = dirpath / "base.yml"
    if not base_path.exists():
        raise ValueError(f"{base_path} not found in infra directory.")

    with open(base_path) as f:
        infra = yaml.safe_load(f) or {}

    # Merge domain files
    domains_dir = dirpath / "domains"
    if domains_dir.is_dir():
        infra.setdefault("domains", {})
        for domain_file in sorted(domains_dir.glob("*.yml")):
            with open(domain_file) as f:
                domain_data = yaml.safe_load(f) or {}
            for dname, dconfig in domain_data.items():
                if dname in infra["domains"]:
                    print(f"WARNING: Domain '{dname}' in {domain_file.name} "
                          f"overrides existing definition.", file=sys.stderr)
                infra["domains"][dname] = dconfig

    # Merge policies
    policies_path = dirpath / "policies.yml"
    if policies_path.exists():
        with open(policies_path) as f:
            policies_data = yaml.safe_load(f) or {}
        if "network_policies" in policies_data:
            infra["network_policies"] = policies_data["network_policies"]

    return infra


def validate(infra, *, check_host_subnets=True):
    """Validate infra.yml constraints. Returns list of error strings (empty = OK)."""
    errors = []
    for key in ("project_name", "global", "domains"):
        if key not in infra:
            errors.append(f"Missing required key: {key}")
    if errors:
        return errors

    domains = infra.get("domains") or {}
    g = infra.get("global", {})
    base_subnet = g.get("base_subnet", "10.100")
    gpu_policy = g.get("gpu_policy", "exclusive")
    subnet_ids, all_machines, all_ips = {}, {}, {}

    # Addressing mode detection (ADR-038)
    has_addressing = "addressing" in g
    computed_addressing = {}
    zone_subnet_ids = {}  # (trust_level, sid) -> dname for per-zone duplicate check
    if has_addressing:
        addr_cfg = g["addressing"]
        if not isinstance(addr_cfg, dict):
            errors.append("global.addressing must be a mapping")
        else:
            base_octet = addr_cfg.get("base_octet", 10)
            if base_octet != 10:
                errors.append(f"global.addressing.base_octet must be 10 (only RFC 1918 /8), got {base_octet}")
            zone_base = addr_cfg.get("zone_base", 100)
            if not isinstance(zone_base, int) or not 0 <= zone_base <= 245:
                errors.append(f"global.addressing.zone_base must be 0-245, got {zone_base}")
            zone_step = addr_cfg.get("zone_step", 10)
            if not isinstance(zone_step, int) or zone_step < 1:
                errors.append(f"global.addressing.zone_step must be a positive integer, got {zone_step}")
            # Compute addressing for IP validation
            computed_addressing = _compute_addressing(infra)

    valid_types = ("lxc", "vm")
    valid_gpu_policies = ("exclusive", "shared")
    valid_firewall_modes = ("host", "vm")
    firewall_mode = g.get("firewall_mode", "host")
    vm_nested = _read_vm_nested()
    yolo = _read_yolo()

    nesting_prefix = g.get("nesting_prefix")
    if nesting_prefix is not None and not isinstance(nesting_prefix, bool):
        errors.append(f"global.nesting_prefix must be a boolean, got {type(nesting_prefix).__name__}")

    if gpu_policy not in valid_gpu_policies:
        errors.append(f"global.gpu_policy must be 'exclusive' or 'shared', got '{gpu_policy}'")
    if firewall_mode not in valid_firewall_modes:
        errors.append(f"global.firewall_mode must be 'host' or 'vm', got '{firewall_mode}'")

    # AI access policy validation (Phase 18a)
    ai_access_policy = g.get("ai_access_policy", "open")
    valid_ai_policies = ("exclusive", "open")
    if ai_access_policy not in valid_ai_policies:
        errors.append(f"global.ai_access_policy must be 'exclusive' or 'open', got '{ai_access_policy}'")

    for dname, domain in domains.items():
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", dname):
            errors.append(f"Domain '{dname}': invalid name (lowercase alphanumeric + hyphen, no trailing hyphen)")
        # Validate enabled field (boolean, default true)
        enabled = domain.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            errors.append(f"Domain '{dname}': enabled must be a boolean, got {type(enabled).__name__}")

        sid = domain.get("subnet_id")
        if has_addressing:
            # Addressing mode: subnet_id is optional (auto-computed from trust_level)
            if sid is not None:
                if not isinstance(sid, int) or not 0 <= sid <= 254:
                    errors.append(f"Domain '{dname}': subnet_id must be 0-254, got {sid}")
                else:
                    trust = domain.get("trust_level", DEFAULT_TRUST_LEVEL)
                    zone_key = (trust, sid)
                    if zone_key in zone_subnet_ids:
                        errors.append(
                            f"Domain '{dname}': subnet_id {sid} already used by "
                            f"'{zone_subnet_ids[zone_key]}' in zone '{trust}'"
                        )
                    else:
                        zone_subnet_ids[zone_key] = dname
        else:
            # Legacy mode: subnet_id required
            if sid is None:
                errors.append(f"Domain '{dname}': missing subnet_id")
            elif not isinstance(sid, int) or not 0 <= sid <= 254:
                errors.append(f"Domain '{dname}': subnet_id must be 0-254, got {sid}")
            elif sid in subnet_ids:
                errors.append(f"Domain '{dname}': subnet_id {sid} already used by '{subnet_ids[sid]}'")
            else:
                subnet_ids[sid] = dname

        domain_eph = domain.get("ephemeral")
        if domain_eph is not None and not isinstance(domain_eph, bool):
            errors.append(f"Domain '{dname}': ephemeral must be a boolean, got {type(domain_eph).__name__}")

        valid_trust_levels = ("admin", "trusted", "semi-trusted", "untrusted", "disposable")
        trust_level = domain.get("trust_level")
        if trust_level is not None and trust_level not in valid_trust_levels:
            errors.append(
                f"Domain '{dname}': trust_level must be one of "
                f"{valid_trust_levels}, got '{trust_level}'"
            )

        domain_profiles = domain.get("profiles") or {}
        domain_profile_names = set(domain_profiles)
        for mname, machine in (domain.get("machines") or {}).items():
            if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", mname):
                errors.append(f"Machine '{mname}': invalid name (lowercase alphanumeric + hyphen, no trailing hyphen)")
            if mname in all_machines:
                errors.append(f"Machine '{mname}': duplicate (already in '{all_machines[mname]}')")
            else:
                all_machines[mname] = dname

            # Validate instance type
            mtype = machine.get("type", "lxc")
            if mtype not in valid_types:
                errors.append(f"Machine '{mname}': type must be 'lxc' or 'vm', got '{mtype}'")

            # Privileged LXC policy (ADR-020)
            mconfig = machine.get("config") or {}
            is_privileged = str(mconfig.get("security.privileged", "false")).lower() == "true"
            if is_privileged and mtype == "lxc" and vm_nested is False:
                if yolo:
                    pass  # YOLO mode: privileged warnings handled in get_warnings()
                else:
                    errors.append(
                        f"Machine '{mname}': security.privileged=true on LXC is forbidden "
                        f"when vm_nested=false (no VM in parent chain). Use a VM or "
                        f"enable --YOLO to bypass."
                    )

            ip = machine.get("ip")
            if ip:
                if ip in all_ips:
                    errors.append(f"Machine '{mname}': IP {ip} already used by '{all_ips[ip]}'")
                else:
                    all_ips[ip] = mname
                if has_addressing and dname in computed_addressing:
                    info = computed_addressing[dname]
                    addr_cfg = g["addressing"]
                    bo = addr_cfg.get("base_octet", 10)
                    expected_prefix = f"{bo}.{info['second_octet']}.{info['domain_seq']}."
                    if not ip.startswith(expected_prefix):
                        errors.append(
                            f"Machine '{mname}': IP {ip} not in subnet "
                            f"{expected_prefix}0/24"
                        )
                elif not has_addressing and sid is not None and not ip.startswith(f"{base_subnet}.{sid}."):
                    errors.append(f"Machine '{mname}': IP {ip} not in subnet {base_subnet}.{sid}.0/24")
            machine_eph = machine.get("ephemeral")
            if machine_eph is not None and not isinstance(machine_eph, bool):
                errors.append(f"Machine '{mname}': ephemeral must be a boolean, got {type(machine_eph).__name__}")
            for p in machine.get("profiles") or []:
                if p != "default" and p not in domain_profile_names:
                    errors.append(f"Machine '{mname}': profile '{p}' not defined in domain '{dname}'")

            # Validate boot_autostart (boolean) and boot_priority (int 0-100)
            boot_autostart = machine.get("boot_autostart")
            if boot_autostart is not None and not isinstance(boot_autostart, bool):
                errors.append(
                    f"Machine '{mname}': boot_autostart must be a boolean, "
                    f"got {type(boot_autostart).__name__}"
                )
            boot_priority = machine.get("boot_priority")
            if boot_priority is not None and (
                not isinstance(boot_priority, int) or not 0 <= boot_priority <= 100
            ):
                errors.append(
                    f"Machine '{mname}': boot_priority must be an integer 0-100, "
                    f"got {boot_priority}"
                )

            # Validate snapshots_schedule (basic cron) and snapshots_expiry (Nd)
            snap_sched = machine.get("snapshots_schedule")
            if snap_sched is not None and (
                not isinstance(snap_sched, str)
                or not re.match(r"^(\S+\s+){4}\S+$", snap_sched)
            ):
                errors.append(
                    f"Machine '{mname}': snapshots_schedule must be a cron expression "
                    f"(5 fields), got '{snap_sched}'"
                )
            snap_expiry = machine.get("snapshots_expiry")
            if snap_expiry is not None and (
                not isinstance(snap_expiry, str)
                or not re.match(r"^\d+[dhm]$", snap_expiry)
            ):
                errors.append(
                    f"Machine '{mname}': snapshots_expiry must be a duration "
                    f"(e.g., '30d', '24h', '60m'), got '{snap_expiry}'"
                )

            # Validate weight for resource_policy
            weight = machine.get("weight")
            if weight is not None and (not isinstance(weight, int) or weight < 1):
                errors.append(
                    f"Machine '{mname}': weight must be a positive integer, got {weight}"
                )

    # GPU policy enforcement (ADR-018)
    gpu_instances = _collect_gpu_instances(infra)
    if len(gpu_instances) > 1 and gpu_policy == "exclusive":
        errors.append(
            f"GPU policy is 'exclusive' but {len(gpu_instances)} instances have GPU access: "
            f"{', '.join(gpu_instances)}. Set global.gpu_policy: shared to allow this."
        )

    # Network policies validation (ADR-021)
    domain_names = set(domains)
    for i, policy in enumerate(infra.get("network_policies") or []):
        if not isinstance(policy, dict):
            errors.append(f"network_policies[{i}]: must be a mapping")
            continue
        for field in ("from", "to"):
            ref = policy.get(field)
            if ref is None:
                errors.append(f"network_policies[{i}]: missing '{field}'")
            elif ref != "host" and ref not in domain_names and ref not in all_machines:
                errors.append(
                    f"network_policies[{i}]: '{field}: {ref}' is not a known "
                    f"domain, machine, or 'host'"
                )
        ports = policy.get("ports")
        if ports is not None and ports != "all":
            if isinstance(ports, list):
                for port in ports:
                    if not isinstance(port, int) or not 1 <= port <= 65535:
                        errors.append(
                            f"network_policies[{i}]: invalid port {port} (must be 1-65535)"
                        )
            else:
                errors.append(f"network_policies[{i}]: ports must be a list or 'all'")
        protocol = policy.get("protocol")
        if protocol is not None and protocol not in ("tcp", "udp"):
            errors.append(f"network_policies[{i}]: protocol must be 'tcp' or 'udp', got '{protocol}'")
        bidirectional = policy.get("bidirectional")
        if bidirectional is not None and not isinstance(bidirectional, bool):
            errors.append(f"network_policies[{i}]: bidirectional must be a boolean, got {type(bidirectional).__name__}")

    # AI access policy exclusive-mode validation (Phase 18a)
    if ai_access_policy == "exclusive":
        ai_access_default = g.get("ai_access_default")
        if ai_access_default is None:
            errors.append("global.ai_access_default is required when ai_access_policy is 'exclusive'")
        elif ai_access_default == "ai-tools":
            errors.append("global.ai_access_default cannot be 'ai-tools' (must be a client domain)")
        elif ai_access_default not in domain_names:
            errors.append(f"global.ai_access_default '{ai_access_default}' is not a known domain")

        if "ai-tools" not in domain_names:
            errors.append("ai_access_policy is 'exclusive' but no 'ai-tools' domain exists")

        ai_tools_policies = [
            p for p in (infra.get("network_policies") or [])
            if isinstance(p, dict) and p.get("to") == "ai-tools"
        ]
        if len(ai_tools_policies) > 1:
            errors.append(
                f"ai_access_policy is 'exclusive' but {len(ai_tools_policies)} "
                f"network_policies target ai-tools (max 1 allowed)"
            )

    # Resource policy validation
    resource_policy = g.get("resource_policy")
    if resource_policy is not None and resource_policy is not True:
        if not isinstance(resource_policy, dict):
            errors.append("global.resource_policy must be a mapping or true")
        else:
            rp_mode = resource_policy.get("mode", "proportional")
            if rp_mode not in ("proportional", "equal"):
                errors.append(
                    f"resource_policy.mode must be 'proportional' or 'equal', got '{rp_mode}'"
                )
            rp_cpu_mode = resource_policy.get("cpu_mode", "allowance")
            if rp_cpu_mode not in ("allowance", "count"):
                errors.append(
                    f"resource_policy.cpu_mode must be 'allowance' or 'count', got '{rp_cpu_mode}'"
                )
            rp_mem_enforce = resource_policy.get("memory_enforce", "soft")
            if rp_mem_enforce not in ("soft", "hard"):
                errors.append(
                    f"resource_policy.memory_enforce must be 'soft' or 'hard', "
                    f"got '{rp_mem_enforce}'"
                )
            rp_overcommit = resource_policy.get("overcommit", False)
            if not isinstance(rp_overcommit, bool):
                errors.append("resource_policy.overcommit must be a boolean")
            hr = resource_policy.get("host_reserve")
            if hr is not None:
                if not isinstance(hr, dict):
                    errors.append("resource_policy.host_reserve must be a mapping")
                else:
                    for field in ("cpu", "memory"):
                        val = hr.get(field)
                        if val is None:
                            continue
                        if isinstance(val, str) and val.endswith("%"):
                            try:
                                pct = int(val.rstrip("%"))
                                if not 0 < pct < 100:
                                    errors.append(
                                        f"resource_policy.host_reserve.{field}: "
                                        f"percentage must be 1-99, got {pct}"
                                    )
                            except ValueError:
                                errors.append(
                                    f"resource_policy.host_reserve.{field}: "
                                    f"invalid format '{val}'"
                                )
                        elif isinstance(val, (int, float)):
                            if val <= 0:
                                errors.append(
                                    f"resource_policy.host_reserve.{field}: "
                                    f"must be positive, got {val}"
                                )
                        elif isinstance(val, str) and field == "memory":
                            if _parse_memory_value(val) <= 0:
                                errors.append(
                                    f"resource_policy.host_reserve.memory: "
                                    f"invalid value '{val}'"
                                )
                        else:
                            errors.append(
                                f"resource_policy.host_reserve.{field}: "
                                f"must be 'N%' or a positive number, got '{val}'"
                            )

    # Host subnet conflict detection — prevents routing loops
    # Skip if check_host_subnets=False or env ANKLUME_SKIP_HOST_SUBNET_CHECK=1
    skip_host_check = (
        not check_host_subnets
        or os.environ.get("ANKLUME_SKIP_HOST_SUBNET_CHECK") == "1"
    )
    host_subnets = [] if skip_host_check else _detect_host_subnets()
    if host_subnets:
        # Build list of (domain_name, network) to check
        subnets_to_check = []
        if has_addressing and computed_addressing:
            addr_cfg = g.get("addressing", {})
            bo = addr_cfg.get("base_octet", 10)
            for dname, info in computed_addressing.items():
                try:
                    net = ipaddress.IPv4Network(
                        f"{bo}.{info['second_octet']}.{info['domain_seq']}.0/24"
                    )
                    subnets_to_check.append((dname, net))
                except ValueError:
                    continue
        else:
            for sid, dname in subnet_ids.items():
                try:
                    net = ipaddress.IPv4Network(f"{base_subnet}.{sid}.0/24")
                    subnets_to_check.append((dname, net))
                except ValueError:
                    continue

        for dname, domain_net in subnets_to_check:
            for ifname, host_net in host_subnets:
                if domain_net.overlaps(host_net):
                    if has_addressing:
                        fix_hint = "Adjust global.addressing.zone_base or use a different subnet_id."
                    else:
                        alt_base = "10.200" if base_subnet == "10.100" else "10.100"
                        fix_hint = (
                            f"Change global.base_subnet to '{alt_base}' or use a "
                            f"different subnet_id for this domain."
                        )
                    errors.append(
                        f"SUBNET CONFLICT: Domain '{dname}' uses {domain_net} which "
                        f"overlaps with host interface '{ifname}' ({host_net}). "
                        f"Incus would create a bridge on the same subnet, causing a "
                        f"routing loop and total loss of network connectivity. "
                        f"{fix_hint}"
                    )

    return errors


def get_warnings(infra):
    """Return non-fatal warnings about the infra configuration."""
    warnings = []
    g = infra.get("global", {})
    gpu_policy = g.get("gpu_policy", "exclusive")
    domains = infra.get("domains") or {}
    gpu_instances = _collect_gpu_instances(infra)
    yolo = _read_yolo()
    vm_nested = _read_vm_nested()

    for domain in domains.values():
        for mname, machine in (domain.get("machines") or {}).items():
            # YOLO mode: privileged LXC warning instead of error
            mconfig = machine.get("config") or {}
            is_privileged = str(mconfig.get("security.privileged", "false")).lower() == "true"
            mtype = machine.get("type", "lxc")
            if is_privileged and mtype == "lxc" and vm_nested is False and yolo:
                warnings.append(
                    f"YOLO: Machine '{mname}' has security.privileged=true on LXC "
                    f"without VM isolation. This is unsafe for production."
                )

    if len(gpu_instances) > 1 and gpu_policy == "shared":
        warnings.append(
            f"GPU policy is 'shared': {len(gpu_instances)} instances share GPU access "
            f"({', '.join(gpu_instances)}). No VRAM isolation on consumer GPUs."
        )

    # Warn if network_policies reference disabled domains
    disabled_domains = {
        dname for dname, d in domains.items()
        if d.get("enabled", True) is False
    }
    if disabled_domains:
        for i, policy in enumerate(infra.get("network_policies") or []):
            if not isinstance(policy, dict):
                continue
            for field in ("from", "to"):
                ref = policy.get(field)
                if ref in disabled_domains:
                    warnings.append(
                        f"network_policies[{i}]: '{field}: {ref}' references "
                        f"disabled domain '{ref}'"
                    )

    return warnings


def enrich_infra(infra):
    """Enrich infra dict with auto-generated resources.

    Called after validate() and before generate(). Mutates infra in place.
    Handles: auto-creation of sys-firewall VM, AI access policy enrichment.
    """
    _enrich_addressing(infra)
    _enrich_firewall(infra)
    _enrich_ai_access(infra)
    _enrich_resources(infra)


def _enrich_addressing(infra):
    """Compute zone-based addressing and auto-assign IPs.

    Runs when global.addressing is present. Sets default trust_level,
    computes zone addressing, and auto-assigns IPs to machines without
    explicit ip: fields. Stores results in infra['_addressing'].
    """
    g = infra.get("global", {})
    if "addressing" not in g:
        return  # Legacy mode (base_subnet), no zone addressing

    addr = g["addressing"]
    base_octet = addr.get("base_octet", 10)

    # Default trust_level to semi-trusted for domains that don't have one
    for domain in (infra.get("domains") or {}).values():
        domain.setdefault("trust_level", DEFAULT_TRUST_LEVEL)

    # Compute zone-based addressing
    addressing = _compute_addressing(infra)
    infra["_addressing"] = addressing

    # Auto-assign IPs per domain
    for dname, domain in (infra.get("domains") or {}).items():
        if dname in addressing:
            info = addressing[dname]
            _auto_assign_ips(domain, base_octet, info["second_octet"], info["domain_seq"])


def _compute_addressing(infra):
    """Compute zone-based addressing from trust levels.

    Groups domains by trust_level, computes second_octet from zone_base + offset,
    and assigns domain_seq (third octet) alphabetically within each zone.
    Explicit subnet_id overrides auto-assignment.

    Returns dict: {domain_name: {"second_octet": int, "domain_seq": int}}
    """
    g = infra.get("global", {})
    addr = g.get("addressing", {})
    zone_base = addr.get("zone_base", 100)
    domains = infra.get("domains") or {}

    # Group domains by trust_level
    zones = {}
    for dname, domain in domains.items():
        trust = domain.get("trust_level", DEFAULT_TRUST_LEVEL)
        zones.setdefault(trust, []).append(dname)

    result = {}
    for trust_level, domain_names in zones.items():
        zone_offset = ZONE_OFFSETS.get(trust_level, ZONE_OFFSETS[DEFAULT_TRUST_LEVEL])
        second_octet = zone_base + zone_offset

        # Separate explicit subnet_id from auto-assign
        explicit_seqs = {}
        auto_names = []
        for dname in sorted(domain_names):
            sid = domains[dname].get("subnet_id")
            if sid is not None:
                explicit_seqs[sid] = dname
            else:
                auto_names.append(dname)

        # Auto-assign domain_seq, skipping explicit values
        seq = 0
        for dname in auto_names:
            while seq in explicit_seqs:
                seq += 1
            explicit_seqs[seq] = dname
            seq += 1

        for seq_val, dname in explicit_seqs.items():
            result[dname] = {"second_octet": second_octet, "domain_seq": seq_val}

    return result


def _auto_assign_ips(domain, base_octet, second_octet, domain_seq):
    """Auto-assign IPs to machines without explicit ip: field.

    Assigns addresses starting from .1 in the static range (.1-.99),
    skipping already-used host numbers. Machines are processed in
    declaration order.
    """
    machines = domain.get("machines") or {}
    subnet_prefix = f"{base_octet}.{second_octet}.{domain_seq}"

    # Collect already-used host numbers in this subnet
    used = set()
    for m in machines.values():
        ip = m.get("ip")
        if ip and ip.startswith(f"{subnet_prefix}."):
            try:
                host = int(ip.rsplit(".", 1)[1])
                used.add(host)
            except (ValueError, IndexError):
                pass

    # Assign IPs to machines without one (declaration order)
    next_host = 1
    for mname, m in machines.items():
        if not m.get("ip"):
            while next_host in used and next_host <= 99:
                next_host += 1
            if next_host > 99:
                raise ValueError(
                    f"Domain ran out of static IPs (.1-.99) for machine '{mname}'"
                )
            m["ip"] = f"{subnet_prefix}.{next_host}"
            used.add(next_host)
            next_host += 1


def _enrich_firewall(infra):
    """Auto-create sys-firewall VM when firewall_mode is 'vm'."""
    g = infra.get("global", {})
    firewall_mode = g.get("firewall_mode", "host")
    if firewall_mode != "vm":
        return

    domains = infra.get("domains") or {}

    # Check if sys-firewall already exists in any domain (user override)
    for domain in domains.values():
        for mname in (domain.get("machines") or {}):
            if mname == "sys-firewall":
                return

    # Require anklume domain
    if "anklume" not in domains:
        raise ValueError(
            "firewall_mode is 'vm' but no 'anklume' domain exists. "
            "Cannot auto-create sys-firewall."
        )

    anklume_domain = domains["anklume"]

    # Compute firewall IP from addressing or legacy base_subnet
    if "_addressing" in infra and "anklume" in infra.get("_addressing", {}):
        info = infra["_addressing"]["anklume"]
        addr_cfg = g.get("addressing", {})
        bo = addr_cfg.get("base_octet", 10)
        fw_ip = f"{bo}.{info['second_octet']}.{info['domain_seq']}.253"
    else:
        base_subnet = g.get("base_subnet", "10.100")
        anklume_subnet_id = anklume_domain.get("subnet_id", 0)
        fw_ip = f"{base_subnet}.{anklume_subnet_id}.253"

    sys_fw = {
        "description": "Centralized firewall VM (auto-created by generator)",
        "type": "vm",
        "ip": fw_ip,
        "config": {
            "limits.cpu": "2",
            "limits.memory": "2GiB",
        },
        "roles": ["base_system", "firewall_router"],
        "ephemeral": False,
    }

    if "machines" not in anklume_domain or anklume_domain["machines"] is None:
        anklume_domain["machines"] = {}
    anklume_domain["machines"]["sys-firewall"] = sys_fw

    print("INFO: firewall_mode is 'vm' — auto-created sys-firewall in anklume domain "
          f"(ip: {fw_ip})", file=sys.stderr)


def _enrich_ai_access(infra):
    """Auto-create network policy for exclusive AI access if missing."""
    g = infra.get("global", {})
    ai_access_policy = g.get("ai_access_policy", "open")
    if ai_access_policy != "exclusive":
        return

    ai_access_default = g.get("ai_access_default")
    if not ai_access_default or "ai-tools" not in (infra.get("domains") or {}):
        return

    existing_policies = infra.get("network_policies") or []
    has_ai_policy = any(
        isinstance(p, dict) and p.get("to") == "ai-tools"
        for p in existing_policies
    )
    if has_ai_policy:
        return

    infra.setdefault("network_policies", [])
    infra["network_policies"].append({
        "description": f"AI access: {ai_access_default} -> ai-tools (auto-created)",
        "from": ai_access_default,
        "to": "ai-tools",
        "ports": "all",
        "bidirectional": True,
    })
    print(f"INFO: ai_access_policy is 'exclusive' — auto-created network policy "
          f"from '{ai_access_default}' to 'ai-tools'", file=sys.stderr)


def _enrich_resources(infra):
    """Auto-allocate CPU and memory based on resource_policy."""
    g = infra.get("global", {})
    policy = g.get("resource_policy")
    if policy is None:
        return

    # resource_policy: true → all defaults
    if policy is True:
        policy = {}
    if not isinstance(policy, dict):
        return

    host = _detect_host_resources()
    if host is None:
        print("WARNING: Could not detect host resources, "
              "skipping resource allocation.", file=sys.stderr)
        return

    host_reserve = policy.get("host_reserve", {})
    if not isinstance(host_reserve, dict):
        host_reserve = {}

    mode = policy.get("mode", "proportional")
    cpu_mode = policy.get("cpu_mode", "allowance")
    memory_enforce = policy.get("memory_enforce", "soft")
    overcommit = policy.get("overcommit", False)

    # Parse CPU reserve
    cpu_reserve_val = host_reserve.get("cpu", "20%")
    if isinstance(cpu_reserve_val, str) and cpu_reserve_val.endswith("%"):
        reserve_cpu = host["cpu"] * int(cpu_reserve_val.rstrip("%")) / 100
    else:
        reserve_cpu = float(cpu_reserve_val)

    # Parse memory reserve
    mem_reserve_val = host_reserve.get("memory", "20%")
    if isinstance(mem_reserve_val, str) and mem_reserve_val.endswith("%"):
        reserve_mem = int(host["memory_bytes"] * int(mem_reserve_val.rstrip("%")) / 100)
    elif isinstance(mem_reserve_val, str):
        reserve_mem = _parse_memory_value(mem_reserve_val)
    else:
        reserve_mem = int(mem_reserve_val)

    available_cpu = host["cpu"] - reserve_cpu
    available_mem = host["memory_bytes"] - reserve_mem

    if available_cpu <= 0 or available_mem <= 0:
        print("WARNING: Host reserve exceeds available resources, "
              "skipping resource allocation.", file=sys.stderr)
        return

    # Collect machines needing allocation
    domains = infra.get("domains") or {}
    entries = []  # (machine_dict, weight, needs_cpu, needs_mem)

    for domain in domains.values():
        for machine in (domain.get("machines") or {}).values():
            config = machine.get("config") or {}
            needs_cpu = "limits.cpu" not in config and "limits.cpu.allowance" not in config
            needs_mem = "limits.memory" not in config
            if needs_cpu or needs_mem:
                entries.append((machine, machine.get("weight", 1), needs_cpu, needs_mem))

    if not entries:
        # Still apply memory_enforce to explicit machines
        if memory_enforce == "soft":
            _apply_memory_enforce(infra)
        return

    # CPU distribution
    cpu_entries = [(m, w) for m, w, nc, _ in entries if nc]
    if cpu_entries:
        w_total = len(cpu_entries) if mode == "equal" else sum(w for _, w in cpu_entries)
        for m, w in cpu_entries:
            share = available_cpu * (1 if mode == "equal" else w) / w_total
            config = m.setdefault("config", {})
            if cpu_mode == "count":
                config["limits.cpu"] = str(max(1, int(share)))
            else:
                pct = max(1, int(share / host["cpu"] * 100))
                config["limits.cpu.allowance"] = f"{pct}%"

    # Memory distribution
    mem_entries = [(m, w) for m, w, _, nm in entries if nm]
    if mem_entries:
        w_total = len(mem_entries) if mode == "equal" else sum(w for _, w in mem_entries)
        for m, w in mem_entries:
            share = int(available_mem * (1 if mode == "equal" else w) / w_total)
            share = max(128 * 1024 * 1024, share)  # min 128 MiB
            config = m.setdefault("config", {})
            config["limits.memory"] = _format_memory(share)

    # Apply memory_enforce: soft
    if memory_enforce == "soft":
        _apply_memory_enforce(infra)

    # Overcommit check — core counts and allowance % are independent constraints
    total_cpu_count = 0.0
    total_cpu_allowance_pct = 0.0
    total_mem = 0
    for domain in domains.values():
        for machine in (domain.get("machines") or {}).values():
            config = machine.get("config") or {}
            if "limits.cpu" in config:
                with contextlib.suppress(ValueError, TypeError):
                    total_cpu_count += int(config["limits.cpu"])
            elif "limits.cpu.allowance" in config:
                val = str(config["limits.cpu.allowance"])
                if val.endswith("%"):
                    with contextlib.suppress(ValueError):
                        total_cpu_allowance_pct += int(val.rstrip("%"))
            if "limits.memory" in config:
                total_mem += _parse_memory_value(config["limits.memory"])

    max_allowance_pct = available_cpu / host["cpu"] * 100
    cpu_count_over = total_cpu_count > available_cpu * 1.001
    cpu_allowance_over = total_cpu_allowance_pct > max_allowance_pct * 1.001
    mem_over = total_mem > available_mem
    if cpu_count_over or cpu_allowance_over or mem_over:
        parts = []
        if cpu_count_over:
            parts.append(
                f"CPU: {total_cpu_count:.0f} cores > {available_cpu:.0f} available"
            )
        if cpu_allowance_over:
            parts.append(
                f"CPU allowance: {total_cpu_allowance_pct:.0f}% > "
                f"{max_allowance_pct:.0f}% available"
            )
        if mem_over:
            parts.append(
                f"Memory: {_format_memory(total_mem)} > "
                f"{_format_memory(int(available_mem))}"
            )
        msg = "Resource overcommit: " + "; ".join(parts)
        if not overcommit:
            raise ValueError(
                f"{msg}. Set resource_policy.overcommit: true to allow."
            )
        else:
            print(f"WARNING: {msg}", file=sys.stderr)


def _apply_memory_enforce(infra):
    """Set limits.memory.enforce: soft on all machines with limits.memory."""
    for domain in (infra.get("domains") or {}).values():
        for machine in (domain.get("machines") or {}).values():
            config = machine.get("config") or {}
            if "limits.memory" in config and "limits.memory.enforce" not in config:
                config["limits.memory.enforce"] = "soft"


def extract_all_images(infra):
    """Collect all unique OS image references from infra.yml.

    Scans every machine's os_image (falling back to global.default_os_image)
    and returns a sorted list of unique image references.
    Used to populate incus_all_images in group_vars/all.yml for the
    incus_images pre-download role.
    """
    g = infra.get("global", {})
    default_image = g.get("default_os_image")
    images = set()

    for domain in (infra.get("domains") or {}).values():
        for machine in (domain.get("machines") or {}).values():
            image = machine.get("os_image", default_image)
            if image:
                images.add(image)

    return sorted(images)


def _managed_block(content_yaml):
    return f"{MANAGED_BEGIN}\n{MANAGED_NOTICE}\n{content_yaml.rstrip()}\n{MANAGED_END}"


def _write_managed(filepath, content_dict, dry_run=False):
    """Write or update a file, replacing only the managed section."""
    filepath = Path(filepath)
    block = _managed_block(_yaml(content_dict))

    if filepath.exists():
        existing = filepath.read_text()
        if MANAGED_RE.search(existing):
            new_content = MANAGED_RE.sub(block, existing, count=1)
        else:
            prefix = "" if existing.startswith("---") else "---\n"
            new_content = f"{prefix}{block}\n\n{existing}"
    else:
        new_content = f"---\n{block}\n\n# Your custom variables below:\n"

    if dry_run:
        return filepath, new_content
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(new_content)
    return filepath, new_content


def generate(infra, base_dir, dry_run=False):
    """Generate all Ansible files. Returns list of written file paths."""
    base = Path(base_dir)
    domains = infra.get("domains") or {}
    g = infra.get("global", {})
    prefix = _get_nesting_prefix(infra)
    written = []

    # group_vars/all.yml
    # Connection params stored as psot_* (informational only).
    # They must NOT be named ansible_connection / ansible_user because
    # inventory variables override play-level keywords (Ansible precedence).
    all_images = extract_all_images(infra)
    network_policies = infra.get("network_policies")
    has_addressing = "addressing" in g
    all_vars = {k: v for k, v in {
        "project_name": infra.get("project_name"),
        "addressing": g.get("addressing") if has_addressing else None,
        "base_subnet": g.get("base_subnet", "10.100") if not has_addressing else None,
        "default_os_image": g.get("default_os_image"),
        "psot_default_connection": g.get("default_connection"),
        "psot_default_user": g.get("default_user"),
        "incus_all_images": all_images if all_images else None,
        "network_policies": network_policies if network_policies else None,
    }.items() if v is not None}
    fp, _ = _write_managed(base / "group_vars" / "all.yml", all_vars, dry_run)
    written.append(fp)

    for dname, domain in domains.items():
        # Skip disabled domains
        if domain.get("enabled", True) is False:
            continue

        machines = domain.get("machines") or {}

        # Compute subnet/gateway from addressing or legacy base_subnet
        if has_addressing and "_addressing" in infra and dname in infra["_addressing"]:
            addr_info = infra["_addressing"][dname]
            addr_cfg = g["addressing"]
            bo = addr_cfg.get("base_octet", 10)
            so = addr_info["second_octet"]
            ds = addr_info["domain_seq"]
            subnet_str = f"{bo}.{so}.{ds}.0/24"
            gateway_str = f"{bo}.{so}.{ds}.254"
            sid = ds  # For subnet_id in group_vars
        else:
            sid = domain.get("subnet_id")
            bs = g.get("base_subnet", "10.100")
            subnet_str = f"{bs}.{sid}.0/24"
            gateway_str = f"{bs}.{sid}.254"

        # inventory/<domain>.yml
        hosts = {}
        for mname, m in machines.items():
            hosts[mname] = {"ansible_host": m["ip"]} if m.get("ip") else None
        inv = {"all": {"children": {dname: {"hosts": hosts or None}}}}
        fp, _ = _write_managed(base / "inventory" / f"{dname}.yml", inv, dry_run)
        written.append(fp)

        # group_vars/<domain>.yml
        domain_ephemeral = domain.get("ephemeral", False)
        gvars = {k: v for k, v in {
            "domain_name": dname,
            "domain_description": domain.get("description", ""),
            "domain_ephemeral": domain_ephemeral,
            "domain_trust_level": domain.get("trust_level"),
            "incus_project": f"{prefix}{dname}",
            "incus_network": {
                "name": f"{prefix}net-{dname}",
                "subnet": subnet_str,
                "gateway": gateway_str,
            },
            "subnet_id": sid,
        }.items() if v is not None}
        if domain.get("profiles"):
            gvars["incus_profiles"] = domain["profiles"]
        fp, _ = _write_managed(base / "group_vars" / f"{dname}.yml", gvars, dry_run)
        written.append(fp)

        # host_vars/<machine>.yml
        for mname, m in machines.items():
            machine_eph = m.get("ephemeral")
            instance_ephemeral = machine_eph if machine_eph is not None else domain_ephemeral
            hvars = {k: v for k, v in {
                "instance_name": f"{prefix}{mname}",
                "instance_type": m.get("type", "lxc"),
                "instance_description": m.get("description", ""),
                "instance_domain": dname,
                "instance_ephemeral": instance_ephemeral,
                "instance_os_image": m.get("os_image", g.get("default_os_image")),
                "instance_ip": m.get("ip"),
                "instance_gpu": m.get("gpu"),
                "instance_profiles": m.get("profiles"),
                "instance_config": m.get("config"),
                "instance_devices": m.get("devices"),
                "instance_storage_volumes": m.get("storage_volumes"),
                "instance_roles": m.get("roles"),
                "instance_boot_autostart": m.get("boot_autostart"),
                "instance_boot_priority": m.get("boot_priority"),
                "instance_snapshots_schedule": m.get("snapshots_schedule"),
                "instance_snapshots_expiry": m.get("snapshots_expiry"),
            }.items() if v is not None}
            fp, _ = _write_managed(base / "host_vars" / f"{mname}.yml", hvars, dry_run)
            written.append(fp)

    return written


def detect_orphans(infra, base_dir):
    """Return orphan files as list of (filepath, is_protected) tuples.

    Protected orphans (ephemeral=false) should be reported but never auto-deleted.
    """
    base = Path(base_dir)
    domains = infra.get("domains") or {}
    domain_names = set(domains)
    machine_names = {m for d in domains.values() for m in (d.get("machines") or {})}

    orphans = []

    for subdir, valid_names in [("inventory", domain_names), ("group_vars", domain_names | {"all"})]:
        d = base / subdir
        if d.exists():
            for f in d.glob("*.yml"):
                if f.stem not in valid_names:
                    # Check if the orphan file corresponds to a previously protected domain
                    is_protected = _is_orphan_protected(f)
                    orphans.append((f, is_protected))

    hv = base / "host_vars"
    if hv.exists():
        for f in hv.glob("*.yml"):
            if f.stem not in machine_names:
                is_protected = _is_orphan_protected(f)
                orphans.append((f, is_protected))

    return orphans


def _is_orphan_protected(filepath):
    """Check if an orphan file contains ephemeral: false (protected)."""
    try:
        content = Path(filepath).read_text()
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return False
        # Check domain-level or instance-level ephemeral
        for key in ("domain_ephemeral", "instance_ephemeral"):
            if key in data:
                return not data[key]
        # Default: not protected (no ephemeral info found)
        return False
    except Exception:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate Ansible files from infra.yml")
    parser.add_argument("infra_file", help="Path to infra.yml or infra/ directory")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--clean-orphans", action="store_true", help="Remove orphan files")
    parser.add_argument("--base-dir", default=".", help="Output base directory")
    args = parser.parse_args(argv)

    try:
        infra = load_infra(args.infra_file)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate(infra)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    try:
        enrich_infra(infra)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Re-validate after enrichment to catch IP collisions from auto-created resources
    post_errors = validate(infra, check_host_subnets=False)
    if post_errors:
        print("Post-enrichment validation errors:", file=sys.stderr)
        for e in post_errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    warnings = get_warnings(infra)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)

    domains = infra.get("domains") or {}
    if not domains:
        print("No domains defined. Nothing to generate.")
        return

    enabled_count = sum(1 for d in domains.values() if d.get("enabled", True) is not False)
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Generating files for {enabled_count} domain(s)...")
    written = generate(infra, args.base_dir, args.dry_run)
    for fp in written:
        print(f"  {prefix}{'Would write' if args.dry_run else 'Written'}: {fp}")

    orphans = detect_orphans(infra, args.base_dir)
    if orphans:
        print(f"\nOrphan files ({len(orphans)}):")
        for filepath, is_protected in orphans:
            if is_protected:
                print(f"  PROTECTED (ephemeral=false): {filepath} — manual removal required")
            else:
                print(f"  ORPHAN: {filepath}")
        if args.clean_orphans and not args.dry_run:
            for filepath, is_protected in orphans:
                if is_protected:
                    print(f"  Skipped (protected): {filepath}")
                else:
                    Path(filepath).unlink()
                    print(f"  Deleted: {filepath}")

    if not args.dry_run:
        print("\nDone. Run `make lint` to validate.")


if __name__ == "__main__":
    main()
