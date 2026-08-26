"""Profile-conformance validation for SQLQuery / SQLView Libraries.

Centralizes the structural invariants from the SQL-on-FHIR v2 Analytics
Layer profiles so parser and direct-dataclass construction paths share
the same guards.
"""

from __future__ import annotations

import re
from typing import Iterable

from .errors import SQLQueryValidationError, UnsupportedDialectError
from .types import (
    SQLQUERY_LIBRARY_TYPE_CODE,
    SQLQUERY_PROFILE_CANONICALS,
    SQLVIEW_PROFILE_CANONICALS,
    SUPPORTED_CONTENT_TYPES,
    SQLContent,
    SQLView,
    _SQLLibraryBase,
)

# sql-on-fhir-v2 models.fsh Invariant sql-name (ASCII-only regex).
SQL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_sql_library(library: _SQLLibraryBase, *, strict: bool = True) -> list[str]:
    """Validate a parsed SQLQuery or SQLView against its profile.

    Args:
        library: A :class:`SQLQuery` or :class:`SQLView` instance.
        strict: When ``True`` (default), raise on the first violation.
            When ``False``, collect violations into a returned list and
            do not raise — useful for permissive "lint" callers.

    Returns:
        List of violation messages. Empty when the library is valid.

    Raises:
        SQLQueryValidationError: when ``strict`` is True and any
            violation is found.
    """
    violations: list[str] = []
    is_sql_view = isinstance(library, SQLView)

    # Profile declaration: meta.profile must contain the expected canonical.
    # The parser already routes through this; we re-check for direct
    # dataclass construction.
    # (Delegated to the parser-side profile detection; here we trust the
    # caller used the right dataclass.)

    # Library type code is enforced at parse time (Library.type.coding).
    # We don't have direct access to it here; the parser asserts it.

    # content 1..* with each contentType starting with application/sql
    if not library.content:
        violations.append(
            f"{'SQLView' if is_sql_view else 'SQLQuery'} must declare at least one "
            f"content[] entry (cardinality 1..*)"
        )
    for i, content in enumerate(library.content):
        if not isinstance(content, SQLContent):
            violations.append(f"content[{i}] must be a SQLContent instance")
            continue
        if not content.content_type.startswith("application/sql"):
            violations.append(
                f"content[{i}].contentType {content.content_type!r} violates "
                f"sql-must-be-sql-expressions: must start with 'application/sql'"
            )

    # relatedArtifact MS — each label must be non-empty and satisfy sql-name.
    for i, ra in enumerate(library.related_artifact):
        if not ra.label or not SQL_NAME_PATTERN.fullmatch(ra.label):
            violations.append(
                f"relatedArtifact[{i}].label {ra.label!r} must satisfy sql-name "
                f"^[A-Za-z][A-Za-z0-9_]*$"
            )
        if not ra.resource:
            violations.append(
                f"relatedArtifact[{i}].resource must be a non-empty canonical"
            )

    # parameter forbidden on SQLView
    if is_sql_view and getattr(library, "parameter", None):
        violations.append(
            "SQLView forbids parameter (cardinality 0..0); use SQLQuery instead"
        )

    if not is_sql_view:
        # SQLQuery parameter shape: each must have name + type + use="in"
        for i, param in enumerate(getattr(library, "parameter", []) or []):
            if not param.name or not SQL_NAME_PATTERN.fullmatch(param.name):
                violations.append(
                    f"parameter[{i}].name {param.name!r} must satisfy sql-name "
                    f"^[A-Za-z][A-Za-z0-9_]*$ (it is bound as a DuckDB named "
                    f"parameter token)"
                )
            if not param.type:
                violations.append(f"parameter[{i}].type must be non-empty")
            if param.use != "in":
                violations.append(
                    f"parameter[{i}].use must be 'in' (got {param.use!r})"
                )

    if strict and violations:
        raise SQLQueryValidationError(
            f"{'SQLView' if is_sql_view else 'SQLQuery'} validation failed: "
            + "; ".join(violations)
        )
    return violations


def select_best_content(content_entries: Iterable[SQLContent]) -> SQLContent:
    """Pick the most-specific supported content type from ``content[]``.

    Preference order: ``application/sql;dialect=duckdb`` > ``application/sql``.
    Other dialects are rejected with :class:`UnsupportedDialectError`.

    Raises:
        SQLQueryValidationError: when no content entry exists.
        UnsupportedDialectError: when content entries exist but none match
            a supported dialect.
    """
    entries = list(content_entries)
    if not entries:
        raise SQLQueryValidationError("No content[] entries to select from")

    for supported in SUPPORTED_CONTENT_TYPES:
        for entry in entries:
            if entry.content_type == supported:
                return entry

    raise UnsupportedDialectError(
        f"No supported DuckDB dialect in content[].contentType values: "
        f"{[e.content_type for e in entries]!r}. Supported: "
        f"{list(SUPPORTED_CONTENT_TYPES)}"
    )


__all__ = [
    "validate_sql_library",
    "select_best_content",
    "SQLQUERY_PROFILE_CANONICALS",
    "SQLVIEW_PROFILE_CANONICALS",
    "SQLQUERY_LIBRARY_TYPE_CODE",
    "SQL_NAME_PATTERN",
]
