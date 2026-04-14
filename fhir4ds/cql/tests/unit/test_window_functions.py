"""
Unit tests for SQL window functions.

Tests for:
- SQLWindowFunction creation and SQL generation
- ROW_NUMBER() with PARTITION BY
- ORDER BY with multiple columns
- _translate_most_recent() helper
- First/Last/MostRecent patterns
"""

import pytest

from ...translator.types import (
    SQLWindowFunction,
    SQLIdentifier,
    SQLLiteral,
    SQLFunctionCall,
    SQLBinaryOp,
    SQLSelect,
    SQLSubquery,
    SQLAlias,
    SQLRaw,
    PRECEDENCE,
)


class TestSQLWindowFunction:
    """Tests for SQLWindowFunction dataclass."""

    def test_simple_row_number(self):
        """Test basic ROW_NUMBER() with no arguments."""
        window = SQLWindowFunction(function="ROW_NUMBER")
        sql = window.to_sql()
        assert sql == "ROW_NUMBER() OVER ()"

    def test_row_number_with_partition_by(self):
        """Test ROW_NUMBER() with PARTITION BY."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
        )
        sql = window.to_sql()
        assert sql == "ROW_NUMBER() OVER (PARTITION BY patient_ref)"

    def test_row_number_with_partition_and_order(self):
        """Test ROW_NUMBER() with PARTITION BY and ORDER BY."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[
                (SQLIdentifier(name="effective_date"), "DESC"),
            ],
        )
        sql = window.to_sql()
        assert sql == "ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY effective_date DESC)"

    def test_row_number_with_multiple_order_columns(self):
        """Test ROW_NUMBER() with multiple ORDER BY columns."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[
                (SQLIdentifier(name="effective_date"), "DESC"),
                (SQLIdentifier(name="resource"), "ASC"),
            ],
        )
        sql = window.to_sql()
        assert "ORDER BY effective_date DESC, resource ASC" in sql

    def test_sum_with_partition(self):
        """Test SUM() with PARTITION BY."""
        window = SQLWindowFunction(
            function="SUM",
            function_args=[SQLIdentifier(name="amount")],
            partition_by=[SQLIdentifier(name="customer_id")],
        )
        sql = window.to_sql()
        assert sql == "SUM(amount) OVER (PARTITION BY customer_id)"

    def test_count_with_partition_and_order(self):
        """Test COUNT(*) with PARTITION BY and ORDER BY."""
        window = SQLWindowFunction(
            function="COUNT",
            function_args=[SQLRaw(raw_sql="*")],  # Use SQLRaw for unquoted *
            partition_by=[SQLIdentifier(name="department")],
            order_by=[(SQLIdentifier(name="hire_date"), "ASC")],
        )
        sql = window.to_sql()
        assert sql == "COUNT(*) OVER (PARTITION BY department ORDER BY hire_date ASC)"

    def test_window_function_with_frame_clause(self):
        """Test window function with frame clause."""
        window = SQLWindowFunction(
            function="SUM",
            function_args=[SQLIdentifier(name="amount")],
            partition_by=[SQLIdentifier(name="customer_id")],
            order_by=[(SQLIdentifier(name="transaction_date"), "ASC")],
            frame_clause="ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW",
        )
        sql = window.to_sql()
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql

    def test_multiple_partition_columns(self):
        """Test window function with multiple PARTITION BY columns."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="category"),
            ],
            order_by=[(SQLIdentifier(name="date"), "DESC")],
        )
        sql = window.to_sql()
        assert "PARTITION BY patient_ref, category" in sql

    def test_function_call_as_order_expression(self):
        """Test using a function call as an ORDER BY expression."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[
                (SQLFunctionCall(
                    name="fhirpath_date",
                    args=[
                        SQLIdentifier(name="resource"),
                        SQLLiteral(value="effectiveDateTime"),
                    ],
                ), "DESC"),
            ],
        )
        sql = window.to_sql()
        assert "fhirpath_date(resource, 'effectiveDateTime') DESC" in sql

    def test_window_function_precedence(self):
        """Test that window function has FUNCTION precedence."""
        window = SQLWindowFunction(function="ROW_NUMBER")
        assert window.precedence == PRECEDENCE["FUNCTION"]


class TestWindowFunctionInSelect:
    """Tests for window functions within SELECT statements."""

    def test_window_function_as_column(self):
        """Test window function used as a SELECT column with alias."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[(SQLIdentifier(name="effective_date"), "DESC")],
        )
        alias = SQLAlias(expr=window, alias="rn")

        select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
                alias,
            ],
            from_clause=SQLRaw(raw_sql="observations"),
        )
        sql = select.to_sql()
        assert "ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY effective_date DESC) AS rn" in sql


