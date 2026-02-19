.DEFAULT_GOAL := help
SHELL := /bin/bash

# ── PSOT Generator ────────────────────────────────────────
INFRA_SRC := $(if $(wildcard infra/base.yml),infra,infra.yml)

sync: ## Generate/update Ansible files from infra.yml or infra/
	$(call tele_wrap,sync,python3 scripts/generate.py $(INFRA_SRC))

sync-dry: ## Preview changes without writing
	python3 scripts/generate.py $(INFRA_SRC) --dry-run

sync-clean: ## Remove orphan files without confirmation
	python3 scripts/generate.py $(INFRA_SRC) --clean-orphans

# ── Telemetry (Phase 19b) ────────────────────────────────
# Shell function to wrap a command with telemetry logging.
# Usage in recipes: $(call tele_wrap,<target>,<command>)
# If telemetry is disabled (no ~/.anklume/telemetry/enabled), runs the command directly.
define tele_wrap
	@if [ -f "$$HOME/.anklume/telemetry/enabled" ]; then \
		_start=$$(date +%s); \
		$(2); _rc=$$?; \
		_end=$$(date +%s); \
		_dur=$$(( _end - _start )); \
		python3 scripts/telemetry.py log --target "$(1)" --duration "$$_dur" --exit-code "$$_rc" \
			$(if $(G),--domain "$(G)") 2>/dev/null || true; \
		exit $$_rc; \
	else \
		$(2); \
	fi
endef

telemetry-on: ## Enable local telemetry (opt-in, local-only)
	@python3 scripts/telemetry.py on

telemetry-off: ## Disable local telemetry
	@python3 scripts/telemetry.py off

telemetry-status: ## Show telemetry state and event count
	@python3 scripts/telemetry.py status

telemetry-clear: ## Delete all telemetry data
	@python3 scripts/telemetry.py clear

telemetry-report: ## Terminal charts of usage patterns
	@python3 scripts/telemetry.py report

# ── Console (Phase 19a) ───────────────────────────────────
console: ## Launch tmux console with domain-colored panes
	python3 scripts/console.py $(if $(KILL),--kill) $(if $(DRY_RUN),--dry-run)

# ── Desktop Integration (Phase 21) ──────────────────────
clipboard-to: ## Copy host clipboard INTO container (I=<instance> [PROJECT=<p>])
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make clipboard-to I=<instance>"; exit 1; }
	scripts/clipboard.sh copy-to $(I) $(if $(PROJECT),--project $(PROJECT))

clipboard-from: ## Copy container clipboard TO host (I=<instance> [PROJECT=<p>])
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make clipboard-from I=<instance>"; exit 1; }
	scripts/clipboard.sh copy-from $(I) $(if $(PROJECT),--project $(PROJECT))

domain-exec: ## Open terminal to instance with domain colors (I=<instance>)
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make domain-exec I=<instance>"; exit 1; }
	scripts/domain-exec.sh $(I) $(if $(PROJECT),--project $(PROJECT)) $(if $(TERMINAL),--terminal)

desktop-config: ## Generate desktop environment config from infra.yml
	python3 scripts/desktop_config.py $(if $(SWAY),--sway) $(if $(FOOT),--foot) $(if $(DESKTOP),--desktop)

dashboard: ## Launch web dashboard (PORT=8888)
	python3 scripts/dashboard.py --port $(or $(PORT),8888) $(if $(HOST),--host $(HOST))

# ── App Export (Phase 26) ────────────────────────────────
export-app: ## Export container app to host desktop (I=<instance> APP=<app>)
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make export-app I=<instance> APP=<app>"; exit 1; }
	@test -n "$(APP)" || { echo "ERROR: APP required."; exit 1; }
	scripts/export-app.sh export $(I) $(APP) $(if $(PROJECT),--project $(PROJECT))

export-list: ## List exported container apps [I=<instance>]
	scripts/export-app.sh list $(if $(I),$(I)) $(if $(PROJECT),--project $(PROJECT))

export-remove: ## Remove exported app (I=<instance> APP=<app>)
	@test -n "$(I)" || { echo "ERROR: I required."; exit 1; }
	@test -n "$(APP)" || { echo "ERROR: APP required."; exit 1; }
	scripts/export-app.sh remove $(I) $(APP)

# ── Quality ───────────────────────────────────────────────
lint: lint-yaml lint-ansible lint-shell lint-python ## Run ALL validators

lint-yaml: ## Validate all YAML files
	yamllint -c .yamllint.yml .

