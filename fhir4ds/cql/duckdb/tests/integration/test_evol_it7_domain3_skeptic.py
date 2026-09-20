"""Iteration 7 / Domain 3 (CQL translation) SKEPTIC regression coverage.

Three translator/parser-level defects found by the hypothesis-driven probe
battery (.temp/qa/evol_it7_d3_skeptic/):

- QA-009 (HIGH): `union` over dynamic FHIR interval operands (E.period)
  fell into list-union semantics — BinderException (VARCHAR[] vs VARCHAR
  CASE mix) for period-vs-literal, or list_concat of Period JSON strings
  for period-vs-period — instead of the CQL 1.5 §19.31 interval union.
- QA-010 (MEDIUM): bare `expand X.period per <unit>` / `collapse X.period
  per <unit>` failed to parse (trailing PER tokens) because the bare-form
  branch parsed only a primary expression, leaving the property chain
  dangling.
- QA-011 (MEDIUM): expand/collapse defines were not marked stored-list —
  Count(X) counted CTE rows (1) instead of list elements, First(X)
  character-sliced the JSON array text, and inline Count(expand ...)
  BinderException'd on list_count over VARCHAR JSON.
"""

import duckdb
import pytest

from fhir4ds.cql import parse_cql
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.loader import FHIRDataLoader
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.errors import ParseError
from fhir4ds.cql.translator import CQLToSQLTranslator

_PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "gender": "male",
}
_ENCOUNTER_1 = {
    "resourceType": "Encounter",
    "id": "e1",
    "status": "planned",
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2024-06-15T08:30:00", "end": "2024-06-25T00:00:00"},
}
_ENCOUNTER_2 = {
    "resourceType": "Encounter",
    "id": "e2",
    "status": "finished",
    "subject": {"reference": "Patient/p1"},
    "period": {"start": "2024-06-25T00:00:00", "end": "2024-07-05T00:00:00"},
}


def _connection():
    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    FHIRDataLoader(con).load_resources(
        [_PATIENT, _ENCOUNTER_1, _ENCOUNTER_2]
    )
    return con


def _define_values(cql: str, names):
    """Translate a library and return {define_name: value} for one patient.

    The final population projection orders columns alphabetically by define
    name (not library order), so values are mapped via the cursor
    description.
    """
    con = _connection()
    try:
        library = parse_cql(cql)
        sql = CQLToSQLTranslator(library).translate_library_to_population_sql(
            library
        )
        cursor = con.execute(sql)
        row = cursor.fetchone()
        cols = [d[0] for d in cursor.description]
    finally:
        con.close()
    assert row is not None, "population SQL returned no row"
    return {col: value for col, value in zip(cols, row)}


class TestDynamicIntervalUnionEvolIt7Skeptic:
    """QA-009: union over dynamic FHIR periods must be the §19.31 interval
    union, not a list concat / mixed-type CASE."""

    _CQL = """
    library U version '1.0'
    using FHIR version '4.0.1'
    context Patient
    define E1: First([Encounter] E where E.status = 'planned')
    define E2: First([Encounter] E where E.status = 'finished')
    define U1: E1.period union Interval[@2024-06-20T00:00:00, @2024-06-30T00:00:00]
    define U2: Interval[@2024-06-20T00:00:00, @2024-06-30T00:00:00] union E1.period
    define U3: E1.period union E2.period
    define StaticUnion: Interval[1, 5] union Interval[5, 10]
    """

    def test_dynamic_period_union_literal_produces_merged_interval(self):
        vals = _define_values(self._CQL, None)
        u1 = vals["U1"]
        u1_text = u1[0] if isinstance(u1, list) else u1
        assert '"low"' in u1_text and '"high"' in u1_text, (
            f"U1 should be an interval JSON object; got {u1!r}"
        )
        assert "2024-06-15T08:30:00" in u1_text and "2024-06-30T00:00:00" in u1_text, (
            f"U1 should merge the overlapping periods; got {u1!r}"
        )

    def test_literal_union_dynamic_period_both_orders_agree(self):
        vals = _define_values(self._CQL, None)
        u1, u2 = vals["U1"], vals["U2"]
        # Accept the singleton-list transport (List-typed defines project
        # through a typed list column) by comparing text forms.
        _t = lambda v: (v[0] if isinstance(v, list) else v)
        assert _t(u1) == _t(u2), (
            f"union is symmetric; got U1={u1!r} vs U2={u2!r}"
        )

    def test_dynamic_period_union_dynamic_period_merges_shared_endpoint(self):
        vals = _define_values(self._CQL, None)
        u3 = vals["U3"]
        u3_text = u3[0] if isinstance(u3, list) else u3
        # e1 ends exactly where e2 starts (closed endpoints) — overlap, so a
        # single merged interval [06-15T08:30, 07-05T00:00] must come back.
        assert '"low"' in u3_text, (
            f"U3 should be an interval JSON object; got {u3!r}"
        )
        assert "2024-06-15T08:30:00" in u3_text and "2024-07-05T00:00:00" in u3_text

    def test_static_interval_union_unchanged(self):
        vals = _define_values(self._CQL, None)
        static = vals["StaticUnion"]
        static_text = static[0] if isinstance(static, list) else static
        assert '"low": "1"' in static_text and '"high": "10"' in static_text


