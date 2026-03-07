"""Tests du calcul d'adressage automatique."""

from anklume.engine.addressing import assign_addresses
from anklume.engine.models import (
    AddressingConfig,
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
)


def _make_infra(domains_data: dict, base: str = "10.100") -> Infrastructure:
    """Construire une Infrastructure depuis un dict simplifié."""
    config = GlobalConfig(addressing=AddressingConfig(base=base))
    domains = {}
    for name, d in domains_data.items():
        machines = {}
        for mname, mdata in d.get("machines", {}).items():
            machines[mname] = Machine(
                name=mname,
                full_name=f"{name}-{mname}",
                description=mdata.get("description", "test"),
                ip=mdata.get("ip"),
            )
        domains[name] = Domain(
            name=name,
            description=d.get("description", "test"),
            trust_level=d.get("trust_level", "semi-trusted"),
            enabled=d.get("enabled", True),
            machines=machines,
        )
    return Infrastructure(config=config, domains=domains, policies=[])


class TestBasicAssignment:
    def test_single_domain_single_machine(self):
        infra = _make_infra(
            {
                "pro": {
                    "trust_level": "semi-trusted",
                    "machines": {"dev": {}},
                },
            }
        )

        assign_addresses(infra)

        assert infra.domains["pro"].machines["dev"].ip == "10.120.0.1"

    def test_machines_assigned_alphabetically(self):
        infra = _make_infra(
            {
                "pro": {
                    "trust_level": "semi-trusted",
                    "machines": {"zulu": {}, "alpha": {}, "mike": {}},
                },
            }
        )

        assign_addresses(infra)
        machines = infra.domains["pro"].machines

        assert machines["alpha"].ip == "10.120.0.1"
        assert machines["mike"].ip == "10.120.0.2"
        assert machines["zulu"].ip == "10.120.0.3"

    def test_subnet_and_gateway_set(self):
        infra = _make_infra(
            {
                "pro": {
                    "trust_level": "semi-trusted",
                    "machines": {"dev": {}},
                },
            }
        )

        assign_addresses(infra)

        assert infra.domains["pro"].subnet == "10.120.0.0/24"
        assert infra.domains["pro"].gateway == "10.120.0.254"


class TestTrustLevelZones:
    def test_admin_zone(self):
        infra = _make_infra(
            {
                "mgmt": {"trust_level": "admin", "machines": {"a": {}}},
            }
        )

        assign_addresses(infra)

        assert infra.domains["mgmt"].machines["a"].ip.startswith("10.100.")

    def test_trusted_zone(self):
        infra = _make_infra(
            {
                "safe": {"trust_level": "trusted", "machines": {"a": {}}},
            }
        )

        assign_addresses(infra)

        assert infra.domains["safe"].machines["a"].ip.startswith("10.110.")

    def test_untrusted_zone(self):
        infra = _make_infra(
            {
                "risky": {"trust_level": "untrusted", "machines": {"a": {}}},
            }
        )

        assign_addresses(infra)

        assert infra.domains["risky"].machines["a"].ip.startswith("10.140.")

    def test_disposable_zone(self):
        infra = _make_infra(
            {
                "throwaway": {"trust_level": "disposable", "machines": {"tmp": {}}},
            }
        )

        assign_addresses(infra)

        assert infra.domains["throwaway"].machines["tmp"].ip.startswith("10.150.")

    def test_different_zones_different_octets(self):
        infra = _make_infra(
            {
                "admin-zone": {"trust_level": "admin", "machines": {"a": {}}},
                "untrust": {"trust_level": "untrusted", "machines": {"b": {}}},
            }
        )

        assign_addresses(infra)

        ip_admin = infra.domains["admin-zone"].machines["a"].ip
        ip_untrust = infra.domains["untrust"].machines["b"].ip
        assert ip_admin.split(".")[1] != ip_untrust.split(".")[1]


class TestMultipleDomainsSameZone:
    def test_alphabetical_domain_seq(self):
        infra = _make_infra(
            {
                "beta": {"trust_level": "trusted", "machines": {"x": {}}},
                "alpha": {"trust_level": "trusted", "machines": {"y": {}}},
            }
        )

        assign_addresses(infra)

        assert infra.domains["alpha"].machines["y"].ip == "10.110.0.1"
        assert infra.domains["beta"].machines["x"].ip == "10.110.1.1"

    def test_different_subnets(self):
        infra = _make_infra(
            {
                "alpha": {"trust_level": "trusted", "machines": {"a": {}}},
                "beta": {"trust_level": "trusted", "machines": {"b": {}}},
            }
        )

        assign_addresses(infra)

        assert infra.domains["alpha"].subnet == "10.110.0.0/24"
        assert infra.domains["beta"].subnet == "10.110.1.0/24"


class TestExistingIPs:
    def test_preserved(self):
        infra = _make_infra(
            {
                "pro": {
                    "trust_level": "semi-trusted",
                    "machines": {
                        "fixed": {"ip": "10.120.0.42"},
                        "auto": {},
                    },
                },
            }
        )

        assign_addresses(infra)

        assert infra.domains["pro"].machines["fixed"].ip == "10.120.0.42"
        assert infra.domains["pro"].machines["auto"].ip == "10.120.0.1"

    def test_host_number_skipped(self):
        infra = _make_infra(
            {
                "pro": {
                    "trust_level": "semi-trusted",
                    "machines": {
                        "fixed": {"ip": "10.120.0.1"},
                        "auto": {},
                    },
                },
            }
        )

        assign_addresses(infra)

        assert infra.domains["pro"].machines["fixed"].ip == "10.120.0.1"
        assert infra.domains["pro"].machines["auto"].ip == "10.120.0.2"


class TestDisabledDomains:
    def test_skipped(self):
        infra = _make_infra(
            {
                "disabled": {
                    "enabled": False,
                    "trust_level": "admin",
                    "machines": {"x": {}},
                },
            }
        )

        assign_addresses(infra)

        assert infra.domains["disabled"].machines["x"].ip is None
        assert infra.domains["disabled"].subnet is None

    def test_no_impact_on_seq(self):
        infra = _make_infra(
            {
                "active": {"trust_level": "trusted", "machines": {"a": {}}},
                "disabled": {
                    "enabled": False,
                    "trust_level": "trusted",
                    "machines": {"b": {}},
                },
            }
        )

        assign_addresses(infra)

        assert infra.domains["active"].machines["a"].ip == "10.110.0.1"
        assert infra.domains["active"].subnet == "10.110.0.0/24"


class TestCustomBase:
    def test_different_base(self):
        infra = _make_infra(
            {"pro": {"trust_level": "admin", "machines": {"dev": {}}}},
            base="172.16",
        )

        assign_addresses(infra)

        assert infra.domains["pro"].machines["dev"].ip == "172.16.0.1"
