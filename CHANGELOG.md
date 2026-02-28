# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0-rc.2] - 2026-02-28

### Fixed

#### Live OS Student UX (Friction Points)
- **F-22**: `require_container` guard now detects Live OS via
  `boot=anklume` kernel parameter and allows direct host execution
  (Makefile + CLI)
- **F-19**: `first-boot.sh` now fully initializes Incus daemon
  (`incus admin init --preseed`) with default network and profile
- **F-16**: Added `dir` storage backend — no dedicated disk required;
  students with a single disk can now use anklume
- **F-15**: "Explore without persistence" wizard option now auto-provisions
  infrastructure (Incus init + starter infra.yml + sync + apply)
- **F-11**: Keyboard layout selection in welcome wizard (7 layouts);
  `anklume.keymap=XX` kernel parameter; sway workspace bindings use
  `--to-code` for layout-independent operation
- **F-07**: Default live user set to `anklume`
- **F-20**: `pool.conf` now written to `/mnt/anklume-persist/` on Live OS
  (matches systemd ConditionPathExists)
- **F-12**: Sway workspace bindings work on any keyboard layout via
  `--to-code` flag

#### Build System
- `KEYMAP` variable in `build-image.sh` replaces hardcoded `fr`
  (default: `fr`, override: `KEYMAP=us scripts/build-image.sh`)
- KDE kxkbrc, vconsole.conf, and /etc/default/keyboard all respect
  the `KEYMAP` build variable
- Fixed autologin failure: `create_live_user()` now ensures `/etc/shadow`
  entry exists with valid password hash (fallback for chroot environments
  where `useradd` creates passwd but skips shadow)
- Changed from `git archive HEAD` to `rsync` for repo copy into ISO
  (includes uncommitted working tree changes during development)

## [1.0.0-rc.1] - 2026-02-28

First release candidate. All 43 implementation phases complete.
The `infra.yml` format, CLI interface, and Ansible role contracts are
considered stable. This release targets community testing before the
final 1.0.0 release.

### Added

#### Core Framework
- **PSOT generator** (`scripts/generate.py`): declarative infrastructure
  from a single `infra.yml` file to a complete Ansible file tree
  (inventory, group_vars, host_vars) with managed sections preserving
  user edits (Phase 1)
- **Trust-level-aware IP addressing** (ADR-038): IP addresses encode
  security zones in the second octet (`10.<zone>.<seq>.<host>/24`),
  making network topology human-readable (Phase 34)
- **Nesting prefix**: optional `{level:03d}-` prefix on Incus resource
  names to prevent collisions in nested anklume deployments (Phase 16)
- **`infra/` directory mode**: split `infra.yml` into per-domain files
  for large deployments; auto-detected by the generator (ADR-030)
- **Resource allocation policy**: automatic CPU/memory distribution
  across instances based on host resources and machine weights (Phase 34)
- **Shared volumes**: declarative cross-domain file sharing via host
  bind mounts, resolved into Incus disk devices (ADR-039, Phase 34)
- **Persistent data volumes**: per-machine host-persisted directories
  surviving container rebuilds (`pd-<name>` devices, ADR-041, Phase 20g)
- **Network policies**: declarative cross-domain firewall rules in
  `infra.yml`, supporting domain/machine/host references and
  bidirectional rules (ADR-021, Phase 16)
- **Ephemeral directive**: domain and machine-level protection against
  accidental deletion, propagated to Incus `security.protection.delete`
- **Boot autostart and priority**: instance auto-start on host boot
  with configurable priority ordering

#### Infrastructure Roles (20 Ansible roles)
- `incus_projects` — Incus project namespace isolation
- `incus_networks` — domain bridge creation and configuration
- `incus_profiles` — reusable Incus profiles (GPU, nesting, resources)
- `incus_instances` — LXC container and KVM VM lifecycle management
  with idempotent reconciliation (Phase 2)
