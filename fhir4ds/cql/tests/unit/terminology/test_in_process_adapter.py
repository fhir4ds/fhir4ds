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

    # D12 SKEPTIC (v0.0.26) order-flake fix: the adapter's search_text
    # prefers ``medterm4ds.services.search`` and falls back to the legacy
    # discovery path only when that import FAILS. When the REAL
    # medterm4ds is installed in the test environment, any earlier test
    # that imported it leaves ``medterm4ds.services.search`` cached in
    # sys.modules — the fake non-package ``medterm4ds.services`` above
    # then cannot shadow it, the adapter takes the real search-service
    # path, and the legacy-path mocks below are never invoked (the 3
    # documented order-dependent failures). Drop any cached real module
    # so the stub fully controls which path is exercised.
    monkeypatch.delitem(sys.modules, "medterm4ds.services.search", raising=False)

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


def test_mt006_connect_call_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """MT-006 + D12 SKEPTIC: connect() is called with db_path ONLY.

    Since medterm4ds 0.0.12, ``cache_indexes`` only takes effect together
    with ``prepare_cache=True`` (and medterm4ds QC-470 recommends NOT
    preparing read-mostly workloads), so the former ``cache_indexes=True``
    was a silent no-op under the pinned >=0.0.14 contract and has been
    dropped. Pin the new call shape so a future re-addition is a
    deliberate decision, not drift.
    """
    _install_medterm4ds_stub(monkeypatch)
    import medterm4ds as fake_pkg

    connect_mock = fake_pkg.connect
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    InProcessTerminologyEndpoint(medterm4ds_db_path="/tmp/mt.db")
    assert connect_mock.call_args.kwargs.get("db_path") == "/tmp/mt.db"
    assert "cache_indexes" not in connect_mock.call_args.kwargs
    assert "prepare_cache" not in connect_mock.call_args.kwargs


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