class TestMostRecentPattern:
    """Tests for the 'most recent per patient' pattern."""

    def test_inner_query_with_window_function(self):
        """Test inner query that adds ROW_NUMBER partitioned by patient."""
        # Build the inner query with ROW_NUMBER
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[
                (SQLIdentifier(name="effective_date"), "DESC"),
                (SQLFunctionCall(
                    name="json_extract_string",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="$.id")],
                ), "ASC"),
            ],
        )

        inner_select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
                SQLAlias(expr=window, alias="rn"),
            ],
            from_clause=SQLRaw(raw_sql="observations"),
        )

        sql = inner_select.to_sql()
        assert "SELECT patient_ref, resource" in sql
        assert "ROW_NUMBER() OVER (PARTITION BY patient_ref" in sql
        assert "ORDER BY effective_date DESC" in sql
        assert "json_extract_string(resource, '$.id') ASC" in sql
        assert "AS rn" in sql

    def test_outer_query_filters_rn_equals_1(self):
        """Test outer query that filters rn = 1."""
        # First, the inner query
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[(SQLIdentifier(name="effective_date"), "DESC")],
        )

        inner_select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
                SQLAlias(expr=window, alias="rn"),
            ],
            from_clause=SQLRaw(raw_sql="observations"),
        )

        # Now the outer query
        outer_select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
            ],
            from_clause=SQLRaw(raw_sql=f"({inner_select.to_sql()}) ranked"),
            where=SQLBinaryOp(
                operator="=",
                left=SQLIdentifier(name="rn"),
                right=SQLLiteral(value=1),
            ),
        )

        sql = outer_select.to_sql()
        assert "SELECT patient_ref, resource" in sql
        assert "FROM (SELECT" in sql
        assert ") ranked" in sql
        assert "WHERE rn = 1" in sql

    def test_complete_most_recent_pattern(self):
        """Test the complete 'most recent per patient' SQL pattern."""
        # Inner query
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
            order_by=[
                (SQLIdentifier(name="effective_date"), "DESC"),
                (SQLFunctionCall(
                    name="json_extract_string",
                    args=[SQLIdentifier(name="resource"), SQLLiteral(value="$.id")],
                ), "ASC"),
            ],
        )

        inner_select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
                SQLAlias(expr=window, alias="rn"),
            ],
            from_clause=SQLRaw(raw_sql="observations"),
        )

        # Outer query
        outer_select = SQLSelect(
            columns=[
                SQLIdentifier(name="patient_ref"),
                SQLIdentifier(name="resource"),
            ],
            from_clause=SQLRaw(raw_sql=f"({inner_select.to_sql()}) ranked"),
            where=SQLBinaryOp(
                operator="=",
                left=SQLIdentifier(name="rn"),
                right=SQLLiteral(value=1),
            ),
        )

        # Wrap in subquery
        subquery = SQLSubquery(query=outer_select)
        sql = subquery.to_sql()

        # Verify the complete pattern
        assert sql.startswith("(")
        assert sql.endswith(")")
        assert "SELECT patient_ref, resource" in sql
        assert "ROW_NUMBER() OVER (PARTITION BY patient_ref" in sql
        assert "WHERE rn = 1" in sql


class TestWindowFunctionPrecedence:
    """Tests for window function precedence handling."""

    def test_window_function_has_function_precedence(self):
        """Test that window functions have FUNCTION precedence."""
        window = SQLWindowFunction(function="ROW_NUMBER")
        assert window.precedence == PRECEDENCE["FUNCTION"]

    def test_window_function_no_parentheses_at_same_precedence(self):
        """Test that window functions don't get extra parentheses at same or lower precedence."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
        )
        # At same or lower precedence, no parentheses needed
        sql = window.to_sql(parent_precedence=PRECEDENCE["FUNCTION"])
        assert sql == "ROW_NUMBER() OVER (PARTITION BY patient_ref)"

        # At lower precedence (like comparison operators), no parentheses
        sql = window.to_sql(parent_precedence=PRECEDENCE["="])
        assert sql == "ROW_NUMBER() OVER (PARTITION BY patient_ref)"

    def test_window_function_with_parentheses_at_higher_precedence(self):
        """Test that window functions get parentheses when inside higher precedence context."""
        window = SQLWindowFunction(
            function="ROW_NUMBER",
            partition_by=[SQLIdentifier(name="patient_ref")],
        )
        # At higher precedence (like PRIMARY), parentheses are added
        sql = window.to_sql(parent_precedence=PRECEDENCE["PRIMARY"])
        assert sql == "(ROW_NUMBER() OVER (PARTITION BY patient_ref))"


class TestWindowFunctionWithFrameClause:
    """Tests for window functions with frame clauses."""

    def test_rows_unbounded_preceding(self):
        """Test window function with ROWS frame clause."""
        window = SQLWindowFunction(
            function="SUM",
            function_args=[SQLIdentifier(name="amount")],
            partition_by=[SQLIdentifier(name="customer_id")],
            order_by=[(SQLIdentifier(name="date"), "ASC")],
            frame_clause="ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW",
        )
        sql = window.to_sql()
        assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
