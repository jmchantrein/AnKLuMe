"""PSOT generator package — Primary Source of Truth to Ansible files.

Public API re-exported here for backward compatibility.
"""

from psot.addressing import (
    _auto_assign_ips,
    _compute_addressing,
    _detect_host_subnets,
)
from psot.constants import (
    DEFAULT_TRUST_LEVEL,
    MANAGED_BEGIN,
    MANAGED_END,
    MANAGED_NOTICE,
    MANAGED_RE,
    ZONE_OFFSETS,
)
from psot.context import (
    _get_nesting_prefix,
    _read_absolute_level,
    _read_vm_nested,
    _read_yolo,
)
from psot.enrich_volumes import (
    _enrich_persistent_data,
    _enrich_shared_volumes,
)
from psot.enrichment import (
    _enrich_addressing,
    _enrich_ai_access,
    _enrich_firewall,
    enrich_infra,
)
from psot.generation import (
    _managed_block,
    _write_managed,
    extract_all_images,
    generate,
)
from psot.io import (
    _is_orphan_protected,
    _load_infra_dir,
    detect_orphans,
    load_infra,
)
from psot.resource_alloc import _enrich_resources
from psot.resources import (
    _apply_memory_enforce,
    _detect_host_resources,
    _format_memory,
    _parse_memory_value,
)
from psot.validation import (
    _collect_gpu_instances,
    validate,
)
from psot.warnings_mod import get_warnings
from psot.yaml_utils import _Dumper, _yaml

__all__ = [
    # Constants
    "DEFAULT_TRUST_LEVEL",
    "MANAGED_BEGIN",
    "MANAGED_END",
    "MANAGED_NOTICE",
    "MANAGED_RE",
    "ZONE_OFFSETS",
    # YAML
    "_Dumper",
    "_yaml",
    # Context
    "_get_nesting_prefix",
    "_read_absolute_level",
    "_read_vm_nested",
    "_read_yolo",
    # Addressing
    "_auto_assign_ips",
    "_compute_addressing",
    "_detect_host_subnets",
    # Resources
    "_apply_memory_enforce",
    "_detect_host_resources",
    "_enrich_resources",
    "_format_memory",
    "_parse_memory_value",
    # Validation
    "_collect_gpu_instances",
    "validate",
    # Warnings
    "get_warnings",
    # Enrichment
    "_enrich_addressing",
    "_enrich_ai_access",
    "_enrich_firewall",
    "_enrich_persistent_data",
    "_enrich_shared_volumes",
    "enrich_infra",
    # Generation
    "_managed_block",
    "_write_managed",
    "extract_all_images",
    "generate",
    # IO
    "_is_orphan_protected",
    "_load_infra_dir",
    "detect_orphans",
    "load_infra",
]
