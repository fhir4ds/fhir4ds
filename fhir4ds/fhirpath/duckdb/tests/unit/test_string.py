"""
Unit tests for FHIRPath string functions.

Tests string manipulation functions including:
- length() and substring()
- startsWith() and endsWith()
- contains(), upper(), lower()
- replace() and regex functions
- split() and join()
- trim()
- concatenate (& operator)
"""

from __future__ import annotations

import pytest

from ...collection import FHIRPathCollection
from ...functions.string import (
    length,
    substring,
    starts_with,
    ends_with,
    contains,
    upper,
    lower,
    replace,
    matches,
    replace_matches,
    split,
    join,
    trim,
    concatenate,
    STRING_FUNCTIONS,
)


class TestLength:
    """Tests for length() function."""

    def test_length_simple(self) -> None:
        """Test length of simple string."""
        result = length(FHIRPathCollection(["hello"]))
        assert result.is_singleton
        assert result.singleton_value == 5

    def test_length_empty_string(self) -> None:
        """Test length of empty string."""
        result = length(FHIRPathCollection([""]))
        assert result.is_singleton
        assert result.singleton_value == 0

    def test_length_unicode(self) -> None:
        """Test length with unicode characters."""
        result = length(FHIRPathCollection(["hello world"]))
        assert result.singleton_value == 11

    def test_length_empty_collection(self) -> None:
        """Test length on empty collection returns empty."""
        result = length(FHIRPathCollection([]))
        assert result.is_empty

    def test_length_multi_element_raises(self) -> None:
        """Test length on multi-element collection raises error."""
        with pytest.raises(Exception):  # FHIRPathFunctionError
            length(FHIRPathCollection(["a", "b"]))


class TestSubstring:
    """Tests for substring() function."""

    def test_substring_start_only(self) -> None:
        """Test substring with start index only."""
        result = substring(FHIRPathCollection(["hello"]), 1)
        assert result.is_singleton
        assert result.singleton_value == "ello"

    def test_substring_with_length(self) -> None:
        """Test substring with start and length."""
        result = substring(FHIRPathCollection(["hello"]), 1, 2)
        assert result.is_singleton
        assert result.singleton_value == "el"

    def test_substring_start_zero(self) -> None:
        """Test substring starting at 0."""
        result = substring(FHIRPathCollection(["hello"]), 0)
        assert result.singleton_value == "hello"

    def test_substring_start_at_end(self) -> None:
        """Test substring starting at string length."""
        result = substring(FHIRPathCollection(["hello"]), 5)
        assert result.singleton_value == ""

    def test_substring_beyond_length(self) -> None:
        """Test substring with start beyond string length."""
        result = substring(FHIRPathCollection(["hello"]), 10)
        assert result.is_empty

    def test_substring_negative_start(self) -> None:
        """Test substring with negative start returns empty."""
        result = substring(FHIRPathCollection(["hello"]), -1)
        assert result.is_empty

    def test_substring_empty_collection(self) -> None:
        """Test substring on empty collection."""
        result = substring(FHIRPathCollection([]), 1)
        assert result.is_empty

    def test_substring_length_exceeds_remaining(self) -> None:
        """Test substring where length exceeds remaining characters."""
        result = substring(FHIRPathCollection(["hello"]), 3, 10)
        assert result.singleton_value == "lo"


class TestStartsWith:
    """Tests for startsWith() function."""

    def test_starts_with_true(self) -> None:
        """Test startsWith returns true."""
        result = starts_with(FHIRPathCollection(["hello"]), "he")
        assert result.is_singleton
        assert result.singleton_value is True

    def test_starts_with_false(self) -> None:
        """Test startsWith returns false."""
        result = starts_with(FHIRPathCollection(["hello"]), "lo")
        assert result.is_singleton
        assert result.singleton_value is False

    def test_starts_with_full_string(self) -> None:
        """Test startsWith with full string."""
        result = starts_with(FHIRPathCollection(["hello"]), "hello")
        assert result.singleton_value is True

    def test_starts_with_empty_prefix(self) -> None:
        """Test startsWith with empty prefix."""
        result = starts_with(FHIRPathCollection(["hello"]), "")
        assert result.singleton_value is True

    def test_starts_with_empty_collection(self) -> None:
        """Test startsWith on empty collection."""
        result = starts_with(FHIRPathCollection([]), "he")
        assert result.is_empty


