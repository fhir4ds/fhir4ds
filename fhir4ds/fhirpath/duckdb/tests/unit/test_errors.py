"""
Tests for FHIRPath error handling and suggestion engine.

Tests cover:
- Structured error classes
- Suggestion engine for field name typos
- Debug logging functionality
"""

from __future__ import annotations

import logging
import pytest

from ...errors import (
    FHIRPathError,
    FHIRPathSyntaxError,
    FHIRPathTypeError,
    FHIRPathNotFoundError,
    FHIRPathEvaluationError,
    FHIRPathFunctionError,
    FHIRPathResourceError,
    levenshtein_distance,
    suggest_field_name,
    format_suggestion,
)
from ...extension import set_debug_logging, is_debug_logging


class TestFHIRPathError:
    """Tests for base FHIRPathError class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = FHIRPathError("Something went wrong")
        assert error.message == "Something went wrong"
        assert str(error) == "Something went wrong"

    def test_error_with_expression(self):
        """Test error with expression context."""
        error = FHIRPathError("Invalid operation", expression="Patient.name")
        assert error.message == "Invalid operation"
        assert error.expression == "Patient.name"
        assert "Patient.name" in str(error)

    def test_error_with_position(self):
        """Test error with position information."""
        error = FHIRPathError("Syntax error", expression="Patient..name", position=8)
        assert error.position == 8
        assert "position 8" in str(error)

    def test_repr(self):
        """Test repr output."""
        error = FHIRPathError("Test error")
        assert repr(error) == "FHIRPathError('Test error')"


class TestFHIRPathSyntaxError:
    """Tests for FHIRPathSyntaxError class."""

    def test_syntax_error_with_token(self):
        """Test syntax error with unexpected token."""
        error = FHIRPathSyntaxError("Unexpected token", token="..")
        assert error.token == ".."
        assert "'..'" in str(error)

    def test_syntax_error_full_context(self):
        """Test syntax error with full context."""
        error = FHIRPathSyntaxError(
            "Unexpected token",
            expression="Patient..name",
            position=8,
            token="..",
        )
        assert error.expression == "Patient..name"
        assert error.position == 8
        assert error.token == ".."


class TestFHIRPathTypeError:
    """Tests for FHIRPathTypeError class."""

    def test_type_error_basic(self):
        """Test basic type error."""
        error = FHIRPathTypeError("Type mismatch")
        assert error.message == "Type mismatch"

    def test_type_error_with_types(self):
        """Test type error with expected/actual types."""
        error = FHIRPathTypeError(
            "Cannot add types",
            expected_type="Integer",
            actual_type="String",
        )
        assert error.expected_type == "Integer"
        assert error.actual_type == "String"
        assert "Expected Integer, got String" in str(error)


class TestFHIRPathNotFoundError:
    """Tests for FHIRPathNotFoundError class."""

    def test_not_found_error_basic(self):
        """Test basic not found error."""
        error = FHIRPathNotFoundError("Patient.unknownField")
        assert error.path == "Patient.unknownField"
        assert "Patient.unknownField" in str(error)

    def test_not_found_error_with_resource_type(self):
        """Test not found error with resource type."""
        error = FHIRPathNotFoundError("unknownField", resource_type="Patient")
        assert error.resource_type == "Patient"
        assert "Patient" in str(error)


class TestFHIRPathEvaluationError:
    """Tests for FHIRPathEvaluationError class."""

    def test_evaluation_error_basic(self):
        """Test basic evaluation error."""
        error = FHIRPathEvaluationError("Division by zero")
        assert error.message == "Division by zero"
        assert error.context == {}
        assert error.path is None
        assert error.value is None
        assert error.suggestion is None

    def test_evaluation_error_with_context(self):
        """Test evaluation error with all context."""
        error = FHIRPathEvaluationError(
            "Invalid value",
            expression="Patient.age + 1",
            context={"index": 5},
            path="Patient.age",
            value="unknown",
            suggestion="Use a numeric value",
        )
        assert error.expression == "Patient.age + 1"
        assert error.context == {"index": 5}
        assert error.path == "Patient.age"
        assert error.value == "unknown"
        assert error.suggestion == "Use a numeric value"

    def test_formatted_message(self):
        """Test formatted error message."""
        error = FHIRPathEvaluationError(
            "Test error",
            expression="expr",
            path="path",
            value="val",
            suggestion="Try this",
        )
        formatted = error._format_message()
        assert "FHIRPath evaluation error: Test error" in formatted
        assert "Expression: expr" in formatted
        assert "At path: path" in formatted
        assert "Value: 'val'" in formatted
        assert "Suggestion: Try this" in formatted

    def test_long_value_truncation(self):
        """Test that long values are truncated in error message."""
        long_value = "x" * 200
        error = FHIRPathEvaluationError("Test", value=long_value)
        formatted = error._format_message()
        # Value representation should be truncated
        assert "..." in formatted
        # Check that the value part is truncated (repr adds quotes)
        value_line = [line for line in formatted.split("\n") if "Value:" in line]
        assert len(value_line[0]) < 150  # Should be truncated


class TestFHIRPathFunctionError:
    """Tests for FHIRPathFunctionError class."""

    def test_function_error(self):
        """Test function error."""
        error = FHIRPathFunctionError("substring", "requires start index")
        assert error.function_name == "substring"
        assert "substring()" in str(error)
        assert "requires start index" in str(error)


class TestFHIRPathResourceError:
    """Tests for FHIRPathResourceError class."""

    def test_resource_error_basic(self):
        """Test basic resource error."""
        error = FHIRPathResourceError("Missing required field")
        assert "Missing required field" in str(error)

    def test_resource_error_with_type(self):
        """Test resource error with type."""
        error = FHIRPathResourceError("Invalid resource", resource_type="Patient")
        assert error.resource_type == "Patient"
        assert "Patient" in str(error)

    def test_resource_error_with_id_and_type(self):
        """Test resource error with ID and type."""
        error = FHIRPathResourceError(
            "Invalid resource",
            resource_id="123",
            resource_type="Patient",
        )
        assert error.resource_id == "123"
        assert "Patient/123" in str(error)


class TestLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""

    def test_identical_strings(self):
        """Test distance between identical strings."""
        assert levenshtein_distance("hello", "hello") == 0

    def test_empty_strings(self):
        """Test distance with empty strings."""
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("hello", "") == 5
        assert levenshtein_distance("", "hello") == 5

    def test_single_edit(self):
        """Test single edit operations."""
        # Substitution
        assert levenshtein_distance("hello", "hallo") == 1
        # Insertion
        assert levenshtein_distance("hello", "helllo") == 1
        # Deletion
        assert levenshtein_distance("hello", "helo") == 1

    def test_multiple_edits(self):
        """Test multiple edit operations."""
        assert levenshtein_distance("kitten", "sitting") == 3
        assert levenshtein_distance("saturday", "sunday") == 3

    def test_case_sensitivity(self):
        """Test that distance is case-sensitive."""
        # The function compares as-is (case matters)
        assert levenshtein_distance("Hello", "hello") == 1


class TestSuggestFieldName:
    """Tests for field name suggestion engine."""

    def test_exact_match_excluded(self):
        """Test that exact matches are excluded."""
        fields = ["name", "id", "status"]
        suggestions = suggest_field_name("name", fields)
        assert "name" not in suggestions

    def test_close_match(self):
        """Test suggestion for close match."""
        fields = ["name", "id", "status", "gender"]
        suggestions = suggest_field_name("nam", fields)
        assert "name" in suggestions

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        fields = ["name", "id", "Status"]
        # STATUS and Status are identical when lowercased, so they're excluded
        # as exact matches. Test with a close but different case variation.
        suggestions = suggest_field_name("statuS", fields)
        # "statuS" lowercased is "status" which is identical to "Status" lowercased
        # so it's excluded as an exact match
        assert "Status" not in suggestions  # Excluded because it's the same word

    def test_case_insensitive_with_typo(self):
        """Test case-insensitive matching with typo."""
        fields = ["name", "id", "Status"]
        # "statos" is 1 char different from "status" (case-insensitive)
        suggestions = suggest_field_name("statos", fields)
        assert "Status" in suggestions

    def test_no_match_too_far(self):
        """Test no suggestions for very different names."""
        fields = ["name", "id", "status"]
        suggestions = suggest_field_name("xyzzy", fields, max_distance=2)
        assert len(suggestions) == 0

    def test_max_suggestions(self):
        """Test max suggestions limit."""
        fields = ["name", "nami", "namo", "namu", "namy"]
        suggestions = suggest_field_name("nam", fields, max_suggestions=2)
        assert len(suggestions) <= 2

    def test_empty_inputs(self):
        """Test empty inputs."""
        assert suggest_field_name("", ["name"]) == []
        assert suggest_field_name("name", []) == []
        assert suggest_field_name("", []) == []

    def test_distance_threshold(self):
        """Test distance threshold parameter."""
        fields = ["patient", "patent", "patten"]
        # With threshold 2, should include more matches
        suggestions_2 = suggest_field_name("patint", fields, max_distance=2)
        # With threshold 1, fewer matches
        suggestions_1 = suggest_field_name("patint", fields, max_distance=1)
        assert len(suggestions_2) >= len(suggestions_1)

    def test_sorted_by_distance(self):
        """Test that suggestions are sorted by distance."""
        fields = ["abcd", "abc", "ab"]
        suggestions = suggest_field_name("a", fields)
        # "ab" should come before "abc" which should come before "abcd"
        assert suggestions == ["ab", "abc", "abcd"]


class TestFormatSuggestion:
    """Tests for suggestion formatting."""

    def test_single_suggestion(self):
        """Test formatting single suggestion."""
        result = format_suggestion("nam", ["name"])
        assert result == "Did you mean 'name'?"

    def test_multiple_suggestions(self):
        """Test formatting multiple suggestions."""
        result = format_suggestion("nam", ["name", "names"])
        assert "Did you mean one of:" in result
        assert "'name'" in result
        assert "'names'" in result

    def test_no_suggestions(self):
        """Test formatting with no suggestions."""
        result = format_suggestion("xyzzy", [])
        assert result is None


class TestDebugLogging:
    """Tests for debug logging functionality."""

    def test_default_debug_logging(self):
        """Test default debug logging state."""
        # Just check that the function works
        original = is_debug_logging()
        # It should be a boolean
        assert isinstance(original, bool)

    def test_set_debug_logging(self):
        """Test setting debug logging."""
        original = is_debug_logging()

        try:
            set_debug_logging(True)
            assert is_debug_logging() is True

            set_debug_logging(False)
            assert is_debug_logging() is False
        finally:
            # Restore original state
            set_debug_logging(original)

    def test_debug_logging_context(self):
        """Test debug logging in evaluation context."""
        import duckdb
        from ...import register_fhirpath

        original = is_debug_logging()

        try:
            # Create a connection and register FHIRPath
            con = duckdb.connect(":memory:")
            register_fhirpath(con)

            # Test with invalid JSON - should return empty list
            result = con.execute(
                "SELECT fhirpath('not valid json', 'id')"
            ).fetchone()
            assert result == ([],)

            # Test with valid JSON but empty result
            result = con.execute(
                "SELECT fhirpath('{\"resourceType\":\"Patient\"}', 'nonexistent')"
            ).fetchone()
            # Should be empty list (FHIRPath semantics)
            assert result == ([],)

            con.close()
        finally:
            set_debug_logging(original)


class TestErrorInheritance:
    """Tests for error class inheritance."""

    def test_all_errors_inherit_from_base(self):
        """Test that all errors inherit from FHIRPathError."""
        errors = [
            FHIRPathSyntaxError("test"),
            FHIRPathTypeError("test"),
            FHIRPathNotFoundError("test"),
            FHIRPathEvaluationError("test"),
            FHIRPathFunctionError("func", "test"),
            FHIRPathResourceError("test"),
        ]

        for error in errors:
            assert isinstance(error, FHIRPathError)
            assert isinstance(error, Exception)

    def test_catch_all_with_base_class(self):
        """Test that all errors can be caught with base class."""
        errors_to_raise = [
            FHIRPathSyntaxError("test"),
            FHIRPathTypeError("test"),
            FHIRPathNotFoundError("test"),
            FHIRPathEvaluationError("test"),
            FHIRPathFunctionError("func", "test"),
            FHIRPathResourceError("test"),
        ]

        for error in errors_to_raise:
            try:
                raise error
            except FHIRPathError:
                pass  # Successfully caught
            else:
                pytest.fail(f"{type(error).__name__} not caught by FHIRPathError")
