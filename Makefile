.DEFAULT_GOAL := help
SHELL := /bin/bash

# ── PSOT Generator ────────────────────────────────────────
INFRA_SRC := $(if $(wildcard infra/base.yml),infra,infra.yml)

sync: ## Generate/update Ansible files from infra.yml or infra/
	python3 scripts/generate.py $(INFRA_SRC)

sync-dry: ## Preview changes without writing
	python3 scripts/generate.py $(INFRA_SRC) --dry-run

sync-clean: ## Remove orphan files without confirmation
	python3 scripts/generate.py $(INFRA_SRC) --clean-orphans

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

# ── Apply ─────────────────────────────────────────────────
apply: ## Apply full infrastructure + provisioning
	ansible-playbook site.yml

apply-infra: ## Apply infrastructure only (networks, projects, instances)
	ansible-playbook site.yml --tags infra

apply-provision: ## Apply provisioning only (packages, services)
	ansible-playbook site.yml --tags provision

apply-base: ## Apply base_system only
	ansible-playbook site.yml --tags base

apply-limit: ## Apply a single domain (G=<group>)
	ansible-playbook site.yml --limit $(G)

apply-images: ## Pre-download OS images to local cache
	ansible-playbook site.yml --tags images

apply-llm: ## Apply LLM roles (Ollama + Open WebUI)
	ansible-playbook site.yml --tags llm

apply-stt: ## Apply STT role (Speaches + faster-whisper)
	ansible-playbook site.yml --tags stt

apply-ai: ## Apply AI tools roles (Ollama + WebUI + LobeChat + OpenCode)
	ansible-playbook site.yml --tags llm,stt,lobechat,opencode

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

# ── Testing ───────────────────────────────────────────────
test: test-generator test-roles ## Run all tests

test-generator: ## Run generator pytest tests
	python3 -m pytest tests/ -v

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
	pip install --user pyyaml pytest molecule ruff
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

.PHONY: sync sync-dry sync-clean lint lint-yaml lint-ansible lint-shell \
        lint-python check syntax apply apply-infra apply-provision \
        apply-base apply-limit apply-images apply-llm apply-stt apply-ai \
        export-images \
        nftables nftables-deploy \
        snapshot snapshot-domain restore \
        restore-domain snapshot-delete snapshot-list \
        test test-generator test-roles test-role \
        test-sandboxed test-sandboxed-role runner-create runner-destroy \
        ai-test ai-test-role ai-develop ai-switch \
        mine-experiences ai-improve \
        agent-runner-setup agent-fix agent-develop \
        flush upgrade import-infra \
        matrix-coverage matrix-generate \
        guide quickstart init install-hooks help
