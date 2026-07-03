"""CQL primitive type parity checks for Python and C++ DuckDB registration."""

from __future__ import annotations

from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.conversion import ConvertsToInteger, ConvertsToLong, ToLong
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_primitive_literal_translation() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    cases = {
        "BooleanTrue": "true",
        "BooleanFalse": "false",
        "IntegerValue": "42",
        "LongValue": "42L",
        "DecimalValue": "1.25",
        "StringValue": "'hello'",
        "NullValue": "null",
    }

    cql = header + "\n".join(f"define {name}: {expr}" for name, expr in cases.items())
    translated = translate_cql(cql)

    assert set(cases) <= set(translated)
    assert "value=True" in str(translated["BooleanTrue"])
    assert "value=False" in str(translated["BooleanFalse"])
    assert "value=42" in str(translated["IntegerValue"])
    assert "value=42" in str(translated["LongValue"])
    assert "value=1.25" in str(translated["DecimalValue"])
    assert "value='hello'" in str(translated["StringValue"])
    assert "SQLNull" in str(translated["NullValue"])


def test_cql_primitive_type_and_boundary_translation() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define IntegerMin: -2147483648",
                "define DecimalMax: 9999999999999999999999999999.99999999",
                "define LongMax: 9223372036854775807L",
                "define LongMin: -9223372036854775808L",
                "define AnyCheck: 5 is Any",
                "define IntegerIsInteger: 5 is Integer",
                "define LongIsLong: 5L is Long",
                "define IntegerIsLong: 5 is Long",
                "define LongIsInteger: 5L is Integer",
                "define IntegerAsInteger: 5 as Integer",
                "define IntegerAsString: 5 as String",
                "define StringAsInteger: '5' as Integer",
                "define BooleanAsInteger: true as Integer",
                "define LongAsInteger: 5L as Integer",
                "define IntegerAsAny: 5 as Any",
            ]
        )
    )

    assert translated["IntegerMin"].to_sql() == "-2147483648"
    assert translated["DecimalMax"].to_sql() == "9999999999999999999999999999.99999999"
    assert translated["LongMax"].to_sql() == "9223372036854775807"
    assert translated["LongMin"].to_sql() == "-9223372036854775808"
    assert translated["AnyCheck"].to_sql() == "5 IS NOT NULL"
    assert translated["IntegerIsInteger"].to_sql() == "TRUE"
    assert translated["LongIsLong"].to_sql() == "TRUE"
    assert translated["IntegerIsLong"].to_sql() == "FALSE"
    assert translated["LongIsInteger"].to_sql() == "FALSE"
    assert translated["IntegerAsInteger"].to_sql() == "5"
    assert translated["IntegerAsString"].to_sql() == "NULL"
    assert translated["StringAsInteger"].to_sql() == "NULL"
    assert translated["BooleanAsInteger"].to_sql() == "NULL"
    assert translated["LongAsInteger"].to_sql() == "NULL"
    assert translated["IntegerAsAny"].to_sql() == "5"

    for invalid in [
        "2147483648",
        "-2147483649",
        "9223372036854775808L",
        "-9223372036854775809L",
    ]:
        try:
            translate_cql(header + f"define Invalid: {invalid}")
        except ValueError:
            continue
        raise AssertionError(f"Expected out-of-range primitive literal to fail: {invalid}")

    for invalid in ["1LL", "1.0L", "1day", "1l"]:
        with pytest.raises(Exception):
            parse_expression(invalid)


def test_cql_primitive_negate_of_minimum_returns_null_per_spec() -> None:
    """CQL §16 Negate: -(minimum Integer) and -(minimum Long) must be NULL.

    The spec example explicitly references -(minimum Integer) returning null
    when the negation cannot be represented. This must also hold for
    literal-spelled minima (e.g. ``-(-2147483648)``) since they represent
    the same value.
    """
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define NegateMinIntFunction: -(minimum Integer)",
                "define NegateMinIntLiteral: -(-2147483648)",
                "define NegateMinLongFunction: -(minimum Long)",
                "define NegateMinLongLiteral: -(-9223372036854775808L)",
            ]
        )
    )
    for name in ("NegateMinIntFunction", "NegateMinIntLiteral",
                 "NegateMinLongFunction", "NegateMinLongLiteral"):
        assert translated[name].to_sql() == "NULL", (
            f"{name} should translate to NULL per CQL §16 Negate spec; got "
            f"{translated[name].to_sql()!r}"
        )