# ----------------------------------------------------------------------
# Iteration 23 / Domain 12 HISTORIAN — expand_intensional return shapes
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "return_value,expected_codes",
    [
        # medterm4ds 0.0.10 returns the code list directly.
        ([{"system": "http://snomed.info/sct", "code": "a"},
          {"system": "http://snomed.info/sct", "code": "b"}], ["a", "b"]),
        # Later builds return (codes, depth_cap_hit).
        (([{"system": "http://snomed.info/sct", "code": "c"}], True), ["c"]),
    ],
)
def test_expand_intensional_accepts_both_medterm4ds_return_shapes(
    monkeypatch: pytest.MonkeyPatch, return_value, expected_codes
) -> None:
    """medterm4ds's expand_intensional_value_set has an ANNOTATION/RUNTIME mismatch.

    Its published signature says ``-> list[dict]`` while medterm4ds 0.0.10
    actually returns ``(list, depth_cap_hit)`` at runtime (verified by calling
    it directly). Code written against the annotation would break on the
    runtime shape, so the adapter accepts BOTH: a strict unpack is unsafe
    against a function whose documented and actual shapes disagree, and the
    surrounding degrade-and-warn path would turn that mismatch into a silent
    empty expansion.
    """
    # Reaches into the REAL medterm4ds module, which is an optional extra
    # (fhir4ds-v2[terminology]); CI installs only .[dev,measures]). Skip rather
    # than error when it is absent. Tests that use _install_medterm4ds_stub do
    # NOT need this guard — importing the real package at module scope shadows
    # that stub and breaks the search tests.
    pytest.importorskip("medterm4ds")
    import medterm4ds.apps.fhir_api as fhir_api_mod

    monkeypatch.setattr(
        fhir_api_mod, "expand_intensional_value_set",
        lambda engine, vs, count, *, include_retired=False: return_value,
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    adapter._engine = object()  # bypass engine provisioning; test the call contract
    refs = adapter.expand_intensional({"resourceType": "ValueSet", "compose": {}})
    assert [r.code for r in refs] == expected_codes
    assert adapter._consecutive_failures == 0


def test_expand_intensional_positional_count_and_include_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """count is POSITIONAL and include_retired must be True (membership policy)."""
    # Reaches into the REAL medterm4ds module, which is an optional extra
    # (fhir4ds-v2[terminology]); CI installs only .[dev,measures]). Skip rather
    # than error when it is absent. Tests that use _install_medterm4ds_stub do
    # NOT need this guard — importing the real package at module scope shadows
    # that stub and breaks the search tests.
    pytest.importorskip("medterm4ds")
    import medterm4ds.apps.fhir_api as fhir_api_mod

    seen: dict = {}

    def fake(engine, vs, count, *, include_retired=False):
        seen.update(count=count, include_retired=include_retired)
        return []

    monkeypatch.setattr(fhir_api_mod, "expand_intensional_value_set", fake)

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    adapter._engine = object()
    adapter.expand_intensional({"resourceType": "ValueSet", "compose": {}})
    assert seen == {"count": 1000, "include_retired": True}


# ----------------------------------------------------------------------
# D12 SKEPTIC (v0.0.26): capability escalation + import-stack actionability
# ----------------------------------------------------------------------


def test_expand_value_error_escapes_as_capability_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA-D12S-001: medterm4ds ValueError (unsupported URL form) is a
    CAPABILITY refusal, not a transient fault — it must raise
    TerminologyCapabilityError (mirroring the sidecar's ValueError->400
    mapping and the HTTP adapter's 400/422 escalation) instead of
    silently returning [] + poisoning the breaker."""
    _install_medterm4ds_stub(monkeypatch)

    import medterm4ds.apps.fhir_api as fhir_api_mod
    from fhir4ds.cql.terminology.errors import TerminologyCapabilityError

    fhir_api_mod.expand_url_pattern = MagicMock(
        side_effect=ValueError(
            "Unsupported fhir_vs URL pattern: 'http://cts.nlm.nih.gov/fhir/"
            "ValueSet/1.2.3'. Only SNOMED CT intensional expansions are "
            "implemented."
        )
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    with pytest.raises(TerminologyCapabilityError) as exc:
        adapter.expand("http://cts.nlm.nih.gov/fhir/ValueSet/1.2.3")
    # Actionable: names the URL and the remediation.
    assert "1.2.3" in str(exc.value)
    assert "expand_intensional" in str(exc.value)
    # Capability refusals must NOT count as breaker failures.
    assert adapter._consecutive_failures == 0


def test_expand_intensional_value_error_escapes_as_capability_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA-D12S-001 (intensional twin): QC-252/QC-246-class ValueErrors from
    expand_intensional_value_set are request-form refusals (the sidecar
    maps them to 400) — escalate, don't degrade."""
    _install_medterm4ds_stub(monkeypatch)

    import medterm4ds.apps.fhir_api as fhir_api_mod
    from fhir4ds.cql.terminology.errors import TerminologyCapabilityError

    fhir_api_mod.expand_intensional_value_set = MagicMock(
        side_effect=ValueError(
            "Unresolvable compose system URI: 'http://example.org/nope'"
        )
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    with pytest.raises(TerminologyCapabilityError):
        adapter.expand_intensional(
            {"resourceType": "ValueSet",
             "compose": {"include": [{"system": "http://example.org/nope"}]}}
        )
    assert adapter._consecutive_failures == 0


def test_expand_facade_fallback_value_error_also_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA-D12S-001: the Terminology.expand_url facade fallback path raises
    the same capability class when medterm4ds refuses the URL form."""
    engine = _install_medterm4ds_stub(monkeypatch)
    terminology = engine.terminology

    monkeypatch.delitem(sys.modules, "medterm4ds.apps.fhir_api")
    monkeypatch.delitem(sys.modules, "medterm4ds.apps")
    terminology.expand_url = MagicMock(
        side_effect=ValueError("Unsupported fhir_vs URL pattern: 'x'")
    )

    from fhir4ds.cql.terminology.errors import TerminologyCapabilityError
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    with pytest.raises(TerminologyCapabilityError):
        adapter.expand("http://snomed.info/sct?fhir_vs=isa/123")
    assert adapter._consecutive_failures == 0


def _install_search_service_stub(
    monkeypatch: pytest.MonkeyPatch, search_side_effect: Exception
) -> None:
    """Install a fake ``medterm4ds.services.search`` module whose service
    reports both artifact families available but whose ``search`` raises."""
    service = MagicMock(name="SearchService")
    service.ensure_lexical = MagicMock(return_value=True)
    service.ensure_semantic = MagicMock(return_value=True)
    service.lexical_available = True
    service.semantic_available = True
    service.search = MagicMock(side_effect=search_side_effect)
    search_mod = types.ModuleType("medterm4ds.services.search")
    search_mod.get_search_service = MagicMock(return_value=service)
    services_pkg = sys.modules["medterm4ds.services"]
    monkeypatch.setitem(sys.modules, "medterm4ds.services.search", search_mod)
    services_pkg.search = search_mod


def test_search_import_error_is_actionable_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA-D12S-002: cached model artifacts pass the availability gate, but an
    unimportable ML runtime (ModuleNotFoundError: transformers) is a PERMANENT
    environment condition — it must raise the actionable RuntimeError (same
    class as the QA-001 artifact gate), not silently return [] and poison the
    breaker."""
    _install_medterm4ds_stub(monkeypatch)
    _install_search_service_stub(
        monkeypatch, ModuleNotFoundError("No module named 'transformers'")
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    with pytest.raises(RuntimeError) as exc:
        adapter.search_text("diabetes", "condition", mode="hybrid")
    msg = str(exc.value)
    assert "transformers" in msg
    assert "lexical" in msg  # the fallback mode remediation must be named
    # Permanent condition: not a breaker failure.
    assert adapter._consecutive_failures == 0


def test_search_transient_error_still_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA-D12S-002 companion: genuine transient faults keep the documented
    WARNING + [] + breaker path."""
    _install_medterm4ds_stub(monkeypatch)
    _install_search_service_stub(
        monkeypatch, RuntimeError("duckdb connection reset")
    )

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    assert adapter.search_text("diabetes", "condition", mode="hybrid") == []
    assert adapter._consecutive_failures == 1


# ----------------------------------------------------------------------
# QA-D12E-002 (v0.0.26 Domain 12 EXPLORER): the result-CONVERSION loops
# sat outside the drift-guard try/except — a hostile/ambiguous-shape
# medterm4ds result (non-dict items, wrong-arity tuple) raised a raw
# AttributeError OUT of the adapter (no degrade, no breaker accounting),
# while the HTTP adapter tolerates the same garbage. Contract: hostile
# result shapes degrade to [] + WARNING + breaker, matching the
# medterm4ds-drift guard on the CALL itself.
# ----------------------------------------------------------------------


def test_qa_d12e002_expand_intensional_wrong_arity_tuple_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _install_medterm4ds_stub(monkeypatch)
    fhir_api = sys.modules["medterm4ds.apps.fhir_api"]
    fhir_api.expand_intensional_value_set = MagicMock(
        return_value=([{"system": "SNOMEDCT_US", "code": "1"}], True, "extra")
    )
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    assert adapter.expand_intensional({"resourceType": "ValueSet"}) == []
    assert adapter._consecutive_failures == 1


def test_qa_d12e002_expand_intensional_non_dict_items_degrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _install_medterm4ds_stub(monkeypatch)
    fhir_api = sys.modules["medterm4ds.apps.fhir_api"]
    fhir_api.expand_intensional_value_set = MagicMock(
        return_value=(["not-a-dict", 42, None], False)
    )
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    assert adapter.expand_intensional({"resourceType": "ValueSet"}) == []
    # Non-dict items are SKIPPED (not a crash); the call still counts
    # as a success (the endpoint answered; the garbage rows are dropped).
    assert adapter._consecutive_failures == 0


def test_qa_d12e002_expand_non_dict_contains_items_do_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _install_medterm4ds_stub(monkeypatch)
    fhir_api = sys.modules["medterm4ds.apps.fhir_api"]
    fhir_api.expand_url_pattern = MagicMock(
        return_value={"expansion": {"contains": [
            "not-a-dict",
            {"system": "SNOMEDCT_US", "code": "valid"},
        ]}}
    )
    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    refs = adapter.expand("http://snomed.info/sct?fhir_vs")
    assert [r.code for r in refs] == ["valid"]
    assert adapter._consecutive_failures == 0


def test_qa_d12e002_search_hostile_score_string_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A search result whose score is a non-float string must not raise
    past the adapter (HTTP adapter's _extract_score coerces to 0.0)."""
    engine = _install_medterm4ds_stub(monkeypatch)

    class _R:
        source = "SNOMEDCT_US"
        code = "1"
        display = "d"
        score = "not-a-float"
        match_grade = "exact"

    service = MagicMock(name="SearchService")
    service.ensure_lexical = MagicMock(return_value=True)
    service.ensure_semantic = MagicMock(return_value=True)
    service.search = MagicMock(return_value=[_R()])
    search_mod = types.ModuleType("medterm4ds.services.search")
    search_mod.get_search_service = MagicMock(return_value=service)
    monkeypatch.setitem(
        sys.modules, "medterm4ds.services.search", search_mod
    )
    sys.modules["medterm4ds.services"].search = search_mod

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    results = adapter.search_text("diabetes", "condition", mode="hybrid")
    assert len(results) == 1 and results[0].score == 0.0
    assert adapter._consecutive_failures == 0


# ---------------------------------------------------------------------------
# FHIR4-25: one thread per DuckDB connection contract
# ---------------------------------------------------------------------------
#
# medterm4ds' own threading guide (docs/threading-and-embedding.md, PR #24)
# states the contract the host must enforce: "One thread per DuckDB
# connection. The DuckDB Python connection is not thread-safe under
# concurrent use ... an in-process adapter must do the same (one DB thread,
# or an external lock around engine calls that share a connection).
# Violating this produces row-shape errors (ValueError: not enough values to
# unpack), not corruption - but it is unsupported."
#
# The adapter owns ONE medterm4ds engine, and that engine owns ONE DuckDB
# connection. Since in-process is now the supported default embedding (the
# phase-isolated benchmark path this replaced existed only to serialize
# inference incidentally), the adapter itself must serialize engine calls.


def _install_concurrency_probe_service(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Install a search service that records in-flight concurrency."""
    import threading
    import time

    state = {"inflight": 0, "max_inflight": 0, "calls": 0}
    lock = threading.Lock()

    def _search(query, *, mode, sources, count, engine):
        with lock:
            state["inflight"] += 1
            state["calls"] += 1
            state["max_inflight"] = max(state["max_inflight"],
                                        state["inflight"])
        time.sleep(0.05)  # hold the "engine" long enough to collide
        with lock:
            state["inflight"] -= 1
        return []

    service = MagicMock(name="SearchService")
    service.ensure_lexical = MagicMock(return_value=True)
    service.ensure_semantic = MagicMock(return_value=True)
    service.lexical_available = True
    service.semantic_available = True
    service.search = MagicMock(side_effect=_search)
    search_mod = types.ModuleType("medterm4ds.services.search")
    search_mod.get_search_service = MagicMock(return_value=service)
    services_pkg = sys.modules["medterm4ds.services"]
    monkeypatch.setitem(sys.modules, "medterm4ds.services.search", search_mod)
    services_pkg.search = search_mod
    return state


def test_search_text_serializes_engine_calls_across_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FHIR4-25: concurrent callers sharing one endpoint must not enter the
    engine (one DuckDB connection) concurrently."""
    import threading

    _install_medterm4ds_stub(monkeypatch)
    state = _install_concurrency_probe_service(monkeypatch)

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            adapter.search_text("diabetes", "condition", mode="hybrid")
        except BaseException as exc:  # noqa: BLE001 - surface in the assert
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == []
    assert state["calls"] == 4
    assert state["max_inflight"] == 1, (
        "engine calls must serialize on the endpoint's connection lock; "
        f"observed {state['max_inflight']} concurrent calls"
    )


def test_expand_serializes_with_search_on_the_same_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lock must span every engine-touching method, not just search."""
    import threading
    import time

    engine = _install_medterm4ds_stub(monkeypatch)
    state = _install_concurrency_probe_service(monkeypatch)
    lock = threading.Lock()
    overlap = {"seen": 0}

    def _expand_url_pattern(engine_arg, url, **kwargs):
        with lock:
            state["inflight"] += 1
            overlap["seen"] = max(overlap["seen"], state["inflight"])
        time.sleep(0.05)
        with lock:
            state["inflight"] -= 1
        return {"expansion": {"contains": []}}

    import medterm4ds.apps.fhir_api as fhir_api_mod

    monkeypatch.setattr(fhir_api_mod, "expand_url_pattern",
                        _expand_url_pattern)

    from fhir4ds.cql.terminology.in_process_adapter import (
        InProcessTerminologyEndpoint,
    )

    adapter = InProcessTerminologyEndpoint()
    threads = [
        threading.Thread(target=lambda: adapter.search_text(
            "diabetes", "condition", mode="hybrid")),
        threading.Thread(target=lambda: adapter.expand(
            "http://snomed.info/sct?fhir_vs=isa/73211009")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert overlap["seen"] == 1, (
        "expand() and search_text() share the engine's DuckDB connection and "
        f"must serialize; observed {overlap['seen']} concurrent calls"
    )
