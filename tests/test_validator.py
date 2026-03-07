"""Tests du validateur d'infrastructure anklume."""

from anklume.engine.models import (
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
    Policy,
    Profile,
)
from anklume.engine.validator import validate


def _minimal_infra(**kwargs) -> Infrastructure:
    """Infrastructure minimale valide."""
    config = kwargs.get("config", GlobalConfig())
    domains = kwargs.get(
        "domains",
        {
            "pro": Domain(
                name="pro",
                description="Test",
                machines={
                    "dev": Machine(name="dev", full_name="pro-dev", description="Dev"),
                },
            ),
        },
    )
    policies = kwargs.get("policies", [])
    return Infrastructure(config=config, domains=domains, policies=policies)


class TestValidInfrastructure:
    def test_minimal_passes(self):
        result = validate(_minimal_infra())
        assert result.valid

    def test_empty_domains_valid(self):
        result = validate(_minimal_infra(domains={}))
        assert result.valid

    def test_valid_domain_names(self):
        for name in ["pro", "ai-tools", "a", "test123", "my-domain-2"]:
            result = validate(
                _minimal_infra(
                    domains={
                        name: Domain(name=name, description="T"),
                    }
                )
            )
            assert result.valid, f"'{name}' devrait être valide"

    def test_valid_profile_reference(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        profiles={"custom": Profile(name="custom")},
                        machines={
                            "dev": Machine(
                                name="dev",
                                full_name="pro-dev",
                                description="D",
                                profiles=["default", "custom"],
                            ),
                        },
                    ),
                }
            )
        )
        assert result.valid

    def test_policy_host_target_valid(self):
        infra = _minimal_infra(
            policies=[
                Policy(description="T", from_target="host", to_target="pro", ports=[80]),
            ]
        )
        result = validate(infra)
        assert result.valid

    def test_policy_machine_target_valid(self):
        infra = _minimal_infra(
            policies=[
                Policy(description="T", from_target="pro-dev", to_target="host", ports=[22]),
            ]
        )
        result = validate(infra)
        assert result.valid


class TestDomainNameValidation:
    def test_uppercase_rejected(self):
        result = validate(
            _minimal_infra(
                domains={
                    "INVALID": Domain(name="INVALID", description="T"),
                }
            )
        )
        assert not result.valid
        assert any("nom de domaine" in str(e) for e in result.errors)

    def test_underscore_rejected(self):
        result = validate(
            _minimal_infra(
                domains={
                    "my_domain": Domain(name="my_domain", description="T"),
                }
            )
        )
        assert not result.valid

    def test_leading_hyphen_rejected(self):
        result = validate(
            _minimal_infra(
                domains={
                    "-bad": Domain(name="-bad", description="T"),
                }
            )
        )
        assert not result.valid

    def test_trailing_hyphen_rejected(self):
        result = validate(
            _minimal_infra(
                domains={
                    "bad-": Domain(name="bad-", description="T"),
                }
            )
        )
        assert not result.valid


class TestTrustLevelValidation:
    def test_invalid_trust_level(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(name="pro", description="T", trust_level="top-secret"),
                }
            )
        )
        assert not result.valid
        assert any("trust_level" in str(e) for e in result.errors)

    def test_all_valid_trust_levels(self):
        for level in ["admin", "trusted", "semi-trusted", "untrusted", "disposable"]:
            result = validate(
                _minimal_infra(
                    domains={
                        "pro": Domain(name="pro", description="T", trust_level=level),
                    }
                )
            )
            assert result.valid, f"'{level}' devrait être valide"


class TestMachineValidation:
    def test_duplicate_full_names(self):
        d1 = Domain(
            name="pro",
            description="T",
            machines={
                "dev": Machine(name="dev", full_name="pro-dev", description="D"),
            },
        )
        d2 = Domain(
            name="test",
            description="T",
            machines={
                "x": Machine(name="x", full_name="pro-dev", description="D"),
            },
        )
        result = validate(_minimal_infra(domains={"pro": d1, "test": d2}))
        assert not result.valid
        assert any("conflit" in str(e) for e in result.errors)

    def test_different_full_names_ok(self):
        d1 = Domain(
            name="pro",
            description="T",
            machines={
                "dev": Machine(name="dev", full_name="pro-dev", description="D"),
            },
        )
        d2 = Domain(
            name="perso",
            description="T",
            machines={
                "dev": Machine(name="dev", full_name="perso-dev", description="D"),
            },
        )
        result = validate(_minimal_infra(domains={"pro": d1, "perso": d2}))
        assert result.valid

    def test_invalid_machine_name(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "CAPS": Machine(name="CAPS", full_name="pro-CAPS", description="D"),
                        },
                    ),
                }
            )
        )
        assert not result.valid

    def test_invalid_machine_type(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "dev": Machine(
                                name="dev",
                                full_name="pro-dev",
                                description="D",
                                type="docker",
                            ),
                        },
                    ),
                }
            )
        )
        assert not result.valid
        assert any("type" in str(e) for e in result.errors)

    def test_invalid_weight_zero(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "dev": Machine(
                                name="dev",
                                full_name="pro-dev",
                                description="D",
                                weight=0,
                            ),
                        },
                    ),
                }
            )
        )
        assert not result.valid
        assert any("weight" in str(e) for e in result.errors)

    def test_negative_weight(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "dev": Machine(
                                name="dev",
                                full_name="pro-dev",
                                description="D",
                                weight=-1,
                            ),
                        },
                    ),
                }
            )
        )
        assert not result.valid


