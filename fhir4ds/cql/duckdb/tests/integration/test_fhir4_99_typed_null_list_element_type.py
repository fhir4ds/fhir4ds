"""FHIR4-99 — a ``(null as List<T>)`` define keeps T's ELEMENT type in its column.

A typed null list stores the whole element list in the definition's value column. FHIR4-75
made the META right (``List<Integer>``, ``stores_list_value``, ``PATIENT_SCALAR``), but the
column itself was hard-coded to ``VARCHAR[]`` no matter what ``T`` said:

    define "L": (null as List<Integer>)
    "L" AS MATERIALIZED (SELECT _pt.patient_id, CAST(NULL AS VARCHAR[]) AS value ...)

so the declare-type and the physical-type disagreed. Every consumer that took one element and
did arithmetic with it was then adding VARCHAR to a number:

    "L"[0] + 1              -> Binder Error: '+(VARCHAR, INTEGER_LITERAL)'
    ("L") N return N + 1    -> the same

There is no data to transport in a statically null list, so the only thing the column type can
carry is the element type the cast just declared — and it should carry it. Element types this
translator transports as JSON TEXT (``Quantity``, ``Interval<T>``, ``Concept``, ``Any``, a
tuple) deliberately keep ``VARCHAR[]``: that is the representation their consumers already
decode, and giving them a native type would change the transport rather than the type. Those
cases are pinned here too, so "make it typed" cannot quietly become "make everything typed".

The shape is asserted, not only the value: ``CAST(NULL AS VARCHAR[])`` answers NULL for
``"L"[0]`` as well, so a value-only assertion passes on the broken form.
"""

from __future__ import annotations

import json

import pytest

import duckdb

from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

_PATIENT = json.dumps({"resourceType": "Patient", "id": "p1"})


def _translate(body: str) -> tuple[duckdb.DuckDBPyConnection, object, object]:
    cql = (
        "library V99 version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "context Patient\n"
        f"{body}\n"
        'define "Initial Population": exists (Patient)\n'
    )
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    con.execute(
        "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
    )
    con.execute("INSERT INTO resources VALUES ('p1','Patient',?,'p1')", [_PATIENT])
    library = parse_cql(cql)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return con, library, translator


def _run(body: str, columns: tuple[str, ...]) -> dict:
    con, library, translator = _translate(body)
    try:
        wanted = ("Initial Population",) + columns
        sql = translator.translate_library_to_population_sql(
            library=library, output_columns={name: name for name in wanted}
        )
        cursor = con.execute(sql)
        return dict(zip([d[0] for d in cursor.description], cursor.fetchone()))
    finally:
        con.close()


def _l_cte_cast(body: str) -> str:
    """The array type cast onto the definition's null list, taken from the emitted SQL.

    A CTE is not visible in the final statement's catalog, so the lowering is read directly:
    the shape IS the claim this card makes, and a value-only assertion cannot see it (a
    ``VARCHAR[]`` of NULLs answers NULL for every element either way).
    """
    con, library, translator = _translate(body)
    try:
        sql = translator.translate_library_to_population_sql(
            library=library, output_columns={"Initial Population": "Initial Population"}
        )
    finally:
        con.close()
    import re

    match = re.search(r"CAST\(NULL AS ([A-Z]+(?:\([0-9,]+\))?\[\])", sql)
    assert match, f"no CAST(NULL AS ...) in the emitted SQL:\n{sql[:400]}"
    return match.group(1)


class TestArithmeticOverTypedNullListElementsBinds:
    def test_an_indexed_element_takes_part_in_arithmetic(self):
        """RED before the fix: Binder Error '+(VARCHAR, INTEGER_LITERAL)'."""
        row = _run(
            'define "L": (null as List<Integer>)\ndefine "X": "L"[0] + 1', ("X",)
        )
        # the list is null, so the element is null and the sum is null — but it BINDS
        assert row["X"] is None

    def test_an_arithmetic_body_over_the_list_binds(self):
        """The card's second shape: a query whose body does arithmetic.

        A query over a NULL list iterates zero rows, so the answer is the empty list — the
        point is that it BINDS, where before it was a Binder Error.
        """
        row = _run(
            'define "L": (null as List<Integer>)\ndefine "X": ("L") N return N + 1', ("X",)
        )
        assert row["X"] == []

    def test_decimal_elements_stay_exact(self):
        row = _run(
            'define "L": (null as List<Decimal>)\ndefine "X": Sum("L") + 0.5', ("X",)
        )
        assert row["X"] is None


class TestTheColumnCarriesTheDeclaredElementType:
    @pytest.mark.parametrize(
        "element, expected",
        [("Integer", "INTEGER[]"), ("Long", "BIGINT[]"), ("Boolean", "BOOLEAN[]"),
         ("Decimal", "DECIMAL(38,8)[]")],
    )
    def test_scalar_element_types_are_typed(self, element, expected):
        assert _l_cte_cast(f'define "L": (null as List<{element}>)') == expected

    @pytest.mark.parametrize(
        "element",
        # the JSON-text transport family: their consumers already decode text, and a native
        # type here would change the TRANSPORT rather than the type
        ["String", "Quantity", "Date", "Interval<Date>", "Any"],
    )
    def test_json_text_element_types_keep_varchar_arrays(self, element):
        assert _l_cte_cast(f'define "L": (null as List<{element}>)') == "VARCHAR[]"


class TestTheStoredListSemanticsAreUnchanged:
    """FHIR4-75's half of this must keep holding: it is still a stored NULL list."""

    def test_count_is_zero_and_aggregates_are_null(self):
        row = _run(
            'define "CountNull": Count(null as List<Integer>)\n'
            'define "SumNull": Sum(null as List<Integer>)\n'
            'define "AvgNull": Avg(null as List<Integer>)',
            ("CountNull", "SumNull", "AvgNull"),
        )
        assert row["CountNull"] == 0
        assert row["SumNull"] is None
        assert row["AvgNull"] is None
