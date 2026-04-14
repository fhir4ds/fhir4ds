"""
Unit tests for DifferenceBetween translation.

Tests the translation of CQL 'difference in X between A and B' expressions
to FHIRPath differenceInX(A, B) function calls.

Difference counts boundary crossings, not whole periods like DurationBetween.
"""

import pytest

from ....parser.ast_nodes import (
    DateTimeLiteral,
    DifferenceBetween,
    Identifier,
    Literal,
)
from ....translator.expressions import ExpressionTranslator
from ....translator import CQLTranslator


class TestDifferenceBetweenTranslation:
    """Tests for DifferenceBetween AST node translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    @pytest.fixture
    def expression_translator(self, translator: CQLTranslator) -> ExpressionTranslator:
        """Get the expression translator from the main translator."""
        return translator._expression_translator

    def test_difference_in_years(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in years between A and B'."""
        expr = DifferenceBetween(
            precision="years",
            operand_left=DateTimeLiteral("2023-12-31"),
            operand_right=DateTimeLiteral("2024-01-01"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInYears(@2023-12-31, @2024-01-01)"

    def test_difference_in_months(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in months between A and B'."""
        expr = DifferenceBetween(
            precision="months",
            operand_left=DateTimeLiteral("2024-01-15"),
            operand_right=DateTimeLiteral("2024-03-20"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInMonths(@2024-01-15, @2024-03-20)"

    def test_difference_in_days(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in days between A and B'."""
        expr = DifferenceBetween(
            precision="days",
            operand_left=DateTimeLiteral("2024-01-01"),
            operand_right=DateTimeLiteral("2024-01-10"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInDays(@2024-01-01, @2024-01-10)"

    def test_difference_in_hours(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in hours between A and B'."""
        expr = DifferenceBetween(
            precision="hours",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00"),
            operand_right=DateTimeLiteral("2024-01-01T12:00:00"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInHours(@2024-01-01T00:00:00, @2024-01-01T12:00:00)"

    def test_difference_in_minutes(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in minutes between A and B'."""
        expr = DifferenceBetween(
            precision="minutes",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00"),
            operand_right=DateTimeLiteral("2024-01-01T00:30:00"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInMinutes(@2024-01-01T00:00:00, @2024-01-01T00:30:00)"

    def test_difference_in_seconds(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in seconds between A and B'."""
        expr = DifferenceBetween(
            precision="seconds",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00"),
            operand_right=DateTimeLiteral("2024-01-01T00:00:45"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInSeconds(@2024-01-01T00:00:00, @2024-01-01T00:00:45)"

    def test_difference_with_identifiers(self, expression_translator: ExpressionTranslator):
        """Test translation with identifier operands."""
        expr = DifferenceBetween(
            precision="years",
            operand_left=Identifier("StartDate"),
            operand_right=Identifier("EndDate"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInYears(StartDate, EndDate)"

    def test_difference_unknown_unit_defaults_to_days(
        self, expression_translator: ExpressionTranslator
    ):
        """Test that unknown units default to differenceInDays."""
        expr = DifferenceBetween(
            precision="unknown",
            operand_left=DateTimeLiteral("2024-01-01"),
            operand_right=DateTimeLiteral("2024-01-10"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInDays(@2024-01-01, @2024-01-10)"

    def test_difference_case_insensitive(self, expression_translator: ExpressionTranslator):
        """Test that precision is case-insensitive."""
        expr = DifferenceBetween(
            precision="YEARS",
            operand_left=DateTimeLiteral("2023-12-31"),
            operand_right=DateTimeLiteral("2024-01-01"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInYears(@2023-12-31, @2024-01-01)"

    def test_difference_in_milliseconds(self, expression_translator: ExpressionTranslator):
        """Test translation of 'difference in milliseconds between A and B'."""
        expr = DifferenceBetween(
            precision="milliseconds",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00.000"),
            operand_right=DateTimeLiteral("2024-01-01T00:00:00.500"),
        )
        result = expression_translator.translate_difference_between(expr)
        assert result == "differenceInMilliseconds(@2024-01-01T00:00:00.000, @2024-01-01T00:00:00.500)"
