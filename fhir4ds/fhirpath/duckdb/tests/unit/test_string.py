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
from ...errors import FHIRPathFunctionError
from ...functions.string import (
    length,
    index_of,
    substring,
    starts_with,
    ends_with,
    contains,
    upper,
    lower,
    replace,
    matches,
    replace_matches,
    to_chars,
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

    def test_length_non_string_raises(self) -> None:
        """Test length on non-string singleton raises error."""
        with pytest.raises(FHIRPathFunctionError):
            length(FHIRPathCollection([123]))


class TestIndexOfFp09Skeptic:
    """Tests for index_of() direct helper (FHIRPath §5.6.1)."""

    def test_index_of_found(self) -> None:
        result = index_of(FHIRPathCollection(["abcdefg"]), "bc")
        assert result.is_singleton
        assert type(result.singleton_value) is int
        assert result.singleton_value == 1

    def test_index_of_first_occurrence(self) -> None:
        result = index_of(FHIRPathCollection(["abcabc"]), "bc")
        assert result.singleton_value == 1

    def test_index_of_not_found(self) -> None:
        result = index_of(FHIRPathCollection(["abcdefg"]), "x")
        assert result.is_singleton
        assert result.singleton_value == -1

    def test_index_of_empty_substring_returns_zero(self) -> None:
        result = index_of(FHIRPathCollection(["abcdefg"]), "")
        assert result.singleton_value == 0

    def test_index_of_empty_input_returns_empty(self) -> None:
        result = index_of(FHIRPathCollection([]), "a")
        assert result.is_empty

    def test_index_of_empty_argument_returns_empty(self) -> None:
        result = index_of(FHIRPathCollection(["abc"]), None)
        assert result.is_empty

    def test_index_of_unicode_positions(self) -> None:
        result = index_of(FHIRPathCollection(["héllo"]), "l")
        assert result.singleton_value == 2

    def test_index_of_non_string_raises(self) -> None:
        with pytest.raises(FHIRPathFunctionError):
            index_of(FHIRPathCollection([3]), "a")

    def test_index_of_multi_element_raises(self) -> None:
        with pytest.raises(FHIRPathFunctionError):
            index_of(FHIRPathCollection(["a", "b"]), "a")

    def test_index_of_registered_in_string_functions(self) -> None:
        assert "indexOf" in STRING_FUNCTIONS


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
        """Test substring starting at string length returns empty."""
        result = substring(FHIRPathCollection(["hello"]), 5)
        assert result.is_empty

    def test_substring_start_at_end_with_length(self) -> None:
        """Test substring starting at string length with length returns empty."""
        result = substring(FHIRPathCollection(["hello"]), 5, 1)
        assert result.is_empty

    def test_substring_non_string_raises(self) -> None:
        """Test substring on non-string singleton raises error."""
        with pytest.raises(FHIRPathFunctionError):
            substring(FHIRPathCollection([123]), 0)

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

    def test_starts_with_non_string_input_raises(self) -> None:
        """Test startsWith on non-string singleton raises error."""
        with pytest.raises(FHIRPathFunctionError):
            starts_with(FHIRPathCollection([123]), "1")


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

    def test_ends_with_non_string_input_raises(self) -> None:
        """Test endsWith on non-string singleton raises error."""
        with pytest.raises(FHIRPathFunctionError):
            ends_with(FHIRPathCollection([123]), "3")


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

    def test_contains_non_string_input_raises(self) -> None:
        """Test contains on non-string singleton raises error."""
        with pytest.raises(FHIRPathFunctionError):
            contains(FHIRPathCollection([123]), "2")


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
        result = matches(FHIRPathCollection(["123"]), r"\d+")
        assert result.is_singleton
        assert result.singleton_value is True

    def test_matches_partial_true(self) -> None:
        """Test that matches searches within the string."""
        result = matches(FHIRPathCollection(["hello123"]), r"\d+")
        assert result.singleton_value is True

    def test_matches_dotall(self) -> None:
        """Test that dot matches newline for FHIRPath single-line regex mode."""
        result = matches(FHIRPathCollection(["a\nb"]), r"a.b")
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

    def test_matches_flags(self) -> None:
        """Test current FHIRPath i/m regex flags."""
        assert matches(FHIRPathCollection(["Library"]), "library", "i").singleton_value is True
        assert matches(FHIRPathCollection(["first\nsecond"]), "^second", "m").singleton_value is True

    def test_matches_invalid_regex_raises(self) -> None:
        """Test matches with invalid regex raises error."""
        from ...errors import FHIRPathFunctionError
        with pytest.raises(FHIRPathFunctionError):
            matches(FHIRPathCollection(["test"]), r"[invalid")

    def test_matches_rejects_redos_pattern(self) -> None:
        """Test matches rejects nested quantifiers before regex evaluation."""
        from ...errors import FHIRPathFunctionError
        with pytest.raises(FHIRPathFunctionError):
            matches(FHIRPathCollection(["aaaaaaaa"]), r"(a+)+")


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

    def test_replace_matches_empty_regex_returns_input(self) -> None:
        """Test empty regex leaves the input unchanged."""
        result = replace_matches(FHIRPathCollection(["abc"]), "", "x")
        assert result.singleton_value == "abc"

    def test_replace_matches_flags(self) -> None:
        """Test current FHIRPath i/m regex flags."""
        result = replace_matches(FHIRPathCollection(["Abc abc"]), "abc", "X", "i")
        assert result.singleton_value == "X X"

    def test_replace_matches_rejects_redos_pattern(self) -> None:
        """Test replaceMatches rejects quantified alternations before regex evaluation."""
        from ...errors import FHIRPathFunctionError
        with pytest.raises(FHIRPathFunctionError):
            replace_matches(FHIRPathCollection(["aaaaaaaa"]), r"(a|aa)+", "x")

    def test_replace_matches_dollar_substitution_syntax_fp10_skeptic2(self) -> None:
        """FP-10 QA-006: helper must implement §5.6.10 $N/${name}/$$ substitution.

        The helper previously passed the replacement straight to re.sub,
        producing literal '$1' text and rejecting PCRE named-group patterns.
        It now delegates to the engine implementation.
        """
        assert replace_matches(FHIRPathCollection(["abc"]), "(b)", "[$1]").singleton_value == "a[b]c"
        # Out-of-range $N → empty substitution (native-matching semantics)
        assert replace_matches(FHIRPathCollection(["abc"]), "(b)", "[$5]").singleton_value == "a[]c"
        # $0 full match
        assert replace_matches(FHIRPathCollection(["abc"]), "(b)", "[$0]").singleton_value == "a[b]c"
        # $$ literal dollar
        assert replace_matches(FHIRPathCollection(["Abc"]), "A", "$$").singleton_value == "$bc"
        # ${name} for existing named group substitutes; unknown name is literal
        assert (
            replace_matches(FHIRPathCollection(["11/30/1972"]), r"(?<year>[0-9]{4})", "[${year}]").singleton_value
            == "11/30/[1972]"
        )
        assert (
            replace_matches(FHIRPathCollection(["abc"]), "(b)", "[${name}]").singleton_value
            == "a[${name}]c"
        )
        # Spec §5.6.10 canonical example (numbered-group form)
        assert (
            replace_matches(
                FHIRPathCollection(["11/30/1972"]),
                r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})",
                "$2-$1-$3",
            ).singleton_value
            == "30-11-1972"
        )

    def test_replace_matches_none_args_return_empty_fp10_skeptic2(self) -> None:
        """FP-10 QA-006: None regex/replacement → empty collection (engine contract)."""
        assert replace_matches(FHIRPathCollection(["abc"]), None, "x").is_empty
        assert replace_matches(FHIRPathCollection(["abc"]), "a", None).is_empty

    def test_replace_none_args_return_empty_fp10_skeptic2(self) -> None:
        """FP-10 QA-006: replace() guards None pattern/replacement."""
        from ...errors import FHIRPathFunctionError

        assert replace(FHIRPathCollection(["abc"]), None, "x").is_empty
        assert replace(FHIRPathCollection(["abc"]), "a", None).is_empty
        with pytest.raises(FHIRPathFunctionError):
            replace(FHIRPathCollection(["abc"]), 123, "x")
        with pytest.raises(FHIRPathFunctionError):
            replace(FHIRPathCollection(["abc"]), "a", 123)

    def test_matches_ascii_class_dialect_fp10_skeptic2(self) -> None:
        """FP-10 QA-003: helper matches() uses ASCII \w/\d/\s/\b (PCRE default),
        matching the native engine, while Unicode case-insensitive matching
        still works."""
        assert matches(FHIRPathCollection(["日本語"]), r"\w+").singleton_value is False
        assert matches(FHIRPathCollection(["abc"]), r"\w+").singleton_value is True
        assert matches(FHIRPathCollection(["a\u0020b"]), r"\s").singleton_value is True
        assert matches(FHIRPathCollection(["É"]), "é", "i").singleton_value is True

    def test_matches_none_and_non_string_regex_arg_fp10_historian(self) -> None:
        """FP-10 HISTORIAN QA-002: matches() None regex → empty collection
        (sibling-helper contract); non-String regex → typed error, not a
        raw TypeError from len(None)."""
        from ...errors import FHIRPathFunctionError

        assert matches(FHIRPathCollection(["abc"]), None).is_empty
        with pytest.raises(FHIRPathFunctionError):
            matches(FHIRPathCollection(["abc"]), 123)


