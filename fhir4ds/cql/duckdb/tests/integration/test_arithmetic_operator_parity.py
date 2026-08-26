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
    # CQL-01 HISTORIAN doctrine: scalar `/` must lower to the exact
    # cqlDivide UDF (DuckDB native `/` promotes DECIMAL to DOUBLE).
    assert "cqlDivide" in str(translated["DivideCheck"])
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

        # CQL v1.5.3 §16.6 Exp and §16.12 Ln both mandate NULL when the
        # result cannot be represented (Exp overflow to +infinity, Ln(0)
        # underflow to -infinity). The section header reinforces: "operations
        # that cause arithmetic overflow or underflow ... will result in
        # null, rather than a run-time error." These must NOT raise.
        for expression in [
            "SELECT Exp(1000)",
            "SELECT Ln(0)",
            "SELECT mathExp('1000')",
            "SELECT mathLn('0')",
        ]:
            assert py.execute(expression).fetchone() == (None,)
            assert cpp.execute(expression).fetchone() == (None,)
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
        # CQL v1.5.3 §16.6 Exp: "If the result of the operation cannot be
        # represented, the result is null." Exp(1000) overflows to +infinity
        # which cannot be represented -> NULL (not a runtime error).
        "ExpOverflow",
        # CQL v1.5.3 §16.12 Ln: "If the result of the operation cannot be
        # represented, the result is null." Ln(0) underflows to -infinity
        # which cannot be represented -> NULL (not a runtime error).
        "LnZero",
        "LnNegative",
        "LogBadBase",
        "DecimalHighTooPrecise",
        "DateHighTooPrecise",
        "TimeLowTooPrecise",
    ]
    expected_errors: list[str] = []

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

        # CQL-10 EXPLORER QA-002: statically-known scalar-vs-Quantity Add
        # mixtures now raise a typed TranslationError (no §9.1 overload)
        # instead of silently translating to NULL.
        for expr in ("10 'mg' + 2", "2 + 10 'mg'", "(O.value as Quantity) + 1"):
            with pytest.raises(TranslationError):
                translate_cql(
                    "library StaticMixed version '1.0.0'\n"
                    "using FHIR version '4.0.1'\n"
                    "context Patient\n"
                    f"define X: {expr}\n"
                )
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
    from decimal import Decimal

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
        "DecimalHighDefault": Decimal("1.58799999"),
        "DecimalLowDefault": Decimal("1.58700000"),
        "DateHighDefault": "2014",
        "DateLowDefault": "2014",
        "DateTimeHighDefault": "2014-01-01T08:59:59.999",
        "DateTimeLowDefault": "2014-01-01T08:00:00.000",
        "TimeHighDefault": "T10:30:59.999",
        "TimeLowDefault": "T10:30:00.000",
        "LogBaseTwo": Decimal("4.00000000"),
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