lint-ansible: ## Validate Ansible roles and playbooks
	ansible-lint

lint-shell: ## Validate shell scripts
	@if compgen -G "scripts/*.sh" > /dev/null || compgen -G "scripts/hooks/*" > /dev/null; then \
		shellcheck scripts/*.sh scripts/hooks/*; \
	else \
		echo "No shell scripts found, skipping shellcheck"; \
	fi

lint-python: ## Validate Python files
	@if compgen -G "scripts/*.py" > /dev/null || compgen -G "tests/*.py" > /dev/null; then \
		ruff check .; \
	else \
		echo "No Python files found, skipping ruff"; \
	fi

check: ## Dry-run (ansible-playbook --check --diff)
	ansible-playbook site.yml --check --diff

syntax: ## Syntax check only
	ansible-playbook site.yml --syntax-check

# ── Network Safety Wrapper ───────────────────────────────
# Wraps network-critical commands with safety checks
# Usage: $(call safe_apply_wrap,<target>,<command>)
define safe_apply_wrap
	$(if $(ANKLUME_SKIP_NETWORK_CHECK),,@echo "🛡️  Network safety: backing up current state...")
	$(if $(ANKLUME_SKIP_NETWORK_CHECK),,@scripts/network-safety-check.sh backup)
	$(if $(SKIP_SNAPSHOT),,@scripts/snapshot-apply.sh create $(if $(3),--limit $(3)))
	@echo "🔄 Running: $(1)"
	@$(call tele_wrap,$(1),$(2))
	$(if $(ANKLUME_SKIP_NETWORK_CHECK),,@echo "✅ Verifying network connectivity...")
	$(if $(ANKLUME_SKIP_NETWORK_CHECK),,@scripts/network-safety-check.sh verify || (echo "⚠️  WARNING: Network connectivity lost after $(1)!" && \
		echo "    Last backup: $$(ls -t ~/.anklume-network-backups/network-*.txt 2>/dev/null | head -1)" && \
		echo "    Run: scripts/network-safety-check.sh restore-info" && exit 1))
	$(if $(SKIP_SNAPSHOT),,@scripts/snapshot-apply.sh cleanup $(if $(KEEP),--keep $(KEEP)))
	@echo "✅ $(1) complete"
endef

# ── Apply ─────────────────────────────────────────────────
apply: ## Apply full infrastructure + provisioning
	@if [ ! -d inventory ] || [ -z "$$(ls inventory/*.yml 2>/dev/null)" ]; then \
		echo "ERROR: No inventory files found. Run 'make sync' first to generate them from infra.yml." >&2; \
		exit 1; \
	fi
	$(call safe_apply_wrap,apply,ansible-playbook site.yml)

apply-infra: ## Apply infrastructure only (networks, projects, instances)
	$(call safe_apply_wrap,apply-infra,ansible-playbook site.yml --tags infra)

apply-provision: ## Apply provisioning only (packages, services)
	$(call tele_wrap,apply-provision,ansible-playbook site.yml --tags provision)

apply-base: ## Apply base_system only
	ansible-playbook site.yml --tags base

apply-limit: ## Apply a single domain (G=<group>)
	$(call safe_apply_wrap,apply-limit,ansible-playbook site.yml --limit $(G),$(G))

apply-images: ## Pre-download OS images to local cache
	ansible-playbook site.yml --tags images

apply-llm: ## Apply LLM roles (Ollama + Open WebUI)
	ansible-playbook site.yml --tags llm

apply-stt: ## Apply STT role (Speaches + faster-whisper)
	ansible-playbook site.yml --tags stt

apply-ai: ## Apply AI tools roles (Ollama + WebUI + LobeChat + OpenCode)
	ansible-playbook site.yml --tags llm,stt,lobechat,opencode

apply-code-sandbox: ## Apply code_sandbox role (sandboxed AI coding)
	ansible-playbook site.yml --tags code_sandbox

export-images: ## Export images for nested Incus sharing
	ansible-playbook site.yml --tags images -e incus_images_export_for_nesting=true

# ── nftables Isolation ───────────────────────────────────
nftables: ## Generate nftables isolation rules
	ansible-playbook site.yml --tags nftables

nftables-deploy: ## Deploy nftables rules on host (run FROM host)
	scripts/deploy-nftables.sh

# ── Snapshots (Ansible role) ──────────────────────────────
snapshot: ## Create snapshot of all instances (NAME=optional)
	ansible-playbook snapshot.yml $(if $(NAME),-e snapshot_name=$(NAME))

snapshot-domain: ## Create snapshot of one domain (D=domain NAME=optional)
	ansible-playbook snapshot.yml --limit $(D) $(if $(NAME),-e snapshot_name=$(NAME))

restore: ## Restore snapshot (NAME=required)
	ansible-playbook snapshot.yml -e snapshot_action=restore -e snapshot_name=$(NAME)

restore-domain: ## Restore snapshot for one domain (D=domain NAME=required)
	ansible-playbook snapshot.yml -e snapshot_action=restore -e snapshot_name=$(NAME) --limit $(D)

snapshot-delete: ## Delete snapshot (NAME=required)
	ansible-playbook snapshot.yml -e snapshot_action=delete -e snapshot_name=$(NAME)

snapshot-list: ## List snapshots for all instances
	ansible-playbook snapshot.yml -e snapshot_action=list

# ── Rollback (Phase 24) ─────────────────────────────────
rollback: ## Restore most recent pre-apply snapshot (or T=<timestamp>)
	@scripts/snapshot-apply.sh rollback $(T)

rollback-list: ## List available pre-apply snapshots
	@scripts/snapshot-apply.sh list

rollback-cleanup: ## Remove old pre-apply snapshots (KEEP=3 default)
	@scripts/snapshot-apply.sh cleanup $(if $(KEEP),--keep $(KEEP))

# ── Testing ───────────────────────────────────────────────
test: test-generator test-roles ## Run all tests

test-generator: ## Run generator pytest tests
	$(call tele_wrap,test-generator,python3 -m pytest tests/ -v)

test-roles: ## Run Molecule tests for all roles
	@for role in roles/*/; do \
		if [ -d "$$role/molecule" ]; then \
			echo "=== Testing $$(basename $$role) ==="; \
			(cd "$$role" && molecule test) || exit 1; \
		fi; \
	done

