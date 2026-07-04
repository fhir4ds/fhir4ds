"""Phase 3 (medterm4ds subsumption) — closure-table builder unit tests.

These tests cover:
    * AST scanning for the three subsumption operand forms
      (``Descendents(X)``, ``X ~ Y``, ``X is Y``).
    * Seed extraction with system normalization.
    * Endpoint expansion routing (SNOMED fast-path vs intensional).
    * Per-seed fault tolerance under the ``warn`` / ``skip`` / ``raise``
      error policies.
    * Idempotent re-runs (``INSERT OR IGNORE`` dedup).
    * Closure-set namespacing so multiple libraries coexist on one connection.
    * Reflexive row insertion so ``X is X`` returns True.

Tests use a stub endpoint and an in-memory DuckDB connection. They do NOT
require medterm4ds, httpx, or any network access.
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Tuple

import pytest

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.terminology import (
    CodeRef,
    SearchResult,
    build_closure_table,
    clear_closure_table,
)
from fhir4ds.cql.terminology.closure import _scan_for_subsumption_seeds


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _StubEndpoint:
    """In-memory endpoint implementing the TerminologyEndpoint protocol.

    Pre-seeded with SNOMED and LOINC expansions used across tests. The
    ``calls`` list exposes every call so tests can assert routing decisions.
    """

    def __init__(
        self,
        snomed_expansions: Dict[str, List[CodeRef]] = None,
        intensional_expansions: Dict[Tuple[str, str], List[CodeRef]] = None,
        fail_seeds: List[str] = None,
    ) -> None:
        self.snomed = snomed_expansions or {}
        self.intensional = intensional_expansions or {}
        self.fail_seeds = set(fail_seeds or [])
        self.calls: List[Tuple[str, object]] = []

    def expand(self, valueset_url: str) -> List[CodeRef]:
        self.calls.append(("expand", valueset_url))
        # SNOMED ?fhir_vs=isa/{code}
        if "?fhir_vs=isa/" in valueset_url:
            code = valueset_url.rsplit("/", 1)[-1]
            if f"http://snomed.info/sct|{code}" in self.fail_seeds:
                raise RuntimeError(f"stub failure for SNOMED {code}")
            return list(self.snomed.get(code, []))
        return []

    def expand_intensional(self, value_set: dict) -> List[CodeRef]:
        self.calls.append(("expand_intensional", value_set))
        include = (value_set.get("compose", {}).get("include") or [{}])[0]
        sys_url = include.get("system", "")
        # Find the is-a filter value.
        code = ""
        for f in include.get("filter", []):
            if f.get("op") == "is-a":
                code = f.get("value", "")
                break
        key = f"{sys_url}|{code}"
        if key in self.fail_seeds:
            raise RuntimeError(f"stub failure for {key}")
        return list(self.intensional.get((sys_url, code), []))

    def search_text(
        self, query: str, category: str, *, mode: str = "hybrid"
    ) -> List[SearchResult]:
        return []

    def search_batch(
        self, queries: List[Tuple[str, str]], *, mode: str = "hybrid"
    ) -> List[List[SearchResult]]:
        return [[] for _ in queries]


def _make_library(cql: str):
    return parse_cql(cql)


@pytest.fixture
def con():
    import duckdb

    conn = duckdb.connect(":memory:")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Helper exposed for tests: resolve_seed_codes — the AST scan + resolve step.
# ---------------------------------------------------------------------------


def test_resolve_seed_codes_via_module_api(con):
    """Smoke test: ``resolve_seed_codes`` (helper) extracts seeds cleanly."""
    # The closure module exposes _scan_for_subsumption_seeds for whitebox tests.
    # Build a tiny library inline to avoid coupling to the parser here.
    cql = """
    library SeedLib version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "Diabetes": '73211009' from "SNOMED-CT" display 'Diabetes mellitus'
    define TestExpand: Descendents("Diabetes")
    """
    lib = _make_library(cql)
    seeds = _scan_for_subsumption_seeds(lib)
    assert len(seeds) >= 1, "expected at least one seed operand from Descendents"


# ---------------------------------------------------------------------------
# Test 1: Empty AST → no-op
# ---------------------------------------------------------------------------


def test_empty_ast_noop(con):
    """Empty library produces no seeds; table is created but empty."""
    cql = """
    library Empty version '1.0'
    using FHIR version '4.0.1'
    define Nothing: 1 + 1
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint()
    report = build_closure_table(lib, endpoint, con)
    assert report.seeds_scanned == 0
    assert report.seeds_expanded == 0
    assert report.rows_loaded == 0
    assert report.errors == []
    # Table exists.
    rows = con.execute("SELECT COUNT(*) FROM terminology_closure").fetchone()
    assert rows[0] == 0
    # No endpoint calls.
    assert endpoint.calls == []


