"""CQL20-F / FHIR4-15: lateral hoisting must be duckdb-wasm-portable.

duckdb-wasm's binder rejects correlated scalar subqueries nested inside a
CROSS JOIN LATERAL *projection* (CMS159 eCQM in the fhir4px wasm demo:
``Referenced table 'sub' not found! Candidate tables: '_pt'``), while
desktop DuckDB binds the same shape fine. The lateral-dedup pass must
therefore never emit that shape:

1. Subquery-bearing candidates are rewritten to hoist the SUBQUERY ITSELF
   as the lateral derived table (direct ``sub.patient_id = _pt.patient_id``
   correlation in the derived table's WHERE — the wasm-legal pattern), with
   use sites becoming ``fhirpath_text(_latN.value, ...)``.
2. As a safety net, any lateral whose derived table still contains a nested
   subquery (SQLSubquery/SQLExists) is scope-UNSAFE and the unwrap pass
   restores the portable inline form.
"""

import re
import sys

import pytest

duckdb = pytest.importorskip("duckdb")

sys.path.insert(0, "/home/jmontavon/src/fhir4ds")

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator
from fhir4ds.cql.translator.types import (
    SQLAlias,
    SQLFunctionCall,
    SQLJoin,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
    SQLLiteral,
)

# Reproduces the CMS159 "Index Depression Assessment" shape: a per-patient
# scalar define (First of a sorted query) referenced 3+ times inside a
# population define's WHERE, whose lowering is
# fhirpath_text((SELECT sub.value FROM "<CTE>" AS sub WHERE
# sub.patient_id = _pt.patient_id LIMIT 1), '<path>') — exactly the
# expression the dedup pass used to hoist into a lateral projection.
REPRO_LIB = """library LateralSubqGuard version '1.0'
using FHIR version '4.0.1'
valueset "ED": 'urn:oid:1.2.3.4'
parameter "MP" Interval<DateTime>
context Patient
define "Assessments": [Observation: "ED"] O where O.effective during day of "MP" sort by effective
define "FirstAssessment": First("Assessments")
define IP:
  AgeInYearsAt(start of "MP") >= 12
    and year from (FirstAssessment.effective as FHIR.dateTime) >= 2020
    and month from (FirstAssessment.effective as FHIR.dateTime) <= 6
    and day from (FirstAssessment.effective as FHIR.dateTime) >= 1
"""


def _population_sql() -> str:
    return CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(REPRO_LIB),
        output_columns={"IP": "IP"},
        parameters={"MP": {"start": "2026-01-01", "end": "2026-12-31"}},
    )


class TestLateralPortability:
    def test_no_subquery_nested_in_lateral_projection(self) -> None:
        """The wasm-illegal shape must never appear in generated SQL."""
        sql = _population_sql()
        for m in re.finditer(r"CROSS JOIN LATERAL \((.*?)\) AS _lat\d+", sql, re.S):
            inner = m.group(1)
            assert "SELECT sub.value FROM" not in inner, (
                "lateral projection embeds a correlated scalar subquery — "
                "non-portable to duckdb-wasm (FHIR4-15 CMS159): "
                + inner[:200]
            )

    def test_subquery_hoisted_directly_as_lateral_table(self) -> None:
        """The perf-preserving rewrite: the subquery IS the lateral table,
        correlating directly to _pt in its WHERE clause (LEFT JOIN so a
        no-match patient keeps its row with a NULL value — the old wrap
        shape always produced exactly one row)."""
        sql = _population_sql()
        direct = re.findall(
            r"LEFT JOIN LATERAL \(SELECT .*? AS value FROM "
            r'"FirstAssessment" AS sub WHERE sub\.patient_id = _pt\.patient_id',
            sql,
        )
        assert direct, (
            "expected at least one direct subquery-as-lateral hoist of the "
            "FirstAssessment scalar define; SQL:\n" + sql
        )
        # Use sites must extract from the hoisted lateral value, not re-run
        # the subquery inline.
        assert "fhirpath_text(_lat" in sql

    def test_hoisted_subquery_evaluates_once_per_patient(self) -> None:
        """Perf contract (Joel acceptance criterion): after the rewrite the
        correlated subquery must appear exactly ONCE in the emitted SQL (as
        the lateral derived table) — referenced everywhere via _latN.value,
        never re-inlined at use sites."""
        sql = _population_sql()
        occurrences = len(
            re.findall(
                r'FROM "FirstAssessment" AS sub WHERE sub\.patient_id',
                sql,
            )
        )
        assert occurrences == 1, (
            f"hoisted subquery should occur exactly once in the population "
            f"SQL (found {occurrences}); SQL:\n{sql}"
        )

    def test_rewritten_sql_executes_on_duckdb(self) -> None:
        """The rewritten SQL binds and executes on desktop DuckDB against
        stub tables."""
        from fhir4ds.cql.duckdb.extension import register_cql

        sql = _population_sql()
        con = duckdb.connect()
        con.execute(
            "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
            "patient_ref VARCHAR, resource JSON)"
        )
        register_cql(con)
        con.execute(sql)  # must not raise
        assert con.fetchall() == []


