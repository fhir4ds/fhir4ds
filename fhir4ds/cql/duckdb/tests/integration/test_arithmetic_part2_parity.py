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

    # CQL-01 EXPLORER doctrine: Integer-typed min/max literals lower with
    # an explicit INTEGER cast so exact-integral semantics survive alias
    # chains instead of DuckDB default INTEGER-inference drift.
    assert translated["MaxInt"].to_sql() == "CAST(2147483647 AS INTEGER)"
    assert translated["MinInt"].to_sql() == "CAST(-2147483648 AS INTEGER)"
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
        assert_scalar("SELECT Round(-0.5)::VARCHAR", "-1.00000000")
        assert_scalar("SELECT Round(-1.5)::VARCHAR", "-2.00000000")
        assert_scalar("SELECT RoundTo(-2.55, 1)::VARCHAR", "-2.60000000")
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


def test_cql_arithmetic_part2_power_overflow_returns_null_per_spec() -> None:
    """CQL §16 Power: 'If the result of the operation cannot be represented,
    the result is null.'

    Covers the CQL-11 SKEPTIC fix that brings the function-form Power to
    parity with the infix `^` form on Integer/Long overflow, AND adds
    Decimal-range checking for Decimal operands. Both backends must
    return NULL for unrepresentable results, and must continue to return
    correct fractional results for negative Integer exponents (per
    official CqlArithmeticFunctionsTest.xml::Power2ToNeg2).
    """
    cql = """
    library PowerOverflowProbe version '1.0'
    define FunIntOverflow: Power(2, 100)
    define FunIntBoundary: Power(2, 31)
    define FunDecOverflow: Power(10.0, 100.0)
    define FunDecOverflowAlt: Power(2.5, 100.0)
    define InfixIntOverflow: 10^100
    define InfixDecOverflow: 10.0^100.0
    define FunIntValid: Power(2, 30)
    define FunDecValid: Power(2.0, 50.0)
    define FunIntNegExp: Power(2, -2)
    define InfixIntNegExp: 2^-2
    define FunIntZero: Power(0, 0)
    define FunDecZero: Power(2.0, 0.0)
    """
    translated = translate_cql(cql)

    # All overflow cases must emit a type-specific TRY_CAST (not AS DOUBLE)
    # so DuckDB returns NULL when the result cannot be represented.
    assert "AS INTEGER" in translated["FunIntOverflow"].to_sql()
    assert "AS INTEGER" in translated["FunIntBoundary"].to_sql()
    assert "AS DECIMAL(38, 8)" in translated["FunDecOverflow"].to_sql()
    assert "AS DECIMAL(38, 8)" in translated["FunDecOverflowAlt"].to_sql()
    assert "AS INTEGER" in translated["InfixIntOverflow"].to_sql()
    assert "AS DECIMAL(38, 8)" in translated["InfixDecOverflow"].to_sql()
    # Negative Integer exponent promotes to DECIMAL (fractional result).
    assert "AS DECIMAL(38, 8)" in translated["FunIntNegExp"].to_sql()
    assert "AS DECIMAL(38, 8)" in translated["InfixIntNegExp"].to_sql()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        # Overflow cases — both backends must return None.
        for name in (
            "FunIntOverflow",
            "FunIntBoundary",
            "FunDecOverflow",
            "FunDecOverflowAlt",
            "InfixIntOverflow",
            "InfixDecOverflow",
        ):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] is None, name
            assert cpp.execute(sql).fetchone()[0] is None, name

        # Valid cases — must produce non-None values.
        assert py.execute("SELECT " + translated["FunIntValid"].to_sql()).fetchone()[0] == 1073741824
        assert cpp.execute("SELECT " + translated["FunIntValid"].to_sql()).fetchone()[0] == 1073741824
        # Decimal valid: 2^50 = 1.125899906842624e15; both backends should agree.
        py_dec = py.execute("SELECT " + translated["FunDecValid"].to_sql()).fetchone()[0]
        cpp_dec = cpp.execute("SELECT " + translated["FunDecValid"].to_sql()).fetchone()[0]
        assert abs(float(py_dec) - float(cpp_dec)) < 1e-6

        # Negative Integer exponent — must NOT truncate to 0 (regression check).
        py_neg = py.execute("SELECT " + translated["FunIntNegExp"].to_sql()).fetchone()[0]
        cpp_neg = cpp.execute("SELECT " + translated["FunIntNegExp"].to_sql()).fetchone()[0]
        assert abs(float(py_neg) - 0.25) < 1e-6, py_neg
        assert abs(float(cpp_neg) - 0.25) < 1e-6, cpp_neg

        py_infix_neg = py.execute("SELECT " + translated["InfixIntNegExp"].to_sql()).fetchone()[0]
        cpp_infix_neg = cpp.execute("SELECT " + translated["InfixIntNegExp"].to_sql()).fetchone()[0]
        assert abs(float(py_infix_neg) - 0.25) < 1e-6, py_infix_neg
        assert abs(float(cpp_infix_neg) - 0.25) < 1e-6, cpp_infix_neg

        # Zero exponent — must return 1.
        assert py.execute("SELECT " + translated["FunIntZero"].to_sql()).fetchone()[0] == 1
        assert cpp.execute("SELECT " + translated["FunIntZero"].to_sql()).fetchone()[0] == 1
    finally:
        py.close()
        cpp.close()