test-role: ## Run Molecule test for one role (R=role_name)
	cd roles/$(R) && molecule test

# ── Sandboxed Testing (Incus-in-Incus) ──────────────────
test-sandboxed: ## Run all Molecule tests in isolated sandbox
	@scripts/run-tests.sh full

test-sandboxed-role: ## Run one role's test in sandbox (R=role_name)
	@scripts/run-tests.sh full $(R)

runner-create: ## Create the AnKLuMe runner container
	@scripts/run-tests.sh create

runner-destroy: ## Destroy the AnKLuMe runner container
	@scripts/run-tests.sh destroy

# ── Scenario Testing (Phase 22) ──────────────────────────
scenario-test: ## Run all E2E scenarios in sandbox (slow, on-demand)
	python3 -m pytest scenarios/ -v --tb=long

scenario-test-best: ## Run best-practice scenarios only
	python3 -m pytest scenarios/best_practices/ -v --tb=long

scenario-test-bad: ## Run bad-practice scenarios only
	python3 -m pytest scenarios/bad_practices/ -v --tb=long

scenario-list: ## List all available scenarios
	@echo "Best practices:"; grep -rh "Scenario:" scenarios/best_practices/ 2>/dev/null | sed 's/^/  /'; \
	echo ""; echo "Bad practices:"; grep -rh "Scenario:" scenarios/bad_practices/ 2>/dev/null | sed 's/^/  /'

# ── Behavior Matrix (Phase 18b) ──────────────────────────
matrix-coverage: ## Show behavior matrix test coverage
	python3 scripts/matrix-coverage.py

matrix-generate: ## Generate tests for uncovered matrix cells (AI_MODE=...)
	scripts/ai-matrix-test.sh $(if $(AI_MODE),--mode $(AI_MODE))

# ── AI-Assisted Testing (Phase 13) ────────────────────────
ai-test: ## Run tests + AI-assisted fixing (AI_MODE=none|local|remote|claude-code|aider)
	ANKLUME_AI_MODE=$(or $(AI_MODE),none) \
	ANKLUME_AI_DRY_RUN=$(or $(DRY_RUN),true) \
	ANKLUME_AI_MAX_RETRIES=$(or $(MAX_RETRIES),3) \
	scripts/ai-test-loop.sh

ai-test-role: ## AI-assisted test for one role (R=role_name AI_MODE=backend)
	ANKLUME_AI_MODE=$(or $(AI_MODE),none) \
	ANKLUME_AI_DRY_RUN=$(or $(DRY_RUN),true) \
	ANKLUME_AI_MAX_RETRIES=$(or $(MAX_RETRIES),3) \
	scripts/ai-test-loop.sh $(R)