class TestToChars:
    """Tests for toChars() function."""

    def test_to_chars_simple(self) -> None:
        result = to_chars(FHIRPathCollection(["abc"]))
        assert result.values == ["a", "b", "c"]

    def test_to_chars_unicode_code_points(self) -> None:
        result = to_chars(FHIRPathCollection(["café"]))
        assert result.values == ["c", "a", "f", "é"]

    def test_to_chars_empty_string(self) -> None:
        result = to_chars(FHIRPathCollection([""]))
        assert result.is_empty

    def test_to_chars_empty_collection(self) -> None:
        result = to_chars(FHIRPathCollection([]))
        assert result.is_empty

    def test_to_chars_non_string_raises(self) -> None:
        with pytest.raises(FHIRPathFunctionError):
            to_chars(FHIRPathCollection([123]))


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


class TestStringHelperEngineContractFp09Historian:
    """Direct string helpers must follow engine (§5.6.1-§5.6.5) semantics.

    Engine parity contract (core evaluator + native fn_* agree):
    - empty argument collection -> empty result collection
    - non-String singleton argument -> typed FHIRPathFunctionError
    - substring(start, length<=0) -> the empty STRING '' (not empty collection)
    """

    def test_starts_with_empty_argument_returns_empty(self) -> None:
        assert starts_with(FHIRPathCollection(["hello"]), None).is_empty

    def test_ends_with_empty_argument_returns_empty(self) -> None:
        assert ends_with(FHIRPathCollection(["hello"]), None).is_empty

    def test_contains_empty_argument_returns_empty(self) -> None:
        assert contains(FHIRPathCollection(["hello"]), None).is_empty

    def test_starts_with_non_string_argument_raises_typed(self) -> None:
        with pytest.raises(FHIRPathFunctionError):
            starts_with(FHIRPathCollection(["hello"]), 3)

    def test_ends_with_non_string_argument_raises_typed(self) -> None:
        with pytest.raises(FHIRPathFunctionError):
            ends_with(FHIRPathCollection(["hello"]), True)

    def test_contains_non_string_argument_raises_typed(self) -> None:
        with pytest.raises(FHIRPathFunctionError):
            contains(FHIRPathCollection(["hello"]), 1.5)

    def test_substring_empty_start_argument_returns_empty(self) -> None:
        assert substring(FHIRPathCollection(["hello"]), None).is_empty

    def test_substring_negative_length_returns_empty_string(self) -> None:
        # Both engines return '' for length <= 0 (§5.6.2), not an empty
        # collection; the helper previously diverged by returning {}.
        result = substring(FHIRPathCollection(["hello"]), 1, -2)
        assert result.is_singleton
        assert result.singleton_value == ""

    def test_substring_zero_length_returns_empty_string(self) -> None:
        result = substring(FHIRPathCollection(["hello"]), 1, 0)
        assert result.is_singleton
        assert result.singleton_value == ""

    def test_substring_negative_start_still_empty_collection(self) -> None:
        # Negative START keeps the empty-collection convention (engines agree).
        assert substring(FHIRPathCollection(["hello"]), -1).is_empty
