# Static Code Analysis

anklume provides static code analysis tools for dead code detection,
call graph generation, and module dependency visualization.

## Quick start

```bash
anklume dev graph --type dead    # Dead code detection (Python + Shell)
anklume dev graph --type call   # Python call graph (DOT + SVG)
anklume dev graph --type dep    # Python module dependency graph (SVG)
anklume dev graph --type code   # Run all analysis tools
```

## Tools

### Dead code detection (`anklume dev graph --type dead`)

Detects unused code across Python and Shell files:

- **Python**: [vulture](https://github.com/jendrikseipp/vulture)
  scans `scripts/` and `tests/` for unused functions, variables,
  imports, and classes. Uses `--min-confidence 80` to reduce false
  positives.
- **Shell**: [ShellCheck](https://www.shellcheck.net/) SC2034 rule
  detects unused variables in `scripts/*.sh`.

Findings are **informational** — vulture may report false positives
for pytest fixtures, dynamically used functions, and abstract method
parameters. Review findings manually before removing code.

### Call graph (`anklume dev graph --type call`)

Generates a call graph of Python functions in `scripts/`. Output is
saved to `reports/call-graph.dot` (GraphViz DOT format) and
`reports/call-graph.svg` (if graphviz is installed).

Uses [pyan3](https://github.com/Technologicat/pyan) when available,
with an AST-based fallback for compatibility with newer Python versions.

### Dependency graph (`anklume dev graph --type dep`)

Generates a module dependency graph using
[pydeps](https://github.com/thebjorn/pydeps). Output is saved to
`reports/dep-graph.svg`. Requires graphviz.

## Dependencies

| Tool | Install | Required for |
|------|---------|-------------|
| vulture | `pip install vulture` | `anklume dev graph --type dead` |
| shellcheck | `apt install shellcheck` | `anklume dev graph --type dead` (shell section) |
| pyan3 | `pip install pyan3` | `anklume dev graph --type call` (optional, AST fallback available) |
| pydeps | `pip install pydeps` | `anklume dev graph --type dep` |
| graphviz | `apt install graphviz` | SVG output for `anklume dev graph --type call` and `anklume dev graph --type dep` |

The script checks for each tool before use and provides clear
installation instructions if missing.

## Output

Reports are generated in the `reports/` directory (gitignored):

```
reports/
├── call-graph.dot   # GraphViz DOT source
├── call-graph.svg   # Call graph visualization (if graphviz installed)
└── dep-graph.svg    # Module dependency graph (if graphviz installed)
```

Use `--output-dir` to change the output directory:

```bash
scripts/code-analysis.sh call-graph --output-dir /tmp/my-reports
```

## CI integration

The `dead-code` job runs in CI as an **informational, non-blocking**
check (`continue-on-error: true`). It reports findings without failing
the pipeline, since dead code detection has inherent false positives.

## Script usage

```bash
scripts/code-analysis.sh <subcommand> [options]

Subcommands:
  dead-code   Run dead code detection
  call-graph  Generate Python call graph
  dep-graph   Generate module dependency graph
  all         Run all analysis tools

Options:
  --output-dir DIR   Output directory for reports (default: reports/)
  --help             Show help
```

## Limitations

- **vulture false positives**: pytest fixtures, `__init__` methods,
  and dynamically called functions are often reported as unused.
  Review carefully before removing.
- **pyan3 compatibility**: pyan3 may not work with Python 3.13+.
  The script falls back to AST-based analysis automatically.
- **pydeps**: requires the project to be structured as a Python
  package. May fail on standalone scripts.
- **graphviz**: required for SVG output. Without it, only DOT files
  are generated for call graphs.
