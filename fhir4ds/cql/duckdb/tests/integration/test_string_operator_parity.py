"""CQL string operator parity checks."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.errors import TranslationError
from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef, IndexerExpression
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


def test_cql_string_expressions_parse_and_translate() -> None:
    for expression in [
        "Combine({'a', 'b'}, ',')",
        "Concatenate('a','b')",
        "EndsWith('abc','bc')",
        "LastPositionOf('l','hello')",
        "Length('abc')",
        "Lower('ABC')",
        "Matches('abc','a.*')",
        "PositionOf('b','abc')",
        "ReplaceMatches('abc','b','X')",
        "Split('a,b', ',')",
        "SplitOnMatches('a1b2','\\d')",
        "StartsWith('abc','a')",
        "Substring('abc', 1, 2)",
        "Upper('abc')",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    parsed_indexer = parse_expression("'abc'[1]")
    assert isinstance(parsed_indexer, IndexerExpression)

    cql = """library Strings version '1.0.0'
using FHIR version '4.0.1'
context Patient
define CombineCheck: Combine({'a', 'b'}, ',')
define ConcatCheck: Concatenate('a','b')
define EndsCheck: EndsWith('abc','bc')
define IndexCheck: 'abc'[1]
define LastPosCheck: LastPositionOf('l','hello')
define LengthCheck: Length('abc')
define LowerCheck: Lower('ABC')
define MatchesCheck: Matches('abc','a.*')
define PositionCheck: PositionOf('b','abc')
define ReplaceMatchesCheck: ReplaceMatches('abc','b','X')
define SplitCheck: Split('a,b', ',')
define SplitOnMatchesCheck: SplitOnMatches('a1b2','\\d')
define StartsCheck: StartsWith('abc','a')
define SubstringCheck: Substring('abc', 1, 2)
define UpperCheck: Upper('abc')
"""
    translated = translate_cql(cql)

    assert "CombineSep" in str(translated["CombineCheck"])
    assert "Concatenate" in str(translated["ConcatCheck"])
    assert "EndsWith" in str(translated["EndsCheck"])
    assert "Indexer" in str(translated["IndexCheck"])
    assert "LastPositionOf" in str(translated["LastPosCheck"])
    assert "LENGTH" in str(translated["LengthCheck"])
    assert "LOWER" in str(translated["LowerCheck"])
    assert "Matches" in str(translated["MatchesCheck"])
    assert "strpos" in str(translated["PositionCheck"])
    assert "ReplaceMatches" in str(translated["ReplaceMatchesCheck"])
    assert "STR_SPLIT" in str(translated["SplitCheck"])
    assert "SplitOnMatches" in str(translated["SplitOnMatchesCheck"])
    assert "StartsWith" in str(translated["StartsCheck"])
    assert "system.substring" in str(translated["SubstringCheck"])
    assert "UPPER" in str(translated["UpperCheck"])


def test_cql_string_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT Combine(['a','b'])",
        "SELECT Combine([])",
        "SELECT CombineSep(['a','b'], ',')",
        "SELECT CombineSep([], ',')",
        "SELECT CombineSep(['a','b'], NULL)",
        "SELECT Concatenate('a','b')",
        "SELECT EndsWith('abc','bc')",
        "SELECT Indexer('abc', 1)",
        "SELECT LastPositionOf('l','hello')",
        "SELECT Length('abc')",
        "SELECT Lower('ABC')",
        "SELECT Matches('abc','a.*')",
        "SELECT Matches('a\nb','a.b')",
        "SELECT Matches('aa','(.)\\1')",
        "SELECT Matches('ab','(?=b)')",
        "SELECT PositionOf('b','abc')",
        "SELECT ReplaceMatches('abc','b','X')",
        "SELECT ReplaceMatches('a\nb','a.b','x')",
        "SELECT ReplaceMatches('book','(.)\\1','X')",
        "SELECT Split('a,b', ',')",
        "SELECT SplitOnMatches('a1b2','\\d')",
        "SELECT SplitOnMatches('a\nb','.')",
        "SELECT SplitOnMatches('ab','(?=b)')",
        "SELECT StartsWith('abc','a')",
        "SELECT StartsWith('abc','a%')",
        "SELECT Substring('abc', 1)",
        "SELECT Substring('abc', 1, 2)",
        "SELECT Substring('abc', 1, CAST(NULL AS INTEGER))",
        "SELECT Substring('abc', 1, -1)",
        "SELECT Substring('abc', 3)",
        "SELECT SubstringLen('abc', 1, 2)",
        "SELECT SubstringLen('abc', 1, -1)",
        "SELECT Upper('abc')",
        "SELECT stringLength('abc')",
        "SELECT stringStartsWith('abc', NULL)",
        "SELECT stringEndsWith('abc', NULL)",
        "SELECT stringSubstring('abc', 1, -1)",
        "SELECT stringSplit('a,b', ',')",
        "SELECT stringMatches('aaaaaaaaaaaaaaaaaaaaaaaa', '(a+)+b')",
        "SELECT stringMatches('a\nb', 'a.b')",
        "SELECT stringMatches('abc', NULL)",
        "SELECT stringReplace('abc', NULL, 'x')",
        "SELECT stringReplace('abc', 'a', NULL)",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_string_skeptic_regressions() -> None:
    cql = """library StringSkeptic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define CombineEmpty: Combine({})
