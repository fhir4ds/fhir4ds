"""
Error categorizer: normalizes ParseResult failures into construct categories
for frequency analysis and fix prioritization.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from .scanner import ParseResult


# Regex patterns to extract construct key from error messages.
# Applied in order; first match wins.
_CONSTRUCT_PATTERNS = [
    # "Unexpected token 'X'" or "Unexpected token X"
    (re.compile(r"[Uu]nexpected token ['\"]?(\S+?)['\"]?(?:\s|$)"), "token:{0}"),
    # "Expected X, found Y" — capture the found token
    (re.compile(r"[Ff]ound ['\"]?(\S+?)['\"]?(?:\s|$)"), "token:{0}"),
    # "Expected X but got Y"
    (re.compile(r"but got ['\"]?(\S+?)['\"]?(?:\s|$)"), "token:{0}"),
    # "Unexpected keyword 'X'"
    (re.compile(r"[Uu]nexpected keyword ['\"]?(\S+?)['\"]?(?:\s|$)"), "keyword:{0}"),
]


@dataclass
class ConstructCategory:
    """Aggregated information about one type of parse failure."""
    key: str                   # e.g. "token:occurs", "unsupported:timing_operator"
    error_type: str            # e.g. "ParseError", "LexerError"
    label: str                 # Human-readable label
    affected_files: List[str] = field(default_factory=list)
    sample_messages: List[str] = field(default_factory=list)
    sample_positions: List[tuple] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.affected_files)

    @property
    def library_count(self) -> int:
        """How many of the affected files are shared libraries (not measure CQLs)."""
        return sum(
            1 for f in self.affected_files
            if not (f.startswith("CMS") or f.startswith("NHSN"))
        )

    @property
    def measure_count(self) -> int:
        return self.count - self.library_count


def _extract_construct_key(result: ParseResult) -> str:
    """
    Derive a stable, normalized category key from a ParseResult.

    Priority:
    1. UnsupportedFeatureError.feature_name (already structured)
    2. ParseError.found field (already extracted by the parser)
    3. Regex match against the error message
    4. Fallback to sanitized error_type:message prefix
    """
    if result.error_type == "UnsupportedFeatureError" and result.feature_name:
        return f"unsupported:{result.feature_name.lower().replace(' ', '_')}"

    if result.error_type == "RecursionError":
        return "recursion:depth_exceeded"

    if result.error_type == "LexerError":
        # Normalize lexer errors by their first significant token
        for pattern, template in _CONSTRUCT_PATTERNS:
            m = pattern.search(result.message or "")
            if m:
                return "lexer:" + template.format(*m.groups())
        return f"lexer:{_sanitize(result.message or 'unknown')[:40]}"

    # ParseError: prefer the structured `found` field
    if result.found:
        token = result.found.strip("'\"").lower()
        return f"token:{token}"

    # Fall back to regex on message
    for pattern, template in _CONSTRUCT_PATTERNS:
        m = pattern.search(result.message or "")
        if m:
            raw = m.group(1).strip("'\"").lower()
            key_part = template.split(":")[0]
            return f"{key_part}:{raw}"

    # Last resort: sanitized message prefix
    return f"other:{_sanitize(result.message or 'unknown')[:40]}"


def _sanitize(s: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", s.lower())


def _make_label(key: str, result: ParseResult) -> str:
    """Human-readable label for a category key."""
    prefix, _, value = key.partition(":")
    if prefix == "token":
        return f"Unexpected token '{value}'"
    if prefix == "keyword":
        return f"Unexpected keyword '{value}'"
    if prefix == "unsupported":
        return f"Unsupported feature: {value.replace('_', ' ')}"
    if prefix == "lexer":
        return f"Lexer error: {value}"
    if prefix == "recursion":
        return "Recursion depth exceeded"
    return result.message or key


def categorize(results: List[ParseResult]) -> List[ConstructCategory]:
    """
    Group failed ParseResults by construct category.

    Returns categories sorted by descending file count (highest impact first).
    """
    categories: Dict[str, ConstructCategory] = {}

    for result in results:
        if result.success:
            continue

        key = _extract_construct_key(result)

        if key not in categories:
            categories[key] = ConstructCategory(
                key=key,
                error_type=result.error_type or "Unknown",
                label=_make_label(key, result),
            )

        cat = categories[key]
        filename = result.file.name
        if filename not in cat.affected_files:
            cat.affected_files.append(filename)

        if len(cat.sample_messages) < 3 and result.message:
            msg = result.message.split("\n")[0]  # first line only
            if msg not in cat.sample_messages:
                cat.sample_messages.append(msg)

        if result.position and result.position not in cat.sample_positions:
            cat.sample_positions.append(result.position)

    return sorted(categories.values(), key=lambda c: c.count, reverse=True)
