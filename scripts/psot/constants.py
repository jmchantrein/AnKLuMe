"""Shared constants for the PSOT generator."""

import re

# Zone offsets for trust-level-aware addressing (ADR-038)
ZONE_OFFSETS = {
    "admin": 0,
    "trusted": 10,
    "semi-trusted": 20,
    "untrusted": 40,
    "disposable": 50,
}
DEFAULT_TRUST_LEVEL = "semi-trusted"

MANAGED_BEGIN = "# === MANAGED BY infra.yml ==="
MANAGED_END = "# === END MANAGED ==="
MANAGED_NOTICE = (
    "# Do not edit this section — it will be overwritten by `make sync`"
)
MANAGED_RE = re.compile(
    re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END), re.DOTALL
)