define CombineSepEmpty: Combine({}, '-')
define CombineSepNullSeparator: Combine({'a', 'b'}, null)
define SubstringAtEnd: Substring('ab', 2)
define SubstringPastEnd: Substring('ab', 3)
define SubstringNegativeLength: Substring('ab', 0, -1)
define StartsWithWildcardLiteral: StartsWith('abc', 'a%')
define EndsWithWildcardLiteral: EndsWith('abc', '_c')
define BracketIndexerAtEnd: 'ab'[2]
define CombineIndexerAtEnd: Combine({'a', 'b'})[2]
define ReplaceMatchesIndexerAtEnd: ReplaceMatches('abc', 'b', 'x')[3]
define LastSplitIndexerAtEnd: Last(Split('ab/cd', '/'))[2]
define AmpersandLeftNull: null & 'b'
define AmpersandRightNull: 'a' & null
define AmpersandBothNull: null & null
"""
    translated = translate_cql(cql)
    expected = {
        "CombineEmpty": None,
        "CombineSepEmpty": None,
        "CombineSepNullSeparator": "ab",
        "SubstringAtEnd": None,
        "SubstringPastEnd": None,
        "SubstringNegativeLength": None,
        "StartsWithWildcardLiteral": False,
        "EndsWithWildcardLiteral": False,
        "BracketIndexerAtEnd": None,
        "CombineIndexerAtEnd": None,
        "ReplaceMatchesIndexerAtEnd": None,
        "LastSplitIndexerAtEnd": None,
        "AmpersandLeftNull": "b",
        "AmpersandRightNull": "a",
        "AmpersandBothNull": "",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] == expected_value
            assert cpp.execute(sql).fetchone()[0] == expected_value
    finally:
        py.close()
        cpp.close()

    direct_queries = {
        "SELECT Combine([])": None,
        "SELECT CombineSep([], '-')": None,
        "SELECT CombineSep(['a','b'], NULL)": "ab",
        "SELECT Substring('ab', 0, 1)": "a",
        "SELECT Substring('ab', 0, CAST(NULL AS INTEGER))": None,
        "SELECT Substring('ab', 0, -1)": None,
        "SELECT Substring('ab', 2)": None,
        "SELECT Substring('ab', 3)": None,
        "SELECT SubstringLen('ab', 0, -1)": None,
        "SELECT StartsWith('abc', 'a%')": False,
        "SELECT EndsWith('abc', '_c')": False,
    }
    with no_python_connection() as con:
        for sql, expected_value in direct_queries.items():
            assert con.execute(sql).fetchone()[0] == expected_value


def test_cql_string_skeptic_rejects_non_string_coercion() -> None:
    """String operator signatures must not inherit DuckDB string coercion."""
    invalid_cql = [
        "Concatenate(1, 'x')",
        "1 & 'x'",
        "'a' + 2",
        "Combine({1, 2})",
    ]
    for expression in invalid_cql:
        cql = f"""library StringTypeDiscipline version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Bad: {expression}
"""
        with pytest.raises(TranslationError):
            translate_cql(cql)

    invalid_direct = [
        "SELECT Concatenate(1, 'x')",
        "SELECT Concatenate(CAST(NULL AS INTEGER), 'x')",
        "SELECT Concat(1, 'x')",
        "SELECT Combine([1, 2])",
        "SELECT Combine(CAST(NULL AS INTEGER[]))",
        "SELECT CombineSep([1, 2], '-')",
        "SELECT CombineSep(['a', 'b'], 1)",
        "SELECT CombineSep(CAST(NULL AS VARCHAR[]), CAST(NULL AS INTEGER))",
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql in invalid_direct:
            with pytest.raises(duckdb.Error):
                py.execute(sql).fetchone()
            with pytest.raises(duckdb.Error):
                cpp.execute(sql).fetchone()
    finally:
        py.close()
        cpp.close()

    with no_python_connection() as con:
        for sql in invalid_direct:
            with pytest.raises(duckdb.Error):
                con.execute(sql).fetchone()


def test_cql_string_historian_regex_single_line_regressions() -> None:
    cql = """library StringHistorian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MatchDotCrossesNewline: Matches('a\\nb', 'a.b')
