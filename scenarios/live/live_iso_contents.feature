Feature: Live ISO — squashfs content verification (L2 tests)
  These tests mount the actual ISO's squashfs filesystem and verify
  that binaries, modules, configurations, and user setup are correct.
  Unlike structural tests (grep on source), these verify the RESULT
  of the build, not the build script's contents.

  Requires: root, ISO file at images/anklume-debian-kde.iso

  Background:
    Given "bash" is available

  # ══════════════════════════════════════════════════════════════
  # A. Display manager — SDDM must be absent (terminal-first)
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: SDDM binary absent from squashfs
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso sddm-absent" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # B. ZFS — kernel module and userspace tools present
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: ZFS kernel module present in squashfs
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso zfs-module" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: ZFS userspace tools present in squashfs
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso zfs-tools" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # C. BTRFS tools present
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: BTRFS tools present in squashfs
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso btrfs-tools" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # D. Incus — binary and service enabled
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Incus binary present and service enabled
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso incus-binary" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Incus service enabled in squashfs
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso incus-service-enabled" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # E. User setup — groups, sudo, password
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Live user in incus-admin group
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso user-groups" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Live user in adm group for journalctl
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso user-adm-group" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Passwordless sudo for live user
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso sudo-nopasswd" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # F. AppArmor — parser present, teardown service configured
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: apparmor_parser binary present
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso apparmor-parser" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: AppArmor teardown service runs before Incus
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso aa-teardown-service" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # G. Framework scripts present
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: start.sh and doctor-checks.sh present
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso start-script" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: anklume CLI present
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso anklume-cli" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # H. Boot and service configuration
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Boot files present in ISO
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso boot-files" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: No display manager auto-starts
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso no-display-manager" and it may fail
    Then exit code is 0
    And output contains "PASS"

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: Serial console enabled for QEMU testing
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso serial-console" and it may fail
    Then exit code is 0
    And output contains "PASS"

  # ══════════════════════════════════════════════════════════════
  # I. Full suite — all tests at once
  # ══════════════════════════════════════════════════════════════

  @gate.iso_contents @requires.root @requires.debian_iso
  Scenario: All ISO content tests pass
    When I run "sudo bash scripts/test-iso-contents.sh images/anklume-debian-kde.iso all" and it may fail
    Then exit code is 0
    And output does not contain "FAIL"
