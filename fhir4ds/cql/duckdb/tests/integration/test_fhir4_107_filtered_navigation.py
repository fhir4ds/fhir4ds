"""FHIR4-107 — a filtered navigation is ONE navigation.

``Patient.extension.where(url = '…').value`` is the every-day spelling of "the value of the
extension with this URL". Before this fix the query was lowered step by step:

- alias-less: the criterion ``url = '…'`` became a bare SQL column, so every consumer after
  it failed with ``Binder Error: Referenced column "url" not found`` — in a define body just
  as much as inline;
- with an alias (``Patient.extension E where E.url = '…'``): the filter ran on the
  UNFILTERED collection, so ``.value`` answered with the FIRST extension whenever ANY
  extension matched (a patient whose first extension has another URL got that one's value).

The query is now one FHIRPath navigation on the resource it starts from. These tests read
VALUES (never shapes or lengths) on both engines; patient p4 has the other extension FIRST,
which is the case the alias spelling used to get wrong.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

URL_X = "http://x"
URL_Y = "http://y"

_X_HELLO = {"url": URL_X, "valueString": "hello"}
_X_GUTEN_TAG = {"url": URL_X, "valueString": "guten tag"}
_Y_TRUE = {"url": URL_Y, "valueBoolean": True}

PATIENTS: dict[str, dict] = {
    "p1": {
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "name": [{"given": ["Jane", "Ann"]}],
        "telecom": [{"system": "phone", "value": "111"}, {"system": "email", "value": "a@b"}],
        "extension": [_X_HELLO, _Y_TRUE],
    },
    # The other URL comes FIRST: the alias spelling used to answer with THIS extension.
    "p4": {"resourceType": "Patient", "id": "p4", "extension": [_Y_TRUE, _X_GUTEN_TAG]},
    "p2": {"resourceType": "Patient", "id": "p2"},
    "p3": {"resourceType": "Patient", "id": "p3", "extension": [_X_GUTEN_TAG]},
    "p5": {"resourceType": "Patient", "id": "p5", "name": [{"given": ["Zoe"]}],
           "extension": [_Y_TRUE]},
}

LIBRARY = f"""library FilteredNavigation version '1.0'
using FHIR version '4.0.1'
context Patient