def test_cql_primitive_abs_of_minimum_returns_null_per_spec() -> None:
    """CQL §16 Abs: Abs(minimum Integer) and Abs(minimum Long) must be NULL.

    The spec example explicitly references ``Abs(minimum Integer)`` returning
    null when the absolute value cannot be represented. This must hold for
    both the ``minimum Integer`` FunctionRef form and the literal-spelled
    ``Abs(-2147483648)`` form, because they represent the same value. Without
    the FunctionRef guard, DuckDB auto-promotes ``abs(-2147483648)`` to a
    valid BIGINT (2147483648) and ``TRY()`` sees no error, leaking the
    out-of-range Integer value through.
    """
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define AbsMinIntFunction: Abs(minimum Integer)",
                "define AbsMinIntLiteral: Abs(-2147483648)",
                "define AbsMinLongFunction: Abs(minimum Long)",
                "define AbsMinLongLiteral: Abs(-9223372036854775808L)",
                "define AbsPosInt: Abs(-5)",
                "define AbsPosLong: Abs(-5L)",
                "define AbsDecimal: Abs(-5.5)",
            ]
        )
    )

    # All four minimum-extreme forms must lower to NULL at translation time.
    for name in ("AbsMinIntFunction", "AbsMinIntLiteral",
                 "AbsMinLongFunction", "AbsMinLongLiteral"):
        assert translated[name].to_sql() == "NULL", (
            f"{name} should translate to NULL per CQL §16 Abs spec; got "
            f"{translated[name].to_sql()!r}"
        )

    # Positive forms must still execute correctly on both backends.
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expected = {"AbsPosInt": 5, "AbsPosLong": 5, "AbsDecimal": Decimal("5.5")}
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,)
            assert cpp.execute(sql).fetchone() == (value,)

        # And the four minimum-extreme NULLs must execute to NULL on both.
        for name in ("AbsMinIntFunction", "AbsMinIntLiteral",
                     "AbsMinLongFunction", "AbsMinLongLiteral"):
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (None,), (
                f"{name} should execute to NULL on Python fallback"
            )
            assert cpp.execute(sql).fetchone() == (None,), (
                f"{name} should execute to NULL on native C++ backend"
            )
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_power_operator_returns_spec_typed_result() -> None:
    """CQL §16 Power: ^(Integer,Integer) Integer, ^(Long,Long) Long, etc.

    Integer overflow must yield NULL. Decimal operands keep DOUBLE typing.
    """
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define IntPower: 2^3",
                "define LongPower: 2L^3L",
                "define DecimalPower: 2.5^2.0",
            ]
        )
    )
    # Integer^Integer must cast to INTEGER (so overflow returns NULL at runtime)
    assert "AS INTEGER" in translated["IntPower"].to_sql(), (
        f"2^3 should target INTEGER per spec; got {translated['IntPower'].to_sql()!r}"
    )
    # Long^Long must cast to BIGINT
    assert "AS BIGINT" in translated["LongPower"].to_sql(), (
        f"2L^3L should target BIGINT per spec; got {translated['LongPower'].to_sql()!r}"
    )
    # Decimal^Decimal uses DECIMAL(38, 8) so overflow returns NULL per spec
    assert "AS DECIMAL(38, 8)" in translated["DecimalPower"].to_sql(), (
        f"2.5^2.0 should target DECIMAL(38, 8) for overflow detection; got {translated['DecimalPower'].to_sql()!r}"
    )

    # Runtime overflow check: 2^31 exceeds Integer max -> NULL
    overflow_sql = translate_cql(header + "define Overflow: 2^31")["Overflow"].to_sql()
    cpp_con = _cpp_connection()
    try:
        row = cpp_con.execute(f"SELECT ({overflow_sql}) AS v").fetchone()
        assert row[0] is None, f"2^31 should overflow Integer and return NULL; got {row[0]!r}"
    finally:
        cpp_con.close()


