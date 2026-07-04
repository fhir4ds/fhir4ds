"""INV-3: adapter modules must not pull their sibling's optional dependency.

Importing ``http_adapter`` MUST NOT leave ``medterm4ds`` in
``sys.modules``; importing ``in_process_adapter`` MUST NOT leave
``httpx`` in ``sys.modules``. Guards against future regressions where a
stray ``import medterm4ds`` at the top of one adapter couples the two.
"""

from __future__ import annotations

import importlib
import sys


def _reload(name: str) -> None:
    if name in sys.modules:
        del sys.modules[name]


def test_http_adapter_does_not_import_medterm4ds() -> None:
    # Make sure medterm4ds is not in sys.modules before the test.
    sys.modules.pop("medterm4ds", None)
    sys.modules.pop("medterm4ds.services", None)
    sys.modules.pop("medterm4ds.engines", None)

    # Re-import http_adapter fresh.
    _reload("fhir4ds.cql.terminology.http_adapter")
    importlib.import_module("fhir4ds.cql.terminology.http_adapter")

    assert "medterm4ds" not in sys.modules, (
        "http_adapter must not import medterm4ds (INV-3 isolation)"
    )


def test_in_process_adapter_does_not_import_httpx() -> None:
    """in_process_adapter should not import httpx at module load time.

    Note: this test only checks the *module body*. Constructing the
    adapter still does not import httpx, but the assertion here is at
    import scope (the strongest static guarantee).
    """
    sys.modules.pop("httpx", None)

    # We can't safely construct the in-process adapter without medterm4ds,
    # but importing the module should not pull httpx regardless.
    _reload("fhir4ds.cql.terminology.in_process_adapter")
    try:
        importlib.import_module("fhir4ds.cql.terminology.in_process_adapter")
    except ImportError:
        # medterm4ds may be missing in the test env; that's fine — the
        # assertion is about httpx specifically.
        pass

    assert "httpx" not in sys.modules, (
        "in_process_adapter must not import httpx (INV-3 isolation)"
    )


def test_terminology_package_does_not_import_adapters() -> None:
    """Top-level package import MUST NOT load adapter modules (INV-1)."""
    for mod in (
        "fhir4ds.cql.terminology",
        "fhir4ds.cql.terminology.http_adapter",
        "fhir4ds.cql.terminology.in_process_adapter",
    ):
        sys.modules.pop(mod, None)

    importlib.import_module("fhir4ds.cql.terminology")

    assert "fhir4ds.cql.terminology.http_adapter" not in sys.modules
    assert "fhir4ds.cql.terminology.in_process_adapter" not in sys.modules
