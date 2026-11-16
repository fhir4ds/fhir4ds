"""AMUX-126: promotion-lookup correlated scalar subqueries → LEFT JOINs.

Gate: FHIR4DS_CQL_PROMOTION_JOINS=1 enables the
``SQLFragment.rewrite_promotion_lookups_as_joins`` pass (structural planner
immunity against duckdb/duckdb#28842). These tests pin:

1. End-to-end: a promoted function's lookups become ONE deduplicated
   ``LEFT JOIN "_fn_..."`` with ``_fvjN.value`` references, and no
   ``(SELECT value FROM "_fn_...`` survives at the rewritten sites.
2. Gate OFF keeps the legacy correlated-subquery form untouched.
3. Scope rules on hand-built ASTs:
   - a lookup whose source alias is not bound at any reachable scope stays
     a subquery (matcher refuses, no join is invented);
   - a child select that SHADOWS the outer source alias is rewritten in its
     own scope (join lands in the child select, never the outer one).
"""

import os
import re
import unittest

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator
from ...translator.types import (
    CTEDefinition,
    SQLAlias,
    SQLBinaryOp,
    SQLFragment,
    SQLIdentifier,
    SQLQualifiedIdentifier,
    SQLSelect,
    SQLSubquery,
)


_CQL = """
library PromoJoinTest version '1.0.0'
using QICore

context Patient

define function encStart(E Encounter):
  E.period.start

define "Three Calls":
  ( [Encounter] E return Tuple { a: "encStart"(E), b: "encStart"(E), c: "encStart"(E) } )

define "IP":
  exists("Three Calls")
"""


def _translate_population_sql() -> str:
    lib = parse_cql(_CQL)
    translator = CQLToSQLTranslator()
    translator.translate_library(lib)
    return translator.translate_library_to_population_sql(
        library=lib,
        output_columns={"IP": "IP"},
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
    )


class TestPromotionJoinRewrite(unittest.TestCase):
    def test_gate_on_rewrites_bare_patient_id_consumer(self):
        """The tuple-return consumer lowers to SELECT DISTINCT patient_id,
        json_object(...). The join WRAPS the CTE in a projection-renaming
        subquery (exposing only `value` + renamed keys), so the bare
        patient_id projection stays unambiguous and the rewrite fires."""
        os.environ["FHIR4DS_CQL_PROMOTION_JOINS"] = "1"
        try:
            sql = _translate_population_sql()
        finally:
            os.environ.pop("FHIR4DS_CQL_PROMOTION_JOINS", None)

        self.assertIn('LEFT JOIN (SELECT _fvjs0.patient_id AS _pj_pid', sql)
        self.assertIn("_fvj0.value", sql)
        self.assertNotIn("_fvj1", sql)
        self.assertNotIn('(SELECT value FROM "_fn_encStart_', sql)

    def test_gate_on_rewrites_lookup_in_qualified_projection(self):
        """A consumer whose projection qualifies every column (the CMS2
        WHERE/define shapes) must still rewrite to LEFT JOINs."""
        from fhir4ds.cql.translator.types import (
            CTEDefinition,
            SQLAlias,
            SQLBinaryOp,
            SQLFragment,
            SQLIdentifier,
            SQLQualifiedIdentifier,
            SQLSelect,
            SQLSubquery,
        )

        lookup = SQLSubquery(
            query=SQLSelect(
                columns=[SQLIdentifier(name="value")],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="_fn_g", quoted=True), alias="_fv"
                ),
                where=SQLBinaryOp(
                    operator="AND",
                    left=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_fv", "patient_id"]),
                        right=SQLQualifiedIdentifier(parts=["E", "patient_id"]),
                    ),
                    right=SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["_fv", "_row_key"]),
                        right=SQLQualifiedIdentifier(parts=["E", "resource"]),
                    ),
                ),
            )
        )
        main = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["E", "patient_id"]), lookup],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="inner_tbl", quoted=True), alias="E"
            ),
        )
        frag = SQLFragment(
            main_query=main,
            ctes=[
                CTEDefinition(
                    name='"_fn_g"',
                    query=SQLSelect(columns=[SQLIdentifier(name="value")]),
                )
            ],
        )
        os.environ["FHIR4DS_CQL_PROMOTION_JOINS"] = "1"
        try:
            frag.rewrite_promotion_lookups_as_joins()
        finally:
            os.environ.pop("FHIR4DS_CQL_PROMOTION_JOINS", None)

        sql = frag.to_sql()
        self.assertIn('LEFT JOIN (SELECT _fvjs0.patient_id AS _pj_pid', sql)
        self.assertIn('"_fn_g" AS _fvjs0', sql)
        self.assertIn("_fvj0.value", sql)
        self.assertNotIn("_fvj1", sql)
        self.assertNotIn('(SELECT value FROM "_fn_g"', sql)

    def test_gate_off_keeps_correlated_subqueries(self):
        os.environ.pop("FHIR4DS_CQL_PROMOTION_JOINS", None)
        sql = _translate_population_sql()
        self.assertIn('(SELECT value FROM "_fn_encStart_', sql)
        self.assertNotIn('LEFT JOIN "_fn_encStart_', sql)