define ReplaceDotCrossesNewline: ReplaceMatches('a\\nb', 'a.b', 'x')
define SplitDotCrossesNewline: SplitOnMatches('a\\nb', '.')
define MatchBackreference: Matches('aa', '(.)\\1')
define MatchLookahead: Matches('ab', '(?=b)')
define ReplaceBackreferencePattern: ReplaceMatches('book', '(.)\\1', 'X')
define SplitLookahead: SplitOnMatches('ab', '(?=b)')
"""
    translated = translate_cql(cql)
    expected = {
        "MatchDotCrossesNewline": True,
        "ReplaceDotCrossesNewline": "x",
        "SplitDotCrossesNewline": ["", "", "", ""],
        "MatchBackreference": True,
        "MatchLookahead": True,
        "ReplaceBackreferencePattern": "bXk",
        "SplitLookahead": ["a", "b"],
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] == expected_value
            assert cpp.execute(sql).fetchone()[0] == expected_value
    finally:
        py.close()
        cpp.close()

    direct_queries = {
        "SELECT Matches('a\nb', 'a.b')": True,
        "SELECT ReplaceMatches('a\nb', 'a.b', 'x')": "x",
        "SELECT SplitOnMatches('a\nb', '.')": ["", "", "", ""],
        "SELECT Matches('aa', '(.)\\1')": True,
        "SELECT Matches('ab', '(?=b)')": True,
        "SELECT ReplaceMatches('book', '(.)\\1', 'X')": "bXk",
        "SELECT SplitOnMatches('ab', '(?=b)')": ["a", "b"],
    }
    with no_python_connection() as con:
        for sql, expected_value in direct_queries.items():
            assert con.execute(sql).fetchone()[0] == expected_value


def test_cql_string_explorer_ext_escapes_fhirpath_string_literals() -> None:
    """CQL string literals embedded into FHIRPath predicates must stay literal."""
    cql_url_literal = r"http://evil\') or true or (url=\'x"
    exact_url = "http://evil') or true or (url='x"
    cql = f"""library StringExplorerExt version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ExtValue: Patient.ext('{cql_url_literal}').value
"""
    translated = translate_cql(cql)
    sql = "SELECT " + translated["ExtValue"].to_sql().replace(
        "_pt.patient_resource",
        "?::JSON",
    )
    nonmatching = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "extension": [
                {"url": "http://safe", "valueString": "SECRET"},
                {"url": "x", "valueString": "X"},
            ],
        }
    )
    matching = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p2",
            "extension": [
                {"url": exact_url, "valueString": "MATCH"},
            ],
        }
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert con.execute(sql, [nonmatching]).fetchone()[0] is None
            assert con.execute(sql, [matching]).fetchone()[0] == "MATCH"
    finally:
        py.close()
        cpp.close()

    with no_python_connection() as con:
        assert con.execute(sql, [nonmatching]).fetchone()[0] is None
        assert con.execute(sql, [matching]).fetchone()[0] == "MATCH"


def test_cql_string_explorer_query_compositions_match_surfaces() -> None:
    cql = r"""library StringExplorerQuery version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QueryCombineSep:
  Combine((from { 'A', null, Lower('B') } S return S), '|')
define QueryCombine:
  Combine((from { 'A', null, Lower('B') } S return S))
define SingletonSubstring:
  Substring(singleton from { 'abcdef' }, 2, 3)
define RegexChain:
  Last(SplitOnMatches(ReplaceMatches('a-1;b-2', '\d', 'X'), ';'))[2]
"""
    translated = translate_cql(cql)
    expected = {
        "QueryCombineSep": "A|b",
        "QueryCombine": "Ab",
        "SingletonSubstring": "cde",
        "RegexChain": "X",
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] == expected_value
            assert cpp.execute(sql).fetchone()[0] == expected_value
    finally:
        py.close()
        cpp.close()

    with no_python_connection() as con:
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert con.execute(sql).fetchone()[0] == expected_value
