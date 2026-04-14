"""
Unit tests for type-aware operator dispatch.

Tests that the `+` operator dispatches to `||` for strings,
`+` for numbers, and defaults to `+` for unknown types.
"""
import pytest
from ...translator.operators import OperatorTranslator
from ...translator.types import (
    SQLBinaryOp,
    SQLCast,
    SQLFunctionCall,
    SQLLiteral,
)


@pytest.fixture
def op_translator():
    """Create an OperatorTranslator with a minimal context."""
    from ...translator.translator import SQLTranslationContext
    context = SQLTranslationContext()
    return OperatorTranslator(context)


class TestInferOperandType:
    """Tests for _infer_operand_type helper."""

    def test_string_literal(self, op_translator):
        assert op_translator._infer_operand_type(SQLLiteral(value="'hello'")) == "String"

    def test_integer_literal(self, op_translator):
        assert op_translator._infer_operand_type(SQLLiteral(value="42")) == "Integer"

    def test_decimal_literal(self, op_translator):
        assert op_translator._infer_operand_type(SQLLiteral(value="3.14")) == "Decimal"

    def test_cast_to_integer(self, op_translator):
        expr = SQLCast(expression=SQLLiteral(value="'42'"), target_type="INTEGER")
        assert op_translator._infer_operand_type(expr) == "Integer"

    def test_fhirpath_text_function(self, op_translator):
        expr = SQLFunctionCall(name="FHIRPATH_TEXT", args=[])
        assert op_translator._infer_operand_type(expr) == "String"

    def test_unknown_expression(self, op_translator):
        from ...translator.types import SQLIdentifier
        assert op_translator._infer_operand_type(SQLIdentifier(name="col")) is None


class TestPlusOperatorDispatch:
    """Tests for type-aware `+` operator dispatch."""

    def test_string_plus_string_uses_concat(self, op_translator):
        """'hello' + 'world' → 'hello' || 'world'"""
        left = SQLLiteral(value="'hello'")
        right = SQLLiteral(value="'world'")
        result = op_translator.translate_binary_op("+", left, right, op_translator.context)
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "||"

    def test_integer_plus_integer_uses_add(self, op_translator):
        """5 + 3 → 5 + 3"""
        left = SQLLiteral(value="5")
        right = SQLLiteral(value="3")
        result = op_translator.translate_binary_op("+", left, right, op_translator.context)
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "+"

    def test_unknown_types_default_to_add(self, op_translator):
        """Unknown types → + (safe default)"""
        from ...translator.types import SQLIdentifier
        left = SQLIdentifier(name="a")
        right = SQLIdentifier(name="b")
        result = op_translator.translate_binary_op("+", left, right, op_translator.context)
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "+"

    def test_string_plus_unknown_uses_concat(self, op_translator):
        """'prefix' + unknown → concatenation (since one side is string)."""
        from ...translator.types import SQLIdentifier
        left = SQLLiteral(value="'prefix'")
        right = SQLIdentifier(name="col")
        result = op_translator.translate_binary_op("+", left, right, op_translator.context)
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "||"

    def test_fhirpath_text_plus_string_uses_concat(self, op_translator):
        """FHIRPATH_TEXT(...) + 'suffix' → concatenation."""
        left = SQLFunctionCall(name="FHIRPATH_TEXT", args=[])
        right = SQLLiteral(value="'suffix'")
        result = op_translator.translate_binary_op("+", left, right, op_translator.context)
        assert isinstance(result, SQLBinaryOp)
        assert result.operator == "||"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
