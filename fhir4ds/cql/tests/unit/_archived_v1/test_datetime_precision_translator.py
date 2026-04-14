"""
Unit tests for datetime precision operator translation.

Tests the translation of CQL datetime precision operators to FHIRPath UDFs.
Phase 8: Translator-UDF Gap Closure.
"""

import pytest

from ....parser.ast_nodes import (
    BinaryExpression,
    DateTimeLiteral,
    Identifier,
    Literal,
)
from ....translator import CQLTranslator


class TestDateTimePrecisionTranslation:
    """Tests for datetime precision operator translation to UDF calls."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_datetime_same_as_translation(self, translator: CQLTranslator):
        """Test 'same as' operator translates to dateTimeSameAs UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same as",
                left=Identifier(name="DateA"),
                right=Identifier(name="DateB"),
            )
        )
        assert "dateTimeSameAs" in result

    def test_datetime_same_or_before_translation(self, translator: CQLTranslator):
        """Test 'same or before' operator translates to dateTimeSameOrBefore UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same or before",
                left=Identifier(name="DateA"),
                right=Identifier(name="DateB"),
            )
        )
        assert "dateTimeSameOrBefore" in result

    def test_datetime_same_or_after_translation(self, translator: CQLTranslator):
        """Test 'same or after' operator translates to dateTimeSameOrAfter UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same or after",
                left=Identifier(name="DateA"),
                right=Identifier(name="DateB"),
            )
        )
        assert "dateTimeSameOrAfter" in result

    def test_datetime_same_as_with_literals(self, translator: CQLTranslator):
        """Test 'same as' operator with DateTime literals."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same as",
                left=DateTimeLiteral(value="2024-01-15"),
                right=DateTimeLiteral(value="2024-01-15"),
            )
        )
        assert "dateTimeSameAs" in result
        assert "@2024-01-15" in result

    def test_datetime_same_or_before_with_literals(self, translator: CQLTranslator):
        """Test 'same or before' operator with DateTime literals."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same or before",
                left=DateTimeLiteral(value="2024-01-15"),
                right=DateTimeLiteral(value="2024-01-20"),
            )
        )
        assert "dateTimeSameOrBefore" in result
        assert "@2024-01-15" in result
        assert "@2024-01-20" in result

    def test_datetime_same_or_after_with_literals(self, translator: CQLTranslator):
        """Test 'same or after' operator with DateTime literals."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same or after",
                left=DateTimeLiteral(value="2024-01-20"),
                right=DateTimeLiteral(value="2024-01-15"),
            )
        )
        assert "dateTimeSameOrAfter" in result
        assert "@2024-01-20" in result
        assert "@2024-01-15" in result

    def test_datetime_precision_with_mixed_operands(self, translator: CQLTranslator):
        """Test datetime precision operators with identifier and literal."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="same as",
                left=Identifier(name="birthDate"),
                right=DateTimeLiteral(value="1990-01-01"),
            )
        )
        assert "dateTimeSameAs" in result
        assert "birthDate" in result
        assert "@1990-01-01" in result
