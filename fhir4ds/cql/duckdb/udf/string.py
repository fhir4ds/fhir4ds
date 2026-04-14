"""
CQL String Function UDFs

DEPRECATED: These UDFs are superseded by Tier 1 SQL macros in macros/string.py
which provide zero Python overhead. These are retained for backward compatibility
with code that references the stringLength/stringLower/etc. function names directly.
New code should use the SQL macro versions (Length, Lower, Upper, etc.) instead.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
import duckdb

if TYPE_CHECKING:
    import duckdb



import logging

_logger = logging.getLogger(__name__)
def stringLength(s: str | None) -> int | None:
    """CQL Length() - character count."""
    if s is None:
        return None
    return len(s)


def stringLower(s: str | None) -> str | None:
    """CQL Lower() - lowercase conversion."""
    if s is None:
        return None
    return s.lower()


def stringUpper(s: str | None) -> str | None:
    """CQL Upper() - uppercase conversion."""
    if s is None:
        return None
    return s.upper()


def stringSubstring(s: str | None, start: int, length: int | None = None) -> str | None:
    """
    CQL Substring(s, start, length) - extract substring.
    Note: CQL uses 0-based indexing.
    """
    if s is None:
        return None
    try:
        if length is None:
            return s[start:]
        return s[start:start + length]
    except TypeError as e:
        _logger.warning("UDF stringSubstring failed: %s", e)
        return None


def stringConcatenate(a: str | None, b: str | None) -> str | None:
    """CQL Concatenate(a, b) - string concatenation."""
    if a is None or b is None:
        return None
    return a + b


def stringSplit(s: str | None, separator: str) -> list | None:
    """CQL Split(s, separator) - split into list."""
    if s is None:
        return None
    return s.split(separator)


def stringPositionOf(pattern: str, s: str | None) -> int | None:
    """CQL PositionOf(pattern, s) - find pattern index."""
    if s is None:
        return None
    try:
        return s.find(pattern)
    except TypeError as e:
        _logger.warning("UDF stringPositionOf failed: %s", e)
        return None


def stringStartsWith(s: str | None, prefix: str) -> bool | None:
    """CQL StartsWith(s, prefix)."""
    if s is None:
        return None
    return s.startswith(prefix)


def stringEndsWith(s: str | None, suffix: str) -> bool | None:
    """CQL EndsWith(s, suffix)."""
    if s is None:
        return None
    return s.endswith(suffix)


def stringContains(s: str | None, substring: str) -> bool | None:
    """CQL Contains(s, substring)."""
    if s is None:
        return None
    return substring in s


def stringMatches(s: str | None, pattern: str) -> bool | None:
    """CQL Matches(s, pattern) - regex match."""
    if s is None:
        return None
    import re
    try:
        return bool(re.search(pattern, s))
    except re.error as e:
        _logger.warning("UDF stringMatches failed: %s", e)
        return None


def stringReplace(s: str | None, old: str, new: str) -> str | None:
    """CQL Replace(s, old, new)."""
    if s is None:
        return None
    return s.replace(old, new)


def registerStringUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all string UDFs."""
    con.create_function("stringLength", stringLength, null_handling="special")
    con.create_function("stringLower", stringLower, null_handling="special")
    con.create_function("stringUpper", stringUpper, null_handling="special")
    con.create_function("stringSubstring", stringSubstring, null_handling="special")
    con.create_function("stringConcatenate", stringConcatenate, null_handling="special")
    # stringSplit returns a list - DuckDB needs explicit type
    con.create_function("stringSplit", stringSplit, return_type="VARCHAR", null_handling="special")
    con.create_function("stringPositionOf", stringPositionOf, null_handling="special")
    con.create_function("stringStartsWith", stringStartsWith, null_handling="special")
    con.create_function("stringEndsWith", stringEndsWith, null_handling="special")
    con.create_function("stringContains", stringContains, null_handling="special")
    con.create_function("stringMatches", stringMatches, null_handling="special")
    con.create_function("stringReplace", stringReplace, null_handling="special")


__all__ = [
    "stringLength", "stringLower", "stringUpper", "stringSubstring",
    "stringConcatenate", "stringSplit", "stringPositionOf",
    "stringStartsWith", "stringEndsWith", "stringContains",
    "stringMatches", "stringReplace", "registerStringUdfs",
]
