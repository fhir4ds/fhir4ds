"""CQL structural type operator parser/translator and DuckDB parity checks."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.errors import TranslationError
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_date_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_quantity_udf,
    fhirpath_repeat_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
    fhirpath_timestamp_udf,
)


def _register_forced_python_fhirpath(con: duckdb.DuckDBPyConnection) -> None:
    con.create_function("fhirpath", fhirpath_scalar, return_type="VARCHAR[]")
    con.create_function("fhirpath_text", fhirpath_text_udf, null_handling="special")
    con.create_function("fhirpath_bool", fhirpath_bool_udf, null_handling="special")
    con.create_function("fhirpath_number", fhirpath_number_udf, null_handling="special")
    con.create_function("fhirpath_date", fhirpath_date_udf, null_handling="special")
    con.create_function("fhirpath_json", fhirpath_json_udf, null_handling="special")
    con.create_function("fhirpath_timestamp", fhirpath_timestamp_udf, null_handling="special")
    con.create_function("fhirpath_quantity", fhirpath_quantity_udf, null_handling="special")
    con.create_function("fhirpath_repeat", fhirpath_repeat_udf, return_type="VARCHAR[]", null_handling="special")


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_forced_python_fhirpath(con)
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=False)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_structural_type_expressions_parse_and_translate() -> None:
    is_expr = parse_expression("true is Boolean")
    as_expr = parse_expression("true as Boolean")
    cast_expr = parse_expression("cast true as Boolean")
    convert_expr = parse_expression("convert '5' to Integer")
    children_expr = parse_expression("Children({ a: 1 })")
    descendants_expr = parse_expression("Descendants({ a: { b: 1 } })")

    assert isinstance(is_expr, BinaryExpression)
    assert is_expr.operator == "is"
    assert isinstance(as_expr, BinaryExpression)
    assert as_expr.operator == "as"
    assert not as_expr.strict
    assert isinstance(cast_expr, BinaryExpression)
    assert cast_expr.operator == "as"
    assert cast_expr.strict
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
define IsChoice: 5 is Choice<Integer, String>
define IsTuple: { a: 1 } is Tuple { a: Integer }
define Converted: convert '5' to Integer
define ConvertAnyPreservesSourceType: (convert 5 to Any) as String
define ChildrenTuple: Children({ a: 1, b: { c: 2 }, d: {3, 4}, n: null })
define DescendantsTuple: Descendants({ a: { b: 1 }, c: {2, 3} })
define MessageAsInterval: Message(null, true, 'NOT_IMPLEMENTED', 'Error', 'x') as Interval<DateTime>
"""
    translated = translate_cql(cql)
    assert set(translated) == {
        "IsBool",
        "AsBool",
        "IsChoice",
        "IsTuple",
        "Converted",
        "ConvertAnyPreservesSourceType",
        "ChildrenTuple",
        "DescendantsTuple",
        "MessageAsInterval",
    }
    assert translated["IsBool"].to_sql() == "TRUE"
    assert "value=True" in str(translated["AsBool"])
    assert translated["Converted"].to_sql() == "ToInteger('5')"
    assert translated["ConvertAnyPreservesSourceType"].to_sql() == "NULL"
    assert translated["ChildrenTuple"].to_sql().startswith("cqlChildren(")
    assert translated["DescendantsTuple"].to_sql().startswith("cqlDescendants(")
    assert translated["MessageAsInterval"].to_sql() == (
        "CQLMessage(NULL, TRUE, 'NOT_IMPLEMENTED', 'Error', 'x')"
    )


def test_cql_structural_type_rejects_unknown_targets() -> None:
    header = "library BadTypes version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    for expression in [
        "5 is DefinitelyNotAType",
        "5 as DefinitelyNotAType",
        "convert 'x' to DefinitelyNotAType",
        "5 as FHIR.DefinitelyNotAType",
    ]:
        with pytest.raises(TranslationError, match=r"unknown type '(FHIR\.)?DefinitelyNotAType'"):
            translate_cql(header + f"define Bad: {expression}\n")


def test_cql_fhir_datatype_targets_accept_extension_value_assertions() -> None:
    translated = translate_cql(
        """library FhirTypeTargets version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Extension Value As Coding":
  singleton from (
    Patient.extension E
      where E.url = 'http://example.org/some-extension'
      return E.value as FHIR.Coding
  )
define "Extension Value Is Coding":
  exists (
    Patient.extension E
      where E.url = 'http://example.org/some-extension'
        and (E.value is FHIR.Coding)
  )
define "Extension Value Cast Coding":
  singleton from (
    Patient.extension E
      where E.url = 'http://example.org/some-extension'
      return cast E.value as FHIR.Coding
  )
define "Extension Value As Instant":
  singleton from (
    Patient.extension E
      where E.url = 'http://example.org/some-instant-extension'
      return E.value as FHIR.instant
  )
define "Extension Value As Period":
  singleton from (
    Patient.extension E
      where E.url = 'http://example.org/some-period-extension'
      return E.value as FHIR.Period
  )
"""
    )

    assert set(translated) == {
        "Extension Value As Coding",
        "Extension Value Is Coding",
        "Extension Value Cast Coding",
        "Extension Value As Instant",
        "Extension Value As Period",
    }
    coding_sql = translated["Extension Value As Coding"].to_sql()
    assert "type().name" in coding_sql
    assert "resourceType" not in coding_sql


