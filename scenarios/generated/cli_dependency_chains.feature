# Auto-generated from _cli_deps.yml — do not edit manually.
# Regenerate with: python3 scripts/generate-dep-scenarios.py --write

Feature: CLI resource dependency chains
  Each command depends on resources produced by prerequisite commands.
  Running a consumer before its producer should fail or produce errors.

  Scenario: backup.create depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # backup.create requires 1 prerequisite(s)

  Scenario: backup.restore depends on backup.create
    # Resources needed: backup_archive
    # Producers: backup.create
    Given a clean sandbox environment
    # backup.restore requires 1 prerequisite(s)

  Scenario: console depends on desktop.apply, domain.apply, setup.import, setup.quickstart
    # Resources needed: desktop_config, incus_state, infra_config
    # Producers: desktop.apply, domain.apply, setup.import, setup.quickstart
    Given a clean sandbox environment
    # console requires 4 prerequisite(s)

  Scenario: desktop.apply depends on setup.import, setup.quickstart
    # Resources needed: infra_config
    # Producers: setup.import, setup.quickstart
    Given a clean sandbox environment
    # desktop.apply requires 2 prerequisite(s)

  Scenario: doctor depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # doctor requires 1 prerequisite(s)

  Scenario: domain.apply depends on setup.data-dirs, setup.init, setup.shares, sync
    # Resources needed: ansible_files, galaxy_deps, host_dirs
    # Producers: setup.data-dirs, setup.init, setup.shares, sync
    Given a clean sandbox environment
    # domain.apply requires 4 prerequisite(s)

  Scenario: domain.check depends on setup.init, sync
    # Resources needed: ansible_files, galaxy_deps
    # Producers: setup.init, sync
    Given a clean sandbox environment
    # domain.check requires 2 prerequisite(s)

  Scenario: domain.exec depends on domain.apply, sync
    # Resources needed: ansible_files, incus_state
    # Producers: domain.apply, sync
    Given a clean sandbox environment
    # domain.exec requires 2 prerequisite(s)

  Scenario: domain.list depends on setup.import, setup.quickstart
    # Resources needed: infra_config
    # Producers: setup.import, setup.quickstart
    Given a clean sandbox environment
    # domain.list requires 2 prerequisite(s)

  Scenario: domain.status depends on domain.apply, setup.import, setup.quickstart, sync
    # Resources needed: ansible_files, incus_state, infra_config
    # Producers: domain.apply, setup.import, setup.quickstart, sync
    Given a clean sandbox environment
    # domain.status requires 4 prerequisite(s)

  Scenario: golden.create depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # golden.create requires 1 prerequisite(s)

  Scenario: golden.derive depends on golden.create
    # Resources needed: golden_images
    # Producers: golden.create
    Given a clean sandbox environment
    # golden.derive requires 1 prerequisite(s)

  Scenario: golden.publish depends on golden.create
    # Resources needed: golden_images
    # Producers: golden.create
    Given a clean sandbox environment
    # golden.publish requires 1 prerequisite(s)

  Scenario: instance.clipboard depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # instance.clipboard requires 1 prerequisite(s)

  Scenario: instance.disp depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # instance.disp requires 1 prerequisite(s)

  Scenario: instance.exec depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # instance.exec requires 1 prerequisite(s)

  Scenario: instance.info depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # instance.info requires 1 prerequisite(s)

  Scenario: instance.list depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # instance.list requires 1 prerequisite(s)

  Scenario: instance.remove depends on domain.apply
    # Resources needed: incus_state
    # Producers: domain.apply
    Given a clean sandbox environment
    # instance.remove requires 1 prerequisite(s)

  Scenario: lab.check depends on lab.check, lab.start
    # Resources needed: lab_progress
    # Producers: lab.check, lab.start
    Given a clean sandbox environment
    # lab.check requires 2 prerequisite(s)

  Scenario: lab.hint depends on lab.check, lab.start
    # Resources needed: lab_progress
    # Producers: lab.check, lab.start
    Given a clean sandbox environment
    # lab.hint requires 2 prerequisite(s)

  Scenario: lab.reset depends on lab.check, lab.start
    # Resources needed: lab_progress
    # Producers: lab.check, lab.start
    Given a clean sandbox environment
    # lab.reset requires 2 prerequisite(s)

  Scenario: lab.solution depends on lab.check, lab.start
    # Resources needed: lab_progress
    # Producers: lab.check, lab.start
    Given a clean sandbox environment
    # lab.solution requires 2 prerequisite(s)

  Scenario: live.test depends on live.build
    # Resources needed: iso_image
    # Producers: live.build
    Given a clean sandbox environment
    # live.test requires 1 prerequisite(s)

  Scenario: live.update depends on live.build
    # Resources needed: iso_image
    # Producers: live.build
    Given a clean sandbox environment
    # live.update requires 1 prerequisite(s)

  Scenario: network.deploy depends on network.rules
    # Resources needed: nftables_rules
    # Producers: network.rules
    Given a clean sandbox environment
    # network.deploy requires 1 prerequisite(s)

  Scenario: network.rules depends on setup.import, setup.quickstart
    # Resources needed: infra_config
    # Producers: setup.import, setup.quickstart
    Given a clean sandbox environment
    # network.rules requires 2 prerequisite(s)

  Scenario: snapshot.create depends on domain.apply, sync
    # Resources needed: ansible_files, incus_state
    # Producers: domain.apply, sync
    Given a clean sandbox environment
    # snapshot.create requires 2 prerequisite(s)

  Scenario: snapshot.delete depends on domain.apply, snapshot.create, sync
    # Resources needed: ansible_files, incus_snapshots, incus_state
    # Producers: domain.apply, snapshot.create, sync
    Given a clean sandbox environment
    # snapshot.delete requires 3 prerequisite(s)

  Scenario: snapshot.list depends on domain.apply, sync
    # Resources needed: ansible_files, incus_state
    # Producers: domain.apply, sync
    Given a clean sandbox environment
    # snapshot.list requires 2 prerequisite(s)

  Scenario: snapshot.restore depends on domain.apply, snapshot.create, sync
    # Resources needed: ansible_files, incus_snapshots, incus_state
    # Producers: domain.apply, snapshot.create, sync
    Given a clean sandbox environment
    # snapshot.restore requires 3 prerequisite(s)

  Scenario: snapshot.rollback depends on domain.apply, snapshot.create, sync
    # Resources needed: ansible_files, incus_snapshots, incus_state
    # Producers: domain.apply, snapshot.create, sync
    Given a clean sandbox environment
    # snapshot.rollback requires 3 prerequisite(s)

  Scenario: sync depends on setup.import, setup.quickstart
    # Resources needed: infra_config
    # Producers: setup.import, setup.quickstart
    Given a clean sandbox environment
    # sync requires 2 prerequisite(s)
