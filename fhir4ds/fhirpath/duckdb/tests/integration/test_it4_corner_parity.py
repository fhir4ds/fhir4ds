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


class TestIt5TypedTemporalFieldParity:
    """v0.0.24 it5 (HISTORIAN): model-typed temporal fields compare as their
    FHIR type (native temporalValueType fix) and default-precision DateTime
    boundaries carry the default timezone (fallback fix). The '@'-prefix
    rendering on partial-precision boundary outputs is a documented
    harness-normalized divergence (fallback '@2020' vs native '2020')."""

    def test_value_time_field_orders_as_time_it5(self, monkeypatch):
        res = json.dumps(
            {"resourceType": "Observation", "valueTime": "10:30:00"}
        )
        native = _connection()
        fallback = _python_fallback_connection(monkeypatch)
        try:
            for expression, expected in [
                ("valueTime < @T11:00:00", ["true"]),
                ("valueTime = @T10:30:00", ["true"]),
                # FP-03 QA-002 pin: plain string literals stay UNCOERCED
                ("'10:30:00' < @T11:00:00", []),
            ]:
                cpp = native.execute(
                    "SELECT fhirpath(?::JSON, ?)", [res, expression]
                ).fetchone()[0]
                py = fallback.execute(
                    "SELECT fhirpath(?::JSON, ?)", [res, expression]
                ).fetchone()[0]
                assert cpp == py == expected, (expression, cpp, py)
        finally:
            native.close()
            fallback.close()

    def test_datetime_boundary_default_tz_parity_it5(self, monkeypatch):
        res = json.dumps(
            {"resourceType": "Observation", "effectiveDateTime": "2020-06-15T10:30"}
        )
        native = _connection()
        fallback = _python_fallback_connection(monkeypatch)
        try:
            for expression, expected in [
                ("effectiveDateTime.lowBoundary()", ["2020-06-15T10:30:00.000+14:00"]),
                ("effectiveDateTime.highBoundary()", ["2020-06-15T10:30:59.999-12:00"]),
            ]:
                cpp = native.execute(
                    "SELECT fhirpath(?::JSON, ?)", [res, expression]
                ).fetchone()[0]
                py = fallback.execute(
                    "SELECT fhirpath(?::JSON, ?)", [res, expression]
                ).fetchone()[0]
                assert cpp == py == expected, (expression, cpp, py)
        finally:
            native.close()
            fallback.close()


class TestIt6ExplorerBoundaryAndEquivalenceParity:
    """v0.0.24 it6 (domain 2 EXPLORER) regressions (e3edf1475a4).

    1. Native Time boundaries with an explicit precision argument preserve
       components at the input's precision (§G-5 doctrine): specified
       seconds survive, only sub-precision components take the 59/999
       (high) / 00/000 (low) fill; authored fraction digits render
       verbatim. The native output carries no '@' prefix while the
       fallback renders the literal form — normalized here (documented
       it5 divergence, harness-normalized in conformance).
    2. Fallback temporal EQUIVALENCE on typed FHIR `time` fields: the
       §6.1.2 implicit-conversion gate must classify ResourceNode-wrapped
       strings as temporal when the peer is temporal, else
       `valueTime ~ @T10:30:00` returned False while `=` returned True.
    """

    TIME_RES = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o6",
            "status": "final",
            "code": {"text": "t"},
            "valueTime": "10:30:00",
        }
    )

    def _strip_at(self, value):
        if isinstance(value, str):
            return value.lstrip("@")
        return value

    def test_time_boundary_preserves_specified_components_it6(self):
        con = _connection()
        cases = [
            ("@T10:30:00.highBoundary(9)", "T10:30:00.999"),
            ("@T10:30:00.lowBoundary(9)", "T10:30:00.000"),
            ("@T10:30:45.highBoundary(9)", "T10:30:45.999"),
            ("@T10:30:45.lowBoundary(9)", "T10:30:45.000"),
            ("@T10:30:45.123.highBoundary(9)", "T10:30:45.123"),
            ("@T10:30:00.5.highBoundary(9)", "T10:30:00.5"),
            # sub-precision inputs keep the template fill
            ("@T10:30.highBoundary(9)", "T10:30:59.999"),
            ("@T10.highBoundary(9)", "T10:59:59.999"),
            # coarser requested precision truncates
            ("@T10:30:00.highBoundary(4)", "T10:30"),
        ]
        for expression, expected in cases:
            row = con.execute(
                "SELECT fhirpath(?, ?)", [json.dumps({"resourceType": "Patient", "id": "p"}), expression]
            ).fetchone()
            assert row is not None and row[0] is not None, expression
            got = [self._strip_at(v) for v in row[0]]
            assert got == [expected], f"{expression}: {got} != ['{expected}']"

    def test_time_boundary_parity_native_vs_fallback_it6(self, monkeypatch):
        native = _connection()
        fallback = _python_fallback_connection(monkeypatch)
        for expression in [
            "@T10:30:00.highBoundary(9)",
            "@T10:30:00.lowBoundary(9)",
            "@T10:30:45.highBoundary(9)",
            "@T10:30:45.123.highBoundary(9)",
            "@T10:30.highBoundary(9)",
            "@T10:30:00.highBoundary(4)",
        ]:
            resource = json.dumps({"resourceType": "Patient", "id": "p"})
            nv = native.execute("SELECT fhirpath(?, ?)", [resource, expression]).fetchone()[0]
            fv = fallback.execute("SELECT fhirpath(?, ?)", [resource, expression]).fetchone()[0]
            assert nv is not None and fv is not None, expression
            assert [self._strip_at(v) for v in nv] == [self._strip_at(v) for v in fv], expression

    def test_typed_time_field_equivalence_it6(self):
        con = _connection()
        for expression, expected in [
            ("valueTime ~ @T10:30:00", ["true"]),
            ("valueTime !~ @T10:30:00", ["false"]),
            ("valueTime ~ @T10:30:30", ["false"]),
            ("valueTime = @T10:30:00", ["true"]),
            # Time vs Date/DateTime peer remains non-equivalent
            ("valueTime ~ @2012-01-01", ["false"]),
        ]:
            row = con.execute(
                "SELECT fhirpath(?, ?)", [self.TIME_RES, expression]
            ).fetchone()
            assert row is not None and row[0] is not None, expression
            got = [str(v).lower() for v in row[0]]
            assert got == expected, f"{expression}: {got} != {expected}"

    def test_typed_time_field_equivalence_parity_it6(self, monkeypatch):
        native = _connection()
        fallback = _python_fallback_connection(monkeypatch)
        for expression in ["valueTime ~ @T10:30:00", "valueTime ~ @T10:30:30"]:
            nv = native.execute("SELECT fhirpath(?, ?)", [self.TIME_RES, expression]).fetchone()[0]
            fv = fallback.execute("SELECT fhirpath(?, ?)", [self.TIME_RES, expression]).fetchone()[0]
            assert nv is not None and fv is not None, expression
            assert [str(v).lower() for v in nv] == [str(v).lower() for v in fv], expression
