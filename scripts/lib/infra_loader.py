"""Shared infra.yml loader for standalone scripts.

Handles both single-file (infra.yml) and directory (infra/) formats.
Used by create-shares.py and create-data-dirs.py.
"""

import sys
from pathlib import Path

import yaml


def load_infra_from_path(path_str: str) -> dict:
    """Load infra dict from a file or directory path.

    Args:
        path_str: Path to infra.yml or infra/ directory.

    Returns:
        Parsed infra dict.

    Raises:
        SystemExit: If the path is invalid or base.yml not found.
    """
    infra_path = Path(path_str)
    if infra_path.is_dir():
        base_path = infra_path / "base.yml"
        if not base_path.exists():
            print(f"ERROR: {base_path} not found", file=sys.stderr)
            sys.exit(1)
        with open(base_path) as f:
            return yaml.safe_load(f) or {}
    with open(infra_path) as f:
        return yaml.safe_load(f) or {}
