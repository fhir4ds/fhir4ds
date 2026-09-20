"""Evolution iter 6 / Domain 2 EXPLORER regressions (2026-09-20, duckdb 1.5.5).

Found via 800-case generative dual-path fuzz (seed 20260920) + boundary
probes; all four were Python-fallback defects (native correct):

- QA-005: minute-precision DateTime ± minute-quantity raised KeyError
  ('minute','minute') — _UNIT_DIVISORS has no diagonal entries.
- QA-006: DateTime/Date arithmetic results lost temporal typing (raw
  strings) so comparisons fell into plain-string ordering
  (`(@2016-02-29 - 1 month) > 'abc'` -> False instead of empty); also
  aligned bare-T day-precision DateTime renders with native ('...T00').
- QA-007: `('a'|'b') / {}` aborted the whole enclosing expression —
  make_param raised 'Unexpected collection' before the nullable check
  could see the empty sibling (§4.4.1 empty propagation must win).
- QA-008: `{} contains (1|2)` returned False — the left-empty
  short-circuit ran before the §6.4.3 singleton violation check.
"""

import json

import duckdb
import pytest

from fhir4ds.fhirpath.duckdb.extension import register_fhirpath


def _cpp_connection():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is True
    return con


def _python_fallback_connection(monkeypatch):
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect()
    assert register_fhirpath(con) is False
    return con


@pytest.fixture
def cpp():
    return _cpp_connection()


@pytest.fixture
def py(monkeypatch):
    return _python_fallback_connection(monkeypatch)


def _run(con, expr, resource=None):
    payload = json.dumps(resource if resource is not None else {"v": None})
    row = con.execute("SELECT fhirpath(?, ?)", [payload, expr]).fetchone()
    result = row[0]
    if isinstance(result, str):
        return json.loads(result)
    return result


# ---------------------------------------------------------------------------
# QA-005: minute-precision DateTime ± minute-quantity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("@2024-01-01T10:30 + 90 minutes", ["2024-01-01T12:00"]),
        ("@2024-01-01T10:30 + 1 minute", ["2024-01-01T10:31"]),
        ("@2024-01-01T10:30 - 45 minutes", ["2024-01-01T09:45"]),
        ("@2024-01-01T10:30 + 90 'min'", ["2024-01-01T12:00"]),
        # finer units truncate to the input precision (minute)
        ("@2024-01-01T10:30 + 30 seconds", ["2024-01-01T10:30"]),
        # coarser precision truncates toward hours
        ("@2024-01-01T10 + 90 minutes", ["2024-01-01T11"]),
        # second-precision applies directly
        ("@2024-01-01T10:30:00 + 45 minutes", ["2024-01-01T11:15:00"]),
    ],
)
def test_minute_precision_datetime_minute_arithmetic_parity_evol_it6(cpp, py, expr, expected):
    assert _run(cpp, expr) == expected
    assert _run(py, expr) == expected


# ---------------------------------------------------------------------------
# QA-006: temporal typing of arithmetic results + bare-T renders
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr,expected",
    [
        # bare-T day-precision DateTime renders with the T00 hour form (native)
        ("@2024-01-01T + 1 day", ["2024-01-02T00"]),
        ("@2024-01-01T + 1 hour", ["2024-01-01T01"]),
        ("@2024-01-01T - 1 day", ["2023-12-31T00"]),
        ("@2024-01-01T + 90 minutes", ["2024-01-01T01"]),
        ("@2024-01-01T + 1 minute", ["2024-01-01T00"]),
        # month/year precision keeps the marker-free render
        ("@2024T + 1 year", ["2025"]),
        ("@2024-01T + 1 month", ["2024-02"]),
        # sub-month units at month/year precision are no-op truncation
        ("@2024-01T + 1 hour", ["2024-01"]),
        ("@2024T + 1 hour", ["2024"]),
    ],
)
def test_datetime_arithmetic_render_parity_evol_it6(cpp, py, expr, expected):
    assert _run(cpp, expr) == expected
    assert _run(py, expr) == expected


