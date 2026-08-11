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
        "IncludesNullSingletonAbsent": (None,),
        "IncludesQuantityEquivalent": (True,),
        "IncludedInNullList": (True,),
        "IncludedInNullSingleton": (None,),
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

