"""FHIR4-108 — aggregates over a Quantity list stay unit-aware and answer from the quantities.

Three defects made `Sum`/`Avg`/`Min`/`Max`/`Count` answer nothing — or the wrong thing — over a
Quantity list:

- A list stored under a define name (`define "Q": {} as List<Quantity>`, a typed null, a
  literal list) left the stored-list aggregate path because of its element type. The translator
  then fell back to a SQL ROW aggregate over the define's demoted scalar —
  `SUM(TRY_CAST((SELECT sub.value FROM "Q" ...) AS DOUBLE))` — which is a Binder Error when it
  sits next to the patient column, and would add the JSON TEXT of one quantity even if it bound.
  The stored list is now aggregated from its CTE value column with the same unit-aware helpers
  the literal spelling already used.

- The element type was matched by its exact spelling. `List<FHIR.Quantity>` is the same element
  type as `List<Quantity>`, but it was not recognised: a stored list took the plain `list_*`
  lowering, which orders the Quantity JSON as TEXT, and an element-rows list gave `Sum` the same
  Binder Error. One predicate now accepts both spellings.

- The element-rows spelling (`[Observation] O return O.valueQuantity as Quantity`) answered
  `Count` 0 and every other aggregate null WITHOUT an error. The retrieve precomputed
  `valueQuantity` as its NUMBER projection (`fhirpath_number`), because the element's FHIR type
  is Quantity; that function answers NULL for a Quantity object, and the column was registered
  under the property's own path, so `O.valueQuantity` was NULL for every row. The column now
  holds the Quantity itself (its JSON text), as `period`/`effective`/`performed` already did.

Values on both engines, plus the SQL shapes the defects produced.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_SYSTEM = "http://unitsofmeasure.org"

_OBSERVATIONS = (
    ("o1", {"value": 3.5, "unit": "mg", "code": "mg", "system": _SYSTEM}),
    ("o2", {"value": 1.5, "unit": "g", "code": "g", "system": _SYSTEM}),
)

_SOURCES = (
    "QEmpty",  # {} as List<Quantity>
    "QNull",  # null as List<Quantity>
    "QList",  # {1 'mg', 2 'mg', 1500 'mg'}
    "QListMixed",  # {1 'g', 500 'mg'}
    "QRows",  # [Observation] O return O.valueQuantity as Quantity (element rows)
    "QFNull",  # null as List<FHIR.Quantity> (the other spelling of the same type)
    "QFRows",  # [Observation] O return O.valueQuantity as FHIR.Quantity
)
_AGGREGATES = ("Count", "Sum", "Min", "Max", "Avg")

LIBRARY = """library QuantityListAggregates version '1.0'
using FHIR version '4.0.1'
context Patient

