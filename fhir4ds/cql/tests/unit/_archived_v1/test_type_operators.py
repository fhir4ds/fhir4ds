"""
Unit tests for CQL type operators (is, as, convert).

Tests parsing and translation of type testing and conversion operators.
"""

import pytest

from ....parser.ast_nodes import (
    BinaryExpression,
    FunctionRef,
    Identifier,
    Literal,
)
from ....translator import CQLTranslator


class TestIsOperatorParsing:
    """Tests for 'is' type operator parsing."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_is_integer_parse(self, translator: CQLTranslator):
        """Test parsing: X is Integer"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="Integer"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Integer" in result

    def test_is_string_parse(self, translator: CQLTranslator):
        """Test parsing: X is String"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="String"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "String" in result

    def test_is_boolean_parse(self, translator: CQLTranslator):
        """Test parsing: X is Boolean"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="Boolean"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Boolean" in result

    def test_is_decimal_parse(self, translator: CQLTranslator):
        """Test parsing: X is Decimal"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="Decimal"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Decimal" in result

    def test_is_datetime_parse(self, translator: CQLTranslator):
        """Test parsing: X is DateTime"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="DateTime"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "DateTime" in result

    def test_is_date_parse(self, translator: CQLTranslator):
        """Test parsing: X is Date"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="Date"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Date" in result

    def test_is_time_parse(self, translator: CQLTranslator):
        """Test parsing: X is Time"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="Time"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Time" in result

    def test_is_quantity_parse(self, translator: CQLTranslator):
        """Test parsing: X is Quantity"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Identifier(name="Quantity"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Quantity" in result

    def test_is_null_check(self, translator: CQLTranslator):
        """Test parsing: X is null"""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="X"),
            right=Literal(value=None),
        )
        result = translator.translate_expression(expr)
        assert "X" in result

    def test_is_with_literal_left(self, translator: CQLTranslator):
        """Test parsing with literal on left side."""
        expr = BinaryExpression(
            operator="is",
            left=Literal(value=42),
            right=Identifier(name="Integer"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Integer" in result


class TestAsOperatorParsing:
    """Tests for 'as' type operator parsing."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_as_string_parse(self, translator: CQLTranslator):
        """Test parsing: X as String"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="String"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "String" in result

    def test_as_integer_parse(self, translator: CQLTranslator):
        """Test parsing: X as Integer"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="Integer"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Integer" in result

    def test_as_decimal_parse(self, translator: CQLTranslator):
        """Test parsing: X as Decimal"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="Decimal"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Decimal" in result

    def test_as_boolean_parse(self, translator: CQLTranslator):
        """Test parsing: X as Boolean"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="Boolean"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Boolean" in result

    def test_as_datetime_parse(self, translator: CQLTranslator):
        """Test parsing: X as DateTime"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="DateTime"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "DateTime" in result

    def test_as_date_parse(self, translator: CQLTranslator):
        """Test parsing: X as Date"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="Date"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Date" in result

    def test_as_time_parse(self, translator: CQLTranslator):
        """Test parsing: X as Time"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="Time"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Time" in result

    def test_as_quantity_parse(self, translator: CQLTranslator):
        """Test parsing: X as Quantity"""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="X"),
            right=Identifier(name="Quantity"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Quantity" in result

    def test_as_with_nested_expression(self, translator: CQLTranslator):
        """Test parsing with nested expression on left side."""
        inner = BinaryExpression(
            operator="+",
            left=Identifier(name="A"),
            right=Identifier(name="B"),
        )
        expr = BinaryExpression(
            operator="as",
            left=inner,
            right=Identifier(name="Decimal"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Decimal" in result


class TestConvertOperator:
    """Tests for 'convert' type operator translation."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_convert_to_decimal_via_todecimal(self, translator: CQLTranslator):
        """Test convert generates ToDecimal()."""
        result = translator.translate_expression(
            FunctionRef(name="ToDecimal", arguments=[Identifier(name="X")])
        )
        assert "toDecimal" in result

    def test_convert_to_string_via_tostring(self, translator: CQLTranslator):
        """Test convert generates ToString()."""
        result = translator.translate_expression(
            FunctionRef(name="ToString", arguments=[Identifier(name="X")])
        )
        assert "toString" in result

    def test_convert_to_integer_via_tointeger(self, translator: CQLTranslator):
        """Test convert generates ToInteger()."""
        result = translator.translate_expression(
            FunctionRef(name="ToInteger", arguments=[Identifier(name="X")])
        )
        assert "toInteger" in result

    def test_convert_to_datetime_via_todatetime(self, translator: CQLTranslator):
        """Test convert generates ToDateTime()."""
        result = translator.translate_expression(
            FunctionRef(name="ToDateTime", arguments=[Identifier(name="X")])
        )
        assert "toDateTime" in result

    def test_convert_to_boolean_via_toboolean(self, translator: CQLTranslator):
        """Test convert generates ToBoolean()."""
        result = translator.translate_expression(
            FunctionRef(name="ToBoolean", arguments=[Identifier(name="X")])
        )
        assert "toBoolean" in result

    def test_convert_to_date_via_todate(self, translator: CQLTranslator):
        """Test convert generates ToDate()."""
        result = translator.translate_expression(
            FunctionRef(name="ToDate", arguments=[Identifier(name="X")])
        )
        assert "toDate" in result

    def test_convert_to_time_via_totime(self, translator: CQLTranslator):
        """Test convert generates ToTime()."""
        result = translator.translate_expression(
            FunctionRef(name="ToTime", arguments=[Identifier(name="X")])
        )
        assert "toTime" in result

    def test_convert_to_quantity_via_toquantity(self, translator: CQLTranslator):
        """Test convert generates ToQuantity()."""
        result = translator.translate_expression(
            FunctionRef(name="ToQuantity", arguments=[Identifier(name="X")])
        )
        assert "toQuantity" in result

    def test_convert_to_concept_via_toconcept(self, translator: CQLTranslator):
        """Test convert generates ToConcept()."""
        result = translator.translate_expression(
            FunctionRef(name="ToConcept", arguments=[Identifier(name="X")])
        )
        assert "toConcept" in result

    def test_convert_with_literal(self, translator: CQLTranslator):
        """Test convert with literal value."""
        result = translator.translate_expression(
            FunctionRef(name="ToInteger", arguments=[Literal(value="42")])
        )
        assert "toInteger" in result
        assert "42" in result

    def test_convert_with_string_literal(self, translator: CQLTranslator):
        """Test convert with string literal value."""
        result = translator.translate_expression(
            FunctionRef(name="ToDecimal", arguments=[Literal(value="3.14")])
        )
        assert "toDecimal" in result
        assert "3.14" in result


