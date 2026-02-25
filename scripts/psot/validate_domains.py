"""Validation of domain definitions."""

import re

from psot.constants import DEFAULT_TRUST_LEVEL
from psot.validate_machines import _validate_machine


def _validate_domains(
    domains, errors, g, base_subnet, has_addressing,
    computed_addressing, zone_subnet_ids, subnet_ids,
    all_machines, all_ips, valid_types, vm_nested, yolo,
):
    """Validate all domain and machine definitions."""
    for dname, domain in domains.items():
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", dname):
            errors.append(
                f"Domain '{dname}': invalid name "
                f"(lowercase alphanumeric + hyphen, "
                f"no trailing hyphen)"
            )
        enabled = domain.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            errors.append(
                f"Domain '{dname}': enabled must be a boolean, "
                f"got {type(enabled).__name__}"
            )

        sid = domain.get("subnet_id")
        if has_addressing:
            if sid is not None:
                if not isinstance(sid, int) or not 0 <= sid <= 254:
                    errors.append(
                        f"Domain '{dname}': subnet_id must be "
                        f"0-254, got {sid}"
                    )
                else:
                    trust = domain.get(
                        "trust_level", DEFAULT_TRUST_LEVEL
                    )
                    zone_key = (trust, sid)
                    if zone_key in zone_subnet_ids:
                        errors.append(
                            f"Domain '{dname}': subnet_id {sid} "
                            f"already used by "
                            f"'{zone_subnet_ids[zone_key]}' "
                            f"in zone '{trust}'"
                        )
                    else:
                        zone_subnet_ids[zone_key] = dname
        else:
            if sid is None:
                errors.append(
                    f"Domain '{dname}': missing subnet_id"
                )
            elif not isinstance(sid, int) or not 0 <= sid <= 254:
                errors.append(
                    f"Domain '{dname}': subnet_id must be 0-254, "
                    f"got {sid}"
                )
            elif sid in subnet_ids:
                errors.append(
                    f"Domain '{dname}': subnet_id {sid} already "
                    f"used by '{subnet_ids[sid]}'"
                )
            else:
                subnet_ids[sid] = dname

        domain_eph = domain.get("ephemeral")
        if domain_eph is not None and not isinstance(
            domain_eph, bool
        ):
            errors.append(
                f"Domain '{dname}': ephemeral must be a boolean, "
                f"got {type(domain_eph).__name__}"
            )

        valid_trust_levels = (
            "admin", "trusted", "semi-trusted",
            "untrusted", "disposable",
        )
        trust_level = domain.get("trust_level")
        if (
            trust_level is not None
            and trust_level not in valid_trust_levels
        ):
            errors.append(
                f"Domain '{dname}': trust_level must be one of "
                f"{valid_trust_levels}, got '{trust_level}'"
            )

        # ai_provider and ai_sanitize validation (Phase 39)
        valid_ai_providers = ("local", "cloud", "local-first")
        ai_provider = domain.get("ai_provider")
        if (
            ai_provider is not None
            and ai_provider not in valid_ai_providers
        ):
            errors.append(
                f"Domain '{dname}': ai_provider must be one of "
                f"{valid_ai_providers}, got '{ai_provider}'"
            )
        valid_ai_sanitize = (True, False, "always")
        ai_sanitize = domain.get("ai_sanitize")
        if (
            ai_sanitize is not None
            and ai_sanitize not in valid_ai_sanitize
        ):
            errors.append(
                f"Domain '{dname}': ai_sanitize must be true, "
                f"false, or 'always', got '{ai_sanitize}'"
            )

        domain_profiles = domain.get("profiles") or {}
        domain_profile_names = set(domain_profiles)
        for mname, machine in (
            domain.get("machines") or {}
        ).items():
            _validate_machine(
                mname, machine, dname, errors, g, base_subnet,
                sid, has_addressing, computed_addressing,
                all_machines, all_ips, valid_types,
                domain_profile_names, vm_nested, yolo,
            )
