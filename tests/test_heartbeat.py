"""Tests for Phase 38: OpenClaw Heartbeat Monitoring.

Covers:
- HEARTBEAT.md.j2 template rendering
- CRON.md.j2 template rendering
- Skill template rendering (anklume-health, anklume-network-diff)
- Default variables for heartbeat config
- Heartbeat task file structure
- Behavior matrix cells HB-001 to HB-005
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROLE_DIR = PROJECT_ROOT / "roles" / "openclaw_server"
TEMPLATES_DIR = ROLE_DIR / "templates"
DEFAULTS_FILE = ROLE_DIR / "defaults" / "main.yml"
TASKS_DIR = ROLE_DIR / "tasks"


# -- Template file existence -------------------------------------------------


class TestHeartbeatTemplateFiles:
    """Verify all heartbeat template files exist."""

    def test_heartbeat_template_exists(self):
        assert (TEMPLATES_DIR / "HEARTBEAT.md.j2").is_file()

    def test_cron_template_exists(self):
        assert (TEMPLATES_DIR / "CRON.md.j2").is_file()

    def test_health_skill_exists(self):
        assert (TEMPLATES_DIR / "skills" / "anklume-health.md.j2").is_file()

    def test_network_diff_skill_exists(self):
        assert (TEMPLATES_DIR / "skills" / "anklume-network-diff.md.j2").is_file()

    def test_heartbeat_tasks_file_exists(self):
        assert (TASKS_DIR / "heartbeat.yml").is_file()


# -- HB-001: HEARTBEAT.md.j2 template content --------------------------------


class TestHeartbeatTemplate:
    """Verify HEARTBEAT.md.j2 contains expected Jinja2 variables and sections.

    # Matrix: HB-001
    """

    @classmethod
    def setup_class(cls):
        cls.content = (TEMPLATES_DIR / "HEARTBEAT.md.j2").read_text()

    def test_has_jinja2_header(self):
        """Template has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_uses_domain_variable(self):
        """Template references openclaw_server_domain."""
        assert "openclaw_server_domain" in self.content

    def test_uses_incus_project_variable(self):
        """Template references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_uses_disk_warn_threshold(self):
        """Template references disk warning threshold."""
        assert "openclaw_server_disk_warn_pct" in self.content

    def test_uses_disk_crit_threshold(self):
        """Template references disk critical threshold."""
        assert "openclaw_server_disk_crit_pct" in self.content

    def test_uses_heartbeat_interval(self):
        """Template references heartbeat interval."""
        assert "openclaw_server_heartbeat_interval" in self.content

    def test_has_container_status_section(self):
        """Template has a container status check section."""
        assert "Container status check" in self.content

    def test_has_disk_monitoring_section(self):
        """Template has a disk space monitoring section."""
        assert "Disk space monitoring" in self.content

    def test_has_service_health_section(self):
        """Template has a service health check section."""
        assert "Service health check" in self.content

    def test_has_network_scan_section(self):
        """Template has a network scan diff section."""
        assert "Network scan diff" in self.content

    def test_uses_incus_list_command(self):
        """Template contains incus list with project flag."""
        assert "incus list --project" in self.content

    def test_uses_agent_name(self):
        """Template uses openclaw_server_agent_name."""
        assert "openclaw_server_agent_name" in self.content


# -- HB-002: CRON.md.j2 template content -------------------------------------


class TestCronTemplate:
    """Verify CRON.md.j2 contains expected Jinja2 variables and sections.

    # Matrix: HB-002
    """

    @classmethod
    def setup_class(cls):
        cls.content = (TEMPLATES_DIR / "CRON.md.j2").read_text()

    def test_has_jinja2_header(self):
        """Template has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_uses_daily_hour(self):
        """Template references cron daily hour."""
        assert "openclaw_server_cron_daily_hour" in self.content

    def test_uses_daily_minute(self):
        """Template references cron daily minute."""
        assert "openclaw_server_cron_daily_minute" in self.content

    def test_uses_domain_variable(self):
        """Template references openclaw_server_domain."""
        assert "openclaw_server_domain" in self.content

    def test_uses_incus_project(self):
        """Template references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_has_daily_summary_section(self):
        """Template has a daily health summary section."""
        assert "Daily health summary" in self.content

    def test_has_snapshot_section(self):
        """Template has a pre-maintenance snapshot section."""
        assert "snapshot" in self.content.lower()

    def test_has_log_rotation_section(self):
        """Template has a log rotation alerts section."""
        assert "Log rotation" in self.content

    def test_has_cron_registration(self):
        """Template has cron registration commands."""
        assert "openclaw cron add" in self.content


# -- HB-003: Skill templates -------------------------------------------------


class TestHealthSkillTemplate:
    """Verify anklume-health.md.j2 skill content.

    # Matrix: HB-003
    """

    @classmethod
    def setup_class(cls):
        cls.content = (
            TEMPLATES_DIR / "skills" / "anklume-health.md.j2"
        ).read_text()

    def test_has_jinja2_header(self):
        """Skill has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_has_project_flag(self):
        """Skill contains --project flag for domain scoping."""
        assert "--project" in self.content

    def test_uses_incus_project(self):
        """Skill references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_uses_disk_thresholds(self):
        """Skill references disk threshold variables."""
        assert "openclaw_server_disk_warn_pct" in self.content
        assert "openclaw_server_disk_crit_pct" in self.content

    def test_has_procedure_section(self):
        """Skill has a procedure section."""
        assert "## Procedure" in self.content

    def test_has_output_section(self):
        """Skill has an output section."""
        assert "## Output" in self.content

    def test_has_list_containers_step(self):
        """Skill has a container listing step."""
        assert "incus list" in self.content

    def test_has_disk_check_step(self):
        """Skill has a disk check step using df."""
        assert "df" in self.content

    def test_has_systemctl_check(self):
        """Skill checks systemd services."""
        assert "systemctl is-active" in self.content


class TestNetworkDiffSkillTemplate:
    """Verify anklume-network-diff.md.j2 skill content.

    # Matrix: HB-003
    """

    @classmethod
    def setup_class(cls):
        cls.content = (
            TEMPLATES_DIR / "skills" / "anklume-network-diff.md.j2"
        ).read_text()

    def test_has_jinja2_header(self):
        """Skill has the ADR-036 header comment."""
        assert "deployed by openclaw_server role (ADR-036)" in self.content

    def test_has_project_flag(self):
        """Skill contains --project flag for domain scoping."""
        assert "--project" in self.content

    def test_uses_incus_project(self):
        """Skill references openclaw_server_incus_project."""
        assert "openclaw_server_incus_project" in self.content

    def test_has_baseline_concept(self):
        """Skill describes baseline comparison."""
        assert "baseline" in self.content.lower()

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

    def test_has_compare_step(self):
        """Skill has a comparison step."""
        assert "Compare" in self.content


# -- HB-004: Default variables ------------------------------------------------


class TestHeartbeatDefaults:
    """Verify heartbeat defaults in openclaw_server defaults/main.yml.

    # Matrix: HB-004
    """

    @classmethod
    def setup_class(cls):
        cls.content = DEFAULTS_FILE.read_text()

    def test_heartbeat_interval_default(self):
        """Default heartbeat interval is 300 seconds."""
        assert "openclaw_server_heartbeat_interval: 300" in self.content

    def test_disk_warn_default(self):
        """Default disk warning threshold is 80%."""
        assert "openclaw_server_disk_warn_pct: 80" in self.content

    def test_disk_crit_default(self):
        """Default disk critical threshold is 95%."""
        assert "openclaw_server_disk_crit_pct: 95" in self.content

    def test_cron_daily_hour_default(self):
        """Default cron daily hour is 8."""
        assert "openclaw_server_cron_daily_hour: 8" in self.content

    def test_cron_daily_minute_default(self):
        """Default cron daily minute is 0."""
        assert "openclaw_server_cron_daily_minute: 0" in self.content

    def test_domain_default(self):
        """Domain variable exists with empty default."""
        assert 'openclaw_server_domain: ""' in self.content

    def test_incus_project_default(self):
        """Incus project variable exists with default."""
        assert 'openclaw_server_incus_project: "default"' in self.content

    def test_all_heartbeat_vars_prefixed(self):
        """All heartbeat variables use the role prefix."""
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


# -- HB-005: Heartbeat task file structure ------------------------------------


class TestHeartbeatTasks:
    """Verify heartbeat.yml task file deploys all templates.

    # Matrix: HB-005
    """

    @classmethod
    def setup_class(cls):
        cls.content = (TASKS_DIR / "heartbeat.yml").read_text()

    def test_deploys_heartbeat_template(self):
        """Task file deploys HEARTBEAT.md.j2."""
        assert "HEARTBEAT.md.j2" in self.content

    def test_deploys_cron_template(self):
        """Task file deploys CRON.md.j2."""
        assert "CRON.md.j2" in self.content

    def test_deploys_health_skill(self):
        """Task file deploys anklume-health skill."""
        assert "anklume-health.md.j2" in self.content

    def test_deploys_network_diff_skill(self):
        """Task file deploys anklume-network-diff skill."""
        assert "anklume-network-diff.md.j2" in self.content

    def test_creates_skills_directory(self):
        """Task file creates the skills directory."""
        assert "skills" in self.content
        assert "directory" in self.content

    def test_uses_fqcn(self):
        """Task file uses FQCN for all modules."""
        assert "ansible.builtin.template" in self.content
        assert "ansible.builtin.file" in self.content

    def test_task_names_follow_convention(self):
        """Task names follow the RoleName | Description convention."""
        for line in self.content.splitlines():
            if "name:" in line and "OpenclawServer" in line:
                assert "OpenclawServer |" in line


class TestMainTasksIntegration:
    """Verify main.yml includes heartbeat tasks."""

    @classmethod
    def setup_class(cls):
        cls.content = (TASKS_DIR / "main.yml").read_text()

    def test_includes_heartbeat(self):
        """main.yml includes heartbeat.yml."""
        assert "heartbeat.yml" in self.content

    def test_include_uses_fqcn(self):
        """Include uses ansible.builtin.include_tasks."""
        assert "ansible.builtin.include_tasks" in self.content

    def test_main_under_200_lines(self):
        """main.yml stays under 200 lines (KISS principle)."""
        line_count = len(self.content.splitlines())
        assert line_count <= 200, f"main.yml has {line_count} lines (max 200)"