class TestIPValidation:
    def test_invalid_ip_format(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "dev": Machine(
                                name="dev",
                                full_name="pro-dev",
                                description="D",
                                ip="not-an-ip",
                            ),
                        },
                    ),
                }
            )
        )
        assert not result.valid
        assert any("IP" in str(e) for e in result.errors)

    def test_duplicate_ips(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "a": Machine(
                                name="a",
                                full_name="pro-a",
                                description="A",
                                ip="10.120.0.1",
                            ),
                            "b": Machine(
                                name="b",
                                full_name="pro-b",
                                description="B",
                                ip="10.120.0.1",
                            ),
                        },
                    ),
                }
            )
        )
        assert not result.valid
        assert any("déjà utilisée" in str(e) for e in result.errors)

    def test_duplicate_ips_cross_domain(self):
        d1 = Domain(
            name="pro",
            description="T",
            machines={
                "a": Machine(
                    name="a",
                    full_name="pro-a",
                    description="A",
                    ip="10.120.0.1",
                ),
            },
        )
        d2 = Domain(
            name="perso",
            description="T",
            machines={
                "b": Machine(
                    name="b",
                    full_name="perso-b",
                    description="B",
                    ip="10.120.0.1",
                ),
            },
        )
        result = validate(_minimal_infra(domains={"pro": d1, "perso": d2}))
        assert not result.valid

    def test_no_ip_is_valid(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "dev": Machine(name="dev", full_name="pro-dev", description="D"),
                        },
                    ),
                }
            )
        )
        assert result.valid


class TestProfileValidation:
    def test_missing_profile_reference(self):
        result = validate(
            _minimal_infra(
                domains={
                    "pro": Domain(
                        name="pro",
                        description="T",
                        machines={
                            "dev": Machine(
                                name="dev",
                                full_name="pro-dev",
                                description="D",
                                profiles=["default", "nonexistent"],
                            ),
                        },
                    ),
                }
            )
        )
        assert not result.valid
        assert any("profil" in str(e) for e in result.errors)


class TestSchemaVersion:
    def test_too_high(self):
        config = GlobalConfig(schema_version=999)
        result = validate(_minimal_infra(config=config))
        assert not result.valid
        assert any("plus récent" in str(e) for e in result.errors)

    def test_too_low(self):
        config = GlobalConfig(schema_version=0)
        result = validate(_minimal_infra(config=config))
        assert not result.valid
        assert any("obsolète" in str(e) for e in result.errors)

    def test_current_version_ok(self):
        result = validate(_minimal_infra())
        assert result.valid


class TestPolicyValidation:
    def test_invalid_from_target(self):
        infra = _minimal_infra(
            policies=[
                Policy(
                    description="T",
                    from_target="nonexistent",
                    to_target="pro",
                    ports=[80],
                ),
            ]
        )
        result = validate(infra)
        assert not result.valid
        assert any("ne correspond" in str(e) for e in result.errors)

    def test_invalid_to_target(self):
        infra = _minimal_infra(
            policies=[
                Policy(
                    description="T",
                    from_target="pro",
                    to_target="nonexistent",
                    ports=[80],
                ),
            ]
        )
        result = validate(infra)
        assert not result.valid

    def test_invalid_protocol(self):
        infra = _minimal_infra(
            policies=[
                Policy(
                    description="T",
                    from_target="pro",
                    to_target="host",
                    ports=[80],
                    protocol="icmp",
                ),
            ]
        )
        result = validate(infra)
        assert not result.valid
        assert any("protocole" in str(e) for e in result.errors)


class TestMultipleErrors:
    def test_errors_collected(self):
        result = validate(
            _minimal_infra(
                domains={
                    "INVALID": Domain(
                        name="INVALID",
                        description="T",
                        trust_level="bad",
                        machines={
                            "x": Machine(
                                name="x",
                                full_name="INVALID-x",
                                description="D",
                                type="docker",
                                weight=0,
                            ),
                        },
                    ),
                }
            )
        )
        assert len(result.errors) >= 3

    def test_str_representation(self):
        result = validate(
            _minimal_infra(
                domains={
                    "INVALID": Domain(name="INVALID", description="T"),
                }
            )
        )
        text = str(result)
        assert "erreur(s) de validation" in text

    def test_valid_str_representation(self):
        result = validate(_minimal_infra())
        assert str(result) == "Validation OK"
