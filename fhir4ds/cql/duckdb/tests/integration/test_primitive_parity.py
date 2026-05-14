"""CQL primitive type parity checks for Python and C++ DuckDB registration."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_primitive_literal_translation() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    cases = {
        "BooleanTrue": "true",
        "BooleanFalse": "false",
        "IntegerValue": "42",
        "LongValue": "42L",
        "DecimalValue": "1.25",
        "StringValue": "'hello'",
        "NullValue": "null",
    }

    cql = header + "\n".join(f"define {name}: {expr}" for name, expr in cases.items())
    translated = translate_cql(cql)

    assert set(cases) <= set(translated)
    assert "value=True" in str(translated["BooleanTrue"])
    assert "value=False" in str(translated["BooleanFalse"])
    assert "value=42" in str(translated["IntegerValue"])
    assert "value=42" in str(translated["LongValue"])
    assert "value=1.25" in str(translated["DecimalValue"])
    assert "value='hello'" in str(translated["StringValue"])
    assert "SQLNull" in str(translated["NullValue"])


def test_cql_primitive_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        'SELECT "And"(true, false)',
        'SELECT "Or"(true, false)',
        'SELECT "Not"(false)',
        'SELECT "Implies"(true, false)',
        'SELECT "IsTrue"(true)',
        'SELECT "IsFalse"(false)',
        "SELECT ToString(123)",
        "SELECT ToInteger('42')",
        "SELECT ToDecimal('1.25')",
        "SELECT ToBoolean('true')",
        "SELECT logicalImplies(true, false)",
        "SELECT logicalImplies(NULL, false)",
        "SELECT fhirpath_text('{\"resourceType\":\"Patient\",\"active\":true}'::JSON, 'active')",
        "SELECT fhirpath_number('{\"resourceType\":\"Observation\",\"valueInteger\":42}'::JSON, 'value')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
