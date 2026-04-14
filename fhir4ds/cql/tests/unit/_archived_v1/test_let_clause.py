"""
Unit tests for let clause translation.

Tests that let variables can be referenced in subsequent where and return clauses.
"""

import pytest

from ....parser.ast_nodes import (
    BinaryExpression,
    Identifier,
    LetClause,
    Literal,
    Property,
    Query,
    QuerySource,
    Retrieve,
    WhereClause,
    ReturnClause,
)
from ....translator import CQLTranslator


class TestLetClauseTranslation:
    """Tests for let clause translation with variable references."""

    def test_let_variable_in_where(self):
        """Test that let variable can be referenced in where clause.

        The let variable 'x' with value 5 should be substituted inline
        in the where clause.
        """
        translator = CQLTranslator()

        # Build query: from [Observation] O let x: 5 where O.value > x
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="x", expression=Literal(value=5)),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Identifier(name="x"),  # Reference to let variable
                )
            ),
        )

        result = translator.translate_expression(query)

        # The let variable x (value 5) should be substituted inline
        assert "__retrieve__:Observation" in result
        assert ".where(" in result
        assert "5" in result

    def test_multiple_let_clauses(self):
        """Test multiple let clauses work together.

        Both x and y should be substituted in the where clause.
        """
        translator = CQLTranslator()

        # Build query with multiple let clauses
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="x", expression=Literal(value=5)),
                LetClause(alias="y", expression=Literal(value=10)),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator="and",
                    left=BinaryExpression(
                        operator=">=",
                        left=Property(source=Identifier(name="O"), path="value"),
                        right=Identifier(name="x"),
                    ),
                    right=BinaryExpression(
                        operator="<=",
                        left=Property(source=Identifier(name="O"), path="value"),
                        right=Identifier(name="y"),
                    ),
                )
            ),
        )

        result = translator.translate_expression(query)

        # Both x and y should be substituted
        assert "5" in result
        assert "10" in result
        assert ".where(" in result

    def test_let_variable_in_return(self):
        """Test that let variable can be referenced in return clause.

        The multiplier should be substituted in the select clause.
        """
        translator = CQLTranslator()

        # Build query with let and return
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="multiplier", expression=Literal(value=2)),
            ],
            return_clause=ReturnClause(
                expression=BinaryExpression(
                    operator="*",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Identifier(name="multiplier"),
                )
            ),
        )

        result = translator.translate_expression(query)

        # The multiplier should be substituted in the select clause
        assert ".select(" in result
        assert "2" in result

    def test_let_with_complex_expression(self):
        """Test let clause with a more complex expression."""
        translator = CQLTranslator()

        # Build query with a complex let expression
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(
                    alias="threshold",
                    expression=BinaryExpression(
                        operator="+",
                        left=Literal(value=10),
                        right=Literal(value=5),
                    ),
                ),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">=",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Identifier(name="threshold"),
                )
            ),
        )

        result = translator.translate_expression(query)

        # The threshold expression should be substituted in the where clause
        assert ".where(" in result
        assert "(10 + 5)" in result

    def test_let_variable_isolation(self):
        """Test that let variables are properly scoped and don't leak between queries."""
        translator = CQLTranslator()

        # First query with let
        query1 = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="x", expression=Literal(value=5)),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Identifier(name="x"),
                )
            ),
        )

        result1 = translator.translate_expression(query1)
        assert "5" in result1

        # Second query without let - should not see x
        query2 = Query(
            source=QuerySource(
                alias="O2",
                expression=Retrieve(type="Observation"),
            ),
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(source=Identifier(name="O2"), path="value"),
                    right=Literal(value=10),
                )
            ),
        )

        result2 = translator.translate_expression(query2)
        # Query2 should reference 10 directly, not be affected by Query1's let variable
        assert "10" in result2
        # The let_variables dict should be empty for query2
        assert len(translator.context.let_variables) == 0

    def test_let_variable_without_reference(self):
        """Test that let clause without reference still works correctly."""
        translator = CQLTranslator()

        # Query with let that is not referenced
        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[
                LetClause(alias="unused", expression=Literal(value=99)),
            ],
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Literal(value=5),
                )
            ),
        )

        result = translator.translate_expression(query)

        # Should still work even though let variable is not used
        assert "__retrieve__:Observation" in result
        assert ".where(" in result
        assert "5" in result

    def test_empty_let_clauses(self):
        """Test query with no let clauses works correctly."""
        translator = CQLTranslator()

        query = Query(
            source=QuerySource(
                alias="O",
                expression=Retrieve(type="Observation"),
            ),
            let_clauses=[],
            where=WhereClause(
                expression=BinaryExpression(
                    operator=">",
                    left=Property(source=Identifier(name="O"), path="value"),
                    right=Literal(value=5),
                )
            ),
        )

        result = translator.translate_expression(query)

        assert "__retrieve__:Observation" in result
        assert ".where(" in result
        assert "5" in result
