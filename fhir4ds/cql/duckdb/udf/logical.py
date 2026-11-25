"""
CQL Logical Function UDFs

Most logical operators are implemented as SQL macros in macros/logical.py for
zero Python overhead. Coalesce is kept here because CQL exposes a two-to-five
scalar overload family plus a single-list overload that cannot be represented
by one type-preserving DuckDB macro.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Any

import duckdb

try:
    from duckdb import sqltypes
except ImportError:  # pragma: no cover
    # The Pyodide/WASM duckdb build does not ship the ``sqltypes`` module.
    # The browser path is translation-only (UDFs are never registered), so a
    # None placeholder keeps the module importable there (viewing-room boot).
    sqltypes = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import duckdb


_COALESCE_RETURN_TYPE = "VARCHAR" if sqltypes is None else getattr(sqltypes, "VARIANT", "VARCHAR")

# CQL §Coalesce: four scalar signatures (2..5 arguments) plus one unbounded
# List<T> signature. "More than 5 inputs must be represented as list"
# (FHIR4-44) — see Coalesce() below. Lockstep: the translator enforces the
# same cap in `_functions.py::_validate_coalesce_scalar_arity`; the C++
# extension registers only the legacy `logicalCoalesce`, so this UDF is the
# authority on BOTH connections.
_COALESCE_MAX_SCALAR_ARITY = 5


def _coalesce_return_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool) and _COALESCE_RETURN_TYPE != "VARCHAR" and hasattr(duckdb, "Value"):
        return duckdb.Value(value, _COALESCE_RETURN_TYPE)
    return value


def Coalesce(*args: Any) -> Any:
    """CQL Coalesce(a, b, ...) and Coalesce(List<T>) - first non-null value.

    CQL §Coalesce declares four scalar overloads (2, 3, 4 and 5 arguments)
    plus ONE unbounded ``Coalesce<T>(arguments List<T>) T``; the spec's own
    example — ``Coalesce(null, 15, null, null, null, null) // more than 5
    inputs must be represented as list`` — makes a sixth SCALAR argument an
    error. The list overload has no upper bound (FHIR4-44).
    """
    if len(args) == 1 and isinstance(args[0], list):
        for value in args[0]:
            if value is not None:
                return _coalesce_return_value(value)
        return None
    if len(args) < 2:
        raise ValueError(
            "Coalesce scalar overload requires 2 or more arguments; "
            "use Coalesce([ ... ]) for list input"
        )
    if len(args) > _COALESCE_MAX_SCALAR_ARITY:
        raise ValueError(
            f"Coalesce has no scalar overload with more than 5 inputs "
            f"(got {len(args)}): 2..5 scalar arguments plus a single list "
            "argument are defined — represent more than 5 inputs as a list"
        )
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
    def _create(name: str, fn: Any, **kwargs: Any) -> None:
        try:
            con.create_function(name, fn, **kwargs)
        except (duckdb.CatalogException, duckdb.InvalidInputException, duckdb.NotImplementedException):
            # SQL macros or the native extension may already provide the public
            # name. Keep registering the rest of the logical surface.
            return

    # Coalesce is variadic and type-preserving on DuckDB versions that expose
    # VARIANT. Older unsupported DuckDB fallback probes lack VARIANT, so use
    # VARCHAR there to keep registration and representative fallback UDFs alive.
    _create("Coalesce", Coalesce, return_type=_COALESCE_RETURN_TYPE, null_handling="special")
    # logicalCoalesce is the legacy string-returning JSON-list helper.
    _create("logicalCoalesce", logicalCoalesce, return_type="VARCHAR", null_handling="special")
    _create("logicalImplies", logicalImplies, null_handling="special")
    # These list-returning functions need explicit types
    _create("logicalAllTrue", logicalAllTrue, return_type="BOOLEAN", null_handling="special")
    _create("logicalAnyTrue", logicalAnyTrue, return_type="BOOLEAN", null_handling="special")
    _create("logicalAllFalse", logicalAllFalse, return_type="BOOLEAN", null_handling="special")
    _create("logicalAnyFalse", logicalAnyFalse, return_type="BOOLEAN", null_handling="special")


__all__ = [
    "Coalesce", "logicalCoalesce", "logicalImplies",
    "logicalAllTrue", "logicalAnyTrue",
    "logicalAllFalse", "logicalAnyFalse",
    "registerLogicalUdfs",
]