def test_cql_arithmetic_part2_truncated_divide_exact_and_typed_per_spec() -> None:
    """CQL §16.16 TruncatedDivide: Integer/Long operands produce
    Integer/Long results; Decimal quotients are exact (never computed
    through DOUBLE); unrepresentable results are null.

    The CQL-11 SKEPTIC fix replaced the DOUBLE ``a / NULLIF(b, 0)``
    lowering with the exact cqlDivide core plus typed TRY_CAST narrowing:
    - 0.3 div 0.1 -> 3 (DOUBLE path returned 2)
    - 9223372036854775807L div 3L -> 3074457345618258602 (exact Long)
    - -9223372036854775808L div -1L -> null (Long overflow)
    """
    cql = """
    library DivExactness version '1.0'
    define DivDecimalNearInteger: 0.3 div 0.1
    define DivDecimalNearInteger2: 0.6 div 0.2
    define DivDecimalNeg: -10.5 div 3.0
    define DivIntType: 10 div 3
    define DivIntNeg: -10 div 3
    define DivLongExact: 9223372036854775807L div 3L
    define DivLongMinNeg: -9223372036854775808L div -1L
    define DivByZero: 10 div 0
    define DivDecimalByZero: 1.5 div 0.0
    """
    translated = translate_cql(cql)
    sql = translated["DivIntType"].to_sql()
    assert "cqlDivide" in sql and "TRUNC" in sql.upper() and "AS INTEGER" in sql
    assert "AS BIGINT" in translated["DivLongExact"].to_sql()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expected = {
            "DivDecimalNearInteger": Decimal("3"),
            "DivDecimalNearInteger2": Decimal("3"),
            "DivDecimalNeg": Decimal("-3"),
            "DivIntType": 3,
            "DivIntNeg": -3,
            "DivLongExact": 3074457345618258602,
            "DivLongMinNeg": None,
            "DivByZero": None,
            "DivDecimalByZero": None,
        }
        for name, expected_value in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            got = py.execute(sql).fetchone()[0]
            assert got == expected_value, f"{name} py: {got!r}"
            assert cpp.execute(sql).fetchone()[0] == expected_value, f"{name} cpp"
        # Integer operands must produce a typed INTEGER (not DOUBLE) column.
        assert py.execute("SELECT " + translated["DivIntType"].to_sql()).description[0][1] == "INTEGER"
    finally:
        py.close()
        cpp.close()


def test_cql_arithmetic_part2_power_underflow_quantizes_to_zero_per_spec() -> None:
    """CQL §16.12 Power: Decimal results are quantized at the
    implementation scale (8). Power(2, -30) = 9.31e-10 quantizes to
    0.00000000, NOT 0.00000001: the old '%.15g' scientific output text
    was rounded UP by DuckDB's VARCHAR->DECIMAL(38,8) cast.
    """
    cql = """
    library PowerUnderflow version '1.0'
    define PowUnderflow: Power(2, -30)
    define PowDeepUnderflow: Power(2, -100)
    define PowJustAbove: Power(2, -27)
    define PowInRange: Power(2, -9)
    """
    translated = translate_cql(cql)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in (
            ("PowUnderflow", Decimal("0E-8")),
            ("PowDeepUnderflow", Decimal("0E-8")),
            ("PowJustAbove", Decimal("1E-8")),
            ("PowInRange", Decimal("0.00195313")),
        ):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] == expected_value, name
            assert cpp.execute(sql).fetchone()[0] == expected_value, name
    finally:
        py.close()
        cpp.close()

    with no_python_connection() as con:
        assert con.execute("SELECT mathPower('2','-30')").fetchone()[0] == "0.00000000"
        assert con.execute("SELECT mathPower('2','-27')").fetchone()[0] == "0.00000001"


