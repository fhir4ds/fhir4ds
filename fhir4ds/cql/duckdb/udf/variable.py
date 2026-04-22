"""
CQL Variable/Parameter UDFs

Implements runtime parameter access for CQL measures.

Note: Uses SQL macros to wrap Python UDFs because DuckDB's create_function
creates duplicate function signatures (ANY and explicit type) which causes
binder ambiguity errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    import duckdb


@dataclass
class _VariableStore:
    values: dict[str, str] = field(default_factory=dict)
    lock: RLock = field(default_factory=RLock)


_VARIABLE_STORES: "WeakKeyDictionary[duckdb.DuckDBPyConnection, _VariableStore]" = WeakKeyDictionary()
_VARIABLE_STORES_LOCK = RLock()
_DIRECT_VARIABLE_STORE = _VariableStore()


def _get_store(con: "duckdb.DuckDBPyConnection | None" = None) -> _VariableStore:
    """Get the variable store for a DuckDB connection or direct Python access."""
    if con is None:
        return _DIRECT_VARIABLE_STORE

    store = _VARIABLE_STORES.get(con)
    if store is None:
        with _VARIABLE_STORES_LOCK:
            store = _VARIABLE_STORES.get(con)
            if store is None:
                store = _VariableStore()
                _VARIABLE_STORES[con] = store
    return store


def clear_variables(con: "duckdb.DuckDBPyConnection | None" = None) -> None:
    """Clear stored variables for one connection or for all known stores."""
    if con is not None:
        store = _get_store(con)
        with store.lock:
            store.values.clear()
        return

    with _DIRECT_VARIABLE_STORE.lock:
        _DIRECT_VARIABLE_STORE.values.clear()

    for store in list(_VARIABLE_STORES.values()):
        with store.lock:
            store.values.clear()


def _setvariable_impl(store: _VariableStore, name: str | None, value: str | None) -> str:
    """Internal: Set a variable value in a specific store."""
    if name is None:
        return ""
    if value is None:
        value = ""
    with store.lock:
        store.values[name] = value
    return value


def _getvariable_impl(store: _VariableStore, name: str | None) -> str:
    """Internal: Get a variable value from a specific store."""
    if name is None:
        return ""
    with store.lock:
        return store.values.get(name, "")


def registerVariableUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """
    Register variable UDFs.

    Uses SQL macros to wrap Python UDFs to avoid DuckDB type binding issues.
    """
    store = _get_store(con)

    def _setvariable_udf(name: str | None, value: str | None) -> str:
        return _setvariable_impl(store, name, value)

    def _getvariable_udf(name: str | None) -> str:
        return _getvariable_impl(store, name)

    # Register internal Python functions (with _impl suffix to avoid conflicts)
    con.create_function("_setvariable_impl", _setvariable_udf, null_handling="special")
    con.create_function("_getvariable_impl", _getvariable_udf, null_handling="special")

    # Create SQL macros as the public API
    con.execute("CREATE OR REPLACE MACRO setvariable(name, value) AS _setvariable_impl(name, value)")
    con.execute("CREATE OR REPLACE MACRO getvariable(name) AS _getvariable_impl(name)")


# Public API for direct Python access
def setvariable(
    name: str,
    value: str,
    con: "duckdb.DuckDBPyConnection | None" = None,
) -> str:
    """Set a variable value for a DuckDB connection or direct Python access."""
    return _setvariable_impl(_get_store(con), name, value)


def getvariable(name: str, con: "duckdb.DuckDBPyConnection | None" = None) -> str:
    """Get a variable value for a DuckDB connection or direct Python access."""
    return _getvariable_impl(_get_store(con), name)
