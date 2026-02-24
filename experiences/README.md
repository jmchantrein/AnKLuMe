# Experience Library

Structured knowledge extracted from anklume's development history.
Used by AI-assisted tools to resolve known issues without LLM cost.

## Directory structure

```
experiences/
├── fixes/                 # Fix patterns from git history
│   ├── ansible-lint.yml   # Linting fix patterns
│   ├── molecule.yml       # Molecule test fix patterns
│   ├── incus-cli.yml      # Incus CLI quirks and workarounds
│   └── generator.yml      # PSOT generator fix patterns
├── patterns/              # Reusable implementation patterns
│   ├── reconciliation.yml # 6-step reconciliation pattern
│   ├── role-structure.yml # Ansible role conventions
│   └── testing.yml        # Test patterns (pytest, Molecule)
└── decisions/             # Promoted architectural decisions
    └── architecture.yml   # Key choices with rationale
```

## Entry format

Each entry follows a consistent YAML schema:

```yaml
- id: FIX-LINT-001
  category: ansible-lint
  problem: "Description of what went wrong"
  solution: "What was done to fix it"
  source_commit: "abc1234"
  files_affected: ["path/to/file"]
  prevention: "How to avoid this in the future"
```

## Usage

The `search_experiences()` function in `scripts/ai-test-loop.sh`
searches these files before calling an LLM, saving time and cost
on known issues.

Run `scripts/mine-experiences.py` to extract new entries from
recent git history.

## Adding entries

1. Manually: edit the relevant YAML file directly
2. Automatically: `make mine-experiences` scans git history
3. After AI fixes: successful fixes are candidates for new entries
