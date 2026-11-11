"""Set-operation grouping: rendered SQL must preserve the AST's semantics.

SQL `UNION`, `INTERSECT` and `EXCEPT` share ONE precedence level and are
left-associative, so the rendered text is only correct if every nested set
operation that is not in first position is parenthesized.

Regression origin (2026-11-11, review REV-003): `_render_set_operands` ran the
`except` union-flattening helper over **all** operands, including the minuend.
Set difference distributes over union only for the SUBTRACTED side
(``X \\ (Y ∪ Z) = (X \\ Y) \\ Z``); for the minuend it does not hold
(``(A ∪ B) \\ C ≠ (A \\ B) \\ C``). So ``(A union B) except C`` rendered as
``A EXCEPT B EXCEPT C``, silently subtracting B from A.

These tests execute the rendered SQL against DuckDB rather than matching text,
so they fail on the semantic error itself.
"""

from __future__ import annotations

import duckdb
import pytest

from ...translator.types import SQLExcept, SQLIntersect, SQLRaw, SQLSubquery, SQLUnion


def _rows(*names: str) -> SQLRaw:
    """A one-row select tagged by name, shaped like a retrieve CTE projection."""
    return SQLRaw(f"SELECT 'p1' AS patient_id, '{names[0]}' AS resource")


def _resources(sql: str) -> set[str]:
    con = duckdb.connect(":memory:")
    try:
        return {row[1] for row in con.execute(sql).fetchall()}
    finally:
        con.close()


A, B, C = _rows("A"), _rows("B"), _rows("C")


class TestExceptWithUnionMinuend:
    def test_union_minuend_is_not_flattened_into_except(self):
        """(A union B) except C must keep the union, not subtract B from A."""
        sql = SQLExcept(operands=[SQLUnion(operands=[A, B]), C]).to_sql()
        # (A ∪ B) \ C = {A, B}. The broken rendering gave {A} because
        # A EXCEPT B EXCEPT C subtracts B from A.
        assert _resources(sql) == {"A", "B"}, f"rendered: {sql}"

    def test_union_minuend_does_not_collapse_to_the_plain_except_chain(self):
        """The minuend form must differ from the genuinely-chained form."""
        minuend = SQLExcept(operands=[SQLUnion(operands=[A, B]), C]).to_sql()
        chained = SQLExcept(operands=[A, B, C]).to_sql()
        assert minuend != chained, (
            "(A union B) except C and A except B except C are different "
            f"expressions but rendered identically:\n  {minuend}"
        )
        assert _resources(chained) == {"A"}


class TestExceptSubtractedUnionStillFlattens:
    """The CMS1028 fix must survive: X except (Y union Z) still flattens."""

    def test_subtracted_union_flattens_and_removes_all_members(self):
        sql = SQLExcept(operands=[A, SQLUnion(operands=[B, C])]).to_sql()
        assert _resources(sql) == {"A"}, f"rendered: {sql}"

    def test_flattened_form_has_no_parentheses(self):
        sql = SQLExcept(operands=[A, SQLUnion(operands=[B, C])]).to_sql()
        assert "(" not in sql, (
            "parenthesizing the subtracted union defeats DuckDB's set-operation "
            f"planning; expected the flattened form, got: {sql}"
        )


class TestNestedSetOperationsInNonFirstPosition:
    def test_intersect_operand_of_union_is_parenthesized(self):
        sql = SQLUnion(operands=[A, SQLIntersect(operands=[B, C])]).to_sql()
        assert _resources(sql) == {"A"}, (
            "A UNION (B INTERSECT C) must yield A only; without parentheses "
            f"INTERSECT binds first and the text means (A UNION B) INTERSECT C. Rendered: {sql}"
        )

    def test_subquery_wrapped_set_operation_is_parenthesized(self):
        """A set operation hidden inside SQLSubquery must still be grouped."""
        wrapped = SQLSubquery(query=SQLUnion(operands=[B, C]))
        sql = SQLExcept(operands=[A, wrapped]).to_sql()
        assert _resources(sql) == {"A"}, f"rendered: {sql}"
