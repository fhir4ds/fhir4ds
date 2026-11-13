"""Derived-table alias column rewriting must traverse the whole AST.

Regression origin (2026-11-11, review REV-007): after the optimizer renames a
derived table's computed columns, ``fix_derived_alias_column_refs`` rewrites
``alias.<optimized_col>`` back to the fhirpath extraction it came from. Its
``SQLSelect`` handler covered columns/from/where/having/order_by/group_by and
then returned, so anything else on the select kept the optimized name:

* ``SQLSelect.joins`` (the ``ON`` condition) — a ``JOIN ... ON d.obs_value = 1``
  would reference a column the derived table no longer exposes
* ``SQLSelect.distinct_on``
* ``SQLCase.when_clauses`` — ``List[Tuple[expr, expr]]``; the generic list walk
  only recursed into items that were themselves ``SQLExpression``, so a tuple
  was skipped wholesale

These are structural assertions on the rewritten AST rather than generated SQL,
so they fail on the traversal gap itself rather than on a downstream symptom.
"""

from __future__ import annotations

from types import SimpleNamespace

from ...translator.derived_alias_refs import fix_derived_alias_column_refs
from ...translator.types import (
    SQLAlias,
    SQLBinaryOp,
    SQLCase,
    SQLIdentifier,
    SQLJoin,
    SQLQualifiedIdentifier,
    SQLRaw,
    SQLSelect,
    SQLUnion,
    SQLLiteral,
)

OPTIMIZED_COL = "obs_value"


class _Registry:
    """Minimal stand-in for the column registry the pass reads."""

    _columns = {"Observation CTE": {OPTIMIZED_COL: SimpleNamespace(fhirpath="value")}}


def _derived_from() -> SQLAlias:
    """A real derived table: an inline UNION aliased ``d``."""
    return SQLAlias(
        expr=SQLUnion(
            operands=[
                SQLRaw("SELECT 1 AS patient_id, resource, value AS obs_value FROM resources"),
                SQLRaw("SELECT 1 AS patient_id, resource, value AS obs_value FROM resources"),
            ]
        ),
        alias="d",
    )


def _derived_select(**overrides) -> SQLSelect:
    """A select over a derived table aliased ``d`` referencing d.<optimized>."""
    select = SQLSelect(
        columns=[SQLQualifiedIdentifier(parts=["d", OPTIMIZED_COL])],
        from_clause=_derived_from(),
    )
    for name, value in overrides.items():
        setattr(select, name, value)
    return select


def _reference_is_rewritten(node) -> bool:
    """True when the ``d.<optimized_col>`` reference became an extraction.

    Checks the QUALIFIED reference: the derived table's own projection still
    names the column (``value AS obs_value``), which is expected and must stay.
    """
    sql = node.to_sql()
    return f"d.{OPTIMIZED_COL}" not in sql and "fhirpath_text" in sql


class TestJoinsAreTraversed:
    def test_join_on_condition_reference_is_rewritten(self):
        join = SQLJoin(
            join_type="LEFT",
            table=SQLIdentifier(name="Other", quoted=True),
            alias="o",
            on_condition=SQLBinaryOp(
                operator="=",
                left=SQLQualifiedIdentifier(parts=["d", OPTIMIZED_COL]),
                right=SQLLiteral(1),
            ),
        )
        ast = _derived_select(joins=[join])
        fix_derived_alias_column_refs(ast, _Registry())
        assert _reference_is_rewritten(ast), (
            "join ON condition still references the optimized column: " + ast.to_sql()
        )


class TestDistinctOnIsTraversed:
    def test_distinct_on_reference_is_rewritten(self):
        ast = _derived_select(distinct_on=[SQLQualifiedIdentifier(parts=["d", OPTIMIZED_COL])])
        fix_derived_alias_column_refs(ast, _Registry())
        assert _reference_is_rewritten(ast), (
            "DISTINCT ON still references the optimized column: " + ast.to_sql()
        )


class TestCaseWhenClausesAreTraversed:
    def test_when_clause_tuple_contents_are_rewritten(self):
        case = SQLCase(
            when_clauses=[
                (
                    SQLBinaryOp(
                        operator="=",
                        left=SQLQualifiedIdentifier(parts=["d", OPTIMIZED_COL]),
                        right=SQLLiteral(1),
                    ),
                    SQLLiteral("one"),
                )
            ],
            else_clause=SQLLiteral("other"),
        )
        ast = _derived_select(columns=[case])
        fix_derived_alias_column_refs(ast, _Registry())
        assert _reference_is_rewritten(ast), (
            "CASE WHEN condition still references the optimized column: " + ast.to_sql()
        )


class TestAlreadyRewrittenReferencesAreUntouched:
    def test_non_optimized_column_is_left_alone(self):
        ast = SQLSelect(
            columns=[SQLQualifiedIdentifier(parts=["d", "resource"])],
            from_clause=_derived_from(),
        )
        fix_derived_alias_column_refs(ast, _Registry())
        assert "d.resource" in ast.to_sql()
