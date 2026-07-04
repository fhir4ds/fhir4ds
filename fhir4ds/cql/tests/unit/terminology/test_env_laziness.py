"""INV-4: env-var reads are lazy — never at module import time.

Importing ``factory`` (and the parent ``terminology`` package) MUST NOT
touch ``FHIR4DS_TERMINOLOGY_*`` env vars. Only calling
``get_terminology_endpoint()`` reads them.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import patch

import pytest


@pytest.fixture
def getenv_spy() -> list[str]:
    """Records every env var name looked up via os.getenv."""
    records: list[str] = []
    real_getenv = os.getenv

    def _spy(name: str, default: object = None) -> object:
        if name.startswith("FHIR4DS_TERMINOLOGY_"):
            records.append(name)
        return real_getenv(name, default)

    patcher = patch("fhir4ds.cql.terminology.factory.os.getenv", side_effect=_spy)
    patcher.start()
    try:
        yield records
    finally:
        patcher.stop()


def _reload_factory() -> None:
    for mod in (
        "fhir4ds.cql.terminology.factory",
        "fhir4ds.cql.terminology",
    ):
        if mod in sys.modules:
            del sys.modules[mod]


def test_module_import_does_not_read_env_vars(getenv_spy: list[str]) -> None:
    """Re-importing factory must not produce any FHIR4DS_TERMINOLOGY_* lookups."""
    _reload_factory()
    importlib.import_module("fhir4ds.cql.terminology.factory")
    assert getenv_spy == [], (
        "Importing factory must not read FHIR4DS_TERMINOLOGY_* env vars (INV-4); "
        f"saw: {getenv_spy}"
    )


def test_calling_factory_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling get_terminology_endpoint() must read FHIR4DS_TERMINOLOGY_MODE."""
    # Ensure disabled so we get a None result without needing deps.
    monkeypatch.setenv("FHIR4DS_TERMINOLOGY_MODE", "disabled")
    from fhir4ds.cql.terminology import get_terminology_endpoint

    records: list[str] = []
    real_getenv = os.getenv

    def _spy(name: str, default: object = None) -> object:
        if name.startswith("FHIR4DS_TERMINOLOGY_"):
            records.append(name)
        return real_getenv(name, default)

    with patch("fhir4ds.cql.terminology.factory.os.getenv", side_effect=_spy):
        result = get_terminology_endpoint()
    assert result is None
    assert "FHIR4DS_TERMINOLOGY_MODE" in records
