"""CQL list operator part 2 parity checks."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef, UnaryExpression
from fhir4ds.cql.translator import translate_cql

from .wasm_runtime_helpers import no_python_connection


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
    assert "NOT CQLListEqualEq" in translated["NotEqualList"].to_sql()
    not_equiv_sql = translated["NotEquivalentList"].to_sql()
    assert "NOT" in not_equiv_sql
    assert "CASE" in not_equiv_sql
    assert "CQLListContainsEq" in str(translated["ProperIncludesList"])
    assert "CQLListContainsEq" in str(translated["ProperIncludedInList"])
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
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            no_py_result = no_py.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert no_py_result == py_result, name
            assert py_result == expected[name], name
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT Last([1, 2, 3])", (3,)),
        ("SELECT COALESCE(array_length([1, 2, 3]), 0)", (3,)),
        ("SELECT Skip([1, 2, 3], 1)", ([2, 3],)),
        ("SELECT Skip([1, 2, 3], 0)", ([1, 2, 3],)),
        ("SELECT Skip([1, 2, 3], NULL)", ([1, 2, 3],)),
        ("SELECT Skip([1, 2, 3], -1)", ([],)),
        ("SELECT Tail([1, 2, 3])", ([2, 3],)),
        ("SELECT Take([1, 2, 3], 2)", ([1, 2],)),
        ("SELECT Take([1, 2, 3], 0)", ([],)),
        ("SELECT SingletonFrom(['only'])", ("only",)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for sql, expected in cases:
            assert py.execute(sql).fetchone() == expected
            assert cpp.execute(sql).fetchone() == expected
            assert no_py.execute(sql).fetchone() == expected
        for con in (py, cpp, no_py):
            with pytest.raises(duckdb.InvalidInputException):
                con.execute("SELECT SingletonFrom(['one', 'two'])").fetchone()
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_edge_semantics_match_no_python_cpp() -> None:
    translated = translate_cql(_cql_list_part2_edge_library())
    expected = {
        "SkipNullCount": ([1, 3, 5],),
        "SkipNegativeCount": ([],),
        "ProperIncludesQuantity": (True,),
        "ProperIncludedInQuantity": (True,),
        "ProperIncludesQuantityList": (True,),
        "ProperIncludedInQuantityList": (True,),
        "ProperIncludesNullSingleton": (True,),
        "ProperIncludedInNullSingleton": (True,),
        "ProperIncludesNullLeft": (None,),
        "ProperIncludedInNullRight": (None,),
        "UnionNullLeft": ([4, 5],),
        "UnionNullBoth": ([],),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            no_py_result = no_py.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert no_py_result == py_result, name
            assert py_result == expected[name], name
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_historian_runtime_chains_match_spec() -> None:
    translated = translate_cql(_cql_list_part2_historian_library())
    expected = {
        "TakeNullFunction": ([],),
        "TakeNullQuery": ([],),
        "TakeNegativeQuery": ([],),
        "LengthSkipNull": (0,),
        "LengthTakeNull": (0,),
        "LengthTailNull": (0,),
        "SingletonSkipSingle": (2,),
        "SingletonTakeSingle": (1,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            if name in {"SingletonSkipMulti", "SingletonTakeMulti"}:
                for con in (py, cpp, no_py):
                    with pytest.raises(duckdb.InvalidInputException, match="SingletonFrom"):
                        con.execute(sql).fetchone()
                continue

            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            no_py_result = no_py.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert no_py_result == py_result, name
            assert py_result == expected[name], name
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_temporal_uncertainty_matches_no_python_cpp() -> None:
    translated = translate_cql(_cql_list_part2_temporal_uncertainty_library())
    expected = {
        "ProperIncludesTimeUncertain": (None,),
        "ProperIncludedInTimeUncertain": (None,),
        "ContainsTimeUncertain": (None,),
        "InTimeUncertain": (None,),
        "EqualTimeUncertain": (None,),
        "NotEqualTimeUncertain": (None,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            no_py_result = no_py.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert no_py_result == py_result, name
            assert py_result == expected[name], name

        direct_cases = [
            ("SELECT CQLListContainsTemporalEq(['T15:59:59.999'], 'T15:59:59')", (None,)),
            ("SELECT CQLListContainsTemporalEq(['T14:59:59.999'], 'T15:59:59')", (False,)),
            ("SELECT CQLListHasAllTemporalEq(['T15:59:59.999'], ['T15:59:59'])", (None,)),
            ("SELECT CQLListEqualTemporalEq(['T15:59:59.999'], ['T15:59:59'])", (None,)),
        ]
        for sql, expected_row in direct_cases:
            assert py.execute(sql).fetchone() == expected_row, sql
            assert cpp.execute(sql).fetchone() == expected_row, sql
            assert no_py.execute(sql).fetchone() == expected_row, sql
    finally:
        no_py_cm.__exit__(None, None, None)
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


def _cql_list_part2_edge_library() -> str:
    return """library List2Edges version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SkipNullCount: Skip({1, 3, 5}, null)
define SkipNegativeCount: Skip({1, 3, 5}, -1)
define ProperIncludesQuantity: { 1 'g', 2 'g' } properly includes 1000 'mg'
define ProperIncludedInQuantity: 1000 'mg' properly included in { 1 'g', 2 'g' }
define ProperIncludesQuantityList: { 1 'g', 2 'g' } properly includes { 1000 'mg' }
define ProperIncludedInQuantityList: { 1000 'mg' } properly included in { 1 'g', 2 'g' }
define ProperIncludesNullSingleton: { 1, 3, 5, null } properly includes null
define ProperIncludedInNullSingleton: null properly included in { 1, 3, 5, null }
define ProperIncludesNullLeft: null properly includes {2}
define ProperIncludedInNullRight: {'s', 'u', 'n'} properly included in null
define UnionNullLeft: (null as List<Integer>) union { 4, 5 }
define UnionNullBoth: (null as List<Integer>) union (null as List<Integer>)
"""


def _cql_list_part2_historian_library() -> str:
    return """library List2Historian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define TakeNullFunction: Take({1,2,3}, null as Integer)
define TakeNullQuery: {1,2,3} take (null as Integer)
define TakeNegativeQuery: {1,2,3} take -1
define LengthSkipNull: Length(Skip(null as List<Integer>, 1))
define LengthTakeNull: Length(Take(null as List<Integer>, 1))
define LengthTailNull: Length(Tail(null as List<Integer>))
define SingletonSkipSingle: singleton from Skip({1,2},1)
define SingletonTakeSingle: singleton from Take({1,2},1)
define SingletonSkipMulti: singleton from Skip({1,2,3},0)
define SingletonTakeMulti: singleton from Take({1,2,3},2)
"""


def _cql_list_part2_temporal_uncertainty_library() -> str:
    return """library List2TemporalUncertainty version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ProperIncludesTimeUncertain: { @T15:59:59.999, @T20:59:59.999 } properly includes @T15:59:59
define ProperIncludedInTimeUncertain: @T15:59:59 properly included in { @T15:59:59.999, @T20:59:59.999 }
define ContainsTimeUncertain: { @T15:59:59.999, @T20:59:59.999 } contains @T15:59:59
define InTimeUncertain: @T15:59:59 in { @T15:59:59.999, @T20:59:59.999 }
define EqualTimeUncertain: { @T15:59:59.999 } = { @T15:59:59 }
define NotEqualTimeUncertain: { @T15:59:59.999 } != { @T15:59:59 }
"""