def test_cql10_spec_compliance_boundaries_typing_and_promotion() -> None:
    """CQL-10 SKEPTIC re-launch (2026-08-21) spec-compliance regression tests.

    Covers five fixes verified against CQL 1.5 Appendix B and the HL7
    reference implementation (HighBoundaryEvaluator/LowBoundaryEvaluator
    in cqframework/clinical_quality_language):
    1. High/LowBoundary Decimal precision truncation at the requested
       precision (fill-and-truncate, matching BigDecimal.setScale(DOWN)).
    2. Ceiling/Floor Integer-extent null rule.
    3. Mixed Integer+Long Add implicit promotion to Long.
    4. Abs typed-overflow null for statically integral operands.
    5. Exp/Ln/Log Decimal (scale-8) result typing.
    """
    cql = """library Cql10SpecCompliance version '1.0.0'
using FHIR version '4.0.1'
context Patient
define High587P2: HighBoundary(1.587, 2)
define Low587P2: LowBoundary(1.587, 2)
define High587P8: HighBoundary(1.587, 8)
define Low587P8: LowBoundary(1.587, 8)
define High5P2: HighBoundary(1.5, 2)
define HighNegP2: HighBoundary(-1.587, 2)
define CeilIn: Ceiling(2147483646.05)
define FloorIn: Floor(-2147483647.5)
define CeilOut: Ceiling(2147483647.05)
define FloorOut: Floor(2147483648.2)
define CeilBig: Ceiling(99999999999999999999999.5)
define AddIntLong: 1 + 2147483647L
define AddLongInt: 2147483647L + 1
define AbsIntOverflowExpr: Abs(-2147483648 - 0)
define AbsLongOverflowExpr: Abs(-9223372036854775807L - 1L)
define AbsIntOk: Abs(-2147483647 - 0)
define ExpDecimalType: Exp(1)
define LnDecimalType: Ln(10)
define LogDecimalType: Log(16, 2)
"""
    translated = translate_cql(cql)

    # 5. Decimal result typing (CQL-01 exact-Decimal doctrine).
    assert "DECIMAL(38, 8)" in translated["ExpDecimalType"].to_sql()
    assert "DECIMAL(38, 8)" in translated["LnDecimalType"].to_sql()
    assert "DECIMAL(38, 8)" in translated["LogDecimalType"].to_sql()
    # 2. Typed Integer narrowing for Ceiling/Floor.
    assert "AS INTEGER" in translated["CeilIn"].to_sql()
    # 4. Typed Integer/Long narrowing for Abs on integral operands.
    assert "AS INTEGER" in translated["AbsIntOverflowExpr"].to_sql()
    assert "AS BIGINT" in translated["AbsLongOverflowExpr"].to_sql()
    # 3. Mixed Integer/Long promotion to BIGINT.
    for name in ("AddIntLong", "AddLongInt"):
        sql_text = translated[name].to_sql()
        assert "BIGINT" in sql_text, sql_text

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        def fetch(con, name, cast=True):
            sql = translated[name].to_sql()
            sql = f"SELECT ({sql})" if cast else f"SELECT {sql}"
            return con.execute(sql).fetchone()[0]

        from decimal import Decimal as _Dec

        expected_values = {
            "High587P2": _Dec("1.58000000"),
            "Low587P2": _Dec("1.58000000"),
            "High587P8": _Dec("1.58799999"),
            "Low587P8": _Dec("1.58700000"),
            "High5P2": _Dec("1.59000000"),
            "HighNegP2": "-1.58",
            "CeilIn": 2147483647,
            "FloorIn": -2147483648,
            "AbsIntOk": 2147483647,
        }
        expected_nulls = [
            "CeilOut",
            "FloorOut",
            "CeilBig",
            "AbsIntOverflowExpr",
            "AbsLongOverflowExpr",
        ]
        for name, value in expected_values.items():
            assert fetch(py, name) == value, (name, fetch(py, name))
            assert fetch(cpp, name) == value, (name, fetch(cpp, name))
        for name in expected_nulls:
            assert fetch(py, name) is None, name
            assert fetch(cpp, name) is None, name
        # Long promotion results (Python int / duckdb int64).
        assert fetch(py, "AddIntLong") == 2147483648
        assert fetch(cpp, "AddIntLong") == 2147483648
        assert fetch(py, "AddLongInt") == 2147483648
        assert fetch(cpp, "AddLongInt") == 2147483648
        # Decimal-typed transcendental results, scale 8.
        from decimal import Decimal

        assert fetch(py, "ExpDecimalType") == Decimal("2.71828183")
        assert fetch(cpp, "ExpDecimalType") == Decimal("2.71828183")
        assert fetch(py, "LnDecimalType") == Decimal("2.30258509")
        assert fetch(cpp, "LnDecimalType") == Decimal("2.30258509")
        assert fetch(py, "LogDecimalType") == Decimal("4.00000000")
        assert fetch(cpp, "LogDecimalType") == Decimal("4.00000000")

        # UDF/macro surfaces (both backends must agree).
        for expression in [
            "SELECT HighBoundary('1.587', 2)",
            "SELECT LowBoundary('1.587', 2)",
            "SELECT HighBoundary('1.587', 0)",
            "SELECT mathCeiling('3147483647.05')",
            "SELECT mathFloor('2147483648.2')",
            "SELECT mathCeiling('2147483646.05')",
        ]:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone(), expression
        assert py.execute("SELECT mathCeiling('3147483647.05')").fetchone() == (None,)
        assert cpp.execute("SELECT mathCeiling('3147483647.05')").fetchone() == (None,)
        assert py.execute("SELECT HighBoundary('1.587', 0)").fetchone() == ("1",)
        assert cpp.execute("SELECT HighBoundary('1.587', 0)").fetchone() == ("1",)
    finally:
        py.close()
        cpp.close()


