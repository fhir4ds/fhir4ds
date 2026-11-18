"""Phase 2 Item 3: conditional materialization by reference count.

CTEDefinition.materialized is now tri-state:
- True  -> forced AS MATERIALIZED (e.g. shared _rt_<Type> base scans)
- False -> forced plain CTE
- None  -> AUTO: SQLFragment.to_sql() keeps MATERIALIZED for CTEs
           referenced by more than one consumer OR whose (single)
           reference is nested inside a subquery (CMS133 regression:
           inlining a CTE into a correlated EXISTS re-evaluated it per
           outer row, 732ms -> ~2000ms; see
           SQLFragment._resolve_materialization).

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
        # "Condition: VS1" is consumed as a TOP-LEVEL FROM table of the
        # "Cond1" define — single top-level reference still INLINES (the
        # phase-2 win is preserved). "Cond1" itself is consumed inside a
        # correlated EXISTS — a NESTED reference (the exact shape that
        # regressed CMS133, 732ms -> ~2000ms when inlined) — so it KEEPS
        # MATERIALIZED under the nesting rule.
        assert '"Condition: VS1" AS (\n' in sql
        assert '"Cond1" AS MATERIALIZED' in sql

    def test_single_reference_toplevel_inline_still_happens(self):
        """Resolver-level check: a single TOP-LEVEL FROM reference inlines.

        The nesting rule must not collapse AUTO back to always-materialized:
        a CTE consumed as a plain top-level FROM table of its consumer's
        outermost SELECT still drops the MATERIALIZED hint.
        """
        from fhir4ds.cql.translator.types import (
            CTEDefinition,
            SQLFragment,
            SQLIdentifier,
            SQLSelect,
        )
        frag = SQLFragment(
            main_query=SQLSelect(
                columns=[SQLIdentifier(name="x")],
                from_clause=SQLIdentifier(name="c"),
            ),
            ctes=[
                CTEDefinition(
                    name="c",
                    query=SQLSelect(
                        columns=[SQLIdentifier(name="x")],
                        from_clause=SQLIdentifier(name="t"),
                    ),
                ),
            ],
        )
        sql = frag.to_sql()
        assert "AS MATERIALIZED (" not in sql

    def test_single_nested_reference_keeps_materialized(self):
        """A single reference inside a subquery keeps MATERIALIZED.

        Regression guard for CMS133: the Condition retrieve CTE whose only
        reference was an arm of a UNION chain inside a correlated EXISTS.
        Reproduced at paren depth 2 with a scalar subquery consumer.
        """
        from fhir4ds.cql.translator.types import (
            CTEDefinition,
            SQLFragment,
            SQLIdentifier,
            SQLRaw,
            SQLSelect,
        )
        # main query references "c" only inside EXISTS (SELECT 1 FROM c)
        main = SQLSelect(
            columns=[SQLRaw(raw_sql="(SELECT 1 FROM c WHERE c.x = o.x)")],
            from_clause=SQLIdentifier(name="o"),
        )
        frag = SQLFragment(
            main_query=main,
            ctes=[
                CTEDefinition(
                    name="c",
                    query=SQLSelect(
                        columns=[SQLIdentifier(name="x")],
                        from_clause=SQLIdentifier(name="t"),
                    ),
                ),
            ],
        )
        assert "c AS MATERIALIZED (" in frag.to_sql()

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
