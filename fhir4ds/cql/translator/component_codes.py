"""Shared component code mapping loaded from JSON configuration.

Single source of truth for BP LOINC codes and their column mappings.
Used by both expressions.py and property_scanner.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from ..paths import get_resource_path

_COMPONENT_CODES: Optional[Dict] = None


def get_component_code_mapping() -> Dict[str, dict]:
    """Load component code mapping from configuration file.

    Returns:
        Dict mapping LOINC codes to their column/name info.
        Example: {"8480-6": {"name": "systolic", "column": "systolic_value"}}
    """
    global _COMPONENT_CODES
    if _COMPONENT_CODES is None:
        path = get_resource_path("terminology", "component_codes.json")
        with open(path) as f:
            raw = json.load(f)
        _COMPONENT_CODES = {k: v for k, v in raw.items() if not k.startswith("_")}
    return _COMPONENT_CODES


def get_code_to_column_mapping() -> Dict[str, str]:
    """Get a simple code -> column_name mapping for use in expressions.py."""
    return {code: info["column"] for code, info in get_component_code_mapping().items()}


def get_code_to_name_mapping() -> Dict[str, str]:
    """Get a simple code -> name mapping for use in property_scanner.py."""
    return {code: info["name"] for code, info in get_component_code_mapping().items()}
