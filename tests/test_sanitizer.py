"""Tests unitaires — Proxy de sanitisation LLM (Phase 11b)."""

from __future__ import annotations

import yaml

from anklume.provisioner import BUILTIN_ROLES_DIR

from .conftest import make_domain, make_infra, make_machine

# ---------------------------------------------------------------------------
# Module engine/sanitizer.py — dataclasses
# ---------------------------------------------------------------------------


class TestSanitizeResult:
    def test_fields(self):
        from anklume.engine.sanitizer import Replacement, SanitizeResult

        r = SanitizeResult(
            text="hello",
            replacements=[
                Replacement(
                    original="10.100.1.1",
                    replaced="[IP_REDACTED_1]",
                    category="ip",
                    position=(0, 10),
                ),
            ],
        )
        assert r.text == "hello"
        assert len(r.replacements) == 1
        assert r.replacements[0].category == "ip"

    def test_empty_result(self):
        from anklume.engine.sanitizer import SanitizeResult

        r = SanitizeResult(text="safe text", replacements=[])
        assert r.replacements == []


# ---------------------------------------------------------------------------
# sanitize() — détection IPs privées
# ---------------------------------------------------------------------------


class TestSanitizeIPs:
    def test_detects_rfc1918_10(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Connexion à 10.120.0.5 réussie")
        assert "10.120.0.5" not in result.text
        assert len(result.replacements) >= 1
        assert result.replacements[0].category == "ip"

    def test_detects_rfc1918_192(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("IP: 192.168.1.100")
        assert "192.168.1.100" not in result.text

    def test_detects_rfc1918_172(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Serveur 172.16.0.1 actif")
        assert "172.16.0.1" not in result.text

    def test_preserves_public_ips(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("DNS 8.8.8.8")
        assert "8.8.8.8" in result.text
        assert len(result.replacements) == 0

    def test_multiple_ips(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("De 10.100.1.1 vers 10.100.2.1")
        assert "10.100.1.1" not in result.text
        assert "10.100.2.1" not in result.text
        assert len(result.replacements) == 2

    def test_mask_mode_placeholder(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("IP: 10.100.1.1", mode="mask")
        assert "[IP_REDACTED_" in result.text

    def test_pseudonymize_mode_consistent(self):
        from anklume.engine.sanitizer import sanitize

        text = "Serveur 10.100.1.1 et aussi 10.100.1.1"
        result = sanitize(text, mode="pseudonymize")
        # Même IP produit le même pseudonyme
        assert "10.100.1.1" not in result.text
        parts = result.text.split(" et aussi ")
        assert len(parts) == 2
        # Les deux remplacements sont identiques
        ip_replacements = [r for r in result.replacements if r.original == "10.100.1.1"]
        replaced_values = {r.replaced for r in ip_replacements}
        assert len(replaced_values) == 1  # Même pseudonyme


# ---------------------------------------------------------------------------
# sanitize() — détection FQDNs internes
# ---------------------------------------------------------------------------


class TestSanitizeFQDNs:
    def test_detects_internal_fqdn(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Résolution de server.internal")
        assert "server.internal" not in result.text
        fqdn_repls = [r for r in result.replacements if r.category == "fqdn"]
        assert len(fqdn_repls) >= 1

    def test_detects_local_fqdn(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Nom: myhost.local")
        assert "myhost.local" not in result.text

    def test_detects_corp_fqdn(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("API: api.corp")
        assert "api.corp" not in result.text


# ---------------------------------------------------------------------------
# sanitize() — détection credentials
# ---------------------------------------------------------------------------


class TestSanitizeCredentials:
    def test_detects_bearer_token(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Authorization: Bearer sk-abc123def456")
        assert "sk-abc123def456" not in result.text
        cred_repls = [r for r in result.replacements if r.category == "credential"]
        assert len(cred_repls) >= 1

    def test_detects_key_value(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("api_key=secret_value_123")
        assert "secret_value_123" not in result.text

    def test_detects_token_value(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("token: ghp_1234567890abcdef")
        assert "ghp_1234567890abcdef" not in result.text

    def test_detects_password_value(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("password=MyS3cr3tP4ss!")
        assert "MyS3cr3tP4ss!" not in result.text


# ---------------------------------------------------------------------------
# sanitize() — détection ressources Incus (via infra)
# ---------------------------------------------------------------------------


class TestSanitizeResources:
    def test_detects_instance_name(self):
        from anklume.engine.sanitizer import sanitize

        domain = make_domain(
            "pro",
            machines={
                "dev": make_machine("dev", "pro"),
            },
        )
        infra = make_infra(domains={"pro": domain})
        result = sanitize("Instance pro-dev est running", infra=infra)
        assert "pro-dev" not in result.text
        resource_repls = [r for r in result.replacements if r.category == "resource"]
        assert len(resource_repls) >= 1

    def test_detects_bridge_name(self):
        from anklume.engine.sanitizer import sanitize

        domain = make_domain("pro")
        infra = make_infra(domains={"pro": domain})
        result = sanitize("Bridge net-pro configuré", infra=infra)
        assert "net-pro" not in result.text

    def test_no_infra_no_resource_detection(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Instance pro-dev est running")
        resource_repls = [r for r in result.replacements if r.category == "resource"]
        assert len(resource_repls) == 0


# ---------------------------------------------------------------------------
# desanitize()
# ---------------------------------------------------------------------------


class TestDesanitize:
    def test_restores_original(self):
        from anklume.engine.sanitizer import desanitize, sanitize

        original = "Connexion à 10.100.1.1 port 8080"
        result = sanitize(original)
        restored = desanitize(result.text, result.replacements)
        assert restored == original

    def test_empty_replacements(self):
        from anklume.engine.sanitizer import desanitize

        text = "Safe text"
        assert desanitize(text, []) == text

    def test_restores_multiple_categories(self):
        from anklume.engine.sanitizer import desanitize, sanitize

        original = "Serveur 10.100.1.1 à myhost.internal"
        result = sanitize(original)
        restored = desanitize(result.text, result.replacements)
        assert restored == original


# ---------------------------------------------------------------------------
# sanitize() — texte sans données sensibles
# ---------------------------------------------------------------------------


class TestSanitizeSafeText:
    def test_safe_text_unchanged(self):
        from anklume.engine.sanitizer import sanitize

        text = "Hello, this is a safe message."
        result = sanitize(text)
        assert result.text == text
        assert result.replacements == []

    def test_code_snippet_preserved(self):
        from anklume.engine.sanitizer import sanitize

        text = "def hello():\n    return 42"
        result = sanitize(text)
        assert result.text == text


# ---------------------------------------------------------------------------
# Modes de remplacement
# ---------------------------------------------------------------------------


class TestSanitizeModes:
    def test_mask_uses_indexed_placeholders(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("IPs: 10.1.1.1, 10.2.2.2", mode="mask")
        assert "[IP_REDACTED_1]" in result.text
        assert "[IP_REDACTED_2]" in result.text

    def test_pseudonymize_preserves_structure(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("IP: 10.100.1.5", mode="pseudonymize")
        # Le pseudonyme doit ressembler à une IP
        assert "10.100.1.5" not in result.text
        # Le remplacement existe
        assert len(result.replacements) == 1

    def test_invalid_mode_raises(self):
        import pytest

        from anklume.engine.sanitizer import sanitize

        with pytest.raises(ValueError, match="mode"):
            sanitize("test", mode="invalid")


# ---------------------------------------------------------------------------
# Rôle Ansible llm_sanitizer
# ---------------------------------------------------------------------------


class TestLlmSanitizerRoleExists:
    def test_role_directory_exists(self):
        role_dir = BUILTIN_ROLES_DIR / "llm_sanitizer"
        assert role_dir.is_dir()

    def test_has_tasks(self):
        tasks = BUILTIN_ROLES_DIR / "llm_sanitizer" / "tasks" / "main.yml"
        assert tasks.is_file()
        content = yaml.safe_load(tasks.read_text())
        assert isinstance(content, list)
        assert len(content) > 0

    def test_has_defaults(self):
        defaults = BUILTIN_ROLES_DIR / "llm_sanitizer" / "defaults" / "main.yml"
        assert defaults.is_file()
        content = yaml.safe_load(defaults.read_text())
        assert "sanitizer_port" in content
        assert content["sanitizer_port"] == 8089

    def test_has_handlers(self):
        handlers = BUILTIN_ROLES_DIR / "llm_sanitizer" / "handlers" / "main.yml"
        assert handlers.is_file()

    def test_defaults_mode_mask(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "llm_sanitizer" / "defaults" / "main.yml").read_text()
        )
        assert defaults["sanitizer_mode"] == "mask"


# ---------------------------------------------------------------------------
# Phase 15 — Patterns supplémentaires (MAC, socket, incus_cmd)
# ---------------------------------------------------------------------------


class TestSanitizeMacAddresses:
    def test_detects_mac_address(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Interface eth0 MAC AA:BB:CC:DD:EE:FF active")
        assert "AA:BB:CC:DD:EE:FF" not in result.text
        mac_repls = [r for r in result.replacements if r.category == "mac"]
        assert len(mac_repls) == 1

    def test_detects_lowercase_mac(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("mac=aa:bb:cc:dd:ee:ff")
        assert "aa:bb:cc:dd:ee:ff" not in result.text

    def test_mask_mode_mac(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("MAC: AA:BB:CC:DD:EE:FF", mode="mask")
        assert "[MAC_REDACTED_1]" in result.text

    def test_pseudonymize_mode_mac(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("MAC: AA:BB:CC:DD:EE:FF", mode="pseudonymize")
        assert "AA:BB:CC:DD:EE:FF" not in result.text
        assert result.replacements[0].replaced.startswith("00:00:00:00:00:")

    def test_multiple_macs(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("src=AA:BB:CC:DD:EE:01 dst=AA:BB:CC:DD:EE:02")
        assert len([r for r in result.replacements if r.category == "mac"]) == 2

    def test_preserves_non_mac(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Version 12:34:56")
        mac_repls = [r for r in result.replacements if r.category == "mac"]
        assert len(mac_repls) == 0


class TestSanitizeSockets:
    def test_detects_run_socket(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Socket /var/run/incus.sock ouvert")
        assert "/var/run/incus.sock" not in result.text
        sock_repls = [r for r in result.replacements if r.category == "socket"]
        assert len(sock_repls) == 1

    def test_detects_tmp_socket(self):
        from anklume.engine.sanitizer import sanitize

        tmp_sock = "/tmp/agent.socket"  # noqa: S108
        result = sanitize(f"Connexion à {tmp_sock}")
        assert tmp_sock not in result.text

    def test_detects_run_direct_socket(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("fd=/run/dbus/system_bus_socket")
        assert "/run/dbus/system_bus_socket" not in result.text

    def test_mask_mode_socket(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Socket: /var/run/incus.sock", mode="mask")
        assert "[SOCKET_REDACTED_1]" in result.text

    def test_pseudonymize_mode_socket(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Socket: /var/run/incus.sock", mode="pseudonymize")
        assert "/run/redacted-" in result.text


class TestSanitizeIncusCommands:
    def test_detects_incus_exec(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Exécution : incus exec pro-dev -- bash")
        assert "incus exec pro-dev -- bash" not in result.text
        cmd_repls = [r for r in result.replacements if r.category == "incus_cmd"]
        assert len(cmd_repls) == 1

    def test_detects_incus_launch(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("incus launch images:debian/13 test-vm")
        assert "incus launch images:debian/13 test-vm" not in result.text

    def test_detects_incus_stop(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("incus stop pro-dev")
        assert "incus stop pro-dev" not in result.text

    def test_detects_incus_config(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("incus config set pro-dev limits.cpu 2")
        assert "incus config set pro-dev limits.cpu 2" not in result.text

    def test_mask_mode_incus_cmd(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("Run: incus exec pro-dev -- ls", mode="mask")
        assert "[INCUS_CMD_REDACTED_1]" in result.text

    def test_preserves_incus_non_command(self):
        from anklume.engine.sanitizer import sanitize

        result = sanitize("incus is a container manager")
        cmd_repls = [r for r in result.replacements if r.category == "incus_cmd"]
        assert len(cmd_repls) == 0


# ---------------------------------------------------------------------------
# Phase 15 — Filtrage par catégories
# ---------------------------------------------------------------------------


class TestSanitizeCategories:
    def test_filter_ip_only(self):
        from anklume.engine.sanitizer import sanitize

        text = "IP 10.100.1.1 MAC AA:BB:CC:DD:EE:FF"
        result = sanitize(text, categories={"ip"})
        assert "10.100.1.1" not in result.text
        assert "AA:BB:CC:DD:EE:FF" in result.text

    def test_filter_mac_only(self):
        from anklume.engine.sanitizer import sanitize

        text = "IP 10.100.1.1 MAC AA:BB:CC:DD:EE:FF"
        result = sanitize(text, categories={"mac"})
        assert "10.100.1.1" in result.text
        assert "AA:BB:CC:DD:EE:FF" not in result.text

    def test_filter_multiple_categories(self):
        from anklume.engine.sanitizer import sanitize

        text = "10.100.1.1 token=secret server.internal"
        result = sanitize(text, categories={"ip", "credential"})
        assert "10.100.1.1" not in result.text
        assert "secret" not in result.text
        assert "server.internal" in result.text

    def test_none_means_all(self):
        from anklume.engine.sanitizer import sanitize

        text = "10.100.1.1 AA:BB:CC:DD:EE:FF"
        result = sanitize(text, categories=None)
        assert "10.100.1.1" not in result.text
        assert "AA:BB:CC:DD:EE:FF" not in result.text

    def test_empty_set_keeps_all(self):
        from anklume.engine.sanitizer import sanitize

        text = "10.100.1.1 AA:BB:CC:DD:EE:FF"
        result = sanitize(text, categories=set())
        assert result.text == text
        assert len(result.replacements) == 0


# ---------------------------------------------------------------------------
# Phase 15 — NER optionnel
# ---------------------------------------------------------------------------


class TestNerBackend:
    def test_detect_ner_backend_returns_string_or_none(self):
        from anklume.engine.sanitizer import detect_ner_backend

        result = detect_ner_backend()
        assert result is None or result in {"gliner", "spacy"}

    def test_ner_extract_returns_list(self):
        from anklume.engine.sanitizer import ner_extract

        # Avec un backend inexistant, retourne liste vide
        result = ner_extract("Jean Dupont habite à Paris", "nonexistent")
        assert result == []

    def test_sanitize_ner_flag(self):
        from anklume.engine.sanitizer import sanitize

        # Avec ner=True et aucun backend, fonctionne comme regex seul
        result = sanitize("IP 10.100.1.1", ner=True)
        assert "10.100.1.1" not in result.text

    def test_sanitize_ner_false_default(self):
        from anklume.engine.sanitizer import sanitize

        # Par défaut ner=False
        result = sanitize("Texte sans données sensibles")
        assert result.text == "Texte sans données sensibles"


# ---------------------------------------------------------------------------
# Phase 15 — Audit logging
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_entry_fields(self):
        from anklume.engine.sanitizer import AuditEntry

        entry = AuditEntry(
            timestamp="2026-03-09T10:00:00",
            mode="mask",
            categories={"ip": 2, "credential": 1},
            total_redactions=3,
        )
        assert entry.total_redactions == 3
        assert entry.categories["ip"] == 2

    def test_audit_log_creates_entry(self, tmp_path):
        from anklume.engine.sanitizer import audit_log, sanitize

        result = sanitize("IP 10.100.1.1 token=secret")
        log_file = tmp_path / "audit.jsonl"
        entry = audit_log(result, mode="mask", log_path=log_file)
        assert entry.total_redactions == 2
        assert entry.categories["ip"] == 1
        assert entry.categories["credential"] == 1

    def test_audit_log_writes_file(self, tmp_path):
        import json

        from anklume.engine.sanitizer import audit_log, sanitize

        result = sanitize("IP 10.100.1.1")
        log_file = tmp_path / "audit.jsonl"
        audit_log(result, mode="mask", log_path=log_file)
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["mode"] == "mask"
        assert data["total_redactions"] == 1

    def test_audit_log_appends(self, tmp_path):
        from anklume.engine.sanitizer import audit_log, sanitize

        log_file = tmp_path / "audit.jsonl"
        r1 = sanitize("IP 10.100.1.1")
        r2 = sanitize("MAC AA:BB:CC:DD:EE:FF")
        audit_log(r1, mode="mask", log_path=log_file)
        audit_log(r2, mode="mask", log_path=log_file)
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_audit_log_no_redactions(self, tmp_path):
        from anklume.engine.sanitizer import audit_log, sanitize

        result = sanitize("Texte propre")
        log_file = tmp_path / "audit.jsonl"
        entry = audit_log(result, mode="mask", log_path=log_file)
        assert entry.total_redactions == 0

    def test_audit_log_creates_parent_dirs(self, tmp_path):
        from anklume.engine.sanitizer import audit_log, sanitize

        result = sanitize("IP 10.100.1.1")
        log_file = tmp_path / "sub" / "dir" / "audit.jsonl"
        audit_log(result, mode="mask", log_path=log_file)
        assert log_file.exists()


# ---------------------------------------------------------------------------
# Phase 15 — CLI `anklume llm sanitize`
# ---------------------------------------------------------------------------


class TestLlmSanitizeCli:
    def test_command_registered(self):
        from anklume.cli import llm_app

        command_names = [cmd.name for cmd in llm_app.registered_commands]
        assert "sanitize" in command_names

    def test_run_llm_sanitize_basic(self, capsys):
        from anklume.cli._llm import run_llm_sanitize

        run_llm_sanitize(text="IP 10.100.1.1 détectée", mode="mask")
        captured = capsys.readouterr()
        assert "[IP_REDACTED_1]" in captured.out
        assert "10.100.1.1" in captured.out  # dans le tableau de remplacements

    def test_run_llm_sanitize_json(self, capsys):
        import json

        from anklume.cli._llm import run_llm_sanitize

        run_llm_sanitize(
            text="Token: Bearer sk-abc123",
            mode="mask",
            json_output=True,
        )
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "text" in data
        assert "replacements" in data

    def test_run_llm_sanitize_no_redactions(self, capsys):
        from anklume.cli._llm import run_llm_sanitize

        run_llm_sanitize(text="Texte propre", mode="mask")
        captured = capsys.readouterr()
        assert "0" in captured.out or "Aucun" in captured.out

    def test_run_llm_sanitize_pseudonymize(self, capsys):
        from anklume.cli._llm import run_llm_sanitize

        run_llm_sanitize(text="IP 10.100.1.1", mode="pseudonymize")
        captured = capsys.readouterr()
        assert "10.100.1.1" in captured.out


# ---------------------------------------------------------------------------
# Phase 15 — Rôle llm_sanitizer enrichi (templates, defaults)
# ---------------------------------------------------------------------------


class TestLlmSanitizerRolePhase15:
    def test_defaults_has_audit_log_path(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "llm_sanitizer" / "defaults" / "main.yml").read_text()
        )
        assert "sanitizer_audit_log_path" in defaults

    def test_defaults_has_categories(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "llm_sanitizer" / "defaults" / "main.yml").read_text()
        )
        assert "sanitizer_categories" in defaults
        assert defaults["sanitizer_categories"] == "all"

    def test_has_config_template(self):
        tpl = BUILTIN_ROLES_DIR / "llm_sanitizer" / "templates" / "config.yml.j2"
        assert tpl.is_file()
        content = tpl.read_text()
        assert "sanitizer_port" in content
        assert "sanitizer_mode" in content

    def test_has_patterns_template(self):
        tpl = BUILTIN_ROLES_DIR / "llm_sanitizer" / "templates" / "patterns.yml.j2"
        assert tpl.is_file()
        content = tpl.read_text()
        assert "ip" in content
        assert "mac" in content

    def test_tasks_use_template(self):
        tasks = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "llm_sanitizer" / "tasks" / "main.yml").read_text()
        )
        template_tasks = [t for t in tasks if "ansible.builtin.template" in str(t)]
        assert len(template_tasks) >= 2