@pytest.mark.parametrize(
    "expr,expected",
    [
        # temporal-vs-plain-string ordering must be EMPTY (type error), not
        # plain-string comparison results
        ("(@2016-02-29 - 1 month) > 'abc'", []),
        ("(@2016-01-31 + 1 month) > '  '", []),
        ("(@2024-01-01T10:00 + 1 day) > 'zzz'", []),
        ("(@2015-02-04 + 1 day) > 'zzz'", []),
        ("(@2024T + 1 year) > 'abc'", []),
        ("(@2024-01T + 1 month) > 'abc'", []),
        # string equality transport is preserved
        ("(@2016-02-29 - 1 month) = '2016-01-29'", ["true"]),
        ("(@2016-02-29 - 1 month) = @2016-01-29", ["true"]),
        ("(@2015-02-04 + 1 day) = '2015-02-05'", ["true"]),
        ("(@2024-01-01T10:30 + 1 day) = '2024-01-02T10:30'", ["true"]),
        ("(@2024T + 1 year) = '2025'", ["true"]),
        ("(@2024-01T + 1 month) = '2024-02'", ["true"]),
        # arithmetic results keep temporal typing
        ("(@2024-01-01T + 1 day).type().name", ["DateTime"]),
        ("(@2024-01-01 + 1 day).type().name", ["Date"]),
    ],
)
def test_datetime_arithmetic_result_typing_parity_evol_it6(cpp, py, expr, expected):
    assert _run(cpp, expr) == expected
    assert _run(py, expr) == expected


# ---------------------------------------------------------------------------
# QA-007: empty propagation wins over sibling operand errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("('a'|'b') / {}", []),
        ("true | ('a'|'b') / {}", ["true"]),
        ("false = true | ('a'|'b') / {}", ["false"]),
        ("true | ('a'|'b') + {}", ["true"]),
        ("true | 'a' / {}", ["true"]),
        ("('a'|'b') div {}", []),
        ("('a'|'b') mod {}", []),
        ("('a'|'b') * {}", []),
        ("('a'|'b') - {}", []),
        # empty-RHS arithmetic on valid singletons stays empty
        ("1 / {}", []),
        ("1 / 'a'", []),
        # a NON-empty sibling error still aborts (FP-19 EXPLORER doctrine)
        ("true | 1 / 'a'", []),
    ],
)
def test_empty_propagation_beats_sibling_errors_parity_evol_it6(cpp, py, expr, expected):
    assert _run(cpp, expr) == expected
    assert _run(py, expr) == expected


def test_non_nullable_equivalence_unaffected_evol_it6(cpp, py):
    # `~` is not nullable: empties must reach the fn ({} ~ {} is true)
    assert _run(cpp, "{} ~ {}") == ["true"]
    assert _run(py, "{} ~ {}") == ["true"]


# ---------------------------------------------------------------------------
# QA-008: singleton violation beats empty short-circuit in contains/in
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("{} contains (1|2)", []),
        ("{} in (1|2)", []),
        ("(1|2) in {}", []),
        # singleton operands keep empty-propagation semantics
        ("{} contains 1", ["false"]),
        ("{} in {}", []),
        ("(1|2) contains {}", []),
        ("1 in {}", ["false"]),
        ("'a' in ('a'|'b')", ["true"]),
        ("('a'|'b') contains 'a'", ["true"]),
    ],
)
def test_membership_singleton_error_beats_empty_short_circuit_evol_it6(cpp, py, expr, expected):
    assert _run(cpp, expr) == expected
    assert _run(py, expr) == expected


def test_membership_dynamic_multi_item_right_operand_evol_it6(cpp, py):
    resource = {
        "resourceType": "Patient",
        "id": "example",
        "name": [
            {"family": "Chalmers", "given": ["John", "Andy"], "use": "official"},
            {"family": "Chalmers2", "given": ["Jo"], "use": "maiden"},
        ],
    }
    # name.use is a 2-item collection: `{} contains name.use` signals the
    # singleton violation (-> empty at the UDF boundary), not False
    assert _run(cpp, "{} contains name.use", resource) == []
    assert _run(py, "{} contains name.use", resource) == []
    assert _run(cpp, "60 's' <= {} contains name.use", resource) == []
    assert _run(py, "60 's' <= {} contains name.use", resource) == []