ai-develop: ## Autonomous development (TASK="description" AI_MODE=backend)
	@test -n "$(TASK)" || { echo "ERROR: TASK required. Usage: make ai-develop TASK=\"...\" AI_MODE=claude-code"; exit 1; }
	ANKLUME_AI_MODE=$(or $(AI_MODE),claude-code) \
	ANKLUME_AI_DRY_RUN=$(or $(DRY_RUN),true) \
	scripts/ai-develop.sh "$(TASK)"

# ── Local LLM Dev Assistant ──────────────────────────────
ollama-dev: ## Interactive local LLM dev assistant (no API credits needed)
	python3 scripts/ollama-dev.py $(if $(TASK),"$(TASK)") $(if $(DRY_RUN),--dry-run) $(if $(FAST),--fast)

# ── Experience Library (Phase 18d) ────────────────────────
mine-experiences: ## Extract fix patterns from git history
	python3 scripts/mine-experiences.py

ai-improve: ## Spec-driven improvement loop (SCOPE=generator|roles|all)
	scripts/ai-improve.sh --scope $(or $(SCOPE),all) $(if $(filter false,$(DRY_RUN)),,--dry-run)

# ── Agent Teams (Phase 15) ────────────────────────────────
agent-runner-setup: ## Install Claude Code + Agent Teams in runner container
	@incus info $(or $(RUNNER),anklume) &>/dev/null || { echo "ERROR: Runner not found. Run 'make runner-create' first."; exit 1; }
	ansible-playbook -i "$(or $(RUNNER),anklume)," -c community.general.incus \
		--extra-vars "ansible_incus_project=$(or $(PROJECT),default)" \
		-e "@roles/dev_agent_runner/defaults/main.yml" \
		site.yml --tags agent-setup 2>/dev/null || \
	incus exec $(or $(RUNNER),anklume) --project $(or $(PROJECT),default) -- bash -c "\
		curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
		apt-get install -y nodejs tmux && \
		npm install -g @anthropic-ai/claude-code && \
		mkdir -p /root/.claude && \
		echo 'Agent runner setup complete'"

ai-switch: ## Switch AI-tools access to another domain (DOMAIN=<name>)
	scripts/ai-switch.sh --domain $(DOMAIN) $(if $(NO_FLUSH),--no-flush)

agent-fix: ## Autonomous test fixing with Claude Code Agent Teams (R=role)
	@scripts/agent-fix.sh $(R)

agent-develop: ## Autonomous development with Agent Teams (TASK="description")
	@test -n "$(TASK)" || { echo "ERROR: TASK required. Usage: make agent-develop TASK=\"...\""; exit 1; }
	@scripts/agent-develop.sh "$(TASK)"

# ── File Transfer and Backup (Phase 20d) ────────────────
file-copy: ## Copy file between instances (SRC=instance:/path DST=instance:/path)
	scripts/transfer.sh copy $(SRC) $(DST)

backup: ## Backup an instance (I=<instance> [GPG=<recipient>] [O=<dir>])
	scripts/transfer.sh backup $(if $(GPG),--gpg-recipient $(GPG)) $(if $(O),--output $(O)) $(I)

restore-backup: ## Restore instance from backup (FILE=<backup> [NAME=<name>] [PROJECT=<project>])
	scripts/transfer.sh restore $(if $(NAME),--name $(NAME)) $(if $(PROJECT),--project $(PROJECT)) $(FILE)

# ── File Portal (Phase 25) ──────────────────────────────
portal-open: ## Open file from container via portal (I=<instance> PATH=<path>)
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make portal-open I=<instance> PATH=<path>"; exit 1; }
	@test -n "$(PATH)" || { echo "ERROR: PATH required."; exit 1; }
	scripts/file-portal.sh open $(I) $(PATH) $(if $(PROJECT),--project $(PROJECT))

portal-push: ## Push file to container via portal (I=<instance> SRC=<src> DST=<dst>)
	@test -n "$(I)" || { echo "ERROR: I required."; exit 1; }
	scripts/file-portal.sh push $(I) $(SRC) $(DST) $(if $(PROJECT),--project $(PROJECT))

portal-pull: ## Pull file from container via portal (I=<instance> SRC=<src> DST=<dst>)
	@test -n "$(I)" || { echo "ERROR: I required."; exit 1; }
	scripts/file-portal.sh pull $(I) $(SRC) $(DST) $(if $(PROJECT),--project $(PROJECT))

