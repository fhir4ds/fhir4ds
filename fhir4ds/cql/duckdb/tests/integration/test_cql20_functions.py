"""CQL 2.0 function additions (campaign cql20_spec_campaign, chunk CQL20-A).

Dual-backend parity tests for:
  * Round(Quantity[, precision])          — FHIR-51030, Appendix B §Round
  * Comparable(Quantity, Quantity)        — FHIR-55384, Appendix B §Comparable
  * Head(list, n) / Tail(list, n)         — FHIR-40612
  * Combine order preservation            — FHIR-52040 (2.0 order guarantee)

Semantics ground truth: CQL 2.0 (R2 STU 1) Appendix B,
https://cql.hl7.org/09-b-cqlreference.html.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql import translate_cql
from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


# ---------------------------------------------------------------------------
# Round(Quantity[, precision]) — FHIR-51030 / CQL 2.0 Appendix B §Round
# ---------------------------------------------------------------------------

ROUND_QUANTITY_CASES = [
    # (cql expression, expected raw JSON value fields)
    ("Round(2.54 'cm')", ('3.0', 'cm')),
    ("Round(-2.54 'cm')", ('-3.0', 'cm')),
    ("Round(2.4 'cm')", ('2.0', 'cm')),
    ("Round(0.5 'mg')", ('1.0', 'mg')),
    ("Round(-0.5 'mg')", ('-1.0', 'mg')),
    ("Round(3.14159 'cm', 2)", ('3.14', 'cm')),
    ("Round(2.5433 'cm', 2)", ('2.54', 'cm')),
    ("Round(1.005 'g', 2)", ('1.01', 'g')),  # exact-Decimal 1.005 ties away from zero
    ("Round(10 'kg')", ('10.0', 'kg')),
]


class TestRoundQuantity:
    @pytest.mark.parametrize("expression,expected", ROUND_QUANTITY_CASES)
    def test_round_quantity_values_match_reference(self, expression, expected):
        """Round keeps the unit verbatim and rounds the value traditionally."""
        import json

        from fhir4ds.connection import create_connection

        con = create_connection()
        try:
            sql = _translate_single(con, expression)
            raw = con.execute(f"SELECT ({sql})").fetchone()[0]
            assert raw is not None
            parsed = json.loads(raw)
            assert parsed["value"] == pytest.approx(float(expected[0]), abs=1e-9)
            assert parsed["unit"] == expected[1]
        finally:
            con.close()

    def test_round_quantity_null_is_null(self):
        from fhir4ds.connection import create_connection

        con = create_connection()
        try:
            sql = _translate_single(con, "Round(null as Quantity)")
            assert con.execute(f"SELECT ({sql})").fetchone()[0] is None
        finally:
            con.close()

    def test_round_quantity_result_stays_quantity_comparable(self):
        """Round(2.54 'cm') = 3 'cm' must compare quantity-aware (unit kept)."""
        from fhir4ds.connection import create_connection

        con = create_connection()
        try:
            sql = _translate_single(con, "Round(2.54 'cm') = 3 'cm'")
            assert con.execute(f"SELECT ({sql})").fetchone()[0] is True
        finally:
            con.close()

    def test_round_quantity_dual_backend_parity(self):
        cases = [
            "Round(2.54 'cm')",
            "Round(-0.5 'mg')",
            "Round(3.14159 'cm', 2)",
            "Round(1 year, 1)",
        ]
        py = _python_only_connection()
        cpp = _cpp_connection()
        try:
            for case in cases:
                sql = _translate_single(py, case)
                py_raw = py.execute(f"SELECT ({sql})").fetchone()[0]
                cpp_raw = cpp.execute(f"SELECT ({sql})").fetchone()[0]
                assert py_raw == cpp_raw, case
        finally:
            py.close()
            cpp.close()


# ---------------------------------------------------------------------------
# Comparable(Quantity, Quantity) — FHIR-55384 / CQL 2.0 Appendix B §Comparable
# ---------------------------------------------------------------------------

COMPARABLE_CASES = [
    # commensurable
    ("Comparable(5 'cm', 5 'm')", True),
    ("Comparable(5 'kg', 5000 'g')", True),
    ("Comparable(37 'Cel', 98.6 '[degF]')", True),
    ("Comparable(1 week, 3 'd')", True),
    ("Comparable(1 year, 6 months)", True),
    ("Comparable(2 'cm', 2 'cm')", True),
    ("Comparable(5, 5)", True),  # default unit '1' on both sides
    # not commensurable
    ("Comparable(5 'cm2', 5 'cm')", False),
    ("Comparable(1 year, 1 'a')", False),  # calendar vs UCUM year
    ("Comparable(1 'cm', 1 's')", False),
    ("Comparable(5 'xyz', 5 'xyz')", False),  # unknown UCUM code
    ("Comparable(1 year, 90 's')", False),  # calendar vs definite duration
    # null propagation
    ("Comparable(1 'cm', null)", None),
    ("Comparable(null, 1 'cm')", None),
]


class TestComparable:
    @pytest.mark.parametrize("expression,expected", COMPARABLE_CASES)
    def test_comparable_semantics(self, expression, expected):
        from fhir4ds.connection import create_connection

        con = create_connection()
        try:
            sql = _translate_single(con, expression)
            got = con.execute(f"SELECT ({sql})").fetchone()[0]
            assert got == expected, expression
        finally:
            con.close()

    def test_comparable_dual_backend_parity(self):
        py = _python_only_connection()
        cpp = _cpp_connection()
        try:
            for expression, _ in COMPARABLE_CASES:
                sql = _translate_single(py, expression)
                py_raw = py.execute(f"SELECT ({sql})").fetchone()[0]
                cpp_raw = cpp.execute(f"SELECT ({sql})").fetchone()[0]
                assert py_raw == cpp_raw, expression
        finally:
            py.close()
            cpp.close()


# ---------------------------------------------------------------------------
# Head(list, n) / Tail(list, n) — FHIR-40612
#
# The tracker asks for "Tail and Head functions with parameter"; the spec
# narrative has not landed, so the pandas/R/Unix head(x,n)/tail(x,n)
# reading is implemented: Head = first n, Tail(n) = LAST n (the zero-arg
# Tail keeps its CQL 1.5 "all but the first" meaning).
# ---------------------------------------------------------------------------

HEAD_TAIL_CASES = [
    ("Head({1,2,3,4}, 2)", [1, 2]),
    ("Head({1,2}, 5)", [1, 2]),
    ("Head({1,2,3}, 0)", []),
    ("Head({1,2,3}, null)", []),
    ("Head(null, 2)", None),
    ("Tail({1,2,3,4}, 2)", [3, 4]),
    ("Tail({1,2}, 5)", [1, 2]),
    ("Tail({1,2,3}, 1)", [3]),
    ("Tail({1,2,3}, 0)", []),
    ("Tail({1,2,3}, null)", []),
    ("Tail(null, 2)", None),
    ("Tail({1,2,3,4})", [2, 3, 4]),  # zero-arg Tail unchanged (1.5)
    ("Head({'a','b','c'}, 2)", ["a", "b"]),
    ("Tail({'a','b','c'}, 2)", ["b", "c"]),
]


class TestHeadTailWithCount:
    @pytest.mark.parametrize("expression,expected", HEAD_TAIL_CASES)
    def test_head_tail_semantics(self, expression, expected):
        from fhir4ds.connection import create_connection

        con = create_connection()
        try:
            sql = _translate_single(con, expression)
            got = con.execute(f"SELECT ({sql})").fetchone()[0]
            assert got == expected, expression
        finally:
            con.close()

    def test_head_tail_dual_backend_parity(self):
        py = _python_only_connection()
        cpp = _cpp_connection()
        try:
            for expression, _ in HEAD_TAIL_CASES:
                sql = _translate_single(py, expression)
                py_raw = py.execute(f"SELECT ({sql})").fetchone()[0]
                cpp_raw = cpp.execute(f"SELECT ({sql})").fetchone()[0]
                assert py_raw == cpp_raw, expression
        finally:
            py.close()
            cpp.close()


# ---------------------------------------------------------------------------
# Combine order preservation — FHIR-52040
# ---------------------------------------------------------------------------


class TestCombineOrderPreservation:
    """CQL 2.0 (FHIR-52040) makes Combine order-preserving: elements are
    combined in the order they appear in the source list.

    The macro lowers to ``array_to_string(list_filter(lst, ...))`` — both
    DuckDB functions preserve list order — so this pins the guarantee with
    inputs where any de-duplication or reordering would change the result.
    """

    ORDER_CASES = [
        ("Combine({'b','a','b'})", "bab"),
        ("Combine({'z','y','x','w'})", "zyxw"),
        ("Combine({'b','a','b'}, '-')", "b-a-b"),
        ("Combine({'x','y','z'}, '-')", "x-y-z"),
        ("Combine({'a', null, 'c', null, 'b'})", "acb"),
    ]

    @pytest.mark.parametrize("expression,expected", ORDER_CASES)
    def test_combine_preserves_source_order(self, expression, expected):
        from fhir4ds.connection import create_connection

        con = create_connection()
        try:
            sql = _translate_single(con, expression)
            got = con.execute(f"SELECT ({sql})").fetchone()[0]
            assert got == expected, expression
        finally:
            con.close()

    def test_combine_order_dual_backend_parity(self):
        py = _python_only_connection()
        cpp = _cpp_connection()
        try:
            for expression, _ in self.ORDER_CASES:
                sql = _translate_single(py, expression)
                py_raw = py.execute(f"SELECT ({sql})").fetchone()[0]
                cpp_raw = cpp.execute(f"SELECT ({sql})").fetchone()[0]
                assert py_raw == cpp_raw, expression
        finally:
            py.close()
            cpp.close()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _translate_single(con, expression: str) -> str:
    """Translate a single CQL expression via a one-define library."""
    from fhir4ds.cql import translate_cql

    result = translate_cql(f"library Probe\ndefine Probe: {expression}")
    sql = result["Probe"]
    return str(sql.to_sql() if hasattr(sql, "to_sql") else sql)
