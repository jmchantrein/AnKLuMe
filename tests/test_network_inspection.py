"""Tests for Phase 40: Network Inspection and Security Monitoring.

Covers:
- Network triage skill template (anklume-network-triage.md.j2)
- Inventory diff skill template (anklume-inventory-diff.md.j2)
- PCAP summary skill template (anklume-pcap-summary.md.j2)
- nmap-diff.sh shellcheck validation
- Network anonymization patterns in llm_sanitizer
- Heartbeat task deployment of all skills
- Behavior matrix cells NI-001 to NI-005, NI-2-001, NI-3-001
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLE_DIR = PROJECT_ROOT / "roles" / "openclaw_server"
TEMPLATES_DIR = ROLE_DIR / "templates"
SKILLS_DIR = TEMPLATES_DIR / "skills"
DEFAULTS_FILE = ROLE_DIR / "defaults" / "main.yml"
TASKS_DIR = ROLE_DIR / "tasks"
SANITIZER_DIR = PROJECT_ROOT / "roles" / "llm_sanitizer" / "templates"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


# -- Template file existence ---------------------------------------------------


class TestNetworkInspectionTemplateFiles:
    """Verify all network inspection template files exist."""

    def test_network_triage_skill_exists(self):
        assert (SKILLS_DIR / "anklume-network-triage.md.j2").is_file()

    def test_inventory_diff_skill_exists(self):
        assert (SKILLS_DIR / "anklume-inventory-diff.md.j2").is_file()

    def test_pcap_summary_skill_exists(self):
        assert (SKILLS_DIR / "anklume-pcap-summary.md.j2").is_file()

    def test_nmap_diff_script_exists(self):
        assert (SCRIPTS_DIR / "nmap-diff.sh").is_file()

    def test_nmap_diff_script_executable(self):
        script = SCRIPTS_DIR / "nmap-diff.sh"
        assert script.stat().st_mode & 0o111, "nmap-diff.sh must be executable"


# -- NI-001: Network triage skill template ------------------------------------


class TestNetworkTriageSkill:
    """Verify anklume-network-triage.md.j2 skill content.

    # Matrix: NI-001
    """

    @classmethod
    def setup_class(cls):
        cls.content = (SKILLS_DIR / "anklume-network-triage.md.j2").read_text()

    def test_has_jinja2_header(self):
        """Skill has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_uses_domain_variable(self):
        """Skill references openclaw_server_domain."""
        assert "openclaw_server_domain" in self.content

    def test_uses_incus_project_variable(self):
        """Skill references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_uses_ollama_url(self):
        """Skill references openclaw_server_ollama_url for LLM analysis."""
        assert "openclaw_server_ollama_url" in self.content

    def test_uses_baseline_dir(self):
        """Skill references openclaw_server_nmap_baseline_dir."""
        assert "openclaw_server_nmap_baseline_dir" in self.content

    def test_has_classification_levels(self):
        """Skill defines normal/suspect/critical classification."""
        assert "normal" in self.content
        assert "suspect" in self.content
        assert "critical" in self.content

    def test_has_procedure_section(self):
        """Skill has a procedure section."""
        assert "## Procedure" in self.content

    def test_has_output_section(self):
        """Skill has an output section."""
        assert "## Output" in self.content

    def test_mentions_nmap(self):
        """Skill mentions nmap as input source."""
        assert "nmap" in self.content.lower()

    def test_mentions_tshark(self):
        """Skill mentions tshark as input source."""
        assert "tshark" in self.content.lower()


# -- NI-002: Inventory diff skill template ------------------------------------


class TestInventoryDiffSkill:
    """Verify anklume-inventory-diff.md.j2 skill content.

    # Matrix: NI-002
    """

    @classmethod
    def setup_class(cls):
        cls.content = (SKILLS_DIR / "anklume-inventory-diff.md.j2").read_text()

    def test_has_jinja2_header(self):
        """Skill has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_uses_domain_variable(self):
        """Skill references openclaw_server_domain."""
        assert "openclaw_server_domain" in self.content

    def test_uses_incus_project_variable(self):
        """Skill references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_uses_baseline_dir(self):
        """Skill references openclaw_server_nmap_baseline_dir."""
        assert "openclaw_server_nmap_baseline_dir" in self.content

    def test_has_procedure_section(self):
        """Skill has a procedure section."""
        assert "## Procedure" in self.content

    def test_has_output_section(self):
        """Skill has an output section."""
        assert "## Output" in self.content

    def test_detects_new_hosts(self):
        """Skill describes detection of new hosts."""
        assert "New hosts" in self.content or "new host" in self.content.lower()

    def test_detects_missing_hosts(self):
        """Skill describes detection of missing hosts."""
        assert "Missing hosts" in self.content or "missing host" in self.content.lower()

    def test_detects_port_changes(self):
        """Skill describes detection of port changes."""
        assert "port" in self.content.lower()

    def test_detects_service_changes(self):
        """Skill describes detection of service changes."""
        assert "service" in self.content.lower()

    def test_has_nmap_command(self):
        """Skill includes nmap command for scanning."""
        assert "nmap" in self.content

    def test_has_compare_step(self):
        """Skill has a comparison step."""
        assert "Compare" in self.content


# -- NI-003: PCAP summary skill template --------------------------------------


class TestPcapSummarySkill:
    """Verify anklume-pcap-summary.md.j2 skill content.

    # Matrix: NI-003
    """

    @classmethod
    def setup_class(cls):
        cls.content = (SKILLS_DIR / "anklume-pcap-summary.md.j2").read_text()

    def test_has_jinja2_header(self):
        """Skill has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_uses_domain_variable(self):
        """Skill references openclaw_server_domain."""
        assert "openclaw_server_domain" in self.content

    def test_uses_incus_project_variable(self):
        """Skill references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_has_procedure_section(self):
        """Skill has a procedure section."""
        assert "## Procedure" in self.content

    def test_has_output_section(self):
        """Skill has an output section."""
        assert "## Output" in self.content

    def test_uses_tshark_commands(self):
        """Skill contains tshark commands for analysis."""
        assert "tshark" in self.content

    def test_has_protocol_statistics(self):
        """Skill extracts protocol statistics."""
        assert "protocol" in self.content.lower()

    def test_has_conversation_summary(self):
        """Skill extracts conversation summaries."""
        assert "conv" in self.content.lower() or "conversation" in self.content.lower()

    def test_has_dns_analysis(self):
        """Skill analyzes DNS queries."""
        assert "dns" in self.content.lower()

    def test_has_anomaly_detection(self):
        """Skill flags anomalous traffic."""
        assert "anomal" in self.content.lower()


# -- NI-004: nmap-diff.sh shellcheck validation --------------------------------


class TestNmapDiffShellcheck:
    """Verify nmap-diff.sh passes shellcheck.

    # Matrix: NI-004
    """

    @pytest.mark.skipif(
        shutil.which("shellcheck") is None,
        reason="shellcheck not installed",
    )
    def test_shellcheck_passes(self):
        """nmap-diff.sh passes shellcheck at warning severity."""
        result = subprocess.run(
            ["shellcheck", "--severity=warning", str(SCRIPTS_DIR / "nmap-diff.sh")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"shellcheck errors:\n{result.stdout}"

    def test_has_bash_shebang(self):
        """Script starts with bash shebang."""
        content = (SCRIPTS_DIR / "nmap-diff.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_uses_set_euo_pipefail(self):
        """Script enables strict mode."""
        content = (SCRIPTS_DIR / "nmap-diff.sh").read_text()
        assert "set -euo pipefail" in content

    def test_has_usage_function(self):
        """Script has a usage/help function."""
        content = (SCRIPTS_DIR / "nmap-diff.sh").read_text()
        assert "usage()" in content or "usage ()" in content

    def test_under_200_lines(self):
        """Script stays under 200 lines (KISS principle)."""
        content = (SCRIPTS_DIR / "nmap-diff.sh").read_text()
        line_count = len(content.splitlines())
        assert line_count <= 200, f"nmap-diff.sh has {line_count} lines (max 200)"


# -- NI-005: Network anonymization patterns ------------------------------------


class TestNetworkAnonymizationPatterns:
    """Verify network-specific patterns in llm_sanitizer patterns.yml.j2.

    # Matrix: NI-005
    """

    @classmethod
    def setup_class(cls):
        cls.content = (SANITIZER_DIR / "patterns.yml.j2").read_text()

    def test_has_network_identifiers_category(self):
        """Patterns file has a network_identifiers category."""
        assert "network_identifiers:" in self.content

    def test_has_mac_address_pattern(self):
        """Patterns include MAC address detection (colon-separated)."""
        assert "mac_address" in self.content

    def test_mac_pattern_matches_valid_mac(self):
        """MAC address regex matches standard format."""
        # Extract the pattern from the template
        match = re.search(
            r"name: mac_address\n.*\n\s+pattern: '([^']+)'",
            self.content,
        )
        assert match, "mac_address pattern not found"
        pattern = match.group(1)
        assert re.search(pattern, "aa:bb:cc:dd:ee:ff")
        assert re.search(pattern, "00:1A:2B:3C:4D:5E")

    def test_has_linux_interface_pattern(self):
        """Patterns include Linux interface name detection."""
        assert "linux_interface" in self.content

    def test_interface_pattern_matches_common_names(self):
        """Interface regex matches eth0, veth, enp, etc."""
        match = re.search(
            r"name: linux_interface\n.*\n\s+pattern: '([^']+)'",
            self.content,
        )
        assert match, "linux_interface pattern not found"
        pattern = match.group(1)
        assert re.search(pattern, "eth0")
        assert re.search(pattern, "veth123abc")
        assert re.search(pattern, "enp5s0")

    def test_has_arp_entry_pattern(self):
        """Patterns include ARP table entry detection."""
        assert "arp_entry" in self.content

    def test_has_nmap_host_report_pattern(self):
        """Patterns include nmap scan report header detection."""
        assert "nmap_host_report" in self.content

    def test_has_mac_address_dash_pattern(self):
        """Patterns include MAC address detection (dash-separated)."""
        assert "mac_address_dash" in self.content


# -- NI-2-001: Heartbeat tasks deploy all skills ------------------------------


class TestHeartbeatDeploysAllSkills:
    """Verify heartbeat.yml deploys all 5 skill templates.

    # Matrix: NI-2-001
    """

    @classmethod
    def setup_class(cls):
        cls.content = (TASKS_DIR / "heartbeat.yml").read_text()

    def test_deploys_health_skill(self):
        """Task file deploys anklume-health skill."""
        assert "anklume-health.md.j2" in self.content

    def test_deploys_network_diff_skill(self):
        """Task file deploys anklume-network-diff skill."""
        assert "anklume-network-diff.md.j2" in self.content

    def test_deploys_network_triage_skill(self):
        """Task file deploys anklume-network-triage skill."""
        assert "anklume-network-triage.md.j2" in self.content

    def test_deploys_inventory_diff_skill(self):
        """Task file deploys anklume-inventory-diff skill."""
        assert "anklume-inventory-diff.md.j2" in self.content

    def test_deploys_pcap_summary_skill(self):
        """Task file deploys anklume-pcap-summary skill."""
        assert "anklume-pcap-summary.md.j2" in self.content

    def test_creates_baseline_directory(self):
        """Task file creates nmap baseline directory."""
        assert "nmap_baseline_dir" in self.content

    def test_uses_fqcn(self):
        """Task file uses FQCN for all modules."""
        assert "ansible.builtin.template" in self.content
        assert "ansible.builtin.file" in self.content

    def test_task_names_follow_convention(self):
        """Task names follow the RoleName | Description convention."""
        for line in self.content.splitlines():
            if "name:" in line and "OpenclawServer" in line:
                assert "OpenclawServer |" in line


# -- NI-3-001: Network inspection + heartbeat + cron integration ---------------


class TestNetworkScanCronIntegration:
    """Verify CRON.md.j2 includes network scan when enabled.

    # Matrix: NI-3-001
    """

    @classmethod
    def setup_class(cls):
        cls.content = (TEMPLATES_DIR / "CRON.md.j2").read_text()

    def test_cron_has_network_scan_conditional(self):
        """CRON.md.j2 has conditional network scan section."""
        assert "openclaw_server_network_scan_enabled" in self.content

    def test_cron_references_nmap_diff(self):
        """CRON.md.j2 references nmap-diff.sh when scan enabled."""
        assert "nmap-diff" in self.content.lower() or "nmap_diff" in self.content

    def test_cron_references_inventory_diff_skill(self):
        """CRON.md.j2 references inventory diff skill."""
        assert "inventory-diff" in self.content.lower()

    def test_cron_references_baseline_dir(self):
        """CRON.md.j2 references nmap baseline directory."""
        assert "openclaw_server_nmap_baseline_dir" in self.content

    def test_cron_registers_network_scan(self):
        """CRON.md.j2 registers network-scan cron job."""
        assert "network-scan" in self.content


# -- Default variables ---------------------------------------------------------


class TestNetworkInspectionDefaults:
    """Verify network inspection defaults in openclaw_server defaults/main.yml.

    # Matrix: NI-001 (defaults complement)
    """

    @classmethod
    def setup_class(cls):
        cls.content = DEFAULTS_FILE.read_text()

    def test_network_scan_enabled_default(self):
        """Default network scan is disabled."""
        assert "openclaw_server_network_scan_enabled: false" in self.content

    def test_network_scan_interval_default(self):
        """Default network scan interval is 3600 seconds."""
        assert "openclaw_server_network_scan_interval: 3600" in self.content

    def test_nmap_baseline_dir_default(self):
        """Default nmap baseline directory is set."""
        assert 'openclaw_server_nmap_baseline_dir: "/var/lib/openclaw/baselines"' in self.content

    def test_all_network_vars_prefixed(self):
        """All network inspection variables use the role prefix."""
        for line in self.content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped or stripped == "---":
                continue
            if ":" in stripped:
                var_name = stripped.split(":")[0].strip()
                if (
                    var_name
                    and not var_name.startswith("openclaw_server_")
                    and var_name[0].isalpha()
                ):
                    msg = f"Variable {var_name!r} missing role prefix"
                    raise AssertionError(msg)


# -- Documentation existence --------------------------------------------------


class TestNetworkInspectionDocs:
    """Verify documentation file exists."""

    def test_network_inspection_doc_exists(self):
        """docs/network-inspection.md exists."""
        assert (PROJECT_ROOT / "docs" / "network-inspection.md").is_file()

    def test_claude_md_references_doc(self):
        """CLAUDE.md includes network-inspection.md in context files."""
        content = (PROJECT_ROOT / "CLAUDE.md").read_text()
        assert "network-inspection.md" in content

    def test_spec_operations_references_phase_40(self):
        """SPEC-operations.md mentions network inspection."""
        content = (PROJECT_ROOT / "docs" / "SPEC-operations.md").read_text()
        assert "network inspection" in content.lower() or "Phase 40" in content
