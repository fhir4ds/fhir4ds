"""Tests for the errors module."""

import pytest

from ..errors import (
    CQLError,
    LexerError,
    ParseError,
    TranslationError,
    CodeGenerationError,
    SemanticError,
    UnsupportedFeatureError,
    unsupported_feature,
    type_mismatch,
)


class TestParseErrorFormatting:
    """Tests for ParseError formatting with expected/found tokens."""

    def test_parse_error_basic(self):
        """Test basic ParseError without expected/found."""
        error = ParseError(message="Unexpected token")
        assert str(error) == "Unexpected token"

    def test_parse_error_with_position(self):
        """Test ParseError with position."""
        error = ParseError(message="Unexpected token", position=(10, 5))
        assert "Line 10, Column 5" in str(error)
        assert "Unexpected token" in str(error)

    def test_parse_error_formatting(self):
        """Test Error shows expected/found tokens."""
        error = ParseError(
            message="Syntax error",
            expected="IDENTIFIER",
            found="NUMBER",
            position=(1, 10),
        )
        error_str = str(error)
        assert "Line 1, Column 10" in error_str
        assert "Syntax error" in error_str
        assert "Expected: IDENTIFIER" in error_str
        assert "Found: NUMBER" in error_str

    def test_parse_error_with_suggestion(self):
        """Test ParseError with suggestion."""
        error = ParseError(
            message="Invalid syntax",
            suggestion="Check your syntax",
        )
        error_str = str(error)
        assert "Invalid syntax" in error_str
        assert "Suggestion: Check your syntax" in error_str


class TestTranslationError:
    """Tests for TranslationError with workaround/suggestion."""

    def test_translation_error_basic(self):
        """Test basic TranslationError."""
        error = TranslationError(message="Cannot translate construct")
        assert str(error) == "Cannot translate construct"

    def test_translation_error_with_suggestion(self):
        """Test Error includes workaround/suggestion."""
        error = TranslationError(
            message="Unsupported CQL construct",
            suggestion="Use a simpler expression",
            position=(5, 1),
        )
        error_str = str(error)
        assert "Line 5, Column 1" in error_str
        assert "Unsupported CQL construct" in error_str
        assert "Suggestion: Use a simpler expression" in error_str


class TestUnsupportedFeatureError:
    """Tests for UnsupportedFeatureError."""

    def test_unsupported_feature_error_basic(self):
        """Test basic UnsupportedFeatureError."""
        error = UnsupportedFeatureError(
            message="Feature not implemented",
            feature_name="choices",
        )
        error_str = str(error)
        assert "Unsupported feature: choices" in error_str

    def test_unsupported_feature_error_shows_feature_and_workaround(self):
        """Test Shows feature name and workaround."""
        error = UnsupportedFeatureError(
            message="Not supported",
            feature_name="context expressions",
            workaround="Use simple expressions instead",
            position=(3, 15),
        )
        error_str = str(error)
        assert "Line 3, Column 15" in error_str
        assert "Unsupported feature: context expressions" in error_str
        assert "Workaround: Use simple expressions instead" in error_str

    def test_unsupported_feature_error_no_workaround(self):
        """Test UnsupportedFeatureError without workaround."""
        error = UnsupportedFeatureError(
            message="Not yet implemented",
            feature_name="complex functions",
        )
        error_str = str(error)
        assert "Unsupported feature: complex functions" in error_str
        assert "Workaround" not in error_str


