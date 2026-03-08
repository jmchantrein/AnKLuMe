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
