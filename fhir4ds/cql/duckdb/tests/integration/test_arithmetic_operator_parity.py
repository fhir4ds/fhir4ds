"""CQL arithmetic operator parity checks."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.errors import TranslationError
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


def test_cql_arithmetic_expressions_parse_and_translate() -> None:
    for expression in [
        "Abs(-5)",
        "Ceiling(2.1)",
        "Floor(2.9)",
        "Exp(0)",
        "Ln(1)",
        "Log(100, 10)",
        "HighBoundary(@2024, 8)",
        "LowBoundary(@2024, 8)",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    for expression, operator in [("1 + 2", "+"), ("4 / 2", "/")]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, BinaryExpression)
        assert parsed.operator == operator

    cql = """library Arithmetic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AddCheck: 1 + 2
define DivideCheck: 4 / 2
define QuantityAdd: 1 'g' + 500 'mg'
define ExpCheck: Exp(0)
define LnCheck: Ln(1)
define LogCheck: Log(100, 10)
define HighCheck: HighBoundary(@2024, 8)
define LowCheck: LowBoundary(@2024, 8)
"""
    translated = translate_cql(cql)

    assert "operator='+'" in str(translated["AddCheck"])
    assert "NULLIF" in str(translated["DivideCheck"])
    assert "quantity_add" in str(translated["QuantityAdd"])
    assert "mathExp" in str(translated["ExpCheck"])
    assert "CAST" in translated["ExpCheck"].to_sql()
    assert "mathLn" in str(translated["LnCheck"])
    assert "CAST" in translated["LnCheck"].to_sql()
    assert "system.log" in str(translated["LogCheck"])
    assert "HighBoundary" in str(translated["HighCheck"])
    assert "LowBoundary" in str(translated["LowCheck"])


def test_cql_arithmetic_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT Abs(-5)",
        "SELECT Ceiling(2.1)",
        "SELECT Floor(2.9)",
        "SELECT Exp(0)::VARCHAR",
        "SELECT Ln(1)::VARCHAR",
        "SELECT Log(100, 10)::VARCHAR",
        "SELECT mathAbs('-5')",
        "SELECT mathCeiling('2.1')",
        "SELECT mathFloor('2.9')",
        "SELECT mathExp('0')",
        "SELECT mathLn('1')",
        "SELECT mathLn('-1')",
        "SELECT mathLog('100','10')",
        "SELECT mathLog('-1','10')",
        "SELECT mathLog('100','1')",
        "SELECT mathExp(CAST(0 AS VARCHAR))",
        "SELECT mathLn(CAST(1 AS VARCHAR))",
        "SELECT TRY(system.log(10, 100))::VARCHAR",
        "SELECT HighBoundary('2024', 8)",
        "SELECT LowBoundary('2024', 8)",
        "SELECT HighBoundary('1.587')",
        "SELECT LowBoundary('1.587')",
        "SELECT HighBoundary('2024')",
        "SELECT LowBoundary('2024')",
        "SELECT HighBoundary('2024-01-01T08')",
        "SELECT LowBoundary('2024-01-01T08')",
        "SELECT HighBoundary('T10:30')",
        "SELECT LowBoundary('T10:30')",
        "SELECT HighBoundary('2024-02', 8)",
        "SELECT LowBoundary('2024-02', 8)",
        (
            "SELECT quantityAdd('{\"value\":1,\"code\":\"g\"}', "
            "'{\"value\":500,\"code\":\"mg\"}')"
        ),
        "SELECT quantityAdd('{\"value\":5}', '{\"value\":3,\"code\":\"1\"}')",
        (
            "SELECT quantityDivide('{\"value\":10,\"code\":\"m\"}', "
            "'{\"value\":2,\"code\":\"s\"}')"
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()

        for expression in [
            "SELECT Ln(-1)",
            "SELECT Log(-1, 10)",
            "SELECT Log(100, 1)",
            "SELECT LogBase(100, 1)",
            "SELECT HighBoundary(1.587, 99)",
            "SELECT LowBoundary('2024', 17)",
            "SELECT HighBoundary('T10:30', 10)",
            "SELECT quantityValue('{\"value\":\"10\",\"code\":\"mg\"}')",
            (
                "SELECT quantityAdd('{\"value\":\"10\",\"code\":\"mg\"}', "
                "'{\"value\":1,\"code\":\"mg\"}')"
            ),
            (
                "SELECT quantityAdd('{\"value\":true,\"code\":\"mg\"}', "
                "'{\"value\":1,\"code\":\"mg\"}')"
            ),
            (
                "SELECT quantityDivide('{\"value\":\"10\",\"code\":\"mg\"}', "
                "'{\"value\":2,\"code\":\"1\"}')"
            ),
        ]:
            assert py.execute(expression).fetchone() == (None,)
            assert cpp.execute(expression).fetchone() == (None,)

        for expression in [
            "SELECT Exp(1000)",
            "SELECT Ln(0)",
            "SELECT mathExp('1000')",
            "SELECT mathLn('0')",
        ]:
            with pytest.raises(duckdb.Error):
                py.execute(expression).fetchone()
            with pytest.raises(duckdb.Error):
                cpp.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_arithmetic_boundaries_execute_with_nulls_and_granular_quantities() -> None:
    cql = """library ArithmeticSkeptic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AbsIntegerMin: Abs(-2147483648)