def test_cql_fhir_datatype_assertion_uses_runtime_fhir_type_name() -> None:
    cql = """library RuntimeFhirTypeTargets version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EncounterClassAsCoding: First([Encounter] E return E.class as FHIR.Coding)
define ObservationValueStringAsCoding: First([Observation] O return O.value as FHIR.Coding)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "encounter_class_as_coding": "EncounterClassAsCoding",
            "observation_value_string_as_coding": "ObservationValueStringAsCoding",
        },
    )
    assert "type().name" in sql

    rows = [
        ("p1", "Patient", "p1", {"resourceType": "Patient", "id": "p1"}),
        (
            "p1",
            "Encounter",
            "e1",
            {
                "resourceType": "Encounter",
                "id": "e1",
                "subject": {"reference": "Patient/p1"},
                "class": {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                    "code": "AMB",
                },
            },
        ),
        (
            "p1",
            "Observation",
            "o1",
            {
                "resourceType": "Observation",
                "id": "o1",
                "subject": {"reference": "Patient/p1"},
                "valueString": '{"system":"http://loinc.org","code":"1234-5"}',
            },
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                """
                CREATE TABLE resources (
                    patient_ref VARCHAR,
                    resourceType VARCHAR,
                    id VARCHAR,
                    resource JSON
                )
                """
            )
            for patient_ref, resource_type, resource_id, resource in rows:
                con.execute(
                    "INSERT INTO resources VALUES (?, ?, ?, ?::JSON)",
                    [patient_ref, resource_type, resource_id, json.dumps(resource)],
                )

        py_result = py.execute(sql).fetchone()
        cpp_result = cpp.execute(sql).fetchone()
        assert cpp_result == py_result
        assert py_result == (
            "p1",
            '{"system":"http://terminology.hl7.org/CodeSystem/v3-ActCode","code":"AMB"}',
            None,
        )
    finally:
        py.close()
        cpp.close()


def test_cql_structural_strict_cast_differs_from_nullable_as() -> None:
    translated = translate_cql(
        """library StructuralStrictCast version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AsMismatch: 5 as String