def test_cql_primitive_duckdb_surface_matches_cpp_registration() -> None:
    expressions = [
        'SELECT "And"(true, false)',
        'SELECT "Or"(true, false)',
        'SELECT "Not"(false)',
        'SELECT "Implies"(true, false)',
        'SELECT "IsTrue"(true)',
        'SELECT "IsFalse"(false)',
        "SELECT ToString(123)",
        "SELECT ToInteger('42')",
        "SELECT ToInteger(true)",
        "SELECT ToInteger('1.0')",
        "SELECT ToInteger('1.5')",
        "SELECT ToDecimal('1.25')",
        "SELECT ToBoolean('true')",
        "SELECT ConvertsToInteger('1.0')",
        "SELECT ConvertsToInteger('1.5')",
        "SELECT ConvertsToLong(true)",
        "SELECT ToLong(true)",
        "SELECT logicalImplies(true, false)",
        "SELECT logicalImplies(NULL, false)",
        "SELECT fhirpath_text('{\"resourceType\":\"Patient\",\"active\":true}'::JSON, 'active')",
        "SELECT fhirpath_number('{\"resourceType\":\"Observation\",\"valueInteger\":42}'::JSON, 'value')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
        assert py.execute("SELECT ToInteger('1.0')").fetchone() == (None,)
        assert py.execute("SELECT ToInteger('1.5')").fetchone() == (None,)
        assert py.execute("SELECT ToInteger(true)").fetchone() == (1,)
        assert py.execute("SELECT ConvertsToInteger('1.0')").fetchone() == (False,)
        assert py.execute("SELECT ConvertsToLong(true), ToLong(true)").fetchone() == (True, 1)
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_string_escapes_match_spec_on_duckdb_backends() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define EscapedSlash: 'a\\/b'",
                "define EscapedBacktick: 'a\\`b'",
                "define UnknownEscapesRemainLiteral: 'a\\v\\0\\bb'",
            ]
        )
    )

    expected = {
        "EscapedSlash": "a/b",
        "EscapedBacktick": "a`b",
        "UnknownEscapesRemainLiteral": "a\\v\\0\\bb",
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,)
            assert cpp.execute(sql).fetchone() == (value,)
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_as_type_assertions_execute_as_null_on_mismatch() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define IntegerAsInteger: 5 as Integer",
                "define IntegerAsString: 5 as String",
                "define StringAsInteger: '5' as Integer",
                "define BooleanAsInteger: true as Integer",
                "define LongAsLong: 5L as Long",
                "define LongAsInteger: 5L as Integer",
                "define NullAsInteger: null as Integer",
                "define IntegerAsAny: 5 as Any",
                "define DynamicStringAsInteger: ToString(5) as Integer",
                "define DynamicIntegerAsString: ToInteger('5') as String",
                "define DynamicLongAsLong: ToLong('5') as Long",
                "define DynamicLongAsInteger: ToLong('5') as Integer",
            ]
        )
    )

    expected = {
        "IntegerAsInteger": 5,
        "IntegerAsString": None,
        "StringAsInteger": None,
        "BooleanAsInteger": None,
        "LongAsLong": 5,
        "LongAsInteger": None,
        "NullAsInteger": None,
        "IntegerAsAny": 5,
        "DynamicStringAsInteger": None,
        "DynamicIntegerAsString": None,
        "DynamicLongAsLong": 5,
        "DynamicLongAsInteger": None,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,)
            assert cpp.execute(sql).fetchone() == (value,)

        fhir_value_sql = translate_cql(
            header + "define FhirIntegerAsInteger: AUASIAssessment.value as Integer"
        )["FhirIntegerAsInteger"].to_sql()
        query = f"SELECT {fhir_value_sql} FROM (SELECT ?::JSON AS AUASIAssessment)"
        resource = '{"resourceType":"Observation","valueInteger":5}'
        assert py.execute(query, [resource]).fetchone() == (5,)
        assert cpp.execute(query, [resource]).fetchone() == (5,)

        fhir_translated = translate_cql(
            header
            + "\n".join(
                [
                    "define FhirAsInteger: O.value as Integer",
                    "define FhirAsString: O.value as String",
                    "define FhirAsBoolean: O.value as Boolean",
                    "define FhirAsDecimal: O.value as Decimal",
                    "define FhirIsInteger: O.value is Integer",
                    "define FhirIsString: O.value is String",
                    "define FhirIsBoolean: O.value is Boolean",
                    "define FhirIsDecimal: O.value is Decimal",
                ]
            )
        )
        resources = {
            "valueInteger": (
                '{"resourceType":"Observation","valueInteger":5}',
                {
                    "FhirAsInteger": 5,
                    "FhirAsString": None,
                    "FhirAsBoolean": None,
                    "FhirAsDecimal": None,
                    "FhirIsInteger": True,
                    "FhirIsString": False,
                    "FhirIsBoolean": False,
                    "FhirIsDecimal": False,
                },
            ),
            "valueStringNumber": (
                '{"resourceType":"Observation","valueString":"5"}',
                {
                    "FhirAsInteger": None,
                    "FhirAsString": "5",
                    "FhirAsBoolean": None,
                    "FhirAsDecimal": None,
                    "FhirIsInteger": False,
                    "FhirIsString": True,
                    "FhirIsBoolean": False,
                    "FhirIsDecimal": False,
                },
            ),
            "valueStringBoolean": (
                '{"resourceType":"Observation","valueString":"true"}',
                {
                    "FhirAsInteger": None,
                    "FhirAsString": "true",
                    "FhirAsBoolean": None,
                    "FhirAsDecimal": None,
                    "FhirIsInteger": False,
                    "FhirIsString": True,
                    "FhirIsBoolean": False,
                    "FhirIsDecimal": False,
                },
            ),
            "valueBoolean": (
                '{"resourceType":"Observation","valueBoolean":true}',
                {
                    "FhirAsInteger": None,
                    "FhirAsString": None,
                    "FhirAsBoolean": True,
                    "FhirAsDecimal": None,
                    "FhirIsInteger": False,
                    "FhirIsString": False,
                    "FhirIsBoolean": True,
                    "FhirIsDecimal": False,
                },
            ),
            "valueDecimal": (
                '{"resourceType":"Observation","valueDecimal":1.25}',
                {
                    "FhirAsInteger": None,
                    "FhirAsString": None,
                    "FhirAsBoolean": None,
                    "FhirAsDecimal": 1.25,
                    "FhirIsInteger": False,
                    "FhirIsString": False,
                    "FhirIsBoolean": False,
                    "FhirIsDecimal": True,
                },
            ),
        }
        for _label, (resource, expected_values) in resources.items():
            for name, expected_value in expected_values.items():
                sql = f"SELECT {fhir_translated[name].to_sql()} FROM (SELECT ?::JSON AS O)"
                assert py.execute(sql, [resource]).fetchone() == (expected_value,)
                assert cpp.execute(sql, [resource]).fetchone() == (expected_value,)
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_parameter_defaults_preserve_declared_type() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "parameter P Integer default 5",
                "parameter D Decimal default 1.2300",
                "parameter S String default 'abc'",
                "parameter N Integer default null",
                "define PValue: P",
                "define PIsInteger: P is Integer",
                "define PIsString: P is String",
                "define PAsInteger: P as Integer",
                "define PAsString: P as String",
                "define PPlusOne: P + 1",
                "define DString: ToString(D)",
                "define SIsString: S is String",
                "define NIsAny: N is Any",
            ]
        )
    )

    expected = {
        "PValue": 5,
        "PIsInteger": True,
        "PIsString": False,
        "PAsInteger": 5,
        "PAsString": None,
        "PPlusOne": 6,
        "DString": "1.2300",
        "SIsString": True,
        "NIsAny": False,
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,)
            assert cpp.execute(sql).fetchone() == (value,)
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_runtime_parameters_preserve_declared_type_in_population_sql() -> None:
    cql = """library Test version '1.0.0'
using FHIR version '4.0.1'
context Patient
parameter P Integer
define PPlusOne: P + 1
define PIsInteger: P is Integer
define PIsString: P is String
"""
    library = parse_cql(cql)
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={
            "p_plus_one": "PPlusOne",
            "p_is_integer": "PIsInteger",
            "p_is_string": "PIsString",
        },
        parameters={"P": 5},
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
        ('p1', 'Patient', 'p1', '{"resourceType":"Patient","id":"p1"}'::JSON)
        """,
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for statement in setup_sql:
                con.execute(statement)
        assert py.execute(sql).fetchone() == ("p1", 6, True, False)
        assert cpp.execute(sql).fetchone() == ("p1", 6, True, False)
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_any_assertions_keep_scalar_definition_shape() -> None:
    cql = """library Test version '1.0.0'
