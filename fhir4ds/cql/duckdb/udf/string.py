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

from ...errors import UnsupportedFeatureError

_logger = logging.getLogger(__name__)

# Maximum regex pattern length to accept (guard against excessively large patterns)
_MAX_REGEX_LENGTH = 1000

# Patterns indicative of catastrophic backtracking (ReDoS).
# Detects nested quantifiers like (a+)+ and quantified alternations like (a|a)+.
_REDOS_PATTERNS = _re.compile(
    r'(\((?:[^()]*[+*])[^()]*\)[+*?]'  # nested quantifier
    r'|\((?:[^()]*\|[^()]*)\)[+*])'     # quantified alternation
)


class CQLRegexPatternRejected(UnsupportedFeatureError):
    """Raised when a CQL regex pattern is rejected by the ReDoS guard.

    Aligned with CQL §17 (Matches / ReplaceMatches / SplitOnMatches): the spec
    only authorizes a null result when an input argument is null. Returning
    null for a syntactically valid pattern would silently mask the rejection
    as a null-input result; instead, raise a typed error so the rejection is
    visible to callers and downstream boolean logic does not propagate a
    misleading null.
    """


def _compile_cql_regex(pattern: str) -> _re.Pattern:
    """Compile a CQL regex pattern.

    Raises:
        CQLRegexPatternRejected: if the pattern is rejected by the ReDoS guard
            or exceeds the maximum accepted length.
        re.error: if the pattern is syntactically invalid.
    """
    if len(pattern) > _MAX_REGEX_LENGTH:
        raise CQLRegexPatternRejected(
            message=(
                f"CQL regex pattern exceeds maximum supported length "
                f"({_MAX_REGEX_LENGTH} characters)"
            ),
            feature_name="Matches",
        )
    if _REDOS_PATTERNS.search(pattern):
        raise CQLRegexPatternRejected(
            message=(
                "CQL regex pattern rejected (potential ReDoS); rewrite without "
                "nested quantifiers or quantified alternations"
            ),
            feature_name="Matches",
        )
    return _re.compile(pattern, flags=_re.DOTALL)


def cqlRegexMatches(s: str | None, pattern: str | None) -> bool | None:
    """CQL Matches() regex helper using partial, single-line matching.

    Returns None only when an input argument is null (per CQL §17). Raises
    CQLRegexPatternRejected when the pattern is rejected by the ReDoS guard
    so the rejection is visible rather than masked as a null-input result.
    """
    if s is None or pattern is None:
        return None
    regex = _compile_cql_regex(pattern)
    return regex.search(s) is not None


def cqlRegexReplaceMatches(
    s: str | None,
    pattern: str | None,
    replacement: str | None,
) -> str | None:
    """CQL ReplaceMatches() regex helper with Java-style replacement text.

    Returns None only when an input argument is null (per CQL §17). Raises
    CQLRegexPatternRejected when the pattern is rejected by the ReDoS guard
    or when the substitution references a group that the pattern does not
    capture. Per CQL §17 ReplaceMatches: "If any argument is null, the
    result is null." Returning None for a syntactically valid pattern with
    a bad backreference would silently mask the rejection as a null-input
    result and propagate misleadingly through downstream boolean logic.
    """
    if s is None or pattern is None or replacement is None:
        return None
    regex = _compile_cql_regex(pattern)
    python_replacement = _cql_replacement_to_python(replacement)
    try:
        return regex.sub(python_replacement, s)
    except _re.error as e:
        # re.error here means the substitution string references a group
        # that the pattern does not capture (e.g. '$1' with pattern 'a'
        # that has no capture group). Per CQL §17, None is authorized
        # only when an input argument is null. Raise a typed error so the
        # rejection is visible rather than masked as a null-input result.
        raise CQLRegexPatternRejected(
            message=(
                f"CQL ReplaceMatches substitution is invalid: {e}"
            ),
            feature_name="ReplaceMatches",
        ) from e


def cqlRegexSplitOnMatches(s: str | None, pattern: str | None) -> list[str] | None:
    """CQL SplitOnMatches() regex helper using Matches() regex semantics.

    Returns None only when an input argument is null (per CQL §17). Raises
    CQLRegexPatternRejected when the pattern is rejected by the ReDoS guard.
    """
    if s is None or pattern is None:
        return None
    if pattern == "":
        return list(s)
    regex = _compile_cql_regex(pattern)
    parts = regex.split(s)
    if regex.groups:
        # Python re.split interleaves capture-group values into the split
        # result (e.g. 'a1b2'.split(r'(\d)') -> ['a','1','b','2','']).
        # CQL SplitOnMatches (Appendix B) has no group-inclusion clause and
        # the reference engine uses Java Pattern.split semantics, which
        # exclude capture groups. Keep only the separator-delimited
        # segments: with N groups the segments sit at indices
        # 0, N+1, 2(N+1), ... (matches the native C++ extension).
        parts = parts[:: regex.groups + 1]
    return parts


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