define AbsLongMin: Abs(-9223372036854775808L)
define AddIntegerOverflow: 2147483647 + 1
define AddLongOverflow: 9223372036854775807L + 1L
define DivideByZero: 4 / 0
define ExpOverflow: Exp(1000)
define LnZero: Ln(0)
define LnNegative: Ln(-1)
define LogBadBase: Log(100, 1)
define DecimalHighTooPrecise: HighBoundary(1.587, 99)
define DateHighTooPrecise: HighBoundary(@2024, 17)
define TimeLowTooPrecise: LowBoundary(@T10:30, 10)
define QuantityAddGThenMg: 1 'g' + 500 'mg'
define QuantityAddMgThenG: 500 'mg' + 1 'g'
"""
    translated = translate_cql(cql)
    expected_nulls = [
        "AbsIntegerMin",
        "AbsLongMin",
        "AddIntegerOverflow",
        "AddLongOverflow",
        "DivideByZero",
        "LnNegative",
        "LogBadBase",
        "DecimalHighTooPrecise",
        "DateHighTooPrecise",
        "TimeLowTooPrecise",
    ]
    expected_errors = ["ExpOverflow", "LnZero"]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in expected_nulls:
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)

        for name in expected_errors:
            sql = f"SELECT {translated[name].to_sql()}"
            with pytest.raises(duckdb.Error):
                py.execute(sql).fetchone()
            with pytest.raises(duckdb.Error):
                cpp.execute(sql).fetchone()

        for name in ("QuantityAddGThenMg", "QuantityAddMgThenG"):
            sql = f"SELECT {translated[name].to_sql()}"
            py_value = json.loads(py.execute(sql).fetchone()[0])
            cpp_value = json.loads(cpp.execute(sql).fetchone()[0])
            assert py_value == cpp_value
            assert py_value["code"] == "mg"
            assert py_value["unit"] == "mg"
            assert py_value["value"] == 1500.0
    finally:
        py.close()
        cpp.close()


def test_cql_dynamic_fhir_arithmetic_edges_match_cpp_and_python() -> None:
    cql = """library DynamicArithmeticEdges version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FhirIntegerAdd: O.value + 1
