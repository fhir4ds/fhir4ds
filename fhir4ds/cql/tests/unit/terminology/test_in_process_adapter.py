"""Unit tests for InProcessTerminologyEndpoint.

The medterm4ds engine and service functions are mocked so the tests run
without a live medterm4ds install in the test environment.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from fhir4ds.cql.terminology import CodeRef, SearchResult


def _install_medterm4ds_stub(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Install a fake ``medterm4ds`` package in ``sys.modules``.

    Returns the engine mock so individual tests can program return values.

    The stub mirrors the published medterm4ds API surface:
    - ``medterm4ds.connect(db_path=...)`` returns a Terminology facade.
    - The Terminology facade exposes ``.engine`` (the DiscoveryEngine)
      and ``.expand_url(url)`` (returns ``list[medterm4ds.CodeRef]``).
    - ``LocalDuckDBEngine`` is also exposed for backward-compat tests
      of the direct-construction fallback path.
    """
    engine = MagicMock(name="DiscoveryEngine")

    # Mock Terminology facade. Tests that program expand() will rebind
    # ``terminology.expand_url`` to control the return value.
    terminology = MagicMock(name="Terminology")
    terminology.engine = engine
    terminology.expand_url = MagicMock(return_value=[])

    fake_pkg = types.ModuleType("medterm4ds")
    engines_pkg = types.ModuleType("medterm4ds.engines")
    base_mod = types.ModuleType("medterm4ds.engines.base")
    local_mod = types.ModuleType("medterm4ds.engines.local_duckdb")
    services_pkg = types.ModuleType("medterm4ds.services")
    services_discovery = types.ModuleType("medterm4ds.services.discovery")

    base_mod.DiscoveryEngine = object
    local_mod.LocalDuckDBEngine = MagicMock(return_value=engine)

    def _fake_search_names(query, engine, *, sources=None, limit=25):
        return []

    services_discovery.search_names = _fake_search_names
    services_pkg.search_names = _fake_search_names

    # Top-level connect(): returns the mock Terminology.
    fake_pkg.connect = MagicMock(return_value=terminology)
    # Expose Terminology and CodeRef on the fake package too.
    fake_pkg.Terminology = terminology

    fake_pkg.engines = engines_pkg
    engines_pkg.base = base_mod
    engines_pkg.local_duckdb = local_mod
    fake_pkg.services = services_pkg
    services_pkg.discovery = services_discovery

    monkeypatch.setitem(sys.modules, "medterm4ds", fake_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.engines", engines_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.engines.base", base_mod)
    monkeypatch.setitem(sys.modules, "medterm4ds.engines.local_duckdb", local_mod)
    monkeypatch.setitem(sys.modules, "medterm4ds.services", services_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.services.discovery", services_discovery)

    # Stash the terminology mock on the engine so tests that only grab
    # the engine return value can still reach the terminology via
    # ``engine.terminology`` if needed.
    engine.terminology = terminology
    return engine


def test_constructs_engine_with_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _install_medterm4ds_stub(monkeypatch)
    # Import after stub install so the adapter picks up the fake.
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint(
        medterm4ds_db_path="/tmp/mt.db",
        search_index_dir="/tmp/idx",
    )
    assert adapter._engine is engine


def test_search_text_returns_results(monkeypatch: pytest.MonkeyPatch) -> None:
    _engine = _install_medterm4ds_stub(monkeypatch)
    # Program a fake search result.
    fake_result = MagicMock()
    fake_code = MagicMock()
    fake_code.source = "SNOMEDCT_US"
    fake_code.code = "73211009"
    fake_result.code = fake_code
    fake_result.name = "Diabetes mellitus"
    fake_result.score = 0.88
    fake_result.match_grade = "probable"
    fake_result.index_version = "2024-01"

    from medterm4ds.services import search_names as _  # noqa: F401 — warm the import
    import medterm4ds.services.discovery as discovery_mod

    discovery_mod.search_names = MagicMock(return_value=[fake_result])

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    results = adapter.search_text("diabetes", "condition")
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, SearchResult)
    # medterm4ds returns source mnemonics (SNOMEDCT_US) which must be
    # expanded to the FHIR canonical URL so downstream joins against
    # valueset_codes succeed.
    assert r.system == "http://snomed.info/sct"
    assert r.code == "73211009"
    assert r.display == "Diabetes mellitus"
    assert r.score == pytest.approx(0.88)
    assert r.match_grade == "probable"
    assert r.index_version == "2024-01"


def test_search_text_normalizes_snomed_module_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """INV-5: SNOMED module URLs returned by medterm4ds reduce to base."""
    _install_medterm4ds_stub(monkeypatch)
    fake_result = MagicMock()
    fake_code = MagicMock()
    # medterm4ds may return a fully-qualified FHIR URL.
    fake_code.source = "http://snomed.info/sct/731000124108"
    fake_code.code = "73211009"
    fake_result.code = fake_code
    fake_result.name = "Diabetes"
    fake_result.score = 1.0
    fake_result.match_grade = "certain"
    fake_result.index_version = None

    import medterm4ds.services.discovery as discovery_mod

    discovery_mod.search_names = MagicMock(return_value=[fake_result])

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    results = adapter.search_text("diabetes", "snomed")
    assert len(results) == 1
    assert results[0].system == "http://snomed.info/sct"