def test_cql10_historian_exact_decimal_boundaries_and_typed_errors() -> None:
    """CQL-10 HISTORIAN (2026-08-21) QA-001/QA-002 regression tests.

    QA-001: High/LowBoundary Decimal results must stay exact Decimals with
    fixture-mandated scale-8 rendering (CqlArithmeticFunctionsTest.xml
    LowBoundaryDecimal expects 1.58700000); no DOUBLE round-trip corruption
    for >15-significant-digit inputs.
    QA-002: statically wrong-typed operands for the arithmetic operator
    family raise a uniform typed TranslationError (CQL 1.5 §16 has no
    String/Boolean overloads; Table 9-E defines no implicit conversion) —
    no silent nulls, no raw DuckDB Binder/Conversion leaks.
    """
    from decimal import Decimal

    cql = """library Cql10Historian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define HBBig: HighBoundary(123456789012345678901234.5, 8)
define LBBig: LowBoundary(123456789012345678901234.5, 8)
define LBFull8: LowBoundary(1.587, 8)
"""
    translated = translate_cql(cql)
    for name in ("HBBig", "LBBig", "LBFull8"):
        sql_text = translated[name].to_sql()
        assert "DECIMAL(38, 8)" in sql_text, sql_text
        assert "AS DOUBLE" not in sql_text, sql_text

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        def fetch(con, name):
            sql = f"SELECT ({translated[name].to_sql()})"
            value = con.execute(sql).fetchone()[0]
            return Decimal(str(value))

        assert fetch(py, "HBBig") == Decimal("123456789012345678901234.59999999")
        assert fetch(cpp, "HBBig") == Decimal("123456789012345678901234.59999999")
        assert fetch(py, "LBBig") == Decimal("123456789012345678901234.50000000")
        assert fetch(cpp, "LBBig") == Decimal("123456789012345678901234.50000000")
        assert fetch(py, "LBFull8") == Decimal("1.58700000")
        assert fetch(cpp, "LBFull8") == Decimal("1.58700000")
        # Scale-8 text rendering via VARCHAR cast matches the official fixture.
        assert py.execute(
            f"SELECT ({translated['LBFull8'].to_sql()})::VARCHAR"
        ).fetchone()[0] == "1.58700000"
        assert cpp.execute(
            f"SELECT ({translated['LBFull8'].to_sql()})::VARCHAR"
        ).fetchone()[0] == "1.58700000"
    finally:
        py.close()
        cpp.close()

    # QA-002: every statically wrong-typed operand must raise the same typed
    # TranslationError, mirroring Add's contract.
    wrong_typed = [
        "1 + 'x'",
        "'x' + 1",
        "1 / 'x'",
        "'x' / 2",
        "2 * 'x'",
        "'x' - 2",
        "2 ^ 'x'",
        "Abs('x')",
        "Abs(true)",
        "Ceiling('x')",
        "Ceiling(true)",
        "Floor('x')",
        "Exp('x')",
        "Ln('x')",
        "Log('x', 2)",
        "Log(8, 'x')",
        "HighBoundary('x', 2)",
        "LowBoundary('x', 2)",
        "HighBoundary(1.587, 'x')",
    ]
    for expression in wrong_typed:
        library = (
            "library T version '1'\nusing FHIR version '4.0.1'\ncontext Patient\n"
            f"define Z: {expression}"
        )
        with pytest.raises(TranslationError):
            translated = translate_cql(library)
        # (pytest.raises consumed the error; keep the loop var meaningful)
        _ = translated


