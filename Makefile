.DEFAULT_GOAL := help
SHELL := /bin/bash

# ── PSOT Generator ────────────────────────────────────────
sync: ## Generate/update Ansible files from infra.yml
	python3 scripts/generate.py infra.yml

sync-dry: ## Preview changes without writing
	python3 scripts/generate.py infra.yml --dry-run

sync-clean: ## Remove orphan files without confirmation
	python3 scripts/generate.py infra.yml --clean-orphans

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

apply-llm: ## Apply LLM roles (Ollama + Open WebUI)
	ansible-playbook site.yml --tags llm

apply-stt: ## Apply STT role (Speaches + faster-whisper)
	ansible-playbook site.yml --tags stt

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
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: sync sync-dry sync-clean lint lint-yaml lint-ansible lint-shell \
        lint-python check syntax apply apply-infra apply-provision \
        apply-base apply-limit apply-llm apply-stt nftables nftables-deploy \
        snapshot snapshot-domain restore \
        restore-domain snapshot-delete snapshot-list \
        test test-generator test-roles test-role \
        test-sandboxed test-sandboxed-role runner-create runner-destroy \
        ai-test ai-test-role ai-develop \
        init install-hooks help