class TestLateralGuardAST:
    """Unit-test the guard on a synthetic SQL AST."""

    def _fragment_with_lateral(self, table):
        select = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["_pt", "patient_id"])],
            from_clause=SQLAlias(expr=SQLLiteral(value="_patients"), alias="_pt"),
            joins=[
                SQLJoin(
                    join_type="CROSS JOIN LATERAL",
                    table=table,
                    alias="_lat0",
                )
            ],
        )
        from fhir4ds.cql.translator.types import SQLFragment, CTEDefinition

        return SQLFragment(
            main_query=select,
            ctes=[
                CTEDefinition(
                    name="IP",
                    query=SQLSelect(
                        columns=[SQLLiteral(value="1")], from_clause=None
                    ),
                )
            ],
        )

    def test_subquery_bearing_lateral_is_scope_unsafe(self) -> None:
        """A lateral whose derived table nests a subquery is reported
        unsafe by _lateral_join_scope_safe (so the unwrap pass restores
        the inline form)."""
        frag = self._fragment_with_lateral(
            SQLSelect(
                columns=[
                    SQLAlias(
                        expr=SQLFunctionCall(
                            name="fhirpath_text",
                            args=[
                                SQLSubquery(
                                    query=SQLSelect(
                                        columns=[
                                            SQLQualifiedIdentifier(
                                                parts=["sub", "value"]
                                            )
                                        ],
                                        from_clause=SQLAlias(
                                            expr=SQLLiteral(value='"Some CTE"'),
                                            alias="sub",
                                        ),
                                        where=SQLFunctionCall(
                                            name="=",
                                            args=[SQLLiteral(value="1")],
                                        ),
                                    )
                                ),
                                SQLLiteral(value="effective"),
                            ],
                        ),
                        alias="value",
                    )
                ]
            )
        )
        join = frag.main_query.joins[0]
        assert not frag._lateral_join_scope_safe(
            join, {"_pt"}
        ), "subquery-bearing lateral must be scope-UNSAFE (wasm portability)"

    def test_subquery_free_lateral_still_scope_safe(self) -> None:
        """The guard must NOT flag subquery-free laterals (the CMS2 dedup
        win depends on them staying hoisted)."""
        frag = self._fragment_with_lateral(
            SQLSelect(
                columns=[
                    SQLAlias(
                        expr=SQLFunctionCall(
                            name="fhirpath_text",
                            args=[
                                SQLQualifiedIdentifier(parts=["_pt", "x"]),
                                SQLLiteral(value="effective"),
                            ],
                        ),
                        alias="value",
                    )
                ]
            )
        )
        join = frag.main_query.joins[0]
        assert frag._lateral_join_scope_safe(join, {"_pt"})

    def test_direct_hoist_lateral_is_scope_safe(self) -> None:
        """The rewritten direct-hoist shape (subquery's select as the
        lateral table, correlation in WHERE) is portable and safe."""
        frag = self._fragment_with_lateral(
            SQLSelect(
                columns=[
                    SQLAlias(
                        expr=SQLQualifiedIdentifier(parts=["sub", "value"]),
                        alias="value",
                    )
                ],
                from_clause=SQLAlias(expr=SQLLiteral(value='"Some CTE"'), alias="sub"),
                where=SQLFunctionCall(name="=", args=[SQLLiteral(value="1")]),
            )
        )
        join = frag.main_query.joins[0]
        assert frag._lateral_join_scope_safe(join, {"_pt"})
