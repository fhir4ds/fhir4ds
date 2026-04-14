"""
FHIRPath String Functions

Implements string manipulation functions defined in the FHIRPath specification.

Key FHIRPath semantics:
- String functions on empty collection return empty collection
- Most functions work on singleton string values
- The & operator converts null/empty to empty string for concatenation

Reference: https://hl7.org/fhirpath/#string-manipulation
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..collection import FHIRPathCollection, EMPTY, wrap_as_collection
from ..errors import FHIRPathFunctionError

if TYPE_CHECKING:
    pass


def _get_singleton_string(collection: FHIRPathCollection, func_name: str) -> str | None:
    """
    Extract singleton string value from collection.

    Args:
        collection: Input collection
        func_name: Function name for error messages

    Returns:
        String value if singleton, None if empty

    Raises:
        FHIRPathFunctionError: If collection has multiple elements or non-string value
    """
    if collection.is_empty:
        return None
    if not collection.is_singleton:
        raise FHIRPathFunctionError(
            func_name,
            f"Expected singleton collection, got {len(collection)} elements"
        )
    value = collection.singleton_value
    if value is None:
        return None
    if not isinstance(value, str):
        # Convert non-string to string
        value = str(value)
    return value


def _string_result(value: str | None) -> FHIRPathCollection:
    """
    Wrap string result in collection, returning empty for None.

    Args:
        value: String value or None

    Returns:
        Collection with string or empty collection
    """
    if value is None:
        return FHIRPathCollection([])
    return FHIRPathCollection([value])


def _bool_result(value: bool | None) -> FHIRPathCollection:
    """
    Wrap boolean result in collection, returning empty for None.

    Args:
        value: Boolean value or None

    Returns:
        Collection with boolean or empty collection
    """
    if value is None:
        return FHIRPathCollection([])
    return FHIRPathCollection([value])


# =============================================================================
# Length and Substring Functions
# =============================================================================


def length(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns the length of the input string.

    If the input collection is empty, the result is empty.
    If the input collection contains multiple items, an error is raised.

    FHIRPath: length() : integer

    Args:
        collection: A collection containing a single string

    Returns:
        Collection containing the length of the string

    Example:
        >>> length(FHIRPathCollection(['hello']))
        FHIRPathCollection([5])
        >>> length(FHIRPathCollection([]))
        FHIRPathCollection({})
    """
    value = _get_singleton_string(collection, "length")
    if value is None:
        return FHIRPathCollection([])
    return FHIRPathCollection([len(value)])


def substring(
    collection: FHIRPathCollection,
    start: int,
    length_val: int | None = None
) -> FHIRPathCollection:
    """
    Returns the part of the string starting at position start (0-based).

    If start is less than 0 or greater than the length of the string,
    the result is empty. If length is provided, at most that many characters
    are returned.

    FHIRPath:
        substring(start : integer) : string
        substring(start : integer, length : integer) : string

    Args:
        collection: A collection containing a single string
        start: Starting position (0-based)
        length_val: Optional maximum number of characters to return

    Returns:
        Collection containing the substring

    Example:
        >>> substring(FHIRPathCollection(['hello']), 1)
        FHIRPathCollection(['ello'])
        >>> substring(FHIRPathCollection(['hello']), 1, 2)
        FHIRPathCollection(['el'])
        >>> substring(FHIRPathCollection(['hello']), 10)
        FHIRPathCollection({})
    """
    value = _get_singleton_string(collection, "substring")
    if value is None:
        return FHIRPathCollection([])

    # Validate start index
    if start < 0 or start > len(value):
        return FHIRPathCollection([])

    if length_val is None:
        return _string_result(value[start:])
    else:
        if length_val < 0:
            return FHIRPathCollection([])
        return _string_result(value[start:start + length_val])


# =============================================================================
# Prefix/Suffix Functions
# =============================================================================


def starts_with(collection: FHIRPathCollection, prefix: str) -> FHIRPathCollection:
    """
    Returns true if the string starts with the given prefix.

    FHIRPath: startsWith(prefix : string) : boolean

    Args:
        collection: A collection containing a single string
        prefix: The prefix to check for

    Returns:
        Collection containing true or false, or empty if input is empty

    Example:
        >>> starts_with(FHIRPathCollection(['hello']), 'he')
        FHIRPathCollection([True])
        >>> starts_with(FHIRPathCollection(['hello']), 'xy')
        FHIRPathCollection([False])
    """
    value = _get_singleton_string(collection, "startsWith")
    if value is None:
        return FHIRPathCollection([])
    return _bool_result(value.startswith(prefix))


