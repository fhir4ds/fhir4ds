"""CQL arithmetic operator part 2 parity checks."""

from __future__ import annotations

import json
import re
from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef, UnaryExpression
from fhir4ds.cql.translator import translate_cql

from .wasm_runtime_helpers import no_python_connection


def _raw_quantity_tuple(payload: str) -> tuple[Decimal, str]:
    value_match = re.search(r'"value":(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)', payload)
    unit_match = re.search(r'"(?:code|unit)":"([^"]*)"', payload)
    assert value_match is not None
    assert unit_match is not None
    return Decimal(value_match.group(1)), unit_match.group(1)


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_arithmetic_part2_expressions_parse_and_translate() -> None:
    for expression in [
        "maximum Integer",
        "minimum Integer",
        "Precision(1.2300)",
        "Power(2, 3)",
        "Round(3.456, 2)",
        "Truncate(3.7)",
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, FunctionRef)

    for expression, operator in [("5 mod 2", "mod"), ("5 * 2", "*"), ("10 div 3", "div")]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, BinaryExpression)
        assert parsed.operator == operator

    for expression, operator in [
        ("-5", "-"),
        ("predecessor of @2024-01-15", "predecessor of"),
        ("successor of @2024-01-15", "successor of"),
    ]:
        parsed = parse_expression(expression)
        assert isinstance(parsed, UnaryExpression)
        assert parsed.operator == operator

    cql = """library Arithmetic2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MaxInt: maximum Integer
define MinInt: minimum Integer
define MaxDateTime: maximum DateTime
define MinDateTime: minimum DateTime
define MaxTime: maximum Time
define MinTime: minimum Time
define ModCheck: 5 mod 2
define QuantityMod: 10 'mg' mod 3 'mg'
define QuantityScalarMod: 10 'mg' mod 3
define MultiplyCheck: 5 * 2
define QuantityMultiply: 5 'm' * 3 's'
define NegateCheck: -5
define QuantityNegate: -(5 'mg')
define PrecisionCheck: Precision(1.2300)
define PredMinInteger: predecessor of minimum Integer
define PredCheck: predecessor of @2024-01-15
define PowerCheck: Power(2, 3)
define RoundCheck: Round(3.456, 2)
define SubtractCheck: 5 - 2
define QuantitySubtract: 10 'mg' - 3 'mg'
define SuccMaxInteger: successor of maximum Integer
define SuccCheck: successor of @2024-01-15
define TruncateCheck: Truncate(3.7)
define DivCheck: 10 div 3
define QuantityDivCheck: 10 'mg' div 3 'mg'
define QuantityScalarDiv: 10 'mg' div 3
"""
    translated = translate_cql(cql)

    assert translated["MaxInt"].to_sql() == "2147483647"
    assert translated["MinInt"].to_sql() == "-2147483648"
    assert translated["MaxDateTime"].to_sql() == "'9999-12-31T23:59:59.999Z'"
    assert translated["MinDateTime"].to_sql() == "'0001-01-01T00:00:00.000Z'"
    assert translated["MaxTime"].to_sql() == "'T23:59:59.999'"
    assert translated["MinTime"].to_sql() == "'T00:00:00.000'"
    assert "operator='%'" in str(translated["ModCheck"])
    assert "quantityModulo" in str(translated["QuantityMod"])
    assert "quantityModulo" in str(translated["QuantityScalarMod"])
    assert "operator='*'" in str(translated["MultiplyCheck"])
    assert "quantityMultiply" in str(translated["QuantityMultiply"])
    assert translated["NegateCheck"].to_sql() == "-5"
    assert "quantityNegate" in str(translated["QuantityNegate"])
    assert "CQLPrecision" in str(translated["PrecisionCheck"])
    assert "'1.2300'" in translated["PrecisionCheck"].to_sql()
    assert translated["PredMinInteger"].to_sql() == "NULL"
    assert "predecessorOf" in str(translated["PredCheck"])
    assert "mathPower" in str(translated["PowerCheck"])
    assert "RoundTo" in str(translated["RoundCheck"])
    assert "operator='-'" in str(translated["SubtractCheck"])
    assert "quantity_subtract" in str(translated["QuantitySubtract"])
    assert translated["SuccMaxInteger"].to_sql() == "NULL"
    assert "successorOf" in str(translated["SuccCheck"])
    assert "Truncate" in str(translated["TruncateCheck"])
    assert "TRUNC" in str(translated["DivCheck"])
    assert "quantityTruncatedDivide" in str(translated["QuantityDivCheck"])
    assert "quantityTruncatedDivide" in str(translated["QuantityScalarDiv"])