using FHIR version '4.0.1'
context Patient
parameter PI Integer default 5
parameter PD Decimal default 1.2300
define I: PI
define D: PD
define IAlias: I
define DAlias: D
define AnyFromInteger: I as Any
define AnyFromSystemInteger: I as System.Any
define AnyThenInteger: (I as System.Any) as System.Integer
define AnyThenString: (I as System.Any) as System.String
define IntegerIsSystemInteger: I is System.Integer
define IntegerAsSystemInteger: I as System.Integer
define IntegerAsSystemLong: I as System.Long
define AliasIsInteger: IAlias is Integer
define AliasPlus: IAlias + 1
define DecimalAliasString: ToString(DAlias)
define NonNullIsSystemAny: I is System.Any
"""
    library = parse_cql(cql)
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={
            "any_from_integer": "AnyFromInteger",
            "any_from_system_integer": "AnyFromSystemInteger",
            "any_then_integer": "AnyThenInteger",
            "any_then_string": "AnyThenString",
            "is_system_integer": "IntegerIsSystemInteger",
            "as_system_integer": "IntegerAsSystemInteger",
            "as_system_long": "IntegerAsSystemLong",
            "alias_is_integer": "AliasIsInteger",
            "alias_plus": "AliasPlus",
            "decimal_alias_string": "DecimalAliasString",
            "nonnull_is_system_any": "NonNullIsSystemAny",
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
        ('p1', 'Patient', 'p1', '{"resourceType":"Patient","id":"p1"}'::JSON)
        """,
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for statement in setup_sql:
                con.execute(statement)
        expected = ("p1", 5, 5, 5, None, True, 5, None, True, 6, "1.2300", True)
        assert py.execute(sql).fetchone() == expected
        assert cpp.execute(sql).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_conversion_translation_uses_spec_boundaries() -> None:
    header = "library Test version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n"
    translated = translate_cql(
        header
        + "\n".join(
            [
                "define ToIntegerDecimalString: ToInteger('1.5')",
                "define ToIntegerWholeDecimalString: ToInteger('1.0')",
                "define ToIntegerDecimal: ToInteger(1.5)",
                "define ConvertDecimalStringToInteger: convert '1.5' to Integer",
                "define ConvertDecimalToInteger: convert 1.5 to Integer",
                "define ToBooleanInvalidString: ToBoolean('2')",
                "define ToDecimalBoolean: ToDecimal(true)",
                "define ToDecimalPreciseString: ToDecimal('25.12345')",
            ]
        )
    )
    expected = {
        "ToIntegerDecimalString": None,
        "ToIntegerWholeDecimalString": None,
        "ToIntegerDecimal": None,
        "ConvertDecimalStringToInteger": None,
        "ConvertDecimalToInteger": None,
        "ToBooleanInvalidString": None,
        "ToDecimalBoolean": Decimal("1.00000000"),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (value,)
            assert cpp.execute(sql).fetchone() == (value,)

        precise_sql = f"SELECT CAST({translated['ToDecimalPreciseString'].to_sql()} AS VARCHAR)"
        assert py.execute(precise_sql).fetchone() == ("25.12345000",)
        assert cpp.execute(precise_sql).fetchone() == ("25.12345000",)

        direct_expressions = [
            "SELECT ToDecimal('25.12345')::VARCHAR, typeof(ToDecimal('25.12345'))",
            "SELECT ToDecimal('true')",
            "SELECT ToDecimal(true), ConvertsToDecimal(true)",
            "SELECT ToBoolean('2')",
            "SELECT ToBoolean(2), ConvertsToBoolean(2)",
        ]
        for expression in direct_expressions:
            assert py.execute(expression).fetchone() == cpp.execute(expression).fetchone()
        assert py.execute("SELECT ToDecimal(true)::VARCHAR, ToBoolean('2')").fetchone() == ("1.00000000", None)
        assert py.execute(
            "SELECT ToDecimal('1e2'), ToDecimal('.5'), ToDecimal('1.'), "
            "ToDecimal('1.123456789'), ToDecimal('1000000000000000000000000000000')"
        ).fetchone() == (
            None,
            None,
            None,
            None,
            None,
        )
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_type_assertions_survive_materialized_ctes() -> None:
    cql = """library Test version '1.0.0'
using FHIR version '4.0.1'
context Patient
define V: First([Observation] O return O.valueQuantity.value)
define VIsString: V is String
define VAsString: V as String
define VIsDecimal: V is Decimal
define VAsDecimal: V as Decimal
"""
    library = parse_cql(cql)
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        library,
        output_columns={
            "v": "V",
            "is_string": "VIsString",
            "as_string": "VAsString",
            "is_decimal": "VIsDecimal",
            "as_decimal": "VAsDecimal",
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
        ('p1', 'Observation', 'o1', '{"resourceType":"Observation","id":"o1","subject":{"reference":"Patient/p1"},"valueQuantity":{"value":1.5,"unit":"mg"}}'::JSON)
        """,
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            for statement in setup_sql:
                con.execute(statement)
        expected = ("p1", "1.500000", False, None, True, 1.5)
        assert py.execute(sql).fetchone() == expected
        assert cpp.execute(sql).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def test_cql_primitive_direct_conversion_apis() -> None:
    assert ConvertsToInteger("2147483647") is True
    assert ConvertsToInteger("2147483648") is False
    assert ConvertsToInteger("1.0") is False
    assert ConvertsToInteger("1.5") is False
    assert ConvertsToInteger(True) is True

    assert ConvertsToLong("9223372036854775807") is True
    assert ConvertsToLong("9223372036854775808") is False
    assert ConvertsToLong("1.0") is False
    assert ConvertsToLong(True) is True
    assert ToLong(True) == 1
