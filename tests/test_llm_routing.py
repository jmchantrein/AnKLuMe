"""Tests unitaires — Routage LLM et intégration sanitiser (Phase 25).

Couvre :
- Module engine/llm_routing.py (resolve, find, enrich)
- Validation des backends et ai_sanitize
- Mise à jour des rôles Ansible (openclaw_server, lobechat, llm_sanitizer)
- Intégration dans le pipeline provisioner (host_vars enrichies)
"""

from __future__ import annotations

import yaml

from anklume.provisioner import BUILTIN_ROLES_DIR
from anklume.provisioner.playbook import generate_host_vars, generate_playbook

from .conftest import make_domain, make_infra, make_machine

# ===========================================================================
# 1. Module engine/llm_routing.py — constantes et dataclasses
# ===========================================================================


class TestLlmRoutingConstants:
    def test_llm_backends_contains_local(self):
        from anklume.engine.llm_routing import LLM_BACKENDS

        assert "local" in LLM_BACKENDS

    def test_llm_backends_contains_openai(self):
        from anklume.engine.llm_routing import LLM_BACKENDS

        assert "openai" in LLM_BACKENDS

    def test_llm_backends_contains_anthropic(self):
        from anklume.engine.llm_routing import LLM_BACKENDS

        assert "anthropic" in LLM_BACKENDS

    def test_ai_sanitize_values(self):
        from anklume.engine.llm_routing import AI_SANITIZE_VALUES

        assert AI_SANITIZE_VALUES == {"false", "true", "always"}

    def test_llm_consumer_roles(self):
        from anklume.engine.llm_routing import LLM_CONSUMER_ROLES

        assert "openclaw_server" in LLM_CONSUMER_ROLES
        assert "lobechat" in LLM_CONSUMER_ROLES
        assert "open_webui" in LLM_CONSUMER_ROLES
        assert "opencode_server" in LLM_CONSUMER_ROLES


class TestLlmEndpointDataclass:
    def test_fields(self):
        from anklume.engine.llm_routing import LlmEndpoint

        ep = LlmEndpoint(
            backend="local",
            url="http://10.100.3.1:11434",
            api_key="",
            model="",
            sanitized=False,
            upstream_url="",
        )
        assert ep.backend == "local"
        assert ep.url == "http://10.100.3.1:11434"
        assert ep.sanitized is False

    def test_external_endpoint(self):
        from anklume.engine.llm_routing import LlmEndpoint

        ep = LlmEndpoint(
            backend="openai",
            url="http://10.100.1.5:8089",
            api_key="sk-test",
            model="gpt-4o",
            sanitized=True,
            upstream_url="https://api.openai.com/v1",
        )
        assert ep.sanitized is True
        assert ep.upstream_url == "https://api.openai.com/v1"


# ===========================================================================
# 2. resolve_llm_endpoint — backend local
# ===========================================================================


