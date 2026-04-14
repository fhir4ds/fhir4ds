"""
Version configuration for the FHIR/QI Core schema layer.

Provides ModelConfig which carries version configuration through the translator,
controlling which schema versions are used for type resolution, profile lookup,
and extension path mapping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from ..paths import get_resource_path


@dataclass
class ModelConfig:
    """
    Version configuration for the FHIR/QI Core schema layer.

    Pass an instance to CQLToSQLTranslator to control which schema
    versions are used for type resolution, profile lookup, and
    extension path mapping.

    Default is the current production target (QI Core 4.1.1 / US Core 3.1.1).
    """

    fhir_r4_version: str = "4.0.1"
    us_core_version: str = "3.1.1"
    qicore_version: str = "4.1.1"

    schema_root: Path = field(
        default_factory=lambda: get_resource_path("schema")
    )

    @property
    def fhir_r4_dir(self) -> Path:
        return self.schema_root / f"fhir-r4-{self.fhir_r4_version}"

    @property
    def us_core_dir(self) -> Path:
        return self.schema_root / f"us-core-{self.us_core_version}"

    @property
    def qicore_dir(self) -> Path:
        return self.schema_root / f"qicore-{self.qicore_version}"

    def validate(self) -> List[str]:
        """Return list of error messages if any required directories are missing."""
        errors: List[str] = []
        for label, path in [
            ("FHIR R4", self.fhir_r4_dir),
            ("US Core", self.us_core_dir),
            ("QI Core", self.qicore_dir),
        ]:
            meta = path / "metadata.json"
            if not meta.exists():
                errors.append(f"{label} schema not found at {path}")
            else:
                m = json.loads(meta.read_text())
                if m.get("status") == "not-implemented":
                    errors.append(
                        f"{label} schema at {path} is not yet implemented: "
                        f"{m.get('notes', '')}"
                    )
        return errors


DEFAULT_MODEL_CONFIG = ModelConfig()