- `incus_snapshots` — declarative snapshot management (Phase 4)
- `incus_images` — OS image cache management (Phase 12)
- `incus_nftables` — inter-bridge isolation rules (Phase 8)
- `incus_firewall_vm` — multi-NIC firewall VM infrastructure (Phase 11)
- `firewall_router` — nftables routing inside firewall VM (Phase 11)
- `base_system` — base packages, locale, timezone (Phase 3)
- `admin_bootstrap` — admin-specific provisioning (Phase 3)
- `ollama_server` — Ollama LLM with GPU detection (Phase 5)
- `open_webui` — Open WebUI frontend (Phase 5)
- `stt_server` — Speech-to-Text (Speaches + faster-whisper, Phase 14)
- `openclaw_server` — self-hosted AI assistant (Phase 28b)
- `opencode_server` — sandboxed AI coding environment (Phase 23b)
- `code_sandbox` — IDE sandbox for AI tools (Phase 23b)
- `lobechat` — LobeChat web UI (Phase 28)
- `llm_sanitizer` — LLM request anonymization proxy (Phase 39)
- `dev_test_runner` / `dev_agent_runner` — test infrastructure (Phase 12, 15)

#### CLI (`bin/anklume`)
- **Docker-style CLI** with Python Typer: `anklume <noun> <verb>`
  pattern with 110+ commands across 15 command groups (Phase 43)
- `anklume sync` / `anklume domain apply` — core workflow
- `anklume snapshot create/restore/delete/list` — snapshot management
- `anklume network rules/deploy` — nftables isolation
- `anklume console` — tmux-based domain launcher with QubesOS-style
  color coding by trust level (Phase 19)
- `anklume dev lint/test/audit` — development toolchain
- `anklume lab list/start/check/hint/reset/solution` — educational labs
- `anklume live build/update/status` — Live OS management
- `anklume setup init/shares/data-dirs/import` — setup and migration
- `anklume instance remove/disp` — instance lifecycle
- `anklume llm switch/status/bench` — LLM backend management
- `anklume desktop config/apply/reset/plugins` — desktop integration
- `anklume portal open/push/pull` — cross-domain file transfer
- `anklume golden create/derive/publish/list` — golden image management
- `anklume app export/list/remove` — distrobox-style app export
- `anklume clipboard to/from/history/recall/purge` — QubesOS-style
  clipboard isolation with auto-purge on domain switch
- `anklume mode user/student/dev` — CLI mode switching
- `anklume dev cli-tree` — CLI introspection with Mermaid/JSON/deps output

#### Security
- **nftables inter-bridge isolation**: all inter-domain traffic dropped
  by default, with selective allow rules from network_policies (Phase 8)
- **Dedicated firewall VM** (`anklume-firewall`): optional VM-based
  routing with defense-in-depth alongside host nftables (Phase 11)
- **Privileged container policy**: `security.privileged=true` forbidden
  on LXC at first nesting level without VM isolation; `--YOLO` flag for
  labs (ADR-020)
- **LLM sanitization proxy**: regex-based anonymization of IaC
  identifiers (IPs, hostnames, Incus names) before cloud API calls,
  with per-domain policy control (Phase 39)
- **Exclusive AI access**: optional single-domain GPU access with VRAM
  flush on domain switch (ADR-032)
- **Pre-commit hook**: blocks private IPs, `infra.yml`, generated files,
  and black reference images from accidental commits
- **Clipboard isolation**: QubesOS-style purge on domain switch, single-use
  paste, configurable timeout, trust-level warnings (Phase 21)
- **nftables content validation**: deploy script verifies table names
  and rejects dangerous patterns before applying rules (D-038)

#### Live OS (Phase 31)
- **Hybrid ISO builder**: bootable USB images for Debian (KDE, Sway,
  labwc) with UEFI + legacy BIOS support
- **Toram support**: copy rootfs to RAM for diskless operation with
  integrity verification
- **NVIDIA GPU support**: automatic driver loading in live environment
- **French-first welcome wizard**: zero-friction onboarding with
  AZERTY keyboard and locale auto-detection
- **A/B update mechanism**: dual-slot rootfs updates with rollback