define FhirIntegerDivide: O.value / 2
define FhirQuantityDivide: (O.value as Quantity) / 2
define FhirQuantityAddScalarIsNull: (O.value as Quantity) + 1
define StaticQuantityAddScalarIsNull: 10 'mg' + 2
define StaticScalarAddQuantityIsNull: 2 + 10 'mg'
"""
    translated = translate_cql(cql)
    cases = [
        (
            "FhirIntegerAdd",
            {"resourceType": "Observation", "valueInteger": 5},
            6,
        ),
        (
            "FhirIntegerAdd",
            {"resourceType": "Observation", "valueString": "5"},
            None,
        ),
        (
            "FhirIntegerAdd",
            {"resourceType": "Observation", "valueQuantity": {"value": 5, "code": "mg"}},
            None,
        ),
        (
            "FhirIntegerDivide",
            {"resourceType": "Observation", "valueInteger": 5},
            2.5,
        ),
        (
            "FhirIntegerDivide",
            {"resourceType": "Observation", "valueString": "5"},
            None,
        ),
        (
            "FhirQuantityAddScalarIsNull",
            {"resourceType": "Observation", "valueQuantity": {"value": 5, "code": "mg"}},
            None,
        ),
        (
            "FhirQuantityDivide",
            {"resourceType": "Observation", "valueQuantity": {"value": "10", "code": "mg"}},
            None,
        ),
        (
            "FhirQuantityDivide",
            {"resourceType": "Observation", "valueQuantity": {"value": True, "code": "mg"}},
            None,
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, resource, expected in cases:
            sql = f"SELECT {translated[name].to_sql()} FROM (SELECT ?::JSON AS O)"
            resource_text = json.dumps(resource)
            assert py.execute(sql, [resource_text]).fetchone() == (expected,)
            assert cpp.execute(sql, [resource_text]).fetchone() == (expected,)

        quantity_resource = json.dumps(
            {"resourceType": "Observation", "valueQuantity": {"value": 10, "code": "mg"}}
        )
        sql = f"SELECT {translated['FhirQuantityDivide'].to_sql()} FROM (SELECT ?::JSON AS O)"
        py_quantity = json.loads(py.execute(sql, [quantity_resource]).fetchone()[0])
        cpp_quantity = json.loads(cpp.execute(sql, [quantity_resource]).fetchone()[0])
        assert py_quantity == cpp_quantity
        assert py_quantity["value"] == 5.0
        assert py_quantity["code"] == "mg"
        assert py_quantity["unit"] == "mg"

        for name in ("StaticQuantityAddScalarIsNull", "StaticScalarAddQuantityIsNull"):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_time_boundary_timezone_strings_match_cpp_and_python() -> None:
    expected = {
        "HighNumericText": "1.58799999",
        "LowNumericText": "1.58700000",
        "HighExponentPrecisionZero": "100",
        "LowExponentPrecisionZero": "100",
        "HighZ": "T10:30:59.999Z",
        "LowZ": "T10:30:00.000Z",
        "HighPlusOffset": "T10:30:59.999+05:00",
        "LowPlusOffset": "T10:30:00.000+05:00",
        "HighMinusOffset": "T10:30:59.999-05:00",
        "LowMinusOffset": "T10:30:00.000-05:00",
        "HighDateTimeOffset": "2024-01-01T10:30:59.999+05:00",
        "LowDateTimeOffset": "2024-01-01T10:30:00.000+05:00",
    }

    direct_sql = {
        "HighNumericText": "SELECT HighBoundary('1.587', 8)",
        "LowNumericText": "SELECT LowBoundary('1.587', 8)",
        "HighExponentPrecisionZero": "SELECT HighBoundary('1e2', 0)",
        "LowExponentPrecisionZero": "SELECT LowBoundary('1e2', 0)",
        "HighZ": "SELECT HighBoundary('T10:30Z', 9)",
        "LowZ": "SELECT LowBoundary('T10:30Z', 9)",
        "HighPlusOffset": "SELECT HighBoundary('T10:30+05:00', 9)",
        "LowPlusOffset": "SELECT LowBoundary('T10:30+05:00', 9)",
        "HighMinusOffset": "SELECT HighBoundary('T10:30-05:00', 9)",
        "LowMinusOffset": "SELECT LowBoundary('T10:30-05:00', 9)",
        "HighDateTimeOffset": "SELECT HighBoundary('2024-01-01T10:30+05:00', 17)",
        "LowDateTimeOffset": "SELECT LowBoundary('2024-01-01T10:30+05:00', 17)",
    }

    invalid_sql = [
        "SELECT HighBoundary('2024-13', 8)",
        "SELECT LowBoundary('2024-13', 8)",
        "SELECT HighBoundary('2024-01foo', 8)",
        "SELECT LowBoundary('2024-01-01T10abc+05:00', 17)",
        "SELECT HighBoundary('2024-02-30', 8)",
        "SELECT LowBoundary('2024-02-30', 8)",
        "SELECT HighBoundary('T25:00', 9)",
        "SELECT LowBoundary('T10:99', 9)",
        "SELECT HighBoundary('T10:30+99:99', 9)",
        "SELECT LowBoundary('T10:30+0500', 9)",
        "SELECT HighBoundary('1e100000000', 8)",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            assert py.execute(direct_sql[name]).fetchone() == (value,)
            assert cpp.execute(direct_sql[name]).fetchone() == (value,)
        for sql in invalid_sql:
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_explorer_arithmetic_edges_match_cpp_and_python() -> None:
    cql = """library ArithmeticExplorer version '1.0.0'
