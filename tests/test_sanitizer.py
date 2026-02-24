"""Tests for LLM sanitization proxy (Phase 39, ADR-044).

Generator validation for ai_provider / ai_sanitize fields,
and pattern matching tests for IaC detection patterns.
"""

import re

import yaml
from generate import (
    enrich_infra,
    generate,
    validate,
)


def _base_infra(**domain_extra):
    """Helper to build infra dict with optional domain-level overrides."""
    domain = {
        "description": "Production",
        "subnet_id": 0,
        "machines": {
            "pro-dev": {
                "description": "Dev",
                "type": "lxc",
                "ip": "10.100.0.1",
            },
        },
        **domain_extra,
    }
    return {
        "project_name": "test",
        "global": {
            "base_subnet": "10.100",
            "default_os_image": "images:debian/13",
            "default_connection": "community.general.incus",
            "default_user": "root",
        },
        "domains": {
            "pro": domain,
        },
    }


# -- Validation tests (Matrix: SAN-001 to SAN-005) ----------------------------


class TestAiProviderValidation:
    def test_valid_local(self):  # Matrix: SAN-001
        """ai_provider: local is accepted."""
        infra = _base_infra(ai_provider="local")
        assert validate(infra) == []

    def test_valid_cloud(self):  # Matrix: SAN-001
        """ai_provider: cloud is accepted."""
        infra = _base_infra(ai_provider="cloud")
        assert validate(infra) == []

    def test_valid_local_first(self):  # Matrix: SAN-001
        """ai_provider: local-first is accepted."""
        infra = _base_infra(ai_provider="local-first")
        assert validate(infra) == []

    def test_invalid_provider(self):  # Matrix: SAN-002
        """Invalid ai_provider value triggers validation error."""
        infra = _base_infra(ai_provider="aws-bedrock")
        errors = validate(infra)
        assert any("ai_provider" in e for e in errors)
        assert any("aws-bedrock" in e for e in errors)

    def test_omitted_provider_is_valid(self):  # Matrix: SAN-001
        """Omitting ai_provider is valid (defaults to local)."""
        infra = _base_infra()
        assert validate(infra) == []


class TestAiSanitizeValidation:
    def test_valid_true(self):  # Matrix: SAN-003
        """ai_sanitize: true is accepted."""
        infra = _base_infra(ai_sanitize=True)
        assert validate(infra) == []

    def test_valid_false(self):  # Matrix: SAN-003
        """ai_sanitize: false is accepted."""
        infra = _base_infra(ai_sanitize=False)
        assert validate(infra) == []

    def test_valid_always(self):  # Matrix: SAN-003
        """ai_sanitize: 'always' is accepted."""
        infra = _base_infra(ai_sanitize="always")
        assert validate(infra) == []

    def test_invalid_sanitize(self):  # Matrix: SAN-004
        """Invalid ai_sanitize value triggers validation error."""
        infra = _base_infra(ai_sanitize="maybe")
        errors = validate(infra)
        assert any("ai_sanitize" in e for e in errors)

    def test_omitted_sanitize_is_valid(self):  # Matrix: SAN-003
        """Omitting ai_sanitize is valid (auto-defaults in generator)."""
        infra = _base_infra()
        assert validate(infra) == []


# -- Generation / propagation tests (Matrix: SAN-005, SAN-006) ----------------


class TestAiPropagation:
    def test_default_local_propagation(self, tmp_path):  # Matrix: SAN-005
        """Default ai_provider=local, ai_sanitize=false propagated to group_vars."""
        infra = _base_infra()
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert gv["domain_ai_provider"] == "local"
        assert gv["domain_ai_sanitize"] is False

    def test_cloud_defaults_sanitize_true(self, tmp_path):  # Matrix: SAN-005
        """ai_provider=cloud without explicit ai_sanitize defaults to true."""
        infra = _base_infra(ai_provider="cloud")
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert gv["domain_ai_provider"] == "cloud"
        assert gv["domain_ai_sanitize"] is True

    def test_local_first_defaults_sanitize_true(self, tmp_path):  # Matrix: SAN-005
        """ai_provider=local-first without explicit ai_sanitize defaults to true."""
        infra = _base_infra(ai_provider="local-first")
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert gv["domain_ai_provider"] == "local-first"
        assert gv["domain_ai_sanitize"] is True

    def test_explicit_sanitize_overrides_default(self, tmp_path):  # Matrix: SAN-006
        """Explicit ai_sanitize=false overrides cloud default."""
        infra = _base_infra(ai_provider="cloud", ai_sanitize=False)
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert gv["domain_ai_provider"] == "cloud"
        assert gv["domain_ai_sanitize"] is False

    def test_always_sanitize_propagated(self, tmp_path):  # Matrix: SAN-006
        """ai_sanitize='always' is propagated as a string."""
        infra = _base_infra(ai_provider="local", ai_sanitize="always")
        enrich_infra(infra)
        generate(infra, tmp_path)
        gv = yaml.safe_load((tmp_path / "group_vars" / "pro.yml").read_text())
        assert gv["domain_ai_sanitize"] == "always"


# -- Pattern matching tests (Matrix: SAN-007) ----------------------------------


