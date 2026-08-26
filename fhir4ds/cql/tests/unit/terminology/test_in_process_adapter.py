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

    The stub mirrors the published medterm4ds PyPI surface:
    - ``medterm4ds.connect(db_path=...)`` returns a Terminology facade.
    - The Terminology facade exposes ``.engine`` (the DiscoveryEngine)
      and ``.expand_url(url)`` (returns ``list[medterm4ds.CodeRef]``).
    - ``LocalDuckDBEngine`` is exposed both at the top level
      (``medterm4ds.LocalDuckDBEngine``) and at the full path
      (``medterm4ds.engines.duckdb.engine.LocalDuckDBEngine``) — the
      two canonical locations guaranteed by the published wheel.
    """
    engine = MagicMock(name="DiscoveryEngine")

    # Mock Terminology facade. Tests that program expand() will rebind
    # ``terminology.expand_url`` to control the return value.
    terminology = MagicMock(name="Terminology")
    terminology.engine = engine
    terminology.expand_url = MagicMock(return_value=[])

    fake_pkg = types.ModuleType("medterm4ds")
    engines_pkg = types.ModuleType("medterm4ds.engines")
    duckdb_pkg = types.ModuleType("medterm4ds.engines.duckdb")
    duckdb_engine_mod = types.ModuleType("medterm4ds.engines.duckdb.engine")
    services_pkg = types.ModuleType("medterm4ds.services")
    services_discovery = types.ModuleType("medterm4ds.services.discovery")

    # LocalDuckDBEngine is exposed at both canonical PyPI paths.
    local_duckdb_factory = MagicMock(return_value=engine)
    fake_pkg.LocalDuckDBEngine = local_duckdb_factory
    duckdb_engine_mod.LocalDuckDBEngine = local_duckdb_factory

    def _fake_search_names(query, engine, *, sources=None, limit=25):
        return []

    services_discovery.search_names = _fake_search_names
    services_pkg.search_names = _fake_search_names

    # apps.fhir_api surface (medterm4ds 0.0.2): expand_url_pattern and
    # expand_intensional_value_set. Default to empty expansions; tests
    # rebind to control returns.
    apps_pkg = types.ModuleType("medterm4ds.apps")
    fhir_api_mod = types.ModuleType("medterm4ds.apps.fhir_api")
    fhir_api_mod.expand_url_pattern = MagicMock(
        return_value={"expansion": {"contains": []}}
    )
    fhir_api_mod.expand_intensional_value_set = MagicMock(return_value=([], False))
    apps_pkg.fhir_api = fhir_api_mod
    fake_pkg.apps = apps_pkg

    # Top-level connect(): returns the mock Terminology.
    fake_pkg.connect = MagicMock(return_value=terminology)
    # Expose Terminology and CodeRef on the fake package too.
    fake_pkg.Terminology = terminology

    fake_pkg.engines = engines_pkg
    engines_pkg.duckdb = duckdb_pkg
    duckdb_pkg.engine = duckdb_engine_mod
    fake_pkg.services = services_pkg
    services_pkg.discovery = services_discovery

    monkeypatch.setitem(sys.modules, "medterm4ds", fake_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.engines", engines_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.engines.duckdb", duckdb_pkg)
    monkeypatch.setitem(
        sys.modules, "medterm4ds.engines.duckdb.engine", duckdb_engine_mod
    )
    monkeypatch.setitem(sys.modules, "medterm4ds.services", services_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.services.discovery", services_discovery)
    monkeypatch.setitem(sys.modules, "medterm4ds.apps", apps_pkg)
    monkeypatch.setitem(sys.modules, "medterm4ds.apps.fhir_api", fhir_api_mod)

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
    """MT-004: expand() prefers expand_url_pattern with retired codes in.

    The Terminology facade's expand_url() has no include_retired opt-in
    and medterm4ds 0.0.2 defaults to active-only, which would silently
    drop codes retired since they were recorded. Expansion feeds
    membership resolution, so the primary path must pass
    include_retired=True (settled retired-code policy).
    """
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology  # mock Terminology facade

    import medterm4ds.apps.fhir_api as fhir_api_mod

    fhir_api_mod.expand_url_pattern = MagicMock(
        return_value={
            "expansion": {
                "contains": [
                    # Canonical URL system — must pass through
                    # _normalize_system unchanged.
                    {
                        "system": "http://snomed.info/sct",
                        "code": "73211009",
                        "display": "Diabetes mellitus",
                    },
                ]
            }
        }
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    refs = adapter.expand("http://snomed.info/sct/73211009?fhir_vs=isa")
    assert refs == [CodeRef("http://snomed.info/sct", "73211009", "Diabetes mellitus")]
    fhir_api_mod.expand_url_pattern.assert_called_once_with(
        engine,
        "http://snomed.info/sct/73211009?fhir_vs=isa",
        count=1000,
        include_retired=True,
    )
    # The facade (no include_retired) must NOT be the primary path.
    terminology.expand_url.assert_not_called()


def test_expand_falls_back_to_facade_without_fhir_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without apps.fhir_api the facade expand_url is the fallback."""
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology

    # Make ``from medterm4ds.apps.fhir_api import ...`` fail.
    monkeypatch.delitem(sys.modules, "medterm4ds.apps.fhir_api")
    monkeypatch.delitem(sys.modules, "medterm4ds.apps")

    # medterm4ds.CodeRef has (source, code) — source is the UMLS
    # mnemonic; the adapter normalizes it to the FHIR canonical URL.
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
    assert refs == [CodeRef("http://snomed.info/sct", "73211009", None)]
    terminology.expand_url.assert_called_once_with(
        "http://snomed.info/sct/73211009?fhir_vs=isa"
    )


