"""Unit tests for Long type support."""
import pytest
import sys

from ....parser.lexer import Lexer, TokenType
from ....parser.parser import parse_expression
from ....parser.ast_nodes import Literal
from ....translator import CQLTranslator


class TestLongLexer:
    def test_long_token_created(self):
        """Test that LONG token is created for L suffix."""
        lexer = Lexer("123L")
        tokens = lexer.tokenize()
        assert any(t.type == TokenType.LONG for t in tokens)

    def test_long_token_value(self):
        """Test that LONG token has correct value."""
        lexer = Lexer("123456789L")
        tokens = lexer.tokenize()
        long_token = next(t for t in tokens if t.type == TokenType.LONG)
        assert long_token.value == "123456789"

    def test_lowercase_l_suffix(self):
        """Test that lowercase l suffix works."""
        lexer = Lexer("999l")
        tokens = lexer.tokenize()
        assert any(t.type == TokenType.LONG for t in tokens)


class TestLongParsing:
    def test_long_literal_parse(self):
        """Test parsing: 123456789L"""
        expr = parse_expression("123456789L")
        assert isinstance(expr, Literal)
        assert expr.value == 123456789
        assert expr.type == "Long"

    def test_negative_long(self):
        """Test parsing: -987654321L"""
        from ....parser.ast_nodes import UnaryExpression
        expr = parse_expression("-987654321L")
        # Negative numbers are parsed as UnaryExpression wrapping a Literal
        assert isinstance(expr, UnaryExpression)
        assert expr.operator == "-"
        assert isinstance(expr.operand, Literal)
        assert expr.operand.value == 987654321
        assert expr.operand.type == "Long"

    def test_max_long_value(self):
        """Test parsing max int64 value."""
        expr = parse_expression("9223372036854775807L")
        assert isinstance(expr, Literal)
        assert expr.type == "Long"


class TestLongTranslation:
    def test_long_translation(self):
        """Test long translates correctly."""
        expr = parse_expression("123456789L")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "123456789" in result

    def test_long_in_expression(self):
        """Test long in arithmetic expression."""
        expr = parse_expression("100L + 50L")
        translator = CQLTranslator()
        result = translator.translate_expression(expr)
        assert "100" in result and "50" in result
