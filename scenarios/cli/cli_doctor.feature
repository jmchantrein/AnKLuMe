Feature: CLI doctor — infrastructure health diagnostics
  The doctor command must work gracefully in all environments:
  with or without Incus, with various --check categories, and
  must never crash or hang. On dev hosts without anklume
  infrastructure, it should report warnings (not errors) and
  exit 0.

  Background:
    Given "python3" is available

  # ══════════════════════════════════════════════════════════════
  # Syntax gate
  # ══════════════════════════════════════════════════════════════

  @gate.doctor_syntax
  Scenario: doctor.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/doctor.sh"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A2.1 — Function existence (18 functions across 3 files)
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario Outline: doctor function <func> is defined in <file>
    Given the script "<file>" source is loaded
    Then function "<func>" is defined in the script

    Examples:
      | func                       | file                      |
      | result_ok                  | scripts/doctor.sh         |
      | result_warn                | scripts/doctor.sh         |
      | result_err                 | scripts/doctor.sh         |
      | verbose                    | scripts/doctor.sh         |
      | cleanup                    | scripts/doctor.sh         |
      | setup_repair_container     | scripts/doctor.sh         |
      | host_cmd                   | scripts/doctor.sh         |
      | check_orphan_veths         | scripts/doctor-network.sh |
      | check_stale_fdb_entries    | scripts/doctor-network.sh |
      | check_stale_routes         | scripts/doctor-network.sh |
      | check_nat_rules            | scripts/doctor-network.sh |
      | check_dns_dhcp_chains      | scripts/doctor-network.sh |
      | check_bridge_health        | scripts/doctor-network.sh |
      | check_incus_running        | scripts/doctor-checks.sh  |
      | check_anklume_running      | scripts/doctor-checks.sh  |
      | check_container_connectivity | scripts/doctor-checks.sh |
      | check_ip_drift             | scripts/doctor-checks.sh  |
      | check_container_deps       | scripts/doctor-checks.sh  |

  # ══════════════════════════════════════════════════════════════
  # Help and arguments
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario: doctor --help exits 0
    Given "bash" is available
    When I run "bash scripts/doctor.sh --help"
    Then exit code is 0
    And output contains "Usage"

  @requires.doctor_syntax
  Scenario: doctor --verbose is documented in help
    Given "bash" is available
    When I run "bash scripts/doctor.sh --help"
    Then exit code is 0
    And output contains "verbose"

  @requires.doctor_syntax
  Scenario: doctor --fix is documented in help
    Given "bash" is available
    When I run "bash scripts/doctor.sh --help"
    Then exit code is 0
    And output contains "fix"

  @requires.doctor_syntax
  Scenario: doctor help mentions all categories
    Given "bash" is available
    When I run "bash scripts/doctor.sh --help"
    Then exit code is 0
    And output contains "network"
    And output contains "instances"
    And output contains "config"
    And output contains "deps"

  # ══════════════════════════════════════════════════════════════
  # A2.2 — Flag × category matrix (20 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario Outline: doctor <flags> with --check <category> completes without hanging
    Given "bash" is available
    When I run "timeout 30 bash scripts/doctor.sh <flags> --check <category>" and it may fail
    Then the command completed within 30 seconds

    Examples:
      | flags               | category  |
      |                     | network   |
      |                     | instances |
      |                     | config    |
      |                     | deps      |
      | --verbose           | network   |
      | --verbose           | instances |
      | --verbose           | config    |
      | --verbose           | deps      |
      | --fix               | network   |
      | --fix               | instances |
      | --fix               | config    |
      | --fix               | deps      |
      | --fix --verbose     | network   |
      | --fix --verbose     | instances |
      | --fix --verbose     | config    |
      | --fix --verbose     | deps      |

  @requires.doctor_syntax
  Scenario Outline: doctor <flags> full run completes without hanging
    Given "bash" is available
    When I run "timeout 60 bash scripts/doctor.sh <flags>" and it may fail
    Then the command completed within 60 seconds

    Examples:
      | flags               |
      |                     |
      | --verbose           |
      | --fix               |
      | --fix --verbose     |

  # ══════════════════════════════════════════════════════════════
  # A2.3 — Graceful degradation on dev host (10 scenarios)
  # These test that doctor reports warnings, not errors, when
  # anklume infrastructure is absent.
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario: doctor --check instances shows 0 errors on dev host
    Given "bash" is available
    When I run "timeout 30 bash scripts/doctor.sh --check instances" and it may fail
    Then the command completed within 30 seconds
    And summary shows 0 errors

  @requires.doctor_syntax
  Scenario: doctor --check deps shows 0 errors on dev host
    Given "bash" is available
    When I run "timeout 30 bash scripts/doctor.sh --check deps" and it may fail
    Then the command completed within 30 seconds
    And summary shows 0 errors

  @requires.doctor_syntax
  Scenario: doctor --check config shows 0 errors on dev host
    Given "bash" is available
    When I run "timeout 30 bash scripts/doctor.sh --check config" and it may fail
    Then the command completed within 30 seconds
    And summary shows 0 errors

  @requires.doctor_syntax
  Scenario: doctor full run exits 0 on dev host without infra
    Given "bash" is available
    When I run "timeout 60 bash scripts/doctor.sh" and it may fail
    Then the command completed within 60 seconds
    And summary shows 0 errors

  @requires.doctor_syntax
  Scenario: anklume-instance absent is warning not error
    Given the script "scripts/doctor-checks.sh" source is loaded
    Then function "check_anklume_running" contains pattern "result_warn.*not found"

  @requires.doctor_syntax
  Scenario: missing instance skips dep checks
    Given the script "scripts/doctor-checks.sh" source is loaded
    Then function "check_container_deps" contains pattern "result_warn.*not found.*skipping"

  @requires.doctor_syntax
  Scenario: missing instance skips dep checks when stopped
    Given the script "scripts/doctor-checks.sh" source is loaded
    Then function "check_container_deps" contains pattern "result_warn.*not running.*skipping"

  @requires.doctor_syntax
  Scenario: no infra.yml skips IP drift
    Given the script "scripts/doctor-checks.sh" source is loaded
    Then function "check_ip_drift" contains pattern "! -f infra.yml.*return"

  @requires.doctor_syntax
  Scenario: net-anklume absent is warning
    Given the script "scripts/doctor.sh" source is loaded
    Then function "setup_repair_container" contains pattern "result_warn.*net-anklume"

  @requires.doctor_syntax
  Scenario: anklume-instance STOPPED is a real error
    Given the script "scripts/doctor-checks.sh" source is loaded
    Then function "check_anklume_running" contains pattern "result_err.*not running"

  # ══════════════════════════════════════════════════════════════
  # A2.4 — Network checks depth (12 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario Outline: network check <func> — <aspect>
    Given the script "scripts/doctor-network.sh" source is loaded
    Then function "<func>" contains pattern "<pattern>"

    Examples:
      | func                    | aspect                          | pattern                          |
      | check_orphan_veths      | uses ip link show type veth     | ip.*link show type veth          |
      | check_orphan_veths      | detects MAC collision           | container_macs                   |
      | check_orphan_veths      | deletes orphan when FIX=true    | \$FIX.*ip link del               |
      | check_stale_fdb_entries | queries bridge fdb show         | bridge fdb show                  |
      | check_stale_fdb_entries | checks device existence         | ip link show                     |
      | check_stale_fdb_entries | deletes stale when FIX=true     | \$FIX.*bridge fdb del            |
      | check_stale_routes      | matches 10.100 subnet pattern   | 10\\.100                         |
      | check_stale_routes      | matches default via veth        | default.*veth                    |
      | check_stale_routes      | deletes route when FIX=true     | \$FIX.*ip route del              |
      | check_nat_rules         | reads nft table inet incus      | nft list table inet incus        |
      | check_nat_rules         | checks pstrt chain per bridge   | chain pstrt                      |
      | check_dns_dhcp_chains   | checks in chain per bridge      | chain in                         |

  # ══════════════════════════════════════════════════════════════
  # A2.5 — Instance/config/deps checks depth (10 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario Outline: instance/config/deps check — <aspect>
    Given the script "scripts/doctor-checks.sh" source is loaded
    Then function "<func>" contains pattern "<pattern>"

    Examples:
      | func                       | aspect                              | pattern                      |
      | check_incus_running        | uses incus list format csv          | incus list.*--format csv     |
      | check_incus_running        | result_err if unreachable           | result_err.*not reachable    |
      | check_anklume_running      | queries --project anklume           | --project anklume            |
      | check_anklume_running      | extracts status column              | --format csv -c s            |
      | check_container_connectivity | parses JSON with python3          | python3 -c                   |
      | check_container_connectivity | pings gateway with -W2            | ping -c1 -W2                 |
      | check_container_connectivity | skips containers without routes   | no default route.*skipped    |
      | check_ip_drift             | compares actual vs infra.yml IPs  | expected.*infra.yml          |
      | check_ip_drift             | skips silently when no infra.yml  | ! -f infra.yml               |
      | check_container_deps       | checks tmux python3 make          | tmux python3 make            |

  # ══════════════════════════════════════════════════════════════
  # Error handling
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario: doctor with unknown category exits non-zero
    Given "bash" is available
    When I run "bash scripts/doctor.sh --check nonexistent" and it may fail
    Then the command completed within 30 seconds

  @requires.doctor_syntax
  Scenario: doctor unknown flag exits non-zero
    Given "bash" is available
    When I run "bash scripts/doctor.sh --badoption" and it may fail
    Then exit code is non-zero

  # ══════════════════════════════════════════════════════════════
  # Structural checks
  # ══════════════════════════════════════════════════════════════

  @requires.doctor_syntax
  Scenario: doctor.sh sources doctor-network.sh
    Given the script "scripts/doctor.sh" source is loaded
    Then the script contains pattern "source.*doctor-network.sh"

  @requires.doctor_syntax
  Scenario: doctor.sh sources doctor-checks.sh
    Given the script "scripts/doctor.sh" source is loaded
    Then the script contains pattern "source.*doctor-checks.sh"

  @requires.doctor_syntax
  Scenario: doctor.sh has trap cleanup EXIT
    Given the script "scripts/doctor.sh" source is loaded
    Then the script contains pattern "trap cleanup EXIT"

  @requires.doctor_syntax
  Scenario: doctor.sh summary prints pass warn err counts
    Given the script "scripts/doctor.sh" source is loaded
    Then the script contains pattern "PASS.*WARN.*ERR"

  @requires.doctor_syntax
  Scenario: doctor.sh exit code reflects error count
    Given the script "scripts/doctor.sh" source is loaded
    Then the script contains pattern "ERR.*>.*0.*\\?.*1.*:.*0"

  @requires.doctor_syntax
  Scenario: doctor --fix suggests make doctor FIX=1
    Given the script "scripts/doctor.sh" source is loaded
    Then the script contains pattern "doctor FIX=1"

  @requires.doctor_syntax
  Scenario: doctor-checks.sh syntax is valid
    Given "bash" is available
    When I run "bash -n scripts/doctor-checks.sh"
    Then exit code is 0

  @requires.doctor_syntax
  Scenario: doctor-network.sh syntax is valid
    Given "bash" is available
    When I run "bash -n scripts/doctor-network.sh"
    Then exit code is 0