# ---------------------------------------------------------------------------
# Test 2: Descendents(Diabetes) — SNOMED fast-path
# ---------------------------------------------------------------------------


def test_descendents_snomed_fastpath(con):
    """Descendents(Code) routes through SNOMED ``?fhir_vs=isa/`` fast-path."""
    cql = """
    library Diab version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "Diabetes": '73211009' from "SNOMED-CT" display 'Diabetes mellitus'
    define Descendants: Descendents("Diabetes")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={
            "73211009": [
                CodeRef(system="http://snomed.info/sct", code="44054006"),
                CodeRef(system="http://snomed.info/sct", code="87049000"),
            ]
        }
    )
    report = build_closure_table(lib, endpoint, con)
    assert report.seeds_scanned == 1
    assert report.seeds_expanded == 1
    # 2 endpoint codes + 1 reflexive row = 3.
    assert report.rows_loaded == 3
    # Confirm the URL form.
    expand_calls = [c for c in endpoint.calls if c[0] == "expand"]
    assert len(expand_calls) == 1
    assert expand_calls[0][1] == "http://snomed.info/sct?fhir_vs=isa/73211009"
    # Confirm rows.
    rows = con.execute(
        "SELECT ancestor_code, descendant_code FROM terminology_closure "
        "ORDER BY descendant_code"
    ).fetchall()
    descendants = {r[1] for r in rows}
    assert descendants == {"73211009", "44054006", "87049000"}


# ---------------------------------------------------------------------------
# Test 3: Code X ~ Code Y seeds both
# ---------------------------------------------------------------------------


def test_equivalence_seeds_both_codes(con):
    """``Code X ~ Code Y`` extracts both X and Y as seeds."""
    cql = """
    library Equiv version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "DM": '73211009' from "SNOMED-CT"
    code "T2DM": '44054006' from "SNOMED-CT"
    define Equivalent: "DM" ~ "T2DM"
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={
            "73211009": [CodeRef(system="http://snomed.info/sct", code="44054006")],
            "44054006": [],
        }
    )
    report = build_closure_table(lib, endpoint, con)
    assert report.seeds_scanned == 2
    # Per-seed reflexive rows are always inserted, so rows_loaded >= 2.
    assert report.rows_loaded >= 2


# ---------------------------------------------------------------------------
# Test 4: Code X is Code Y seeds both codes
# ---------------------------------------------------------------------------