def test_cql_arithmetic_part2_precision_integer_literal_engine_parity() -> None:
    """CQL §22.24 Precision: numeric literals must reach the CQLPrecision
    UDF as VARCHAR text. A raw INTEGER literal previously raised a
    BinderException on the native path while the Python path returned 0.
    """
    cql = """
    library PrecisionLiteralParity version '1.0'
    define PrecisionIntLiteral: Precision(5)
    define PrecisionLongLiteral: Precision(5L)
    define PrecisionDecimalLiteral: Precision(1.2300)
    """
    translated = translate_cql(cql)
    assert translated["PrecisionIntLiteral"].to_sql() == "CQLPrecision('5')"
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in (
            ("PrecisionIntLiteral", 0),
            ("PrecisionLongLiteral", 0),
            ("PrecisionDecimalLiteral", 4),
        ):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] == expected_value, name
            assert cpp.execute(sql).fetchone()[0] == expected_value, name
    finally:
        py.close()
        cpp.close()


def test_cql_arithmetic_part2_predecessor_successor_literal_boundary_returns_null_per_spec() -> None:
    """CQL §22.25 Predecessor / §22.26 Successor: "If the result cannot be
    represented (e.g. `successor of (maximum Integer)`), the result is null."

    The translator's FunctionRef-form guard at
    `_operators.py:_translate_unary_expression` returns NULL for
    `successor of (maximum Integer)` and `predecessor of (minimum Integer)`.
    However, the literal-spelled forms (`successor of 2147483647`,
    `predecessor of -2147483648`) previously fell through to the generic
    UDF call (`successorOf(2147483647)`). DuckDB silently promotes
    INTEGER to BIGINT during execution, so the UDF returned
    `2147483648` / `-2147483649` (valid BIGINT values that exceed the
    CQL §Integer range `[-2147483648, 2147483647]`).

    The CQL-11 EXPLORER fix mirrors the FunctionRef guard for the
    literal-spelled form, returning SQLNull() when the literal value
    equals `_CQL_INTEGER_MAX` / `_CQL_INTEGER_MIN` / `_CQL_LONG_MAX` /
    `_CQL_LONG_MIN`.

    Both backends (Python fallback and native C++ extension) must
    return None for the boundary literal forms AND for the FunctionRef
    forms. In-range literal values must continue to work correctly.
    """
    cql = """
    library PredSuccLiteralBoundary version '1.0'
    define SuccIntMaxLiteral: successor of 2147483647
    define PredIntMinLiteral: predecessor of -2147483648
    define SuccIntMaxFuncref: successor of (maximum Integer)
    define PredIntMinFuncref: predecessor of (minimum Integer)
    define SuccLongMaxLiteral: successor of 9223372036854775807L
    define PredLongMinLiteral: predecessor of -9223372036854775808L
    define SuccLongMaxFuncref: successor of (maximum Long)
    define PredLongMinFuncref: predecessor of (minimum Long)
    define SuccIntInRange: successor of 100
    define PredIntInRange: predecessor of 100
    define SuccIntJustBelowMax: successor of 2147483646
    define PredIntJustAboveMin: predecessor of -2147483647
    """
    translated = translate_cql(cql)

    # The literal-spelled boundary forms must emit SQL NULL directly
    # (not the UDF call) so DuckDB never auto-promotes to BIGINT.
    assert translated["SuccIntMaxLiteral"].to_sql() == "NULL"
    assert translated["PredIntMinLiteral"].to_sql() == "NULL"
    assert translated["SuccLongMaxLiteral"].to_sql() == "NULL"
    assert translated["PredLongMinLiteral"].to_sql() == "NULL"

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        # All boundary cases (literal and FunctionRef) must return None.
        for name in (
            "SuccIntMaxLiteral",
            "PredIntMinLiteral",
            "SuccIntMaxFuncref",
            "PredIntMinFuncref",
            "SuccLongMaxLiteral",
            "PredLongMinLiteral",
            "SuccLongMaxFuncref",
            "PredLongMinFuncref",
        ):
            sql = "SELECT " + translated[name].to_sql()
            assert py.execute(sql).fetchone()[0] is None, f"{name}: python should be None"
            assert cpp.execute(sql).fetchone()[0] is None, f"{name}: cpp should be None"

        # In-range cases must continue to work correctly.
        assert py.execute("SELECT " + translated["SuccIntInRange"].to_sql()).fetchone()[0] == 101
        assert cpp.execute("SELECT " + translated["SuccIntInRange"].to_sql()).fetchone()[0] == 101
        assert py.execute("SELECT " + translated["PredIntInRange"].to_sql()).fetchone()[0] == 99
        assert cpp.execute("SELECT " + translated["PredIntInRange"].to_sql()).fetchone()[0] == 99
        assert py.execute("SELECT " + translated["SuccIntJustBelowMax"].to_sql()).fetchone()[0] == 2147483647
        assert cpp.execute("SELECT " + translated["SuccIntJustBelowMax"].to_sql()).fetchone()[0] == 2147483647
        assert py.execute("SELECT " + translated["PredIntJustAboveMin"].to_sql()).fetchone()[0] == -2147483648
        assert cpp.execute("SELECT " + translated["PredIntJustAboveMin"].to_sql()).fetchone()[0] == -2147483648
    finally:
        py.close()
        cpp.close()



