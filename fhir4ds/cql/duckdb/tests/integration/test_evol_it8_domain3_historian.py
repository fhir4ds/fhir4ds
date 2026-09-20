"""Iteration 8 / Domain 3 (CQL translation) HISTORIAN regression coverage.

Systematic query-construct walkthrough (CQL 1.5 §10 / Appendix B) found two
translator defects, both pre-existing on the clean tree (verified via
git-checkout bisect):

- QA-012 (MEDIUM): `distinct (<query>)` over a rows-shaped query return
  emitted `"Distinct"(LIST((SELECT ...)))` — the LIST aggregate next to the
  outer `_pt.patient_id` projection raised a DuckDB GROUP BY
  BinderException. Fixed by coercing the rows source to the per-patient
  list subquery before the Distinct wrap.
- QA-013 (MEDIUM): `<retrieve> O aggregate T starting <init>: <body>`
  folded `(SELECT * FROM <cte>)` — "Subquery returns N columns" — and the
  accumulator/element types did not bind. Fixed by materializing the
  patient-correlated per-patient resource list (VARCHAR elements, _lt_
  alias binding for fhirpath element access, DECIMAL accumulator binding
  for numeric starts) and classifying aggregate queries PATIENT_SCALAR.
"""

import duckdb

from fhir4ds.cql import parse_cql
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.loader import FHIRDataLoader
from fhir4ds.cql.translator import CQLToSQLTranslator

_RESOURCES = [
    {"resourceType": "Patient", "id": "p1"},
    {"resourceType": "Patient", "id": "p2"},
    {"resourceType": "Observation", "id": "o1", "status": "final",
     "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Observation", "id": "o2", "status": "final",
     "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Observation", "id": "o3", "status": "preliminary",
     "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Observation", "id": "z1", "status": "final",
     "subject": {"reference": "Patient/p2"}},
]


def _define_values(cql: str):
    con = duckdb.connect()
    try:
        _register_python_supplements(
            con, cpp_loaded=False, include_fhirpath=True
        )
        FHIRDataLoader(con).load_resources(_RESOURCES)
        library = parse_cql(cql)
        sql = CQLToSQLTranslator(library).translate_library_to_population_sql(
            library
        )
        return {
            pid: value
            for pid, value in con.execute(sql).fetchall()
        }
    finally:
        con.close()


_AGG_TEMPLATE = """
library Agg version '1.0'
using FHIR version '4.0.1'
context Patient
define RESULT: {expr}
"""


class TestDistinctOverQueryReturnEvolIt8Historian:
    """QA-012: distinct(<query>) must not put LIST() next to patient_id."""

    def test_distinct_query_return_executes_and_dedups(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="distinct ([Observation] O return O.status)"
        ))
        # List-typed defines transport through a per-patient LIST()
        # projection (singleton outer list); p1 sees all three statuses.
        assert sorted(vals["p1"][0]) == ["final", "preliminary"], (
            f"expected the deduplicated statuses; got {vals}"
        )

    def test_distinct_query_return_sql_has_no_bare_list_wrap(self):
        library = parse_cql(_AGG_TEMPLATE.format(
            expr="distinct ([Observation] O return O.status)"
        ))
        sql = CQLToSQLTranslator(library).translate_library_to_population_sql(
            library
        )
        assert '"Distinct"(LIST(' not in sql, (
            "bare LIST() wrap regressed (GROUP BY binder failure shape)"
        )


class TestAggregateOverRetrieveEvolIt8Historian:
    """QA-013: aggregate over a retrieve folds per-patient element lists."""

    def test_count_fold(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="[Observation] O aggregate T starting 0: T + 1"
        ))
        assert float(vals["p1"]) == 3.0
        assert float(vals["p2"]) == 1.0

    def test_conditional_body_fold(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="[Observation] O aggregate T starting 0: "
                 "T + (if O.status = 'final' then 1 else 0)"
        ))
        assert float(vals["p1"]) == 2.0
        assert float(vals["p2"]) == 1.0

    def test_literal_list_aggregate_unaffected(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="{1,2,3} X aggregate T starting 0: T + X"
        ))
        assert float(vals["p1"]) == 6.0

    def test_rows_do_not_leak_across_patients(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="[Observation] O aggregate T starting 0: "
                 "T + (if O.status = 'preliminary' then 1 else 0)"
        ))
        assert float(vals["p1"]) == 1.0
        assert float(vals["p2"]) == 0.0

    def test_aggregate_query_is_patient_scalar(self):
        library = parse_cql(_AGG_TEMPLATE.format(
            expr="[Observation] O aggregate T starting 0: T + 1"
        ))
        translator = CQLToSQLTranslator()
        translator.translate_library_to_sql(library)
        meta = translator.context.definition_meta["RESULT"]
        from fhir4ds.cql.translator.context import RowShape
        assert meta.shape == RowShape.PATIENT_SCALAR, (
            "aggregate queries fold to one value per patient (§19.27)"
        )


