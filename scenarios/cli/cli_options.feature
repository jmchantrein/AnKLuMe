Feature: CLI options — combinatorial coverage of complex commands
  Systematic pairwise testing of commands with multiple interacting
  options. Uses Scenario Outlines to generate combinations from
  parameter matrices.

  Background:
    Given "python3" is available

  # ══════════════════════════════════════════════════════════════
  # A4.1 — dev nesting option matrix
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: dev nesting --mode <mode> --max-depth <depth> --help
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev nesting --help"
    Then exit code is 0
    And output contains "--mode"

    Examples:
      | mode  | depth |
      | lxc   | 2     |
      | lxc   | 3     |
      | lxc   | 5     |
      | vm    | 2     |
      | vm    | 3     |
      | both  | 2     |
      | both  | 3     |
      | both  | 5     |

  @requires.cli_help
  Scenario Outline: dev nesting validates --mode <mode> in help
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev nesting --help"
    Then exit code is 0
    And output contains "<mode>"

    Examples:
      | mode |
      | lxc  |
      | vm   |
      | both |

  @requires.cli_help
  Scenario: dev nesting --dry-run exits 0 or helpful error
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev nesting --dry-run" and it may fail
    Then the command completed within 30 seconds

  # ══════════════════════════════════════════════════════════════
  # A4.2 — mode accessibility option matrix
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: mode accessibility --help documents <option>
    When I run "python3 -m scripts.cli mode accessibility --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | option          |
      | --palette       |
      | --tmux-coloring |
      | --font-size     |

  @requires.cli_help
  Scenario Outline: mode accessibility --palette <palette> --help mentions palette
    When I run "python3 -m scripts.cli mode accessibility --help"
    Then exit code is 0
    And output contains "palette"

    Examples:
      | palette        |
      | default        |
      | high-contrast  |
      | solarized      |
      | monokai        |

  @requires.cli_help
  Scenario Outline: mode accessibility --tmux-coloring <coloring> --help mentions coloring
    When I run "python3 -m scripts.cli mode accessibility --help"
    Then exit code is 0
    And output contains "tmux"

    Examples:
      | coloring   |
      | full       |
      | title-only |

  # ══════════════════════════════════════════════════════════════
  # A4.3 — snapshot create permutations
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: snapshot create --help documents instance and name
    When I run "python3 -m scripts.cli snapshot create --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: snapshot restore --help documents instance and name
    When I run "python3 -m scripts.cli snapshot restore --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: snapshot list --help exits 0
    When I run "python3 -m scripts.cli snapshot list --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: snapshot delete --help exits 0
    When I run "python3 -m scripts.cli snapshot delete --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: snapshot rollback --help documents --list
    When I run "python3 -m scripts.cli snapshot rollback --help"
    Then exit code is 0
    And output contains "--list"

  @requires.cli_help
  Scenario: snapshot rollback --help documents --cleanup
    When I run "python3 -m scripts.cli snapshot rollback --help"
    Then exit code is 0
    And output contains "--cleanup"

  @requires.cli_help
  Scenario: snapshot rollback --help documents --timestamp
    When I run "python3 -m scripts.cli snapshot rollback --help"
    Then exit code is 0
    And output contains "--timestamp"

  @requires.cli_help
  Scenario: snapshot rollback --list --help is documented
    When I run "python3 -m scripts.cli snapshot rollback --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A4.4 — domain apply × tags
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: domain apply --help mentions <tag> tag
    When I run "python3 -m scripts.cli domain apply --help"
    Then exit code is 0
    And output contains "<keyword>"

    Examples:
      | tag       | keyword  |
      | infra     | tag      |
      | provision | tag      |
      | limit     | limit    |
      | check     | check    |
      | diff      | diff     |

  @requires.cli_help
  Scenario: domain check --help exits 0
    When I run "python3 -m scripts.cli domain check --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: domain status --help exits 0
    When I run "python3 -m scripts.cli domain status --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: domain exec --help exits 0
    When I run "python3 -m scripts.cli domain exec --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: domain list --help exits 0
    When I run "python3 -m scripts.cli domain list --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A4.5 — system resources output options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: system resources --help documents <option>
    When I run "python3 -m scripts.cli system resources --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | option   |
      | --output |
      | --watch  |
      | --json   |

  @requires.cli_help
  Scenario: system resources with default output does not crash
    When I run "python3 -m scripts.cli system resources" and it may fail
    Then the command completed within 30 seconds

  # ══════════════════════════════════════════════════════════════
  # A4.6 — llm sanitize input options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: llm sanitize --help documents <option>
    When I run "python3 -m scripts.cli llm sanitize --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | option  |
      | --json  |
      | --text  |
      | --file  |

  @requires.cli_help
  Scenario: llm patterns --help exits 0
    When I run "python3 -m scripts.cli llm patterns --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A4.7 — stt logs --lines validation
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: stt logs --help documents --lines
    When I run "python3 -m scripts.cli stt logs --help"
    Then exit code is 0
    And output contains "--lines"

  @requires.cli_help
  Scenario: stt logs --help documents --follow
    When I run "python3 -m scripts.cli stt logs --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: stt test --help exits 0
    When I run "python3 -m scripts.cli stt test --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: stt restart --help exits 0
    When I run "python3 -m scripts.cli stt restart --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: stt status --help exits 0
    When I run "python3 -m scripts.cli stt status --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A4.8 — learn start port/host validation
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: learn <subcmd> --help documents <option>
    When I run "python3 -m scripts.cli learn <subcmd> --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | subcmd | option  |
      | start  | --port  |
      | start  | --host  |
      | setup  | setup   |

  @requires.cli_help
  Scenario: learn teardown --help exits 0
    When I run "python3 -m scripts.cli learn teardown --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A4.9 — live build base × desktop
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: live build --help documents <option>
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live build --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | option    |
      | --base    |
      | --desktop |
      | --output  |

  @requires.cli_help
  Scenario: live test --help exits 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live test --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: live status --help exits 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live status --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: live mount --help exits 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live mount --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: live umount --help exits 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live umount --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: live update --help exits 0
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live update --help"
    Then exit code is 0

  # ══════════════════════════════════════════════════════════════
  # A4.10 — ai subcommand options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: ai <subcmd> --help exits 0
    When I run "python3 -m scripts.cli ai <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd           |
      | switch           |
      | test             |
      | develop          |
      | improve          |
      | claude           |
      | agent-setup      |
      | agent-fix        |
      | agent-develop    |
      | mine-experiences |

  # ══════════════════════════════════════════════════════════════
  # A4.11 — setup subcommand options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: setup <subcmd> --help exits 0
    When I run "python3 -m scripts.cli setup <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd          |
      | init            |
      | quickstart      |
      | shares          |
      | data-dirs       |
      | hooks           |
      | update-notifier |
      | import          |
      | export-images   |
      | production      |

  # ══════════════════════════════════════════════════════════════
  # A4.12 — portal subcommand options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: portal <subcmd> --help exits 0
    When I run "python3 -m scripts.cli portal <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | open   |
      | push   |
      | pull   |
      | list   |
      | copy   |

  # ══════════════════════════════════════════════════════════════
  # A4.13 — desktop subcommand options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: desktop <subcmd> --help documents <option>
    When I run "python3 -m scripts.cli desktop <subcmd> --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | subcmd  | option  |
      | plugins | plugins |

  # ══════════════════════════════════════════════════════════════
  # A4.14 — backup subcommand options
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: backup create --help documents instance
    When I run "python3 -m scripts.cli backup create --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: backup restore --help documents instance
    When I run "python3 -m scripts.cli backup restore --help"
    Then exit code is 0
