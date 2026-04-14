"""
Unit tests for DurationBetween translation.

Tests the translation of CQL 'X between A and B' expressions
to FHIRPath XBetween(A, B) function calls.

Duration returns whole calendar periods between two dates.
"""

import pytest

from ....parser.ast_nodes import (
    DateTimeLiteral,
    DurationBetween,
    Identifier,
    Literal,
)
from ....translator.expressions import ExpressionTranslator
from ....translator import CQLTranslator


class TestDurationBetweenTranslation:
    """Tests for DurationBetween AST node translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    @pytest.fixture
    def expression_translator(self, translator: CQLTranslator) -> ExpressionTranslator:
        """Get the expression translator from the main translator."""
        return translator._expression_translator

    def test_years_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'years between A and B'."""
        expr = DurationBetween(
            precision="years",
            operand_left=DateTimeLiteral("2020-01-01"),
            operand_right=DateTimeLiteral("2024-01-01"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "yearsBetween(@2020-01-01, @2024-01-01)"

    def test_months_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'months between A and B'."""
        expr = DurationBetween(
            precision="months",
            operand_left=DateTimeLiteral("2024-01-15"),
            operand_right=DateTimeLiteral("2024-06-15"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "monthsBetween(@2024-01-15, @2024-06-15)"

    def test_weeks_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'weeks between A and B'."""
        expr = DurationBetween(
            precision="weeks",
            operand_left=DateTimeLiteral("2024-01-01"),
            operand_right=DateTimeLiteral("2024-01-22"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "weeksBetween(@2024-01-01, @2024-01-22)"

    def test_days_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'days between A and B'."""
        expr = DurationBetween(
            precision="days",
            operand_left=DateTimeLiteral("2024-01-01"),
            operand_right=DateTimeLiteral("2024-01-10"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "daysBetween(@2024-01-01, @2024-01-10)"

    def test_hours_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'hours between A and B'."""
        expr = DurationBetween(
            precision="hours",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00"),
            operand_right=DateTimeLiteral("2024-01-01T12:00:00"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "hoursBetween(@2024-01-01T00:00:00, @2024-01-01T12:00:00)"

    def test_minutes_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'minutes between A and B'."""
        expr = DurationBetween(
            precision="minutes",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00"),
            operand_right=DateTimeLiteral("2024-01-01T00:30:00"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "minutesBetween(@2024-01-01T00:00:00, @2024-01-01T00:30:00)"

    def test_seconds_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'seconds between A and B'."""
        expr = DurationBetween(
            precision="seconds",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00"),
            operand_right=DateTimeLiteral("2024-01-01T00:00:45"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "secondsBetween(@2024-01-01T00:00:00, @2024-01-01T00:00:45)"

    def test_milliseconds_between(self, expression_translator: ExpressionTranslator):
        """Test translation of 'milliseconds between A and B'."""
        expr = DurationBetween(
            precision="milliseconds",
            operand_left=DateTimeLiteral("2024-01-01T00:00:00.000"),
            operand_right=DateTimeLiteral("2024-01-01T00:00:00.500"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "millisecondsBetween(@2024-01-01T00:00:00.000, @2024-01-01T00:00:00.500)"

    def test_duration_with_identifiers(self, expression_translator: ExpressionTranslator):
        """Test translation with identifier operands."""
        expr = DurationBetween(
            precision="years",
            operand_left=Identifier("StartDate"),
            operand_right=Identifier("EndDate"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "yearsBetween(StartDate, EndDate)"

    def test_duration_unknown_unit_defaults_to_days(
        self, expression_translator: ExpressionTranslator
    ):
        """Test that unknown units default to daysBetween."""
        expr = DurationBetween(
            precision="unknown",
            operand_left=DateTimeLiteral("2024-01-01"),
            operand_right=DateTimeLiteral("2024-01-10"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "daysBetween(@2024-01-01, @2024-01-10)"

    def test_duration_case_insensitive(self, expression_translator: ExpressionTranslator):
        """Test that precision is case-insensitive."""
        expr = DurationBetween(
            precision="YEARS",
            operand_left=DateTimeLiteral("2020-01-01"),
            operand_right=DateTimeLiteral("2024-01-01"),
        )
        result = expression_translator.translate_duration_between(expr)
        assert result == "yearsBetween(@2020-01-01, @2024-01-01)"

    def test_duration_dispatched_from_translator(self, translator: CQLTranslator):
        """Test that DurationBetween is properly dispatched from translate_expression."""
        expr = DurationBetween(
            precision="years",
            operand_left=DateTimeLiteral("2020-01-01"),
            operand_right=DateTimeLiteral("2024-01-01"),
        )
        result = translator.translate_expression(expr)
        assert result == "yearsBetween(@2020-01-01, @2024-01-01)"
