"""CQL logical operator truth-table parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_logical_truth_tables_match_cpp_registration() -> None:
    values = ["true", "false", "NULL"]
    expressions = []
    for left in values:
        for right in values:
            expressions.extend(
                [
                    f'SELECT "And"({left}, {right})',
                    f'SELECT "Or"({left}, {right})',
                    f'SELECT "Xor"({left}, {right})',
                    f'SELECT "Implies"({left}, {right})',
                    f"SELECT logicalImplies({left}, {right})",
                ]
            )
    for value in values:
        expressions.append(f'SELECT "Not"({value})')

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