def test_cql10_explorer_quantity_divide_unit_cancellation_and_typed_mixed_guards() -> None:
    """CQL-10 EXPLORER iteration 1 regression tests.

    QA-001 (HIGH): CQL 1.5 §9.4 Divide — "For division operations involving
    quantities, the resulting quantity will have the appropriate unit." The
    reference engine (cqframework DivideEvaluator.kt) uses
    ucumService.divideBy, which applies the unit conversion factor and
    cancels commensurable units: 1000 'mg' / 1 'g' = 1.0 '1', not
    1000 'mg/g'. Both the pint-backed Python UDF (to_reduced_units) and the
    native quantity_divide (units_compatible + to_base ratio) must agree.

    QA-002 (MEDIUM): statically-known scalar-vs-Quantity mixtures with no
    valid CQL 1.5 §9 overload (Add/Sub: Quantity only against Quantity;
    Divide: no scalar-left/Quantity-right signature; Power: no Quantity
    overload) and Quantity inputs to Ceiling/Floor/Exp/Ln/Log/
    High/LowBoundary (no Quantity overload per §16; Abs keeps its valid
    Quantity overload) must raise a typed TranslationError instead of
    silently translating to NULL.
    """
    cql = """library QuantityDivideUnits version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DivCommensurable: 1000 'mg' / 1 'g'
define DivCommensurableDec: 1.5 'g' / 250 'mg'
define DivLikeUnits: 10 'mg' / 2 'mg'
define DivIncommensurable: 8 'mg' / 2 'mL'
define DivSpecExample: 12 'cm2' / 3 'cm'
define DivByUnity: 8 'mg' / 2 '1'
define DivQByScalar: 10 'mg' / 2
define MulScalarQty: 2 * 3 'mg'
define AbsQuantity: Abs(-5 'mg')
define TemporalPlusQuantity: @2024-01-01 + 1 'day'
"""
    translated = translate_cql(cql)
    expected = {
        "DivCommensurable": (1.0, "1"),
        "DivCommensurableDec": (6.0, "1"),
        "DivLikeUnits": (5.0, "1"),
        "DivIncommensurable": (4.0, "mg/mL"),
        "DivSpecExample": (4.0, "cm"),
        "DivByUnity": (4.0, "mg"),
        "DivQByScalar": (5.0, "mg"),
        "MulScalarQty": (6.0, "mg"),
        "AbsQuantity": (5.0, "mg"),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, (value, unit) in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            for engine, con in (("python", py), ("cpp", cpp)):
                row = con.execute(sql).fetchone()[0]
                parsed = json.loads(row)
                assert parsed["value"] == value, (engine, name, parsed)
                assert parsed["unit"] == unit, (engine, name, parsed)
        assert str(py.execute(f"SELECT {translated['TemporalPlusQuantity'].to_sql()}").fetchone()[0]) == "2024-01-02"
        assert str(cpp.execute(f"SELECT {translated['TemporalPlusQuantity'].to_sql()}").fetchone()[0]) == "2024-01-02"
    finally:
        py.close()
        cpp.close()

    invalid = [
        "1 + 1 'mg'",
        "1 'mg' + 1",
        "1 - 1 'mg'",
        "1 'mg' - 1",
        "10 / 2 'mg'",
        "2 ^ 2 'mg'",
        "2 'mg' ^ 2",
        "Ceiling(5 'mg')",
        "Floor(5 'mg')",
        "Exp(5 'mg')",
        "Ln(5 'mg')",
        "Log(5 'mg', 2)",
        "HighBoundary(5 'mg', 3)",
        "LowBoundary(5 'mg', 3)",
        "HighBoundary(5 'mg')",
    ]
    for expr in invalid:
        library = (
            "library TypedMixed version '1.0.0'\n"
            "using FHIR version '4.0.1'\n"
            "context Patient\n"
            f"define X: {expr}\n"
        )
        with pytest.raises(TranslationError):
            translate_cql(library)
