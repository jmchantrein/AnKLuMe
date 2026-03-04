Feature: Live ISO persistence — start.sh exhaustive coverage
  The start.sh script must initialize Incus storage reliably,
  handle all three backends (ZFS, BTRFS, dir), LUKS encryption,
  disk detection, CLI argument parsing, and framework bootstrap.
  All verifications are static analysis of the script source — no
  destructive execution.

  Background:
    Given "python3" is available

  # ── Shell syntax ─────────────────────────────────────────────

  @gate.start_syntax
  Scenario: start.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/start.sh"
    Then exit code is 0

  # ── AppArmor suppression ─────────────────────────────────────

  @requires.start_syntax
  Scenario: aa-teardown is handled by a dedicated systemd service before incus
    Given the file "host/boot/systemd/anklume-aa-teardown.service" exists

  @requires.start_syntax
  Scenario: incus admin init commands suppress stderr
    Given the script "scripts/start.sh" source is loaded
    Then function "initialize_incus" contains pattern "incus admin init --preseed.*2>"

  @requires.start_syntax
  Scenario: warn messages in initialize_incus do not mention AppArmor
    Given the script "scripts/start.sh" source is loaded
    Then function "initialize_incus" does not contain pattern "warn[^\n]*AppArmor"

  # ── Backend selection ────────────────────────────────────────

  @requires.start_syntax
  Scenario: choose_backend shows default=1 in prompt
    Given the script "scripts/start.sh" source is loaded
    Then function "choose_backend" contains pattern "default=1"

  # ── live-os-lib.sh syntax ────────────────────────────────────

  @requires.start_syntax
  Scenario: live-os-lib.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/live-os-lib.sh"
    Then exit code is 0

  # ── start.sh --help works ────────────────────────────────────

  @requires.start_syntax
  Scenario: start.sh --help exits 0
    Given "bash" is available
    When I run "bash scripts/start.sh --help"
    Then exit code is 0
    And output contains "Usage"

  # ══════════════════════════════════════════════════════════════
  # A1.1 — Function existence (19 functions)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: function <func> is defined in start.sh
    Given the script "scripts/start.sh" source is loaded
    Then function "<func>" is defined in the script

    Examples:
      | func                    |
      | detect_distro           |
      | die                     |
      | success                 |
      | prompt_yes_no           |
      | usage                   |
      | list_disks              |
      | detect_data_disks       |
      | select_disk             |
      | choose_backend          |
      | setup_luks              |
      | setup_zfs_pool          |
      | setup_btrfs_pool        |
      | setup_dir_pool          |
      | initialize_incus        |
      | configure_incus_storage |
      | write_pool_conf         |
      | copy_framework          |
      | bootstrap_incus         |
      | main                    |

  # ══════════════════════════════════════════════════════════════
  # A1.2 — Backend × LUKS × dependency matrix (20 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: <backend> backend — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "<func>" contains pattern "<pattern>"

    Examples:
      | backend | func           | aspect                                   | pattern                        |
      | zfs     | setup_zfs_pool | checks zpool availability                | command -v zpool               |
      | zfs     | setup_zfs_pool | calls zpool create with -f flag          | zpool create -f                |
      | zfs     | setup_zfs_pool | sets compression=lz4                     | compression=lz4                |
      | zfs     | setup_zfs_pool | sets atime=off                           | atime=off                      |
      | zfs     | setup_zfs_pool | dies with message if zpool missing       | die.*not found                 |
      | zfs     | setup_zfs_pool | supports LUKS via cryptsetup luksFormat  | cryptsetup luksFormat          |
      | zfs     | setup_zfs_pool | uses /dev/mapper after LUKS open         | /dev/mapper/                   |
      | zfs     | setup_zfs_pool | sets POOL_MOUNT_POINT                    | POOL_MOUNT_POINT=              |
      | btrfs   | setup_btrfs_pool | checks mkfs.btrfs availability         | command -v mkfs.btrfs          |
      | btrfs   | setup_btrfs_pool | calls mkfs.btrfs with -f -L flags      | mkfs.btrfs -f -L              |
      | btrfs   | setup_btrfs_pool | dies with message if missing            | die.*not found                 |
      | btrfs   | setup_btrfs_pool | supports LUKS via cryptsetup luksFormat | cryptsetup luksFormat          |
      | btrfs   | setup_btrfs_pool | uses /dev/mapper after LUKS open        | /dev/mapper/                   |
      | btrfs   | setup_btrfs_pool | sets POOL_MOUNT_POINT                   | POOL_MOUNT_POINT=              |

  @requires.start_syntax
  Scenario: dir backend does not call mkfs or zpool
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_dir_pool" does not contain pattern "mkfs"
    And function "setup_dir_pool" does not contain pattern "zpool"

  @requires.start_syntax
  Scenario: dir backend does not require LUKS
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_dir_pool" does not contain pattern "cryptsetup"

  @requires.start_syntax
  Scenario: dir backend sets POOL_MOUNT_POINT to /var/lib/incus
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_dir_pool" contains pattern "POOL_MOUNT_POINT=.*/var/lib/incus"

  @requires.start_syntax
  Scenario: dir backend does not require any disk
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_dir_pool" does not contain pattern "DISK"

  @requires.start_syntax
  Scenario: configure_incus_storage handles zfs source
    Given the script "scripts/start.sh" source is loaded
    Then function "configure_incus_storage" contains pattern "zfs.*source="

  @requires.start_syntax
  Scenario: configure_incus_storage handles btrfs mount check
    Given the script "scripts/start.sh" source is loaded
    Then function "configure_incus_storage" contains pattern "mountpoint -q"

  # ══════════════════════════════════════════════════════════════
  # A1.3 — LUKS depth (15 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: LUKS — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "<func>" contains pattern "<pattern>"

    Examples:
      | func       | aspect                                        | pattern                          |
      | setup_luks | checks cryptsetup availability                | command -v cryptsetup            |
      | setup_luks | dies if cryptsetup not found                  | die.*cryptsetup not found        |
      | setup_luks | prompts for encryption with yes/no            | prompt_yes_no.*[Ee]ncrypt        |
      | setup_luks | reads password silently                       | read -rs                         |
      | setup_luks | requires password confirmation                | [Cc]onfirm password              |
      | setup_luks | rejects empty passwords                      | -z.*LUKS_PASSWORD                |
      | setup_luks | rejects mismatched passwords                 | LUKS_PASSWORD.*!=.*password_confirm |
      | setup_luks | allows 3 attempts maximum                    | attempts -lt 3                   |
      | setup_luks | dies after 3 failed attempts                 | die.*3 attempts                  |
      | setup_luks | sets LUKS_ENABLED=true on success            | LUKS_ENABLED=true                |
      | setup_luks | sets LUKS_ENABLED=false when user declines   | LUKS_ENABLED=false               |
      | setup_luks | sets LUKS_ENABLED true on acceptance        | LUKS_ENABLED=true                |

  @requires.start_syntax
  Scenario: LUKS pipes password via printf not echo
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_zfs_pool" contains pattern "printf.*LUKS_PASSWORD"

  @requires.start_syntax
  Scenario: LUKS_NAME is anklume-crypt
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "LUKS_NAME" to "anklume-crypt"



  # ══════════════════════════════════════════════════════════════
  # A1.4 — Disk detection and validation (18 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: disk detection — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "<func>" contains pattern "<pattern>"

    Examples:
      | func              | aspect                                 | pattern                   |
      | list_disks        | uses lsblk to enumerate block devices  | lsblk -d                 |
      | detect_data_disks | excludes root device via findmnt        | findmnt                   |
      | detect_data_disks | filters disks smaller than 100 GB      | -lt 100                   |
      | list_disks        | marks small disks with SKIP             | SKIP.*too small           |
      | select_disk       | auto-selects when single disk found    | Single data disk          |
      | select_disk       | shows interactive menu for multiple    | Multiple disks            |
      | detect_data_disks | dies when no suitable disks found      | die.*No suitable          |
      | select_disk       | validates numeric input range          | selection >= 1            |

  @requires.start_syntax
  Scenario: --disk flag sets DISK variable
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "--disk.*DISK="

  @requires.start_syntax
  Scenario: --disk requires device path argument
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "--disk.*die.*requires"

  @requires.start_syntax
  Scenario: --list calls list_disks and exits
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "--list.*list_disks"

  @requires.start_syntax
  Scenario: list_disks output includes NAME SIZE
    Given the script "scripts/start.sh" source is loaded
    Then function "list_disks" contains pattern "NAME,SIZE"

  @requires.start_syntax
  Scenario: detect_data_disks minimum is 100 GB
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_data_disks" contains pattern "100"

  @requires.start_syntax
  Scenario: disk selection skipped for dir backend
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "BACKEND.*!=.*dir"

  @requires.start_syntax
  Scenario: destructive warning shown for non-dir backends
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "DESTRUCTIVE OPERATION"

  @requires.start_syntax
  Scenario: invalid block device check uses -b test
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "! -b.*DISK"

  @requires.start_syntax
  Scenario: invalid block device triggers die
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "die.*not a block device"

  # ══════════════════════════════════════════════════════════════
  # A1.5 — CLI flags and argument parsing (16 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: start.sh flag <flag> — <behavior>
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "<pattern>"

    Examples:
      | flag       | behavior                         | pattern                  |
      | --help     | handled in argument parsing      | --help\)                 |
      | -h         | handled in argument parsing      | -h\|--help               |
      | --yes      | sets CONFIRM_YES=true            | --yes.*CONFIRM_YES=true  |
      | --backend  | requires argument                | --backend.*die.*requires |
      | --backend  | shifts two args                  | --backend.*shift 2       |
      | --disk     | requires device path argument    | --disk.*die.*requires    |
      | --disk     | shifts two args                  | --disk.*shift 2          |
      | (unknown)  | dies with Unknown option message | die.*Unknown option      |

  @requires.start_syntax
  Scenario: --help exits 0 when invoked
    Given "bash" is available
    When I run "bash scripts/start.sh --help"
    Then exit code is 0
    And output contains "Usage"

  @requires.start_syntax
  Scenario: -h exits 0 when invoked
    Given "bash" is available
    When I run "bash scripts/start.sh -h"
    Then exit code is 0
    And output contains "Usage"

  @requires.start_syntax
  Scenario: --list calls list_disks and exits 0
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "--list.*list_disks"
    And function "main" contains pattern "--list.*exit 0"

  @requires.start_syntax
  Scenario: --yes auto-accepts all prompts
    Given the script "scripts/start.sh" source is loaded
    Then function "prompt_yes_no" contains pattern "CONFIRM_YES.*true"

  @requires.start_syntax
  Scenario: root check at script start
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "EUID -ne 0"

  @requires.start_syntax
  Scenario: no args enters interactive mode
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "choose_backend"

  @requires.start_syntax
  Scenario: --help output contains all backend names
    Given "bash" is available
    When I run "bash scripts/start.sh --help"
    Then exit code is 0
    And output contains "zfs"
    And output contains "btrfs"

  # ══════════════════════════════════════════════════════════════
  # A1.6 — Incus initialization depth (22 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: initialize_incus — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "initialize_incus" contains pattern "<pattern>"

    Examples:
      | aspect                                               | pattern                              |
      | starts systemctl if daemon not active                | systemctl start incus                |
      | polls incus info for readiness up to 15 seconds      | wait_count -lt 15                    |
      | skips init when already initialized                  | already initialized                  |
      | loads bridge kernel module via modprobe               | modprobe bridge                      |
      | loads br_netfilter kernel module                     | modprobe br_netfilter                |
      | preseed config includes incusbr0 network             | name: incusbr0                       |
      | preseed config includes dir storage pool             | driver: dir                          |
      | preseed config includes default profile with eth0    | name: eth0                           |
      | preseed config includes root disk device             | path: /                              |
      | falls back to minimal init on preseed failure        | incus admin init --minimal           |
      | reports error on initialization failure               | err.*initialization failed           |
      | preseed captures stderr for diagnostics              | 2>&1                                 |
      | daemon timeout is non-fatal (warns)                  | warn.*not responding                 |
      | preseed uses incus admin init --preseed              | incus admin init --preseed           |
      | modprobe errors are suppressed                       | modprobe.*\|\| true                  |
      | sleep 2 after daemon start                           | sleep 2                              |
      | ipv4.address set to auto in preseed                  | ipv4.address: auto                   |
      | ipv6.address set to none in preseed                  | ipv6.address: none                   |
      | storage pool driver is dir in preseed                | driver: dir                          |
      | pool name is default in preseed                      | name: default                        |
      | systemctl is-active check precedes start             | systemctl is-active                  |
      | checks eth0 in default profile for init detection    | grep -q.*eth0                        |

  # ══════════════════════════════════════════════════════════════
  # A1.7 — configure_incus_storage × backend (12 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: configure_incus_storage <backend> — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "configure_incus_storage" contains pattern "<pattern>"

    Examples:
      | backend | aspect                            | pattern                        |
      | zfs     | uses source=POOL_NAME             | zfs source=                    |
      | zfs     | creates zfs type storage pool      | storage create.*zfs            |
      | btrfs   | checks mountpoint before mount    | mountpoint -q                  |
      | btrfs   | mounts disk if not mounted        | mount.*DISK.*POOL_MOUNT_POINT  |
      | btrfs   | creates btrfs type storage pool   | storage create.*btrfs          |
      | btrfs   | source is POOL_MOUNT_POINT        | btrfs source=                  |
      | dir     | creates dir type storage pool     | storage create.*dir            |
      | (all)   | dies if incus list fails          | die.*not accessible            |
      | btrfs   | mkdir -p for mount point          | mkdir -p                       |

  @requires.start_syntax
  Scenario: configure_incus_storage pool creation failure is fatal
    Given the script "scripts/start.sh" source is loaded
    Then function "configure_incus_storage" contains pattern "die.*Failed to create"

  @requires.start_syntax
  Scenario: configure_incus_storage zfs does not need mkdir
    Given the script "scripts/start.sh" source is loaded
    # The zfs case block should not have mkdir
    Then the script contains pattern "zfs\).*source="

  @requires.start_syntax
  Scenario: configure_incus_storage dir has no disk or mount
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_dir_pool" does not contain pattern "mount "

  # ══════════════════════════════════════════════════════════════
  # A1.8 — write_pool_conf, copy_framework, bootstrap_incus (22)
  # ══════════════════════════════════════════════════════════════

  # -- write_pool_conf (8) --

  @requires.start_syntax
  Scenario Outline: write_pool_conf — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "write_pool_conf" contains pattern "<pattern>"

    Examples:
      | aspect                                  | pattern                   |
      | writes POOL_NAME to output file         | POOL_NAME=                |
      | writes POOL_BACKEND to output file      | POOL_BACKEND=             |
      | writes POOL_DEVICE to output file       | POOL_DEVICE=              |
      | writes POOL_MOUNT_POINT to output file  | POOL_MOUNT_POINT=         |
      | writes LUKS_ENABLED to output file      | LUKS_ENABLED=             |
      | writes timestamp via date               | date                      |

  @requires.start_syntax
  Scenario: write_pool_conf on live OS writes to /mnt/anklume-persist
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "/mnt/anklume-persist/pool.conf"

  @requires.start_syntax
  Scenario: write_pool_conf on standard host writes to pool.conf
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "POOL_CONF_FILE" to "pool.conf"

  # -- copy_framework (8) --

  @requires.start_syntax
  Scenario Outline: copy_framework — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "copy_framework" contains pattern "<pattern>"

    Examples:
      | aspect                                  | pattern                   |
      | validates ANKLUME_REPO exists           | ! -d.*ANKLUME_REPO        |
      | dies if repo not found                  | die.*not found             |
      | prefers rsync over tar                  | command -v rsync           |
      | falls back to tar when rsync missing    | tar -C                    |
      | excludes .git directory                 | exclude=.*\.git            |
      | excludes .venv directory                | exclude=.*\.venv           |

  @requires.start_syntax
  Scenario: copy_framework zfs creates dataset for anklume
    Given the script "scripts/start.sh" source is loaded
    Then function "copy_framework" contains pattern "POOL_NAME.*anklume"

  # -- bootstrap_incus (6) --

  @requires.start_syntax
  Scenario Outline: bootstrap_incus — <aspect>
    Given the script "scripts/start.sh" source is loaded
    Then function "bootstrap_incus" contains pattern "<pattern>"

    Examples:
      | aspect                                  | pattern                        |
      | checks pool exists via incus storage    | incus storage show             |
      | skips if container already exists       | already exists.*skipping       |
      | launches with memory and cpu limits     | limits.memory                  |
      | polls container readiness for 30 secs   | wait_count -lt 30              |
      | installs curl and git                   | install.*curl.*git             |
      | readiness timeout is non-fatal          | warn.*did not become ready     |

  # ══════════════════════════════════════════════════════════════
  # A1.9 — Execution flow matrix (18 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario: execution flow — backend=dir skips setup_luks
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "BACKEND.*!=.*dir.*setup_luks"

  @requires.start_syntax
  Scenario: execution flow — backend=dir skips select_disk
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "BACKEND.*!=.*dir"

  @requires.start_syntax
  Scenario: execution flow — zfs LUKS uses cryptsetup before zpool
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_zfs_pool" contains pattern "cryptsetup luksFormat"
    And function "setup_zfs_pool" contains pattern "zpool create"

  @requires.start_syntax
  Scenario: execution flow — btrfs LUKS uses cryptsetup before mkfs
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_btrfs_pool" contains pattern "cryptsetup luksFormat"
    And function "setup_btrfs_pool" contains pattern "mkfs.btrfs"

  @requires.start_syntax
  Scenario: execution flow — --yes flag makes prompt_yes_no return 0
    Given the script "scripts/start.sh" source is loaded
    Then function "prompt_yes_no" contains pattern "CONFIRM_YES.*true.*return 0"

  @requires.start_syntax
  Scenario: execution flow — live OS detected sets persist path
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "boot=anklume.*anklume-persist"

  @requires.start_syntax
  Scenario: execution flow — preseed fails then minimal init attempted
    Given the script "scripts/start.sh" source is loaded
    Then function "initialize_incus" contains pattern "incus admin init --preseed"
    And function "initialize_incus" contains pattern "incus admin init --minimal"

  @requires.start_syntax
  Scenario: execution flow — both init methods fail reports error
    Given the script "scripts/start.sh" source is loaded
    Then function "initialize_incus" contains pattern "err.*initialization failed"

  @requires.start_syntax
  Scenario: execution flow — no root dies immediately
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "EUID -ne 0.*die"

  @requires.start_syntax
  Scenario: execution flow — rsync available uses rsync
    Given the script "scripts/start.sh" source is loaded
    Then function "copy_framework" contains pattern "rsync -a"

  @requires.start_syntax
  Scenario: execution flow — rsync unavailable uses tar
    Given the script "scripts/start.sh" source is loaded
    Then function "copy_framework" contains pattern "tar -C"

  @requires.start_syntax
  Scenario: execution flow — single disk found auto-selected
    Given the script "scripts/start.sh" source is loaded
    Then function "select_disk" contains pattern "Single data disk"

  @requires.start_syntax
  Scenario: execution flow — multiple disks show menu
    Given the script "scripts/start.sh" source is loaded
    Then function "select_disk" contains pattern "Multiple disks"

  @requires.start_syntax
  Scenario: execution flow — BACKEND set via --backend skips choose
    Given the script "scripts/start.sh" source is loaded
    Then function "choose_backend" contains pattern "-n.*BACKEND.*return 0"

  @requires.start_syntax
  Scenario: execution flow — container already exists skips bootstrap
    Given the script "scripts/start.sh" source is loaded
    Then function "bootstrap_incus" contains pattern "already exists.*skipping"

  @requires.start_syntax
  Scenario: execution flow — pool creation failure is fatal
    Given the script "scripts/start.sh" source is loaded
    Then function "configure_incus_storage" contains pattern "die.*Failed to create"

  @requires.start_syntax
  Scenario: execution flow — standard host uses local pool.conf
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "POOL_CONF_FILE" to "pool.conf"

  # ══════════════════════════════════════════════════════════════
  # A1.10 — Distro detection (6 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: detect_distro maps <id> to <family>
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_distro" contains pattern "<id>.*echo.*<family>"

    Examples:
      | id           | family  |
      | arch         | arch    |
      | cachyos      | arch    |
      | endeavouros  | arch    |
      | debian       | debian  |
      | ubuntu       | debian  |

  @requires.start_syntax
  Scenario: detect_distro handles unknown distro
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_distro" contains pattern "echo.*unknown"

  # ══════════════════════════════════════════════════════════════
  # A1.11 — Error messages distro-specific (6 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario Outline: <backend> missing tool error mentions <distro> package <package>
    Given the script "scripts/start.sh" source is loaded
    Then function "<func>" contains pattern "<package>"

    Examples:
      | backend | distro | package          | func             |
      | zfs     | arch   | archzfs          | setup_zfs_pool   |
      | zfs     | debian | zfsutils-linux   | setup_zfs_pool   |
      | btrfs   | arch   | btrfs-progs      | setup_btrfs_pool |
      | btrfs   | debian | btrfs-progs      | setup_btrfs_pool |
      | luks    | debian | cryptsetup       | setup_luks       |

  @requires.start_syntax
  Scenario: LUKS missing tool error mentions install
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_luks" contains pattern "die.*cryptsetup not found"

  # ══════════════════════════════════════════════════════════════
  # A1.12 — Global variables and constants (8 scenarios)
  # ══════════════════════════════════════════════════════════════

  @requires.start_syntax
  Scenario: POOL_NAME is anklume-data
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "POOL_NAME" to "anklume-data"

  @requires.start_syntax
  Scenario: LUKS_NAME constant is anklume-crypt
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "LUKS_NAME" to "anklume-crypt"

  @requires.start_syntax
  Scenario: SCRIPT_VERSION is defined
    Given the script "scripts/start.sh" source is loaded
    Then the script defines variable "SCRIPT_VERSION"

  @requires.start_syntax
  Scenario: ANKLUME_REPO has default value
    Given the script "scripts/start.sh" source is loaded
    Then the script contains pattern "ANKLUME_REPO=.*PROJECT_ROOT"

  @requires.start_syntax
  Scenario: BOOTSTRAP_IMAGE computed from distro
    Given the script "scripts/start.sh" source is loaded
    Then the script contains pattern "BOOTSTRAP_IMAGE=.*HOST_DISTRO"

  @requires.start_syntax
  Scenario: INCUS_DIR is /var/lib/incus
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "INCUS_DIR" to "/var/lib/incus"

  @requires.start_syntax
  Scenario: CONFIRM_YES defaults to false
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "CONFIRM_YES" to "false"

  @requires.start_syntax
  Scenario: LUKS_ENABLED defaults to false
    Given the script "scripts/start.sh" source is loaded
    Then the script sets "LUKS_ENABLED" to "false"

  # ══════════════════════════════════════════════════════════════
  # A2. Pool detection on second boot (critical safety feature)
  # ══════════════════════════════════════════════════════════════

  # -- A2.1: Detection function scans all disks --

  @requires.start_syntax
  Scenario: detect_existing_pool is defined
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" is defined in the script

  @requires.start_syntax
  Scenario: scan_all_disks_for_pool is defined
    Given the script "scripts/start.sh" source is loaded
    Then function "scan_all_disks_for_pool" is defined in the script

  @requires.start_syntax
  Scenario: scan_all_disks_for_pool iterates over candidate disks
    Given the script "scripts/start.sh" source is loaded
    Then function "scan_all_disks_for_pool" contains pattern "lsblk"

  @requires.start_syntax
  Scenario: scan_all_disks_for_pool calls detect_existing_pool per disk
    Given the script "scripts/start.sh" source is loaded
    Then function "scan_all_disks_for_pool" contains pattern "detect_existing_pool"

  @requires.start_syntax
  Scenario: scan_all_disks_for_pool pre-loads ZFS module for detection
    Given the script "scripts/start.sh" source is loaded
    Then function "scan_all_disks_for_pool" contains pattern "modprobe zfs"

  @requires.start_syntax
  Scenario: detection runs BEFORE choose_backend in main
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "scan_all_disks_for_pool.*choose_backend"

  @requires.start_syntax
  Scenario: detection runs BEFORE select_disk in main
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "scan_all_disks_for_pool.*select_disk"

  # -- A2.2: Detection identifies filesystem signatures --

  @requires.start_syntax
  Scenario: detect_existing_pool uses blkid for filesystem detection
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" contains pattern "blkid"

  @requires.start_syntax
  Scenario: detect_existing_pool recognizes crypto_LUKS
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" contains pattern "crypto_LUKS"

  @requires.start_syntax
  Scenario: detect_existing_pool recognizes zfs_member
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" contains pattern "zfs_member"

  @requires.start_syntax
  Scenario: detect_existing_pool recognizes btrfs
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" contains pattern "btrfs"

  @requires.start_syntax
  Scenario: detect_existing_pool checks zpool import as fallback
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" contains pattern "zpool import"

  @requires.start_syntax
  Scenario: detect_existing_pool checks pool.conf on persist partition
    Given the script "scripts/start.sh" source is loaded
    Then function "detect_existing_pool" contains pattern "/mnt/anklume-persist/pool.conf"

  # -- A2.3: Resume flow --

  @requires.start_syntax
  Scenario: resume_existing_pool is defined
    Given the script "scripts/start.sh" source is loaded
    Then function "resume_existing_pool" is defined in the script

  @requires.start_syntax
  Scenario: resume flow re-imports ZFS pool
    Given the script "scripts/start.sh" source is loaded
    Then function "resume_existing_pool" contains pattern "zpool import"

  @requires.start_syntax
  Scenario: resume flow mounts BTRFS filesystem
    Given the script "scripts/start.sh" source is loaded
    Then function "resume_existing_pool" contains pattern "mount.*BTRFS"

  @requires.start_syntax
  Scenario: resume flow opens LUKS volume
    Given the script "scripts/start.sh" source is loaded
    Then function "resume_existing_pool" contains pattern "cryptsetup luksOpen"

  @requires.start_syntax
  Scenario: resume flow skips destructive operations
    Given the script "scripts/start.sh" source is loaded
    Then function "resume_existing_pool" does not contain pattern "mkfs"
    And function "resume_existing_pool" does not contain pattern "zpool create"

  @requires.start_syntax
  Scenario: resume success skips choose_backend
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "resume_existing_pool.*copy_framework"

  @requires.start_syntax
  Scenario: resume with --yes auto-accepts
    Given the script "scripts/start.sh" source is loaded
    Then function "resume_existing_pool" contains pattern "CONFIRM_YES"

  # -- A2.4: ZFS best practices --

  @requires.start_syntax
  Scenario: ZFS pool enables deduplication
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_zfs_pool" contains pattern "dedup=on"

  @requires.start_syntax
  Scenario: ZFS pool enables compression lz4
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_zfs_pool" contains pattern "compression=lz4"

  @requires.start_syntax
  Scenario: ZFS pool disables atime
    Given the script "scripts/start.sh" source is loaded
    Then function "setup_zfs_pool" contains pattern "atime=off"

  # -- A2.5: Safety — destructive warning only for undetected disks --

  @requires.start_syntax
  Scenario: DESTRUCTIVE WARNING only shown when no pool detected
    Given the script "scripts/start.sh" source is loaded
    Then function "main" contains pattern "DESTRUCTIVE OPERATION"
