"""CQL structural type operator parser/translator and DuckDB parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_structural_type_expressions_parse_and_translate() -> None:
    is_expr = parse_expression("true is Boolean")
    as_expr = parse_expression("true as Boolean")
    convert_expr = parse_expression("convert '5' to Integer")
    children_expr = parse_expression("Children({ a: 1 })")
    descendants_expr = parse_expression("Descendants({ a: { b: 1 } })")

    assert isinstance(is_expr, BinaryExpression)
    assert is_expr.operator == "is"
    assert isinstance(as_expr, BinaryExpression)
    assert as_expr.operator == "as"
    assert isinstance(convert_expr, BinaryExpression)
    assert convert_expr.operator == "convert"
    assert isinstance(children_expr, FunctionRef)
    assert children_expr.name == "Children"
    assert isinstance(descendants_expr, FunctionRef)
    assert descendants_expr.name == "Descendants"

    cql = """library Structural version '1.0.0'
using FHIR version '4.0.1'
context Patient
define IsBool: true is Boolean
define AsBool: true as Boolean
define Converted: convert '5' to Integer
"""
    translated = translate_cql(cql)
    assert set(translated) == {"IsBool", "AsBool", "Converted"}
    assert "typeof" in str(translated["IsBool"])
    assert "value=True" in str(translated["AsBool"])
    assert "target_type='INTEGER'" in str(translated["Converted"])


def test_cql_structural_duckdb_surface_matches_cpp_registration() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "flag": True,
            "count": 42,
            "name": [{"family": "Smith", "given": ["Ann"]}],
            "nested": {"a": {"b": 1}},
            "nullable": None,
        }
    )
    expressions = [
        ("SELECT fhirpath_bool(?::JSON, 'flag.is(FHIR.boolean)')", [resource]),
        ("SELECT fhirpath_bool(?::JSON, 'flag.is(System.Boolean)')", [resource]),
        ("SELECT fhirpath_text(?::JSON, 'count.as(integer)')", [resource]),
        ("SELECT fhirpath_text(?::JSON, 'name.as(HumanName).family')", [resource]),
        ("SELECT fhirpath_number(?::JSON, 'children().count()')", [resource]),
        ("SELECT fhirpath_number(?::JSON, 'descendants().count()')", [resource]),
        ("SELECT fhirpath_json(?::JSON, 'name.children()')", [resource]),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, params in expressions:
            assert cpp.execute(sql, params).fetchone() == py.execute(sql, params).fetchone()
    finally:
        py.close()
        cpp.close()
