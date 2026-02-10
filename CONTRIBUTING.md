# Contributing to AnKLuMe

## Development workflow

This project follows **spec-driven, test-driven development**:

1. **Spec first**: Update `docs/SPEC.md` or `docs/ARCHITECTURE.md` with the
   intended behavior. If adding a new structural decision, write an ADR.
2. **Tests second**: Write tests that validate the spec:
   - Ansible roles → Molecule tests in `roles/<n>/molecule/`
   - Generator → pytest in `tests/test_generate.py`
3. **Implement third**: Write code until all tests pass.
4. **Validate**: Run `make lint` — this chains all validators:
   - `ansible-lint` (production profile)
   - `yamllint`
   - `shellcheck` (all `.sh` files)
   - `ruff` (all `.py` files)
5. **Test**: Run `make test`.
6. **Commit**: Only when everything passes.

## Code conventions

- **Language**: All code, comments, and documentation in English.
- **Ansible**: See conventions in `CLAUDE.md`.
- **Python**: Standard library + PyYAML only. No external dependencies.
- **Shell**: Must pass `shellcheck` without warnings.
- Keep files under 200 lines.
- Follow existing patterns — read `.claude/skills/incus-ansible/SKILL.md`
  before writing a new role.

## Branching

- `main` is the stable branch.
- Feature branches: `feat/<description>`
- Bug fixes: `fix/<description>`

## Questions?

Open an issue or check `docs/SPEC.md` for the full specification.