def ends_with(collection: FHIRPathCollection, suffix: str) -> FHIRPathCollection:
    """
    Returns true if the string ends with the given suffix.

    FHIRPath: endsWith(suffix : string) : boolean

    Args:
        collection: A collection containing a single string
        suffix: The suffix to check for

    Returns:
        Collection containing true or false, or empty if input is empty

    Example:
        >>> ends_with(FHIRPathCollection(['hello']), 'lo')
        FHIRPathCollection([True])
        >>> ends_with(FHIRPathCollection(['hello']), 'xy')
        FHIRPathCollection([False])
    """
    value = _get_singleton_string(collection, "endsWith")
    if value is None:
        return FHIRPathCollection([])
    return _bool_result(value.endswith(suffix))


# =============================================================================
# Contains and Case Functions
# =============================================================================


def contains(collection: FHIRPathCollection, substring_val: str) -> FHIRPathCollection:
    """
    Returns true if the string contains the given substring.

    FHIRPath: contains(substring : string) : boolean

    Args:
        collection: A collection containing a single string
        substring_val: The substring to search for

    Returns:
        Collection containing true or false, or empty if input is empty

    Example:
        >>> contains(FHIRPathCollection(['hello world']), 'world')
        FHIRPathCollection([True])
        >>> contains(FHIRPathCollection(['hello world']), 'xyz')
        FHIRPathCollection([False])
    """
    value = _get_singleton_string(collection, "contains")
    if value is None:
        return FHIRPathCollection([])
    return _bool_result(substring_val in value)


