# AI-Assisted Testing and Development

AnKLuMe supports optional AI-assisted test fixing and autonomous
development. An LLM backend analyzes test failures, proposes fixes,
and optionally applies them — all within the project's safety guardrails.

## Modes

| Mode | Value | Backend | Description |
|------|-------|---------|-------------|
| None | `none` | — | Standard Molecule tests, no AI (default) |
| Local | `local` | Ollama | Local LLM via Ollama API |
| Remote | `remote` | Claude API | Cloud API with Anthropic key |
| Claude Code | `claude-code` | CLI | Claude Code in autonomous mode |
| Aider | `aider` | CLI | Aider connected to Ollama or API |

Set the mode via environment variable or config file:

```bash
export ANKLUME_AI_MODE=local
make ai-test
```

## Quick start

### Test + fix mode

Run Molecule tests and let an LLM fix failures:

```bash
# Dry-run (default): show proposed fixes without applying
make ai-test AI_MODE=local

# Apply fixes automatically
make ai-test AI_MODE=local DRY_RUN=false

# Test a single role
make ai-test-role R=base_system AI_MODE=claude-code
```

### Development mode

Let an LLM implement a task autonomously:

```bash
# Dry-run: show what the LLM would do
make ai-develop TASK="Add a monitoring role" AI_MODE=claude-code

# Apply changes and run tests
make ai-develop TASK="Add a monitoring role" AI_MODE=claude-code DRY_RUN=false
```

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANKLUME_AI_MODE` | `none` | AI backend selection |
| `ANKLUME_AI_DRY_RUN` | `true` | Show fixes without applying |
| `ANKLUME_AI_AUTO_PR` | `false` | Auto-create PRs on success |
| `ANKLUME_AI_MAX_RETRIES` | `3` | Max fix attempts per role |
| `ANKLUME_AI_OLLAMA_URL` | `http://homelab-ai:11434` | Ollama API URL |
| `ANKLUME_AI_OLLAMA_MODEL` | `qwen2.5-coder:32b` | Ollama model |
| `ANTHROPIC_API_KEY` | — | API key for remote mode |
| `ANKLUME_AI_LOG_DIR` | `logs` | Session log directory |

### Config file (optional)

Create `anklume.conf.yml` at the project root:

```yaml
ai:
  mode: none
  ollama_url: "http://homelab-ai:11434"
  ollama_model: "qwen2.5-coder:32b"
  anthropic_api_key: ""
  max_retries: 3
  auto_pr: false
  dry_run: true
```

Environment variables take precedence over the config file.

## Safety guardrails

AnKLuMe defaults to maximum safety:

| Guardrail | Default | Description |
|-----------|---------|-------------|
| `dry_run` | `true` | LLM proposes fixes, human applies |
| `auto_pr` | `false` | Human creates the PR manually |
| Max retries | 3 | Prevents infinite fix loops |
| Session logging | Always | Full transcript for audit |
| Sandbox | Phase 12 | Incus-in-Incus isolates execution |

### Progressive trust model

1. Start with `dry_run=true` — review every proposed fix
2. Enable `dry_run=false` when confident in the backend
3. Enable `auto_pr=true` for fully autonomous workflows
4. Use the Incus-in-Incus sandbox (Phase 12) for isolation

## Backend setup

### Local (Ollama)

Requires an Ollama instance accessible from the admin container:

```bash
# Verify connectivity
curl http://homelab-ai:11434/api/tags

# Set mode
export ANKLUME_AI_MODE=local
export ANKLUME_AI_OLLAMA_URL=http://homelab-ai:11434
export ANKLUME_AI_OLLAMA_MODEL=qwen2.5-coder:32b
```

### Remote (Claude API)

Requires an Anthropic API key:

```bash
export ANKLUME_AI_MODE=remote
export ANTHROPIC_API_KEY=sk-ant-...
```

### Claude Code CLI

Requires Claude Code installed:

```bash
npm install -g @anthropic-ai/claude-code
export ANKLUME_AI_MODE=claude-code
```

Claude Code operates directly on files (no patch extraction needed).
It reads CLAUDE.md for project conventions.

### Aider

Requires Aider installed with an Ollama backend:

```bash
pip install aider-chat
export ANKLUME_AI_MODE=aider
export ANKLUME_AI_OLLAMA_MODEL=qwen2.5-coder:32b
```

## Session logs

Every AI session produces a log file in `logs/`:

```
logs/
├── ai-test-20260212-143022.log          # Session transcript
├── ai-test-20260212-143022-base_system-molecule.log  # Test output
├── ai-test-20260212-143022-base_system-context.txt   # LLM context
└── ai-test-20260212-143022-response.patch            # LLM response
```

Logs are not committed to git (add `logs/` to `.gitignore`).

## Makefile targets

| Target | Description |
|--------|-------------|
| `make ai-test` | Run tests + AI fix (all roles) |
| `make ai-test-role R=<name>` | Test + AI fix for one role |
| `make ai-develop TASK="..."` | Autonomous development |

Override AI settings via Make variables:

```bash
make ai-test AI_MODE=local DRY_RUN=false MAX_RETRIES=5
```

## How it works

### Test loop (ai-test-loop.sh)

```
1. Run molecule test for each role
2. If test passes → next role
3. If test fails → build context (log + source code)
4. Send context to LLM backend
5. LLM returns a fix (patch or direct file modification)
6. Apply fix (if not dry-run)
7. Re-test
8. Loop until pass or max retries
9. Commit successful fixes
10. Optionally create PR
```

### Development (ai-develop.sh)

```
1. Create feature branch (feature/<task-slug>)
2. Build project context (CLAUDE.md + ROADMAP.md + task)
3. Send to LLM backend
4. LLM implements the task
5. Run test suite (pytest + molecule)
6. If tests fail → retry (send failure context)
7. Loop until pass or max retries
8. Commit and optionally create PR
```

## Troubleshooting

### "AI_MODE=none: no automatic fix attempted"

Expected behavior when no AI backend is configured. Set `ANKLUME_AI_MODE`
to a valid backend.

### Ollama connection refused

Verify the Ollama URL is reachable from where you run `make ai-test`:

```bash
curl http://homelab-ai:11434/api/tags
```

If running inside the admin container, ensure the homelab domain is
accessible (requires admin→homelab network access).

### Claude Code not found

Install globally:

```bash
npm install -g @anthropic-ai/claude-code
```

### Patch does not apply cleanly

The LLM-generated patch may not match the current file state exactly.
In dry-run mode, the patch is saved for manual review. Check:

```bash
cat logs/ai-test-*-response.patch
```