class TestResolveLocal:
    def test_local_default_ollama_same_domain(self):
        """Backend local, Ollama dans le meme domaine -> localhost."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m_ollama = make_machine(
            "gpu-server", "ai-tools", roles=["ollama_server"], ip="10.100.3.1"
        )
        m_claw = make_machine(
            "assistant",
            "ai-tools",
            roles=["openclaw_server"],
            ip="10.100.3.5",
        )
        domain = make_domain(
            "ai-tools",
            machines={"gpu-server": m_ollama, "assistant": m_claw},
        )
        infra = make_infra(domains={"ai-tools": domain})

        ep = resolve_llm_endpoint(m_claw, domain, infra)
        assert ep.backend == "local"
        assert "10.100.3.1" in ep.url
        assert "11434" in ep.url
        assert ep.sanitized is False
        assert ep.api_key == ""

    def test_local_finds_ollama_in_other_domain(self):
        """Backend local, Ollama dans un autre domaine -> IP de l'autre domaine."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m_ollama = make_machine(
            "gpu-server", "ai-tools", roles=["ollama_server"], ip="10.100.3.1"
        )
        d_ai = make_domain("ai-tools", machines={"gpu-server": m_ollama})

        m_claw = make_machine(
            "assistant", "pro", roles=["openclaw_server"], ip="10.100.1.5"
        )
        d_pro = make_domain("pro", machines={"assistant": m_claw})

        infra = make_infra(domains={"ai-tools": d_ai, "pro": d_pro})

        ep = resolve_llm_endpoint(m_claw, d_pro, infra)
        assert ep.backend == "local"
        assert "10.100.3.1" in ep.url

    def test_local_no_ollama_found_uses_localhost(self):
        """Pas d'Ollama trouve -> fallback localhost."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m_claw = make_machine(
            "assistant", "pro", roles=["openclaw_server"], ip="10.100.1.5"
        )
        domain = make_domain("pro", machines={"assistant": m_claw})
        infra = make_infra(domains={"pro": domain})

        ep = resolve_llm_endpoint(m_claw, domain, infra)
        assert ep.backend == "local"
        assert "localhost" in ep.url


# ===========================================================================
# 3. resolve_llm_endpoint — backend externe
# ===========================================================================


class TestResolveExternal:
    def test_openai_backend_direct(self):
        """Backend openai sans sanitisation -> URL directe."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "llm_model": "gpt-4o",
            },
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        ep = resolve_llm_endpoint(m, domain, infra)
        assert ep.backend == "openai"
        assert ep.url == "https://api.openai.com/v1"
        assert ep.api_key == "sk-test"
        assert ep.model == "gpt-4o"
        assert ep.sanitized is False

    def test_anthropic_backend_direct(self):
        """Backend anthropic sans sanitisation."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "anthropic",
                "llm_api_url": "https://api.anthropic.com/v1",
                "llm_api_key": "sk-ant-test",
                "llm_model": "claude-sonnet-4-20250514",
            },
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        ep = resolve_llm_endpoint(m, domain, infra)
        assert ep.backend == "anthropic"
        assert ep.api_key == "sk-ant-test"
        assert ep.sanitized is False

    def test_openai_missing_api_url_raises(self):
        """Backend externe sans llm_api_url -> ValueError."""
        import pytest

        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={"llm_backend": "openai", "llm_api_key": "sk-test"},
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        with pytest.raises(ValueError, match="llm_api_url"):
            resolve_llm_endpoint(m, domain, infra)

    def test_openai_missing_api_key_raises(self):
        """Backend externe sans llm_api_key -> ValueError."""
        import pytest

        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
            },
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        with pytest.raises(ValueError, match="llm_api_key"):
            resolve_llm_endpoint(m, domain, infra)

    def test_invalid_backend_raises(self):
        """Backend inconnu -> ValueError."""
        import pytest

        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={"llm_backend": "gemini"},
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        with pytest.raises(ValueError, match="llm_backend"):
            resolve_llm_endpoint(m, domain, infra)


# ===========================================================================
# 4. resolve_llm_endpoint — sanitisation
# ===========================================================================


class TestResolveSanitized:
    def _make_infra_with_sanitizer(self, *, machine_vars: dict | None = None):
        """Helper : infra avec sanitizer + assistant dans le meme domaine."""
        m_sanitizer = make_machine(
            "sanitizer",
            "pro",
            roles=["llm_sanitizer"],
            ip="10.100.1.2",
        )
        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars=machine_vars or {},
        )
        domain = make_domain(
            "pro",
            machines={"sanitizer": m_sanitizer, "assistant": m_claw},
        )
        return m_claw, domain, make_infra(domains={"pro": domain})

    def test_external_with_sanitize_true(self):
        """Backend externe + ai_sanitize: true -> passe par sanitizer."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m, domain, infra = self._make_infra_with_sanitizer(
            machine_vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "ai_sanitize": "true",
            }
        )
        ep = resolve_llm_endpoint(m, domain, infra)
        assert ep.sanitized is True
        assert "8089" in ep.url  # port sanitizer
        assert "10.100.1.2" in ep.url  # IP sanitizer
        assert ep.upstream_url == "https://api.openai.com/v1"

    def test_external_with_sanitize_always(self):
        """Backend externe + ai_sanitize: always -> sanitiser."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m, domain, infra = self._make_infra_with_sanitizer(
            machine_vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "ai_sanitize": "always",
            }
        )
        ep = resolve_llm_endpoint(m, domain, infra)
        assert ep.sanitized is True

    def test_local_with_sanitize_true_not_sanitized(self):
        """Backend local + ai_sanitize: true -> PAS de sanitisation."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m, domain, infra = self._make_infra_with_sanitizer(
            machine_vars={"ai_sanitize": "true"}
        )
        ep = resolve_llm_endpoint(m, domain, infra)
        assert ep.sanitized is False
        assert ep.backend == "local"

    def test_local_with_sanitize_always_is_sanitized(self):
        """Backend local + ai_sanitize: always -> sanitisation."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m_ollama = make_machine(
            "gpu-server", "pro", roles=["ollama_server"], ip="10.100.1.3"
        )
        m_sanitizer = make_machine(
            "sanitizer", "pro", roles=["llm_sanitizer"], ip="10.100.1.2"
        )
        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={"ai_sanitize": "always"},
        )
        domain = make_domain(
            "pro",
            machines={
                "gpu-server": m_ollama,
                "sanitizer": m_sanitizer,
                "assistant": m_claw,
            },
        )
        infra = make_infra(domains={"pro": domain})

        ep = resolve_llm_endpoint(m_claw, domain, infra)
        assert ep.sanitized is True
        assert "10.100.1.2" in ep.url  # sanitizer
        assert "10.100.1.3" in ep.upstream_url  # ollama derriere

    def test_sanitize_true_no_sanitizer_warns(self):
        """ai_sanitize: true mais pas de machine sanitizer -> ValueError."""
        import pytest

        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "ai_sanitize": "true",
            },
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        with pytest.raises(ValueError, match="sanitizer"):
            resolve_llm_endpoint(m, domain, infra)

    def test_invalid_ai_sanitize_raises(self):
        """ai_sanitize invalide -> ValueError."""
        import pytest

        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={"ai_sanitize": "maybe"},
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        with pytest.raises(ValueError, match="ai_sanitize"):
            resolve_llm_endpoint(m, domain, infra)


# ===========================================================================
# 5. find_sanitizer_url
# ===========================================================================


class TestFindSanitizerUrl:
    def test_finds_in_same_domain(self):
        from anklume.engine.llm_routing import find_sanitizer_url

        m_san = make_machine(
            "sanitizer", "pro", roles=["llm_sanitizer"], ip="10.100.1.2"
        )
        domain = make_domain("pro", machines={"sanitizer": m_san})
        infra = make_infra(domains={"pro": domain})

        url = find_sanitizer_url(domain, infra)
        assert url is not None
        assert "10.100.1.2" in url
        assert "8089" in url

    def test_finds_in_other_domain(self):
        from anklume.engine.llm_routing import find_sanitizer_url

        m_san = make_machine(
            "sanitizer", "ai-tools", roles=["llm_sanitizer"], ip="10.100.3.2"
        )
        d_ai = make_domain("ai-tools", machines={"sanitizer": m_san})
        d_pro = make_domain("pro", machines={})
        infra = make_infra(domains={"ai-tools": d_ai, "pro": d_pro})

        url = find_sanitizer_url(d_pro, infra)
        assert url is not None
        assert "10.100.3.2" in url

    def test_returns_none_if_no_sanitizer(self):
        from anklume.engine.llm_routing import find_sanitizer_url

        domain = make_domain("pro", machines={})
        infra = make_infra(domains={"pro": domain})

        assert find_sanitizer_url(domain, infra) is None

    def test_uses_custom_port(self):
        from anklume.engine.llm_routing import find_sanitizer_url

        m_san = make_machine(
            "sanitizer",
            "pro",
            roles=["llm_sanitizer"],
            ip="10.100.1.2",
            vars={"sanitizer_port": 9090},
        )
        domain = make_domain("pro", machines={"sanitizer": m_san})
        infra = make_infra(domains={"pro": domain})

        url = find_sanitizer_url(domain, infra)
        assert "9090" in url


# ===========================================================================
# 6. find_ollama_url
# ===========================================================================


class TestFindOllamaUrl:
    def test_finds_in_same_domain(self):
        from anklume.engine.llm_routing import find_ollama_url

        m_ollama = make_machine(
            "gpu-server", "ai-tools", roles=["ollama_server"], ip="10.100.3.1"
        )
        domain = make_domain("ai-tools", machines={"gpu-server": m_ollama})
        infra = make_infra(domains={"ai-tools": domain})

        url = find_ollama_url(domain, infra)
        assert "10.100.3.1" in url
        assert "11434" in url

    def test_finds_in_other_domain(self):
        from anklume.engine.llm_routing import find_ollama_url

        m_ollama = make_machine(
            "gpu-server", "ai-tools", roles=["ollama_server"], ip="10.100.3.1"
        )
        d_ai = make_domain("ai-tools", machines={"gpu-server": m_ollama})
        d_pro = make_domain("pro", machines={})
        infra = make_infra(domains={"ai-tools": d_ai, "pro": d_pro})

        url = find_ollama_url(d_pro, infra)
        assert "10.100.3.1" in url

    def test_fallback_localhost(self):
        from anklume.engine.llm_routing import find_ollama_url

        domain = make_domain("pro", machines={})
        infra = make_infra(domains={"pro": domain})

        url = find_ollama_url(domain, infra)
        assert "localhost" in url

    def test_uses_custom_port(self):
        from anklume.engine.llm_routing import find_ollama_url

        m_ollama = make_machine(
            "gpu-server",
            "ai-tools",
            roles=["ollama_server"],
            ip="10.100.3.1",
            vars={"ollama_port": 12345},
        )
        domain = make_domain("ai-tools", machines={"gpu-server": m_ollama})
        infra = make_infra(domains={"ai-tools": domain})

        url = find_ollama_url(domain, infra)
        assert "12345" in url


# ===========================================================================
# 7. enrich_llm_vars
# ===========================================================================


class TestEnrichLlmVars:
    def test_enriches_openclaw_with_local(self):
        """Machine openclaw sans config LLM -> vars enrichies local."""
        from anklume.engine.llm_routing import enrich_llm_vars

        m_ollama = make_machine(
            "gpu-server", "ai-tools", roles=["ollama_server"], ip="10.100.3.1"
        )
        m_claw = make_machine(
            "assistant",
            "ai-tools",
            roles=["openclaw_server"],
            ip="10.100.3.5",
        )
        domain = make_domain(
            "ai-tools",
            machines={"gpu-server": m_ollama, "assistant": m_claw},
        )
        infra = make_infra(domains={"ai-tools": domain})

        enriched = enrich_llm_vars(infra)
        assistant = enriched.domains["ai-tools"].machines["assistant"]

        assert assistant.vars["llm_effective_backend"] == "local"
        assert "10.100.3.1" in assistant.vars["llm_effective_url"]
        assert assistant.vars["llm_effective_key"] == ""

    def test_enriches_openclaw_with_external(self):
        """Machine openclaw avec backend openai -> vars enrichies."""
        from anklume.engine.llm_routing import enrich_llm_vars

        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "llm_model": "gpt-4o",
            },
        )
        domain = make_domain("pro", machines={"assistant": m_claw})
        infra = make_infra(domains={"pro": domain})

        enriched = enrich_llm_vars(infra)
        assistant = enriched.domains["pro"].machines["assistant"]

        assert assistant.vars["llm_effective_backend"] == "openai"
        assert assistant.vars["llm_effective_url"] == "https://api.openai.com/v1"
        assert assistant.vars["llm_effective_key"] == "sk-test"
        assert assistant.vars["llm_effective_model"] == "gpt-4o"

    def test_enriches_with_sanitizer(self):
        """Machine avec sanitisation -> URL du sanitizer."""
        from anklume.engine.llm_routing import enrich_llm_vars

        m_san = make_machine(
            "sanitizer", "pro", roles=["llm_sanitizer"], ip="10.100.1.2"
        )
        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "ai_sanitize": "true",
            },
        )
        domain = make_domain(
            "pro",
            machines={"sanitizer": m_san, "assistant": m_claw},
        )
        infra = make_infra(domains={"pro": domain})

        enriched = enrich_llm_vars(infra)
        assistant = enriched.domains["pro"].machines["assistant"]

        assert "10.100.1.2" in assistant.vars["llm_effective_url"]
        assert "8089" in assistant.vars["llm_effective_url"]

    def test_does_not_enrich_non_consumer(self):
        """Machine sans role consommateur LLM -> pas enrichie."""
        from anklume.engine.llm_routing import enrich_llm_vars

        m = make_machine("web", "pro", roles=["base"], ip="10.100.1.5")
        domain = make_domain("pro", machines={"web": m})
        infra = make_infra(domains={"pro": domain})

        enriched = enrich_llm_vars(infra)
        web = enriched.domains["pro"].machines["web"]

        assert "llm_effective_url" not in web.vars

    def test_preserves_existing_vars(self):
        """L'enrichissement preserve les vars existantes."""
        from anklume.engine.llm_routing import enrich_llm_vars

        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={"openclaw_channels": ["telegram"]},
        )
        domain = make_domain("pro", machines={"assistant": m_claw})
        infra = make_infra(domains={"pro": domain})

        enriched = enrich_llm_vars(infra)
        assistant = enriched.domains["pro"].machines["assistant"]

        assert assistant.vars["openclaw_channels"] == ["telegram"]
        assert "llm_effective_url" in assistant.vars

    def test_enriches_sanitizer_upstream(self):
        """La machine sanitizer recoit sanitizer_upstream_url."""
        from anklume.engine.llm_routing import enrich_llm_vars

        m_san = make_machine(
            "sanitizer", "pro", roles=["llm_sanitizer"], ip="10.100.1.2"
        )
        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "ai_sanitize": "true",
            },
        )
        domain = make_domain(
            "pro",
            machines={"sanitizer": m_san, "assistant": m_claw},
        )
        infra = make_infra(domains={"pro": domain})

        enriched = enrich_llm_vars(infra)
        sanitizer = enriched.domains["pro"].machines["sanitizer"]

        assert "sanitizer_upstream_url" in sanitizer.vars


