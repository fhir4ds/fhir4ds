"""CQL logical operator truth-table parity checks."""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.errors import TranslationError
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.translator import CQLToSQLTranslator


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_logical_truth_tables_match_cpp_registration() -> None:
    values = ["true", "false", "NULL"]
    expressions = []
    for left in values:
        for right in values:
            expressions.extend(
                [
                    f'SELECT "And"({left}, {right})',
                    f'SELECT "Or"({left}, {right})',
                    f'SELECT "Xor"({left}, {right})',
                    f'SELECT "Implies"({left}, {right})',
                    f"SELECT logicalImplies({left}, {right})",
                ]
            )
    for value in values:
        expressions.append(f'SELECT "Not"({value})')

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert cpp.execute(expression).fetchone() == py.execute(expression).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_direct_logical_helpers_do_not_use_duckdb_truthiness() -> None:
    expressions = [
        'SELECT "And"(1, true)',
        "SELECT \"And\"('x', true)",
        'SELECT "Or"(false, 1)',
        'SELECT "Xor"(1, false)',
        'SELECT "Implies"(1, false)',
        'SELECT "Not"(1)',
        "SELECT logicalImplies('yes', 'false')",
        "SELECT logicalImplies('bad', 'true')",
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for expression in expressions:
            assert py.execute(expression).fetchone() == (None,), expression
            assert cpp.execute(expression).fetchone() == (None,), expression
    finally:
        py.close()
        cpp.close()


def test_cql_logical_operators_survive_query_let_return_population_sql() -> None:
    cql = """
library CQL04LogicalMeasureSurface version '1.0.0'
using FHIR version '4.0.1'
context Patient

define QueryWhereLogic:
  exists ([Observation] O
    let HasHighValue: O.value > 10,
        IsFinal: O.status = 'final'
    where HasHighValue and IsFinal or false
    return O)

define QueryReturnLogic:
  singleton from ([Observation] O
    let HasHighValue: O.value > 10,
        IsFinal: O.status = 'final'
    where O.id = 'o1'
    return HasHighValue implies IsFinal)
"""
    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "QueryWhereLogic": "QueryWhereLogic",
            "QueryReturnLogic": "QueryReturnLogic",
        },
    )

    patient = json.dumps({"resourceType": "Patient", "id": "p1"})
    observations = [
        json.dumps(
            {
                "resourceType": "Observation",
                "id": "o1",
                "subject": {"reference": "Patient/p1"},
                "status": "preliminary",
                "valueInteger": 15,
            }
        ),
        json.dumps(
            {
                "resourceType": "Observation",
                "id": "o2",
                "subject": {"reference": "Patient/p1"},
                "status": "final",
                "valueInteger": 7,
            }
        ),
        json.dumps(
            {
                "resourceType": "Observation",
                "id": "o3",
                "subject": {"reference": "Patient/p1"},
                "status": "final",
                "valueInteger": 20,
            }
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            con.execute("INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')", [patient])
            for idx, observation in enumerate(observations, start=1):
                con.execute(
                    "INSERT INTO resources VALUES (?, 'Observation', ?::JSON, 'p1')",
                    [f"o{idx}", observation],
                )
            assert con.execute(population_sql).fetchone() == ("p1", True, False)
    finally:
        py.close()
        cpp.close()


def test_cql_logical_singleton_query_return_is_patient_correlated() -> None:
    cql = """
library CQL04LogicalSingletonQueryCorrelation version '1.0.0'
using FHIR version '4.0.1'
context Patient

define QueryLetWhereReturn:
  singleton from ([Observation] O
    let High: O.value > 10,
        Final: O.status = 'final'
    where High implies Final
    return High xor Final)
"""
    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={"QueryLetWhereReturn": "QueryLetWhereReturn"},
    )

    resources = [
        (
            "p1",
            "Patient",
            json.dumps({"resourceType": "Patient", "id": "p1", "active": True}),
            "p1",
        ),
        (
            "o1",
            "Observation",
            json.dumps(
                {
                    "resourceType": "Observation",
                    "id": "o1",
                    "subject": {"reference": "Patient/p1"},
                    "status": "final",
                    "valueInteger": 15,
                }
            ),
            "p1",
        ),
        (
            "p2",
            "Patient",
            json.dumps({"resourceType": "Patient", "id": "p2", "active": False}),
            "p2",
        ),
        (
            "o2",
            "Observation",
            json.dumps(
                {
                    "resourceType": "Observation",
                    "id": "o2",
                    "subject": {"reference": "Patient/p2"},
                    "status": "preliminary",
                    "valueInteger": 5,
                }
            ),
            "p2",
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            con.execute(
                "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
            )
            for row in resources:
                con.execute(
                    "INSERT INTO resources VALUES (?, ?, ?::JSON, ?)",
                    list(row),
                )
            assert con.execute(population_sql).fetchall() == [
                ("p1", False),
                ("p2", False),
            ]
    finally:
        py.close()
        cpp.close()


def test_cql_logical_precedence_matches_spec_in_translated_execution() -> None:
    cql = """
library CQL04LogicalPrecedence version '1.0.0'

define AndBeforeImplies: false and false implies false
define OrBeforeImplies: false or true implies false
define XorOrLeftToRight: true xor true or true
define XorBeforeImplies: true xor true implies false
define ParenthesizedOverride: false and (false implies false)
define TemporalPrecisionThenAnd: Interval[@2026-01-01, @2026-01-02] ends during day of Interval[@2026-01-01, @2026-01-31] and true
"""
    translated = CQLToSQLTranslator().translate_library(parse_cql(cql))

    expected = {
        "AndBeforeImplies": True,
        "OrBeforeImplies": False,
        "XorOrLeftToRight": True,
        "XorBeforeImplies": True,
        "ParenthesizedOverride": False,
        "TemporalPrecisionThenAnd": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()


@pytest.mark.parametrize(
    "expression",
    [
        "1 and true",
        "'x' or false",
        "true xor 1",
        "1 implies false",
        "not 1",
        "{ true, false } and true",
        "Code { code: 'x', system: 'urn:test' } and true",
        "not Code { code: 'x', system: 'urn:test' }",
    ],
)
def test_cql_logical_operators_reject_static_non_boolean_operands(expression: str) -> None:
    cql = f"""
library CQL04LogicalInvalidOperand version '1.0.0'

define Result: {expression}
"""

    with pytest.raises(TranslationError, match="requires Boolean operands"):
        CQLToSQLTranslator().translate_library(parse_cql(cql))


@pytest.mark.parametrize(
    "expression",
    [
        "(1 as Any) and true",
        "(Code { code: 'x', system: 'urn:test' } as Any) or false",
        "(5 'mg' as System.Any) xor true",
        "not ({ true, false } as Any)",
        "(Tuple { a: true } as Any) implies true",
        "(Interval[1, 2] as System.Any) and true",
        "(convert 1 to Any) and true",
        "(convert true to String) and true",
        "ToString(true) and true",
        "(ToString(true) as Any) and true",
        "ToInteger('1') and true",
        "ToQuantity('5 \\'mg\\'') and true",
    ],
)
def test_cql_logical_operators_reject_non_boolean_as_any_operands(expression: str) -> None:
    cql = f"""
library CQL04LogicalInvalidAsAnyOperand version '1.0.0'

define Result: {expression}
"""

    with pytest.raises(TranslationError, match="requires Boolean operands"):
        CQLToSQLTranslator().translate_library(parse_cql(cql))


def test_cql_logical_operators_allow_boolean_as_any_operands() -> None:
    cql = """
library CQL04LogicalBooleanAsAnyOperand version '1.0.0'

define Result: (true as Any) and true
define ConvertedBoolean: (convert true to Boolean) and true
define ToBooleanResult: ToBoolean('yes') and true
define ConvertsResult: ConvertsToInteger('1') and true
"""

    translated = CQLToSQLTranslator().translate_library(parse_cql(cql))

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name in ("Result", "ConvertedBoolean", "ToBooleanResult", "ConvertsResult"):
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (True,)
            assert cpp.execute(sql).fetchone() == (True,)
    finally:
        py.close()
        cpp.close()


def test_cql_logical_operators_reject_non_boolean_definition_aliases() -> None:
    cql = """
library CQL04LogicalInvalidAlias version '1.0.0'

define NumericAlias: 1
define StringAlias: 'x'
define BadAnd: NumericAlias and true
define BadNot: not StringAlias
"""

    with pytest.raises(TranslationError, match="requires Boolean operands"):
        CQLToSQLTranslator().translate_library(parse_cql(cql))


def test_cql_logical_operators_reject_non_boolean_parameters() -> None:
    cql = """
library CQL04LogicalInvalidParameter version '1.0.0'

parameter P Integer default 1

define BadAnd: P and true
"""

    with pytest.raises(TranslationError, match="requires Boolean operands"):
        CQLToSQLTranslator().translate_library(parse_cql(cql))


@pytest.mark.parametrize(
    "expression",
    [
        # Binary arithmetic operands must be rejected per CQL §Logical.
        # Spec citation: CQL 1.5.3 Appendix B — And/Or/Xor/Implies/Not
        # require Boolean operands; binary arithmetic yields Integer/Long/
        # Decimal/Quantity per CQL §Types/§Arithmetic, never Boolean.
        "1 + 1 and true",
        "5 - 2 or false",
        "2 * 3 xor true",
        "10 div 2 implies true",
        "7 mod 3 and false",
        "2 ^ 3 or true",
        "5.5 + 1.5 and true",
        "(1 + 1) and true",
        "(1 + 2) and (3 * 4)",
        "not (1 + 1)",
        "not (5 mod 2)",
        "(5 > 3) and (1 + 1)",
        "0 - 1 or false",
    ],
)
def test_cql_logical_operators_reject_binary_arithmetic_operands(
    expression: str,
) -> None:
    cql = f"""
library CQL04LogicalInvalidArithmeticOperand version '1.0.0'

define Result: {expression}
"""

    with pytest.raises(TranslationError, match="requires Boolean operands"):
        CQLToSQLTranslator().translate_library(parse_cql(cql))


def test_cql_logical_operators_accept_comparison_and_logical_sub_expressions() -> (
    None
):
    """Positive controls: comparison/logical sub-expressions are Boolean and
    must still be accepted as logical operands (guards against an over-broad
    rejection of BinaryExpression operands)."""
    cql = """
library CQL04LogicalBooleanBinaryOperands version '1.0.0'

define A: (5 > 3) and (4 < 2)
define B: (5 > 3) or (4 < 2)
define C: (5 > 3) xor (4 < 2)
define D: (5 > 3) implies (4 < 2)
define E: not (5 > 3)
"""

    translated = CQLToSQLTranslator().translate_library(parse_cql(cql))

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        expected = {"A": False, "B": True, "C": True, "D": False, "E": False}
        for name, expected_value in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == (expected_value,), name
            assert cpp.execute(sql).fetchone() == (expected_value,), name
    finally:
        py.close()
        cpp.close()