class TestEndsWith:
    """Tests for endsWith() function."""

    def test_ends_with_true(self) -> None:
        """Test endsWith returns true."""
        result = ends_with(FHIRPathCollection(["hello"]), "lo")
        assert result.is_singleton
        assert result.singleton_value is True

    def test_ends_with_false(self) -> None:
        """Test endsWith returns false."""
        result = ends_with(FHIRPathCollection(["hello"]), "he")
        assert result.is_singleton
        assert result.singleton_value is False

    def test_ends_with_full_string(self) -> None:
        """Test endsWith with full string."""
        result = ends_with(FHIRPathCollection(["hello"]), "hello")
        assert result.singleton_value is True

    def test_ends_with_empty_suffix(self) -> None:
        """Test endsWith with empty suffix."""
        result = ends_with(FHIRPathCollection(["hello"]), "")
        assert result.singleton_value is True

    def test_ends_with_empty_collection(self) -> None:
        """Test endsWith on empty collection."""
        result = ends_with(FHIRPathCollection([]), "lo")
        assert result.is_empty


class TestContains:
    """Tests for contains() function."""

    def test_contains_true(self) -> None:
        """Test contains returns true."""
        result = contains(FHIRPathCollection(["hello world"]), "world")
        assert result.is_singleton
        assert result.singleton_value is True

    def test_contains_false(self) -> None:
        """Test contains returns false."""
        result = contains(FHIRPathCollection(["hello world"]), "xyz")
        assert result.is_singleton
        assert result.singleton_value is False

    def test_contains_at_start(self) -> None:
        """Test contains at string start."""
        result = contains(FHIRPathCollection(["hello"]), "hel")
        assert result.singleton_value is True

    def test_contains_at_end(self) -> None:
        """Test contains at string end."""
        result = contains(FHIRPathCollection(["hello"]), "llo")
        assert result.singleton_value is True

    def test_contains_empty_substring(self) -> None:
        """Test contains with empty substring."""
        result = contains(FHIRPathCollection(["hello"]), "")
        assert result.singleton_value is True

    def test_contains_empty_collection(self) -> None:
        """Test contains on empty collection."""
        result = contains(FHIRPathCollection([]), "test")
        assert result.is_empty


class TestUpper:
    """Tests for upper() function."""

    def test_upper_lowercase(self) -> None:
        """Test upper on lowercase string."""
        result = upper(FHIRPathCollection(["hello"]))
        assert result.is_singleton
        assert result.singleton_value == "HELLO"

    def test_upper_mixed_case(self) -> None:
        """Test upper on mixed case string."""
        result = upper(FHIRPathCollection(["HeLLo"]))
        assert result.singleton_value == "HELLO"

    def test_upper_already_upper(self) -> None:
        """Test upper on already uppercase string."""
        result = upper(FHIRPathCollection(["HELLO"]))
        assert result.singleton_value == "HELLO"

    def test_upper_empty_string(self) -> None:
        """Test upper on empty string."""
        result = upper(FHIRPathCollection([""]))
        assert result.singleton_value == ""

    def test_upper_empty_collection(self) -> None:
        """Test upper on empty collection."""
        result = upper(FHIRPathCollection([]))
        assert result.is_empty