def test_mt006_connect_runtime_error_gets_config_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MT-006: medterm4ds RuntimeError on missing db is re-raised with a hint."""
    _install_medterm4ds_stub(monkeypatch)
    import medterm4ds as fake_pkg

    fake_pkg.connect = MagicMock(
        side_effect=RuntimeError("database not found: /nonexistent/mt.db")
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    with pytest.raises(RuntimeError, match="FHIR4DS_TERMINOLOGY_DB") as exc:
        InProcessTerminologyEndpoint(medterm4ds_db_path="/nonexistent/mt.db")
    # The remediation actions must be surfaced to the operator.
    msg = str(exc.value)
    assert "build-duckdb" in msg
    assert "prepare-derived" in msg
    # The underlying medterm4ds message is preserved.
    assert "/nonexistent/mt.db" in msg


def test_mt006_connect_passes_cache_indexes(monkeypatch: pytest.MonkeyPatch) -> None:
    """MT-006: the long-lived adapter engine persists BM25 indexes."""
    _install_medterm4ds_stub(monkeypatch)
    import medterm4ds as fake_pkg

    connect_mock = fake_pkg.connect
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    InProcessTerminologyEndpoint(medterm4ds_db_path="/tmp/mt.db")
    assert connect_mock.call_args.kwargs.get("db_path") == "/tmp/mt.db"
    assert connect_mock.call_args.kwargs.get("cache_indexes") is True


def test_mt005_expand_intensional_wired_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MT-005: intensional expansion uses the 0.0.2 programmatic helper.

    ``count`` is POSITIONAL in expand_intensional_value_set; retired
    codes are included per the settled policy (expansion feeds
    membership).
    """
    engine = _install_medterm4ds_stub(monkeypatch)

    import medterm4ds.apps.fhir_api as fhir_api_mod

    fhir_api_mod.expand_intensional_value_set = MagicMock(
        return_value=(
            [
                {
                    "system": "http://snomed.info/sct",
                    "code": "444814009",
                    "display": "Viral sinusitis",
                },
            ],
            False,
        )
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    body = {"resourceType": "ValueSet", "compose": {"include": []}}
    refs = adapter.expand_intensional(body)
    assert refs == [
        CodeRef("http://snomed.info/sct", "444814009", "Viral sinusitis")
    ]
    # count POSITIONAL, include_retired keyword.
    fhir_api_mod.expand_intensional_value_set.assert_called_once_with(
        engine, body, 1000, include_retired=True
    )
    assert adapter._consecutive_failures == 0


def test_mt005_expand_intensional_falls_back_to_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without apps.fhir_api the facade expand_intensional is the fallback."""
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology

    monkeypatch.delitem(sys.modules, "medterm4ds.apps.fhir_api")
    monkeypatch.delitem(sys.modules, "medterm4ds.apps")

    mt_coderef = MagicMock()
    mt_coderef.source = "LNC"
    mt_coderef.code = "718-7"
    mt_coderef.display = "Hemoglobin"
    terminology.expand_intensional = MagicMock(return_value=[mt_coderef])

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    body = {"resourceType": "ValueSet", "compose": {"include": []}}
    refs = adapter.expand_intensional(body)
    assert refs == [CodeRef("http://loinc.org", "718-7", "Hemoglobin")]
    terminology.expand_intensional.assert_called_once_with(body, count=1000)


def test_expand_intensional_returns_empty_when_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No helper and no facade: [] without tripping the breaker."""
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology

    monkeypatch.delitem(sys.modules, "medterm4ds.apps.fhir_api")
    monkeypatch.delitem(sys.modules, "medterm4ds.apps")
    del terminology.expand_intensional

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint(breaker_threshold=2)
    body = {"resourceType": "ValueSet", "compose": {"include": []}}
    assert adapter.expand_intensional(body) == []
    # "not supported" must NOT trip the breaker — otherwise
    # expand()/search_text() would collateral-fail after a few closure
    # lookups.
    assert adapter._consecutive_failures == 0


def test_expand_degrades_to_empty_on_helper_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the medterm4ds fhir_api helper raises, expand() returns []."""
    _install_medterm4ds_stub(monkeypatch)

    import medterm4ds.apps.fhir_api as fhir_api_mod

    fhir_api_mod.expand_url_pattern = MagicMock(side_effect=RuntimeError("boom"))

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    assert adapter.expand("http://example.org/ValueSet/Foo") == []
    fhir_api_mod.expand_url_pattern.assert_called_once()


# ----------------------------------------------------------------------
# Circuit breaker (mirror HTTP tests at smaller scale)
# ----------------------------------------------------------------------


def test_in_process_circuit_breaker_trips_and_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After threshold failures, breaker trips and subsequent calls return []."""
    engine = _install_medterm4ds_stub(monkeypatch)

    import medterm4ds.apps.fhir_api as fhir_api_mod

    fhir_api_mod.expand_url_pattern = MagicMock(side_effect=RuntimeError("boom"))

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

    # Breaker open: the third call short-circuits before reaching
    # medterm4ds.
    call_count_before = fhir_api_mod.expand_url_pattern.call_count
    assert adapter.expand("http://example.org/ValueSet/Baz") == []
    assert fhir_api_mod.expand_url_pattern.call_count == call_count_before


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
