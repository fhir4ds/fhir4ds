"""
Unit tests for logical function translation.

Tests the translation of CQL logical functions to FHIRPath UDFs.
Phase 8: Translator-UDF Gap Closure.
"""

import pytest

from ....parser.ast_nodes import (
    FunctionRef,
    Identifier,
    Literal,
    BinaryExpression,
)
from ....translator import CQLTranslator


class TestCoalesceTranslation:
    """Tests for Coalesce function translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_coalesce_translation(self, translator: CQLTranslator):
        """Test Coalesce function translation."""
        result = translator.translate_expression(
            FunctionRef(
                name="Coalesce",
                arguments=[
                    Identifier(name="value1"),
                    Identifier(name="value2"),
                    Literal(value="default"),
                ],
            )
        )
        # Coalesce should translate to FHIRPath coalesce or equivalent
        assert "coalesce" in result.lower()

    def test_coalesce_with_two_args(self, translator: CQLTranslator):
        """Test Coalesce with two arguments."""
        result = translator.translate_expression(
            FunctionRef(
                name="Coalesce",
                arguments=[
                    Identifier(name="nullable"),
                    Literal(value=0),
                ],
            )
        )
        assert "coalesce" in result.lower()

    def test_coalesce_with_single_arg(self, translator: CQLTranslator):
        """Test Coalesce with single argument."""
        result = translator.translate_expression(
            FunctionRef(
                name="Coalesce",
                arguments=[Identifier(name="value")],
            )
        )
        # Single arg coalesce is just the value
        assert "value" in result


class TestImpliesTranslation:
    """Tests for 'implies' logical operator translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_implies_translation(self, translator: CQLTranslator):
        """Test 'implies' operator translation."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="implies",
                left=Identifier(name="condition"),
                right=Identifier(name="consequence"),
            )
        )
        # implies should be translated as: not A or B
        # or passed through to FHIRPath
        assert "implies" in result or ("not" in result.lower() and "or" in result.lower())

    def test_implies_with_literals(self, translator: CQLTranslator):
        """Test 'implies' with boolean literals."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="implies",
                left=Literal(value=True),
                right=Literal(value=False),
            )
        )
        # Should contain the operands
        assert "true" in result.lower()
        assert "false" in result.lower()

    def test_implies_with_complex_operands(self, translator: CQLTranslator):
        """Test 'implies' with complex operands."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="implies",
                left=BinaryExpression(
                    operator=">",
                    left=Identifier(name="age"),
                    right=Literal(value=18),
                ),
                right=BinaryExpression(
                    operator="=",
                    left=Identifier(name="status"),
                    right=Literal(value="adult"),
                ),
            )
        )
        # Should contain both sub-expressions
        assert "age" in result
        assert "status" in result


class TestLogicalOperatorPrecedence:
    """Tests for logical operator handling."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_and_operator_translation(self, translator: CQLTranslator):
        """Test 'and' operator translation."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="and",
                left=Literal(value=True),
                right=Literal(value=False),
            )
        )
        assert "and" in result.lower()

    def test_or_operator_translation(self, translator: CQLTranslator):
        """Test 'or' operator translation."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="or",
                left=Literal(value=True),
                right=Literal(value=False),
            )
        )
        assert "or" in result.lower()

    def test_xor_operator_translation(self, translator: CQLTranslator):
        """Test 'xor' operator translation."""
        result = translator.translate_expression(
            BinaryExpression(
                operator="xor",
                left=Literal(value=True),
                right=Literal(value=False),
            )
        )
        assert "xor" in result.lower()
