"""v0.0.24 it4 (domain 2 SKEPTIC) corner-case parity regressions.

Three divergences found by the it4 dual-engine probe and fixed in
9e2dbd99bc2 + the e10 sign follow-up:
1. exact decimal boundaries for E-notation values (half-unit = 0.5 *
   10^Decimal-exponent, precision-padded rendering incl. near-zero)
2. join() requires String items (error -> empty at the UDF boundary)
3. complex-vs-temporal equality is definitively false
"""
from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _python_fallback_connection(monkeypatch) -> duckdb.DuckDBPyConnection:
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(con) is False
    return con


RES = json.dumps(
    {
        "resourceType": "Observation",
        "id": "o1",
        "status": "final",
        "code": {"text": "t"},
        "negExp": -2.5e-3,
        "posExp": 1.25e3,
    }
)

BOUNDARY_CASES = [
    ("negExp.highBoundary(2)", ["0.00"]),
    ("negExp.lowBoundary(8)", ["-0.00255000"]),
    ("posExp.lowBoundary(4)", ["1249.9500"]),
]

# Documented divergence (NOT a parity bug): for JSON-double inputs at
# precision 0 the fallback serializes its float result with a trailing
# ".0" (['1251.0']) while the native text path renders fixture-style
# (['1251'], official LowBoundaryDecimalExponent1 pins "945" without a
# decimal point). Values agree; the fixture convention has no decimal
# point, so native is the aligned surface.

JOIN_CASES = [
    ("('a' | 'b').join('-')", ["a-b"]),
    ("(1 | 2 | 3).join('-')", []),  # non-String items: error -> empty
]

EQUALITY_CASES = [
    ("code = true", ["false"]),
    ("code = @2020-01-01", ["false"]),
    ("code != @2020-01-01", ["true"]),
]


class TestIt4CornerParity:
    def _run(self, monkeypatch, cases):
        native = _connection()
        fallback = _python_fallback_connection(monkeypatch)
        try:
            for expression, expected in cases:
                cpp = native.execute(
                    "SELECT fhirpath(?::JSON, ?)", [RES, expression]
                ).fetchone()[0]
                py = fallback.execute(
                    "SELECT fhirpath(?::JSON, ?)", [RES, expression]
                ).fetchone()[0]
                assert cpp == py == expected, (expression, cpp, py, expected)
        finally:
            native.close()
            fallback.close()

    def test_boundary_e_notation_parity_it4(self, monkeypatch):
        self._run(monkeypatch, BOUNDARY_CASES)

    def test_join_requires_strings_it4(self, monkeypatch):
        self._run(monkeypatch, JOIN_CASES)

    def test_complex_vs_temporal_equality_it4(self, monkeypatch):
        self._run(monkeypatch, EQUALITY_CASES)
