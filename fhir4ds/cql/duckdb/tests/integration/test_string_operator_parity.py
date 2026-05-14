"""CQL string operator parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import FunctionRef, IndexerExpression
from fhir4ds.cql.translator import translate_cql


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
    assert "LIKE" in str(translated["EndsCheck"])
    assert "LIST_EXTRACT" in str(translated["IndexCheck"])
    assert "LastPositionOf" in str(translated["LastPosCheck"])
    assert "LENGTH" in str(translated["LengthCheck"])
    assert "LOWER" in str(translated["LowerCheck"])
    assert "Matches" in str(translated["MatchesCheck"])
    assert "strpos" in str(translated["PositionCheck"])
    assert "ReplaceMatches" in str(translated["ReplaceMatchesCheck"])
    assert "STR_SPLIT" in str(translated["SplitCheck"])
    assert "SplitOnMatches" in str(translated["SplitOnMatchesCheck"])
    assert "LIKE" in str(translated["StartsCheck"])
    assert "system.substring" in str(translated["SubstringCheck"])
    assert "UPPER" in str(translated["UpperCheck"])


def test_cql_string_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT Combine(['a','b'])",
        "SELECT CombineSep(['a','b'], ',')",
        "SELECT Concatenate('a','b')",
        "SELECT EndsWith('abc','bc')",
        "SELECT Indexer('abc', 1)",
        "SELECT LastPositionOf('l','hello')",
        "SELECT Length('abc')",
        "SELECT Lower('ABC')",
        "SELECT Matches('abc','a.*')",
        "SELECT PositionOf('b','abc')",
        "SELECT ReplaceMatches('abc','b','X')",
        "SELECT Split('a,b', ',')",
        "SELECT SplitOnMatches('a1b2','\\d')",
        "SELECT StartsWith('abc','a')",
        "SELECT Substring('abc', 1)",
        "SELECT SubstringLen('abc', 1, 2)",
        "SELECT Upper('abc')",
        "SELECT stringLength('abc')",
        "SELECT stringSplit('a,b', ',')",
        "SELECT stringMatches('aaaaaaaaaaaaaaaaaaaaaaaa', '(a+)+b')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()
