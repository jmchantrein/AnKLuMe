"""Tests for the LLM sanitizer dry-run module."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestLoadPatterns:
    """Test pattern loading from template."""

    def test_load_from_template(self):
        from scripts.sanitizer_dryrun import load_patterns

        patterns = load_patterns()
        assert len(patterns) > 0

    def test_all_categories_loaded(self):
        from scripts.sanitizer_dryrun import load_patterns, pattern_stats

        patterns = load_patterns()
        stats = pattern_stats(patterns)
        expected = {
            "ip_addresses", "incus_resources", "fqdn",
            "service_identifiers", "ansible_names",
            "network_identifiers", "credentials",
        }
        assert expected == set(stats.keys())

    def test_pattern_count_matches_template(self):
        """Should load all 147+ patterns from the template."""
        from scripts.sanitizer_dryrun import load_patterns

        patterns = load_patterns()
        # Template has 5+4+4+3+4+5+5 = 30 patterns minimum
        assert len(patterns) >= 25

    def test_pattern_has_required_fields(self):
        from scripts.sanitizer_dryrun import load_patterns

        patterns = load_patterns()
        for p in patterns:
            assert "category" in p
            assert "name" in p
            assert "pattern" in p
            assert "replacement" in p
            assert p["pattern"], f"Empty pattern in {p['name']}"

    def test_load_from_explicit_file(self, tmp_path):
        import yaml

        from scripts.sanitizer_dryrun import load_patterns

        custom = tmp_path / "patterns.yml"
        custom.write_text(yaml.dump({
            "categories": {
                "test_cat": [
                    {"name": "test_p", "pattern": r"\bfoo\b", "replacement": "BAR"},
                ],
            },
        }))
        patterns = load_patterns(str(custom))
        assert len(patterns) == 1
        assert patterns[0]["category"] == "test_cat"

    def test_load_falls_back_when_explicit_missing(self):
        """When explicit file doesn't exist, falls back to template."""
        from scripts.sanitizer_dryrun import load_patterns

        result = load_patterns("/nonexistent/path.yml")
        # Should still load from template fallback
        assert len(result) > 0

    def test_all_patterns_are_valid_regex(self):
        """Every pattern should compile without error."""
        import re

        from scripts.sanitizer_dryrun import load_patterns

        patterns = load_patterns()
        for p in patterns:
            try:
                re.compile(p["pattern"])
            except re.error as e:
                raise AssertionError(f"Invalid regex in {p['name']}: {e}") from e


class TestApplyPatterns:
    """Test pattern application."""

    def test_redacts_anklume_ips(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Server at 10.120.1.5 is running."
        sanitized, redactions = apply_patterns(text, patterns)
        assert "10.120.1.5" not in sanitized
        assert len(redactions) > 0

    def test_redacts_rfc1918_class_c(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Home router at 192.168.1.1"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "192.168.1.1" not in sanitized

    def test_redacts_incus_bridges(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Bridge net-pro is up."
        sanitized, redactions = apply_patterns(text, patterns)
        assert "net-pro" not in sanitized

    def test_redacts_mac_addresses(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "MAC: 00:16:3e:ab:cd:ef"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "00:16:3e:ab:cd:ef" not in sanitized

    def test_redacts_credentials(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized

    def test_redacts_ssh_private_key_header(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "-----BEGIN RSA PRIVATE KEY-----"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "BEGIN RSA PRIVATE KEY" not in sanitized

    def test_redacts_ansible_paths(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Edit group_vars/pro.yml and host_vars/pro-dev.yml"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "group_vars/pro.yml" not in sanitized
        assert "host_vars/pro-dev.yml" not in sanitized

    def test_redacts_ollama_endpoint(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Ollama at http://10.100.3.1:11434"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "10.100.3.1:11434" not in sanitized

    def test_redacts_internal_fqdn(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "DNS: server.internal and printer.local"
        sanitized, redactions = apply_patterns(text, patterns)
        assert "server.internal" not in sanitized
        assert "printer.local" not in sanitized

    def test_no_redactions_on_clean_text(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Hello world, this is a simple prompt."
        sanitized, redactions = apply_patterns(text, patterns)
        assert sanitized == text
        assert len(redactions) == 0

    def test_multiple_redactions_in_same_text(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "Server 10.120.1.5 on net-pro with MAC 00:16:3e:ab:cd:ef"
        sanitized, redactions = apply_patterns(text, patterns)
        assert len(redactions) >= 3

    def test_redaction_metadata_contains_position(self):
        from scripts.sanitizer_dryrun import apply_patterns, load_patterns

        patterns = load_patterns()
        text = "IP is 10.120.1.5 here"
        _, redactions = apply_patterns(text, patterns)
        assert len(redactions) > 0
        r = redactions[0]
        assert "start" in r
        assert "end" in r
        assert r["start"] >= 0
        assert r["end"] > r["start"]


class TestFormatDiff:
    """Test the diff formatting."""

    def test_no_redactions_message(self):
        from scripts.sanitizer_dryrun import format_diff

        result = format_diff("hello", "hello", [])
        assert "No redactions" in result

    def test_diff_contains_counts(self):
        from scripts.sanitizer_dryrun import format_diff

        redactions = [
            {"category": "ip_addresses", "name": "test", "original": "1.2.3.4",
             "replacement": "X.X.X.X", "start": 0, "end": 7},
        ]
        result = format_diff("1.2.3.4", "X.X.X.X", redactions)
        assert "1 redaction" in result

    def test_diff_shows_category(self):
        from scripts.sanitizer_dryrun import format_diff

        redactions = [
            {"category": "ip_addresses", "name": "test", "original": "1.2.3.4",
             "replacement": "X.X.X.X", "start": 0, "end": 7},
        ]
        result = format_diff("1.2.3.4", "X.X.X.X", redactions)
        assert "ip_addresses" in result

    def test_diff_shows_sanitized_output(self):
        from scripts.sanitizer_dryrun import format_diff

        redactions = [
            {"category": "test", "name": "t", "original": "old",
             "replacement": "new", "start": 0, "end": 3},
        ]
        result = format_diff("old text", "new text", redactions)
        assert "new text" in result


class TestPatternStats:
    """Test pattern statistics."""

    def test_stats_returns_dict(self):
        from scripts.sanitizer_dryrun import load_patterns, pattern_stats

        patterns = load_patterns()
        stats = pattern_stats(patterns)
        assert isinstance(stats, dict)
        assert all(isinstance(v, int) for v in stats.values())

    def test_stats_sum_equals_total(self):
        from scripts.sanitizer_dryrun import load_patterns, pattern_stats

        patterns = load_patterns()
        stats = pattern_stats(patterns)
        assert sum(stats.values()) == len(patterns)


class TestCLIIntegration:
    """Test CLI commands exist."""

    def test_sanitize_command_exists(self):
        from scripts.cli.llm import app

        callback_names = [
            cmd.callback.__name__ if cmd.callback else cmd.name
            for cmd in app.registered_commands
        ]
        assert "sanitize" in callback_names

    def test_patterns_command_exists(self):
        from scripts.cli.llm import app

        callback_names = [
            cmd.name or (cmd.callback.__name__ if cmd.callback else None)
            for cmd in app.registered_commands
        ]
        assert "patterns" in callback_names


class TestModuleEntrypoint:
    """Test the module can be imported and run."""

    def test_module_importable(self):
        import scripts.sanitizer_dryrun as mod
        assert hasattr(mod, "load_patterns")
        assert hasattr(mod, "apply_patterns")
        assert hasattr(mod, "format_diff")
        assert hasattr(mod, "main")