# ===========================================================================
# 8. Mise a jour du role openclaw_server
# ===========================================================================


class TestOpenclawRoleLlmVars:
    def test_defaults_has_llm_provider(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert "openclaw_llm_provider" in defaults

    def test_defaults_llm_provider_ollama(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert defaults["openclaw_llm_provider"] == "ollama"

    def test_defaults_has_llm_url(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert "openclaw_llm_url" in defaults

    def test_defaults_has_llm_api_key(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert "openclaw_llm_api_key" in defaults

    def test_defaults_has_llm_model(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "openclaw_server" / "defaults" / "main.yml").read_text()
        )
        assert "openclaw_llm_model" in defaults

    def test_systemd_override_template_has_llm_env_vars(self):
        tmpl = (
            BUILTIN_ROLES_DIR / "openclaw_server" / "templates" / "llm.conf.j2"
        ).read_text()
        assert "OPENCLAW_LLM_PROVIDER" in tmpl
        assert "OPENCLAW_LLM_URL" in tmpl
        assert "OPENCLAW_LLM_API_KEY" in tmpl
        assert "OPENCLAW_LLM_MODEL" in tmpl


# ===========================================================================
# 9. Mise a jour du role lobechat
# ===========================================================================


class TestLobechatRoleLlmVars:
    def test_defaults_has_llm_backend(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "lobechat" / "defaults" / "main.yml").read_text()
        )
        assert "lobechat_llm_backend" in defaults

    def test_defaults_has_llm_url(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "lobechat" / "defaults" / "main.yml").read_text()
        )
        assert "lobechat_llm_url" in defaults

    def test_defaults_has_llm_api_key(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "lobechat" / "defaults" / "main.yml").read_text()
        )
        assert "lobechat_llm_api_key" in defaults


