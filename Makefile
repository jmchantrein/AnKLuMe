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
	@if compgen -G "scripts/*.sh" > /dev/null; then \
		shellcheck scripts/*.sh; \
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

apply-limit: ## Apply a single domain (G=<group>)
	ansible-playbook site.yml --limit $(G)

# ── Snapshots ─────────────────────────────────────────────
snap: ## Create snapshot (I=<instance|self> [S=<name>])
	@bash scripts/snap.sh create $(I) $(S)

snap-restore: ## Restore snapshot (I=<instance|self> S=<snap-name>)
	@bash scripts/snap.sh restore $(I) $(S)

snap-list: ## List snapshots ([I=<instance|self>])
	@bash scripts/snap.sh list $(I)

snap-delete: ## Delete snapshot (I=<instance|self> S=<snap-name>)
	@bash scripts/snap.sh delete $(I) $(S)

# ── Testing ───────────────────────────────────────────────
test: test-generator test-roles ## Run all tests

test-generator: ## Run generator pytest tests
	python3 -m pytest tests/ -v

test-roles: ## Run Molecule tests for all roles
	@for role in roles/incus_*/; do \
		echo "=== Testing $$role ==="; \
		(cd "$$role" && molecule test) || exit 1; \
	done

# ── Setup ─────────────────────────────────────────────────
init: ## Initial setup: install all dependencies
	ansible-galaxy collection install -r requirements.yml
	pip install --user pyyaml pytest molecule ruff
	@echo "---"
	@echo "Also install system packages: ansible-lint yamllint shellcheck"
	@echo "  Arch:   pacman -S ansible-lint yamllint shellcheck"
	@echo "  Debian: apt install ansible-lint yamllint shellcheck"

# ── Help ──────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: sync sync-dry sync-clean lint lint-yaml lint-ansible lint-shell \
        lint-python check syntax apply apply-infra apply-provision \
        apply-limit snap snap-restore snap-list snap-delete \
        test test-generator test-roles init help
