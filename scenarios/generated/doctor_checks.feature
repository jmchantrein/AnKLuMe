# Matrix: DR-001 to DR-003
Feature: Doctor — infrastructure health checker

  Scenario: doctor.sh is valid bash with shellcheck
    # Matrix: DR-001
    Given "shellcheck" is available
    When I run "shellcheck -S warning scripts/doctor.sh scripts/doctor-network.sh scripts/doctor-checks.sh"
    Then exit code is 0

  Scenario: doctor.sh supports help flag
    # Matrix: DR-002
    Given "bash" is available
    When I run "bash scripts/doctor.sh --help"
    Then exit code is 0
    And output contains "Usage"

  Scenario: doctor-network.sh defines all check functions
    # Matrix: DR-003
    Given "python3" is available
    When I run "python3 -c 'content=open("scripts/doctor-network.sh").read(); checks=["check_orphan_veths","check_stale_fdb_entries","check_stale_routes","check_nat_rules","check_dns_dhcp_chains","check_bridge_health"]; missing=[c for c in checks if c+"()" not in content]; assert not missing, "Missing: %s" % missing; print("all checks defined")'"
    Then exit code is 0
    And output contains "all checks defined"
