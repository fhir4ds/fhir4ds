"""
Unit tests for SQLUnion type and union translation.

Tests that CQL unions are correctly translated to SQL UNION ALL instead of
nested jsonConcat calls.
"""
import pytest
from ...translator.types import (
    SQLUnion,
    SQLSubquery,
    SQLSelect,
    SQLIdentifier,
    SQLLiteral,
    SQLFunctionCall,
    SQLBinaryOp,
)


class TestSQLUnionType:
    """Tests for the SQLUnion dataclass."""

    def test_union_distinct_default(self):
        """SQLUnion should use UNION (distinct) by default (CQL semantics)."""
        select1 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("conditions"),
        )
        select2 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("observations"),
        )
        union_expr = SQLUnion(operands=[SQLSubquery(select1), SQLSubquery(select2)])

        sql = union_expr.to_sql()
        assert "UNION" in sql
        assert "UNION ALL" not in sql  # Default is distinct, not ALL

    def test_union_all_explicit(self):
        """SQLUnion can use UNION ALL when distinct=False."""
        select1 = SQLSelect(
            columns=[SQLIdentifier("id")],
            from_clause=SQLIdentifier("table1"),
        )
        select2 = SQLSelect(
            columns=[SQLIdentifier("id")],
            from_clause=SQLIdentifier("table2"),
        )
        union_expr = SQLUnion(
            operands=[SQLSubquery(select1), SQLSubquery(select2)],
            distinct=False
        )

        sql = union_expr.to_sql()
        assert "UNION ALL" in sql

    def test_union_wraps_selects_in_parens(self):
        """SELECT statements should be wrapped in parentheses for UNION."""
        select = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("conditions"),
        )
        subquery = SQLSubquery(select)
        union_expr = SQLUnion(operands=[subquery, subquery])

        sql = union_expr.to_sql()
        # Each SELECT should be in parens
        assert "(SELECT" in sql

    def test_flatten_three_way_union(self):
        """Three-way unions should be flattened to single SQLUnion."""
        select1 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("conditions"),
        )
        select2 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("observations"),
        )
        select3 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("procedures"),
        )

        # Simulate flattening: (A union B) union C with distinct=False (UNION ALL)
        union_ab = SQLUnion(operands=[SQLSubquery(select1), SQLSubquery(select2)], distinct=False)
        union_abc = SQLUnion(operands=[union_ab, SQLSubquery(select3)], distinct=False)

        # The SQL should still be valid
        sql = union_abc.to_sql()
        assert "UNION ALL" in sql


class TestSQLUnionPrecedence:
    """Tests for UNION precedence handling."""

    def test_union_low_precedence(self):
        """UNION should have low precedence (0)."""
        from ...translator.types import PRECEDENCE
        assert PRECEDENCE.get("UNION", -1) == 0
        assert PRECEDENCE.get("UNION_ALL", -1) == 0


class TestExtractSubqueriesFromUnion:
    """Tests for _extract_subqueries_from_union helper."""

    def test_extract_simple_subquery(self):
        """Should extract a single SQLSubquery."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        select = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("conditions"),
        )
        subquery = SQLSubquery(select)

        result = translator._extract_subqueries_from_union(subquery)
        assert len(result) == 1
        assert result[0] is subquery

    def test_extract_from_jsonconcat(self):
        """Should extract subqueries from nested jsonConcat."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        select1 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("conditions"),
        )
        select2 = SQLSelect(
            columns=[SQLIdentifier("resource")],
            from_clause=SQLIdentifier("observations"),
        )

        # Simulate jsonConcat(subquery1, subquery2)
        json_concat = SQLFunctionCall(
            name="jsonConcat",
            args=[SQLSubquery(select1), SQLSubquery(select2)]
        )

        result = translator._extract_subqueries_from_union(json_concat)
        assert len(result) == 2

    def test_extract_from_nested_jsonconcat(self):
        """Should extract subqueries from deeply nested jsonConcat."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        select1 = SQLSelect(columns=[SQLIdentifier("a")], from_clause=SQLIdentifier("t1"))
        select2 = SQLSelect(columns=[SQLIdentifier("b")], from_clause=SQLIdentifier("t2"))
        select3 = SQLSelect(columns=[SQLIdentifier("c")], from_clause=SQLIdentifier("t3"))

        # Simulate jsonConcat(jsonConcat(sub1, sub2), sub3)
        inner_concat = SQLFunctionCall(
            name="jsonConcat",
            args=[SQLSubquery(select1), SQLSubquery(select2)]
        )
        outer_concat = SQLFunctionCall(
            name="jsonConcat",
            args=[inner_concat, SQLSubquery(select3)]
        )

        result = translator._extract_subqueries_from_union(outer_concat)
        assert len(result) == 3

    def test_extract_from_non_union_returns_empty(self):
        """Should return empty list for non-union expressions."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        # A literal is not a union-compatible expression
        literal = SQLLiteral(value=42)
        result = translator._extract_subqueries_from_union(literal)
        assert result == []


class TestUnionDisjointness:
    """Tests for UNION ALL optimization when branches are provably disjoint."""

    def test_different_resource_types_use_union_all(self):
        """Two RetrievePlaceholders with different resource types → UNION ALL."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext
        from ...translator.placeholder import RetrievePlaceholder

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        left = SQLSubquery(query=RetrievePlaceholder(resource_type="Condition", valueset=None))
        right = SQLSubquery(query=RetrievePlaceholder(resource_type="Observation", valueset=None))

        assert translator._check_union_disjointness([left, right]) is True

    def test_same_resource_type_uses_union(self):
        """Two RetrievePlaceholders with same resource type → UNION (distinct)."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext
        from ...translator.placeholder import RetrievePlaceholder

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        left = SQLSubquery(query=RetrievePlaceholder(resource_type="Condition", valueset="vs1"))
        right = SQLSubquery(query=RetrievePlaceholder(resource_type="Condition", valueset="vs2"))

        assert translator._check_union_disjointness([left, right]) is False

    def test_unknown_types_default_to_union(self):
        """When resource types can't be determined, default to UNION (safe)."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        left = SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier("*")],
            from_clause=SQLIdentifier("some_table"),
        ))
        right = SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier("*")],
            from_clause=SQLIdentifier("other_table"),
        ))

        assert translator._check_union_disjointness([left, right]) is False

    def test_cte_names_with_different_resource_types(self):
        """CTE names like 'Condition: X' and 'Observation: Y' → disjoint."""
        from ...translator.expressions import ExpressionTranslator
        from ...translator.translator import SQLTranslationContext

        context = SQLTranslationContext()
        translator = ExpressionTranslator(context)

        left = SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier("*")],
            from_clause=SQLIdentifier(name="Condition: Essential Hypertension", quoted=True),
        ))
        right = SQLSubquery(query=SQLSelect(
            columns=[SQLIdentifier("*")],
            from_clause=SQLIdentifier(name="Observation: Blood Pressure", quoted=True),
        ))

        assert translator._check_union_disjointness([left, right]) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
