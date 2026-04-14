"""
Unit tests for interval operator translation.

Tests the translation of CQL interval operators to FHIRPath UDFs.
Phase 8: Translator-UDF Gap Closure.
"""

import pytest

from ....parser.ast_nodes import (
    BinaryExpression,
    Identifier,
    Interval,
    Literal,
    UnaryExpression,
)
from ....translator import CQLTranslator


class TestIntervalBinaryOperators:
    """Tests for interval binary operator translation to UDF calls."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_interval_contains_translation(self, translator: CQLTranslator):
        """Test 'contains' operator translates to intervalContains UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="contains",
                left=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
                right=Literal(value=5),
            )
        )
        assert "intervalContains" in result

    def test_interval_properly_contains_translation(self, translator: CQLTranslator):
        """Test 'properly contains' operator translates to intervalProperlyContains UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="properly contains",
                left=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
                right=Literal(value=5),
            )
        )
        assert "intervalProperlyContains" in result

    def test_interval_includes_translation(self, translator: CQLTranslator):
        """Test 'includes' operator translates to intervalIncludes UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="includes",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalIncludes" in result

    def test_interval_properly_includes_translation(self, translator: CQLTranslator):
        """Test 'properly includes' operator translates to intervalProperlyIncludes UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="properly includes",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalProperlyIncludes" in result

    def test_interval_included_in_translation(self, translator: CQLTranslator):
        """Test 'included in' operator translates to intervalIncludedIn UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="included in",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalIncludedIn" in result

    def test_interval_properly_included_in_translation(self, translator: CQLTranslator):
        """Test 'properly included in' operator translates to intervalProperlyIncludedIn UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="properly included in",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalProperlyIncludedIn" in result

    def test_interval_before_translation(self, translator: CQLTranslator):
        """Test 'before' operator translates to intervalBefore UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="before",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalBefore" in result

    def test_interval_after_translation(self, translator: CQLTranslator):
        """Test 'after' operator translates to intervalAfter UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="after",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalAfter" in result

    def test_interval_meets_translation(self, translator: CQLTranslator):
        """Test 'meets' operator translates to intervalMeets UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="meets",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalMeets" in result

    def test_interval_meets_before_translation(self, translator: CQLTranslator):
        """Test 'meets before' operator translates to intervalMeetsBefore UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="meets before",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalMeetsBefore" in result

    def test_interval_meets_after_translation(self, translator: CQLTranslator):
        """Test 'meets after' operator translates to intervalMeetsAfter UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="meets after",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalMeetsAfter" in result

    def test_interval_overlaps_translation(self, translator: CQLTranslator):
        """Test 'overlaps' operator translates to intervalOverlaps UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="overlaps",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalOverlaps" in result

    def test_interval_overlaps_before_translation(self, translator: CQLTranslator):
        """Test 'overlaps before' operator translates to intervalOverlapsBefore UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="overlaps before",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalOverlapsBefore" in result

    def test_interval_overlaps_after_translation(self, translator: CQLTranslator):
        """Test 'overlaps after' operator translates to intervalOverlapsAfter UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="overlaps after",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalOverlapsAfter" in result

    def test_interval_starts_translation(self, translator: CQLTranslator):
        """Test 'starts' operator translates to intervalStartsSame UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="starts",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalStartsSame" in result

    def test_interval_ends_translation(self, translator: CQLTranslator):
        """Test 'ends' operator translates to intervalEndsSame UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="ends",
                left=Identifier(name="IntervalA"),
                right=Identifier(name="IntervalB"),
            )
        )
        assert "intervalEndsSame" in result


class TestIntervalUnaryOperators:
    """Tests for interval unary operator translation to UDF calls."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_start_of_translation(self, translator: CQLTranslator):
        """Test 'start of' operator translates to intervalStart UDF."""
        result = translator.translate_expression(
            UnaryExpression(
                operator="start of",
                operand=Identifier(name="MyInterval"),
            )
        )
        assert "intervalStart" in result

    def test_end_of_translation(self, translator: CQLTranslator):
        """Test 'end of' operator translates to intervalEnd UDF."""
        result = translator.translate_expression(
            UnaryExpression(
                operator="end of",
                operand=Identifier(name="MyInterval"),
            )
        )
        assert "intervalEnd" in result

    def test_width_of_translation(self, translator: CQLTranslator):
        """Test 'width of' operator translates to intervalWidth UDF."""
        result = translator.translate_expression(
            UnaryExpression(
                operator="width of",
                operand=Identifier(name="MyInterval"),
            )
        )
        assert "intervalWidth" in result

    def test_start_of_with_interval_literal(self, translator: CQLTranslator):
        """Test 'start of' with interval literal."""
        result = translator.translate_expression(
            UnaryExpression(
                operator="start of",
                operand=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )
        assert "intervalStart" in result
        assert "Interval[1, 10]" in result

    def test_end_of_with_interval_literal(self, translator: CQLTranslator):
        """Test 'end of' with interval literal."""
        result = translator.translate_expression(
            UnaryExpression(
                operator="end of",
                operand=Interval(
                    low=Literal(value=1),
                    high=Literal(value=10),
                    low_closed=True,
                    high_closed=True,
                ),
            )
        )
        assert "intervalEnd" in result
        assert "Interval[1, 10]" in result