class TestLower:
    """Tests for lower() function."""

    def test_lower_uppercase(self) -> None:
        """Test lower on uppercase string."""
        result = lower(FHIRPathCollection(["HELLO"]))
        assert result.is_singleton
        assert result.singleton_value == "hello"

    def test_lower_mixed_case(self) -> None:
        """Test lower on mixed case string."""
        result = lower(FHIRPathCollection(["HeLLo"]))
        assert result.singleton_value == "hello"

    def test_lower_already_lower(self) -> None:
        """Test lower on already lowercase string."""
        result = lower(FHIRPathCollection(["hello"]))
        assert result.singleton_value == "hello"

    def test_lower_empty_string(self) -> None:
        """Test lower on empty string."""
        result = lower(FHIRPathCollection([""]))
        assert result.singleton_value == ""

    def test_lower_empty_collection(self) -> None:
        """Test lower on empty collection."""
        result = lower(FHIRPathCollection([]))
        assert result.is_empty


class TestReplace:
    """Tests for replace() function."""

    def test_replace_simple(self) -> None:
        """Test simple string replacement."""
        result = replace(FHIRPathCollection(["hello world"]), "world", "universe")
        assert result.is_singleton
        assert result.singleton_value == "hello universe"

    def test_replace_multiple_occurrences(self) -> None:
        """Test replacement of multiple occurrences."""
        result = replace(FHIRPathCollection(["a,b,a"]), "a", "x")
        assert result.singleton_value == "x,b,x"

    def test_replace_not_found(self) -> None:
        """Test replacement when pattern not found."""
        result = replace(FHIRPathCollection(["hello"]), "xyz", "abc")
        assert result.singleton_value == "hello"

    def test_replace_with_empty(self) -> None:
        """Test replacement with empty string."""
        result = replace(FHIRPathCollection(["hello"]), "l", "")
        assert result.singleton_value == "heo"

    def test_replace_empty_collection(self) -> None:
        """Test replace on empty collection."""
        result = replace(FHIRPathCollection([]), "a", "b")
        assert result.is_empty


class TestMatches:
    """Tests for matches() function."""

    def test_matches_digit_true(self) -> None:
        """Test regex match with digits."""
        result = matches(FHIRPathCollection(["hello123"]), r"\d+")
        assert result.is_singleton
        assert result.singleton_value is True

    def test_matches_digit_false(self) -> None:
        """Test regex match without digits."""
        result = matches(FHIRPathCollection(["hello"]), r"\d+")
        assert result.is_singleton
        assert result.singleton_value is False

    def test_matches_email_pattern(self) -> None:
        """Test regex match with email pattern."""
        result = matches(FHIRPathCollection(["test@example.com"]), r"[\w.]+@[\w.]+")
        assert result.singleton_value is True

    def test_matches_empty_string(self) -> None:
        """Test regex match on empty string."""
        result = matches(FHIRPathCollection([""]), r"\d+")
        assert result.singleton_value is False

    def test_matches_empty_collection(self) -> None:
        """Test matches on empty collection."""
        result = matches(FHIRPathCollection([]), r"\d+")
        assert result.is_empty

    def test_matches_invalid_regex_raises(self) -> None:
        """Test matches with invalid regex raises error."""
        from ...errors import FHIRPathFunctionError
        with pytest.raises(FHIRPathFunctionError):
            matches(FHIRPathCollection(["test"]), r"[invalid")


class TestReplaceMatches:
    """Tests for replaceMatches() function."""

    def test_replace_matches_digits(self) -> None:
        """Test regex replacement of digits."""
        result = replace_matches(FHIRPathCollection(["hello123world"]), r"\d+", "X")
        assert result.is_singleton
        assert result.singleton_value == "helloXworld"

    def test_replace_matches_multiple(self) -> None:
        """Test regex replacement of multiple matches."""
        result = replace_matches(FHIRPathCollection(["a1b2c3"]), r"\d", "-")
        assert result.singleton_value == "a-b-c-"

    def test_replace_matches_no_match(self) -> None:
        """Test regex replacement when no match."""
        result = replace_matches(FHIRPathCollection(["hello"]), r"\d+", "X")
        assert result.singleton_value == "hello"

    def test_replace_matches_with_groups(self) -> None:
        """Test regex replacement with capture groups."""
        result = replace_matches(FHIRPathCollection(["hello world"]), r"(\w+) (\w+)", r"\2 \1")
        assert result.singleton_value == "world hello"

    def test_replace_matches_empty_collection(self) -> None:
        """Test replaceMatches on empty collection."""
        result = replace_matches(FHIRPathCollection([]), r"\d+", "X")
        assert result.is_empty


