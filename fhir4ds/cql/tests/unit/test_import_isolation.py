"""Sentinel tests guarding the zero-optional-dep import contract.

Background (REV-001):
    A CRITICAL regression shipped where ``httpx`` was imported at module
    top of ``fhir4ds/cql/terminology/http_adapter.py``. That made the
    factory's ``try: import httpx except ImportError`` block dead code:
    users without ``httpx`` got the cryptic
    ``import of httpx halted; None in sys.modules`` instead of the
    helpful ``pip install 'fhir4ds-v2[terminology]'`` hint.

    The fix moved the import into a lazy helper. These tests ensure no
    future maintainer re-introduces the pattern by poisoning
    ``sys.modules[dep] = None`` for every optional dependency and
    re-importing every public fhir4ds subpackage. If any subpackage's
    import chain pulls an optional dep at module load, the import fails
    with an actionable error message.

Hermeticity:
    Each test snapshots ``sys.modules`` on entry and restores it on exit
    (``try/finally``), so these tests are safe both in isolation and in
    the full suite.
"""

from __future__ import annotations

import importlib
import sys

import pytest


# ---------------------------------------------------------------------------
# Optional dependencies that must NEVER be imported at module load time.
# Poisoning ``sys.modules[name] = None`` mimics Python's "import failed
# once" marker — any subsequent ``import name`` raises ImportError.
# ---------------------------------------------------------------------------
_OPTIONAL_DEPS = [
    "httpx",
    "medterm4ds",
    "medspacy",
    "spacy",
    "transformers",
    "torch",
]


# ---------------------------------------------------------------------------
# Public fhir4ds subpackages. Every entry here must import successfully
# with all optional deps poisoned — that is the zero-dep default contract.
# Add new public surface here as it lands.
# ---------------------------------------------------------------------------
_PUBLIC_SUBPACKAGES = [
    "fhir4ds",
    "fhir4ds.cql",
    "fhir4ds.cql.terminology",
    "fhir4ds.cql.terminology.endpoint",
    "fhir4ds.cql.terminology.http_adapter",
    "fhir4ds.cql.terminology.in_process_adapter",
    "fhir4ds.cql.terminology.factory",
    "fhir4ds.cql.terminology.closure",
    "fhir4ds.cql.loader",
    "fhir4ds.cql.loader.auto_coder",
    "fhir4ds.cql.loader.notes_pipeline",
    "fhir4ds.cql.loader.notes_text_extractor",
    "fhir4ds.measure",
]


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    """Snapshot ``sys.modules`` before each test and restore it after.

    Tests in this module mutate ``sys.modules`` (poison optional deps,
    delete cached fhir4ds subpackages). Without this fixture, those
    mutations would leak into subsequent tests in the same session and
    cause spurious ImportErrors. Snapshot-and-restore keeps the tests
    hermetic.
    """
    saved = dict(sys.modules)
    try:
        yield
    finally:
        sys.modules.clear()
        sys.modules.update(saved)


def test_no_optional_dep_imported_at_module_load():
    """All public fhir4ds subpackages import without ANY optional dep installed.

    Guards against the REV-001 class of bug: a top-level
    ``import httpx`` / ``import medterm4ds`` / etc. that defeats the
    lazy-import contract. Poisoning ``sys.modules[dep] = None`` causes
    Python's import machinery to raise ImportError on any subsequent
    attempt to import ``dep`` — surfacing the bug at test time rather
    than in production.
    """
    # Poison every optional dep. ``None`` is Python's "import failed"
    # sentinel: the import machinery raises ImportError on next attempt.
    for dep in _OPTIONAL_DEPS:
        sys.modules[dep] = None

    # Drop cached fhir4ds subpackages so the import machinery re-runs
    # every top-level statement (this is where a stray top-level
    # ``import httpx`` would trigger the poison).
    for key in list(sys.modules.keys()):
        if key == "fhir4ds" or key.startswith("fhir4ds."):
            del sys.modules[key]

    failures: list[str] = []
    for pkg in _PUBLIC_SUBPACKAGES:
        try:
            importlib.import_module(pkg)
        except ImportError as exc:
            failures.append(
                f"{pkg!r}: {exc}. Top-level `import <optional-dep>` "
                f"likely leaked back into this module's import chain."
            )

    if failures:
        pytest.fail(
            "ImportError raised while optional deps were poisoned:\n  - "
            + "\n  - ".join(failures)
            + "\n\nThis violates the zero-dep default contract. Check "
            "for top-level `import httpx` / `import medterm4ds` / "
            "`import spacy` / etc. in the offending module(s)."
        )


def test_http_adapter_raises_install_hint_without_httpx():
    """HTTPTerminologyEndpoint surfaces a clear install hint on first request.

    Module load of ``http_adapter`` must succeed without ``httpx``
    (REV-001 invariant), and adapter construction must also succeed
    (the lazy import is deferred to request time). The first request
    then surfaces the user-facing
    ``pip install 'fhir4ds-v2[terminology]'`` hint via ``_require_httpx``,
    rather than the bare ``import of httpx halted; None in sys.modules``
    error that motivated REV-001.
    """
    sys.modules["httpx"] = None
    for key in list(sys.modules.keys()):
        if "http_adapter" in key or key.startswith("fhir4ds.cql.terminology"):
            del sys.modules[key]

    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    # Construction must NOT raise — httpx is only needed at request time.
    adapter = HTTPTerminologyEndpoint(base_url="http://localhost:8001/fhir")

    # First request triggers the lazy import and surfaces the install hint.
    with pytest.raises(ImportError, match=r"fhir4ds-v2\[terminology\]"):
        adapter._client()


def test_in_process_adapter_raises_install_hint_without_medterm4ds():
    """InProcessTerminologyEndpoint instantiation surfaces a clear install hint.

    Module load of ``in_process_adapter`` must succeed without
    ``medterm4ds``, but constructing a live adapter must fail with an
    install hint pointing at the medterm4ds sibling repo.
    """
    sys.modules["medterm4ds"] = None
    for key in list(sys.modules.keys()):
        if "in_process_adapter" in key or key.startswith("fhir4ds.cql.terminology"):
            del sys.modules[key]

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    with pytest.raises(ImportError, match=r"medterm4ds"):
        InProcessTerminologyEndpoint(medterm4ds_db_path=None)