def test_cql_arithmetic_part2_static_temporal_boundaries_raise_for_conformance() -> None:
    for expression in [
        "predecessor of DateTime(0001, 1, 1, 0, 0, 0, 0)",
        "predecessor of @0001-01-01T00:00:00.000",
        "predecessor of @0001-01-01T00:00:00.000Z",
        "predecessor of @T00:00:00.000",
        "successor of DateTime(9999, 12, 31, 23, 59, 59, 999)",
        "successor of @9999-12-31T23:59:59.999",
        "successor of @9999-12-31T23:59:59.999Z",
        "successor of @T23:59:59.999",
    ]:
        cql = f"""library Arithmetic2Invalid version '1.0.0'
using FHIR version '4.0.1'
context Patient
define InvalidBoundary: {expression}
"""
        with pytest.raises(ValueError):
            translate_cql(cql)


def test_cql_arithmetic_part2_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        "SELECT Round(3.456)::VARCHAR",
        "SELECT RoundTo(3.456, 2)::VARCHAR",
        "SELECT Power(2, 3)::VARCHAR",
        "SELECT Truncate(3.7)::VARCHAR",
        "SELECT Mod(5, 2)",
        "SELECT Div(10, 3)",
        "SELECT Div(10.1, 3.1)",
        "SELECT Div(-10.1, 3.1)",
        "SELECT mathRound('2.5','0')",
        "SELECT mathRound('-0.5','0')",
        "SELECT mathRound('-1.5','0')",
        "SELECT mathRound('-2.5','0')",
        "SELECT mathRound('-2.55','1')",
        "SELECT mathRound('3.456','2')",
        "SELECT mathRound('3.1', NULL)",
        "SELECT Power(-2, 0.5)",
        "SELECT mathPower('2','10')",
        "SELECT mathPower('4','0.5')",
        "SELECT mathPower('-2','3')",
        "SELECT mathPower('-2','0.5')",
        "SELECT mathPower('1e308','2')",
        "SELECT mathTruncate('2.9')",
        "SELECT mathTruncate('-2.9')",
        "SELECT CQLPrecision('2024-01-15T10:30:45.100')",
        "SELECT CQLPrecision('1.2300')",
        "SELECT predecessorOf('2024-01-15')",
        "SELECT predecessorOf('2024-01-15T')",
        "SELECT successorOf('2024-01-15')",
        "SELECT successorOf('2024-01-15T')",
        "SELECT predecessorOf('0001-01-01')",
        "SELECT successorOf('9999-12-31')",
        "SELECT predecessorOf('-99999999999999999999.99999999')",
        "SELECT successorOf('99999999999999999999.99999999')",
        "SELECT predecessorOf('T00:00:00.000')",
        "SELECT successorOf('T23:59:59.999')",
        "SELECT predecessorOf(CAST('-9223372036854775808' AS BIGINT))",
        "SELECT successorOf(CAST('9223372036854775807' AS BIGINT))",
        (
            "SELECT quantitySubtract('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityMultiply('{\"value\":5,\"code\":\"m\"}', "
            "'{\"value\":3,\"code\":\"s\"}')"
        ),
        "SELECT quantityNegate('{\"value\":5,\"code\":\"mg\"}')",
        "SELECT quantityAbs('{\"value\":-5,\"code\":\"mg\"}')",
        (
            "SELECT quantityModulo('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityModulo('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"g\"}')"
        ),
        (
            "SELECT quantityModulo('{\"value\":10,\"code\":\"g\"}', "
            "'{\"value\":3000,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"mg\"}')"
        ),
        (
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"g\"}')"
        ),
        (
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"g\"}', "
            "'{\"value\":3000,\"code\":\"mg\"}')"
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()

        def assert_scalar(sql: str, expected) -> None:
            assert py.execute(sql).fetchone()[0] == expected
            assert cpp.execute(sql).fetchone()[0] == expected

        assert_scalar("SELECT mathRound('-0.5','0')", "-1")
        assert_scalar("SELECT mathRound('-1.5','0')", "-2")
        assert_scalar("SELECT mathRound('-2.5','0')", "-3")
        assert_scalar("SELECT mathRound('-2.55','1')", "-2.6")
        assert_scalar("SELECT mathRound('3.1', NULL)", "3")
        assert_scalar("SELECT RoundTo(3.1, NULL)::VARCHAR", "3.00000000")
        assert_scalar("SELECT Power(-2, 0.5)", None)
        assert_scalar("SELECT mathPower('1e308','2')", None)
        assert_scalar("SELECT Div(10.1, 3.1)", 3.0)
        assert_scalar("SELECT Div(-10.1, 3.1)", -3.0)
        assert_scalar("SELECT predecessorOf('-99999999999999999999.99999999')", None)
        assert_scalar("SELECT successorOf('99999999999999999999.99999999')", None)
        assert_scalar("SELECT predecessorOf('0001-01-01')", None)
        assert_scalar("SELECT successorOf('9999-12-31')", None)
        assert_scalar("SELECT predecessorOf('T00:00:00.000')", None)
        assert_scalar("SELECT successorOf('T23:59:59.999')", None)

        def assert_quantity(sql: str, expected_value: float, expected_code: str) -> None:
            for con in (py, cpp):
                payload = con.execute(sql).fetchone()[0]
                parsed = json.loads(payload)
                assert parsed["value"] == expected_value
                assert parsed["code"] == expected_code

        assert_quantity(
            "SELECT quantityModulo('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"g\"}')",
            10.0,
            "mg",
        )
        assert_quantity(
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"mg\"}', "
            "'{\"value\":3,\"code\":\"g\"}')",
            0.0,
            "mg",
        )
        assert_quantity(
            "SELECT quantityModulo('{\"value\":10,\"code\":\"g\"}', "
            "'{\"value\":3000,\"code\":\"mg\"}')",
            1.0,
            "g",
        )
        assert_quantity(
            "SELECT quantityTruncatedDivide('{\"value\":10,\"code\":\"g\"}', "
            "'{\"value\":3000,\"code\":\"mg\"}')",
            3.0,
            "g",
        )
    finally:
        py.close()
        cpp.close()


def test_cql_arithmetic_part2_historian_boundary_regressions() -> None:
    cql = """library Arithmetic2Historian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NegMinInteger: -(minimum Integer)
define NegMinLong: -(minimum Long)
define NegMinDecimal: -(minimum Decimal)
define PredMinDecimal: predecessor of minimum Decimal
define SuccMaxDecimal: successor of maximum Decimal
define PrecisionOffset: Precision(@2014-01-01T10:30:00.000-05:00)
define RoundNegHalf: Round(-0.5)
define RoundNegTenth: Round(-2.55, 1)
define RoundNullPrecision: Round(3.1, null as Integer)
"""
    translated = translate_cql(cql)
    expected = {
        "NegMinInteger": None,
        "NegMinLong": None,
        "NegMinDecimal": Decimal("99999999999999999999.99999999"),
        "PredMinDecimal": None,
        "SuccMaxDecimal": None,
        "PrecisionOffset": 17,
        "RoundNegHalf": Decimal("-1.00000000"),
        "RoundNegTenth": Decimal("-2.60000000"),
        "RoundNullPrecision": Decimal("3.00000000"),
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
        assert con.execute("SELECT predecessorOf('T25:00')").fetchone()[0] is None
        assert con.execute("SELECT CQLPrecision('2014-01-01T10:30:00.000-05:00')").fetchone()[0] == 17
        assert con.execute("SELECT RoundTo(3.1, NULL)::VARCHAR").fetchone()[0] == "3.00000000"


def test_cql_arithmetic_part2_quantity_predecessor_successor_shape() -> None:
    cql = """library Arithmetic2QuantityStep version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PredIntegerQuantity: predecessor of 1 'cm'
define SuccIntegerQuantity: successor of 1 'cm'
define PredDecimalQuantity: predecessor of 1.0 'cm'
define SuccDecimalQuantity: successor of 1.0 'cm'
"""
    translated = translate_cql(cql)
    expected = {
        "PredIntegerQuantity": (Decimal("0"), "cm"),
        "SuccIntegerQuantity": (Decimal("2"), "cm"),
        "PredDecimalQuantity": (Decimal("0.99999999"), "cm"),
        "SuccDecimalQuantity": (Decimal("1.00000001"), "cm"),
    }

    def quantity_tuple(payload: str) -> tuple[Decimal, str]:
        parsed = json.loads(payload)
        return Decimal(str(parsed["value"])), parsed["code"]

    direct_cases = {
        "SELECT predecessorOf('{\"value\":\"5\",\"code\":\"mg\"}')": None,
        "SELECT successorOf('{\"value\":\"5\",\"code\":\"mg\"}')": None,
        "SELECT predecessorOf('{\"value\":1,\"code\":\"cm\"}')": (Decimal("0"), "cm"),
        "SELECT successorOf('{\"value\":1,\"code\":\"cm\"}')": (Decimal("2"), "cm"),
        "SELECT predecessorOf('{\"value\":1.0,\"code\":\"cm\"}')": (Decimal("0.99999999"), "cm"),
        "SELECT successorOf('{\"value\":1.0,\"code\":\"cm\"}')": (Decimal("1.00000001"), "cm"),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for name, expected_value in expected.items():
                got = con.execute("SELECT " + translated[name].to_sql()).fetchone()[0]
                assert quantity_tuple(got) == expected_value
            for sql, expected_value in direct_cases.items():
                got = con.execute(sql).fetchone()[0]
                assert (quantity_tuple(got) if got is not None else None) == expected_value
    finally:
        py.close()
        cpp.close()

    with no_python_connection() as con:
        for sql, expected_value in direct_cases.items():
            got = con.execute(sql).fetchone()[0]
            assert (quantity_tuple(got) if got is not None else None) == expected_value


def test_cql_arithmetic_part2_max_min_quantity_and_numeric_text_surface() -> None:
    cql = """library Arithmetic2ExplorerMaxMin version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MaxQuantity: maximum Quantity
define MinQuantity: minimum Quantity
define QueryQuantityPred: singleton from (from { 1 'cm' } Q return predecessor of Q)
define QueryQuantitySucc: singleton from (from { 1.0 'cm' } Q return successor of Q)
define SingletonQuantityPred: predecessor of singleton from { 1 'cm' }
define SingletonQuantitySucc: successor of singleton from { 1.0 'cm' }
"""
    translated = translate_cql(cql)
    expected = {
        "MaxQuantity": (Decimal("99999999999999999999.99999999"), "1"),
        "MinQuantity": (Decimal("-99999999999999999999.99999999"), "1"),
        "QueryQuantityPred": (Decimal("0"), "cm"),
        "QueryQuantitySucc": (Decimal("1.00000001"), "cm"),
        "SingletonQuantityPred": (Decimal("0"), "cm"),
        "SingletonQuantitySucc": (Decimal("1.00000001"), "cm"),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for name, expected_value in expected.items():
                got = con.execute("SELECT " + translated[name].to_sql()).fetchone()[0]
                assert _raw_quantity_tuple(got) == expected_value

            assert con.execute("SELECT predecessorOf('5')").fetchone()[0] == 4.99999999
            assert con.execute("SELECT successorOf('5')").fetchone()[0] == 5.00000001
    finally:
        py.close()
        cpp.close()

    for expression in ("maximum String", "minimum String", "maximum Code", "minimum Concept"):
        cql = f"""library Arithmetic2ExplorerInvalid version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Invalid: {expression}
"""
        with pytest.raises(ValueError):
            translate_cql(cql)

    with no_python_connection() as con:
        assert con.execute("SELECT predecessorOf('5')").fetchone()[0] == "4.99999999"
        assert con.execute("SELECT successorOf('5')").fetchone()[0] == "5.00000001"


def test_cql_arithmetic_part2_dynamic_fhir_numeric_choices() -> None:
    cql = """library Arithmetic2Dynamic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DivVal: O.value div 2
define PowVal: Power(O.value, 2)
define CaretVal: O.value ^ 2
define RoundVal: Round(O.value)
define TruncVal: Truncate(O.value)
"""
    translated = translate_cql(cql)
    expected_integer = {
        "DivVal": 2.0,
        "PowVal": 25.0,
        "CaretVal": 25.0,
        "RoundVal": Decimal("5.00000000"),
        "TruncVal": 5.0,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        integer_resource = json.dumps({"resourceType": "Observation", "valueInteger": 5})
        string_resource = json.dumps({"resourceType": "Observation", "valueString": "5"})
        for name, expected_value in expected_integer.items():
            sql = f"SELECT {translated[name].to_sql()} FROM (SELECT ?::JSON AS O)"
            assert py.execute(sql, [integer_resource]).fetchone()[0] == expected_value
            assert cpp.execute(sql, [integer_resource]).fetchone()[0] == expected_value
            assert py.execute(sql, [string_resource]).fetchone()[0] is None
            assert cpp.execute(sql, [string_resource]).fetchone()[0] is None
    finally:
        py.close()
        cpp.close()


def test_cql_arithmetic_part2_explorer_boundary_regressions() -> None:
    cql = """library Arithmetic2Explorer version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DivDecimal: 10.1 div 3.1
define DivNegativeDecimal: -10.1 div 3.1
define PredYear: predecessor of @2014
define SuccYear: successor of @2014
define PredMonth: predecessor of @2014-01
define SuccMonth: successor of @2014-12
define PredDateTimeYear: predecessor of @2014T
define SuccDateTimeYear: successor of @2014T
define PredDateTimeMonth: predecessor of @2014-01T
define SuccDateTimeMonth: successor of @2014-12T
define PredDateTimeHour: predecessor of @2014-01-01T10
define SuccDateTimeHour: successor of @2014-01-01T10
define PredTimeHour: predecessor of @T12
define SuccTimeHour: successor of @T12
define PredTimeMinute: predecessor of @T12:30
define SuccTimeMinute: successor of @T12:30
define QuantityScalarMod: 10 'mg' mod 3
define ScalarQuantityMod: 10 mod 3 'mg'
define QuantityScalarDiv: 10 'mg' div 3
define ScalarQuantityDiv: 10 div 3 'mg'
"""
    translated = translate_cql(cql)
    expected = {
        "DivDecimal": 3.0,
        "DivNegativeDecimal": -3.0,
        "PredYear": "2013",
        "SuccYear": "2015",
        "PredMonth": "2013-12",
        "SuccMonth": "2015-01",
        "PredDateTimeYear": "2013T",
        "SuccDateTimeYear": "2015T",
        "PredDateTimeMonth": "2013-12T",
        "SuccDateTimeMonth": "2015-01T",
        "PredDateTimeHour": "2014-01-01T09",
        "SuccDateTimeHour": "2014-01-01T11",
        "PredTimeHour": "T11",
        "SuccTimeHour": "T13",
        "PredTimeMinute": "T12:29",
        "SuccTimeMinute": "T12:31",
        "QuantityScalarMod": None,
        "ScalarQuantityMod": None,
        "QuantityScalarDiv": None,
        "ScalarQuantityDiv": None,
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
        "SELECT predecessorOf('2014')": "2013",
        "SELECT successorOf('2014')": "2015",
        "SELECT predecessorOf('2014-01')": "2013-12",
        "SELECT successorOf('2014-12')": "2015-01",
        "SELECT predecessorOf('2014T')": "2013T",
        "SELECT successorOf('2014T')": "2015T",
        "SELECT predecessorOf('2014-01T')": "2013-12T",
        "SELECT successorOf('2014-12T')": "2015-01T",
        "SELECT predecessorOf('2014-01-01T10')": "2014-01-01T09",
        "SELECT successorOf('2014-01-01T10')": "2014-01-01T11",
        "SELECT predecessorOf('T12')": "T11",
        "SELECT successorOf('T12')": "T13",
        "SELECT predecessorOf('T12:30')": "T12:29",
        "SELECT successorOf('T12:30')": "T12:31",
        "SELECT predecessorOf('-99999999999999999999.99999999')": None,
        "SELECT successorOf('99999999999999999999.99999999')": None,
    }
    with no_python_connection() as con:
        for sql, expected_value in direct_queries.items():
            assert con.execute(sql).fetchone()[0] == expected_value