class TestSplit:
    """Tests for split() function."""

    def test_split_comma(self) -> None:
        """Test split by comma."""
        result = split(FHIRPathCollection(["a,b,c"]), ",")
        assert len(result) == 3
        assert result.values == ["a", "b", "c"]

    def test_split_space(self) -> None:
        """Test split by space."""
        result = split(FHIRPathCollection(["hello world"]), " ")
        assert len(result) == 2
        assert result.values == ["hello", "world"]

    def test_split_no_separator(self) -> None:
        """Test split when separator not found."""
        result = split(FHIRPathCollection(["hello"]), ",")
        assert len(result) == 1
        assert result.singleton_value == "hello"

    def test_split_empty_string(self) -> None:
        """Test split on empty string."""
        result = split(FHIRPathCollection([""]), ",")
        assert len(result) == 1
        assert result.singleton_value == ""

    def test_split_empty_collection(self) -> None:
        """Test split on empty collection."""
        result = split(FHIRPathCollection([]), ",")
        assert result.is_empty


class TestJoin:
    """Tests for join() function."""

    def test_join_comma(self) -> None:
        """Test join with comma."""
        result = join(FHIRPathCollection(["a", "b", "c"]), ",")
        assert result.is_singleton
        assert result.singleton_value == "a,b,c"

    def test_join_space(self) -> None:
        """Test join with space."""
        result = join(FHIRPathCollection(["hello", "world"]), " ")
        assert result.singleton_value == "hello world"

    def test_join_single_element(self) -> None:
        """Test join with single element."""
        result = join(FHIRPathCollection(["hello"]), ",")
        assert result.singleton_value == "hello"

    def test_join_empty_separator(self) -> None:
        """Test join with empty separator."""
        result = join(FHIRPathCollection(["a", "b"]), "")
        assert result.singleton_value == "ab"

    def test_join_empty_collection(self) -> None:
        """Test join on empty collection."""
        result = join(FHIRPathCollection([]), ",")
        assert result.is_empty

    def test_join_with_nulls(self) -> None:
        """Test join handles nulls as empty strings."""
        result = join(FHIRPathCollection(["a", None, "b"]), ",")
        assert result.singleton_value == "a,,b"


class TestTrim:
    """Tests for trim() function."""

    def test_trim_both_sides(self) -> None:
        """Test trim removes from both sides."""
        result = trim(FHIRPathCollection(["  hello  "]))
        assert result.is_singleton
        assert result.singleton_value == "hello"

    def test_trim_leading(self) -> None:
        """Test trim removes leading whitespace."""
        result = trim(FHIRPathCollection(["   hello"]))
        assert result.singleton_value == "hello"

    def test_trim_trailing(self) -> None:
        """Test trim removes trailing whitespace."""
        result = trim(FHIRPathCollection(["hello   "]))
        assert result.singleton_value == "hello"

    def test_trim_no_whitespace(self) -> None:
        """Test trim on string without whitespace."""
        result = trim(FHIRPathCollection(["hello"]))
        assert result.singleton_value == "hello"

    def test_trim_only_whitespace(self) -> None:
        """Test trim on string with only whitespace."""
        result = trim(FHIRPathCollection(["   "]))
        assert result.singleton_value == ""

    def test_trim_empty_string(self) -> None:
        """Test trim on empty string."""
        result = trim(FHIRPathCollection([""]))
        assert result.singleton_value == ""

    def test_trim_empty_collection(self) -> None:
        """Test trim on empty collection."""
        result = trim(FHIRPathCollection([]))
        assert result.is_empty