def test_cql_round_macro_survives_integer_range_shift_cql11_historian2() -> None:
    """CQL-11 HISTORIAN2 QA-001: Round/RoundTo must not inherit the CQL
    Floor macro's TRY_CAST-to-INTEGER narrowing.

    CQL 1.5 Appendix B Round returns a Decimal; only results unrepresentable
    as Decimal(38, 8) are null. Previously the macros called FLOOR/CEIL,
    and Floor(x) is overridden in the same registration as the CQL Floor
    macro (TRY_CAST AS INTEGER), so any shifted magnitude above the Integer
    range rounded to NULL (RoundTo(123.456, 8) -> NULL).
    """
    cql = """library RoundMacro version '1.0.0'
using FHIR version '4.0.1'
context Patient
define RoundHighPrec: Round(2.12345678901234, 10)
define RoundPrec8Large: Round(123.456, 8)
define RoundPrec8Negative: Round(-123.456, 8)
define RoundNoPrecLarge: Round(3147483647.05)
define RoundNoPrecSmall: Round(-2.5)
define RoundPrec8Exact: Round(1.234567895, 8)
"""
    translated = translate_cql(cql)
    py = _python_only_connection()
    cpp = _cpp_connection()
    expected = {
        "RoundHighPrec": Decimal("2.12345679"),
        "RoundPrec8Large": Decimal("123.45600000"),
        "RoundPrec8Negative": Decimal("-123.45600000"),
        "RoundNoPrecLarge": Decimal("3147483647.00000000"),
        "RoundNoPrecSmall": Decimal("-3.00000000"),
        "RoundPrec8Exact": Decimal("1.23456790"),
    }
    try:
        for name, want in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            for label, con in (("python", py), ("cpp", cpp)):
                got = con.execute(sql).fetchone()[0]
                assert got == want, f"{name} ({label}): got {got!r}, expected {want!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_decimal_multiply_overflow_is_null_cql11_historian2() -> None:
    """CQL-11 HISTORIAN2 QA-002: Decimal arithmetic overflow -> null.

    CQL 1.5 Appendix B arithmetic header: overflow results in null rather
    than a run-time error. Statically-foldable Decimal literal products
    beyond DECIMAL(38, 8) must fold to NULL instead of raising DuckDB
    OutOfRangeException at execution.
    """
    cql = """library DecOverflow version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MulOverflow: 9999999999999999999999999999.0 * 9999999999999999999999999999.0
define MulInRange: 9999999999999999999999999999.0 * 2.0
"""
    translated = translate_cql(cql)
    assert translated["MulOverflow"].to_sql() == "NULL"

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, want in (
            ("MulOverflow", None),
            ("MulInRange", Decimal("19999999999999999999999999998.00000000")),
        ):
            sql = "SELECT " + translated[name].to_sql()
            for label, con in (("python", py), ("cpp", cpp)):
                got = con.execute(sql).fetchone()[0]
                assert got == want, f"{name} ({label}): got {got!r}, expected {want!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_integer_successor_boundary_nonliteral_is_null_cql11_explorer2() -> None:
    """CQL-11 EXPLORER2 QA-001: statically Integer non-literal successor/predecessor boundary -> null.

    CQL 1.5 Appendix B Arithmetic Operators header + Successor/Predecessor:
    "If the argument is already the maximum value for the type, a null is
    returned" / "If the result ... would result in an overflow, the result is
    null." DuckDB's BIGINT helper clamps only at Long bounds, so the
    translator must guard the Integer boundary for statically Integer-typed
    non-literal operands (literal forms were covered by CQL-11 EXPLORER
    QA-001).
    """
    cql = """library IntBoundary version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SuccIntMax: successor of Coalesce({2147483647})
define PredIntMin: predecessor of Coalesce({-2147483648})
define SuccIntNear: successor of Coalesce({2147483646})
define PredIntNear: predecessor of Coalesce({-2147483647})
define SuccIntNullable: successor of Coalesce(null, 2147483647)
define SuccLongMax: successor of Coalesce({9223372036854775807L})
define PredLongMin: predecessor of Coalesce({-9223372036854775808L})
"""
    translated = translate_cql(cql)
    assert "CASE WHEN" in translated["SuccIntMax"].to_sql()
    assert "CASE WHEN" in translated["PredIntMin"].to_sql()

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expected = {
            "SuccIntMax": None,
            "PredIntMin": None,
            "SuccIntNear": 2147483647,
            "PredIntNear": -2147483648,
            "SuccIntNullable": None,
            "SuccLongMax": None,
            "PredLongMin": None,
        }
        for name, want in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            for label, con in (("python", py), ("cpp", cpp)):
                got = con.execute(sql).fetchone()[0]
                assert got == want, f"{name} ({label}): got {got!r}, expected {want!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_negate_duration_between_cql11_explorer2() -> None:
    """CQL-11 EXPLORER2 QA-002: Negate over duration/difference between.

    CQL 1.5 Negate has Integer/Long/Decimal/Quantity overloads and duration
    between is Integer-valued, so `-(days between A and B)` is valid CQL.
    The lowering must normalize the VARCHAR-returning cqlDurationBetween /
    cqlDifferenceBetween helpers to a numeric type before applying prefix
    minus, otherwise DuckDB binder-fails with -(VARCHAR).
    """
    cql = """library NegDur version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NegDays: -(days between @2024-01-01 and @2024-01-10)
define NegMonths: -(months between @2023-01-01 and @2024-03-01)
define NegDiffDays: -(difference in days between @2024-01-01 and @2024-01-10)
"""
    translated = translate_cql(cql)
    for name in ("NegDays", "NegMonths", "NegDiffDays"):
        assert "TRY_CAST(" in translated[name].to_sql(), name

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expected = {"NegDays": -9, "NegMonths": -14, "NegDiffDays": -9}
        for name, want in expected.items():
            sql = "SELECT " + translated[name].to_sql()
            for label, con in (("python", py), ("cpp", cpp)):
                got = con.execute(sql).fetchone()[0]
                assert got == want, f"{name} ({label}): got {got!r}, expected {want!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_negate_quantity_preserves_unit_parity_cql11_explorer2() -> None:
    """CQL-11 EXPLORER2 QA-003: quantityNegate must preserve the unit verbatim.

    CQL 1.5 Negate: "When negating quantities, the unit is unchanged." The
    Python fallback previously round-tripped through pint, which normalizes
    calendar-duration keywords ('day') to UCUM ('d') and diverged from the
    native engine for `-(3 days)`.
    """
    cql = """library NegQty version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NegTemporal: -(3 days)
define NegCm: -(1.5 'cm')
define NegMg: -(5 'mg')
"""
    translated = translate_cql(cql)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in ("NegTemporal", "NegCm", "NegMg"):
            sql = "SELECT " + translated[name].to_sql()
            py_got = py.execute(sql).fetchone()[0]
            cpp_got = cpp.execute(sql).fetchone()[0]
            assert py_got == cpp_got, f"{name}: python {py_got!r} != cpp {cpp_got!r}"
        assert '"unit":"day"' in py.execute(
            "SELECT " + translated["NegTemporal"].to_sql()
        ).fetchone()[0]
        assert '"unit":"cm"' in py.execute(
            "SELECT " + translated["NegCm"].to_sql()
        ).fetchone()[0]
    finally:
        py.close()
        cpp.close()


def test_parse_expression_rejects_trailing_tokens_cql11_explorer2() -> None:
    """CQL-11 EXPLORER2 QA-004: parse_expression must consume the whole input.

    Bare Time literals require the @ prefix; `successor of T05:30` used to
    silently parse `successor of T05` and drop `:30`.
    """
    from fhir4ds.cql.errors import ParseError

    for bad in ("successor of T05:30", "Precision(T05:30:15.123"):
        with pytest.raises(ParseError):
            parse_expression(bad)
    for good in ("successor of @T05:30", "1 + 2", "Round(1.5, 0)", "Coalesce(null, 5)"):
        parse_expression(good)
