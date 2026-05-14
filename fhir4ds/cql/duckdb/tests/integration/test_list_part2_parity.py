"""CQL list operator part 2 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef, UnaryExpression
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_list_part2_expressions_parse_and_translate() -> None:
    for expression in ["Last({1,2,3})", "Length({1,2,3})", "Skip({1,2,3},1)", "Tail({1,2,3})", "Take({1,2,3},2)"]:
        assert isinstance(parse_expression(expression), FunctionRef)
    assert isinstance(parse_expression("singleton from {1}"), UnaryExpression)

    for expression in [
        "{1,2} != {1,3}",
        "{1,2} !~ {1,3}",
        "{1,2,3} properly includes 2",
        "2 properly included in {1,2,3}",
        "{1,2} union {2,3}",
    ]:
        assert isinstance(parse_expression(expression), BinaryExpression)

    translated = translate_cql(_cql_list_part2_library())
    assert "LIST_EXTRACT" in translated["LastList"].to_sql()
    assert "array_length" in translated["LengthList"].to_sql()
    assert "!=" in translated["NotEqualList"].to_sql()
    assert "NOT CASE" in translated["NotEquivalentList"].to_sql()
    assert "list_contains" in str(translated["ProperIncludesList"])
    assert "list_contains" in str(translated["ProperIncludedInList"])
    assert "LIST_EXTRACT" in translated["SingletonList"].to_sql()
    assert "Skip" in str(translated["SkipList"])
    assert "Tail" in str(translated["TailList"])
    assert "Take" in str(translated["TakeList"])
    assert "list_concat" in str(translated["UnionList"])


def test_cql_list_part2_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_list_part2_library())
    expected = {
        "LastList": (3,),
        "LengthList": (3,),
        "NotEqualList": (True,),
        "NotEquivalentList": (True,),
        "ProperIncludesList": (True,),
        "ProperIncludedInList": (True,),
        "SingletonList": (1,),
        "SkipList": ([2, 3],),
        "TailList": ([2, 3],),
        "TakeList": ([1, 2],),
        "UnionList": ([1, 2, 3],),
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


def test_cql_list_part2_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT Last([1, 2, 3])", (3,)),
        ("SELECT COALESCE(array_length([1, 2, 3]), 0)", (3,)),
        ("SELECT Skip([1, 2, 3], 1)", ([2, 3],)),
        ("SELECT Skip([1, 2, 3], 0)", ([1, 2, 3],)),
        ("SELECT Tail([1, 2, 3])", ([2, 3],)),
        ("SELECT Take([1, 2, 3], 2)", ([1, 2],)),
        ("SELECT Take([1, 2, 3], 0)", ([],)),
        ("SELECT SingletonFrom(['only'])", ("only",)),
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


def _cql_list_part2_library() -> str:
    return """library List2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define LastList: Last({1,2,3})
define LengthList: Length({1,2,3})
define NotEqualList: {1,2} != {1,3}
define NotEquivalentList: {1,2} !~ {1,3}
define ProperIncludesList: {1,2,3} properly includes 2
define ProperIncludedInList: 2 properly included in {1,2,3}
define SingletonList: singleton from {1}
define SkipList: Skip({1,2,3},1)
define TailList: Tail({1,2,3})
define TakeList: Take({1,2,3},2)
define UnionList: {1,2} union {2,3}
"""