#### Testing
- **3953 pytest tests** across generator, roles, CLI, hooks, and properties
- **Behavior matrix** (`tests/behavior_matrix.yml`): structured coverage
  tracking with unique cell IDs (e.g., `DL-001`)
- **Property-based tests** (Hypothesis): generator invariants —
  idempotency, no duplicate IPs, managed markers, orphan detection
- **BDD scenarios** (behave): 21 feature files, 44 scenarios, 252 steps
  covering PSOT workflow, validation, and best/bad practices
- **Vision-based GUI tests**: QEMU + Ollama VLM for Live OS visual
  validation with soft assertions and HTML reports
- **5-layer test pyramid**: L0 (lint) → L1 (pytest/behave) →
  L2 (squashfs chroot) → L3 (container push) → L4 (QEMU) →
  L5 (full ISO rebuild)

#### Education
- **Lab framework**: self-contained labs with `lab.yml` metadata,
  step validation, hint system, and progress tracking (Phase 30)
- **5 labs**: first deployment, network isolation, snapshots,
  GPU/LLM setup, advanced networking
- **Student mode**: bilingual help (English + French), mode persistence,
  language override via `ANKLUME_LANG`

#### Desktop Integration (Phase 21)
- **Plugin system** for desktop environments: Sway, KDE, GNOME, Hyprland
  with schema-driven interface (Phase 42)
- **App export**: distrobox-style `.desktop` entry generation for
  containerized applications (Phase 26)
- **File portal**: cross-domain file transfer via `incus file push/pull`
  (Phase 25)

#### Operations
- **Golden images**: create/derive/publish workflow using `pristine`
  snapshot convention (D-048)
- **Disposable instances**: `anklume instance disp` for ephemeral
  sandboxes with auto-destruction (Phase 20a)
- **Flush protection**: `anklume flush` respects
  `security.protection.delete` and never deletes persistent data
  directories (ADR-042)
- **Upgrade mechanism**: `anklume upgrade` with conflict detection,
  `.bak` creation, and version marker (ADR-031)
- **Import**: `anklume setup import` generates `infra.yml` from
  existing Incus state
- **Doctor**: `anklume doctor` diagnoses infrastructure health
  including orphan veth pair detection

#### Documentation
- **SPEC.md**: comprehensive specification (infra.yml format, PSOT
  model, validation constraints, naming conventions)
- **ARCHITECTURE.md**: 46 Architecture Decision Records (ADR-001
  to ADR-046)
- **46 documentation files** covering all features, with French
  translations maintained in sync
- **Mermaid diagrams**: all architecture diagrams use Mermaid for
  rendering on GitHub and MkDocs (ADR-046)
- **12 example `infra.yml` files** for different use cases

#### AI Integration
- **Per-domain AI assistants** respecting network boundaries
- **Ollama backend management**: switch models, benchmark inference,
  monitor VRAM usage
- **MCP services**: inter-container tool invocation via stdio transport
  (Phase 20c)
- **OpenClaw**: per-domain self-hosted AI assistant with heartbeat
  monitoring (Phase 37, 38)
- **Network inspection**: nmap diffing and security monitoring (Phase 40)
- **Local LLM delegation**: MCP ollama-coder for GPU-accelerated code
  generation during development (Phase 28)

### Fixed
- Pre-commit hook test using whitelisted IP range (`10.100.x.x`) instead
  of a non-whitelisted `10.x.x.x` address
- Missing French translations for `build-images` and `welcome` Makefile
  targets in `i18n/fr.yml`

### Known Issues
- **Orphan veth pairs on container restart**: stale veth pairs in host
  network namespace with same MAC as new pair, causing unicast failures.
  Workaround: `anklume doctor FIX=1`. Root cause under investigation
  (possible Incus upstream issue).
- **Debian 13 (Trixie) bootstrap**: `bootstrap.sh` not yet validated
  on Trixie specifically (works on Debian 12).

[Unreleased]: https://github.com/jmchantrein/AnKLuMe/compare/v1.0.0-rc.1...HEAD
[1.0.0-rc.1]: https://github.com/jmchantrein/AnKLuMe/releases/tag/v1.0.0-rc.1
