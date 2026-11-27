"""FHIR4-76 — a fold's accumulator takes the type of its starting value.

A CQL ``aggregate`` with a starting value declares the accumulator's type through that value
(CQL 1.5 section 19.27: the body evaluates to the accumulator's type). Two lowering defects
ignored that:

* the multi-source fold cast EVERY starting value to BIGINT, so ``starting 0.5`` with ``R + 1``
  over six rows answered 7 instead of 6.5, a String/Date/Boolean start failed to bind, and an
  Integer overflow raised instead of answering null;
* the single-source fold carried the accumulator inside the element list (``list_reduce`` over
  ``list_prepend(start, elements)``), so every step was rounded back to the element type:
  ``starting 0: R + X * 0.5`` over ``{1, 2, 3}`` answered 4 instead of 3.0, a Boolean start
  came back as the integer 1, and a Date start did not bind.

The accumulator now lives in the working table of the fold and is cast to its CQL type; an
integral start whose body is statically Long or Decimal is widened to the body's type.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from decimal import Decimal

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_HALF = "Decimal('0.5')"
_LONG_MAX = "9223372036854775807L"

_LIBRARY = """library FHIR4_76 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
define "__DEFINITION__":
  __EXPRESSION__
"""

_DECIMAL = Decimal("0.5")

#: (id, expression, expected, expected SQL type). Values are what one patient (p1) answers.
_CASES = [
    # ── Decimal starting values, both source arities ────────────────────────────────────────
    ("SsDecimalLiteral", "({1, 2, 3}) X aggregate R starting 0.5: R + X", Decimal("6.5")),
    ("SsDecimalExpression", "({1, 2, 3}) X aggregate R starting 1 / 2: R + X", Decimal("6.5")),
    ("SsDecimalElements", "({1.5, 2.5}) X aggregate R starting 0.0: R + X", Decimal("4.0")),
    # Each step keeps its scale: 0 + 0.125 + 0.125 + 0.125.
    ("SsDecimalNoPerStepRounding", "({1, 1, 1}) X aggregate R starting 0.0: R + X * 0.125", Decimal("0.375")),
    ("MsDecimalLiteral", "from ({1, 2, 3}) X, ({10, 20}) Y aggregate R starting 0.5: R + 1", Decimal("6.5")),
    ("MsDecimalExpression", "from ({1, 2, 3}) X, ({10, 20}) Y aggregate R starting ToDecimal('0.5'): R + 1", Decimal("6.5")),
    ("MsDecimalLiteralScale", "from ({1, 1, 1}) X, ({1}) Y aggregate R starting 0.0: R + 0.125", Decimal("0.375")),
    # ── An integral start with a Decimal body is widened, not truncated ─────────────────────
    ("SsIntStartDecimalBody", "({1, 2, 3}) X aggregate R starting 0: R + X * 0.5", Decimal("3.0")),
    ("MsIntStartDecimalBody", "from ({1, 2, 3}) X, ({10, 20}) Y aggregate R starting 0: R + 0.5", Decimal("3.0")),
    # ── Integer and Long starts keep their extent: overflow is null, never an error ──────────
    ("SsIntegerOverflowIsNull", "({1}) X aggregate R starting 2147483647: R + X", None),
    ("SsLongOverflowIsNull", f"({{1}}) X aggregate R starting {_LONG_MAX}: R + X", None),
    ("MsIntegerOverflowIsNull", "from ({1}) X, ({1}) Y aggregate R starting 2147483647: R + X + Y", None),
    ("MsLongOverflowIsNull", f"from ({{1}}) X, ({{1}}) Y aggregate R starting {_LONG_MAX}: R + X + Y", None),
    ("MsIntegerUnchanged", "from ({1, 2, 3}) X, ({10, 20}) Y aggregate R starting 1: R * X", 36),
    # ── Non-numeric starting values ─────────────────────────────────────────────────────────
    ("SsString", "({'a', 'b', 'c'}) X aggregate R starting '': R & X", "abc"),
    ("SsBoolean", "({1, 2, 3}) X aggregate R starting true: R and X > 0", True),
    ("SsDate", "({1}) X aggregate R starting @2024-01-01: R + 1 day", "2024-01-02"),
    ("MsDate", "from ({1}) X aggregate R starting @2024-01-01: R + 1 day", "2024-01-02"),
    ("MsBoolean", "from ({1, 2, 3}) X, ({1}) Y aggregate R starting true: R and X > 0", True),
    # A null start stays null: null propagates through every step.
    ("SsNullStart", "({1, 2, 3}) X aggregate R starting (null as Integer): R + X", None),
    ("MsNullStart", "from ({1}) X, ({1}) Y aggregate R starting (null as Integer): R + X + Y", None),
    # ── A fold WITHOUT a starting value is unchanged ────────────────────────────────────────
    ("SsNoStart", "({1, 2, 3}) X aggregate R: Coalesce(R, 0) + X", 6),
    ("MsNoStart", "from ({1}) X, ({2}) Y, ({3}) Z aggregate R: Coalesce(R, 0) + X + Y + Z", 6),
]

#: SQL type of the result column, by case; Decimal cases share one entry.
_TYPES = {
    "Decimal": "DECIMAL(38,8)",
    "Boolean": "BOOLEAN",
}

_STRING_MULTI = "from ({'b', 'a'}) X, ({1}) Y aggregate R starting '': R & X"

_FOLD = re.compile(r"\(WITH RECURSIVE .*? SELECT __acc FROM __fold ORDER BY __rn DESC LIMIT 1\)", re.S)


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines():
    """Python supplements and the C++-only engine: the lowering must hold on both."""
    for build in (_python_connection, no_python_connection):
        with build() as con:
            yield con


def _library(definition: str, expression: str) -> str:
    return _LIBRARY.replace("__DEFINITION__", definition).replace("__EXPRESSION__", expression)


def _translate(con, library_text: str, definition: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(library_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    columns = {
        "Initial Population": "Initial Population",
        "Denominator": "Denominator",
        "Numerator": "Numerator",
        definition: definition,
    }
    return translator.translate_library_to_population_sql(library=library, output_columns=columns)


def _load_patient(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    con.execute(
        "INSERT INTO resources VALUES ('p1','Patient',?::JSON,'p1')",
        [json.dumps({"resourceType": "Patient", "id": "p1"})],
    )


def _answer(con, definition: str, expression: str):
    """(value, SQL type) the definition answers for p1 through the population SQL."""
    sql = _translate(con, _library(definition, expression), definition)
    _load_patient(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    assert len(rows) == 1 and str(rows[0][names.index("patient_id")]) == "p1", rows
    typed = con.execute(
        f"SELECT ({definition}), typeof(({definition})) FROM ({sql}) AS _pop"
    ).fetchone()
    return typed[0], typed[1]


def _kind(expected) -> str:
    if isinstance(expected, Decimal):
        return "Decimal"
    if isinstance(expected, bool):
        return "Boolean"
    return ""


def _same(got, expected) -> bool:
    if isinstance(expected, Decimal):
        return isinstance(got, Decimal) and got == expected
    if isinstance(expected, bool):
        return isinstance(got, bool) and got is expected
    return got == expected


@pytest.mark.parametrize(("definition", "expression", "expected"), _CASES, ids=[c[0] for c in _CASES])
def test_the_accumulator_takes_the_type_of_its_starting_value(definition, expression, expected):
    for con in _engines():
        value, sql_type = _answer(con, definition, expression)
        assert _same(value, expected), f"answered {value!r} ({sql_type})"
        kind = _kind(expected)
        if kind:
            assert sql_type == _TYPES[kind], f"SQL type {sql_type}"


def test_a_string_start_folds_every_pair():
    """The cross-join order of several sources is not specified; every pair is folded once."""
    for con in _engines():
        value, _ = _answer(con, "MsString", _STRING_MULTI)
        assert value in ("ab", "ba"), value


@pytest.mark.parametrize(
    ("expression", "anchor"),
    [
        # An Integer start is INT32, so an overflow reaches the body's TRY guard.
        ("({1}) X aggregate R starting 2147483647: R + X", "CAST(2147483647 AS INTEGER) AS __acc"),
        (f"({{1}}) X aggregate R starting {_LONG_MAX}: R + X", "CAST(9223372036854775807 AS BIGINT) AS __acc"),
        ("({1, 2, 3}) X aggregate R starting 0.5: R + X", "CAST(0.5 AS DECIMAL(38,8)) AS __acc"),
        ("({'a'}) X aggregate R starting '': R & X", "CAST('' AS VARCHAR) AS __acc"),
        ("({1}) X aggregate R starting true: R and true", "CAST(TRUE AS BOOLEAN) AS __acc"),
        ("from ({1}) X, ({1}) Y aggregate R starting 0.5: R + 1", "CAST(0.5 AS DECIMAL(38,8)) AS __acc"),
        ("from ({1}) X, ({1}) Y aggregate R starting 0: R + X + Y", "CAST(0 AS INTEGER) AS __acc"),
        # Widened to the body's type.
        ("({1}) X aggregate R starting 0: R + X * 0.5", "CAST(0 AS DECIMAL(38,8)) AS __acc"),
    ],
)
def test_the_anchor_is_cast_to_the_starting_values_type(expression, anchor):
    from fhir4ds.cql import translate_cql

    for con in _engines():
        sql = translate_cql(f'library T version \'1.0\'\ndefine "TestResult": {expression}', connection=con)[
            "TestResult"
        ].to_sql()
        folds = _FOLD.findall(sql)
        assert len(folds) == 1, sql.count("WITH RECURSIVE")
        assert anchor in folds[0], folds[0][:300]
        # A starting value never travels inside the element list.
        assert "list_reduce" not in sql, sql[:300]


def test_a_date_literal_before_the_clause_colon_lexes():
    """``starting @2024-01-01: …`` is valid CQL; greedy lexing swallowed the colon into the
    literal and raised an invalid-literal error."""
    from fhir4ds.cql.errors import LexerError
    from fhir4ds.cql.parser import parse_cql

    for literal in ("@2024-01-01", "@2024-01-01T10:30", "@2024-01-01T10:30+05:30", "@T10:30"):
        library = parse_cql(f"library T version '1.0'\ndefine \"D\": ({{1}}) X aggregate R starting {literal}: R")
        assert [statement.name for statement in library.statements] == ["D"]
    # A colon still belongs to the literal between two digits.
    assert parse_cql("library T version '1.0'\ndefine \"D\": @T10:30") is not None
    # …and the literal itself is still validated.
    with pytest.raises(LexerError):
        parse_cql("library T version '1.0'\ndefine \"D\": @2024-13-01")