using FHIR version '4.0.1'
context Patient
define QuantityDivideNull: 1 'mg' / null
define QuantityMultiplyNull: 1 'mg' * null
define QuantityTimesDynamic: 10 'mg' * O.value
define PowerInvalid: Power(-2, 0.5)
define PowerOperatorInvalid: (-2) ^ 0.5
define DatePlusInteger: @2024-01-01 + 1
define IntegerUnderflow: -2147483648 - 1
"""
    translated = translate_cql(cql)

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in ("QuantityDivideNull", "QuantityMultiplyNull"):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)

        quantity_dynamic_sql = (
            "SELECT "
            + translated["QuantityTimesDynamic"].to_sql()
            + " FROM (SELECT ?::JSON AS O)"
        )
        numeric_resource = json.dumps({"resourceType": "Observation", "valueInteger": 5})
        py_quantity = json.loads(py.execute(quantity_dynamic_sql, [numeric_resource]).fetchone()[0])
        cpp_quantity = json.loads(cpp.execute(quantity_dynamic_sql, [numeric_resource]).fetchone()[0])
        assert py_quantity == cpp_quantity
        assert py_quantity["value"] == 50.0
        assert py_quantity["code"] == "mg"
        for resource in [
            {"resourceType": "Observation", "valueString": "5"},
            {"resourceType": "Observation", "valueString": "abc"},
        ]:
            resource_text = json.dumps(resource)
            assert py.execute(quantity_dynamic_sql, [resource_text]).fetchone() == (None,)
            assert cpp.execute(quantity_dynamic_sql, [resource_text]).fetchone() == (None,)

        for name in ("PowerInvalid", "PowerOperatorInvalid", "IntegerUnderflow"):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (None,)
            assert cpp.execute(sql).fetchone() == (None,)

        sql = "SELECT " + translated["DatePlusInteger"].to_sql()
        assert py.execute(sql).fetchone() == ("2025-01-01",)
        assert cpp.execute(sql).fetchone() == ("2025-01-01",)
    finally:
        py.close()
        cpp.close()


def test_cql_log_requires_base_and_boundary_default_precision() -> None:
    cql = """library ArithmeticHistorian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DecimalHighDefault: HighBoundary(1.587)
define DecimalLowDefault: LowBoundary(1.587)
define DateHighDefault: HighBoundary(@2014)
define DateLowDefault: LowBoundary(@2014)
define DateTimeHighDefault: HighBoundary(@2014-01-01T08)
define DateTimeLowDefault: LowBoundary(@2014-01-01T08)
define TimeHighDefault: HighBoundary(@T10:30)
define TimeLowDefault: LowBoundary(@T10:30)
define LogBaseTwo: Log(16, 2)
"""
    translated = translate_cql(cql)
    expected = {
        "DecimalHighDefault": 1.58799999,
        "DecimalLowDefault": 1.587,
        "DateHighDefault": "2014",
        "DateLowDefault": "2014",
        "DateTimeHighDefault": "2014-01-01T08:59:59.999",
        "DateTimeLowDefault": "2014-01-01T08:00:00.000",
        "TimeHighDefault": "T10:30:59.999",
        "TimeLowDefault": "T10:30:00.000",
        "LogBaseTwo": 4.0,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone() == (value,)
            assert cpp.execute(sql).fetchone() == (value,)
        with pytest.raises(TranslationError):
            translate_cql(
                """library BadLog version '1.0.0'
using FHIR version '4.0.1'
context Patient
define BadLog: Log(100)
"""
            )
    finally:
        py.close()
        cpp.close()