define CastMismatch: cast 5 as String
define CastQuantityMismatch: cast 5 as Quantity
define CastMatch: cast 5 as Integer
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert con.execute(f"SELECT {translated['AsMismatch'].to_sql()}").fetchone() == (None,)
            assert con.execute(f"SELECT {translated['CastMatch'].to_sql()}").fetchone() == (5,)
            for name in ("CastMismatch", "CastQuantityMismatch"):
                sql = translated[name].to_sql()
                assert "CQL strict cast failed" in sql
                with pytest.raises(duckdb.Error, match="CQL strict cast failed"):
                    con.execute(f"SELECT {sql}").fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_structural_strict_cast_survives_function_inlining() -> None:
    translated = translate_cql(
        """library StructuralStrictCastFunction version '1.0.0'
using FHIR version '4.0.1'
context Patient
define function StrictString(x Any): cast x as String
define function NullableString(x Any): x as String
define StrictFunctionMismatch: StrictString(5)
define StrictFunctionMatch: StrictString('ok')
define NullableFunctionMismatch: NullableString(5)
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert con.execute(
                f"SELECT {translated['StrictFunctionMatch'].to_sql()}"
            ).fetchone() == ("ok",)
            assert con.execute(
                f"SELECT {translated['NullableFunctionMismatch'].to_sql()}"
            ).fetchone() == (None,)
            with pytest.raises(duckdb.Error, match="CQL strict cast failed"):
                con.execute(
                    f"SELECT {translated['StrictFunctionMismatch'].to_sql()}"
                ).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_structural_traversal_preserves_nested_primitive_type_tags() -> None:
    translated = translate_cql(
        """library StructuralNestedTraversal version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NestedDateDescendants: Descendants({ a: { d: @2024-01-01 } })
define NestedDateDescendantIsDate: Last(Descendants({ a: { d: @2024-01-01 } })) is Date
define NestedDateDescendantAsDate: Last(Descendants({ a: { d: @2024-01-01 } })) as Date
define NestedTimeDescendantIsTime: Last(Descendants({ a: { t: @T10:00:00 } })) is Time
define ListDateChildIsDate: First(Children({ a: {@2024-01-01} })) is Date
define ListDateChildAsDate: First(Children({ a: {@2024-01-01} })) as Date
define NestedLongDescendantIsLong: Last(Descendants({ a: { l: 1L } })) is Long
define NestedLongDescendantIsInteger: Last(Descendants({ a: { l: 1L } })) is Integer
"""
    )
    expected = {
        "NestedDateDescendantIsDate": (True,),
        "NestedDateDescendantAsDate": ("2024-01-01",),
        "NestedTimeDescendantIsTime": (True,),
        "ListDateChildIsDate": (True,),
        "ListDateChildAsDate": ("2024-01-01",),
        "NestedLongDescendantIsLong": (True,),
        "NestedLongDescendantIsInteger": (False,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            py_result = py.execute(f"SELECT {expr.to_sql()}").fetchone()
            cpp_result = cpp.execute(f"SELECT {expr.to_sql()}").fetchone()
            assert cpp_result == py_result, name
            if name == "NestedDateDescendants":
                assert py_result == (
                    [
                        '{"d":{"__fhir4ds_cql_type":"Date","value":"2024-01-01"}}',
                        '{"__fhir4ds_cql_type":"Date","value":"2024-01-01"}',
                    ],
                )
            else:
                assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_structural_type_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(
        """library StructuralExecution version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ChildrenTuple: Children({ a: 1, b: { c: 2 }, d: {3, 4}, n: null })
define DescendantsTuple: Descendants({ a: { b: 1 }, c: {2, 3} })
define ChildIntIsInteger: First(Children({ a: 1 })) is Integer
define ChildBoolIsBoolean: First(Children({ a: true })) is Boolean
define ChildStringAsInteger: First(Children({ a: '1' })) as Integer
define ChildDateIsDate: First(Children({ a: @2024-01-01 })) is Date
define ChildDateIsNotString: First(Children({ a: @2024-01-01 })) is String
define ChildDateAsDate: First(Children({ a: @2024-01-01 })) as Date
define ChildDateTimeIsDateTime: First(Children({ a: @2024-01-01T10:00:00 })) is DateTime
define ChildTimeIsTime: First(Children({ a: @T10:00:00 })) is Time
define ChildLongIsLong: First(Children({ a: 1L })) is Long
define ChildLongIsNotInteger: First(Children({ a: 1L })) is Integer
define ChildLongAsLong: First(Children({ a: 1L })) as Long
define ChildrenIsListAny: Children({ a: 1 }) is List<Any>
define ChildrenIntsIsListInteger: Children({ a: 1, b: {2}, n: null }) is List<Integer>
define ChildrenMixedIsNotListInteger: Children({ a: 1, b: 'x' }) is List<Integer>
define ChildrenAsListAny: Children({ a: 1 }) as List<Any>
define CountChildrenSkipsNull: Count(Children({ a: 1, n: null }))
define ExistsOnlyNullChild: exists Children({ a: null })
define QuantityIsTrue: 5 'mg' is Quantity
define IntegerIsNotQuantity: 5 is Quantity
define QuantityAsQuantity: 5 'mg' as Quantity
define IntegerAsQuantity: 5 as Quantity
define StringConvertToQuantity: convert '5 ''mg''' to Quantity
define QuantityConvertToString: convert 5 'mg' to String
define ConvertedQuantityConvertToString: convert (convert '5 ''mg''' to Quantity) to String
define StringConvertToRatio: convert '10 ''mg'':2 ''mL''' to Ratio
define RatioConvertToString: convert ToRatio('10 ''mg'':2 ''mL''') to String
define StringConvertToConcept: convert '{"code":"x","system":"s"}' to Concept
define StringConvertToPatient: convert 'x' to Patient
define ConvertIntegerAnyAsString: (convert 5 to Any) as String
define ConvertStringAnyAsInteger: (convert '5' to Any) as Integer
define ConvertIntegerAnyIsString: (convert 5 to Any) is String
define ConvertStringAnyIsInteger: (convert '5' to Any) is Integer
define ConvertDateAnyIsDateTime: (convert @2024-01-01 to Any) is DateTime
define ListIsList: {1, 2} is List<Integer>
define IntegerIsNotList: 5 is List<Integer>
define ListAsList: {1, 2} as List<Integer>
define IntegerAsList: 5 as List<Integer>
define NullListIsList: (null as List<Integer>) is List<Integer>
define NullListAsList: null as List<Integer>
define MixedListAsListInteger: {1, 'x'} as List<Integer>
define MixedListIsListInteger: {1, 'x'} is List<Integer>
define IntegerIsChoice: 5 is Choice<Integer, String>
define StringAsChoice: 'abc' as Choice<Integer, String>
define BoolAsChoice: true as Choice<Integer, String>
define TupleIsTuple: { a: 1 } is Tuple { a: Integer }
define TupleStringIsNotTuple: { a: '1' } is Tuple { a: Integer }
define TupleAsTuple: { a: 1 } as Tuple { a: Integer }
define IntervalIsDateInterval: Interval[@2024-01-01, @2024-01-31] is Interval<Date>
define IntegerIsNotInterval: 5 is Interval<Date>
define IntervalAsDateInterval: Interval[@2024-01-01, @2024-01-31] as Interval<Date>
define IntegerAsInterval: 5 as Interval<Date>
define RatioIsRatio: ToRatio('10 ''mg'':2 ''mL''') is Ratio
define RatioAsRatio: ToRatio('10 ''mg'':2 ''mL''') as Ratio
define DateIsDate: @2024-01-01 is Date
define DateIsNotDateTime: @2024-01-01 is DateTime
define DateAsDateTime: @2024-01-01 as DateTime
define DateTimeIsDateTime: @2024-01-01T00:00:00 is DateTime
define DateTimeIsNotDate: @2024-01-01T00:00:00 is Date
define TimeIsTime: @T10:00:00 is Time
define TimeIsNotDate: @T10:00:00 is Date
define ListAlias: {1, 2}
define ListAliasIsList: ListAlias is List<Integer>
define ListAliasAsList: ListAlias as List<Integer>
define DateAlias: @2024-01-01
define DateAliasIsDate: DateAlias is Date
define DateAliasIsNotDateTime: DateAlias is DateTime
define DateAliasAsDate: DateAlias as Date
define RatioAlias: ToRatio('10 ''mg'':2 ''mL''')
define RatioAliasIsRatio: RatioAlias is Ratio
define RatioAliasAsRatio: RatioAlias as Ratio
"""
    )
    expected = {
        "ChildrenTuple": (
            [
                '{"__fhir4ds_cql_type":"Integer","value":1}',
                '{"c":2}',
                '{"__fhir4ds_cql_type":"Integer","value":3}',
                '{"__fhir4ds_cql_type":"Integer","value":4}',
                None,
            ],
        ),
        "DescendantsTuple": (
            [
                '{"b":1}',
                '{"__fhir4ds_cql_type":"Integer","value":1}',
                '{"__fhir4ds_cql_type":"Integer","value":2}',
                '{"__fhir4ds_cql_type":"Integer","value":3}',
            ],
        ),
        "ChildIntIsInteger": (True,),
        "ChildBoolIsBoolean": (True,),
        "ChildStringAsInteger": (None,),
        "ChildDateIsDate": (True,),
        "ChildDateIsNotString": (False,),
        "ChildDateAsDate": ("2024-01-01",),
        "ChildDateTimeIsDateTime": (True,),
        "ChildTimeIsTime": (True,),
        "ChildLongIsLong": (True,),
        "ChildLongIsNotInteger": (False,),
        "ChildLongAsLong": (1,),
        "ChildrenIsListAny": (True,),
        "ChildrenIntsIsListInteger": (True,),
        "ChildrenMixedIsNotListInteger": (False,),
        "ChildrenAsListAny": (['{"__fhir4ds_cql_type":"Integer","value":1}'],),
        "CountChildrenSkipsNull": (1,),
        "ExistsOnlyNullChild": (False,),
        "QuantityIsTrue": (True,),
        "IntegerIsNotQuantity": (False,),
        "IntegerAsQuantity": (None,),
        "QuantityConvertToString": ("5 'mg'",),
        "ConvertedQuantityConvertToString": ("5 'mg'",),
        "RatioConvertToString": ("10.0 'mg':2.0 'mL'",),
        "StringConvertToPatient": (None,),
        "ConvertIntegerAnyAsString": (None,),
        "ConvertStringAnyAsInteger": (None,),
        "ConvertIntegerAnyIsString": (False,),
        "ConvertStringAnyIsInteger": (False,),
        "ConvertDateAnyIsDateTime": (False,),
        "ListIsList": (True,),
        "IntegerIsNotList": (False,),
        "ListAsList": ([1, 2],),
        "IntegerAsList": (None,),
        "NullListIsList": (False,),
        "NullListAsList": (None,),
        "MixedListAsListInteger": (None,),
        "MixedListIsListInteger": (False,),
        "IntegerIsChoice": (True,),
        "StringAsChoice": ("abc",),
        "BoolAsChoice": (None,),
        "TupleIsTuple": (True,),
        "TupleStringIsNotTuple": (False,),
        "IntervalIsDateInterval": (True,),
        "IntegerIsNotInterval": (False,),
        "IntegerAsInterval": (None,),
        "RatioIsRatio": (True,),
        "DateIsDate": (True,),
        "DateIsNotDateTime": (False,),
        "DateAsDateTime": (None,),
        "DateTimeIsDateTime": (True,),
        "DateTimeIsNotDate": (False,),
        "TimeIsTime": (True,),
        "TimeIsNotDate": (False,),
        "ListAlias": ([1, 2],),
        "ListAliasIsList": (True,),
        "ListAliasAsList": ([1, 2],),
        "DateAlias": ("2024-01-01",),
        "DateAliasIsDate": (True,),
        "DateAliasIsNotDateTime": (False,),
        "DateAliasAsDate": ("2024-01-01",),
        "RatioAliasIsRatio": (True,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            if name in {"QuantityAsQuantity", "StringConvertToQuantity"}:
                assert json.loads(cpp_result[0]) == json.loads(py_result[0]), name
            else:
                assert cpp_result == py_result, name
            if name in expected:
                assert py_result == expected[name], name

        for name in ["QuantityAsQuantity", "StringConvertToQuantity"]:
            value = py.execute(f"SELECT {translated[name].to_sql()}").fetchone()[0]
            assert json.loads(value) == {
                "value": 5.0,
                "unit": "mg",
                "code": "mg",
                "system": "http://unitsofmeasure.org",
            }

        ratio = json.loads(py.execute(
            f"SELECT {translated['StringConvertToRatio'].to_sql()}"
        ).fetchone()[0])
        assert ratio["numerator"]["value"] == 10.0
        assert ratio["numerator"]["unit"] == "mg"
        assert ratio["denominator"]["value"] == 2.0
        assert ratio["denominator"]["unit"] == "mL"

        concept = json.loads(py.execute(
            f"SELECT {translated['StringConvertToConcept'].to_sql()}"
        ).fetchone()[0])
        assert concept == {"codes": [{"code": "x", "system": "s"}]}

        interval = json.loads(py.execute(
            f"SELECT {translated['IntervalAsDateInterval'].to_sql()}"
        ).fetchone()[0])
        assert interval == {
            "low": "2024-01-01",
            "high": "2024-01-31",
            "lowClosed": True,
            "highClosed": True,
        }

        tuple_as = json.loads(py.execute(
            f"SELECT {translated['TupleAsTuple'].to_sql()}"
        ).fetchone()[0])
        assert tuple_as == {"a": 1}

        ratio_as = json.loads(py.execute(
            f"SELECT {translated['RatioAsRatio'].to_sql()}"
        ).fetchone()[0])
        assert ratio_as["numerator"]["value"] == 10.0
        assert ratio_as["numerator"]["unit"] == "mg"
        assert ratio_as["denominator"]["value"] == 2.0
        assert ratio_as["denominator"]["unit"] == "mL"

        ratio_alias = json.loads(py.execute(
            f"SELECT {translated['RatioAliasAsRatio'].to_sql()}"
        ).fetchone()[0])
        assert ratio_alias["numerator"]["value"] == 10.0
        assert ratio_alias["denominator"]["value"] == 2.0
    finally:
        py.close()
        cpp.close()


def test_cql_structural_quantity_assertion_preserves_fhir_quantity_comparison() -> None:
    cql = """library StructuralQuantity version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EstimatedGestationalAge: First([Observation] O return O.value as Quantity)
define GestationalAgeAtLeast37Weeks: EstimatedGestationalAge >= 37 'weeks'
define GestationalAgeToString: convert EstimatedGestationalAge to String
"""
    library = parse_cql(cql)
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={
            "estimated_gestational_age": "EstimatedGestationalAge",
            "gestational_age_at_least_37_weeks": "GestationalAgeAtLeast37Weeks",
            "gestational_age_to_string": "GestationalAgeToString",
        },
    )
    setup_sql = [
        """
        CREATE TABLE resources (
            patient_ref VARCHAR,
            resourceType VARCHAR,
            id VARCHAR,
            resource JSON
        )
        """,
        """
        INSERT INTO resources VALUES
        ('p1', 'Patient', 'p1', '{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1', 'Observation', 'o1', '{"resourceType":"Observation","id":"o1","subject":{"reference":"Patient/p1"},"valueQuantity":{"value":38,"unit":"weeks","code":"weeks","system":"http://unitsofmeasure.org"}}'::JSON),
        ('p2', 'Patient', 'p2', '{"resourceType":"Patient","id":"p2"}'::JSON),
        ('p2', 'Observation', 'o2', '{"resourceType":"Observation","id":"o2","subject":{"reference":"Patient/p2"},"valueQuantity":{"value":37,"unit":"cm","code":"cm","system":"http://unitsofmeasure.org"}}'::JSON)
        """,
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for statement in setup_sql:
                con.execute(statement)

        py_rows = {row[0]: row for row in py.execute(sql).fetchall()}
        cpp_rows = {row[0]: row for row in cpp.execute(sql).fetchall()}
        assert cpp_rows.keys() == py_rows.keys()
        assert json.loads(cpp_rows["p1"][1]) == json.loads(py_rows["p1"][1])
        assert json.loads(cpp_rows["p2"][1]) == json.loads(py_rows["p2"][1])
        assert cpp_rows["p1"][2] == py_rows["p1"][2]
        assert cpp_rows["p2"][2] == py_rows["p2"][2]
        # CQL 1.5 ToString Table 9-G + CQL-06 doctrine: calendar-duration
        # keyword units (weeks) render bare; UCUM units (cm) stay quoted.
        assert cpp_rows["p1"][3] == py_rows["p1"][3] == "38 weeks"
        assert cpp_rows["p2"][3] == py_rows["p2"][3] == "37 'cm'"
        quantity = json.loads(py_rows["p1"][1])
        assert quantity["value"] == 38
        assert quantity["code"] == "weeks"
        assert py_rows["p1"][2] is True
        assert json.loads(py_rows["p2"][1])["code"] == "cm"
        assert py_rows["p2"][2] is False
    finally:
        py.close()
        cpp.close()


def test_cql_structural_concept_assertion_preserves_fhir_codeable_concept_equivalence() -> None:
    cql = """library StructuralConcept version '1.0.0'
using FHIR version '4.0.1'
codesystem SNOMED: 'http://snomed.info/sct'
code "Target Stage": '1228889001' from SNOMED display 'target'
context Patient
define HasTargetConcept: exists ([Observation] O where O.value as Concept ~ "Target Stage")
"""
    library = parse_cql(cql)
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={"has_target_concept": "HasTargetConcept"},
    )
    setup_sql = [
        """
        CREATE TABLE resources (
            patient_ref VARCHAR,
            resourceType VARCHAR,
            id VARCHAR,
            resource JSON
        )
        """,
        """
        INSERT INTO resources VALUES
        ('p1', 'Patient', 'p1', '{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1', 'Observation', 'o1', '{"resourceType":"Observation","id":"o1","subject":{"reference":"Patient/p1"},"valueCodeableConcept":{"coding":[{"system":"http://snomed.info/sct","code":"1228889001"}]}}'::JSON)
        """,
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for statement in setup_sql:
                con.execute(statement)
        assert py.execute(sql).fetchone() == ("p1", True)
        assert cpp.execute(sql).fetchone() == ("p1", True)
    finally:
        py.close()
        cpp.close()


def test_cql_structural_children_clinical_and_conversion_parity() -> None:
    translated = translate_cql(
        """library StructuralClinical version '1.0.0'
using FHIR version '4.0.1'
codesystem LOINC: 'http://loinc.org'
code "Systolic": '8480-6' from LOINC display 'Systolic BP'
concept "BP": { "Systolic" } display 'Blood pressure'
context Patient
define ChildCodeIsCode: First(Children({ a: "Systolic" })) is Code
define ChildCodeAsConcept: First(Children({ a: "Systolic" })) as Concept
define ChildIntAsCode: First(Children({ a: 1 })) as Code
define ChildConceptIsConcept: First(Children({ a: "BP" })) is Concept
define ChildConceptAsCode: First(Children({ a: "BP" })) as Code
define ListCodeToConcept: convert { "Systolic" } to Concept
define ConceptToListCode: convert "BP" to List<Code>
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            assert cpp_result == py_result, name

        assert py.execute(f"SELECT {translated['ChildCodeIsCode'].to_sql()}").fetchone() == (True,)
        assert py.execute(f"SELECT {translated['ChildCodeAsConcept'].to_sql()}").fetchone() == (None,)
        assert py.execute(f"SELECT {translated['ChildIntAsCode'].to_sql()}").fetchone() == (None,)
        assert py.execute(f"SELECT {translated['ChildConceptIsConcept'].to_sql()}").fetchone() == (True,)
        assert py.execute(f"SELECT {translated['ChildConceptAsCode'].to_sql()}").fetchone() == (None,)

        concept = json.loads(py.execute(
            f"SELECT {translated['ListCodeToConcept'].to_sql()}"
        ).fetchone()[0])
        assert concept == {
            "codes": [{"code": "8480-6", "system": "http://loinc.org", "display": "Systolic BP"}]
        }

        codes = py.execute(f"SELECT {translated['ConceptToListCode'].to_sql()}").fetchone()[0]
        assert [json.loads(code) for code in codes] == [
            {"code": "8480-6", "system": "http://loinc.org", "display": "Systolic BP"}
        ]
    finally:
        py.close()
        cpp.close()


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
        assert py.execute(
            "SELECT COUNT(*) FROM duckdb_functions() WHERE lower(function_name) = 'fhirpath_predicate'"
        ).fetchone() == (0,)
        assert cpp.execute(
            "SELECT COUNT(*) FROM duckdb_functions() WHERE lower(function_name) = 'fhirpath_predicate'"
        ).fetchone() == (1,)
        for sql, params in expressions:
            assert cpp.execute(sql, params).fetchone() == py.execute(sql, params).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_structural_forced_python_fhirpath_choice_is_as_matches_cpp() -> None:
    resource = json.dumps({"resourceType": "Observation", "valueInteger": 7})
    expressions = [
        ("SELECT fhirpath(?::JSON, 'value.is(Integer)')", [resource], (["true"],)),
        ("SELECT fhirpath_bool(?::JSON, 'value.is(Integer)')", [resource], (True,)),
        ("SELECT fhirpath_bool(?::JSON, 'value.is(System.Integer)')", [resource], (False,)),
        ("SELECT fhirpath_bool(?::JSON, 'Observation.value.is(Integer)')", [resource], (True,)),
        ("SELECT fhirpath_bool(?::JSON, 'value.is(String)')", [resource], (False,)),
        ("SELECT fhirpath_text(?::JSON, 'value.as(Integer)')", [resource], ("7",)),
        ("SELECT fhirpath_number(?::JSON, 'value.as(Integer)')", [resource], (7.0,)),
        ("SELECT fhirpath_json(?::JSON, 'value.as(Integer)')", [resource], ("[7]",)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        assert py.execute(
            "SELECT COUNT(*) FROM duckdb_functions() WHERE lower(function_name) = 'fhirpath_predicate'"
        ).fetchone() == (0,)
        for sql, params, expected in expressions:
            py_result = py.execute(sql, params).fetchone()
            cpp_result = cpp.execute(sql, params).fetchone()
            assert cpp_result == py_result
            assert py_result == expected
    finally:
        py.close()
        cpp.close()


def test_cql_structural_bare_numeric_ratio_literal_parses_per_spec() -> None:
    """CQL 1.5.3 §Types/Ratio and §Equal Ratio examples.

    The bare numeric ratio literal form ``<quantity>:<quantity>`` (with
    default UCUM unit '1' on both components) is used throughout the
    spec's own Ratio examples:

        define "RatioEqualIsTrue": 1:8 = 1:8
        define "RatioEqualIsFalse": 1:8 = 2:16
        define "RatioEquivalentIsTrue": 1:8 ~ 2:16

    Previously ``parse_literal`` only routed unit-qualified quantities
    (``1 'mg':2 'mg'``) through ``_maybe_parse_ratio_literal``; bare
    Integer/Decimal/Long numerics returned a ``Literal`` directly,
    silently dropping the ``:<denominator>`` and leaving a dangling
    COLON that raised ``ParseError`` at the library level.
    """
    # Parser-level: bare numeric ratio literal must produce a FunctionRef
    # (ToRatio) on both Integer and Decimal numerators.
    assert isinstance(parse_expression("1:8"), FunctionRef)
    assert isinstance(parse_expression("1.5:2.5"), FunctionRef)
    # Bare numerics without a trailing colon are unaffected.
    from fhir4ds.cql.parser.ast_nodes import Literal
    assert isinstance(parse_expression("5"), Literal)
    assert isinstance(parse_expression("5.5"), Literal)

    # Translator + execution: spec Ratio equality/equivalence examples.
    cql = (
        "library RatioSpec version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "context Patient\n"
        "define RatioEqualIsTrue: 1:8 = 1:8\n"
        "define RatioEqualIsFalse: 1:8 = 2:16\n"
        "define RatioEquivalentIsTrue: 1:8 ~ 2:16\n"
        "define RatioEquivalentScaled: 1:100 ~ 10:1000\n"
        "define DecimalRatio: 1.5:2.5\n"
    )
    translated = translate_cql(cql)
    # Ratio equality/equivalence lowers to ratioCompare UDF (Ratio is a
    # structured type; tuple equality is UDF-implemented).
    assert "ratioCompare" in translated["RatioEqualIsTrue"].to_sql()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expected = {
            "RatioEqualIsTrue": (True,),
            "RatioEqualIsFalse": (False,),
            "RatioEquivalentIsTrue": (True,),
            "RatioEquivalentScaled": (True,),
        }
        for define_name, want in expected.items():
            sql = f"SELECT {translated[define_name].to_sql()}"
            assert py.execute(sql).fetchone() == want
            assert cpp.execute(sql).fetchone() == want

        # Decimal-ratio numerator must produce a valid Ratio JSON value
        # on both backends.
        dec_sql = f"SELECT {translated['DecimalRatio'].to_sql()}"
        py_ratio = json.loads(py.execute(dec_sql).fetchone()[0])
        cpp_ratio = json.loads(cpp.execute(dec_sql).fetchone()[0])
        assert py_ratio == cpp_ratio
        assert py_ratio["numerator"]["value"] == 1.5
        assert py_ratio["denominator"]["value"] == 2.5
    finally:
        py.close()
        cpp.close()


def test_cql_structural_first_last_singleton_over_bare_retrieve() -> None:
    """CQL §22.12/§22.16/§22.30: First/Last/`singleton from` over a bare
    retrieve must generate valid per-patient SQL instead of referencing the
    retrieve CTE as a bare column."""
    library = """library StructuralBareRetrieve version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FirstObs: First([Observation])
define LastObs: Last([Observation])
define FirstEmpty: First([Encounter])
define SingletonPatient: singleton from [Patient]
define FirstObsAsObservation: First([Observation]) as Observation
define FirstObsAsPatient: First([Observation]) as Patient
define FirstObsIsObservation: First([Observation]) is Observation
"""
    translated = translate_cql(library)
    setup = [
        "CREATE TABLE resources (patient_ref VARCHAR, resourceType VARCHAR, id VARCHAR, resource JSON)",
        """INSERT INTO resources VALUES
        ('p1','Patient','p1','{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1','Observation','o1','{"resourceType":"Observation","id":"o1","subject":{"reference":"Patient/p1"}}'::JSON),
        ('p1','Observation','o2','{"resourceType":"Observation","id":"o2","subject":{"reference":"Patient/p1"}}'::JSON)""",
    ]
    # End-to-end population SQL is the authoritative reproducer (QA-001):
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(library),
        output_columns={
            "first_obs": "FirstObs",
            "first_empty": "FirstEmpty",
            "singleton_patient": "SingletonPatient",
            "first_obs_as_observation": "FirstObsAsObservation",
            "first_obs_as_patient": "FirstObsAsPatient",
            "first_obs_is_observation": "FirstObsIsObservation",
        },
    )
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for stmt in setup:
                con.execute(stmt)
        py_row = py.execute(sql).fetchone()
        cpp_row = cpp.execute(sql).fetchone()
        # First/Last over an unordered retrieve have no deterministic
        # element order; compare order-insensitively for those columns.
        def _norm(row):
            return tuple(
                json.dumps(json.loads(v), sort_keys=True) if isinstance(v, str) and v.startswith("{") else v
                for v in row
            )
        for _i, (_pv, _cv) in enumerate(zip(py_row, cpp_row)):
            if _i in (1, 2, 4, 5) and isinstance(_pv, str) and isinstance(_cv, str):
                # First/Last/as-Observation pick either observation under an
                # unordered retrieve; accept either id across backends.
                assert (
                    json.loads(_pv)["id"] in {"o1", "o2"}
                    and json.loads(_cv)["id"] in {"o1", "o2"}
                ), _i
            else:
                assert _cv == _pv, _i
        # Columns follow output_columns order: patient, FirstObs, FirstEmpty,
        # SingletonPatient, FirstObsAsObservation, FirstObsAsPatient,
        # FirstObsIsObservation.
        assert py_row[0] == "p1"
        assert json.loads(py_row[1])["id"] in {"o1", "o2"}
        assert py_row[2] is None  # First([Encounter]) on empty retrieve
        assert json.loads(py_row[3])["id"] == "p1"  # singleton from [Patient]
        assert json.loads(py_row[4])["resourceType"] == "Observation"
        assert py_row[5] is None  # Observation as Patient -> null (§As)
        assert py_row[6] is True
    finally:
        py.close()
        cpp.close()


def test_cql_structural_alias_over_list_and_traversal_sources() -> None:
    """QA-002/QA-004: where-clause aliases over list literals and
    Children()/Descendants() sources must bind per element (CQL §9, §22.9,
    §22.10), including `is` type tests on each element."""
    translated = translate_cql(
        """library StructuralAliasSources version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FromListWhereGt: Count(from {1,2,3} N where N > 1)
define FromListIsInteger: Count(from {'1', 'x'} N where N is Integer)
define ExistsListIsInteger: exists ({1, 2} N where N is Integer)
define ExistsChildIsInteger: exists (Children({ a: 1, b: 'x' }) C where C is Integer)
define ExistsDescendantIsInteger: exists (Descendants({ a: { b: 1 } }) D where D is Integer)
define ExistsDescendantIsNotString: exists (Descendants({ a: { b: 1 } }) D where D is String)
"""
    )
    py = _python_only_connection()
    cpp = _cpp_connection()
    expected = {
        "FromListWhereGt": (2,),
        "FromListIsInteger": (0,),
        "ExistsListIsInteger": (True,),
        "ExistsChildIsInteger": (True,),
        "ExistsDescendantIsInteger": (True,),
        "ExistsDescendantIsNotString": (False,),
    }
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

    # Retrieve-backed traversal with per-element is-checks (QA-002 end-to-end).
    cql = """library StructuralTraversalRetrieve version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DescendantsHaveQuantity: exists ([Observation] O where exists (Descendants(O) D where D is Quantity))
define ChildrenHaveFhirQuantity: exists ([Observation] O where exists (Children(O) C where C is FHIR.Quantity))
define DescendantIsDate: exists ([Observation] O where exists (Descendants(O) D where D is Date))
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "descendants_have_quantity": "DescendantsHaveQuantity",
            "children_have_fhir_quantity": "ChildrenHaveFhirQuantity",
            "descendant_is_date": "DescendantIsDate",
        },
    )
    setup = [
        "CREATE TABLE resources (patient_ref VARCHAR, resourceType VARCHAR, id VARCHAR, resource JSON)",
        """INSERT INTO resources VALUES
        ('p1','Patient','p1','{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1','Observation','o1','{"resourceType":"Observation","id":"o1","subject":{"reference":"Patient/p1"},"valueQuantity":{"value":38,"unit":"weeks","code":"weeks"},"status":"final"}'::JSON)""",
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for stmt in setup:
                con.execute(stmt)
        py_row = py.execute(sql).fetchone()
        cpp_row = cpp.execute(sql).fetchone()
        assert cpp_row == py_row
        assert py_row == ("p1", True, True, False)
    finally:
        py.close()
        cpp.close()


def test_cql_structural_fhir_string_family_satisfies_is_string() -> None:
    """CQL FHIR model mapping: FHIR string-family primitives (code, id, uri,
    ...) are System.String, so `is String` accepts them, while `is FHIR.string`
    still tests the exact FHIR type (status is FHIR.code, not FHIR.string)."""
    cql = """library StructuralStringFamily version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StatusIsString: exists ([Observation] O where O.status is String)
define StatusIsFhirString: exists ([Observation] O where O.status is FHIR.string)
define StatusIsFhirCode: exists ([Observation] O where O.status is FHIR.code)
define IdIsString: exists ([Observation] O where O.id is String)
define ValueIsString: exists ([Observation] O where O.value is String)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "status_is_string": "StatusIsString",
            "status_is_fhir_string": "StatusIsFhirString",
            "status_is_fhir_code": "StatusIsFhirCode",
            "id_is_string": "IdIsString",
            "value_is_string": "ValueIsString",
        },
    )
    setup = [
        "CREATE TABLE resources (patient_ref VARCHAR, resourceType VARCHAR, id VARCHAR, resource JSON)",
        """INSERT INTO resources VALUES
        ('p1','Patient','p1','{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1','Observation','o1','{"resourceType":"Observation","id":"o1","subject":{"reference":"Patient/p1"},"status":"final","valueString":"high"}'::JSON)""",
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for stmt in setup:
                con.execute(stmt)
        py_row = py.execute(sql).fetchone()
        cpp_row = cpp.execute(sql).fetchone()
        assert cpp_row == py_row
        assert py_row == ("p1", True, False, True, True, True)
    finally:
        py.close()
        cpp.close()


def test_cql_structural_as_cast_query_source_alias_binds_element_values() -> None:
    """QA-101: `X e return v as T a where a is T` must test the cast VALUE.

    CQL 1.5 §Query: a query source may be any expression; the alias binds to
    each element of its result.  §As: run-time mismatch yields null and
    `null is T` is false, so the count must only include rows whose cast
    succeeded (not every resource row).
    """
    cql = """library AsCastAlias version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QtyAliasedIsQty: Count([Observation] O return O.value as FHIR.Quantity Q where Q is FHIR.Quantity)
define QtyAliasedNotNull: Count([Observation] O return O.value as FHIR.Quantity Q where Q is not null)
define StrAliasedIsString: Count([Observation] O return O.value as FHIR.string S where S is String)
define StrAliasedIsFhirString: Count([Observation] O return O.value as FHIR.string S where S is FHIR.string)
define CodeAliasedIsCode: Count([Observation] O return O.status as FHIR.code C where C is FHIR.code)
define LiteralAsIsString: Count([Observation] O return 'x' as String X where X is String)
define AsMismatchIsType: Count([Observation] O return 'x' as Integer X where X is Integer)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "qty_aliased_is_qty": "QtyAliasedIsQty",
            "qty_aliased_not_null": "QtyAliasedNotNull",
            "str_aliased_is_string": "StrAliasedIsString",
            "str_aliased_is_fhir_string": "StrAliasedIsFhirString",
            "code_aliased_is_code": "CodeAliasedIsCode",
            "literal_as_is_string": "LiteralAsIsString",
            "as_mismatch_is_type": "AsMismatchIsType",
        },
    )
    rows = [
        ("p1", "Patient", "p1", {"resourceType": "Patient", "id": "p1"}),
        (
            "p1",
            "Observation",
            "o1",
            {
                "resourceType": "Observation",
                "id": "o1",
                "subject": {"reference": "Patient/p1"},
                "status": "final",
                "valueQuantity": {"value": 5.5, "unit": "mg"},
            },
        ),
        (
            "p1",
            "Observation",
            "o2",
            {
                "resourceType": "Observation",
                "id": "o2",
                "subject": {"reference": "Patient/p1"},
                "status": "final",
                "valueString": "text",
            },
        ),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                """
                CREATE TABLE resources (
                    patient_ref VARCHAR,
                    resourceType VARCHAR,
                    id VARCHAR,
                    resource JSON
                )
                """
            )
            for patient_ref, resource_type, resource_id, resource in rows:
                con.execute(
                    "INSERT INTO resources VALUES (?, ?, ?, ?::JSON)",
                    [patient_ref, resource_type, resource_id, json.dumps(resource)],
                )
        py_row = py.execute(sql).fetchone()
        cpp_row = cpp.execute(sql).fetchone()
        assert cpp_row == py_row
        # Alias binds cast VALUES: only o1 satisfies the Quantity cast,
        # only o2 satisfies the string cast; 'x' as Integer is null → 0.
        assert py_row == (
            "p1",
            1,  # qty_aliased_is_qty
            1,  # qty_aliased_not_null
            1,  # str_aliased_is_string
            1,  # str_aliased_is_fhir_string
            2,  # code_aliased_is_code
            2,  # literal_as_is_string
            0,  # as_mismatch_is_type
        )
    finally:
        py.close()
        cpp.close()


def test_cql_structural_traversal_over_nested_list_literals() -> None:
    """QA-102: Descendants/Children over list literals containing lists.

    CQL 1.5 §Children/§Descendants: a list source invokes the operator on each
    element and flattens; primitive elements have no children, so the result
    is empty — not a binder error from an untypable heterogeneous SQL array.
    """
    translated = translate_cql(
        """library NestedListTraversal version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DescendantsNestedList: Descendants({1, {2, 3}})
define ChildrenNestedList: Children({1, {2, 3}})
define DescendantsNestedListFirst: Descendants({{ { a: 1 } }, 2})
define ChildrenNestedListFirst: Children({{ { a: 1 } }, 2})
define DescendantsFlatList: Descendants({1, 2})
define DescendantsEmpty: Descendants({})
"""
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected in [
            ("DescendantsNestedList", []),
            ("ChildrenNestedList", []),
            ("DescendantsFlatList", []),
            ("DescendantsEmpty", []),
        ]:
            sql = f"SELECT {translated[name].to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert py_result == (expected,), name
        # List elements that themselves have children contribute their values.
        for name in ("DescendantsNestedListFirst", "ChildrenNestedListFirst"):
            sql = f"SELECT {translated[name].to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            assert cpp_result == py_result, name
            assert py_result == (
                ['{"__fhir4ds_cql_type":"Integer","value":1}'],
            ), name
    finally:
        py.close()
        cpp.close()


def test_cql_structural_strict_cast_in_arithmetic_binds() -> None:
    """QA-104: strict casts lower to CASE ... ELSE error(...) END; the
    integral-arithmetic TRY overflow guard must not wrap volatile error()
    calls (DuckDB: TRY cannot combine with volatile functions)."""
    library = """library StructuralCastArith version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AnyPlusOne: (cast 5 as Any) + 1
define AsAnyPlusOne: (5 as Any) + 1
"""
    translated = translate_cql(library)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_row = py.execute(sql).fetchone()
            cpp_row = cpp.execute(sql).fetchone()
            assert cpp_row == py_row == (6,), (name, sql, py_row, cpp_row)
    finally:
        py.close()
        cpp.close()


def test_cql_structural_element_access_over_retrieve_bound_define_alias() -> None:
    """QA-105: First/Last/indexer/method-first over a define alias bound to a
    bare retrieve must surface the per-patient element list (CQL Appendix B
    First/Last/Indexer), not a scalarized LIMIT-1 row."""
    library = """library StructuralAliasElement version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ObsList: [Observation]
define FirstStatus: First(ObsList).status
define LastStatus: Last(ObsList).status
define IndexerStatus: ObsList[0].status
define MethodFirstId: ObsList.first().id
define AliasCount: Count(ObsList)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(library),
        output_columns={
            "first_status": "FirstStatus",
            "last_status": "LastStatus",
            "indexer_status": "IndexerStatus",
            "method_first_id": "MethodFirstId",
            "alias_count": "AliasCount",
        },
    )
    setup = [
        "CREATE TABLE resources (patient_ref VARCHAR, resourceType VARCHAR, id VARCHAR, resource JSON)",
        """INSERT INTO resources VALUES
        ('p1','Patient','p1','{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1','Observation','o1','{"resourceType":"Observation","id":"o1","status":"final","subject":{"reference":"Patient/p1"}}'::JSON),
        ('p1','Observation','o2','{"resourceType":"Observation","id":"o2","status":"preliminary","subject":{"reference":"Patient/p1"}}'::JSON)""",
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for stmt in setup:
                con.execute(stmt)
        py_row = py.execute(sql).fetchone()
        cpp_row = cpp.execute(sql).fetchone()
        assert py_row[0] == "p1"
        assert py_row[1] in {"final", "preliminary"}  # unordered retrieve
        assert py_row[2] in {"final", "preliminary"}
        assert py_row[3] in {"final", "preliminary"}
        # Method-form .first() may surface the id as a singleton list or
        # scalar (CQL properties of a single resource are 0..* lists).
        _mid = py_row[4][0] if isinstance(py_row[4], list) else json.loads(py_row[4]) if isinstance(py_row[4], str) and py_row[4].startswith("{") else py_row[4]
        assert _mid in {"o1", "o2"}, py_row[4]
        assert py_row[5] == 2  # Count over the alias counts both elements
        assert cpp_row == py_row
    finally:
        py.close()
        cpp.close()


def test_cql_structural_array_property_on_singleton_resource_expressions() -> None:
    """QA-106: 0..* FHIR element access (.contained/.component) on singleton
    resource expressions must return all elements (CQL Appendix B Property).
    fhirpath_text returns only the first element, so Count/First over such
    properties must use the list-returning fhirpath UDF."""
    library = """library StructuralArrayProp version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ObsListAlias: [Observation]
define SingletonObs: singleton from [Observation]
define ContainedCount: Count(First([Observation]).contained)
define SingletonContainedCount: Count(SingletonObs.contained)
define FirstContainedId: First(First([Observation]).contained).id
define ComponentCount: Count(First([Observation]).component)
define AliasContainedCount: Count(First(ObsListAlias).contained)
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(library),
        output_columns={
            "contained_count": "ContainedCount",
            "singleton_contained_count": "SingletonContainedCount",
            "first_contained_id": "FirstContainedId",
            "component_count": "ComponentCount",
            "alias_contained_count": "AliasContainedCount",
        },
    )
    setup = [
        "CREATE TABLE resources (patient_ref VARCHAR, resourceType VARCHAR, id VARCHAR, resource JSON)",
        """INSERT INTO resources VALUES
        ('p1','Patient','p1','{"resourceType":"Patient","id":"p1"}'::JSON),
        ('p1','Observation','o1','{"resourceType":"Observation","id":"o1","status":"final","subject":{"reference":"Patient/p1"},"contained":[{"resourceType":"Observation","id":"c1"},{"resourceType":"Observation","id":"c2"}],"component":[{"code":{"text":"sys"},"valueQuantity":{"value":120,"code":"mm[Hg]"}},{"code":{"text":"dia"},"valueQuantity":{"value":80,"code":"mm[Hg]"}}]}'::JSON)""",
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for stmt in setup:
                con.execute(stmt)
        py_row = py.execute(sql).fetchone()
        cpp_row = cpp.execute(sql).fetchone()
        assert py_row[0] == "p1"
        assert py_row[1] == 2  # two contained resources
        assert py_row[2] == 2  # singleton-from alias sees the same list
        assert py_row[3] in {"c1", "c2"}  # unordered contained pick
        assert py_row[4] == 2  # two components
        assert py_row[5] == 2  # First(alias).contained
        assert cpp_row == py_row
    finally:
        py.close()
        cpp.close()
