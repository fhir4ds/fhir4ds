"""FHIR4-83 — a fold whose starting value is a Quantity accumulates Quantities.

CQL 1.5 §19.27 (Aggregate): the accumulator takes the type of the starting value. The
arithmetic dispatch could not see that type for a fold accumulator (the alias was bound to
``__fold.__acc`` with no CQL type), so a Quantity start reached the "the other operand is a
Quantity, so this operand must be a date" branch and every step lowered to
``dateAddQuantity``. ``0 'mg'`` is not a date, so the step answered NULL and the whole fold
answered NULL — indistinguishable, in a population, from "no data".

The accumulator and each fold element alias now carry their statically known CQL type, so
``aggregate R starting 0 'mg': R + 1 'mg'`` over three elements answers ``3 'mg'``
(unit-aware: ``1 'g' + 2 'g'`` over a Quantity source answers ``3000 'mg'``), while
incompatible units follow CQL §Add and answer NULL.

Binary64 note: quantities are transported as float JSON, so three ``0.1 'mg'`` steps carry
the usual rounding (``0.30000000000000004``). That is the engine-wide Quantity transport
doctrine and is NOT specific to the fold — plain `0.0 'mg' + 0.1 'mg' + 0.1 'mg' + 0.1 'mg'`
answers the same value and the same ``= 0.3 'mg'`` false.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_LIBRARY = """library FHIR4_83 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "Initial Population"
define "__DEFINITION__":
  __EXPRESSION__
"""


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


def _library(expression: str) -> str:
    return _LIBRARY.replace("__DEFINITION__", "F").replace("__EXPRESSION__", expression)


def _translate(con, expression: str) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_library(expression))
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *a: None)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library,
        output_columns={
            "Initial Population": "Initial Population",
            "Denominator": "Denominator",
            "Numerator": "Numerator",
            "F": "F",
        },
    )


def _load_patient(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    con.execute(
        "INSERT INTO resources VALUES ('p1','Patient',?::JSON,'p1')",
        [json.dumps({"resourceType": "Patient", "id": "p1"})],
    )


def _fold_sql(con, expression: str) -> str:
    return _translate(con, expression)


def _answer(con, expression: str):
    """(value, SQL type) the definition answers for p1 through the population SQL."""
    sql = _translate(con, expression)
    _load_patient(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    assert len(rows) == 1 and str(rows[0][names.index("patient_id")]) == "p1", rows
    return con.execute(
        f"SELECT (F), typeof((F)) FROM ({sql}) AS _pop"
    ).fetchone()



def test_quantity_fold_accumulates_quantities_value_not_binding() -> None:
    """The card's referee: three elements, ``0 'mg'`` start, ``+ 1 'mg'`` body."""
    for con in _engines():
        value, sql_type = _answer(
            con, "({1, 2, 3}) X aggregate R starting 0 'mg': R + 1 'mg'"
        )
        assert value is not None, "a Quantity fold answered NULL instead of 3 'mg'"
        quantity = json.loads(value)
        assert quantity["value"] == 3.0
        assert quantity["unit"] == "mg"
        assert quantity["code"] == "mg"
        assert sql_type == "VARCHAR"


def test_quantity_fold_result_is_a_quantity_value_comparable_to_a_literal() -> None:
    """The answer is a Quantity VALUE: it compares unit-aware to ``3 'mg'``."""
    for con in _engines():
        value, _ = _answer(con, "({1, 2, 3}) X aggregate R starting 0 'mg': R + 1 'mg'")
        con.execute("CREATE OR REPLACE TABLE one_quantity (q JSON)")
        con.execute("INSERT INTO one_quantity VALUES (?::JSON)", [value])
        equal_to_literal = con.execute(
            "SELECT quantityCompare(q, parse_quantity('"
            '{"value": 3, "unit": "mg", "system": "http://unitsofmeasure.org"}'
            "'), '==') FROM one_quantity"
        ).fetchone()[0]
        assert equal_to_literal is True


def test_quantity_fold_over_quantity_elements_is_unit_aware() -> None:
    """A Quantity element source is added unit-aware: 1 g + 2 g = 3000 mg."""
    for con in _engines():
        value, _ = _answer(
            con, "({1 'g', 2 'g'}) X aggregate R starting 0 'mg': R + X"
        )
        assert value is not None, "a Quantity-element fold answered NULL"
        quantity = json.loads(value)
        assert quantity["value"] == 3000.0
        assert quantity["unit"] == "mg"


def test_quantity_fold_empty_source_answers_the_starting_value() -> None:
    for con in _engines():
        value, _ = _answer(con, "({}) X aggregate R starting 0 'mg': R + 1 'mg'")
        quantity = json.loads(value)
        assert quantity["value"] == 0.0
        assert quantity["unit"] == "mg"


def test_quantity_fold_multi_source() -> None:
    for con in _engines():
        value, _ = _answer(
            con,
            "from ({1, 2}) X, ({10}) Y aggregate R starting 0 'mg': R + 1 'mg'",
        )
        quantity = json.loads(value)
        assert quantity["value"] == 2.0
        assert quantity["unit"] == "mg"


def test_quantity_fold_incompatible_units_follows_cql() -> None:
    """CQL §Add: incompatible units cannot be summed — the step is null, never a value."""
    for con in _engines():
        value, _ = _answer(
            con, "({1, 2, 3}) X aggregate R starting 0 'mg': R + 1 'cm'"
        )
        assert value is None


def test_date_fold_still_works() -> None:
    """The regression the Quantity path must not break."""
    for con in _engines():
        value, _ = _answer(con, "({1}) X aggregate R starting @2024-01-01: R + 1 day")
        assert value == "2024-01-02"


def test_quantity_fold_body_does_not_lower_to_date_arithmetic() -> None:
    """SQL-shape pin: the fold step is Quantity addition, not ``dateAddQuantity``."""
    for con in _engines():
        sql = _fold_sql(con, "({1, 2, 3}) X aggregate R starting 0 'mg': R + 1 'mg'")
        assert "dateAddQuantity" not in sql
        assert "quantity_add" in sql


def test_other_accumulator_types_unchanged() -> None:
    """The FHIR4-76 anchor typing still applies to the non-Quantity members."""
    for con in _engines():
        sql = _fold_sql(con, "({1, 2, 3}) X aggregate R starting 0.5: R + X")
        assert "CAST(0.5 AS DECIMAL(38,8)) AS __acc" in sql
        value, _ = _answer(con, "({1, 2, 3}) X aggregate R starting 0.5: R + X")
        assert value == pytest.approx(6.5)
        sql = _fold_sql(con, "({'a', 'b'}) X aggregate R starting '': R & X")
        assert "CAST('' AS VARCHAR) AS __acc" in sql
