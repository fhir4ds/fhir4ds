"""Package version consistency tests."""

from __future__ import annotations

from pathlib import Path
import re

import fhir4ds
import fhir4ds.cql
import fhir4ds.dqm
import fhir4ds.fhirpath
import fhir4ds.fhirpath.duckdb
import fhir4ds.viewdef


def test_public_subpackage_versions_match_root() -> None:
    expected = fhir4ds.__version__
    assert fhir4ds.cql.__version__ == expected
    assert fhir4ds.dqm.__version__ == expected
    assert fhir4ds.fhirpath.__version__ == expected
    assert fhir4ds.fhirpath.duckdb.__version__ == expected
    assert fhir4ds.viewdef.__version__ == expected


def test_pyproject_version_matches_public_root_version() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    match = re.search(
        r"(?ms)^\[project\]\s+.*?^version\s*=\s*\"([^\"]+)\"",
        pyproject.read_text(),
    )

    assert match is not None
    assert match.group(1) == fhir4ds.__version__
