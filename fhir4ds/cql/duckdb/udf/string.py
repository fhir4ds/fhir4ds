"""
CQL String Function UDFs

DEPRECATED: These UDFs are superseded by Tier 1 SQL macros in macros/string.py
which provide zero Python overhead. These are retained for backward compatibility
with code that references the stringLength/stringLower/etc. function names directly.
New code should use the SQL macro versions (Length, Lower, Upper, etc.) instead.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb



import logging
import re as _re

_logger = logging.getLogger(__name__)

# Maximum regex pattern length to accept (guard against excessively large patterns)
_MAX_REGEX_LENGTH = 1000

# Patterns indicative of catastrophic backtracking (ReDoS).
# Detects nested quantifiers like (a+)+ and quantified alternations like (a|a)+.
_REDOS_PATTERNS = _re.compile(
    r'(\((?:[^()]*[+*])[^()]*\)[+*?]'  # nested quantifier
    r'|\((?:[^()]*\|[^()]*)\)[+*])'     # quantified alternation
)


def _compile_cql_regex(pattern: str) -> _re.Pattern | None:
    if len(pattern) > _MAX_REGEX_LENGTH:
        _logger.warning("CQL regex pattern exceeds max length (%d)", len(pattern))
        return None
    if _REDOS_PATTERNS.search(pattern):
        _logger.warning("CQL regex pattern rejected (potential ReDoS)")
        return None
    try:
        return _re.compile(pattern, flags=_re.DOTALL)
    except _re.error as e:
        _logger.warning("CQL regex compilation failed: %s", e)
        return None


def cqlRegexMatches(s: str | None, pattern: str | None) -> bool | None:
    """CQL Matches() regex helper using partial, single-line matching."""
    if s is None or pattern is None:
        return None
    regex = _compile_cql_regex(pattern)
    if regex is None:
        return None
    return regex.search(s) is not None


def cqlRegexReplaceMatches(
    s: str | None,
    pattern: str | None,
    replacement: str | None,
) -> str | None:
    """CQL ReplaceMatches() regex helper with Java-style replacement text."""
    if s is None or pattern is None or replacement is None:
        return None
    regex = _compile_cql_regex(pattern)
    if regex is None:
        return None
    python_replacement = _cql_replacement_to_python(replacement)
    try:
        return regex.sub(python_replacement, s)
    except _re.error as e:
        _logger.warning("CQL regex replacement failed: %s", e)
        return None


def cqlRegexSplitOnMatches(s: str | None, pattern: str | None) -> list[str] | None:
    """CQL SplitOnMatches() regex helper using Matches() regex semantics."""
    if s is None or pattern is None:
        return None
    if pattern == "":
        return list(s)
    regex = _compile_cql_regex(pattern)
    if regex is None:
        return None
    return regex.split(s)


def _cql_replacement_to_python(replacement: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(replacement):
        ch = replacement[i]
        if ch == "\\" and i + 1 < len(replacement):
            nxt = replacement[i + 1]
            if nxt == "$":
                result.append("$")
            elif nxt == "\\":
                result.append("\\\\")
            else:
                result.append("\\")
                result.append(nxt)
            i += 2
            continue
        if ch == "$" and i + 1 < len(replacement) and replacement[i + 1].isdigit():
            result.append("\\")
            result.append(replacement[i + 1])
            i += 2
            continue
        if ch == "\\":
            result.append("\\\\")
        else:
            result.append(ch)
        i += 1
    return "".join(result)


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
        if start is None or start < 0 or start >= len(s):
            return None
        if length is not None and length < 0:
            return None
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
    if s is None or prefix is None:
        return None
    return s.startswith(prefix)


def stringEndsWith(s: str | None, suffix: str) -> bool | None:
    """CQL EndsWith(s, suffix)."""
    if s is None or suffix is None:
        return None
    return s.endswith(suffix)


def stringContains(s: str | None, substring: str) -> bool | None:
    """CQL Contains(s, substring)."""
    if s is None or substring is None:
        return None
    return substring in s


def stringMatches(s: str | None, pattern: str) -> bool | None:
    """CQL Matches(s, pattern) - regex match."""
    return cqlRegexMatches(s, pattern)


def stringReplace(s: str | None, old: str, new: str) -> str | None:
    """CQL Replace(s, old, new)."""
    if s is None or old is None or new is None:
        return None
    return s.replace(old, new)


def registerStringUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all string UDFs."""
    def _create(name: str, fn, **kwargs) -> None:
        try:
            con.create_function(name, fn, null_handling="special", **kwargs)
        except Exception:
            _logger.debug("Skipping string UDF %s during registration", name)

    _create("cqlRegexMatches", cqlRegexMatches)
    _create("cqlRegexReplaceMatches", cqlRegexReplaceMatches)
    _create("cqlRegexSplitOnMatches", cqlRegexSplitOnMatches, return_type="VARCHAR[]")
    _create("stringLength", stringLength)
    _create("stringLower", stringLower)
    _create("stringUpper", stringUpper)
    _create("stringSubstring", stringSubstring)
    _create("stringConcatenate", stringConcatenate)
    # stringSplit returns a list - DuckDB needs explicit type
    _create("stringSplit", stringSplit, return_type="VARCHAR")
    _create("stringPositionOf", stringPositionOf)
    _create("stringStartsWith", stringStartsWith)
    _create("stringEndsWith", stringEndsWith)
    _create("stringContains", stringContains)
    _create("stringMatches", stringMatches)
    _create("stringReplace", stringReplace)


def registerRegexStringUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register regex UDFs needed by Tier 1 string macros."""
    def _create(name: str, fn, **kwargs) -> None:
        try:
            con.create_function(name, fn, null_handling="special", **kwargs)
        except Exception:
            _logger.debug("Skipping regex string UDF %s during registration", name)

    _create("cqlRegexMatches", cqlRegexMatches)
    _create("cqlRegexReplaceMatches", cqlRegexReplaceMatches)
    _create("cqlRegexSplitOnMatches", cqlRegexSplitOnMatches, return_type="VARCHAR[]")


__all__ = [
    "stringLength", "stringLower", "stringUpper", "stringSubstring",
    "stringConcatenate", "stringSplit", "stringPositionOf",
    "stringStartsWith", "stringEndsWith", "stringContains",
    "stringMatches", "stringReplace", "registerStringUdfs", "registerRegexStringUdfs",
    "cqlRegexMatches", "cqlRegexReplaceMatches", "cqlRegexSplitOnMatches",
]