class TestTypeMismatchError:
    """Tests for SemanticError type mismatch functionality."""

    def test_type_mismatch_error_basic(self):
        """Test basic type mismatch error."""
        error = type_mismatch("myVar", "Integer", "String")
        error_str = str(error)
        assert "Type mismatch for 'myVar'" in error_str
        assert "Expected type: Integer" in error_str
        assert "Actual type: String" in error_str
        assert "Symbol: myVar" in error_str

    def test_type_mismatch_error_shows_expected_vs_actual(self):
        """Test Shows expected vs actual types."""
        error = type_mismatch(
            symbol="patient.age",
            expected="Number",
            actual="String",
            position=(10, 20),
        )
        error_str = str(error)
        assert "Line 10, Column 20" in error_str
        assert "Type mismatch for 'patient.age'" in error_str
        assert "Expected type: Number" in error_str
        assert "Actual type: String" in error_str
        assert "Symbol: patient.age" in error_str
        assert "Suggestion: Ensure 'patient.age' is of type 'Number'" in error_str

    def test_semantic_error_direct(self):
        """Test creating SemanticError directly."""
        error = SemanticError(
            message="Incompatible types",
            symbol="x",
            expected_type="Boolean",
            actual_type="Integer",
        )
        error_str = str(error)
        assert "Incompatible types" in error_str
        assert "Expected type: Boolean" in error_str
        assert "Actual type: Integer" in error_str


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_unsupported_feature_factory(self):
        """Test unsupported_feature factory function."""
        error = unsupported_feature(
            feature="aggregate functions",
            position=(1, 1),
            workaround="Use union instead",
        )
        assert isinstance(error, UnsupportedFeatureError)
        assert error.feature_name == "aggregate functions"
        assert error.position == (1, 1)
        assert error.workaround == "Use union instead"
        assert "aggregate functions" in str(error)
        assert "Workaround: Use union instead" in str(error)

    def test_unsupported_feature_factory_minimal(self):
        """Test unsupported_feature factory with minimal args."""
        error = unsupported_feature(feature="some feature")
        assert isinstance(error, UnsupportedFeatureError)
        assert error.feature_name == "some feature"
        assert error.position is None
        assert error.workaround is None

    def test_type_mismatch_factory(self):
        """Test type_mismatch factory function."""
        error = type_mismatch(
            symbol="count",
            expected="List",
            actual="Integer",
            position=(5, 10),
        )
        assert isinstance(error, SemanticError)
        assert error.symbol == "count"
        assert error.expected_type == "List"
        assert error.actual_type == "Integer"
        assert error.position == (5, 10)
        assert "Type mismatch for 'count'" in str(error)

    def test_type_mismatch_factory_minimal(self):
        """Test type_mismatch factory with minimal args."""
        error = type_mismatch(symbol="val", expected="String", actual="Number")
        assert isinstance(error, SemanticError)
        assert error.symbol == "val"
        assert error.expected_type == "String"
        assert error.actual_type == "Number"
        assert error.position is None


class TestErrorHierarchy:
    """Tests for error class hierarchy."""

    def test_all_errors_inherit_from_cql_error(self):
        """Test that all errors inherit from CQLError."""
        assert issubclass(LexerError, CQLError)
        assert issubclass(ParseError, CQLError)
        assert issubclass(TranslationError, CQLError)
        assert issubclass(CodeGenerationError, CQLError)
        assert issubclass(SemanticError, CQLError)
        assert issubclass(UnsupportedFeatureError, CQLError)

    def test_errors_are_catchable_as_cql_error(self):
        """Test that specific errors can be caught as CQLError."""
        errors = [
            LexerError(message="lexer error"),
            ParseError(message="parse error"),
            TranslationError(message="translation error"),
            CodeGenerationError(message="codegen error"),
            SemanticError(message="semantic error"),
            UnsupportedFeatureError(message="unsupported"),
        ]

        for error in errors:
            assert isinstance(error, CQLError)

    def test_errors_can_be_raised_and_caught(self):
        """Test that errors can be raised and caught properly."""
        with pytest.raises(CQLError) as exc_info:
            raise SemanticError(message="test error")
        assert "test error" in str(exc_info.value)


class TestExports:
    """Tests for __all__ exports."""

    def test_all_exports_available(self):
        """Test that all __all__ items are importable."""
        from ..import errors

        for name in errors.__all__:
            assert hasattr(errors, name), f"Missing export: {name}"