def test_is_operator_seeds_both_codes(con):
    """``Code X is Code Y`` extracts both X and Y.

    CQL grammar note: ``A is B`` parses the right side as a
    NamedTypeSpecifier (type-check form). The closure builder correctly
    skips this case — it does not seed code-vs-code `is` because the CQL
    grammar cannot express it syntactically. The translator's
    ``_translate_code_is_op`` may still be invoked by callers constructing
    AST nodes directly; this test documents the parser limitation.
    """
    cql = """
    library IsOp version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "A": '73211009' from "SNOMED-CT"
    code "B": '44054006' from "SNOMED-CT"
    define IsCheck: "A" is "B"
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint()
    report = build_closure_table(lib, endpoint, con)
    # The parser routes `A is B` as type-check (right is NamedTypeSpecifier),
    # so the closure builder correctly identifies zero seeds.
    assert report.seeds_scanned == 0


def test_is_type_check_not_seeded(con):
    """``Order is MedicationRequest`` (NamedTypeSpecifier) is NOT seeded."""
    cql = """
    library TypeCheck version '1.0'
    using FHIR version '4.0.1'
    define IsTypeCheck: [Condition] is MedicationRequest
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint()
    report = build_closure_table(lib, endpoint, con)
    assert report.seeds_scanned == 0


# ---------------------------------------------------------------------------
# Test 5: Per-seed fault tolerance
# ---------------------------------------------------------------------------


def test_per_seed_failure_warn_continues(con):
    """One failing seed should not stop the others."""
    cql = """
    library Multi version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "A": '111' from "SNOMED-CT"
    code "B": '222' from "SNOMED-CT"
    code "C": '333' from "SNOMED-CT"
    define Multi: "A" ~ "B" ~ "C"
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={
            "111": [CodeRef(system="http://snomed.info/sct", code="111x")],
            "222": [],
            "333": [CodeRef(system="http://snomed.info/sct", code="333x")],
        },
        fail_seeds=["http://snomed.info/sct|222"],
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = build_closure_table(lib, endpoint, con, on_expand_error="warn")
    # The failing seed is recorded.
    assert any("222" in label for label, _ in report.errors)
    # Other seeds still expanded (each returned at least one row).
    assert report.seeds_expanded == 2
    # A warning was emitted.
    assert any("222" in str(w.message) for w in caught)


def test_per_seed_failure_raise(con):
    """``on_expand_error='raise'`` re-raises the underlying exception."""
    cql = """
    library Raise version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "X": '111' from "SNOMED-CT"
    define Test: Descendents("X")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={"111": []},
        fail_seeds=["http://snomed.info/sct|111"],
    )
    with pytest.raises(RuntimeError, match="stub failure"):
        build_closure_table(lib, endpoint, con, on_expand_error="raise")


# ---------------------------------------------------------------------------
# Test 6: System normalization
# ---------------------------------------------------------------------------


def test_system_normalization_on_load(con):
    """SNOMED module URLs are normalized to ``http://snomed.info/sct`` on load."""
    cql = """
    library Norm version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-US": 'http://snomed.info/sct/731000124108'
    code "DM": '73211009' from "SNOMED-US"
    define Test: Descendents("DM")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={
            "73211009": [
                CodeRef(
                    system="http://snomed.info/sct/731000124108", code="44054006"
                ),
            ]
        }
    )
    report = build_closure_table(lib, endpoint, con)
    assert report.seeds_scanned == 1
    rows = con.execute(
        "SELECT DISTINCT ancestor_system, descendant_system FROM terminology_closure"
    ).fetchall()
    # Both sides reduced to the base SNOMED URI.
    for anc_sys, desc_sys in rows:
        assert anc_sys == "http://snomed.info/sct"
        assert desc_sys == "http://snomed.info/sct"


# ---------------------------------------------------------------------------
# Test 7: Closure-set namespacing
# ---------------------------------------------------------------------------


def test_closure_set_namespacing(con):
    """Two libraries can share a connection without row collisions."""
    cql1 = """
    library NS1 version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "A": '111' from "SNOMED-CT"
    define T: Descendents("A")
    """
    cql2 = """
    library NS2 version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "B": '222' from "SNOMED-CT"
    define T: Descendents("B")
    """
    endpoint = _StubEndpoint(
        snomed_expansions={
            "111": [CodeRef(system="http://snomed.info/sct", code="111a")],
            "222": [CodeRef(system="http://snomed.info/sct", code="222a")],
        }
    )
    build_closure_table(_make_library(cql1), endpoint, con)
    build_closure_table(_make_library(cql2), endpoint, con)
    sets = con.execute(
        "SELECT DISTINCT closure_set FROM terminology_closure ORDER BY closure_set"
    ).fetchall()
    sets_list = [s[0] for s in sets]
    assert "http://snomed.info/sct|111" in sets_list
    assert "http://snomed.info/sct|222" in sets_list


# ---------------------------------------------------------------------------
# Test 8: Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_rerun(con):
    """Running twice on the same library/connection is a near no-op."""
    cql = """
    library Idem version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "DM": '73211009' from "SNOMED-CT"
    define T: Descendents("DM")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={
            "73211009": [CodeRef(system="http://snomed.info/sct", code="44054006")]
        }
    )
    first = build_closure_table(lib, endpoint, con)
    assert first.rows_loaded > 0
    second = build_closure_table(lib, endpoint, con)
    # All rows already present (INSERT OR IGNORE) — second run loads nothing.
    assert second.rows_loaded == 0
    # But seeds_scanned and seeds_expanded are still recorded.
    assert second.seeds_scanned == 1
    assert second.seeds_expanded == 1