# ===========================================================================
# 10. Mise a jour du role llm_sanitizer
# ===========================================================================


class TestSanitizerRoleUpdated:
    def test_defaults_has_audit(self):
        defaults = yaml.safe_load(
            (BUILTIN_ROLES_DIR / "llm_sanitizer" / "defaults" / "main.yml").read_text()
        )
        assert "sanitizer_audit" in defaults
        assert defaults["sanitizer_audit"] is True


# ===========================================================================
# 11. Integration host_vars — les vars enrichies passent au provisioner
# ===========================================================================


class TestHostVarsEnriched:
    def test_llm_effective_vars_in_host_vars(self):
        """Les vars llm_effective_* apparaissent dans host_vars."""
        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_effective_url": "https://api.openai.com/v1",
                "llm_effective_key": "sk-test",
                "llm_effective_model": "gpt-4o",
                "llm_effective_backend": "openai",
            },
        )
        domain = make_domain("pro", machines={"assistant": m_claw})
        infra = make_infra(domains={"pro": domain})

        host_vars = generate_host_vars(infra)
        assert "pro-assistant" in host_vars
        hv = host_vars["pro-assistant"]
        assert hv["llm_effective_url"] == "https://api.openai.com/v1"
        assert hv["llm_effective_backend"] == "openai"


