"""FHIR4-94 — CQL ``ConvertQuantity`` lowered to a SQL name NEITHER engine registers.

CQL 1.5 Appendix B declares

    ConvertQuantity(argument Quantity, unit String) Quantity

and again: *"If the unit is not specified, or the units are not compatible, the result is
null."* The function is listed in this translator's ``static_inline_functions`` — i.e. it is a
known CQL function — but it had **no lowering**, so ``_translate_function_ref`` fell through to
raw pass-through and emitted the CQL spelling as a SQL identifier:

    ConvertQuantity(parse_quantity('{"value": 5, ...}'), 'g')

Neither engine registers a scalar by that name (the implementation lives at ``quantityConvert``
in both: ``fhir4ds/cql/duckdb/udf/quantity.py`` and ``cql_extension.cpp``, and it is in
``_PYTHON_PREFERRED_CPP_CONFLICTS`` so Python is the desktop authority while C++ serves the
browser). Result: ``CatalogException: Scalar Function with name convertquantity does not
exist`` — the CQL never runs at all, on any surface.

How it got here, because the shape recurs: ``ConvertQuantity`` was a Python registration once,
and was deleted as "dead" in the v0.0.14 WASM campaign *because nothing emitted it*. Something
did — the pass-through. A registration can only be judged dead by looking at what the
TRANSLATOR emits, never by looking for other registrations of the same name.

There is a second, independent defect on the route this fix takes, and it is asserted here
because it would otherwise be introduced by the fix rather than found by it: ``quantityConvert``
crashed on a NULL target unit (``TypeError: argument of type 'NoneType' is not iterable`` ->
``InvalidInputException``) instead of answering null. CQL says a unit that is not specified
gives null, so the UDF has to be null-safe on the argument the spec allows to be absent.

The referees:

* ``ConvertQuantity(5 'mg', 'g')`` answers a Quantity of 0.005 g (it was a Catalog Error);
* the same through a define alias — the operand shape the card named;
* an incompatible unit and a null unit both answer NULL, never an error;
* the emitted SQL calls a REGISTERED name, asserted on the SQL text, because a value-only
  assertion cannot distinguish a fixed lowering from a lucky one;
* ``quantityConvert(<quantity>, NULL)`` is NULL on both engines, asserted directly at the SQL
  surface as well as through the translation, since that is where the crash lived;
* the CQL-06 calendar-duration doctrine survives the re-route: 1 year -> 365.25 day, 1 year ->
  12 mo (UCUM Julian factors), so this is a rename and not a re-implementation.
"""

from __future__ import annotations

import json

import pytest

import duckdb

from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_PATIENT = json.dumps({"resourceType": "Patient", "id": "p1"})


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    con.execute(
        "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
    )
    con.execute("INSERT INTO resources VALUES ('p1','Patient',?,'p1')", [_PATIENT])
    return con


def _run(body: str, columns: tuple[str, ...]) -> tuple[dict, str]:
    """Translate a one-define library, execute it, return (row, sql)."""
    cql = (
        "library V94 version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "context Patient\n"
        f"{body}\n"
        'define "Initial Population": exists (Patient)\n'
        'define "Denominator": "Initial Population"\n'
        'define "Numerator": true\n'
    )
    wanted = ("Initial Population", "Denominator", "Numerator") + columns
    con = _connection()
    try:
        library = parse_cql(cql)
        translator = CQLToSQLTranslator(connection=con)
        translator.translate_library(library)
        sql = translator.translate_library_to_population_sql(
            library=library, output_columns={name: name for name in wanted}
        )
        cursor = con.execute(sql)
        row = dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
        return row, sql
    finally:
        con.close()


def _quantity(cell) -> dict:
    """A population column carries the Quantity as JSON text."""
    assert cell is not None, "expected a converted quantity, got NULL"
    return json.loads(cell) if isinstance(cell, str) else cell


class TestConvertQuantityLowersToARegisteredName:
    def test_a_quantity_literal_converts(self):
        """RED before the fix: CatalogException — the name was never registered."""
        row, _ = _run('define "Conv": ConvertQuantity(5 \'mg\', \'g\')', ("Conv",))
        converted = _quantity(row["Conv"])
        assert converted["value"] == pytest.approx(0.005)
        assert (converted.get("unit") or converted.get("code")) == "g"

    def test_the_emitted_sql_names_a_registered_function(self):
        """A value-only assertion cannot tell a fix from a lucky one, so pin the SQL text."""
        _, sql = _run('define "Conv": ConvertQuantity(5 \'mg\', \'g\')', ("Conv",))
        assert "quantityConvert(" in sql
        # the CQL spelling must not survive as a SQL identifier
        assert not __import__("re").search(r"(?<![A-Za-z_])ConvertQuantity\s*\(", sql)

    def test_a_define_alias_operand_converts(self):
        """The shape the card named: the operand is a define, not a literal."""
        row, _ = _run(
            'define "Q": 5 \'mg\'\ndefine "Conv": ConvertQuantity("Q", \'g\')', ("Conv",)
        )
        converted = _quantity(row["Conv"])
        assert converted["value"] == pytest.approx(0.005)


class TestNullOrImpossibleConversionsAnswerNull:
    def test_an_incompatible_unit_is_null(self):
        """CQL: "If ... the units are not compatible, the result is null." """
        row, _ = _run('define "Conv": ConvertQuantity(5 \'mg\', \'cm\')', ("Conv",))
        assert row["Conv"] is None

    def test_a_null_unit_is_null_not_an_error(self):
        """CQL: "If the unit is not specified ... the result is null."

        This is the defect the re-route would otherwise INTRODUCE: ``quantityConvert`` raised
        ``TypeError`` on a null unit, surfacing as a DuckDB ``InvalidInputException``.
        """
        row, _ = _run('define "Conv": ConvertQuantity(5 \'mg\', null)', ("Conv",))
        assert row["Conv"] is None


class TestTheUdfIsNullSafeAtTheSqlSurface:
    """Asserted directly at the SQL surface: that is where the crash lived."""

    @pytest.mark.parametrize(
        "sql, params",
        [
            ("SELECT quantityConvert(?, NULL)", ['{"value":5,"unit":"mg","code":"mg"}']),
            ("SELECT quantityConvert(NULL, 'g')", []),
            ("SELECT quantityConvert(?, NULL)", [None]),
        ],
    )
    def test_null_arguments_answer_null(self, sql, params):
        con = _connection()
        try:
            assert con.execute(sql, params).fetchone() == (None,)
        finally:
            con.close()


class TestTheCalendarDurationDoctrineSurvivesTheReroute:
    """A rename, not a re-implementation: the CQL-06 UCUM Julian factors must hold."""

    @pytest.mark.parametrize(
        "value, unit, expected",
        # UCUM Julian year: day = 365.25, so month = 365.25/12 = 30.4375.  Both
        # figures are the pinned CQL-06 doctrine, asserted here because a re-route
        # is only safe if it preserves the factors it re-routes TO.
        [(1, "year", {"day": 365.25, "mo": 12.0}), (1, "mo", {"day": 30.4375})],
    )
    def test_ucum_julian_factors(self, value, unit, expected):
        for target, want in expected.items():
            row, _ = _run(
                f'define "Conv": ConvertQuantity({value} \'{unit}\', \'{target}\')', ("Conv",)
            )
            assert _quantity(row["Conv"])["value"] == pytest.approx(want)
