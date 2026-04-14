"""
Tests for interval overlap decomposition to simple date comparisons.

This module tests that interval overlaps are decomposed to simple SQL comparisons
instead of using UDF chains like intervalOverlaps(intervalFromBounds(...), ...).
"""

import pytest

from ...parser.ast_nodes import (
    BinaryExpression,
    Identifier,
    Interval,
    Literal,
)
from ...translator.context import SQLTranslationContext
from ...translator.expressions import ExpressionTranslator
from ...translator.types import SQLBinaryOp, SQLFunctionCall, SQLInterval, SQLNull, SQLLiteral


class TestIntervalOverlapDecomposition:
    """Tests for decomposing interval overlaps to simple comparisons."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_interval_literal_overlaps_decomposes(self, translator: ExpressionTranslator):
        """Test that Interval[A, B) overlaps Interval[C, D) decomposes to simple comparisons."""
        # Interval[1, 10) overlaps Interval[5, 15)
        left_interval = Interval(
            low=Literal(value=1),
            high=Literal(value=10),
            low_closed=True,
            high_closed=False,
        )
        right_interval = Interval(
            low=Literal(value=5),
            high=Literal(value=15),
            low_closed=True,
            high_closed=False,
        )
        expr = BinaryExpression(
            operator="overlaps",
            left=left_interval,
            right=right_interval,
        )

        result = translator.translate(expr)

        # Should decompose to: left_start < right_end AND left_end >= right_start
        # For [1, 10) overlaps [5, 15): 1 < 15 AND 10 >= 5
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"

        sql = result.to_sql()
        # Should have simple comparisons, not UDF calls
        assert "intervalOverlaps" not in sql
        # Should have the start < end comparison
        assert "<" in sql
        # Should have the end >= start comparison
        assert ">=" in sql

    def test_interval_overlaps_with_closed_bounds(self, translator: ExpressionTranslator):
        """Test that closed intervals use <= and >= operators."""
        # Interval[1, 10] overlaps Interval[5, 15]
        left_interval = Interval(
            low=Literal(value=1),
            high=Literal(value=10),
            low_closed=True,
            high_closed=True,
        )
        right_interval = Interval(
            low=Literal(value=5),
            high=Literal(value=15),
            low_closed=True,
            high_closed=True,
        )
        expr = BinaryExpression(
            operator="overlaps",
            left=left_interval,
            right=right_interval,
        )

        result = translator.translate(expr)

        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"

        sql = result.to_sql()
        # Should NOT have UDF calls
        assert "intervalOverlaps" not in sql

    def test_interval_overlaps_half_open(self, translator: ExpressionTranslator):
        """Test half-open intervals [a, b) overlaps [c, d)."""
        # Interval[1, 10) overlaps Interval[5, 15)
        left_interval = Interval(
            low=Literal(value=1),
            high=Literal(value=10),
            low_closed=True,
            high_closed=False,
        )
        right_interval = Interval(
            low=Literal(value=5),
            high=Literal(value=15),
            low_closed=True,
            high_closed=False,
        )
        expr = BinaryExpression(
            operator="overlaps",
            left=left_interval,
            right=right_interval,
        )

        result = translator.translate(expr)

        assert isinstance(result, SQLBinaryOp)
        sql = result.to_sql()
        # For [a, b) overlaps [c, d): a < d AND b >= c
        assert "intervalOverlaps" not in sql

    def test_interval_overlaps_no_overlap_non_overlapping(self, translator: ExpressionTranslator):
        """Test that non-overlapping intervals produce correct comparisons."""
        # Interval[1, 5) overlaps Interval[10, 15) - no overlap
        left_interval = Interval(
            low=Literal(value=1),
            high=Literal(value=5),
            low_closed=True,
            high_closed=False,
        )
        right_interval = Interval(
            low=Literal(value=10),
            high=Literal(value=15),
            low_closed=True,
            high_closed=False,
        )
        expr = BinaryExpression(
            operator="overlaps",
            left=left_interval,
            right=right_interval,
        )

        result = translator.translate(expr)

        # Should still produce the decomposition (the SQL evaluation will return FALSE)
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "AND"
        sql = result.to_sql()
        assert "intervalOverlaps" not in sql


class TestIntervalBoundsExtraction:
    """Tests for extracting bounds from various interval expression types."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_sql_interval_bounds_extraction(self, translator: ExpressionTranslator):
        """Test extracting bounds from SQLInterval objects."""
        interval = Interval(
            low=Literal(value=1),
            high=Literal(value=10),
            low_closed=True,
            high_closed=False,
        )
        result = translator.translate(interval)

        # Should produce SQLInterval
        assert isinstance(result, SQLInterval)
        assert result.low_closed is True
        assert result.high_closed is False

    def test_interval_with_null_high(self, translator: ExpressionTranslator):
        """Test interval with NULL high bound (open-ended)."""
        # Interval[1, null) - open-ended interval
        interval = Interval(
            low=Literal(value=1),
            high=None,  # NULL high
            low_closed=True,
            high_closed=False,
        )
        result = translator.translate(interval)

        assert isinstance(result, SQLInterval)
        # High should be SQLNull when not provided
        assert result.high is None or isinstance(result.high, SQLNull)


