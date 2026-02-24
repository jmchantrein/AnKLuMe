# Claude Code Workflow

How to work on anklume with Claude Code effectively.

## Starting a session

Claude Code automatically reads `CLAUDE.md` at session start. For deeper
context on a specific task, load the relevant doc:

```
@docs/SPEC.md           # Full spec — formats, roles, architecture
@docs/ARCHITECTURE.md   # ADRs — decisions you must not override
@docs/ROADMAP.md        # What to work on next
```

## Development cycle (spec-driven, test-driven)

1. **Check the spec**: Before implementing anything, read the relevant
   section of SPEC.md. If the spec is missing or unclear, update it first.

2. **Write tests**: Before writing code, write the tests:
   - Roles → Molecule test (`roles/<n>/molecule/default/`)
   - Generator → pytest (`tests/test_generate.py`)

3. **Implement**: Write code until tests pass.

4. **Validate**: Run `make lint` (chains all validators).

5. **Review**: Invoke the reviewer agent:
   ```
   @.claude/agents/reviewer.md Review the changes in roles/incus_networks/
   ```

6. **Commit**: Only when `make lint && make test` pass.

## Using agents

### Architect
For structural decisions, design questions, new ADRs:
```
@.claude/agents/architect.md Should we split incus_instances into
separate roles for LXC and VM, or keep them together?
```

### Reviewer
Before committing, for quality checks:
```
@.claude/agents/reviewer.md Review all changes since last commit
```

## Using skills

The `incus-ansible` skill is auto-loaded when working on files in `roles/`.
It provides the reconciliation pattern template and common Incus commands.

## Tips

- **Keep context focused**: Load only what's relevant to the current task.
- **Use subagents for distinct tasks**: Avoid context pollution.
- **Run `make lint` frequently**: Catch issues early.
- **Check ROADMAP.md**: Know what phase you're in.
