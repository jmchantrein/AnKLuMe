Feature: Live ISO — real execution tests
  These tests EXECUTE start.sh functions and doctor-checks.sh
  via scripts/test-start.sh. Every test runs real code and
  checks actual output and exit codes. No pattern-matching on
  source code — only runtime behavior.

  Background:
    Given "bash" is available

  # ══════════════════════════════════════════════════════════════
  # A. detect_data_disks — real execution with host disks
  # ══════════════════════════════════════════════════════════════

  @gate.start_exec
  Scenario: detect_data_disks with no qualifying disk exits non-zero
    When I run "bash scripts/test-start.sh detect-no-disk" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # B. select_disk — guard against empty disk list
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: select_disk with no disks shows clear error not [1-0]
    When I run "bash scripts/test-start.sh select-disk-empty" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # C. choose_backend — no-terminal fallback
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: choose_backend defaults to dir when no terminal
    When I run "bash scripts/test-start.sh choose-backend-no-tty" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # D. Disk size minimum — 100 GB enforced in runtime
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: disk size filter rejects < 100 GB and accepts >= 100 GB
    When I run "bash scripts/test-start.sh disk-size-filter" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # E. initialize_incus — output cleanliness
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: initialize_incus failure uses err not warn
    When I run "bash scripts/test-start.sh init-no-warn" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # F. doctor-checks.sh — incus reachability with retry
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: doctor check_incus_running has retry before failing
    When I run "bash scripts/test-start.sh doctor-retry" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @requires.start_exec
  Scenario: doctor check_incus_running succeeds on running host
    Given "incus" is available
    And Incus daemon is available
    When I run "bash scripts/test-start.sh doctor-reachable" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # G. bash_profile — KDE auto-start is guarded
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: bash_profile KDE auto-start is guarded by ANKLUME_DE check
    When I run "bash scripts/test-start.sh bash-profile-no-auto" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @requires.start_exec
  Scenario: no display manager enabled in ISO build
    When I run "bash scripts/test-start.sh no-display-manager" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # H. SDDM purged after plasma-desktop install (terminal-first)
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: build-image.sh purges sddm and masks display managers
    When I run "bash scripts/test-start.sh sddm-purged" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # I. Start service — kernel cmdline condition, not sddm path
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: start service uses kernel cmdline condition
    When I run "bash scripts/test-start.sh start-condition" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # J. Storage creation — errors propagated, not swallowed
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: configure_incus_storage propagates errors via die
    When I run "bash scripts/test-start.sh storage-error-propagation" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @requires.start_exec
  Scenario: configure_incus_storage is idempotent for existing pool
    When I run "bash scripts/test-start.sh storage-idempotent" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # K. --yes mode skips LUKS (no default password)
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: --yes mode skips LUKS encryption
    When I run "bash scripts/test-start.sh yes-skips-luks" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # L. Pool detection — second boot safety
  # ══════════════════════════════════════════════════════════════

  @requires.start_exec
  Scenario: scan_all_disks_for_pool scans disks via detect_existing_pool
    When I run "bash scripts/test-start.sh detect-scans-all-disks" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @requires.start_exec
  Scenario: detection runs before choose_backend in main
    When I run "bash scripts/test-start.sh detect-before-backend" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @requires.start_exec
  Scenario: ZFS pool enables deduplication
    When I run "bash scripts/test-start.sh zfs-dedup-enabled" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @requires.start_exec
  Scenario: detect_existing_pool handles all filesystem signatures
    When I run "bash scripts/test-start.sh detect-signatures" and it may fail
    Then exit code is 0
    And output contains "PASS"
