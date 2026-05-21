"""
CQL Logical Function UDFs

Most logical operators are implemented as SQL macros in macros/logical.py for
zero Python overhead. Coalesce is kept here because CQL exposes variadic and
single-list overloads that cannot be represented by one type-preserving DuckDB
macro.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Any

from duckdb import sqltypes

if TYPE_CHECKING:
    import duckdb


_COALESCE_RETURN_TYPE = getattr(sqltypes, "VARIANT", "VARCHAR")


def _coalesce_return_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def Coalesce(*args: Any) -> Any:
    """CQL Coalesce(a, b, ...) and Coalesce(List<T>) - first non-null value."""
    if len(args) == 1 and isinstance(args[0], list):
        for value in args[0]:
            if value is not None:
                return _coalesce_return_value(value)
        return None
    for arg in args:
        if arg is not None:
            return _coalesce_return_value(arg)
    return None


def logicalCoalesce(*args: Any) -> Any:
    """CQL Coalesce(a, b, ...) - first non-null value."""
    if len(args) == 1 and isinstance(args[0], str):
        text = args[0].strip()
        if text.startswith("["):
            try:
                values = json.loads(text)
                if isinstance(values, list):
                    for value in values:
                        if value is not None:
                            if isinstance(value, bool):
                                return "true" if value else "false"
                            if isinstance(value, (dict, list)):
                                return json.dumps(value, separators=(",", ":"))
                            return str(value)
                    return None
            except (TypeError, ValueError):
                pass
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


def _parse_bool_list(values: List[bool | None] | str | None) -> List[bool | None] | None:
    if isinstance(values, str):
        text = values.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return parsed
            except (TypeError, ValueError):
                return None
    return values


def logicalAllTrue(values: List[bool | None] | None) -> bool | None:
    """CQL AllTrue(list) — true iff no non-null element is false.

    Per CQL §22.1: nulls are ignored. If all non-null elements are true
    (or there are no non-null elements), returns true.
    Null argument is treated as empty list → true.
    """
    values = _parse_bool_list(values)
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
    values = _parse_bool_list(values)
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
    values = _parse_bool_list(values)
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
    values = _parse_bool_list(values)
    if values is None or len(values) == 0:
        return False
    for v in values:
        if v is False:
            return True
    return False


def registerLogicalUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register all logical UDFs."""
    # Coalesce is variadic and type-preserving on DuckDB versions that expose
    # VARIANT. Older unsupported DuckDB fallback probes lack VARIANT, so use
    # VARCHAR there to keep registration and representative fallback UDFs alive.
    con.create_function("Coalesce", Coalesce, return_type=_COALESCE_RETURN_TYPE, null_handling="special")
    # logicalCoalesce is the legacy string-returning JSON-list helper.
    con.create_function("logicalCoalesce", logicalCoalesce, return_type="VARCHAR", null_handling="special")
    con.create_function("logicalImplies", logicalImplies, null_handling="special")
    # These list-returning functions need explicit types
    con.create_function("logicalAllTrue", logicalAllTrue, return_type="BOOLEAN", null_handling="special")
    con.create_function("logicalAnyTrue", logicalAnyTrue, return_type="BOOLEAN", null_handling="special")
    con.create_function("logicalAllFalse", logicalAllFalse, return_type="BOOLEAN", null_handling="special")
    con.create_function("logicalAnyFalse", logicalAnyFalse, return_type="BOOLEAN", null_handling="special")


__all__ = [
    "Coalesce", "logicalCoalesce", "logicalImplies",
    "logicalAllTrue", "logicalAnyTrue",
    "logicalAllFalse", "logicalAnyFalse",
    "registerLogicalUdfs",
]
