"""
CQL Logical Function UDFs

DEPRECATED: These UDFs are superseded by Tier 1/2 SQL macros in macros/logical.py
which provide zero Python overhead. These are retained for backward compatibility
with code that references the logicalCoalesce/logicalImplies/etc. function names.
New code should use the SQL macro versions (Coalesce, Implies, etc.) instead.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, List, Any
import duckdb

if TYPE_CHECKING:
    import duckdb


def logicalCoalesce(*args: Any) -> Any:
    """CQL Coalesce(a, b, ...) - first non-null value."""
    for arg in args:
        if arg is not None:
            return arg
    return None


def logicalImplies(a: bool | None, b: bool | None) -> bool | None:
    """
    CQL Implies(a, b) - logical implication.

    Truth table (3-valued logic):
    a      b      result
    true   true   true
    true   false  false
    true   null   null
    false  *      true
    null   true   true
    null   false  null
    null   null   null
    """
    if a is False:
        return True
    if a is None:
        if b is True:
            return True
        return None
    # a is True
    return b


def logicalAllTrue(values: List[bool | None] | None) -> bool | None:
    """CQL AllTrue(list) - true if all are true (vacuous truth for empty)."""
    if values is None:
        return None
    if len(values) == 0:
        return True
    has_null = False
    for v in values:
        if v is False:
            return False
        if v is None:
            has_null = True
    return None if has_null else True


def logicalAnyTrue(values: List[bool | None] | None) -> bool | None:
    """CQL AnyTrue(list) - true if any is true (false for empty)."""
    if values is None:
        return None
    if len(values) == 0:
        return False
    has_null = False
    for v in values:
        if v is True:
            return True
        if v is None:
            has_null = True
    return None if has_null else False


def logicalAllFalse(values: List[bool | None] | None) -> bool | None:
    """CQL AllFalse(list) - true if all are false (vacuous truth for empty)."""
    if values is None:
        return None
    if len(values) == 0:
        return True
    has_null = False
    for v in values:
        if v is True:
            return False
        if v is None:
            has_null = True
    return None if has_null else True


def logicalAnyFalse(values: List[bool | None] | None) -> bool | None:
    """CQL AnyFalse(list) - true if any is false (false for empty)."""
    if values is None:
        return None
    if len(values) == 0:
        return False
    has_null = False
    for v in values:
        if v is False:
            return True
        if v is None:
            has_null = True
    return None if has_null else False


def registerLogicalUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all logical UDFs."""
    # logicalCoalesce needs explicit type due to variadic args
    con.create_function("logicalCoalesce", logicalCoalesce, return_type="VARCHAR", null_handling="special")
    con.create_function("logicalImplies", logicalImplies, null_handling="special")
    # These list-returning functions need explicit types
    con.create_function("logicalAllTrue", logicalAllTrue, return_type="BOOLEAN", null_handling="special")
    con.create_function("logicalAnyTrue", logicalAnyTrue, return_type="BOOLEAN", null_handling="special")
    con.create_function("logicalAllFalse", logicalAllFalse, return_type="BOOLEAN", null_handling="special")
    con.create_function("logicalAnyFalse", logicalAnyFalse, return_type="BOOLEAN", null_handling="special")


__all__ = [
    "logicalCoalesce", "logicalImplies",
    "logicalAllTrue", "logicalAnyTrue",
    "logicalAllFalse", "logicalAnyFalse",
    "registerLogicalUdfs",
]
