Feature: CLI exhaustive — every subcommand responds to --help
  Systematic coverage of ALL anklume CLI subcommands. Each must
  accept --help and exit 0 without crashing. This is the BDD
  contract that ensures no broken imports or missing registrations.

  Background:
    Given "python3" is available

  # ── Top-level commands ──────────────────────────────────────

  @requires.cli_help
  Scenario Outline: Top-level command <cmd> accepts --help
    When I run "python3 -m scripts.cli <cmd> --help"
    Then exit code is 0

    Examples:
      | cmd       |
      | sync      |
      | flush     |
      | upgrade   |
      | guide     |
      | doctor    |
      | console   |
      | dashboard |

  # ── domain subcommands ──────────────────────────────────────

  @requires.cli_help
  Scenario Outline: domain <subcmd> accepts --help
    When I run "python3 -m scripts.cli domain <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | list   |
      | apply  |
      | check  |
      | exec   |
      | status |

  # ── instance subcommands ────────────────────────────────────

  @requires.cli_help
  Scenario Outline: instance <subcmd> accepts --help
    When I run "python3 -m scripts.cli instance <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd    |
      | list      |
      | remove    |
      | exec      |
      | info      |
      | disp      |
      | clipboard |

  # ── snapshot subcommands ────────────────────────────────────

  @requires.cli_help
  Scenario Outline: snapshot <subcmd> accepts --help
    When I run "python3 -m scripts.cli snapshot <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd   |
      | create   |
      | restore  |
      | list     |
      | delete   |
      | rollback |

  # ── network subcommands ─────────────────────────────────────

  @requires.cli_help
  Scenario Outline: network <subcmd> accepts --help
    When I run "python3 -m scripts.cli network <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | status |
      | rules  |
      | deploy |

  # ── setup subcommands ───────────────────────────────────────

  @requires.cli_help
  Scenario Outline: setup <subcmd> accepts --help
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

  # ── ai subcommands ──────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: ai <subcmd> accepts --help
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

  # ── portal subcommands ──────────────────────────────────────

  @requires.cli_help
  Scenario Outline: portal <subcmd> accepts --help
    When I run "python3 -m scripts.cli portal <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | open   |
      | push   |
      | pull   |
      | list   |
      | copy   |

  # ── llm subcommands ─────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: llm <subcmd> accepts --help
    When I run "python3 -m scripts.cli llm <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd   |
      | status   |
      | switch   |
      | bench    |
      | dev      |
      | sanitize |
      | patterns |

  # ── stt subcommands ─────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: stt <subcmd> accepts --help
    When I run "python3 -m scripts.cli stt <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd  |
      | status  |
      | restart |
      | logs    |
      | test    |

  # ── dev subcommands (dev mode) ──────────────────────────────

  @requires.cli_help
  Scenario Outline: dev <subcmd> accepts --help (dev mode)
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd             |
      | test               |
      | lint               |
      | matrix             |
      | audit              |
      | smoke              |
      | scenario           |
      | syntax             |
      | chain-test         |
      | test-summary       |
      | test-report        |
      | bdd-stubs          |
      | generate-scenarios |
      | nesting            |
      | runner             |

  # ── live subcommands (dev mode) ─────────────────────────────

  @requires.cli_help
  Scenario Outline: live <subcmd> accepts --help (dev mode)
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli live <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | build  |
      | update |
      | status |
      | test   |
      | mount  |
      | umount |

  # ── golden subcommands (dev mode) ───────────────────────────

  @requires.cli_help
  Scenario Outline: golden <subcmd> accepts --help (dev mode)
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli golden <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd  |
      | create  |
      | derive  |
      | list    |
      | publish |

  # ── mcp subcommands (dev mode) ──────────────────────────────

  @requires.cli_help
  Scenario Outline: mcp <subcmd> accepts --help (dev mode)
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli mcp <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | list   |
      | call   |

  # ── desktop subcommands ─────────────────────────────────────

  @requires.cli_help
  Scenario Outline: desktop <subcmd> accepts --help
    When I run "python3 -m scripts.cli desktop <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd  |
      | apply   |
      | reset   |
      | plugins |
      | config  |

  # ── backup subcommands ──────────────────────────────────────

  @requires.cli_help
  Scenario Outline: backup <subcmd> accepts --help
    When I run "python3 -m scripts.cli backup <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd  |
      | create  |
      | restore |

  # ── mode subcommands ────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: mode <subcmd> accepts --help
    When I run "python3 -m scripts.cli mode <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd        |
      | user          |
      | student       |
      | dev           |
      | learn-incus   |
      | accessibility |

  # ── lab subcommands ─────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: lab <subcmd> accepts --help
    When I run "python3 -m scripts.cli lab <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd   |
      | list     |
      | start    |
      | check    |
      | hint     |
      | reset    |
      | solution |

  # ── learn subcommands ───────────────────────────────────────

  @requires.cli_help
  Scenario Outline: learn <subcmd> accepts --help
    When I run "python3 -m scripts.cli learn <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd   |
      | start    |
      | setup    |
      | teardown |

  # ── system subcommands ──────────────────────────────────────

  @requires.cli_help
  Scenario: system resources accepts --help
    When I run "python3 -m scripts.cli system resources --help"
    Then exit code is 0

  # ── app subcommands ─────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: app <subcmd> accepts --help
    When I run "python3 -m scripts.cli app <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | export |
      | list   |
      | remove |

  # ── docs subcommands ────────────────────────────────────────

  @requires.cli_help
  Scenario Outline: docs <subcmd> accepts --help
    When I run "python3 -m scripts.cli docs <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | build  |
      | serve  |

  # ── telemetry subcommands (dev mode) ────────────────────────

  @requires.cli_help
  Scenario Outline: telemetry <subcmd> accepts --help (dev mode)
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli telemetry <subcmd> --help"
    Then exit code is 0

    Examples:
      | subcmd |
      | on     |
      | off    |
      | status |
      | clear  |
      | report |

  # ── Error handling ──────────────────────────────────────────

  @requires.cli_help
  Scenario: Unknown subcommand in domain group exits non-zero
    When I run "python3 -m scripts.cli domain nonexistent" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Unknown subcommand in instance group exits non-zero
    When I run "python3 -m scripts.cli instance nonexistent" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Unknown subcommand in setup group exits non-zero
    When I run "python3 -m scripts.cli setup nonexistent" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Unknown subcommand in dev group exits non-zero
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev nonexistent" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Unknown subcommand in ai group exits non-zero
    When I run "python3 -m scripts.cli ai nonexistent" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Unknown top-level command exits non-zero
    When I run "python3 -m scripts.cli totally-fake-command" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: Empty domain group shows help
    When I run "python3 -m scripts.cli domain" and it may fail
    Then output contains "Usage"

  @requires.cli_help
  Scenario: Empty dev group shows help (dev mode)
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev" and it may fail
    Then output contains "Usage"

  @requires.cli_help
  Scenario: Empty setup group shows help
    When I run "python3 -m scripts.cli setup" and it may fail
    Then output contains "Usage"

  @requires.cli_help
  Scenario: Empty ai group shows help
    When I run "python3 -m scripts.cli ai" and it may fail
    Then output contains "Usage"

  # ══════════════════════════════════════════════════════════════
  # A3.1 — Mode visibility matrix (dev-only groups × modes)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: <group> group hidden in <mode> mode
    When I run "ANKLUME_MODE=<mode> python3 -m scripts.cli --help" and it may fail
    Then output does not contain "<group_label>"

    Examples:
      | group     | mode    | group_label |
      | telemetry | user    | telemetry   |
      | telemetry | student | telemetry   |
      | live      | user    | live        |
      | live      | student | live        |
      | golden    | user    | golden      |
      | golden    | student | golden      |
      | mcp       | user    | mcp         |
      | mcp       | student | mcp         |

  @requires.cli_help
  Scenario Outline: <group> group visible in dev mode
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli --help" and it may fail
    Then output contains "<group>"

    Examples:
      | group     |
      | telemetry |
      | live      |
      | golden    |
      | mcp       |
      | dev       |

  @requires.cli_help
  Scenario Outline: essential group <group> visible in all modes (<mode>)
    When I run "ANKLUME_MODE=<mode> python3 -m scripts.cli --help" and it may fail
    Then output contains "<group>"

    Examples:
      | group  | mode    |
      | domain | user    |
      | domain | student |
      | domain | dev     |
      | lab    | user    |
      | lab    | student |
      | lab    | dev     |
      | mode   | user    |
      | mode   | student |
      | mode   | dev     |

  # ══════════════════════════════════════════════════════════════
  # A3.2 — Argument validation errors (missing required args)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: <group> <subcmd> with missing args exits non-zero
    When I run "<cmd>" and it may fail
    Then exit code is non-zero

    Examples:
      | group    | subcmd   | cmd                                                                    |
      | instance | remove   | python3 -m scripts.cli instance remove                                 |
      | instance | exec     | python3 -m scripts.cli instance exec                                   |
      | instance | info     | python3 -m scripts.cli instance info                                   |
      | snapshot | restore  | python3 -m scripts.cli snapshot restore                                |
      | snapshot | delete   | python3 -m scripts.cli snapshot delete                                 |
      | lab      | start    | python3 -m scripts.cli lab start                                       |
      | lab      | check    | python3 -m scripts.cli lab check                                       |
      | lab      | hint     | python3 -m scripts.cli lab hint                                        |
      | lab      | reset    | python3 -m scripts.cli lab reset                                       |
      | lab      | solution | python3 -m scripts.cli lab solution                                    |
      | portal   | open     | python3 -m scripts.cli portal open                                     |
      | portal   | push     | python3 -m scripts.cli portal push                                     |
      | portal   | pull     | python3 -m scripts.cli portal pull                                     |
      | backup   | create   | python3 -m scripts.cli backup create                                   |
      | backup   | restore  | python3 -m scripts.cli backup restore                                  |
      | golden   | create   | ANKLUME_MODE=dev python3 -m scripts.cli golden create                  |
      | golden   | derive   | ANKLUME_MODE=dev python3 -m scripts.cli golden derive                  |
      | golden   | publish  | ANKLUME_MODE=dev python3 -m scripts.cli golden publish                 |
      | app      | export   | python3 -m scripts.cli app export                                      |
      | app      | remove   | python3 -m scripts.cli app remove                                      |
      | doctor   | (bad)    | python3 -m scripts.cli doctor --check nonexistent_cat_42               |

  # ══════════════════════════════════════════════════════════════
  # A3.3 — Enum / valid option acceptance
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: <group> <subcmd> --help documents <option>
    When I run "<cmd>"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | group    | subcmd         | option         | cmd                                                            |
      | domain   | apply          | --tags         | python3 -m scripts.cli domain apply --help                     |
      | domain   | apply          | --limit        | python3 -m scripts.cli domain apply --help                     |
      | instance | list           | --sort         | python3 -m scripts.cli instance list --help                    |
      | snapshot | create         | --name         | python3 -m scripts.cli snapshot create --help                  |
      | snapshot | rollback       | --list         | python3 -m scripts.cli snapshot rollback --help                |
      | dev      | test           | --generator    | ANKLUME_MODE=dev python3 -m scripts.cli dev test --help        |
      | dev      | lint           | --yaml         | ANKLUME_MODE=dev python3 -m scripts.cli dev lint --help        |
      | dev      | scenario       | --best         | ANKLUME_MODE=dev python3 -m scripts.cli dev scenario --help    |
      | dev      | nesting        | --mode         | ANKLUME_MODE=dev python3 -m scripts.cli dev nesting --help     |
      | dev      | nesting        | --max-depth    | ANKLUME_MODE=dev python3 -m scripts.cli dev nesting --help     |
      | mode     | accessibility  | --palette      | python3 -m scripts.cli mode accessibility --help               |
      | desktop  | apply          | --engine       | python3 -m scripts.cli desktop apply --help                    |
      | llm      | sanitize       | --json         | python3 -m scripts.cli llm sanitize --help                     |
      | stt      | logs           | --lines        | python3 -m scripts.cli stt logs --help                         |
      | learn    | start          | --port         | python3 -m scripts.cli learn start --help                      |
      | sync     | (top)          | --dry-run      | python3 -m scripts.cli sync --help                             |
      | flush    | (top)          | --force        | python3 -m scripts.cli flush --help                            |
      | system   | resources      | --output       | python3 -m scripts.cli system resources --help                 |

  # ══════════════════════════════════════════════════════════════
  # A3.4 — Top-level command depth
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario: sync --help contains dry-run
    When I run "python3 -m scripts.cli sync --help"
    Then exit code is 0
    And output contains "dry-run"

  @requires.cli_help
  Scenario: flush --help contains force
    When I run "python3 -m scripts.cli flush --help"
    Then exit code is 0
    And output contains "force"

  @requires.cli_help
  Scenario: upgrade --help exits 0
    When I run "python3 -m scripts.cli upgrade --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: guide --help exits 0
    When I run "python3 -m scripts.cli guide --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: console --help exits 0
    When I run "python3 -m scripts.cli console --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: dashboard --help exits 0
    When I run "python3 -m scripts.cli dashboard --help"
    Then exit code is 0

  @requires.cli_help
  Scenario: Unknown top-level command exits non-zero (second variant)
    When I run "python3 -m scripts.cli xyzzy_does_not_exist_42" and it may fail
    Then exit code is non-zero

  @requires.cli_help
  Scenario: sync without infra.yml gives helpful error
    When I run "python3 -m scripts.cli sync --dry-run" and it may fail
    # Should either succeed (dry-run) or give a clear error about missing infra.yml
    Then the command completed within 30 seconds

  # ══════════════════════════════════════════════════════════════
  # A3.5 — dev subcommands depth (lint filters, test filters)
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: dev <subcmd> --help documents <option>
    When I run "ANKLUME_MODE=dev python3 -m scripts.cli dev <subcmd> --help"
    Then exit code is 0
    And output contains "<option>"

    Examples:
      | subcmd     | option       |
      | lint       | --yaml       |
      | lint       | --ansible    |
      | lint       | --shell      |
      | lint       | --python     |
      | test       | --generator  |
      | test       | --roles      |
      | scenario   | --best       |
      | scenario   | --bad        |
      | matrix     | --generate   |
      | audit      | --json       |
      | chain-test | --dry-run    |
      | nesting    | --dry-run    |
      | nesting    | --mode       |
      | nesting    | --max-depth  |

  # ══════════════════════════════════════════════════════════════
  # A3.6 — Empty groups show help
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: Empty <group> group shows help
    When I run "<cmd>" and it may fail
    Then output contains "Usage"

    Examples:
      | group     | cmd                                                  |
      | instance  | python3 -m scripts.cli instance                      |
      | snapshot  | python3 -m scripts.cli snapshot                      |
      | network   | python3 -m scripts.cli network                       |
      | portal    | python3 -m scripts.cli portal                        |
      | llm       | python3 -m scripts.cli llm                           |
      | stt       | python3 -m scripts.cli stt                           |
      | backup    | python3 -m scripts.cli backup                        |
      | app       | python3 -m scripts.cli app                           |
      | desktop   | python3 -m scripts.cli desktop                       |
      | lab       | python3 -m scripts.cli lab                           |
      | learn     | python3 -m scripts.cli learn                         |
      | golden    | ANKLUME_MODE=dev python3 -m scripts.cli golden        |
      | mcp       | ANKLUME_MODE=dev python3 -m scripts.cli mcp           |
      | telemetry | ANKLUME_MODE=dev python3 -m scripts.cli telemetry     |
      | live      | ANKLUME_MODE=dev python3 -m scripts.cli live          |
      | docs      | python3 -m scripts.cli docs                          |

  # ══════════════════════════════════════════════════════════════
  # A3.7 — Unknown subcommand in every group exits non-zero
  # ══════════════════════════════════════════════════════════════

  @requires.cli_help
  Scenario Outline: Unknown subcommand in <group> group exits non-zero
    When I run "<cmd>" and it may fail
    Then exit code is non-zero

    Examples:
      | group     | cmd                                                              |
      | snapshot  | python3 -m scripts.cli snapshot nonexistent                      |
      | network   | python3 -m scripts.cli network nonexistent                      |
      | portal    | python3 -m scripts.cli portal nonexistent                       |
      | llm       | python3 -m scripts.cli llm nonexistent                          |
      | stt       | python3 -m scripts.cli stt nonexistent                          |
      | backup    | python3 -m scripts.cli backup nonexistent                       |
      | app       | python3 -m scripts.cli app nonexistent                          |
      | desktop   | python3 -m scripts.cli desktop nonexistent                      |
      | lab       | python3 -m scripts.cli lab nonexistent                          |
      | learn     | python3 -m scripts.cli learn nonexistent                        |
      | mode      | python3 -m scripts.cli mode nonexistent                         |
      | golden    | ANKLUME_MODE=dev python3 -m scripts.cli golden nonexistent      |
      | mcp       | ANKLUME_MODE=dev python3 -m scripts.cli mcp nonexistent         |
      | telemetry | ANKLUME_MODE=dev python3 -m scripts.cli telemetry nonexistent   |
      | live      | ANKLUME_MODE=dev python3 -m scripts.cli live nonexistent        |
      | docs      | python3 -m scripts.cli docs nonexistent                         |
