"""CQL list operator part 1 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, DistinctExpression, ExistsExpression, FunctionRef
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_list_part1_expressions_parse_and_translate() -> None:
    assert isinstance(parse_expression("distinct {1,2,2}"), DistinctExpression)
    assert isinstance(parse_expression("exists {1}"), ExistsExpression)
    assert isinstance(parse_expression("flatten {{1,2},{3}}"), FunctionRef)
    assert isinstance(parse_expression("First({1,2})"), FunctionRef)
    assert isinstance(parse_expression("IndexOf({1,2,3},2)"), FunctionRef)

    for expression in [
        "{1,2,3} contains 2",
        "{1,2} = {1,2}",
        "{1,2} ~ {1,2}",
        "{1,2,3} except {2}",
        "2 in {1,2,3}",
        "{1,2,3} includes 2",
        "2 included in {1,2,3}",
        "{1,2,3} intersect {2,3,4}",
    ]:
        assert isinstance(parse_expression(expression), BinaryExpression)

    translated = translate_cql(_cql_list_part1_library())
    assert "list_contains" in str(translated["ContainsList"])
    assert "Distinct" in str(translated["DistinctList"])
    assert "=" in translated["EqualList"].to_sql()
    assert "CASE" in translated["EquivalentList"].to_sql()
    assert "list_filter" in str(translated["ExceptList"])
    assert "list_count" in str(translated["ExistsList"])
    assert "flatten" in str(translated["FlattenList"])
    assert "LIST_EXTRACT" in translated["FirstList"].to_sql()
    assert "array_contains" in str(translated["InList"])
    assert "list_contains" in str(translated["IncludesList"])
    assert "list_contains" in str(translated["IncludedInList"])
    assert "CQLIndexOf" in str(translated["IndexOfList"])
    assert "list_intersect" in str(translated["IntersectList"])


def test_cql_list_part1_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_list_part1_library())
    expected = {
        "ContainsList": (True,),
        "DistinctList": ([1, 2],),
        "EqualList": (True,),
        "EquivalentList": (True,),
        "ExceptList": ([1, 3],),
        "ExistsList": (True,),
        "FlattenList": ([1, 2, 3],),
        "FirstList": (1,),
        "InList": (True,),
        "IncludesList": (True,),
        "IncludedInList": (True,),
        "IndexOfList": (1,),
        "IntersectList": ([2, 3],),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT First([1, 2, 3])", (1,)),
        ('SELECT "Distinct"([1, 2, 2])', ([1, 2],)),
        ("SELECT CQLIndexOf([1, 2, 3], 2)", (1,)),
        ("SELECT SingletonFrom(['only'])", ("only",)),
        ("SELECT ElementAt(['a', 'b', 'c'], 1)", ("b",)),
        ("SELECT jsonConcat(['a'], ['b'])", (["a", "b"],)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in cases:
            assert py.execute(sql).fetchone() == expected
            assert cpp.execute(sql).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def _cql_list_part1_library() -> str:
    return """library List1 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ContainsList: {1,2,3} contains 2
define DistinctList: distinct {1,2,2}
define EqualList: {1,2} = {1,2}
define EquivalentList: {1,2} ~ {1,2}
define ExceptList: {1,2,3} except {2}
define ExistsList: exists {1}
define FlattenList: flatten {{1,2},{3}}
define FirstList: First({1,2})
define InList: 2 in {1,2,3}
define IncludesList: {1,2,3} includes 2
define IncludedInList: 2 included in {1,2,3}
define IndexOfList: IndexOf({1,2,3},2)
define IntersectList: {1,2,3} intersect {2,3,4}
"""