class TestIntervalOverlapEdgeCases:
    """Tests for edge cases in interval overlap decomposition."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_point_interval_overlaps(self, translator: ExpressionTranslator):
        """Test point interval [5, 5] overlaps another interval."""
        # Interval[5, 5] overlaps Interval[1, 10)
        left_interval = Interval(
            low=Literal(value=5),
            high=Literal(value=5),
            low_closed=True,
            high_closed=True,
        )
        right_interval = Interval(
            low=Literal(value=1),
            high=Literal(value=10),
            low_closed=True,
            high_closed=False,
        )
        expr = BinaryExpression(
            operator="overlaps",
            left=left_interval,
            right=right_interval,
        )

        result = translator.translate(expr)

        assert isinstance(result, SQLBinaryOp)
        sql = result.to_sql()
        assert "intervalOverlaps" not in sql


class TestIntervalOverlapWithNullEnd:
    """Tests for interval overlaps with NULL end (open-ended intervals like active conditions)."""

    @pytest.fixture
    def translator(self) -> ExpressionTranslator:
        """Create an ExpressionTranslator instance for testing."""
        context = SQLTranslationContext()
        return ExpressionTranslator(context)

    def test_interval_from_bounds_with_null_end_adds_coalesce(self, translator: ExpressionTranslator):
        """Test that intervalFromBounds with NULL end adds COALESCE for the comparison."""
        # Simulate prevalenceInterval pattern: intervalFromBounds(onset, NULL, TRUE, FALSE)
        # overlaps Interval['2024-01-01', '2024-12-31')

        # Create left interval with NULL end (simulating active condition)
        left_interval = SQLInterval(
            low=SQLFunctionCall(name="fhirpath_date", args=[SQLNull(), SQLLiteral(value="onsetDateTime")]),
            high=SQLNull(),
            low_closed=True,
            high_closed=False,
        )

        # Create right interval (Measurement Period)
        right_interval = SQLInterval(
            low=SQLLiteral(value="2024-01-01"),
            high=SQLLiteral(value="2024-12-31"),
            low_closed=True,
            high_closed=False,
        )

        # Call decomposition directly
        result = translator._try_decompose_interval_overlaps(left_interval, right_interval, None)

        assert result is not None
        sql = result.to_sql()

        # Should NOT have UDF calls
        assert "intervalOverlaps" not in sql
        # Should have COALESCE for the NULL end
        assert "COALESCE" in sql
        # Should use 9999-12-31 as the default for NULL
        assert "9999-12-31" in sql

    def test_interval_with_null_end_overlaps_literal_interval(self, translator: ExpressionTranslator):
        """Test that interval with NULL end correctly overlaps a literal interval."""
        # Interval[1, NULL) overlaps Interval[5, 15)
        # Should produce: 1 < 15 AND COALESCE(NULL, '9999-12-31') >= 5
        left_interval = Interval(
            low=Literal(value=1),
            high=None,  # NULL = open-ended
            low_closed=True,
            high_closed=False,
        )
        right_interval = Interval(
            low=Literal(value=5),
            high=Literal(value=15),
            low_closed=True,
            high_closed=False,
        )
        expr = BinaryExpression(
            operator="overlaps",
            left=left_interval,
            right=right_interval,
        )

        result = translator.translate(expr)

        assert isinstance(result, SQLBinaryOp)
        sql = result.to_sql()

        # Should NOT have UDF calls
        assert "intervalOverlaps" not in sql
        # Should have COALESCE for NULL handling
        assert "COALESCE" in sql
        assert "9999-12-31" in sql