class TestBareExpandCollapsePropertyPathEvolIt7Skeptic:
    """QA-010: `expand X.period per day` must parse."""

    def test_expand_property_path_per_day_parses(self):
        expr = parse_expression("expand E1.period per day")
        assert expr.name.lower() == "expand"
        assert len(expr.arguments) == 2

    def test_collapse_property_path_per_day_parses(self):
        expr = parse_expression("collapse E1.period per day")
        assert expr.name.lower() == "collapse"
        assert len(expr.arguments) == 2

    def test_existing_expand_forms_still_parse(self):
        for src in (
            "expand Interval[1, 10] per 2",
            "expand { Interval[1, 10] }",
            "expand E1 per day",
            "collapse { Interval[1, 4], Interval[4, 8] } per 2",
        ):
            parse_expression(src)  # must not raise

    def test_trailing_per_without_value_still_rejected(self):
        with pytest.raises(ParseError):
            parse_expression("expand E1.period per")


class TestExpandCollapseStoredListConsumersEvolIt7Skeptic:
    """QA-011: Count/First over expand/collapse defines use list semantics."""

    _CQL = """
    library X version '1.0'
    using FHIR version '4.0.1'
    context Patient
    define X: expand Interval[@2024-01-01, @2024-01-05] per day
    define CountX: Count(X)
    define FirstX: First(X)
    define Y: expand { Interval[@2024-01-01, @2024-01-03], Interval[@2024-01-05, @2024-01-06] } per day
    define CountY: Count(Y)
    define C: collapse { Interval[1, 4], Interval[4, 8] } per 2
    define CountC: Count(C)
    define InlineCount: Count(expand Interval[@2024-01-01, @2024-01-05] per day)
    """

    def test_count_over_expand_define_counts_elements(self):
        vals = _define_values(self._CQL, None)
        assert vals["CountX"] == 5, f"Count(X) should be 5; got {vals['CountX']!r}"

    def test_first_over_expand_define_returns_first_element(self):
        vals = _define_values(self._CQL, None)
        first = vals["FirstX"]
        assert first == "2024-01-01", (
            f"First(X) should be '2024-01-01'; got {first!r}"
        )

    def test_count_over_multi_interval_expand_define(self):
        vals = _define_values(self._CQL, None)
        assert vals["CountY"] == 5, (
            f"Count(Y) should be 5 (3+2 days); got {vals['CountY']!r}"
        )

    def test_count_over_collapse_define_counts_merged_intervals(self):
        vals = _define_values(self._CQL, None)
        assert vals["CountC"] == 1, (
            f"Count(C) should be 1 merged interval; got {vals['CountC']!r}"
        )

    def test_inline_count_over_expand(self):
        vals = _define_values(self._CQL, None)
        assert vals["InlineCount"] == 5, (
            f"inline Count(expand ...) should be 5; got {vals['InlineCount']!r}"
        )
