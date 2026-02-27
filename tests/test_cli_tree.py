"""Tests for the CLI tree introspection module (anklume dev cli-tree)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("typer")

from scripts.cli._cli_tree import (  # noqa: E402
    introspect_app,
    load_intents,
    render_intent,
    render_json,
    render_mermaid,
)


@pytest.fixture()
def cli_tree():
    """Introspect the live anklume Typer app."""
    from scripts.cli import app

    return introspect_app(app)


# ── introspect_app ─────────────────────────────────────────


class TestIntrospect:
    def test_returns_dict_with_required_keys(self, cli_tree):
        assert "name" in cli_tree
        assert "commands" in cli_tree
        assert "groups" in cli_tree

    def test_name_is_anklume(self, cli_tree):
        assert cli_tree["name"] == "anklume"

    def test_commands_are_list(self, cli_tree):
        assert isinstance(cli_tree["commands"], list)
        assert len(cli_tree["commands"]) > 0

    def test_groups_are_list(self, cli_tree):
        assert isinstance(cli_tree["groups"], list)
        assert len(cli_tree["groups"]) > 0

    def test_known_top_level_commands_present(self, cli_tree):
        names = {c["name"] for c in cli_tree["commands"]}
        for expected in ("sync", "flush", "doctor", "guide"):
            assert expected in names, f"Missing top-level command: {expected}"

    def test_known_groups_present(self, cli_tree):
        names = {g["name"] for g in cli_tree["groups"]}
        for expected in ("domain", "instance", "snapshot", "network"):
            assert expected in names, f"Missing group: {expected}"

    def test_command_has_required_fields(self, cli_tree):
        cmd = cli_tree["commands"][0]
        assert "name" in cmd
        assert "help" in cmd
        assert "hidden" in cmd
        assert "params" in cmd

    def test_group_commands_have_params(self, cli_tree):
        domain = next(g for g in cli_tree["groups"] if g["name"] == "domain")
        apply_cmd = next(c for c in domain["commands"] if c["name"] == "apply")
        assert isinstance(apply_cmd["params"], list)

    def test_param_has_required_fields(self, cli_tree):
        sync = next(c for c in cli_tree["commands"] if c["name"] == "sync")
        assert len(sync["params"]) > 0
        param = sync["params"][0]
        assert "name" in param
        assert "kind" in param
        assert "required" in param


# ── render_mermaid ─────────────────────────────────────────


class TestMermaid:
    def test_starts_with_graph_lr(self, cli_tree):
        output = render_mermaid(cli_tree)
        assert output.startswith("graph LR")

    def test_contains_root_node(self, cli_tree):
        output = render_mermaid(cli_tree)
        assert 'root(["anklume"])' in output

    def test_contains_top_level_commands(self, cli_tree):
        output = render_mermaid(cli_tree)
        assert 'root --> sync["sync"]' in output
        assert 'root --> doctor["doctor"]' in output

    def test_contains_group_edges(self, cli_tree):
        output = render_mermaid(cli_tree)
        assert 'root --> domain["domain"]' in output
        assert 'domain --> domain_apply["apply"]' in output

    def test_hidden_filtered_when_show_hidden_false(self, cli_tree):
        hidden_groups = {g["name"] for g in cli_tree["groups"] if g["hidden"]}
        if not hidden_groups:
            pytest.skip("No hidden groups in current mode")
        output = render_mermaid(cli_tree, show_hidden=False)
        for name in hidden_groups:
            assert f'root --> {name.replace("-", "_")}[' not in output

    def test_show_hidden_includes_all_groups(self, cli_tree):
        all_names = {g["name"] for g in cli_tree["groups"]}
        output = render_mermaid(cli_tree, show_hidden=True)
        for name in all_names:
            assert name in output

    def test_arguments_shown_as_asymmetric_nodes(self, cli_tree):
        output = render_mermaid(cli_tree, show_hidden=True)
        # runner command has an ACTION argument
        assert ">ACTION]" in output


# ── render_json ────────────────────────────────────────────


class TestJSON:
    def test_valid_json(self, cli_tree):
        output = render_json(cli_tree)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_json_structure(self, cli_tree):
        parsed = json.loads(render_json(cli_tree))
        assert "name" in parsed
        assert "commands" in parsed
        assert "groups" in parsed

    def test_json_hidden_filtered_by_default(self, cli_tree):
        parsed = json.loads(render_json(cli_tree, show_hidden=False))
        group_names = {g["name"] for g in parsed["groups"]}
        # dev is hidden by default in its Typer definition
        hidden_in_tree = {
            g["name"] for g in cli_tree["groups"] if g["hidden"]
        }
        for h in hidden_in_tree:
            assert h not in group_names

    def test_json_hidden_included_with_flag(self, cli_tree):
        parsed = json.loads(render_json(cli_tree, show_hidden=True))
        group_names = {g["name"] for g in parsed["groups"]}
        assert "dev" in group_names


# ── render_intent ──────────────────────────────────────────


class TestIntent:
    def test_starts_with_graph_lr(self, cli_tree):
        output = render_intent(cli_tree)
        assert output.startswith("graph LR")

    def test_contains_decision_node(self, cli_tree):
        output = render_intent(cli_tree)
        assert "What do you want to do?" in output

    def test_contains_intent_categories(self, cli_tree):
        output = render_intent(cli_tree)
        assert "Deploy & Configure" in output
        assert "Manage Resources" in output
        assert "AI & LLM" in output

    def test_domain_in_deploy_category(self, cli_tree):
        output = render_intent(cli_tree)
        assert "deploy_domain" in output

    def test_sync_in_deploy_category(self, cli_tree):
        output = render_intent(cli_tree)
        assert "deploy_sync" in output


# ── load_intents ───────────────────────────────────────────


class TestLoadIntents:
    def test_loads_dict(self):
        intents = load_intents()
        assert isinstance(intents, dict)

    def test_has_expected_categories(self):
        intents = load_intents()
        for cat in ("deploy", "manage", "interact", "ai", "develop"):
            assert cat in intents, f"Missing intent category: {cat}"

    def test_each_category_has_label(self):
        intents = load_intents()
        for cat, meta in intents.items():
            assert "label" in meta, f"Category {cat} missing label"

    def test_each_category_has_groups_or_commands(self):
        intents = load_intents()
        for cat, meta in intents.items():
            has_groups = "groups" in meta and len(meta["groups"]) > 0
            has_commands = "commands" in meta and len(meta["commands"]) > 0
            assert has_groups or has_commands, (
                f"Category {cat} has neither groups nor commands"
            )
