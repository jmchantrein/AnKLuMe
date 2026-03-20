"""Tests du parser anklume (YAML → modèles typés)."""

import pytest
import yaml

from anklume.engine.parser import ParseError, parse_project


def _write_anklume_yml(path, schema_version=1):
    data = {
        "schema_version": schema_version,
        "defaults": {"os_image": "images:debian/13", "trust_level": "semi-trusted"},
        "addressing": {"base": "10.100", "zone_step": 10},
        "nesting": {"prefix": True},
    }
    (path / "anklume.yml").write_text(yaml.dump(data))


def _write_domain(path, name, data):
    domains_dir = path / "domains"
    domains_dir.mkdir(exist_ok=True)
    (domains_dir / f"{name}.yml").write_text(yaml.dump(data))


def _write_policies(path, policies):
    (path / "policies.yml").write_text(yaml.dump({"policies": policies}))


class TestParseProject:
    def test_minimal_valid(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Test domain",
                "machines": {"dev": {"description": "Dev machine"}},
            },
        )

        infra = parse_project(tmp_path)

        assert "pro" in infra.domains
        assert "dev" in infra.domains["pro"].machines
        assert infra.domains["pro"].machines["dev"].full_name == "pro-dev"

    def test_missing_anklume_yml(self, tmp_path):
        with pytest.raises(ParseError, match="introuvable"):
            parse_project(tmp_path)

    def test_empty_domain_file(self, tmp_path):
        _write_anklume_yml(tmp_path)
        (tmp_path / "domains").mkdir()
        (tmp_path / "domains" / "empty.yml").write_text("")

        with pytest.raises(ParseError, match="vide"):
            parse_project(tmp_path)

    def test_domain_missing_description(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "machines": {"dev": {"description": "test"}},
            },
        )

        with pytest.raises(ParseError, match="description"):
            parse_project(tmp_path)

    def test_machine_missing_description(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Test",
                "machines": {"dev": {"type": "lxc"}},
            },
        )

        with pytest.raises(ParseError, match="description"):
            parse_project(tmp_path)

    def test_defaults_applied(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Test",
                "machines": {"dev": {"description": "Dev"}},
            },
        )

        infra = parse_project(tmp_path)
        machine = infra.domains["pro"].machines["dev"]

        assert machine.type == "lxc"
        assert machine.weight == 1
        assert machine.profiles == ["default"]
        assert machine.gpu is False

    def test_ephemeral_inheritance(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Test",
                "ephemeral": True,
                "machines": {
                    "inherits": {"description": "Inherits"},
                    "overrides": {"description": "Overrides", "ephemeral": False},
                },
            },
        )

        infra = parse_project(tmp_path)

        assert infra.domains["pro"].machines["inherits"].ephemeral is True
        assert infra.domains["pro"].machines["overrides"].ephemeral is False

    def test_schema_version_parsed(self, tmp_path):
        _write_anklume_yml(tmp_path, schema_version=2)

        infra = parse_project(tmp_path)

        assert infra.config.schema_version == 2

    def test_no_domains_dir(self, tmp_path):
        _write_anklume_yml(tmp_path)

        infra = parse_project(tmp_path)

        assert infra.domains == {}

    def test_multiple_domains(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Pro",
                "machines": {"dev": {"description": "Dev"}},
            },
        )
        _write_domain(
            tmp_path,
            "perso",
            {
                "description": "Perso",
                "machines": {"web": {"description": "Web"}},
            },
        )

        infra = parse_project(tmp_path)

        assert len(infra.domains) == 2
        assert "pro" in infra.domains
        assert "perso" in infra.domains

    def test_all_machine_fields(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Test",
                "machines": {
                    "full": {
                        "description": "Full machine",
                        "type": "vm",
                        "ip": "10.120.0.5",
                        "ephemeral": True,
                        "gpu": True,
                        "profiles": ["default", "gpu-passthrough"],
                        "roles": ["base", "desktop"],
                        "config": {"limits.cpu": "4"},
                        "persistent": {"data": "/srv/data"},
                        "vars": {"custom_var": "value"},
                        "weight": 3,
                    },
                },
            },
        )

        infra = parse_project(tmp_path)
        m = infra.domains["pro"].machines["full"]

        assert m.type == "vm"
        assert m.ip == "10.120.0.5"
        assert m.ephemeral is True
        assert m.gpu is True
        assert m.profiles == ["default", "gpu-passthrough"]
        assert m.roles == ["base", "desktop"]
        assert m.config == {"limits.cpu": "4"}
        assert m.persistent == {"data": "/srv/data"}
        assert m.vars == {"custom_var": "value"}
        assert m.weight == 3

    def test_profiles_parsed(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_domain(
            tmp_path,
            "pro",
            {
                "description": "Test",
                "profiles": {
                    "gpu-passthrough": {
                        "devices": {"gpu": {"type": "gpu"}},
                    },
                },
                "machines": {"dev": {"description": "Dev"}},
            },
        )

        infra = parse_project(tmp_path)

        assert "gpu-passthrough" in infra.domains["pro"].profiles
        prof = infra.domains["pro"].profiles["gpu-passthrough"]
        assert prof.devices == {"gpu": {"type": "gpu"}}

    def test_nesting_config_parsed(self, tmp_path):
        _write_anklume_yml(tmp_path)

        infra = parse_project(tmp_path)

        assert infra.config.nesting.prefix is True

    def test_resource_policy_parsed(self, tmp_path):
        (tmp_path / "anklume.yml").write_text(
            yaml.dump(
                {
                    "schema_version": 1,
                    "resource_policy": {
                        "host_reserve": {"cpu": "30%", "memory": "4GiB"},
                        "mode": "equal",
                        "overcommit": True,
                    },
                }
            )
        )

        infra = parse_project(tmp_path)
        rp = infra.config.resource_policy

        assert rp is not None
        assert rp.host_reserve_cpu == "30%"
        assert rp.host_reserve_memory == "4GiB"
        assert rp.mode == "equal"
        assert rp.overcommit is True

    def test_resource_policy_absent(self, tmp_path):
        _write_anklume_yml(tmp_path)

        infra = parse_project(tmp_path)

        assert infra.config.resource_policy is None


class TestParsePolicies:
    def test_policies_parsed(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_policies(
            tmp_path,
            [
                {"from": "pro", "to": "ai-tools", "ports": [11434], "description": "Test"},
            ],
        )

        infra = parse_project(tmp_path)

        assert len(infra.policies) == 1
        assert infra.policies[0].from_target == "pro"
        assert infra.policies[0].to_target == "ai-tools"
        assert infra.policies[0].ports == [11434]

    def test_policies_missing_from(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_policies(
            tmp_path,
            [
                {"to": "ai-tools", "description": "Test"},
            ],
        )

        with pytest.raises(ParseError, match="from"):
            parse_project(tmp_path)

    def test_policies_missing_description(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_policies(
            tmp_path,
            [
                {"from": "pro", "to": "ai-tools", "ports": [80]},
            ],
        )

        with pytest.raises(ParseError, match="description"):
            parse_project(tmp_path)

    def test_no_policies_file(self, tmp_path):
        _write_anklume_yml(tmp_path)

        infra = parse_project(tmp_path)

        assert infra.policies == []

    def test_empty_policies_file(self, tmp_path):
        _write_anklume_yml(tmp_path)
        (tmp_path / "policies.yml").write_text("")

        infra = parse_project(tmp_path)

        assert infra.policies == []

    def test_policies_bidirectional(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_policies(
            tmp_path,
            [
                {
                    "from": "pro",
                    "to": "perso",
                    "ports": "all",
                    "description": "Test",
                    "bidirectional": True,
                },
            ],
        )

        infra = parse_project(tmp_path)

        assert infra.policies[0].bidirectional is True
        assert infra.policies[0].ports == "all"

    def test_policies_defaults(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_policies(
            tmp_path,
            [
                {"from": "pro", "to": "perso", "ports": [80], "description": "Test"},
            ],
        )

        infra = parse_project(tmp_path)
        p = infra.policies[0]

        assert p.protocol == "tcp"
        assert p.bidirectional is False

    def test_policies_invalid_ports_string(self, tmp_path):
        _write_anklume_yml(tmp_path)
        _write_policies(
            tmp_path,
            [
                {"from": "pro", "to": "perso", "ports": "invalid", "description": "Test"},
            ],
        )

        with pytest.raises(ParseError, match="ports"):
            parse_project(tmp_path)


class TestMalformedYaml:
    """Tests de robustesse pour le parsing YAML malformé."""

    def test_malformed_yaml_anklume(self, tmp_path):
        """YAML invalide dans anklume.yml doit lever une erreur."""
        (tmp_path / "anklume.yml").write_text("key: 'unclosed quote\n  invalid: yaml:")
        with pytest.raises(yaml.YAMLError):
            parse_project(tmp_path)

    def test_malformed_yaml_domain(self, tmp_path):
        """YAML invalide dans un fichier domaine doit lever une erreur."""
        _write_anklume_yml(tmp_path)
        (tmp_path / "domains").mkdir()
        (tmp_path / "domains" / "bad.yml").write_text(
            "description: 'unclosed\n  machines:\n    - invalid: :"
        )
        with pytest.raises(yaml.YAMLError):
            parse_project(tmp_path)

    def test_non_dict_anklume_yml(self, tmp_path):
        """anklume.yml contenant une liste au lieu d'un dict lève ParseError."""
        (tmp_path / "anklume.yml").write_text("- item1\n- item2\n")
        with pytest.raises(ParseError, match="mapping YAML"):
            parse_project(tmp_path)

    def test_non_dict_domain_file(self, tmp_path):
        """Fichier domaine contenant une liste au lieu d'un dict lève ParseError."""
        _write_anklume_yml(tmp_path)
        (tmp_path / "domains").mkdir()
        (tmp_path / "domains" / "bad.yml").write_text("- item1\n- item2\n")
        with pytest.raises(ParseError, match="mapping YAML"):
            parse_project(tmp_path)

    def test_malformed_yaml_policies(self, tmp_path):
        """YAML invalide dans policies.yml doit lever une erreur."""
        _write_anklume_yml(tmp_path)
        (tmp_path / "policies.yml").write_text("policies:\n  - from: 'unclosed\n    bad: :")
        with pytest.raises(yaml.YAMLError):
            parse_project(tmp_path)