def upper(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns the string with all characters converted to uppercase.

    FHIRPath: upper() : string

    Args:
        collection: A collection containing a single string

    Returns:
        Collection containing the uppercase string, or empty if input is empty

    Example:
        >>> upper(FHIRPathCollection(['hello']))
        FHIRPathCollection(['HELLO'])
    """
    value = _get_singleton_string(collection, "upper")
    if value is None:
        return FHIRPathCollection([])
    return _string_result(value.upper())


def lower(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns the string with all characters converted to lowercase.

    FHIRPath: lower() : string

    Args:
        collection: A collection containing a single string

    Returns:
        Collection containing the lowercase string, or empty if input is empty

    Example:
        >>> lower(FHIRPathCollection(['HELLO']))
        FHIRPathCollection(['hello'])
    """
    value = _get_singleton_string(collection, "lower")
    if value is None:
        return FHIRPathCollection([])
    return _string_result(value.lower())


# =============================================================================
# Replace and Regex Functions
# =============================================================================


def replace(
    collection: FHIRPathCollection,
    pattern: str,
    replacement: str
) -> FHIRPathCollection:
    """
    Returns a string with all occurrences of pattern replaced with replacement.

    This is a simple string replacement, not regex-based.

    FHIRPath: replace(pattern : string, replacement : string) : string

    Args:
        collection: A collection containing a single string
        pattern: The substring pattern to replace
        replacement: The replacement string

    Returns:
        Collection containing the string with replacements, or empty if input is empty

    Example:
        >>> replace(FHIRPathCollection(['hello world']), 'world', 'universe')
        FHIRPathCollection(['hello universe'])
    """
    value = _get_singleton_string(collection, "replace")
    if value is None:
        return FHIRPathCollection([])
    return _string_result(value.replace(pattern, replacement))


def matches(collection: FHIRPathCollection, regex: str) -> FHIRPathCollection:
    """
    Returns true if the string matches the given regular expression.

    FHIRPath uses partial matching semantics - the regex matches if any
    part of the string matches.

    FHIRPath: matches(regex : string) : boolean

    Args:
        collection: A collection containing a single string
        regex: The regular expression pattern (Python regex syntax)

    Returns:
        Collection containing true or false, or empty if input is empty

    Example:
        >>> matches(FHIRPathCollection(['hello123']), r'\\d+')
        FHIRPathCollection([True])
        >>> matches(FHIRPathCollection(['hello']), r'\\d+')
        FHIRPathCollection([False])
    """
    value = _get_singleton_string(collection, "matches")
    if value is None:
        return FHIRPathCollection([])
    try:
        # FHIRPath uses partial matching (search), not full matching
        result = bool(re.search(regex, value))
        return _bool_result(result)
    except re.error as e:
        raise FHIRPathFunctionError("matches", f"Invalid regular expression: {e}")


def replace_matches(
    collection: FHIRPathCollection,
    regex: str,
    replacement: str
) -> FHIRPathCollection:
    """
    Returns a string with all matches of the regex replaced.

    FHIRPath: replaceMatches(regex : string, replacement : string) : string

    Args:
        collection: A collection containing a single string
        regex: The regular expression pattern
        replacement: The replacement string (can include backreferences)

    Returns:
        Collection containing the string with replacements, or empty if input is empty

    Example:
        >>> replace_matches(FHIRPathCollection(['hello123world']), r'\\d+', 'X')
        FHIRPathCollection(['helloXworld'])
    """
    value = _get_singleton_string(collection, "replaceMatches")
    if value is None:
        return FHIRPathCollection([])
    try:
        result = re.sub(regex, replacement, value)
        return _string_result(result)
    except re.error as e:
        raise FHIRPathFunctionError("replaceMatches", f"Invalid regular expression: {e}")


# =============================================================================
# Split and Join Functions
# =============================================================================


def split(collection: FHIRPathCollection, separator: str) -> FHIRPathCollection:
    """
    Splits the string by the given separator and returns a collection of strings.

    FHIRPath: split(separator : string) : collection

    Args:
        collection: A collection containing a single string
        separator: The separator string to split on

    Returns:
        Collection containing the split parts

    Example:
        >>> split(FHIRPathCollection(['a,b,c']), ',')
        FHIRPathCollection(['a', 'b', 'c'])
        >>> split(FHIRPathCollection(['hello']), ',')
        FHIRPathCollection(['hello'])
    """
    value = _get_singleton_string(collection, "split")
    if value is None:
        return FHIRPathCollection([])
    parts = value.split(separator)
    return FHIRPathCollection(parts)


def join(collection: FHIRPathCollection, separator: str) -> FHIRPathCollection:
    """
    Joins a collection of strings into a single string with the given separator.

    FHIRPath: join(separator : string) : string

    Args:
        collection: A collection of strings to join
        separator: The separator string to join with

    Returns:
        Collection containing the joined string, or empty if input is empty

    Example:
        >>> join(FHIRPathCollection(['a', 'b', 'c']), ',')
        FHIRPathCollection(['a,b,c'])
    """
    if collection.is_empty:
        return FHIRPathCollection([])

    # Convert all values to strings
    str_values = []
    for val in collection.values:
        if val is None:
            str_values.append("")
        else:
            str_values.append(str(val))

    return _string_result(separator.join(str_values))


def trim(collection: FHIRPathCollection) -> FHIRPathCollection:
    """
    Returns the string with leading and trailing whitespace removed.

    FHIRPath: trim() : string

    Args:
        collection: A collection containing a single string

    Returns:
        Collection containing the trimmed string, or empty if input is empty

    Example:
        >>> trim(FHIRPathCollection(['  hello  ']))
        FHIRPathCollection(['hello'])
    """
    value = _get_singleton_string(collection, "trim")
    if value is None:
        return FHIRPathCollection([])
    return _string_result(value.strip())


# =============================================================================
# String Concatenation Operator
# =============================================================================


def concatenate(
    left: FHIRPathCollection,
    right: FHIRPathCollection
) -> FHIRPathCollection:
    """
    Concatenate two strings using FHIRPath & operator semantics.

    The & operator in FHIRPath:
    - Converts null/empty to empty string
    - Returns empty if both operands are empty
    - Returns the non-empty operand if one is empty

    FHIRPath: left & right

    Args:
        left: Left operand collection
        right: Right operand collection

    Returns:
        Collection containing the concatenated string, or empty if both are empty

    Example:
        >>> concatenate(FHIRPathCollection(['hello']), FHIRPathCollection([' world']))
        FHIRPathCollection(['hello world'])
        >>> concatenate(FHIRPathCollection([]), FHIRPathCollection(['world']))
        FHIRPathCollection(['world'])
        >>> concatenate(FHIRPathCollection([]), FHIRPathCollection([]))
        FHIRPathCollection({})
    """
    # Get left value (empty string if empty/null)
    left_value = ""
    if not left.is_empty:
        val = left.singleton_value if left.is_singleton else None
        if val is not None:
            left_value = str(val) if not isinstance(val, str) else val

    # Get right value (empty string if empty/null)
    right_value = ""
    if not right.is_empty:
        val = right.singleton_value if right.is_singleton else None
        if val is not None:
            right_value = str(val) if not isinstance(val, str) else val

    # If both are empty strings (from empty collections), return empty
    if left.is_empty and right.is_empty:
        return FHIRPathCollection([])

    return _string_result(left_value + right_value)


# =============================================================================
# Function Registry for Evaluator Integration
# =============================================================================

STRING_FUNCTIONS = {
    # No-argument functions
    "length": lambda col: length(col),
    "upper": lambda col: upper(col),
    "lower": lambda col: lower(col),
    "trim": lambda col: trim(col),

    # Single-argument functions
    "startsWith": lambda col, arg: starts_with(col, arg),
    "endsWith": lambda col, arg: ends_with(col, arg),
    "contains": lambda col, arg: contains(col, arg),
    "matches": lambda col, arg: matches(col, arg),
    "split": lambda col, arg: split(col, arg),
    "join": lambda col, arg: join(col, arg),
    "substring": lambda col, arg: substring(col, arg),

    # Two-argument functions
    "replace": lambda col, arg1, arg2: replace(col, arg1, arg2),
    "replaceMatches": lambda col, arg1, arg2: replace_matches(col, arg1, arg2),

    # Variable-argument substring
    "substringWithLength": lambda col, start, length_val: substring(col, start, length_val),
}
