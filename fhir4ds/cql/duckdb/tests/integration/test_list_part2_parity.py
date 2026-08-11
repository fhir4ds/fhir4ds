"""CQL list operator part 2 parity checks."""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.errors import TranslationError
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
        ("SELECT Length(NULL::INTEGER[])", (0,)),
        ("SELECT Length(NULL::VARCHAR)", (None,)),
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
            for sql in [
                "SELECT Skip([1, 2, 3], 1.5)",
                "SELECT Take([1, 2, 3], 1.5)",
                "SELECT Take([1, 2, 3], '1')",
            ]:
                with pytest.raises(duckdb.InvalidInputException, match="Integer"):
                    con.execute(sql).fetchone()
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_rejects_non_integer_skip_take_counts() -> None:
    for expression in [
        "Skip({1, 2, 3}, 1.5)",
        "Take({1, 2, 3}, 1.5)",
        "{1, 2, 3} skip 1.5",
        "{1, 2, 3} take 1.5",
    ]:
        with pytest.raises(TranslationError, match="count argument must be Integer"):
            translate_cql(
                f"""library List2CountDiscipline version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Bad: {expression}
"""
            )


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


def test_cql_list_part2_interval_elements_use_interval_semantics() -> None:
    translated = translate_cql(_cql_list_part2_interval_semantics_library())
    expected = {
        "IntervalListEqualSemantic": (True,),
        "IntervalListNotEqualSemantic": (False,),
        "IntervalListEquivalentSemantic": (True,),
        "IntervalListNotEquivalentSemantic": (False,),
        "IntervalListProperIncludesSemantic": (True,),
        "IntervalListProperIncludedInSemantic": (True,),
        "IntervalListUnionSemanticLength": (1,),
    }

    direct_sql = """
WITH vals AS (
  SELECT
    intervalFromBounds('1', '6', false, true) AS open_interval,
    intervalFromBounds('2', '6', true, true) AS closed_interval
)
SELECT
  CQLListElementEqual(open_interval, closed_interval),
  CQLListElementEquivalent(open_interval, closed_interval),
  CQLListContainsEq([open_interval], closed_interval),
  CQLListEqualEq([open_interval], [closed_interval]),
  CQLListEquivalentEq([open_interval], [closed_interval]),
  array_length("Distinct"(list_concat([open_interval], [closed_interval])))
FROM vals
"""
    direct_expected = (True, True, True, True, True, 1)

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

        for con in (py, cpp, no_py):
            assert con.execute(direct_sql).fetchone() == direct_expected
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_query_produced_lists_remain_lists() -> None:
    translated = translate_cql(_cql_list_part2_explorer_query_library())
    expected = {
        "LastQuery": (3,),
        "LengthQuery": (3,),
        "TailQuery": ([2, 3],),
        "SkipQuery": ([2, 3],),
        "TakeQuery": ([1, 2],),
        "LengthAlias": (3,),
        "TailAlias": ([2, 3],),
        "LastAlias": (3,),
        "ProperIncludesQueryElement": (True,),
        "ProperIncludedInQueryElement": (True,),
        "ProperIncludesQueryList": (True,),
        "ProperIncludedInQueryList": (True,),
        "UnionQueryLiteralLength": (3,),
        "TailDistinctUnionQuery": ([2, 3],),
        "SkipDistinctUnionQuery": ([2, 3],),
        "TakeDistinctUnionQuery": ([1, 2],),
        "SingletonQuerySingle": (2,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for name, expected_row in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            no_py_result = no_py.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert no_py_result == py_result, name
            assert py_result == expected_row, name

        sql = f"SELECT {translated['SingletonQueryMulti'].to_sql()}"
        for con in (py, cpp, no_py):
            with pytest.raises(duckdb.InvalidInputException, match="SingletonFrom"):
                con.execute(sql).fetchone()
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


def _cql_list_part2_interval_semantics_library() -> str:
    return """library List2IntervalSemantics version '1.0.0'
using FHIR version '4.0.1'
context Patient
define IntervalListEqualSemantic: { Interval(1, 6] } = { Interval[2, 6] }
define IntervalListNotEqualSemantic: { Interval(1, 6] } != { Interval[2, 6] }
define IntervalListEquivalentSemantic: { Interval(1, 6] } ~ { Interval[2, 6] }
define IntervalListNotEquivalentSemantic: { Interval(1, 6] } !~ { Interval[2, 6] }
define IntervalListProperIncludesSemantic: { Interval(1, 6], Interval[10, 11] } properly includes Interval[2, 6]
define IntervalListProperIncludedInSemantic: Interval[2, 6] properly included in { Interval(1, 6], Interval[10, 11] }
define IntervalListUnionSemanticLength: Length({ Interval(1, 6] } union { Interval[2, 6] })
"""


def _cql_list_part2_explorer_query_library() -> str:
    return """library List2ExplorerQuery version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QueryValues: (from {1, 2, 3} X return X)
define LastQuery: Last((from {1, 2, 3} X return X))
define LengthQuery: Length((from {1, 2, 3} X return X))
define TailQuery: Tail((from {1, 2, 3} X return X))
define SkipQuery: Skip((from {1, 2, 3} X return X), 1)
define TakeQuery: Take((from {1, 2, 3} X return X), 2)
define LengthAlias: Length(QueryValues)
define TailAlias: Tail(QueryValues)
define LastAlias: Last(QueryValues)
define ProperIncludesQueryElement: (from {1, 2, 3} X return X) properly includes 2
define ProperIncludedInQueryElement: 2 properly included in (from {1, 2, 3} X return X)
define ProperIncludesQueryList: (from {1, 2, 3} X return X) properly includes {1, 2}
define ProperIncludedInQueryList: {1, 2} properly included in (from {1, 2, 3} X return X)
define UnionQueryLiteralLength: Length((from {1, 2} X return X) union {2, 3})
define TailDistinctUnionQuery: Tail((from {1, 2} X return X) union {2, 3})
define SkipDistinctUnionQuery: Skip((from {1, 2} X return X) union {2, 3}, 1)
define TakeDistinctUnionQuery: Take((from {1, 2} X return X) union {2, 3}, 2)
define SingletonQuerySingle: singleton from (from {2} X return X)
define SingletonQueryMulti: singleton from (from {1, 2} X return X)
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


def _cql_list_part2_symbolic_pipe_library() -> str:
    """CQL v1.5.3 §20.29: the union operator can also be invoked with the
    symbolic operator (|). Both list and interval overloads must translate
    identically to the `union` keyword form.
    """
    return """library List2SymbolicPipe version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PipeListDedup: { 1, 2 } | { 2, 3 }
define PipeListLength: Length({ 1, 2 } | { 2, 3 })
define PipeNullLeft: (null as List<Integer>) | { 4, 5 }
define PipeNullBoth: (null as List<Integer>) | (null as List<Integer>)
"""


def test_cql_list_part2_symbolic_pipe_union_matches_keyword_union() -> None:
    """CQL §20.29: `|` is the symbolic form of `union` for lists."""
    translated = translate_cql(_cql_list_part2_symbolic_pipe_library())
    expected = {
        "PipeListDedup": ({1, 2, 3},),
        "PipeListLength": (3,),
        "PipeNullLeft": ({4, 5},),
        "PipeNullBoth": (set(),),
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
            # Normalize list results to sets since order is unspecified for
            # union per CQL §20.29.
            def _norm(row):
                if isinstance(row, tuple) and len(row) == 1:
                    val = row[0]
                    if isinstance(val, list):
                        return (set(val),)
                    return row
                return row

            assert _norm(py_result) == _norm(cpp_result), name
            assert _norm(py_result) == _norm(no_py_result), name
            assert _norm(py_result) == expected[name], name
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def test_cql_list_part2_symbolic_pipe_parses_as_union_binary_expression() -> None:
    """The parser emits operator == '|' for the symbolic pipe form; ensure
    it now routes through the union translator (regression sentinel for
    CQL-19 QA-001)."""
    expr = parse_expression("{1, 2} | {2, 3}")
    assert isinstance(expr, BinaryExpression)
    assert expr.operator == "|"
    # Translation must succeed and produce SQL list_concat / list_distinct.
    translated = translate_cql(
        """library Sentinel version '1.0.0'
using FHIR version '4.0.1'
context Patient
define X: {1, 2} | {2, 3}
"""
    )
    sql_text = str(translated["X"])
    # The union lowering path uses list_concat + Distinct (or list_distinct).
    # Just ensure no raw bitwise `|` operator remains in the SQL.
    assert "list_concat" in sql_text or "Distinct" in sql_text or "list_distinct" in sql_text


def _cql_list_part2_typed_empty_union_library() -> str:
    """CQL v1.5.3 §20.29 Union (List): typed-empty-list union must return an
    empty list, not raise BinderException. Regression coverage for
    CQL-19 HISTORIAN iter 1 QA-001.

    The previous translator fallback emitted a CASE expression that mixed
    `jsonConcat` (returns VARCHAR[]) with typed CASE arms (e.g., INTEGER[]),
    raising BinderException on Integer/Long/Decimal/Boolean typed-empty unions.
    """
    return """library List2TypedEmptyUnion version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EmptyInteger: ({} as List<Integer>) union ({} as List<Integer>)
define EmptyLong: ({} as List<Long>) union ({} as List<Long>)
define EmptyDecimal: ({} as List<Decimal>) union ({} as List<Decimal>)
define EmptyBoolean: ({} as List<Boolean>) union ({} as List<Boolean>)
define EmptyString: ({} as List<String>) union ({} as List<String>)
define EmptyDateTime: ({} as List<DateTime>) union ({} as List<DateTime>)
define EmptyTime: ({} as List<Time>) union ({} as List<Time>)
define EmptyQuantity: ({} as List<Quantity>) union ({} as List<Quantity>)
define TypedEmptyPlusLiteral: ({} as List<Integer>) union {1, 2, 3}
define LiteralPlusTypedEmpty: {1, 2, 3} union ({} as List<Integer>)
define TypedNonEmptyUnion: ({1, 2} as List<Integer>) union ({3, 4} as List<Integer>)
define TypedEmptyPlusNonEmpty: ({} as List<Integer>) union ({1, 2} as List<Integer>)
define TypedEmptyPlusNull: ({} as List<Integer>) union (null as List<Integer>)
define NullPlusTypedEmpty: (null as List<Integer>) union ({} as List<Integer>)
"""


def test_cql_list_part2_typed_empty_list_union_returns_empty_per_spec() -> None:
    """CQL §20.29: typed-empty-list union must return an empty list, not
    raise BinderException. Verifies the fix for CQL-19 HISTORIAN iter 1 QA-001
    across all three DuckDB backends (Python fallback, native C++ extension,
    no-Python/browser-style C++)."""
    translated = translate_cql(_cql_list_part2_typed_empty_union_library())
    expected = {
        "EmptyInteger": ([],),
        "EmptyLong": ([],),
        "EmptyDecimal": ([],),
        "EmptyBoolean": ([],),
        "EmptyString": ([],),
        "EmptyDateTime": ([],),
        "EmptyTime": ([],),
        "EmptyQuantity": ([],),
        "TypedEmptyPlusLiteral": ([1, 2, 3],),
        "LiteralPlusTypedEmpty": ([1, 2, 3],),
        "TypedNonEmptyUnion": ([1, 2, 3, 4],),
        "TypedEmptyPlusNonEmpty": ([1, 2],),
        "TypedEmptyPlusNull": ([],),
        "NullPlusTypedEmpty": ([],),
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
            # Normalize lists to sorted form for order-insensitive comparison.
            def _norm_list(row):
                if isinstance(row, tuple) and len(row) == 1 and isinstance(row[0], list):
                    return (sorted(row[0], key=lambda x: (str(type(x)), str(x))),)
                return row
            py_n = _norm_list(py_result)
            cpp_n = _norm_list(cpp_result)
            no_py_n = _norm_list(no_py_result)
            exp_n = _norm_list(expected[name])
            assert cpp_n == py_n, f"{name}: cpp={cpp_n!r} py={py_n!r}"
            assert no_py_n == py_n, f"{name}: no_py={no_py_n!r} py={py_n!r}"
            assert py_n == exp_n, f"{name}: py={py_n!r} expected={exp_n!r}"
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


def _cql_list_part2_explorer_typed_null_list_library() -> str:
    """CQL v1.5.3 §20 List Properly Includes / Properly Included In:

    For the list-list overload, if either argument is null, the result is null.

    Typed-null lists (e.g., `null as List<Integer>`) translate to
    `CASE WHEN FALSE THEN NULL ELSE NULL END` rather than a bare SQLNull.
    The list-list null-check must detect this pattern, otherwise the
    array_length comparison short-circuits to 0 > N = False, returning
    False instead of NULL.
    """
    return """library List2TypedNullList version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PI_LeftNullList: (null as List<Integer>) properly includes {1, 3, 5}
define PI_RightNullList: {1, 3, 5} properly includes (null as List<Integer>)
define PI_BothNullList: (null as List<Integer>) properly includes (null as List<Integer>)
define PIIB_LeftNullList: (null as List<Integer>) properly included in {1, 3, 5}
define PIIB_RightNullList: {1, 3, 5} properly included in (null as List<Integer>)
define PIIB_BothNullList: (null as List<Integer>) properly included in (null as List<Integer>)
"""


def test_cql_list_part2_typed_null_list_properly_includes_returns_null_per_spec() -> None:
    """CQL §20: For the list-list overload of properly includes / properly
    included in, if either argument is null, the result is null.

    Regression coverage for CQL-19 EXPLORER iter 1. The typed-null list
    `(null as List<Integer>)` is translated to a CASE expression that must
    be detected by the list-list null guard. Otherwise, the array_length
    comparison short-circuits to 0 > N = False, returning False instead of
    NULL across all three DuckDB backends.
    """
    translated = translate_cql(_cql_list_part2_explorer_typed_null_list_library())
    expected = {
        "PI_LeftNullList": (None,),
        "PI_RightNullList": (None,),
        "PI_BothNullList": (None,),
        "PIIB_LeftNullList": (None,),
        "PIIB_RightNullList": (None,),
        "PIIB_BothNullList": (None,),
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
            assert py_result == expected[name], f"{name}: got {py_result!r}, expected {expected[name]!r}"
    finally:
        no_py_cm.__exit__(None, None, None)
        py.close()
        cpp.close()


