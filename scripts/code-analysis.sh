#!/usr/bin/env bash
# code-analysis.sh — Static code analysis for anklume
# Usage: scripts/code-analysis.sh <subcommand> [options]
#
# Subcommands:
#   dead-code   Run dead code detection (vulture for Python)
#   call-graph  Generate Python call graph (DOT + SVG)
#   dep-graph   Generate Python module dependency graph (SVG)
#   all         Run all analysis tools
#
# Options:
#   --output-dir DIR   Output directory for reports (default: reports/)
#   --help             Show this help

set -euo pipefail

# ── Globals ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/reports"
SUBCOMMAND=""

# ── Argument parsing ────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        dead-code|call-graph|dep-graph|all)
            SUBCOMMAND="$1"
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            sed -n '2,/^$/{ s/^# //; s/^#$//; p }' "$0"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            echo "Usage: $0 <dead-code|call-graph|dep-graph|all> [--output-dir DIR]" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$SUBCOMMAND" ]]; then
    echo "ERROR: Subcommand required." >&2
    echo "Usage: $0 <dead-code|call-graph|dep-graph|all> [--output-dir DIR]" >&2
    exit 1
fi

# ── Helpers ──────────────────────────────────────────────
check_command() {
    local cmd="$1"
    local pkg="$2"
    if ! command -v "$cmd" &>/dev/null; then
        echo "WARNING: $cmd not found. Install with: $pkg" >&2
        return 1
    fi
    return 0
}

ensure_output_dir() {
    mkdir -p "$OUTPUT_DIR"
}

# ── Dead code detection ────────────────────────────────
run_dead_code() {
    echo "=== Dead Code Detection ==="
    local found_tool=false
    local rc=0

    # Python dead code via vulture (try command, then python -m)
    local vulture_cmd=""
    if command -v vulture &>/dev/null; then
        vulture_cmd="vulture"
    elif python3 -m vulture --version &>/dev/null 2>&1; then
        vulture_cmd="python3 -m vulture"
    fi

    if [[ -n "$vulture_cmd" ]]; then
        found_tool=true
        echo ""
        echo "--- Python (vulture) ---"
        local py_files
        py_files=$(find "$PROJECT_DIR/scripts" "$PROJECT_DIR/tests" \
            -name '*.py' -not -path '*/__pycache__/*' 2>/dev/null || true)

        if [[ -n "$py_files" ]]; then
            # Use whitelist to reduce false positives on test fixtures
            # vulture exits 1 when it finds dead code (informational, not an error)
            # shellcheck disable=SC2086
            $vulture_cmd $py_files --min-confidence 80 || rc=$?
            if [[ $rc -eq 0 ]]; then
                echo "No dead code found."
            else
                echo ""
                echo "Note: vulture may report false positives (e.g., pytest fixtures,"
                echo "dynamically used functions). Review findings manually."
                # Reset rc — dead code findings are informational
                rc=0
            fi
        else
            echo "No Python files found."
        fi
    fi

    # Shell unused variables via shellcheck (SC2034)
    if check_command shellcheck "apt install shellcheck"; then
        found_tool=true
        echo ""
        echo "--- Shell (shellcheck SC2034 — unused variables) ---"
        local sh_files
        sh_files=$(find "$PROJECT_DIR/scripts" -name '*.sh' 2>/dev/null || true)

        if [[ -n "$sh_files" ]]; then
            local sc_output
            # shellcheck disable=SC2086
            sc_output=$(shellcheck --include=SC2034 $sh_files 2>&1 || true)
            if [[ -n "$sc_output" ]]; then
                echo "$sc_output"
            else
                echo "No unused shell variables found."
            fi
        else
            echo "No shell scripts found."
        fi
    fi

    if [[ -z "$vulture_cmd" ]] && ! check_command vulture "pip install vulture" 2>/dev/null; then
        echo "WARNING: vulture not found. Install with: pip install vulture" >&2
    fi

    if [[ "$found_tool" == "false" ]]; then
        echo "ERROR: No analysis tools available." >&2
        echo "Install vulture: pip install vulture" >&2
        return 1
    fi

    echo ""
    echo "Dead code analysis complete."
    return $rc
}

