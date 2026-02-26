# Interactive Onboarding Guide

anklume includes a step-by-step interactive guide that walks you through
setting up your infrastructure from scratch.

## Usage

```bash
anklume guide              # Start from step 1
anklume guide STEP=5       # Resume from step 5
anklume guide AUTO=1       # Non-interactive CI mode
```

Or run the script directly:

```bash
scripts/guide.sh
scripts/guide.sh --step 5
scripts/guide.sh --auto
```

## Steps

| Step | Name | Description |
|------|------|-------------|
| 1 | Prerequisites | Checks required tools (incus, ansible, python3, git, make) |
| 2 | Use case | Select a pre-built example (student, teacher, pro, custom) |
| 3 | infra.yml | Copy the example and optionally edit it |
| 4 | Generate | Run `anklume sync` to create Ansible files |
| 5 | Validate | Run linters and syntax checks |
| 6 | Apply | Create Incus infrastructure (`anklume domain apply`) |
| 7 | Verify | List running instances and networks |
| 8 | Snapshot | Create an initial snapshot for rollback |
| 9 | Next steps | Links to advanced features and documentation |

## Auto mode

The `--auto` flag runs all steps non-interactively:

- Selects option 1 for all prompts
- Skips steps requiring a live Incus daemon (steps 6-8)
- Exits immediately on any failure
- Useful for CI smoke testing

## Resume support

Each step is independent. If the guide exits or you press Ctrl+C,
resume from where you left off:

```bash
anklume guide STEP=4    # Resume from step 4
```

## Troubleshooting

### "incus not found"

Install Incus following the upstream documentation:
https://linuxcontainers.org/incus/docs/main/installing/

### "anklume sync failed"

Check `infra.yml` for syntax errors. Common issues:
- Duplicate machine names
- Duplicate subnet IDs
- IPs outside the declared subnet

Run `anklume sync --dry-run` to preview without writing.

### "Cannot connect to Incus"

Steps 6-8 require a running Incus daemon. Either:
- Run from a machine with Incus installed and initialized
- Run from the admin container with the Incus socket mounted
- Skip these steps and run `anklume domain apply` manually later

### Editor not opening

The guide uses `$EDITOR` or `$VISUAL` (defaults to `vi`).
Set your preferred editor:

```bash
export EDITOR=nano
anklume guide STEP=3
```