portal-list: ## List configured file portals
	scripts/file-portal.sh list

# ── Code Analysis (Phase 19c) ────────────────────────
dead-code: ## Run dead code detection (vulture + shellcheck)
	@scripts/code-analysis.sh dead-code

call-graph: ## Generate Python call graph (DOT + SVG in reports/)
	@scripts/code-analysis.sh call-graph

dep-graph: ## Generate module dependency graph (SVG in reports/)
	@scripts/code-analysis.sh dep-graph

code-graph: ## Run all static code analysis tools
	@scripts/code-analysis.sh all

audit: ## Produce codebase audit report (dead code, metrics, coverage)
	@python3 scripts/code-audit.py

audit-json: ## Produce audit report as JSON (to reports/audit.json)
	@python3 scripts/code-audit.py --json --output reports/audit.json

# ── Smoke Testing (Phase 29) ────────────────────────────
smoke: ## Real-world smoke test (requires running Incus daemon)
	@echo "=== AnKLuMe Smoke Test ==="
	@echo ""
	@echo "--- Step 1/5: Generator (make sync-dry) ---"
	@python3 scripts/generate.py $(INFRA_SRC) --dry-run
	@echo "PASS: Generator works"
	@echo ""
	@echo "--- Step 2/5: Dry-run apply (make check) ---"
	@ansible-playbook site.yml --check --diff
	@echo "PASS: Dry-run apply succeeds"
	@echo ""
	@echo "--- Step 3/5: Linting (make lint) ---"
	@$(MAKE) lint
	@echo "PASS: All linters pass"
	@echo ""
	@echo "--- Step 4/5: Snapshot listing ---"
	@ansible-playbook snapshot.yml -e snapshot_action=list
	@echo "PASS: Snapshot infrastructure responds"
	@echo ""
	@echo "--- Step 5/5: Incus connectivity ---"
	@incus list --format csv | head -5 || { echo "FAIL: incus list failed"; exit 1; }
	@echo "PASS: Incus daemon reachable"
	@echo ""
	@echo "=== All smoke tests passed ==="

# ── Disposable Instances (Phase 20a) ────────────────────
disp: ## Launch disposable ephemeral instance (IMAGE=... CMD=... DOMAIN=... VM=1)
	scripts/disp.sh $(if $(IMAGE),--image $(IMAGE)) $(if $(DOMAIN),--domain $(DOMAIN)) $(if $(CMD),--cmd "$(CMD)") $(if $(VM),--vm)

# ── Golden Images (Phase 20b) ───────────────────────────
golden-create: ## Create golden image from instance (NAME=<instance> [PROJECT=<project>])
	@test -n "$(NAME)" || { echo "ERROR: NAME required. Usage: make golden-create NAME=<instance>"; exit 1; }
	scripts/golden.sh create $(NAME) $(if $(PROJECT),--project $(PROJECT))

golden-derive: ## Derive instance from golden image (TEMPLATE=<name> INSTANCE=<new> [PROJECT=<project>])
	@test -n "$(TEMPLATE)" || { echo "ERROR: TEMPLATE required."; exit 1; }
	@test -n "$(INSTANCE)" || { echo "ERROR: INSTANCE required."; exit 1; }
	scripts/golden.sh derive $(TEMPLATE) $(INSTANCE) $(if $(PROJECT),--project $(PROJECT))

golden-publish: ## Publish golden image as Incus image (TEMPLATE=<name> ALIAS=<alias> [PROJECT=<project>])
	@test -n "$(TEMPLATE)" || { echo "ERROR: TEMPLATE required."; exit 1; }
	@test -n "$(ALIAS)" || { echo "ERROR: ALIAS required."; exit 1; }
	scripts/golden.sh publish $(TEMPLATE) $(ALIAS) $(if $(PROJECT),--project $(PROJECT))

golden-list: ## List golden images (instances with 'pristine' snapshot)
	@scripts/golden.sh list $(if $(PROJECT),--project $(PROJECT))

# ── MCP Services (Phase 20c) ──────────────────────────────
mcp-list: ## List MCP tools available on an instance (I=<instance>)
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make mcp-list I=<instance>"; exit 1; }
	python3 scripts/mcp-client.py --instance $(I) $(if $(PROJECT),-p $(PROJECT)) list