define "V": Patient.extension.where(url = '{URL_X}').value
define "VNoSpaces": Patient.extension.where(url='{URL_X}').value
define "VString": Patient.extension.where(url = '{URL_X}').value as FHIR.string
define "VExists": Patient.extension.where(url = '{URL_X}').value.exists()
define "VNotNull": Patient.extension.where(url = '{URL_X}').value is not null
define "QExists": exists(Patient.extension.where(url = '{URL_X}'))
define "AliasV": (Patient.extension E where E.url = '{URL_X}').value
define "ThisV": Patient.extension.where($this.url = '{URL_X}').value
define "FirstV": First(Patient.extension.where(url = '{URL_X}')).value
define "FirstUrl": First(Patient.extension.where(url = '{URL_X}')).url
define "LastUrl": Last(Patient.extension.where(url = '{URL_X}')).url
define "N": Count(Patient.extension.where(url = '{URL_X}'))
define "MethodN": Patient.extension.where(url = '{URL_X}').count()
define "MethodFirstUrl": Patient.extension.where(url = '{URL_X}').first().url
define "MethodExists": Patient.extension.where(url = '{URL_X}').exists()
define "YBool": Patient.extension.where(url = '{URL_Y}').value as FHIR.boolean
define "LiteralFirstV": Patient.extension.where('{URL_X}' = url).value
define "NotXCount": Count(Patient.extension.where(not (url = '{URL_X}')))
define "NeXCount": Count(Patient.extension.where(url != '{URL_X}'))
define "AndCount": Count(Patient.extension.where(url = '{URL_X}' and valueString = 'hello'))
define "Phones": Patient.telecom.where(system = 'phone').value
define "GivenExists": Patient.name.given.exists()
define "ActiveExists": Patient.active.exists()
define "AliasRootX": exists([Patient] P where P.extension.where(url = '{URL_X}').value is not null)
"""

COLUMNS = {
    "V": "V", "VNoSpaces": "VNoSpaces", "VString": "VString", "VExists": "VExists",
    "VNotNull": "VNotNull", "QExists": "QExists", "AliasV": "AliasV", "ThisV": "ThisV",
    "FirstV": "FirstV", "FirstUrl": "FirstUrl", "LastUrl": "LastUrl", "N": "N",
    "MethodN": "MethodN", "MethodFirstUrl": "MethodFirstUrl", "MethodExists": "MethodExists",
    "YBool": "YBool", "LiteralFirstV": "LiteralFirstV", "NotXCount": "NotXCount",
    "NeXCount": "NeXCount", "AndCount": "AndCount", "Phones": "Phones",
    "GivenExists": "GivenExists", "ActiveExists": "ActiveExists", "AliasRootX": "AliasRootX",
}

_P = ("p1", "p2", "p3", "p4", "p5")

_VALUE_OF_X = {"p1": "hello", "p2": None, "p3": "guten tag", "p4": "guten tag", "p5": None}
_HAS_X = {"p1": True, "p2": False, "p3": True, "p4": True, "p5": False}
_NO_X_COUNT = {"p1": 1, "p2": 0, "p3": 0, "p4": 1, "p5": 1}

#: column -> patient -> answer. p4 is the patient whose FIRST extension has the other URL.
EXPECTED: dict[str, dict[str, object]] = {
    "V": _VALUE_OF_X,
    "VNoSpaces": _VALUE_OF_X,
    "VString": _VALUE_OF_X,
    "VExists": _HAS_X,
    "VNotNull": _HAS_X,
    "QExists": _HAS_X,
    "AliasV": _VALUE_OF_X,
    "ThisV": _VALUE_OF_X,
    "FirstV": _VALUE_OF_X,
    "FirstUrl": {"p1": URL_X, "p2": None, "p3": URL_X, "p4": URL_X, "p5": None},
    "LastUrl": {"p1": URL_X, "p2": None, "p3": URL_X, "p4": URL_X, "p5": None},
    "N": {"p1": 1, "p2": 0, "p3": 1, "p4": 1, "p5": 0},
    "MethodN": {"p1": 1, "p2": 0, "p3": 1, "p4": 1, "p5": 0},
    # The METHOD spelling `.first().url` is one navigation too, but its define is still
    # filed as a stored list by the define-shape heuristic in translator.py (every define
    # that ends in a navigation is): the answers are one-element lists, empty when nothing
    # matches. Same wrap FHIR4-70 and FHIR4-81 recorded; not this card's to change.
    "MethodFirstUrl": {"p1": [URL_X], "p2": [], "p3": [URL_X], "p4": [URL_X], "p5": []},
    "MethodExists": _HAS_X,
    "YBool": {"p1": True, "p2": None, "p3": None, "p4": True, "p5": True},
    "LiteralFirstV": _VALUE_OF_X,
    "NotXCount": _NO_X_COUNT,
    "NeXCount": _NO_X_COUNT,
    # Only p1's x-extension carries the string the second condition names.
    "AndCount": {"p1": 1, "p2": 0, "p3": 0, "p4": 0, "p5": 0},
    "Phones": {"p1": ["111"], "p2": [], "p3": [], "p4": [], "p5": []},
    "GivenExists": {"p1": True, "p2": False, "p3": False, "p4": False, "p5": True},
    "ActiveExists": {"p1": True, "p2": False, "p3": False, "p4": False, "p5": False},
    "AliasRootX": _HAS_X,
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
            for patient_id, resource in PATIENTS.items():
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [patient_id, "Patient", json.dumps(resource), patient_id],
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
    answers: dict[str, dict[str, object]] = {column: {} for column in COLUMNS}
    for row in cursor.fetchall():
        for column in COLUMNS:
            value = row[names.index(column)]
            answers[column][str(row[0])] = sorted(value) if isinstance(value, list) else value
    return answers, sql


@pytest.mark.parametrize("column", sorted(EXPECTED))
def test_a_filtered_navigation_answers_by_value(column: str) -> None:
    for label, con in _engines():
        answers, _ = _population(con)
        got = answers[column]
        assert set(got) == set(_P), f"[{label}] {column}: patients {sorted(got)}"
        for patient_id in _P:
            assert got[patient_id] == EXPECTED[column][patient_id], (
                f"[{label}] {column} for {patient_id}: {got[patient_id]!r}, "
                f"expected {EXPECTED[column][patient_id]!r}"
            )


def test_the_define_body_is_one_navigation_on_the_resource() -> None:
    """One evaluation of one navigation: no bare ``url`` column, no filter-after-the-fact."""
    # Inside a SQL string literal the URL's own quotes are doubled.
    filtered = f"extension.where(url = ''{URL_X}'')"
    # What each define's own CTE must contain (read from the define's name onwards).
    cte = {
        "V": f"fhirpath_text(_pt.patient_resource, '{filtered}.value')",
        "VExists": f"fhirpath_bool(_pt.patient_resource, '{filtered}.value.exists()')",
        "FirstUrl": f"fhirpath_text(_pt.patient_resource, '{filtered}.first().url')",
        "MethodFirstUrl": f"fhirpath(_pt.patient_resource, '{filtered}.first().url')",
    }
    for label, con in _engines():
        _, sql = _population(con)
        for name, call in cte.items():
            start = sql.index(f'"{name}" AS ')
            own = sql[start : start + 300]
            assert call in own, f"[{label}] {name} is not one navigation:\n{own}"
        assert "CASE WHEN url = " not in sql, f"[{label}] the criterion became a bare column"