class TestTypeOperatorPrecedence:
    """Tests for type operator precedence."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_is_in_parentheses(self, translator: CQLTranslator):
        """Test is operator in parentheses context."""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="value"),
            right=Identifier(name="Integer"),
        )
        result = translator.translate_expression(expr)
        assert "value" in result
        assert "Integer" in result

    def test_as_after_arithmetic(self, translator: CQLTranslator):
        """Test as operator after arithmetic expression."""
        inner = BinaryExpression(
            operator="+",
            left=Literal(value=1),
            right=Literal(value=2),
        )
        expr = BinaryExpression(
            operator="as",
            left=inner,
            right=Identifier(name="Decimal"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result


class TestTypeOperatorEdgeCases:
    """Tests for edge cases in type operators."""

    @pytest.fixture
    def translator(self) -> CQLTranslator:
        """Create a translator instance for testing."""
        return CQLTranslator()

    def test_is_with_qualified_type(self, translator: CQLTranslator):
        """Test is with qualified type name."""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="resource"),
            right=Identifier(name="FHIR.Patient"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "Patient" in result

    def test_as_with_qualified_type(self, translator: CQLTranslator):
        """Test as with qualified type name."""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="resource"),
            right=Identifier(name="FHIR.Observation"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Observation" in result

    def test_is_with_list_type(self, translator: CQLTranslator):
        """Test is with list type."""
        expr = BinaryExpression(
            operator="is",
            left=Identifier(name="values"),
            right=Identifier(name="List"),
        )
        result = translator.translate_expression(expr)
        assert "is" in result
        assert "List" in result

    def test_as_with_interval_type(self, translator: CQLTranslator):
        """Test as with interval type."""
        expr = BinaryExpression(
            operator="as",
            left=Identifier(name="range"),
            right=Identifier(name="Interval"),
        )
        result = translator.translate_expression(expr)
        assert "as" in result
        assert "Interval" in result
