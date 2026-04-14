"""
Unit tests for quantity arithmetic and comparison translation.

Tests the translation of CQL quantity operations to FHIRPath UDFs.
Phase 8: Translator-UDF Gap Closure.
"""

import json

import pytest

from ....parser.ast_nodes import (
    BinaryExpression,
    Quantity,
    Literal,
)
from ....translator import CQLTranslator


class TestQuantityArithmeticTranslation:
    """Tests for quantity arithmetic translation to UDF calls."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_quantity_addition_translation(self, translator: CQLTranslator):
        """Test quantity addition translates to quantityAdd UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="+",
                left=Quantity(value=5, unit="mg"),
                right=Quantity(value=3, unit="mg"),
            )
        )
        assert "quantityAdd" in result

    def test_quantity_subtraction_translation(self, translator: CQLTranslator):
        """Test quantity subtraction translates to quantitySubtract UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="-",
                left=Quantity(value=10, unit="mg"),
                right=Quantity(value=3, unit="mg"),
            )
        )
        assert "quantitySubtract" in result

    def test_quantity_addition_with_mixed_values(self, translator: CQLTranslator):
        """Test quantity addition with different numeric values."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="+",
                left=Quantity(value=2.5, unit="mL"),
                right=Quantity(value=1.5, unit="mL"),
            )
        )
        assert "quantityAdd" in result
        # Verify quantities are serialized as JSON
        assert "(" in result and ")" in result

    def test_quantity_subtraction_result_format(self, translator: CQLTranslator):
        """Test that quantity subtraction produces correct UDF call format."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="-",
                left=Quantity(value=100, unit="mg"),
                right=Quantity(value=25, unit="mg"),
            )
        )
        # Should be quantitySubtract(left_json, right_json)
        assert result.startswith("quantitySubtract(")
        assert result.endswith(")")


class TestQuantityComparisonTranslation:
    """Tests for quantity comparison translation to UDF calls."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_quantity_less_than_translation(self, translator: CQLTranslator):
        """Test quantity less than translates to quantityCompare UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="<",
                left=Quantity(value=5, unit="mg"),
                right=Quantity(value=10, unit="mg"),
            )
        )
        assert "quantityCompare" in result
        assert "'<'" in result

    def test_quantity_greater_than_translation(self, translator: CQLTranslator):
        """Test quantity greater than translates to quantityCompare UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator=">",
                left=Quantity(value=10, unit="mg"),
                right=Quantity(value=5, unit="mg"),
            )
        )
        assert "quantityCompare" in result
        assert "'>'" in result

    def test_quantity_equality_translation(self, translator: CQLTranslator):
        """Test quantity equality translates to quantityCompare UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="=",
                left=Quantity(value=5, unit="mg"),
                right=Quantity(value=5, unit="mg"),
            )
        )
        assert "quantityCompare" in result
        # Equality uses '==' in UDF
        assert "'=='" in result

    def test_quantity_less_or_equal_translation(self, translator: CQLTranslator):
        """Test quantity less or equal translates to quantityCompare UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="<=",
                left=Quantity(value=5, unit="mg"),
                right=Quantity(value=10, unit="mg"),
            )
        )
        assert "quantityCompare" in result
        assert "'<='" in result

    def test_quantity_greater_or_equal_translation(self, translator: CQLTranslator):
        """Test quantity greater or equal translates to quantityCompare UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator=">=",
                left=Quantity(value=10, unit="mg"),
                right=Quantity(value=5, unit="mg"),
            )
        )
        assert "quantityCompare" in result
        assert "'>='" in result

    def test_quantity_not_equal_translation(self, translator: CQLTranslator):
        """Test quantity not equal translates to quantityCompare UDF."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="!=",
                left=Quantity(value=5, unit="mg"),
                right=Quantity(value=10, unit="mg"),
            )
        )
        assert "quantityCompare" in result
        assert "'!='" in result


class TestQuantityJsonSerialization:
    """Tests for quantity JSON serialization in UDF calls."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_quantity_json_format_in_addition(self, translator: CQLTranslator):
        """Test that quantities are serialized as JSON with correct structure."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="+",
                left=Quantity(value=5, unit="mg"),
                right=Quantity(value=3, unit="mg"),
            )
        )
        # Extract the JSON from the UDF call
        # Format: quantityAdd(json1, json2)
        import re
        # Find JSON objects in the result
        json_pattern = r'\{[^}]+\}'
        matches = re.findall(json_pattern, result)
        assert len(matches) >= 2  # Should have two quantity JSONs

        # Verify JSON structure
        for match in matches:
            parsed = json.loads(match)
            assert "value" in parsed
            assert "code" in parsed

    def test_quantity_json_with_ucum_unit(self, translator: CQLTranslator):
        """Test quantity serialization with UCUM unit."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="+",
                left=Quantity(value=100, unit="kg/m2"),
                right=Quantity(value=5, unit="kg/m2"),
            )
        )
        assert "quantityAdd" in result
        assert "kg/m2" in result
