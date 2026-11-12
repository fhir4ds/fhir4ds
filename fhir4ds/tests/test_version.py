"""Package version consistency tests."""

from __future__ import annotations

import re
from pathlib import Path

import importlib

import fhir4ds


def _version_packages() -> list[str]:
    """Every package in the tree whose __init__ declares __version__.

    Enumerated from disk rather than listed by hand: the hand-maintained list
    silently omitted ``fhir4ds.sqlquery``, which sat at the previous release
    version through a release bump. A new subpackage cannot drift now.
    """
    root = Path(__file__).resolve().parents[1]
    packages = []
    for init in sorted(root.rglob("__init__.py")):
        if "__pycache__" in init.parts:
            continue
        # Test-harness packages (e.g. fhir4ds.dqm.tests.conformance) carry
        # their OWN version for the runner and are not part of the public
        # release surface.
        if "tests" in init.parts or "conformance" in init.parts:
            continue
        if '__version__ = "' in init.read_text():
            packages.append(".".join(init.parent.relative_to(root.parent).parts))
    return packages


def test_every_package_version_matches_root() -> None:
    expected = fhir4ds.__version__
    packages = _version_packages()
    assert "fhir4ds" in packages and "fhir4ds.sqlquery" in packages
    mismatched = {}
    for name in packages:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", None)
        if version != expected:
            mismatched[name] = version
    assert not mismatched, f"version drift vs {expected}: {mismatched}"


def test_pyproject_version_matches_public_root_version() -> None:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    match = re.search(
        r"(?ms)^\[project\]\s+.*?^version\s*=\s*\"([^\"]+)\"",
        pyproject.read_text(),
    )

    assert match is not None
    assert match.group(1) == fhir4ds.__version__