class TestConcatenate:
    """Tests for concatenate (& operator) function."""

    def test_concatenate_simple(self) -> None:
        """Test simple concatenation."""
        result = concatenate(FHIRPathCollection(["hello"]), FHIRPathCollection([" world"]))
        assert result.is_singleton
        assert result.singleton_value == "hello world"

    def test_concatenate_no_space(self) -> None:
        """Test concatenation without space."""
        result = concatenate(FHIRPathCollection(["hello"]), FHIRPathCollection(["world"]))
        assert result.singleton_value == "helloworld"

    def test_concatenate_left_empty(self) -> None:
        """Test concatenation with empty left operand."""
        result = concatenate(FHIRPathCollection([]), FHIRPathCollection(["world"]))
        assert result.singleton_value == "world"

    def test_concatenate_right_empty(self) -> None:
        """Test concatenation with empty right operand."""
        result = concatenate(FHIRPathCollection(["hello"]), FHIRPathCollection([]))
        assert result.singleton_value == "hello"

    def test_concatenate_both_empty(self) -> None:
        """Test concatenation with both empty."""
        result = concatenate(FHIRPathCollection([]), FHIRPathCollection([]))
        assert result.is_empty

    def test_concatenate_with_null(self) -> None:
        """Test concatenation handles null as empty string."""
        result = concatenate(FHIRPathCollection([None]), FHIRPathCollection(["world"]))
        assert result.singleton_value == "world"

    def test_concatenate_empty_strings(self) -> None:
        """Test concatenation of empty strings."""
        result = concatenate(FHIRPathCollection([""]), FHIRPathCollection([""]))
        assert result.singleton_value == ""


class TestStringFunctionRegistry:
    """Tests for STRING_FUNCTIONS registry."""

    def test_registry_has_required_functions(self) -> None:
        """Test that registry contains all required functions."""
        required_functions = [
            "length",
            "upper",
            "lower",
            "trim",
            "startsWith",
            "endsWith",
            "contains",
            "matches",
            "split",
            "join",
            "substring",
            "replace",
            "replaceMatches",
        ]
        for func_name in required_functions:
            assert func_name in STRING_FUNCTIONS, f"Missing function: {func_name}"

    def test_length_via_registry(self) -> None:
        """Test calling length through registry."""
        func = STRING_FUNCTIONS["length"]
        result = func(FHIRPathCollection(["hello"]))
        assert result.singleton_value == 5

    def test_starts_with_via_registry(self) -> None:
        """Test calling startsWith through registry."""
        func = STRING_FUNCTIONS["startsWith"]
        result = func(FHIRPathCollection(["hello"]), "he")
        assert result.singleton_value is True

    def test_replace_via_registry(self) -> None:
        """Test calling replace through registry."""
        func = STRING_FUNCTIONS["replace"]
        result = func(FHIRPathCollection(["hello world"]), "world", "universe")
        assert result.singleton_value == "hello universe"


class TestFHIRPathSemantics:
    """Tests for FHIRPath-specific semantics."""

    def test_empty_propagation(self) -> None:
        """Test that empty collections propagate correctly."""
        # All string functions should return empty for empty input
        empty = FHIRPathCollection([])

        assert length(empty).is_empty
        assert upper(empty).is_empty
        assert lower(empty).is_empty
        assert trim(empty).is_empty

    def test_singleton_unwrapping(self) -> None:
        """Test that singletons are properly unwrapped."""
        # Single string should be unwrapped for operations
        result = length(FHIRPathCollection(["test"]))
        assert result.is_singleton
        assert result.singleton_value == 4

    def test_multi_element_error(self) -> None:
        """Test that multi-element collections raise errors."""
        multi = FHIRPathCollection(["a", "b"])

        with pytest.raises(Exception):
            length(multi)

        with pytest.raises(Exception):
            upper(multi)

    def test_boolean_return_type(self) -> None:
        """Test that boolean functions return proper boolean values."""
        result = starts_with(FHIRPathCollection(["hello"]), "he")
        assert type(result.singleton_value) is bool
        assert result.singleton_value is True

    def test_integer_return_type(self) -> None:
        """Test that length returns integer."""
        result = length(FHIRPathCollection(["hello"]))
        assert type(result.singleton_value) is int
        assert result.singleton_value == 5
