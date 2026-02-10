# ROADMAP.md — Implementation Phases

Each phase produces a testable deliverable. Do not start phase N+1 before
phase N is complete and validated.

---

## Phase 1: PSOT Generator ✦ PRIORITY

**Goal**: `infra.yml` → complete Ansible file tree

**Deliverables**:
- `scripts/generate.py` — the generator
- `infra.yml.example` — annotated example file
- Generated inventory, group_vars, host_vars with managed sections
- Constraint validation (unique names, subnets, IPs)
- Orphan detection
- `make sync` and `make sync-dry`
- `tests/test_generate.py` — pytest suite

**Validation criteria**:
- [ ] `make sync` is idempotent (re-running changes nothing)
- [ ] Adding a domain in infra.yml + `make sync` → files created
- [ ] Removing a domain → orphans detected and listed
- [ ] Managed sections rewritten, user content preserved
- [ ] Clear error messages on constraint violations
- [ ] All pytest tests pass
- [ ] `ruff` clean

---

## Phase 2: Infrastructure roles (Incus reconciliation)

**Goal**: `make apply --tags infra` creates the full Incus infrastructure

**Deliverables**:
- `roles/incus_networks/` — bridges
- `roles/incus_projects/` — projects + default profile
- `roles/incus_profiles/` — extra profiles (GPU, nesting)
- `roles/incus_storage/` — dedicated volumes
- `roles/incus_instances/` — LXC + VM instances
- `site.yml` — master playbook
- Molecule tests for each role

**Validation criteria**:
- [ ] `ansible-lint` 0 violations, production profile
- [ ] Idempotent (re-running changes nothing)
- [ ] Orphans detected and reported
- [ ] `--tags networks` works standalone
- [ ] `--limit <domain>` works standalone
- [ ] All Molecule tests pass

---

## Phase 3: Instance provisioning

**Goal**: `make apply --tags provision` installs packages and services

**Deliverables**:
- `roles/base_system/`
- `roles/incus_provision/` — installation methods (apt, pip, script, git)
- `site.yml` — phase 2 added
- `community.general.incus` connection plugin configured

**Validation criteria**:
- [ ] Instance created + provisioned in a single `make apply`
- [ ] Re-provisioning is idempotent
- [ ] Installed packages verifiable

---

## Phase 4: Snapshots

### Phase 4a: Imperative snapshot MVP (ADR-013)

**Goal**: `make snap` / `make snap-restore` via shell script

**Deliverables**:
- `scripts/snap.sh` — Bash wrapper around `incus snapshot`
- `self` keyword for auto-detection from inside an instance
- `tests/test_snap.py` — pytest suite with mocked `incus`
- Makefile targets: `snap`, `snap-restore`, `snap-list`, `snap-delete`

**Validation criteria**:
- [x] `shellcheck` clean
- [x] Individual instance snapshot/restore
- [x] `self` detection via hostname
- [x] Self-restore safety warning
- [x] All pytest tests pass

### Phase 4b: Declarative snapshots (future, if needed)

**Goal**: Ansible role with pre/post hooks, scheduling

**Deliverables**:
- `roles/incus_snapshots/`
- `snapshot.yml`
- Pre/post hooks (stop services before snapshot, etc.)

---

## Phase 5: GPU + LLM (optional)

**Goal**: GPU-enabled LXC container with LLM inference

**Deliverables**:
- Example roles (`ollama_server`, `open_webui`)
- Guide `docs/gpu-llm.md`

---

## Phase 6: Molecule + CI tests

**Goal**: Automated tests for every role, CI pipeline

**Deliverables**:
- `molecule/` in each role
- GitHub Actions workflow (`.github/workflows/ci.yml`)
- `make test` runs everything

---

## Phase 7: Documentation + release

**Goal**: Project usable by others

**Deliverables**:
- `README.md` + `README_FR.md` (always in sync)
- `docs/quickstart.md`
- `docs/lab-teaching.md`
- `docs/gpu-llm.md`
- `CONTRIBUTING.md`

---

## Current state

**Existing** (from previous sessions):
- Host bootstrap scripts (`01-host-prerequisites.sh`, `02-bootstrap-incus.sh`)
- NVIDIA driver 590.48.01 working on host
- Incus 6.21 initialized with admin container
- Prototype roles (incus_networks, incus_projects, incus_profiles) — lint-clean
  but based on old architecture, need refactoring (see ADR-001)

**To refactor**:
- Existing roles must read from group_vars/host_vars instead of custom
  `domains/` folder