# ── Call graph generation ──────────────────────────────
run_call_graph() {
    echo "=== Call Graph Generation ==="
    ensure_output_dir

    local py_files
    py_files=$(find "$PROJECT_DIR/scripts" -name '*.py' \
        -not -path '*/__pycache__/*' 2>/dev/null || true)

    if [[ -z "$py_files" ]]; then
        echo "No Python files found in scripts/."
        return 0
    fi

    local dot_file="${OUTPUT_DIR}/call-graph.dot"
    local generated=false

    # Try pyan3 first (best output quality)
    if check_command pyan3 "pip install pyan3"; then
        echo "Generating call graph via pyan3..."
        # shellcheck disable=SC2086
        if pyan3 $py_files --dot 2>/dev/null > "$dot_file" && [[ -s "$dot_file" ]]; then
            generated=true
        else
            echo "WARNING: pyan3 failed (may be incompatible with Python version)." >&2
            echo "Falling back to AST-based analysis." >&2
        fi
    fi

    # Fallback: AST-based call graph via inline Python
    if [[ "$generated" == "false" ]]; then
        echo "Generating call graph via AST analysis..."
        # shellcheck disable=SC2086
        python3 - "$dot_file" $py_files <<'PYEOF'
import ast
import os
import sys

dot_file = sys.argv[1]
py_files = sys.argv[2:]

edges = []
functions = set()

for filepath in py_files:
    module = os.path.basename(filepath).replace(".py", "")
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read(), filename=filepath)
    except SyntaxError:
        continue

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = f"{module}.{node.name}"
            functions.add(func_name)
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    callee = None
                    if isinstance(child.func, ast.Name):
                        callee = child.func.id
                    elif isinstance(child.func, ast.Attribute):
                        callee = child.func.attr
                    if callee:
                        edges.append((func_name, callee))

with open(dot_file, "w") as f:
    f.write("digraph call_graph {\n")
    f.write("    rankdir=LR;\n")
    f.write("    node [shape=box, style=filled, fillcolor=lightblue];\n")
    for func in sorted(functions):
        f.write(f'    "{func}";\n')
    for src, dst in sorted(set(edges)):
        f.write(f'    "{src}" -> "{dst}";\n')
    f.write("}\n")
PYEOF
        generated=true
    fi

    echo "DOT file: $dot_file"

    # Convert to SVG if graphviz is available
    if check_command dot "apt install graphviz"; then
        local svg_file="${OUTPUT_DIR}/call-graph.svg"
        dot -Tsvg "$dot_file" -o "$svg_file"
        echo "SVG file: $svg_file"
    else
        echo "Skipping SVG conversion (graphviz not installed)."
    fi

    echo ""
    echo "Call graph generation complete."
}

# ── Dependency graph generation ────────────────────────
run_dep_graph() {
    echo "=== Dependency Graph Generation ==="
    ensure_output_dir

    if ! check_command pydeps "pip install pydeps"; then
        return 1
    fi

    if ! check_command dot "apt install graphviz"; then
        echo "WARNING: graphviz required for pydeps SVG output." >&2
        echo "Skipping dependency graph (install with: apt install graphviz)." >&2
        return 1
    fi

    local main_script="${PROJECT_DIR}/scripts/generate.py"
    if [[ ! -f "$main_script" ]]; then
        echo "No generate.py found — skipping dependency graph."
        return 0
    fi

    local svg_file="${OUTPUT_DIR}/dep-graph.svg"
    echo "Generating module dependency graph..."
    pydeps "$main_script" \
        --no-show \
        --max-bacon=2 \
        -o "$svg_file" \
        -T svg 2>/dev/null || {
        echo "WARNING: pydeps failed. This may require the project to be a proper Python package." >&2
        echo "Skipping dependency graph." >&2
        return 1
    }

    echo "SVG file: $svg_file"
    echo ""
    echo "Dependency graph generation complete."
}

# ── Main dispatch ──────────────────────────────────────
case "$SUBCOMMAND" in
    dead-code)
        run_dead_code
        ;;
    call-graph)
        run_call_graph
        ;;
    dep-graph)
        run_dep_graph
        ;;
    all)
        overall_rc=0
        run_dead_code || overall_rc=$?
        echo ""
        run_call_graph || overall_rc=$?
        echo ""
        run_dep_graph || overall_rc=$?
        exit $overall_rc
        ;;
esac