def _lookup_subquery(cte: str, src: str):
    """Build the promotion-lookup shape the matcher expects."""
    return SQLSubquery(
        query=SQLSelect(
            columns=[SQLIdentifier(name="value")],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name=cte, quoted=True), alias="_fv"
            ),
            where=SQLBinaryOp(
                operator="AND",
                left=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_fv", "patient_id"]),
                    right=SQLQualifiedIdentifier(parts=[src, "patient_id"]),
                ),
                right=SQLBinaryOp(
                    operator="=",
                    left=SQLQualifiedIdentifier(parts=["_fv", "_row_key"]),
                    right=SQLQualifiedIdentifier(parts=[src, "resource"]),
                ),
            ),
        )
    )


def _dummy_fn_cte(name: str) -> CTEDefinition:
    return CTEDefinition(
        name=name,
        query=SQLSelect(
            columns=[SQLIdentifier(name="patient_id"), SQLIdentifier(name="value")],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="src_tbl", quoted=True), alias="s"
            ),
        ),
    )


class TestPromotionJoinRewriteScopes(unittest.TestCase):
    def _run(self, fragment: SQLFragment) -> SQLFragment:
        fragment.rewrite_promotion_lookups_as_joins()
        return fragment

    def test_unreachable_source_alias_stays_subquery(self):
        # "Z" is not bound anywhere: the matcher must refuse and the lookup
        # must survive verbatim rather than invent a join.
        frag = SQLFragment(
            main_query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["E", "patient_id"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="src_tbl", quoted=True), alias="E"
                ),
                where=_lookup_subquery("_fn_f", "Z"),
            ),
            ctes=[_dummy_fn_cte("_fn_f")],
        )
        self._run(frag)
        sql = frag.main_query.to_sql()
        self.assertIn('(SELECT value FROM "_fn_f"', sql)
        self.assertNotIn('LEFT JOIN "_fn_f"', sql)

    def test_shadowing_child_select_rewrites_in_own_scope(self):
        # Inner select REBINDS "E": a lookup inside it correlates to the
        # INNER E (SQL shadowing), so its join must land in the inner select
        # — never in the outer one.
        inner = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["E", "patient_id"])],
            from_clause=SQLAlias(
                expr=SQLIdentifier(name="inner_tbl", quoted=True), alias="E"
            ),
            where=_lookup_subquery("_fn_g", "E"),
        )
        outer_where = SQLSubquery(query=inner)
        frag = SQLFragment(
            main_query=SQLSelect(
                columns=[SQLQualifiedIdentifier(parts=["E", "patient_id"])],
                from_clause=SQLAlias(
                    expr=SQLIdentifier(name="src_tbl", quoted=True), alias="E"
                ),
                where=outer_where,
            ),
            ctes=[_dummy_fn_cte("_fn_g")],
        )
        self._run(frag)

        inner_sql = inner.to_sql()
        outer_sql = frag.main_query.to_sql()
        # inner scope got the join and the reference
        self.assertIn('_fvj0.value', inner_sql)
        self.assertIn("_fvj0.value", inner_sql)
        self.assertNotIn('(SELECT value FROM "_fn_g"', inner_sql)
        # the outer select was NOT given a join for the shadowed lookup
        self.assertNotIn('LEFT JOIN "_fn_g"', outer_sql.split("WHERE")[0])


if __name__ == "__main__":
    unittest.main()
