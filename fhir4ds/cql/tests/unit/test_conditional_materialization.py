"""Phase 2 Item 3: conditional materialization by reference count.

CTEDefinition.materialized is now tri-state:
- True  -> forced AS MATERIALIZED (e.g. shared _rt_<Type> base scans)
- False -> forced plain CTE
- None  -> AUTO: SQLFragment.to_sql() keeps MATERIALIZED only for CTEs
           referenced by more than one consumer.

Rationale (measured): the Phase-1 pathology (DuckDB inlining retrieves into
consumers and pushing heavy predicates into base table scans) only recurs
when a MULTI-reference CTE is inlined at several sites. Single-reference
CTEs inline once — equal-or-faster, and avoids eager materialization cost
(CMS2 rung100 2046->1910ms, CMS130 rung1000 12801->11658ms).
"""
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator

_CQL_MULTI = """
library Test version '1.0.0'
valueset "VS1": 'http://example.org/vs1'
valueset "VS2": 'http://example.org/vs2'
parameter "Measurement Period" Interval<DateTime>
  default Interval[@2026-01-01T00:00:00.000, @2026-12-31T23:59:59.999]
context Patient
define "Cond1": [Condition: "VS1"]
define "Cond2": [Condition: "VS2"]
define "First1": First("Cond1")
define "Count1": Count("Cond1")
define "IP": exists "Cond1" or exists "Cond2"
"""

_CQL_SINGLE = """
library Test version '1.0.0'
valueset "VS1": 'http://example.org/vs1'
parameter "Measurement Period" Interval<DateTime>
  default Interval[@2026-01-01T00:00:00.000, @2026-12-31T23:59:59.999]
context Patient
define "Cond1": [Condition: "VS1"]
define "IP": exists "Cond1"
"""


def _pop_sql(cql: str) -> str:
    t = CQLToSQLTranslator()
    return t.translate_library_to_population_sql(
        library=parse_cql(cql),
        output_columns={"IP": "IP"},
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
    )


class TestConditionalMaterialization:
    def test_multi_reference_cte_stays_materialized(self):
        sql = _pop_sql(_CQL_MULTI)
        # The population define "IP" is referenced in the final SELECT and
        # its own EXISTS consumers -> multi-ref -> MATERIALIZED retained.
        assert '"IP" AS MATERIALIZED' in sql
        # Shared _rt_ bases are force-materialized.
        assert '"_rt_Condition" AS MATERIALIZED' in sql

    def test_single_reference_cte_inlines(self):
        sql = _pop_sql(_CQL_SINGLE)
        # "Condition: VS1" has exactly one consumer (the "Cond1" define) and
        # "Cond1" one consumer (the IP EXISTS) — they must NOT be forced
        # MATERIALIZED; the resolver drops the hint for single-ref CTEs.
        assert '"Condition: VS1" AS (\n' in sql
        assert '"Cond1" AS (\n' in sql

    def test_tri_state_forced_values_survive(self):
        from fhir4ds.cql.translator.types import (
            CTEDefinition,
            SQLFragment,
            SQLIdentifier,
            SQLSelect,
        )
        sel = SQLSelect(columns=[SQLIdentifier(name="x")],
                        from_clause=SQLIdentifier(name="t"))
        frag = SQLFragment(
            main_query=SQLSelect(columns=[SQLIdentifier(name="x")],
                                 from_clause=SQLIdentifier(name="c")),
            ctes=[
                CTEDefinition(name="c", query=sel, materialized=True),
            ],
        )
        assert "AS MATERIALIZED (" in frag.to_sql()
        frag2 = SQLFragment(
            main_query=SQLSelect(columns=[SQLIdentifier(name="x")],
                                 from_clause=SQLIdentifier(name="c")),
            ctes=[
                CTEDefinition(name="c", query=sel, materialized=False),
            ],
        )
        assert "AS MATERIALIZED" not in frag2.to_sql()