def test_search_batch_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_medterm4ds_stub(monkeypatch)
    import medterm4ds.services.discovery as discovery_mod

    discovery_mod.search_names = MagicMock(return_value=[])

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    results = adapter.search_batch([("a", "condition"), ("b", "medication")])
    assert len(results) == 2
    assert discovery_mod.search_names.call_count == 2


def test_expand_uses_medterm4ds_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """expand() should delegate to Terminology.expand_url (Option B)."""
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology  # mock Terminology facade

    # Program expand_url to return a list of medterm4ds-style CodeRef
    # objects. medterm4ds.CodeRef has (source, code) — source is the
    # UMLS mnemonic; the adapter normalizes it to the FHIR canonical URL.
    mt_coderef = MagicMock()
    mt_coderef.source = "SNOMEDCT_US"
    mt_coderef.code = "73211009"
    mt_coderef.display = None
    terminology.expand_url = MagicMock(return_value=[mt_coderef])

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    refs = adapter.expand("http://snomed.info/sct/73211009?fhir_vs=isa")
    # Adapter normalized SNOMEDCT_US → http://snomed.info/sct.
    assert refs == [CodeRef("http://snomed.info/sct", "73211009", None)]
    terminology.expand_url.assert_called_once_with(
        "http://snomed.info/sct/73211009?fhir_vs=isa"
    )


def test_expand_intensional_uses_medterm4ds_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_medterm4ds_stub(monkeypatch)
    fake_helpers = types.ModuleType("medterm4ds.apps.fhir_api_helpers")
    fake_helpers.expand_intensional = MagicMock(
        return_value={
            "expansion": {
                "contains": [
                    {"system": "http://snomed.info/sct", "code": "73211009"}
                ]
            }
        }
    )
    fake_apps = types.ModuleType("medterm4ds.apps")
    monkeypatch.setitem(sys.modules, "medterm4ds.apps", fake_apps)
    monkeypatch.setitem(sys.modules, "medterm4ds.apps.fhir_api_helpers", fake_helpers)

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    body = {"resourceType": "ValueSet", "compose": {"include": []}}
    refs = adapter.expand_intensional(body)
    assert refs == [CodeRef("http://snomed.info/sct", "73211009", None)]
    fake_helpers.expand_intensional.assert_called_once()


def test_expand_degrades_to_empty_on_helper_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If medterm4ds helper raises, expand() returns [] (does NOT propagate)."""
    _install_medterm4ds_stub(monkeypatch)
    fake_helpers = types.ModuleType("medterm4ds.apps.fhir_api_helpers")
    fake_helpers.expand_url_pattern = MagicMock(side_effect=RuntimeError("boom"))
    fake_apps = types.ModuleType("medterm4ds.apps")
    monkeypatch.setitem(sys.modules, "medterm4ds.apps", fake_apps)
    monkeypatch.setitem(sys.modules, "medterm4ds.apps.fhir_api_helpers", fake_helpers)

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    assert adapter.expand("http://example.org/ValueSet/Foo") == []


# ----------------------------------------------------------------------
# Circuit breaker (mirror HTTP tests at smaller scale)
# ----------------------------------------------------------------------


def test_in_process_circuit_breaker_trips_and_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After threshold failures, breaker trips and subsequent calls return []."""
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology  # mock Terminology facade
    terminology.expand_url = MagicMock(side_effect=RuntimeError("boom"))

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint(
        breaker_threshold=2,
        breaker_cooldown_seconds=60.0,
    )
    # Two failures (each returns [] and increments the failure counter).
    assert adapter.expand("http://example.org/ValueSet/Foo") == []
    assert adapter.expand("http://example.org/ValueSet/Bar") == []
    assert adapter._consecutive_failures == 2
    assert adapter._tripped_until > 0.0

    # Breaker open: the third call short-circuits before reaching the
    # Terminology facade.
    call_count_before = terminology.expand_url.call_count
    assert adapter.expand("http://example.org/ValueSet/Baz") == []
    assert terminology.expand_url.call_count == call_count_before


def test_in_process_is_healthy_with_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """A constructed adapter with an engine advertises health."""
    engine = _install_medterm4ds_stub(monkeypatch)
    # Engine is a MagicMock — it auto-exposes arbitrary attrs, but we
    # want to test the explicit surface the probe checks for.
    engine.search_codes = MagicMock()

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    assert adapter.is_healthy() is True


def test_in_process_is_healthy_returns_false_without_engine_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Engine missing the discovery surface => is_healthy returns False."""
    _install_medterm4ds_stub(monkeypatch)

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    # Replace the engine with a bare object that has none of the
    # discovery surface attrs the probe looks for.
    adapter._engine = object()
    assert adapter.is_healthy() is False
