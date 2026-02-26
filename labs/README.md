# Educational Labs

anklume ships with guided labs for learning system administration,
networking, and security concepts in isolated, reproducible environments.

## Directory structure

Each lab is a self-contained directory:

```
labs/
  lab-schema.yml              # Validation schema for lab.yml
  01-first-deploy/
    lab.yml                   # Metadata: title, difficulty, duration, steps
    infra.yml                 # Lab-specific infrastructure definition
    steps/
      01-create-infra.md      # Step instructions (ordered)
      02-verify.md
      03-cleanup.md
    solution/
      commands.sh             # Reference commands for each step
  02-network-isolation/
    ...
```

## lab.yml format

```yaml
title: "Lab title"
description: "What the student will learn"
difficulty: beginner          # beginner | intermediate | advanced
duration: "30m"               # Estimated time (e.g., 15m, 1h)
prerequisites: []             # List of prior labs or knowledge
objectives:
  - "Objective 1"
  - "Objective 2"
steps:
  - id: "01"
    title: "Step title"
    instruction_file: "steps/01-step-name.md"
    hint: "Optional hint text"
    validation: "incus list --format csv | grep -q RUNNING"
```

## Make targets

```bash
anklume lab list              # List available labs
anklume lab start 01        # Start lab 01, display first step
anklume lab check 01        # Validate current step
anklume lab hint 01        # Show hint for current step
anklume lab reset 01        # Reset lab to initial state
anklume lab solution 01     # Show solution (marks as assisted)
```

## Progress tracking

Lab progress is stored in `~/.anklume/labs/<lab-id>/progress.yml`:

```yaml
current_step: 2
started_at: "2026-02-25T10:00:00"
assisted: false
completed_steps:
  - "01"
  - "02"
```

## Writing new labs

1. Create a numbered directory under `labs/` (e.g., `04-gpu-passthrough/`)
2. Write `lab.yml` following the schema in `lab-schema.yml`
3. Create a lab-specific `infra.yml`
4. Write ordered step files in `steps/`
5. Add reference commands in `solution/commands.sh`
6. Run `anklume lab list` to verify detection