# Patterns extracted from patterns.yml.j2 for direct testing
PATTERNS = {
    "anklume_zone_ips": r"\b10\.1[0-5][0-9]\.\d{1,3}\.\d{1,3}\b",
    "rfc1918_class_a": r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    "rfc1918_class_b": r"\b172\.(1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}\b",
    "rfc1918_class_c": r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    "incus_bridge": r"\b(\d{3}-)?net-[a-z][a-z0-9-]*\b",
    "internal_domain": r"\b[a-z0-9][a-z0-9.-]*\.internal\b",
    "corp_domain": r"\b[a-z0-9][a-z0-9.-]*\.corp\b",
    "local_domain": r"\b[a-z0-9][a-z0-9.-]*\.local\b",
    "bearer_token": r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}",
    "api_key_header": r"(?i)(x-api-key|authorization|api[_-]?key)\s*[:=]\s*\S{10,}",
    "generic_secret": r"(?i)(password|secret|token|api_key)\s*[:=]\s*[^\s,;}]{8,}",
    "ssh_private_key": r"-----BEGIN\s+(RSA|OPENSSH|EC|DSA)\s+PRIVATE\s+KEY-----",
    "group_vars_path": r"group_vars/[a-z][a-z0-9-]+\.yml",
    "host_vars_path": r"host_vars/[a-z][a-z0-9-]+\.yml",
    "ansible_host_var": r"ansible_host:\s*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    "subnet_cidr": r"\b10\.1[0-5][0-9]\.\d{1,3}\.0/24\b",
}


class TestIpPatterns:
    def test_anklume_zone_ip(self):  # Matrix: SAN-007
        """Pattern matches anklume convention IPs (10.100-159.x.x)."""
        pattern = re.compile(PATTERNS["anklume_zone_ips"])
        assert pattern.search("connected to 10.120.0.5 on port 22")
        assert pattern.search("gateway 10.100.0.254")
        assert pattern.search("subnet 10.150.3.1")
        # Should not match non-zone IPs
        assert not pattern.search("connected to 10.200.0.5")
        assert not pattern.search("version 10.160.0.1")

    def test_rfc1918_class_b(self):  # Matrix: SAN-007
        """Pattern matches 172.16-31.x.x range."""
        pattern = re.compile(PATTERNS["rfc1918_class_b"])
        assert pattern.search("route via 172.16.0.1")
        assert pattern.search("host 172.31.255.254")
        assert not pattern.search("host 172.15.0.1")
        assert not pattern.search("host 172.32.0.1")

    def test_rfc1918_class_c(self):  # Matrix: SAN-007
        """Pattern matches 192.168.x.x range."""
        pattern = re.compile(PATTERNS["rfc1918_class_c"])
        assert pattern.search("my router at 192.168.1.1")
        assert not pattern.search("server at 192.169.1.1")

    def test_subnet_cidr(self):  # Matrix: SAN-007
        """Pattern matches anklume CIDR subnets."""
        pattern = re.compile(PATTERNS["subnet_cidr"])
        assert pattern.search("network 10.120.0.0/24")
        assert not pattern.search("network 10.200.0.0/24")


class TestIncusPatterns:
    def test_bridge_name(self):  # Matrix: SAN-007
        """Pattern matches Incus bridge names."""
        pattern = re.compile(PATTERNS["incus_bridge"])
        assert pattern.search("interface net-pro is up")
        assert pattern.search("bridge 001-net-admin connected")

    def test_fqdn_internal(self):  # Matrix: SAN-007
        """Pattern matches *.internal domains."""
        pattern = re.compile(PATTERNS["internal_domain"])
        assert pattern.search("resolved db.staging.internal")
        assert not pattern.search("resolved example.com")

    def test_fqdn_corp(self):  # Matrix: SAN-007
        """Pattern matches *.corp domains."""
        pattern = re.compile(PATTERNS["corp_domain"])
        assert pattern.search("mail.company.corp")

    def test_fqdn_local(self):  # Matrix: SAN-007
        """Pattern matches *.local mDNS domains."""
        pattern = re.compile(PATTERNS["local_domain"])
        assert pattern.search("printer.local")


class TestCredentialPatterns:
    def test_bearer_token(self):  # Matrix: SAN-007
        """Pattern matches Bearer tokens."""
        pattern = re.compile(PATTERNS["bearer_token"])
        assert pattern.search("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test")
        assert not pattern.search("Bearer short")

    def test_api_key(self):  # Matrix: SAN-007
        """Pattern matches API key headers."""
        pattern = re.compile(PATTERNS["api_key_header"])
        assert pattern.search("X-API-Key: sk-1234567890abcdef")
        assert pattern.search("api_key=supersecretvalue123")

    def test_generic_secret(self):  # Matrix: SAN-007
        """Pattern matches common secret patterns."""
        pattern = re.compile(PATTERNS["generic_secret"])
        assert pattern.search("password=MyS3cr3tP4ss!")
        assert pattern.search("token=ghp_ABCDEFghijklmnop1234")

    def test_ssh_key(self):  # Matrix: SAN-007
        """Pattern matches SSH private key headers."""
        pattern = re.compile(PATTERNS["ssh_private_key"])
        assert pattern.search("-----BEGIN RSA PRIVATE KEY-----")
        assert pattern.search("-----BEGIN OPENSSH PRIVATE KEY-----")


class TestAnsiblePatterns:
    def test_group_vars_path(self):  # Matrix: SAN-007
        """Pattern matches group_vars file paths."""
        pattern = re.compile(PATTERNS["group_vars_path"])
        assert pattern.search("editing group_vars/pro.yml")
        assert pattern.search("in group_vars/ai-tools.yml")

    def test_host_vars_path(self):  # Matrix: SAN-007
        """Pattern matches host_vars file paths."""
        pattern = re.compile(PATTERNS["host_vars_path"])
        assert pattern.search("reading host_vars/pro-dev.yml")

    def test_ansible_host(self):  # Matrix: SAN-007
        """Pattern matches ansible_host with IP."""
        pattern = re.compile(PATTERNS["ansible_host_var"])
        assert pattern.search("ansible_host: 10.120.0.5")
        assert not pattern.search("ansible_host: hostname")