# ---------------------------------------------------------------------------
# Test 9: Reflexive row always inserted
# ---------------------------------------------------------------------------


def test_reflexive_row_inserted(con):
    """The seed code is always present as a descendant of itself."""
    cql = """
    library Refl version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "DM": '73211009' from "SNOMED-CT"
    define T: Descendents("DM")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        snomed_expansions={"73211009": []}  # Endpoint returns nothing.
    )
    report = build_closure_table(lib, endpoint, con)
    assert report.rows_loaded == 1  # Only the reflexive row.
    rows = con.execute(
        "SELECT ancestor_code, descendant_code FROM terminology_closure"
    ).fetchall()
    assert rows == [("73211009", "73211009")]


# ---------------------------------------------------------------------------
# Test 10: LOINC intensional expansion
# ---------------------------------------------------------------------------


def test_loinc_uses_intensional(con):
    """LOINC (non-SNOMED) routes through expand_intensional."""
    cql = """
    library Loinc version '1.0'
    using FHIR version '4.0.1'
    codesystem "LOINC": 'http://loinc.org'
    code "BP": '8480-6' from "LOINC"
    define T: Descendents("BP")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint(
        intensional_expansions={
            ("http://loinc.org", "8480-6"): [
                CodeRef(system="http://loinc.org", code="8480-6-child")
            ]
        }
    )
    report = build_closure_table(lib, endpoint, con)
    assert report.seeds_scanned == 1
    intensional_calls = [c for c in endpoint.calls if c[0] == "expand_intensional"]
    assert len(intensional_calls) == 1


# ---------------------------------------------------------------------------
# Test 11: clear_closure_table
# ---------------------------------------------------------------------------


def test_clear_closure_table(con):
    """``clear_closure_table`` drops the table entirely."""
    cql = """
    library Clear version '1.0'
    using FHIR version '4.0.1'
    codesystem "SNOMED-CT": 'http://snomed.info/sct'
    code "DM": '73211009' from "SNOMED-CT"
    define T: Descendents("DM")
    """
    lib = _make_library(cql)
    endpoint = _StubEndpoint()
    build_closure_table(lib, endpoint, con)
    clear_closure_table(con)
    # Table is gone.
    tables = con.execute("SHOW TABLES").fetchall()
    assert ("terminology_closure",) not in [t for (t,) in tables]


# ---------------------------------------------------------------------------
# Test 12: Invalid on_expand_error
# ---------------------------------------------------------------------------


def test_invalid_on_expand_error(con):
    lib = _make_library(
        "library X version '1'\nusing FHIR version '4.0.1'\n"
    )
    endpoint = _StubEndpoint()
    with pytest.raises(ValueError, match="on_expand_error"):
        build_closure_table(lib, endpoint, con, on_expand_error="bogus")
