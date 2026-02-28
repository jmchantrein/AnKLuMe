"""Tests for the CLI dependency graph module (anklume dev cli-tree --format deps)."""

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("typer")

from scripts.cli._cli_deps import (  # noqa: E402
    build_dep_graph,
    has_cycle,
    load_deps,
    merge_llm_deps,
    render_deps_json,
    render_deps_mermaid,
)
from scripts.cli._cli_tree import introspect_app  # noqa: E402


@pytest.fixture()
def cli_tree():
    """Introspect the live anklume Typer app."""
    from scripts.cli import app

    return introspect_app(app)


@pytest.fixture()
def resources():
    """Load resource flow declarations."""
    return load_deps()


@pytest.fixture()
def dep_graph(cli_tree, resources):
    """Build the full dependency graph."""
    return build_dep_graph(cli_tree, resources)


# ── Resource YAML validation ─────────────────────────────


class TestResourceYAML:
    def test_loads_dict(self, resources):
        assert isinstance(resources, dict)
        assert len(resources) > 0

    def test_each_resource_has_description(self, resources):
        for name, res in resources.items():
            assert "description" in res, f"Resource {name} missing description"

    def test_each_resource_has_producers_and_consumers(self, resources):
        for name, res in resources.items():
            assert "producers" in res, f"Resource {name} missing producers"
            assert "consumers" in res, f"Resource {name} missing consumers"
            assert isinstance(res["producers"], list)
            assert isinstance(res["consumers"], list)

    def test_yaml_file_is_valid(self):
        deps_path = Path(__file__).resolve().parent.parent / "scripts" / "cli" / "_cli_deps.yml"
        with open(deps_path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)
        assert "resources" in data


# ── Dependency graph ─────────────────────────────────────


class TestDepGraph:
    def test_graph_is_dict(self, dep_graph):
        assert isinstance(dep_graph, dict)
        assert len(dep_graph) > 0

    def test_no_cycles(self, dep_graph):
        assert not has_cycle(dep_graph), "Dependency graph contains a cycle"

    def test_sync_depends_on_quickstart_or_import(self, dep_graph):
        sync_deps = {d["command"] for d in dep_graph.get("sync", {}).get("depends_on", [])}
        assert sync_deps & {"setup.quickstart", "setup.import"}, (
            "sync should depend on setup.quickstart or setup.import"
        )

    def test_domain_apply_depends_on_sync(self, dep_graph):
        apply_deps = {d["command"] for d in dep_graph.get("domain.apply", {}).get("depends_on", [])}
        assert "sync" in apply_deps, "domain.apply should depend on sync"

    def test_network_deploy_depends_on_rules(self, dep_graph):
        deploy_deps = {
            d["command"] for d in dep_graph.get("network.deploy", {}).get("depends_on", [])
        }
        assert "network.rules" in deploy_deps, "network.deploy should depend on network.rules"

    def test_snapshot_restore_depends_on_create(self, dep_graph):
        restore_deps = {
            d["command"] for d in dep_graph.get("snapshot.restore", {}).get("depends_on", [])
        }
        assert "snapshot.create" in restore_deps

    def test_each_entry_has_required_keys(self, dep_graph):
        for cmd, info in dep_graph.items():
            assert "depends_on" in info, f"{cmd} missing depends_on"
            assert "dependents" in info, f"{cmd} missing dependents"

    def test_edges_have_source_field(self, dep_graph):
        for cmd, info in dep_graph.items():
            for dep in info["depends_on"]:
                assert "source" in dep, f"Edge to {cmd} missing source field"
                assert dep["source"] in ("deterministic", "llm")


# ── LLM merge ────────────────────────────────────────────


class TestLLMMerge:
    def test_merge_adds_edges(self, dep_graph):
        original_count = sum(len(v["depends_on"]) for v in dep_graph.values())
        llm_edges = [{"from": "setup.init", "to": "doctor", "reason": "verify setup"}]
        merge_llm_deps(dep_graph, llm_edges)
        new_count = sum(len(v["depends_on"]) for v in dep_graph.values())
        assert new_count == original_count + 1

    def test_merge_marks_source_llm(self, dep_graph):
        merge_llm_deps(dep_graph, [{"from": "sync", "to": "doctor", "reason": "check health"}])
        doctor_deps = dep_graph["doctor"]["depends_on"]
        llm_deps = [d for d in doctor_deps if d["source"] == "llm"]
        assert len(llm_deps) >= 1

    def test_merge_ignores_unknown_commands(self, dep_graph):
        original_count = sum(len(v["depends_on"]) for v in dep_graph.values())
        merge_llm_deps(dep_graph, [{"from": "nonexistent", "to": "sync", "reason": "x"}])
        new_count = sum(len(v["depends_on"]) for v in dep_graph.values())
        assert new_count == original_count

    def test_merge_no_self_loops(self, dep_graph):
        merge_llm_deps(dep_graph, [{"from": "sync", "to": "sync", "reason": "self"}])
        sync_deps = dep_graph["sync"]["depends_on"]
        self_refs = [d for d in sync_deps if d["command"] == "sync"]
        assert len(self_refs) == 0


# ── Mermaid rendering ────────────────────────────────────


class TestMermaid:
    def test_starts_with_graph_lr(self, dep_graph):
        output = render_deps_mermaid(dep_graph)
        assert output.startswith("graph LR")

    def test_contains_known_edge(self, dep_graph):
        output = render_deps_mermaid(dep_graph)
        assert "sync" in output
        assert "domain__apply" in output

    def test_llm_edges_use_dotted_arrows(self, dep_graph):
        merge_llm_deps(dep_graph, [{"from": "sync", "to": "doctor", "reason": "verify"}])
        output = render_deps_mermaid(dep_graph)
        assert "-.->|verify|" in output


# ── JSON rendering ───────────────────────────────────────


class TestJSON:
    def test_valid_json(self, dep_graph):
        output = render_deps_json(dep_graph)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_contains_known_commands(self, dep_graph):
        parsed = json.loads(render_deps_json(dep_graph))
        assert "domain.apply" in parsed
        assert "sync" in parsed

    def test_depends_on_structure(self, dep_graph):
        parsed = json.loads(render_deps_json(dep_graph))
        for _cmd, info in parsed.items():
            assert "depends_on" in info
            assert "dependents" in info
            for dep in info["depends_on"]:
                assert "command" in dep
                assert "resource" in dep
                assert "source" in dep