define "QEmpty": {} as List<Quantity>
define "QNull": null as List<Quantity>
define "QList": {1.0 'mg', 2.0 'mg', 1500.0 'mg'}
define "QListMixed": {1.0 'g', 500.0 'mg'}
define "QRows": [Observation] O return O.valueQuantity as Quantity
define "QFNull": null as List<FHIR.Quantity>
define "QFRows": [Observation] O return O.valueQuantity as FHIR.Quantity
""" + "\n".join(
    f'define "{aggregate}{source}": {aggregate}("{source}")'
    for source in _SOURCES
    for aggregate in _AGGREGATES
)

COLUMNS = {
    f"{aggregate}{source}": f"{aggregate}{source}"
    for source in _SOURCES
    for aggregate in _AGGREGATES
}


def _to_mg(quantity: object) -> object:
    """A Quantity cell as ``(milligrams, unit)``; anything else unchanged."""
    if not isinstance(quantity, str) or not quantity.startswith("{"):
        return quantity
    value = json.loads(quantity)
    magnitude, unit = float(value["value"]), value["unit"]
    return (magnitude * 1000.0, "mg") if unit == "g" else (magnitude, unit)


_EMPTY = {"p1": None, "p2": None}
_COUNT_EMPTY = {"p1": 0, "p2": 0}

#: The observations above: 3.5 mg and 1.5 g, so the maximum is 1.5 g = 1500 mg.
_FROM_OBSERVATIONS = {
    "Count": {"p1": 2, "p2": 0},
    "Sum": {"p1": (1503.5, "mg"), "p2": None},
    "Min": {"p1": (3.5, "mg"), "p2": None},
    "Max": {"p1": (1500.0, "mg"), "p2": None},
    "Avg": {"p1": (751.75, "mg"), "p2": None},
}

#: column -> patient -> answer (quantities already expressed in milligrams)
EXPECTED: dict[str, dict[str, object]] = {
    # Nothing stored: Count is 0 and every other aggregate is null, in either type spelling.
    **{f"{aggregate}{source}": (_COUNT_EMPTY if aggregate == "Count" else _EMPTY)
       for source in ("QEmpty", "QNull", "QFNull") for aggregate in _AGGREGATES},
    # One unit throughout.
    "CountQList": {"p1": 3, "p2": 3},
    "SumQList": {"p1": (1503.0, "mg"), "p2": (1503.0, "mg")},
    "MinQList": {"p1": (1.0, "mg"), "p2": (1.0, "mg")},
    "MaxQList": {"p1": (1500.0, "mg"), "p2": (1500.0, "mg")},
    "AvgQList": {"p1": (501.0, "mg"), "p2": (501.0, "mg")},
    # Grams and milligrams in one list: the comparison and the sum convert.
    "CountQListMixed": {"p1": 2, "p2": 2},
    "SumQListMixed": {"p1": (1500.0, "mg"), "p2": (1500.0, "mg")},
    "MinQListMixed": {"p1": (500.0, "mg"), "p2": (500.0, "mg")},
    "MaxQListMixed": {"p1": (1000.0, "mg"), "p2": (1000.0, "mg")},
    "AvgQListMixed": {"p1": (750.0, "mg"), "p2": (750.0, "mg")},
    # The element-rows spelling answers the same, in either type spelling.
    **{f"{aggregate}{source}": answer
       for source in ("QRows", "QFRows")
       for aggregate, answer in _FROM_OBSERVATIONS.items()},
}
assert set(EXPECTED) == set(COLUMNS), "every projected define has an expected answer"


@contextmanager
def _python_connection():
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    try:
        yield con
    finally:
        con.close()


def _engines() -> Iterator[tuple[str, object]]:
    """The Python-supplement engine and the C++-only engine: the lowering must hold on both."""
    for label, build in (("python", _python_connection), ("c++", no_python_connection)):
        with build() as con:
            con.execute(
                "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                "resource JSON, patient_ref VARCHAR)"
            )
            for patient_id in ("p1", "p2"):
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [patient_id, "Patient", json.dumps({"resourceType": "Patient", "id": patient_id}),
                     patient_id],
                )
            for observation_id, quantity in _OBSERVATIONS:
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [observation_id, "Observation",
                     json.dumps({"resourceType": "Observation", "id": observation_id,
                                 "status": "final", "subject": {"reference": "Patient/p1"},
                                 "valueQuantity": quantity}), "p1"],
                )
            yield label, con


def _population(con) -> tuple[dict[str, dict[str, object]], str]:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(LIBRARY)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library, output_columns=COLUMNS
    )
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    rows = cursor.fetchall()
    return {
        column: {str(row[0]): _to_mg(row[names.index(column)]) for row in rows}
        for column in COLUMNS
    }, sql


@pytest.mark.parametrize("column", sorted(EXPECTED))
def test_an_aggregate_over_a_quantity_list_answers_by_value(column: str) -> None:
    for label, con in _engines():
        answers, _ = _population(con)
        assert answers[column] == EXPECTED[column], f"[{label}] {column}: {answers[column]}"


def test_a_stored_quantity_list_is_never_a_row_aggregate() -> None:
    """No SQL row aggregate over the define's demoted scalar (the Binder Error shape)."""
    for label, con in _engines():
        _, sql = _population(con)
        for source in ("QEmpty", "QNull", "QFNull"):
            for shape in (f'SUM(TRY_CAST((SELECT sub.value FROM "{source}"',
                          f'LEAST((SELECT sub.value FROM "{source}"',
                          f'GREATEST((SELECT sub.value FROM "{source}"'):
                assert shape not in sql, f"[{label}] {shape!r} is a row aggregate over a scalar"


def test_a_quantity_list_is_never_aggregated_as_text() -> None:
    """No plain ``list_*`` aggregate: every source in the library is a list of Quantities."""
    for label, con in _engines():
        _, sql = _population(con)
        for shape in ("list_min(", "list_max(", "list_sum(", "list_avg("):
            assert shape not in sql, f"[{label}] {shape[:-1]} orders Quantity JSON as text"
        assert "quantityAdd(" in sql and "quantityCompare(" in sql, (
            f"[{label}] the aggregates are not the unit-aware ones"
        )


def test_a_quantity_element_is_precomputed_as_the_quantity_itself() -> None:
    """The retrieve's ``valueQuantity`` column is the Quantity JSON, never its number projection.

    ``fhirpath_number`` answers NULL for a Quantity object, so the NUMBER projection made
    ``O.valueQuantity`` NULL on every row: the ``as Quantity`` cast answered null and each
    aggregate over it 0 / null, with no error anywhere.
    """
    projection = "fhirpath_number(r.resource, 'valueQuantity') AS value_quantity"
    for label, con in _engines():
        _, sql = _population(con)
        assert "fhirpath_text(r.resource, 'valueQuantity') AS value_quantity" in sql, (
            f"[{label}] the valueQuantity column is not the Quantity itself"
        )
        assert projection not in sql, f"[{label}] valueQuantity is precomputed as a number"
        assert "parse_quantity(CAST(O.value_quantity AS VARCHAR))" in sql, (
            f"[{label}] the as-Quantity cast does not read the precomputed Quantity"
        )