mcp-call: ## Call an MCP tool on an instance (I=<instance> TOOL=<name> ARGS='{}')
	@test -n "$(I)" || { echo "ERROR: I required."; exit 1; }
	@test -n "$(TOOL)" || { echo "ERROR: TOOL required."; exit 1; }
	python3 scripts/mcp-client.py --instance $(I) $(if $(PROJECT),-p $(PROJECT)) call $(TOOL) $(if $(ARGS),'$(ARGS)')

# ── Tor Gateway (Phase 20e) ────────────────────────────────
apply-tor: ## Setup Tor transparent proxy in container (I=<instance> [PROJECT=<project>])
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make apply-tor I=<instance>"; exit 1; }
	scripts/tor-gateway.sh setup $(I) $(if $(PROJECT),--project $(PROJECT))

# ── Print Service (Phase 20e) ─────────────────────────────
apply-print: ## Setup CUPS print service in container (I=<instance> [PROJECT=<project>])
	@test -n "$(I)" || { echo "ERROR: I required. Usage: make apply-print I=<instance>"; exit 1; }
	scripts/sys-print.sh setup $(I) $(if $(PROJECT),--project $(PROJECT))

# ── Lifecycle ─────────────────────────────────────────────
flush: ## Destroy all AnKLuMe infrastructure (FORCE=true required in prod)
	@scripts/flush.sh $(if $(FORCE),--force)

upgrade: ## Safe framework update with conflict detection
	@scripts/upgrade.sh

import-infra: ## Generate infra.yml from existing Incus state
	@scripts/import-infra.sh $(if $(O),-o $(O))

# ── Getting Started ──────────────────────────────────────
guide: ## Interactive step-by-step onboarding tutorial
	scripts/guide.sh $(if $(STEP),--step $(STEP)) $(if $(AUTO),--auto)

quickstart: ## Copy example infra.yml and generate Ansible files
	@test ! -f infra.yml || { echo "infra.yml already exists. Remove it first."; exit 1; }
	@cp infra.yml.example infra.yml
	@echo "Copied infra.yml.example -> infra.yml"
	@echo "Edit infra.yml, then run: make sync && make apply"

# ── Setup ─────────────────────────────────────────────────
init: install-hooks ## Initial setup: install all dependencies
	ansible-galaxy collection install -r requirements.yml
	pip install --user --break-system-packages pyyaml pytest molecule ruff
	@echo "---"
	@echo "Also install system packages: ansible-lint yamllint shellcheck"
	@echo "  Arch:   pacman -S ansible-lint yamllint shellcheck"
	@echo "  Debian: apt install ansible-lint yamllint shellcheck"

install-hooks: ## Install git pre-commit hooks
	@mkdir -p .git/hooks
	@cp scripts/hooks/pre-commit .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Git hooks installed. Use --no-verify to bypass."

# ── Help ──────────────────────────────────────────────────
help: ## Show this help
	@echo ""
	@echo "  AnKLuMe — Infrastructure Compartmentalization"
	@echo ""
	@echo "  GETTING STARTED:"
	@echo "    make init        Install Ansible dependencies"
	@echo "    make quickstart  Copy example infra.yml and sync"
	@echo "    make guide       Interactive step-by-step tutorial"
	@echo ""
	@echo "  ALL TARGETS:"
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "    \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

.PHONY: sync sync-dry sync-clean console ollama-dev lint lint-yaml lint-ansible lint-shell \
        lint-python check syntax apply apply-infra apply-provision \
        apply-base apply-limit apply-images apply-llm apply-stt apply-ai \
        export-images \
        nftables nftables-deploy \
        snapshot snapshot-domain restore \
        restore-domain snapshot-delete snapshot-list \
        rollback rollback-list rollback-cleanup \
        test test-generator test-roles test-role \
        test-sandboxed test-sandboxed-role runner-create runner-destroy \
        ai-test ai-test-role ai-develop ai-switch \
        mine-experiences ai-improve \
        agent-runner-setup agent-fix agent-develop \
        apply-code-sandbox \
        flush upgrade import-infra \
        matrix-coverage matrix-generate \
        telemetry-on telemetry-off telemetry-status telemetry-clear telemetry-report \
        file-copy backup restore-backup \
        portal-open portal-push portal-pull portal-list \
        disp \
        golden-create golden-derive golden-publish golden-list \
        mcp-list mcp-call \
        apply-tor apply-print \
        dead-code call-graph dep-graph code-graph \
        audit audit-json smoke \
        scenario-test scenario-test-best scenario-test-bad scenario-list \
        clipboard-to clipboard-from domain-exec desktop-config dashboard \
        export-app export-list export-remove \
        guide quickstart init install-hooks help