# ===========================================================================
# 12. Integration playbook — role consommateur reçoit les vars
# ===========================================================================


class TestPlaybookWithLlmRouting:
    def test_openclaw_with_external_in_playbook(self):
        m = make_machine(
            "assistant",
            "pro",
            roles=["base", "openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
            },
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        plays = generate_playbook(infra)
        assert len(plays) == 1
        assert "openclaw_server" in plays[0]["roles"]

    def test_sanitizer_in_playbook(self):
        m = make_machine(
            "sanitizer", "pro", roles=["base", "llm_sanitizer"], ip="10.100.1.2"
        )
        domain = make_domain("pro", machines={"sanitizer": m})
        infra = make_infra(domains={"pro": domain})

        plays = generate_playbook(infra)
        assert any("llm_sanitizer" in p["roles"] for p in plays)


# ===========================================================================
# 13. Validation — llm_backend et ai_sanitize
# ===========================================================================


class TestLlmValidation:
    def test_valid_backend_accepted(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config("local", "false", "", "")
        assert len(errors) == 0

    def test_invalid_backend_rejected(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config("gemini", "false", "", "")
        assert any("llm_backend" in e for e in errors)

    def test_valid_ai_sanitize_accepted(self):
        from anklume.engine.llm_routing import validate_llm_config

        for val in ("false", "true", "always"):
            errors = validate_llm_config("local", val, "", "")
            assert len(errors) == 0

    def test_invalid_ai_sanitize_rejected(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config("local", "maybe", "", "")
        assert any("ai_sanitize" in e for e in errors)

    def test_external_without_url_rejected(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config("openai", "false", "", "sk-test")
        assert any("llm_api_url" in e for e in errors)

    def test_external_without_key_rejected(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config("openai", "false", "https://api.openai.com/v1", "")
        assert any("llm_api_key" in e for e in errors)

    def test_external_with_url_and_key_accepted(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config(
            "openai", "false", "https://api.openai.com/v1", "sk-test"
        )
        assert len(errors) == 0

    def test_local_ignores_url_key(self):
        from anklume.engine.llm_routing import validate_llm_config

        errors = validate_llm_config("local", "false", "", "")
        assert len(errors) == 0


# ===========================================================================
# 14. Sanitizer cross-domaine
# ===========================================================================


class TestCrossDomainSanitizer:
    def test_sanitizer_in_ai_tools_used_by_pro(self):
        """Sanitizer deploye dans ai-tools, consomme par pro."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m_san = make_machine(
            "sanitizer", "ai-tools", roles=["llm_sanitizer"], ip="10.100.3.2"
        )
        d_ai = make_domain("ai-tools", machines={"sanitizer": m_san})

        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "ai_sanitize": "true",
            },
        )
        d_pro = make_domain("pro", machines={"assistant": m_claw})

        infra = make_infra(domains={"ai-tools": d_ai, "pro": d_pro})

        ep = resolve_llm_endpoint(m_claw, d_pro, infra)
        assert ep.sanitized is True
        assert "10.100.3.2" in ep.url


# ===========================================================================
# 15. OpenRouter (abonnement) — cas reel
# ===========================================================================


class TestOpenRouterScenario:
    def test_openrouter_as_openai_backend(self):
        """OpenRouter utilise le format OpenAI-compatible."""
        from anklume.engine.llm_routing import resolve_llm_endpoint

        m = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://openrouter.ai/api/v1",
                "llm_api_key": "sk-or-test",
                "llm_model": "anthropic/claude-sonnet-4-20250514",
            },
        )
        domain = make_domain("pro", machines={"assistant": m})
        infra = make_infra(domains={"pro": domain})

        ep = resolve_llm_endpoint(m, domain, infra)
        assert ep.backend == "openai"
        assert "openrouter.ai" in ep.url
        assert ep.model == "anthropic/claude-sonnet-4-20250514"


# ===========================================================================
# 16. Integration pipeline provision — enrich_llm_vars cable
# ===========================================================================


class TestProvisionPipelineIntegration:
    def test_provision_calls_enrich(self, tmp_path):
        """provision() enrichit l'infra avant d'ecrire les fichiers."""
        from unittest.mock import patch

        from anklume.provisioner import provision

        m_ollama = make_machine(
            "gpu-server", "ai-tools", roles=["ollama_server"], ip="10.100.3.1"
        )
        m_claw = make_machine(
            "assistant",
            "ai-tools",
            roles=["openclaw_server"],
            ip="10.100.3.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
            },
        )
        domain = make_domain(
            "ai-tools",
            machines={"gpu-server": m_ollama, "assistant": m_claw},
        )
        infra = make_infra(domains={"ai-tools": domain})

        # Simuler ansible absent pour skipper l'execution reelle
        with patch("anklume.provisioner.ansible_available", return_value=False):
            result = provision(infra, tmp_path)

        assert result.skipped is True

    def test_enriched_host_vars_written(self, tmp_path):
        """Les host_vars ecrites contiennent les vars enrichies."""
        from unittest.mock import patch

        from anklume.provisioner import provision

        m_claw = make_machine(
            "assistant",
            "pro",
            roles=["openclaw_server"],
            ip="10.100.1.5",
            vars={
                "llm_backend": "openai",
                "llm_api_url": "https://api.openai.com/v1",
                "llm_api_key": "sk-test",
                "llm_model": "gpt-4o",
            },
        )
        domain = make_domain("pro", machines={"assistant": m_claw})
        infra = make_infra(domains={"pro": domain})

        # Simuler ansible disponible mais intercepter run_playbook
        with (
            patch("anklume.provisioner.ansible_available", return_value=True),
            patch("anklume.provisioner.run_playbook") as mock_run,
        ):
            from anklume.provisioner.runner import ProvisionResult

            mock_run.return_value = ProvisionResult(success=True)
            provision(infra, tmp_path)

        # Verifier que host_vars contient les vars enrichies
        hv_file = tmp_path / "ansible" / "host_vars" / "pro-assistant.yml"
        assert hv_file.exists()
        content = yaml.safe_load(hv_file.read_text())
        assert content["llm_effective_backend"] == "openai"
        assert content["llm_effective_url"] == "https://api.openai.com/v1"
        assert content["llm_effective_key"] == "sk-test"
        assert content["llm_effective_model"] == "gpt-4o"