class TestFirstLastOverExpandCollapseInlineEvolIt9Explorer:
    """QA-014 (it9 EXPLORER): First/Last directly over inline expand/collapse
    FunctionRefs must parse the JSON array text — LIST_EXTRACT over the raw
    VARCHAR character-slices it (First(collapse ...) -> '[')."""

    def test_first_over_inline_collapse(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="First(collapse { Interval[@2024-01-01, @2024-01-05], "
                 "Interval[@2024-01-04, @2024-01-10] } per day)"
        ))
        assert vals["p1"].startswith('{"low":"2024-01-01"'), (
            f"First(collapse) should be the merged interval JSON; got {vals}"
        )

    def test_first_over_inline_expand(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="First(expand Interval[@2024-01-01, @2024-01-05] per day)"
        ))
        assert vals["p1"] == "2024-01-01", (
            f"First(expand) should be '2024-01-01'; got {vals}"
        )

    def test_start_of_first_collapse(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="start of First(collapse { Interval[@2024-01-01, @2024-01-05], "
                 "Interval[@2024-01-04, @2024-01-10] } per day)"
        ))
        assert vals["p1"] == "2024-01-01"


class TestAggregateOverExpandEvolIt9Explorer:
    """QA-015 (it9 EXPLORER): aggregate over an expand query source parses
    the JSON array text to a list before the fold."""

    def test_aggregate_over_expand(self):
        vals = _define_values(_AGG_TEMPLATE.format(
            expr="(expand Interval[@2024-01-01, @2024-01-05] per day) D "
                 "aggregate T starting 0: T + 1"
        ))
        assert float(vals["p1"]) == 5.0


class TestExpandPerPrecisionRenderingEvolIt9Explorer:
    """QA-016 (it9 EXPLORER): expand of a has_time DateTime per day renders
    per-precision dates on BOTH engines (native previously emitted
    '2024-06-15T00')."""

    def test_day_per_datetime_renders_dates_native(self):
        from fhir4ds.cql.duckdb import register as register_cql
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        try:
            register_cql(con)
            row = con.execute(
                "SELECT expand_points("
                "intervalFromBounds('2024-06-15T08:30:00', '2024-06-18T00:00:00', "
                "TRUE, TRUE), "
                "parse_quantity('{\"value\": 1.0, \"unit\": \"day\"}'))"
            ).fetchone()
            assert row[0] == '["2024-06-15","2024-06-16","2024-06-17","2024-06-18"]', (
                f"native per-day expand of a DateTime must render dates; got {row[0]}"
            )
        finally:
            con.close()

    def test_day_per_datetime_matches_python_fallback(self):
        from fhir4ds.cql.duckdb import register as register_cql
        results = {}
        for native in (False, True):
            con = (
                duckdb.connect(config={"allow_unsigned_extensions": True})
                if native else duckdb.connect()
            )
            try:
                if native:
                    register_cql(con)
                else:
                    _register_python_supplements(
                        con, cpp_loaded=False, include_fhirpath=True
                    )
                row = con.execute(
                    "SELECT expand_points("
                    "intervalFromBounds('2024-06-15T08:30:00', '2024-06-18T00:00:00', "
                    "TRUE, TRUE), "
                    "parse_quantity('{\"value\": 1.0, \"unit\": \"day\"}'))"
                ).fetchone()
                results["native" if native else "python"] = row[0]
            finally:
                con.close()
        assert results["python"] == results["native"], results
