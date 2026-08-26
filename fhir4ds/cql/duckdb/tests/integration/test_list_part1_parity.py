"""CQL list operator part 1 parity checks."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, DistinctExpression, ExistsExpression, FunctionRef
from fhir4ds.cql.translator import translate_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

from .wasm_runtime_helpers import no_python_connection


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def _normalize(value):
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return _normalize(json.loads(value))
        except json.JSONDecodeError:
            return value
    return value


def _seed_resources(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
          id VARCHAR,
          resourceType VARCHAR,
          resource JSON,
          patient_ref VARCHAR
        )
        """
    )
    con.execute("DELETE FROM resources")
    con.execute(
        """
        INSERT INTO resources VALUES
        ('P1', 'Patient', '{"resourceType":"Patient","id":"P1"}', NULL),
        ('O1', 'Observation', '{"resourceType":"Observation","id":"O1","subject":{"reference":"Patient/P1"}}', 'P1')
        """
    )


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
    assert "CQLListContainsEq" in str(translated["ContainsList"])
    assert "Distinct" in str(translated["DistinctList"])
    assert "CQLListEqualEq" in translated["EqualList"].to_sql()
    assert "CASE" in translated["EquivalentList"].to_sql()
    assert "CQLListExceptEq" in str(translated["ExceptList"])
    assert "list_count" in str(translated["ExistsList"])
    assert "flatten" in str(translated["FlattenList"])
    assert "LIST_EXTRACT" in translated["FirstList"].to_sql()
    assert "CQLListContainsEq" in str(translated["InList"])
    assert "CQLListContainsEq" in str(translated["IncludesList"])
    assert "CQLListContainsEq" in str(translated["IncludedInList"])
    assert "CQLIndexOf" in str(translated["IndexOfList"])
    assert "CQLListIntersectEq" in str(translated["IntersectList"])


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
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_result = py.execute(sql).fetchone()
                cpp_result = cpp.execute(sql).fetchone()
                no_py_result = no_py.execute(sql).fetchone()
                assert cpp_result == py_result, name
                assert no_py_result == py_result, name
                assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_edge_cases_match_no_python_runtime() -> None:
    translated = translate_cql(_cql_list_part1_edge_library())
    expected = {
        "ContainsNullPresent": (True,),
        "ContainsNullAbsent": (False,),
        "ContainsQuantityEquivalent": (True,),
        "ContainsMixedFalse": (False,),
        "ContainsBigMixedNumericFalse": (False,),
        "DistinctNulls": ([None, "a"],),
        "DistinctQuantityEquivalent": ([{"value": 1.0, "code": "g", "system": "http://unitsofmeasure.org", "unit": "g"}],),
        "EqualNullNull": (True,),
        "EqualQuantityEquivalent": (True,),
        "EquivalentNullNull": (True,),
        "EquivalentBigScalarFalse": (False,),
        "EquivalentBigMixedNumericFalse": (False,),
        "EquivalentQuantityEquivalent": (True,),
        "ExceptSetDedup": ([1, 3],),
        "ExceptNullRight": ([1, 4],),
        "ExceptNullElement": ([1, 3],),
        "ExceptQuantityEquivalent": ([{"value": 2.0, "code": "g", "system": "http://unitsofmeasure.org", "unit": "g"}],),
        "ExistsNullOnly": (False,),
        "FlattenPreservesNulls": ([None, None],),
        "FirstNull": (None,),
        "InNullPresent": (True,),
        "InNullAbsent": (False,),
        "InQuantityEquivalent": (True,),
        "InMixedFalse": (False,),
        "InBigMixedNumericFalse": (False,),
        "IncludesNullList": (True,),
        "IncludesNullSingletonAbsent": (False,),  # CQL 1.5 §10.10: null element -> true iff list contains nulls (EXPLORER QA-003)
        "IncludesQuantityEquivalent": (True,),
        "IncludedInNullList": (True,),
        "IncludedInNullSingleton": (False,),  # CQL 1.5 §10.11: null element -> true iff list contains nulls (EXPLORER QA-003)
        "IncludedInQuantityEquivalent": (True,),
        "IndexOfNullElement": (None,),
        "IndexOfMissing": (-1,),
        "IndexOfBigMixedNumericMissing": (-1,),
        "IndexOfQuantityEquivalent": (0,),
        "IntersectSetDedup": ([1, 3],),
        "IntersectNullElement": ([None, 3],),
        "IntersectBigMixedNumericEmpty": ([],),
        "IntersectQuantityEquivalent": ([{"value": 1.0, "code": "g", "system": "http://unitsofmeasure.org", "unit": "g"}],),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_result = _normalize(py.execute(sql).fetchone())
                cpp_result = _normalize(cpp.execute(sql).fetchone())
                no_py_result = _normalize(no_py.execute(sql).fetchone())
                assert cpp_result == py_result, name
                assert no_py_result == py_result, name
                assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_temporal_and_numeric_equality_match_cpp_registration() -> None:
    """CQL-18 SKEPTIC iteration 1 regression: temporal-aware dispatch for
    Except/Intersect/IndexOf, and Integer/Decimal list equality.

    Spec citations:
      - CQL §Equal (List): "uses equality semantics" — and §Equal (scalar)
        explicitly says 1.0 = 1 is true (conformance SimpleEqFloat1Int1).
        Therefore {1} = {1.0} must be true.
      - CQL §Except/§Intersect/§IndexOf: each "uses equality semantics".
        §Equal (DateTime) compares by timezone-normalized instant, so
        same-instant DateTimes must be considered set-equal.
      - CQL §Equal (DateTime): precision-mismatch comparison returns null.
        §IndexOf: "If either argument is null, the result is null." An
        uncertain equality propagates as null.
    """
    translated = translate_cql(_cql_list_part1_temporal_numeric_library())
    expected = {
        # QA-001: Integer/Decimal list equality must reach the runtime macro.
        "EqualIntDec": (True,),
        "EqualDecInt": (True,),
        "EqualIntDecMulti": (True,),
        "EqualIntDecDifferent": (False,),
        # QA-002: IndexOf with DateTime tz mismatch must use temporal compare.
        "IndexOfDateTimeTzMatch": (0,),
        # QA-003: Except with DateTime tz mismatch must remove the element.
        "ExceptDateTimeTz": ([],),
        # QA-004: Intersect with DateTime tz mismatch must keep the element.
        "IntersectDateTimeTz": (["2024-01-01T10:00:00+00:00"],),
        # QA-005: IndexOf with DateTime precision mismatch returns null.
        "IndexOfDateTimePrecision": (None,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_result = _normalize(py.execute(sql).fetchone())
                cpp_result = _normalize(cpp.execute(sql).fetchone())
                no_py_result = _normalize(no_py.execute(sql).fetchone())
                assert cpp_result == py_result, name
                assert no_py_result == py_result, name
                assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_direct_surface_matches_cpp_registration() -> None:
    cases = [
        ("SELECT First([1, 2, 3])", (1,)),
        ('SELECT "Distinct"([1, 2, 2])', ([1, 2],)),
        ('SELECT "Distinct"([NULL, NULL, 1, 1])', ([None, 1],)),
        ("SELECT CQLListEquivalentEq([' A  b '], ['a b'])", (True,)),
        ("SELECT CQLListExceptEq([1, 1, 2, 3], [2])", ([1, 3],)),
        ("SELECT CQLListIntersectEq([NULL, 1, 3], [NULL, 3, 5])", ([None, 3],)),
        ("SELECT CQLIndexOf([1, 2, 3], 2)", (1,)),
        (
            "SELECT CQLListContainsEq([parse_quantity('{\"value\":1,\"unit\":\"g\"}')], "
            "parse_quantity('{\"value\":1000,\"unit\":\"mg\"}'))",
            (True,),
        ),
        (
            "SELECT CQLIndexOf([parse_quantity('{\"value\":1,\"unit\":\"g\"}')], "
            "parse_quantity('{\"value\":1000,\"unit\":\"mg\"}'))",
            (0,),
        ),
        (
            "SELECT CQLIndexOf([parse_quantity('{\"value\":1,\"unit\":\"cm\"}')], "
            "parse_quantity('{\"value\":1,\"unit\":\"cm2\"}'))",
            (None,),
        ),
        (
            "SELECT CQLIndexOf("
            "[json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\"}')], "
            "json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\",\"display\":\"A\"}'))",
            (None,),
        ),
        (
            "SELECT CQLListElementEqual("
            "9223372036854775807::BIGINT, "
            "9223372036854775806::DECIMAL(19,0))",
            (False,),
        ),
        (
            "SELECT CQLListContainsEq("
            "[9223372036854775807::BIGINT], "
            "9223372036854775806::DECIMAL(19,0))",
            (False,),
        ),
        (
            "SELECT CQLListEquivalentEq("
            "[9223372036854775807::BIGINT], "
            "[9223372036854775806::DECIMAL(19,0)])",
            (False,),
        ),
        (
            "SELECT CQLListExceptEq("
            "[9223372036854775807::BIGINT], "
            "[9223372036854775806::DECIMAL(19,0)])",
            ([9223372036854775807],),
        ),
        (
            "SELECT CQLListIntersectEq("
            "[9223372036854775807::BIGINT], "
            "[9223372036854775806::DECIMAL(19,0)])",
            ([],),
        ),
        (
            "SELECT CQLIndexOf("
            "[9223372036854775807::BIGINT], "
            "9223372036854775806::DECIMAL(19,0))",
            (-1,),
        ),
        (
            "SELECT CQLListEquivalentEq("
            "[json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\",\"display\":\"A\"}')], "
            "[json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\",\"display\":\"B\"}')])",
            (True,),
        ),
        (
            "SELECT CQLListElementEqual("
            "json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\",\"display\":\"A\"}'), "
            "json('{\"display\":\"A\",\"system\":\"http://loinc.org\",\"code\":\"1234-5\"}'))",
            (True,),
        ),
        (
            "SELECT CQLListElementEqual("
            "json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\"}'), "
            "json('{\"code\":\"1234-5\",\"system\":\"http://loinc.org\",\"display\":\"A\"}'))",
            (None,),
        ),
        (
            "SELECT CQLListEqualEq("
            "[parse_quantity('{\"value\":1,\"unit\":\"cm\"}')], "
            "[parse_quantity('{\"value\":1,\"unit\":\"cm2\"}')])",
            (None,),
        ),
        (
            "SELECT CQLListContainsEq("
            "[parse_quantity('{\"value\":1,\"unit\":\"cm\"}')], "
            "parse_quantity('{\"value\":1,\"unit\":\"cm2\"}'))",
            (None,),
        ),
        (
            "SELECT CQLListEquivalentEq("
            "[json('{\"codes\":[{\"code\":\"1234-5\",\"system\":\"http://loinc.org\"}],\"display\":\"A\"}')], "
            "[json('{\"codes\":[{\"code\":\"1234-5\",\"system\":\"http://loinc.org\"}],\"display\":\"B\"}')])",
            (True,),
        ),
        ("SELECT SingletonFrom(['only'])", ("only",)),
        ("SELECT SingletonFrom([1])", ("1",)),
        ("SELECT SingletonFrom([1.25])", ("1.25",)),
        ("SELECT SingletonFrom([1::DECIMAL(10,2)])", ("1.00",)),
        ("SELECT SingletonFrom([true])", ("true",)),
        ("SELECT ElementAt(['a', 'b', 'c'], 1)", ("b",)),
        ("SELECT ElementAt([1, 2, 3], 1)", ("2",)),
        ("SELECT ElementAt([true, false], 1)", ("false",)),
        ("SELECT ElementAt([1.25, 2.50], -1)", ("2.50",)),
        ("SELECT jsonConcat(['a'], ['b'])", (["a", "b"],)),
        ("SELECT jsonConcat([1], [2])", (["1", "2"],)),
        ("SELECT jsonConcat([true], [false])", (["true", "false"],)),
        ("SELECT jsonConcat([1.25], [2.50])", (["1.25", "2.50"],)),
        (
            "SELECT jsonConcat([1::DECIMAL(10,2)], [2::DECIMAL(10,2)])",
            (["1.00", "2.00"],),
        ),
        ("SELECT jsonConcat(NULL, NULL)", (None,)),
        (
            "SELECT jsonConcat(CAST(NULL AS INTEGER[]), CAST(NULL AS INTEGER[]))",
            (None,),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in cases:
                assert _normalize(py.execute(sql).fetchone()) == expected
                assert _normalize(cpp.execute(sql).fetchone()) == expected
                assert _normalize(no_py.execute(sql).fetchone()) == expected
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_translated_clinical_and_quantity_unknowns_match_cpp_registration() -> None:
    cql = """library List1Unknowns version '1.0.0'
codesystem CS: 'http://loinc.org'
code "A No Display": '1234-5' from CS
code "A Display": '1234-5' from CS display 'Display A'

define QuantityIncompatibleEqual: { 1 'cm' } = { 1 'cm2' }
define QuantityIncompatibleContains: { 1 'cm' } contains 1 'cm2'
define QuantityIncompatibleIndexOf: IndexOf({ 1 'cm' }, 1 'cm2')
define ClinicalMissingComponentEqual: { "A No Display" } = { "A Display" }
define ClinicalMissingComponentEquivalent: { "A No Display" } ~ { "A Display" }
define ClinicalMissingComponentIndexOf: IndexOf({ "A No Display" }, "A Display")
"""
    translated = translate_cql(cql)
    expected = {
        "QuantityIncompatibleEqual": (None,),
        "QuantityIncompatibleContains": (None,),
        "QuantityIncompatibleIndexOf": (None,),
        "ClinicalMissingComponentEqual": (None,),
        "ClinicalMissingComponentEquivalent": (True,),
        "ClinicalMissingComponentIndexOf": (None,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for label, con in (("forced_python", py), ("native_loaded", cpp), ("no_python_cpp", no_py)):
                actual = {
                    name: _normalize(con.execute(f"SELECT {translated[name].to_sql()}").fetchone())
                    for name in expected
                }
                assert actual == expected, label
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_direct_singletonfrom_multi_item_errors_match_cpp_registration() -> None:
    sql = "SELECT SingletonFrom([1, 2])"

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for con in (py, cpp, no_py):
                with pytest.raises(duckdb.InvalidInputException, match="SingletonFrom"):
                    con.execute(sql).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_transported_clinical_list_equivalence_matches_cpp_registration() -> None:
    cql = """library List1ClinicalTransport version '1.0.0'
using FHIR version '4.0.1'
context Patient
codesystem LOINC: 'http://loinc.org'
code "Code A": '1234-5' from LOINC display 'Display A'
code "Code B": '1234-5' from LOINC display 'Display B'
concept "Concept A": { "Code A" } display 'Concept A'
concept "Concept B": { "Code B" } display 'Concept B'
define CodeListAliasEquivalent:
  (singleton from { { "Code A" } }) ~ (singleton from { { "Code B" } })
define ConceptListAliasEquivalent:
  (singleton from { { "Concept A" } }) ~ (singleton from { { "Concept B" } })
"""
    expected = {
        "CodeListAliasEquivalent": (True,),
        "ConceptListAliasEquivalent": (True,),
    }
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={name: name for name in expected},
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for con in (py, cpp, no_py):
                _seed_resources(con)
            for label, con in (("forced_python", py), ("native_loaded", cpp), ("no_python_cpp", no_py)):
                row = con.execute(sql).fetchone()
                assert row is not None, label
                actual = {
                    name: _normalize((row[index + 1],))
                    for index, name in enumerate(expected)
                }
                assert actual == expected, label
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_named_list_definition_population_sql_matches_cpp_registration() -> None:
    cql = """library List1Named version '1.0.0'
using FHIR version '4.0.1'
context Patient
define LNumeric: { 1, 2, null }
define LNulls: { null, null, 'a', 'a' }
define LQty: { 1 'g', 1000 'mg' }
define Nested: { { 1, null }, { 2 } }
define DistinctIdentifierNulls: distinct LNulls
define DistinctIdentifierQuantity: distinct LQty
define ExistsIdentifierNullOnly: exists { null }
define ExistsNamedNullOnly: exists { null, null }
define FlattenNamed: Flatten(Nested)
define FirstNamed: First(LNumeric)
define ContainsNullIdentifier: LNumeric contains null
define InNullIdentifier: null in LNumeric
define IncludesElementIdentifier: LNumeric includes 2
define IncludedInElementIdentifier: 2 included in LNumeric
define IncludesListIdentifier: LNumeric includes { 1, null }
define IncludedInListIdentifier: { 1, null } included in LNumeric
define IndexOfNullIdentifier: IndexOf(LNumeric, null)
define IndexOfIncompatibleQuantityIdentifier: IndexOf({ 1 'cm' }, 1 'cm2')
define IndexOfQueryQuantityIdentifier: IndexOf((from { 1 'g' } Q return Q), 1000 'mg')
define IndexOfQueryQuantityUnknown: IndexOf((from { 1 'cm' } Q return Q), 1 'cm2')
define ExceptIdentifierNull: LNumeric except { null }
define IntersectIdentifierNull: LNumeric intersect { null, 2 }
define EqualIdentifierNull: LNumeric = { 1, 2, null }
define EquivalentIdentifierNull: LNumeric ~ { 1, 2, null }
"""
    expected = {
        "DistinctIdentifierNulls": ([None, "a"],),
        "DistinctIdentifierQuantity": ([{"value": 1.0, "code": "g", "system": "http://unitsofmeasure.org", "unit": "g"}],),
        "ExistsIdentifierNullOnly": (False,),
        "ExistsNamedNullOnly": (False,),
        "FlattenNamed": ([1, None, 2],),
        "FirstNamed": (1,),
        "ContainsNullIdentifier": (True,),
        "InNullIdentifier": (True,),
        "IncludesElementIdentifier": (True,),
        "IncludedInElementIdentifier": (True,),
        "IncludesListIdentifier": (True,),
        "IncludedInListIdentifier": (True,),
        "IndexOfNullIdentifier": (None,),
        "IndexOfIncompatibleQuantityIdentifier": (None,),
        "IndexOfQueryQuantityIdentifier": (0,),
        "IndexOfQueryQuantityUnknown": (None,),
        "ExceptIdentifierNull": ([1, 2],),
        "IntersectIdentifierNull": ([2, None],),
        "EqualIdentifierNull": (True,),
        "EquivalentIdentifierNull": (True,),
    }
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={name: name for name in expected},
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for con in (py, cpp, no_py):
                _seed_resources(con)
            for label, con in (("forced_python", py), ("native_loaded", cpp), ("no_python_cpp", no_py)):
                row = con.execute(sql).fetchone()
                assert row is not None, label
                actual = {
                    name: _normalize((row[index + 1],))
                    for index, name in enumerate(expected)
                }
                assert actual == expected, label
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


def _cql_list_part1_edge_library() -> str:
    return """library List1Edges version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ContainsNullPresent: { 'a', 'b', null } contains null
define ContainsNullAbsent: { 'a', 'b' } contains null
define ContainsQuantityEquivalent: { 1 'g' } contains 1000 'mg'
define ContainsMixedFalse: { 'a' } contains 1
define ContainsBigMixedNumericFalse: { 9223372036854775806.0 } contains 9223372036854775807L
define DistinctNulls: distinct { null, null, 'a', 'a' }
define DistinctQuantityEquivalent: distinct { 1 'g', 1000 'mg' }
define EqualNullNull: { null } = { null }
define EqualQuantityEquivalent: { 1 'g' } = { 1000 'mg' }
define EquivalentNullNull: { null } ~ { null }
define EquivalentBigScalarFalse: 9223372036854775807L ~ 9223372036854775806.0
define EquivalentBigMixedNumericFalse: { 9223372036854775807L } ~ { 9223372036854775806.0 }
define EquivalentQuantityEquivalent: { 1 'g' } ~ { 1000 'mg' }
define ExceptSetDedup: { 1, 1, 2, 3 } except { 2 }
define ExceptNullRight: { 1, 4 } except null
define ExceptNullElement: { 1, null, 3 } except { null }
define ExceptQuantityEquivalent: { 1 'g', 2 'g' } except { 1000 'mg' }
define ExistsNullOnly: exists { null }
define FlattenPreservesNulls: flatten {{null}, {null}}
define FirstNull: First({ null, 1 })
define InNullPresent: null in { 1, null }
define InNullAbsent: null in { 1, 2 }
define InQuantityEquivalent: 1000 'mg' in { 1 'g' }
define InMixedFalse: 1 in { 'a' }
define InBigMixedNumericFalse: 9223372036854775807L in { 9223372036854775806.0 }
define IncludesNullList: { null } includes { null }
define IncludesNullSingletonAbsent: { 's', 'a', 'm' } includes null
define IncludesQuantityEquivalent: { 1 'g' } includes 1000 'mg'
define IncludedInNullList: { null } included in { null }
define IncludedInNullSingleton: null included in { 2 }
define IncludedInQuantityEquivalent: 1000 'mg' included in { 1 'g' }
define IndexOfNullElement: IndexOf({ 1, null }, null)
define IndexOfMissing: IndexOf({ 1, 2 }, 9)
define IndexOfBigMixedNumericMissing: IndexOf({ 9223372036854775807L }, 9223372036854775806.0)
define IndexOfQuantityEquivalent: IndexOf({ 1 'g' }, 1000 'mg')
define IntersectSetDedup: { 1, 1, 2, 3 } intersect { 1, 3, 3 }
define IntersectNullElement: { null, 1, 3 } intersect { null, 3, 5 }
define IntersectBigMixedNumericEmpty: { 9223372036854775807L } intersect { 9223372036854775806.0 }
define IntersectQuantityEquivalent: { 1 'g', 2 'g' } intersect { 1000 'mg' }
"""


def _cql_list_part1_temporal_numeric_library() -> str:
    """CQL-18 SKEPTIC iteration 1 regression library for temporal-aware
    list-operator dispatch and Integer/Decimal list equality.
    """
    return """library List1TemporalNumeric version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EqualIntDec: { 1 } = { 1.0 }
define EqualDecInt: { 1.0 } = { 1 }
define EqualIntDecMulti: { 1, 2 } = { 1.0, 2.0 }
define EqualIntDecDifferent: { 1, 2 } = { 1.0, 3.0 }
define IndexOfDateTimeTzMatch: IndexOf({ @2024-01-01T10:00:00+00:00 }, @2024-01-01T12:00:00+02:00)
define ExceptDateTimeTz: { @2024-01-01T10:00:00+00:00 } except { @2024-01-01T12:00:00+02:00 }
define IntersectDateTimeTz: { @2024-01-01T10:00:00+00:00 } intersect { @2024-01-01T12:00:00+02:00 }
define IndexOfDateTimePrecision: IndexOf({ @2024-01-01 }, @2024-01-01T12)
"""



def test_cql_list_part1_dynamic_fhir_lists_execute_and_match_cpp_registration() -> None:
    """CQL-18 SKEPTIC re-launch regression: list operators over retrieved
    multi-valued FHIR fields (name.given) in patient-context population SQL.

    Before the fix, dynamic multi-valued properties lowered to scalar
    fhirpath_text (first-node truncation): `exists` returned false with data
    present, `contains` used substring semantics over one node, and Distinct,
    Equal/Equivalent, Except/Intersect, IndexOf, Includes/IncludedIn and
    Flatten-of-list-literal raised DuckDB BinderExceptions. CQL 1.5 §10.x
    requires full-list equality semantics for every operator.
    """
    cql = """library List1Dynamic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define GivenExists: exists Patient.name.given
define GivenContainsHit: Patient.name.given contains 'Peter'
define GivenContainsPartial: Patient.name.given contains 'Ji'
define GivenIn: 'Peter' in Patient.name.given
define GivenDistinct: distinct Patient.name.given
define GivenEqual: Patient.name.given = { 'Jim', 'Peter', 'Jim' }
define GivenEquivalent: Patient.name.given ~ { 'Jim', 'Peter', 'Jim' }
define GivenExcept: Patient.name.given except { 'Jim' }
define GivenIntersect: Patient.name.given intersect { 'Jim', 'Peter' }
define GivenIncludes: Patient.name.given includes { 'Peter' }
define GivenIncludedIn: { 'Peter' } included in Patient.name.given
define GivenIndexOf: IndexOf(Patient.name.given, 'Peter')
define GivenFlattenCount: Count(flatten { Patient.name.given })
define TelecomExists: exists Patient.telecom.system
define NoTelecomExists: exists Patient.contact.name.given
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            name: name
            for name in (
                "GivenExists", "GivenContainsHit", "GivenContainsPartial",
                "GivenIn", "GivenDistinct", "GivenEqual", "GivenEquivalent",
                "GivenExcept", "GivenIntersect", "GivenIncludes",
                "GivenIncludedIn", "GivenIndexOf", "GivenFlattenCount",
                "TelecomExists", "NoTelecomExists",
            )
        },
    )
    patient = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "name": [{"given": ["Jim", "Peter"]}, {"given": ["Jim"]}],
            "telecom": [{"system": "phone", "value": "555"}],
        }
    )
    expected = {
        "GivenExists": True,
        "GivenContainsHit": True,
        # Equality semantics (§10.1), not substring over the first node.
        "GivenContainsPartial": False,
        "GivenIn": True,
        # First-occurrence order preserved (§10.2).
        "GivenDistinct": ["Jim", "Peter"],
        "GivenEqual": True,
        "GivenEquivalent": True,
        # Set semantics with duplicates eliminated (§10.5).
        "GivenExcept": ["Peter"],
        "GivenIntersect": ["Jim", "Peter"],
        "GivenIncludes": True,
        "GivenIncludedIn": True,
        "GivenIndexOf": 1,
        "GivenFlattenCount": 3,
        "TelecomExists": True,
        "NoTelecomExists": False,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("DELETE FROM resources")
            con.execute(
                "INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')",
                [patient],
            )
            row = con.execute(sql).fetchone()
            columns = [d[0] for d in con.execute(sql).description]
            values = dict(zip(columns, row))
            for name, want in expected.items():
                got = _normalize((values[name],))[0]
                assert got == want, f"{name}: got {got!r}, want {want!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_historian_relaunch_alias_and_dynamic_list_ops() -> None:
    """CQL-18 HISTORIAN relaunch QA-001/QA-002 regression coverage.

    A define alias bound to a dynamic multi-valued FHIR property
    (``define G: Patient.name.given``) must behave like List<String> in
    every list operator (CQL 1.5 Appendix B §10.x), and
    ``A includes B`` with both operands dynamic must use list has-all
    semantics (§10.10), not interval containment.
    """
    patient = json.dumps(
        {
            "resourceType": "Patient",
            "id": "p1",
            "name": [
                {"given": ["Jim", "Peter"], "family": "Chalmers"},
                {"given": ["Jim"], "family": "Chalmers"},
            ],
        }
    )
    cql = """
    library F version '1.0.0'
    using FHIR version '4.0.1'
    context Patient
    define G: Patient.name.given
    define AliasDistinct: distinct G
    define AliasCount: Count(G)
    define AliasExcept: G except { 'Jim' }
    define AliasIndexOf: IndexOf(G, 'Peter')
    define AliasContains: G contains 'Peter'
    define AliasIn: 'Peter' in G
    define AliasFirst: First(G)
    define IncludesSelf: Patient.name.given includes Patient.name.given
    define IncludedInSelf: Patient.name.given included in Patient.name.given
    """
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "AliasDistinct": "AliasDistinct",
            "AliasCount": "AliasCount",
            "AliasExcept": "AliasExcept",
            "AliasIndexOf": "AliasIndexOf",
            "AliasContains": "AliasContains",
            "AliasIn": "AliasIn",
            "AliasFirst": "AliasFirst",
            "IncludesSelf": "IncludesSelf",
            "IncludedInSelf": "IncludedInSelf",
        },
    )
    expected = {
        "AliasDistinct": ["Jim", "Peter"],
        "AliasCount": 3,
        "AliasExcept": ["Peter"],
        "AliasIndexOf": 1,
        "AliasContains": True,
        "AliasIn": True,
        "AliasFirst": "Jim",
        "IncludesSelf": True,
        "IncludedInSelf": True,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("DELETE FROM resources")
            con.execute(
                "INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')",
                [patient],
            )
            row = con.execute(sql).fetchone()
            columns = [d[0] for d in con.execute(sql).description]
            values = dict(zip(columns, row))
            for name, want in expected.items():
                got = _normalize((values[name],))[0]
                assert got == want, f"{name}: got {got!r}, want {want!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_list_part1_historian_relaunch_first_rejects_string() -> None:
    """CQL 1.5 §10.8: First(argument List<T>) has no String overload.

    A bare String must not be silently sliced as a character list
    (First('final') used to return 'f').
    """
    from fhir4ds.cql.errors import TranslationError

    cql = (
        "library F version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "context Patient\n"
        "define D: First('final')\n"
    )
    with pytest.raises(TranslationError, match="First requires a list argument"):
        CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql), output_columns={"D": "D"}
        )


def test_cql_list_part1_historian_relaunch_retrieve_alias_multivalued_navigation() -> None:
    """CQL-18 HISTORIAN relaunch QA-004 regression coverage.

    Navigating a multi-valued element over a retrieve-alias define must
    aggregate all matching nodes across rows (CQL 1.5 Appendix B Property
    semantics): Count(O.component) counts elements, not CTE rows, and
    membership tests over the flattened list see every code.
    """
    patient = json.dumps({"resourceType": "Patient", "id": "p1"})
    obs = json.dumps(
        {
            "resourceType": "Observation",
            "id": "o1",
            "status": "final",
            "subject": {"reference": "Patient/p1"},
            "component": [
                {"code": {"coding": [{"system": "http://loinc.org", "code": "29463-7"}]}},
                {"code": {"coding": [{"system": "http://loinc.org", "code": "8302-2"}]}},
            ],
        }
    )
    cql = """
    library F version '1.0.0'
    using FHIR version '4.0.1'
    context Patient
    define O: [Observation]
    define ComponentCount: Count(O.component)
    define CodingIn: '29463-7' in O.component.code.coding.code
    define CodingDistinct: Count(distinct O.component.code.coding.code)
    """
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "ComponentCount": "ComponentCount",
            "CodingIn": "CodingIn",
            "CodingDistinct": "CodingDistinct",
        },
    )
    expected = {
        "ComponentCount": 2,
        "CodingIn": True,
        "CodingDistinct": 2,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("DELETE FROM resources")
            con.execute(
                "INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')",
                [patient],
            )
            con.execute(
                "INSERT INTO resources VALUES ('o1', 'Observation', ?::JSON, 'p1')",
                [obs],
            )
            row = con.execute(sql).fetchone()
            columns = [d[0] for d in con.execute(sql).description]
            values = dict(zip(columns, row))
            for name, want in expected.items():
                got = _normalize((values[name],))[0]
                assert got == want, f"{name}: got {got!r}, want {want!r}"
    finally:
        py.close()
        cpp.close()


# ── CQL-18 EXPLORER launch regressions (2026-08-22) ─────────────────────

_P1_RESOURCE = (
    '{"resourceType":"Patient","id":"p1"}'
)
# Two-component Observation (8480-6, 8462-4) for p1; single-component (8867-4) for p2.
_P1_OBS = (
    '{"resourceType":"Observation","id":"o1","status":"final",'
    '"code":{"coding":[{"system":"http://loinc.org","code":"29463-7"}]},'
    '"subject":{"reference":"Patient/p1"},'
    '"component":[{"code":{"coding":[{"system":"http://loinc.org","code":"8480-6"}]}},'
    '{"code":{"coding":[{"system":"http://loinc.org","code":"8462-4"}]}}]}'
)
_P2_RESOURCE = (
    '{"resourceType":"Patient","id":"p2"}'
)
_P2_OBS = (
    '{"resourceType":"Observation","id":"o2","status":"final",'
    '"code":{"coding":[{"system":"http://loinc.org","code":"8867-4"}]},'
    '"subject":{"reference":"Patient/p2"},'
    '"component":[{"code":{"coding":[{"system":"http://loinc.org","code":"8867-4"}]}},'
    '{"code":{"coding":[{"system":"http://loinc.org","code":"8867-4"}]}}]}'
)


def _seed_two_patients(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
    )
    con.execute("DELETE FROM resources")
    con.execute("INSERT INTO resources VALUES ('p1','Patient',?::JSON,'p1')", [_P1_RESOURCE])
    con.execute("INSERT INTO resources VALUES ('o1','Observation',?::JSON,'p1')", [_P1_OBS])
    con.execute("INSERT INTO resources VALUES ('p2','Patient',?::JSON,'p2')", [_P2_RESOURCE])
    con.execute("INSERT INTO resources VALUES ('o2','Observation',?::JSON,'p2')", [_P2_OBS])


def _population_rows(cql: str, names: list[str]) -> tuple[dict, dict]:
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql), output_columns={n: n for n in names}
    )
    py = _python_only_connection()
    cpp = _cpp_connection()
    out: dict[str, dict] = {}
    try:
        for label, con in (("python", py), ("native", cpp)):
            _seed_two_patients(con)
            rows = con.execute(sql).fetchall()
            columns = [d[0] for d in con.execute(sql).description]
            per_patient = {}
            for row in rows:
                values = dict(zip(columns, row))
                pid = values.get("patient_id")
                per_patient[pid] = _normalize(tuple(values[n] for n in names))
            out[label] = per_patient
    finally:
        py.close()
        cpp.close()
    return out["python"], out["native"]


def test_explorer_qa001_deep_navigation_define_alias() -> None:
    """QA-001: `define CC: Obs.component.code.coding.code` must be usable by
    every list operator consumer (CQL 1.5 define referential transparency)."""
    cql = """
library T version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Obs: [Observation]
define CC: Obs.component.code.coding.code
define CountCC: Count(CC)
define FirstCC: First(CC)
define ContainsHR: CC contains '8867-4'
define IncludesBP: CC includes '8480-6'
define DistinctCount: Count(distinct CC)
define ExceptHR: Count(CC except '8867-4')
define IntersectHR: Count(CC intersect { '8867-4' })
"""
    names = ["CountCC", "FirstCC", "ContainsHR", "IncludesBP",
             "DistinctCount", "ExceptHR", "IntersectHR"]
    py, native = _population_rows(cql, names)
    assert py == native
    assert py["p1"] == (2, "8480-6", False, True, 2, 2, 0)
    assert py["p2"] == (2, "8867-4", True, False, 1, 0, 1)  # 2 dup components -> Count 2, distinct 1


def test_explorer_qa002_chained_list_operators() -> None:
    """QA-002: inline chaining (except/intersect/distinct/flatten feeding
    includes) must translate to executable SQL (CQL 1.5 App B List Ops)."""
    cases = [
        ("({1,3,5} except {1}) includes 5", True),
        ("({ 1, 1, 3, 5, 5 } except distinct { 1, 3 }) includes 5", True),
        ("({1,3,5} intersect {3,5}) includes 5", True),
        ("{1,3,5} includes (distinct {5,5})", True),
        ("(Flatten({{1,2},{3}})) includes 3", True),
        ("{1,3,5} except 3", [1, 5]),
    ]
    for expr, expected in cases:
        cql = f"""
library T version '1.0.0'
using FHIR version '4.0.1'
context Patient
define R: {expr}
"""
        py, native = _population_rows(cql, ["R"])
        assert py == native, expr
        assert py["p1"][0] == expected, (expr, py["p1"])


def test_explorer_qa003_includes_null_semantics() -> None:
    """QA-003: includes/included-in singleton overload follows contains/in
    null-element semantics (CQL 1.5 §10.10/§10.11)."""
    cases = [
        ("{null, 1} includes null", True),
        ("{1, 3} includes null", False),
        ("null included in {1, null, 3}", True),
        ("null included in {1, 3}", False),
    ]
    for expr, expected in cases:
        cql = f"""
library T version '1.0.0'
using FHIR version '4.0.1'
context Patient
define R: {expr}
"""
        py, native = _population_rows(cql, ["R"])
        assert py == native, expr
        assert py["p1"][0] == expected, (expr, py["p1"])
    # List-list overload with a typed-null list lowers to a NULL expression
    # (rendered False by the boolean population convention).
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(
            "library T version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define R: {1,3} includes (null as List<Integer>)\n"
        ),
        output_columns={"R": "R"},
    )
    assert "WHERE NULL" in sql


def test_explorer_qa004_first_through_two_alias_levels() -> None:
    """QA-004: First over an alias-of-distinct-of-alias returns the first
    element, not the whole list (CQL 1.5 §10.8 First)."""
    cql = """
library T version '1.0.0'
using FHIR version '4.0.1'
context Patient
define A_Lit: {10, 20, 30}
define A2: distinct A_Lit
define FirstA2: First(A2)
define LastA2: Last(A2)
"""
    py, native = _population_rows(cql, ["FirstA2", "LastA2"])
    assert py == native
    assert py["p1"] == (10, 30)


def test_explorer_qa005_heterogeneous_list_literal_translation_error() -> None:
    """QA-005: a String/numeric heterogeneous list literal has no common
    element type and must fail at translation time (CQL 1.5 App B List
    selector), not as a DuckDB conversion error."""
    from fhir4ds.cql.errors import TranslationError

    for expr in ("{1, 'x'}", "distinct { 1, 1.0, 2, 2.0, 'x', null, null }"):
        with pytest.raises(TranslationError):
            CQLToSQLTranslator().translate_library_to_sql(
                parse_cql(
                    "library T version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
                    f"define R: {expr}\n"
                )
            )
    # Compatible lists still translate.
    CQLToSQLTranslator().translate_library_to_sql(
        parse_cql(
            "library T version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
            "define R: {1, 1.0, 2, null}\n"
        )
    )
