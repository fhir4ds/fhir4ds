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
    """CQL AllTrue(list) — true iff no non-null element is false.

    Per CQL §22.1: nulls are ignored. If all non-null elements are true
    (or there are no non-null elements), returns true.
    Null argument is treated as empty list → true.
    """
    if values is None or len(values) == 0:
        return True
    for v in values:
        if v is False:
            return False
    return True


def logicalAnyTrue(values: List[bool | None] | None) -> bool | None:
    """CQL AnyTrue(list) — true iff any non-null element is true.

    Per CQL §22.2: nulls are ignored. If any non-null element is true,
    returns true. If no non-null elements, returns false.
    Null argument is treated as empty list → false.
    """
    if values is None or len(values) == 0:
        return False
    for v in values:
        if v is True:
            return True
    return False


def logicalAllFalse(values: List[bool | None] | None) -> bool | None:
    """CQL AllFalse(list) — true iff no non-null element is true.

    Per CQL §22.3: nulls are ignored. If all non-null elements are false
    (or there are no non-null elements), returns true.
    Null argument is treated as empty list → true.
    """
    if values is None or len(values) == 0:
        return True
    for v in values:
        if v is True:
            return False
    return True


def logicalAnyFalse(values: List[bool | None] | None) -> bool | None:
    """CQL AnyFalse(list) — true iff any non-null element is false.

    Per CQL §22.4: nulls are ignored. If any non-null element is false,
    returns true. If no non-null elements, returns false.
    Null argument is treated as empty list → false.
    """
    if values is None or len(values) == 0:
        return False
    for v in values:
        if v is False:
            return True
    return False


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
