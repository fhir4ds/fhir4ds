"""FHIR4-90 — a cast of an inline navigation to ``List<T>`` is answered by the schema.

``Patient.name.given as List<String>`` is the list the FHIR schema already says the navigation
is. Before this fix the inline spelling was lowered to a RUNTIME probe of the FIRST element —
``json_extract_string(fhirpath_text(...), '$.resourceType') = 'List<String>'`` — which crashed
on the plain string (``Invalid Input Error: Malformed JSON … Input: "Jane"``) and, had it not
crashed, compared a JSON field with a type name, so it could only ever have answered NULL.

These tests read VALUES on both engines: the list for a patient with two given names, and an
EMPTY list (not NULL, not an error) for a patient with none. List order is not part of the
answer, so lists are compared sorted. Nothing here pins how a define is TYPED (that is
FHIR4-106), and a DEFINE REFERENCE cast is asserted only where it already agrees — the empty
case of that spelling is carded separately.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_P = ("p1", "p2", "p3")

_PATIENTS: dict[str, dict] = {
    "p1": {
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"given": ["Jane", "Ann"], "family": "Doe", "prefix": ["Dr"]}],
        "telecom": [{"system": "phone", "value": "111"}, {"system": "email", "value": "a@b"}],
    },
    # No names at all: the navigation is an EMPTY list, which is still a List<String>.
    "p2": {"resourceType": "Patient", "id": "p2"},
    "p3": {"resourceType": "Patient", "id": "p3", "name": [{"given": ["Zoe"]}]},
}

#: (observation id, patient id, value payload)
_OBSERVATIONS: tuple[tuple[str, str, dict], ...] = (
    ("o1", "p1", {"valueString": "5"}),
    ("o2", "p1", {"valueBoolean": True}),  # not a String: a null ELEMENT, the row stays
    ("o3", "p3", {"valueString": "7"}),
)

_HEADER = """library InlineListCast version '1.0'
using FHIR version '4.0.1'
context Patient

"""

#: The inline spellings, all in one population.
INLINE = _HEADER + """define "PlainGiven": Patient.name.given
define "InlineGiven": Patient.name.given as List<String>
define "InlineSystem": Patient.telecom.system as List<String>
define "InlineFamily": Patient.name.family as List<String>
define "InlineUnion": (Patient.name.given union Patient.name.prefix) as List<String>
define "InlineNames": Patient.name as List<FHIR.HumanName>
define "InlineWrong": Patient.name.given as List<Integer>
define "InlineIsRight": Patient.name.given is List<String>
define "InlineIsWrong": Patient.name.given is List<Integer>
define "InlineCount": Count(Patient.name.given as List<String>)
define "InlineCastOk": cast Patient.name.given as List<String>
"""

_GIVEN = {"p1": ["Ann", "Jane"], "p2": [], "p3": ["Zoe"]}
_NONE = dict.fromkeys(_P)
_TRUE = dict.fromkeys(_P, True)
_FALSE = dict.fromkeys(_P, False)

#: column -> patient -> answer, lists already sorted.
EXPECTED: dict[str, dict[str, object]] = {
    "PlainGiven": _GIVEN,
    "InlineGiven": _GIVEN,
    "InlineSystem": {"p1": ["email", "phone"], "p2": [], "p3": []},
    "InlineFamily": {"p1": ["Doe"], "p2": [], "p3": []},
    "InlineUnion": {"p1": ["Ann", "Dr", "Jane"], "p2": [], "p3": ["Zoe"]},
    "InlineWrong": _NONE,
    "InlineIsRight": _TRUE,
    "InlineIsWrong": _FALSE,
    "InlineCount": {"p1": 2, "p2": 0, "p3": 1},
    "InlineCastOk": _GIVEN,
}

_HUMAN_NAMES = {
    "p1": [("Doe", ("Ann", "Jane"))],
    "p2": [],
    "p3": [(None, ("Zoe",))],
}

_COLUMNS = {name: name for name in EXPECTED}


def _normalize(value: object) -> object:
    return sorted(value, key=repr) if isinstance(value, list) else value


def _define_body(sql: str, name: str) -> str:
    """One definition's CTE body: from its name up to the patient scan."""
    start = sql.index(f'"{name}" AS')
    return sql[start + len(name) + 3 : sql.index("FROM _patients", start)]


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
            for patient_id, resource in _PATIENTS.items():
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [patient_id, "Patient", json.dumps(resource), patient_id],
                )
            for observation_id, patient_id, value in _OBSERVATIONS:
                resource = {"resourceType": "Observation", "id": observation_id, "status": "final",
                            "subject": {"reference": f"Patient/{patient_id}"}, **value}
                con.execute(
                    "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [observation_id, "Observation", json.dumps(resource), patient_id],
                )
            yield label, con


def _population(con, cql: str, columns: dict[str, str]) -> tuple[dict[str, dict[str, object]], str]:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(cql)
    translator = CQLToSQLTranslator(connection=con, library_loader=lambda *args: None)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(library=library, output_columns=columns)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    answers: dict[str, dict[str, object]] = {column: {} for column in columns}
    for row in cursor.fetchall():
        for column in columns:
            answers[column][str(row[0])] = _normalize(row[names.index(column)])
    return answers, sql


@pytest.mark.parametrize("column", sorted(EXPECTED))
def test_an_inline_list_cast_answers_the_value_it_already_has(column: str) -> None:
    expected = {p: _normalize(v) for p, v in EXPECTED[column].items()}
    for label, con in _engines():
        answers, _ = _population(con, INLINE, _COLUMNS)
        assert answers[column] == expected, f"[{label}] {column}: {answers[column]}"


def test_the_human_name_cast_is_the_list_of_name_elements() -> None:
    def as_tuples(value: object) -> list[tuple[object, tuple[object, ...]]]:
        names = [json.loads(text) for text in value] if isinstance(value, list) else []
        return sorted((n.get("family"), tuple(sorted(n.get("given", [])))) for n in names)

    for label, con in _engines():
        answers, _ = _population(con, INLINE, {"InlineNames": "InlineNames"})
        got = {p: as_tuples(answers["InlineNames"].get(p)) for p in _P}
        assert got == _HUMAN_NAMES, f"[{label}] {got}"


def test_consumers_of_the_inline_cast_see_the_list() -> None:
    """`First` is one element of the list, `Upper` applies to it, `is null` is false when empty."""
    cql = _HEADER + (
        'define "InlineFirst": First(Patient.name.given as List<String>)\n'
        'define "InlineUpperFirst": Upper(First(Patient.name.given as List<String>))\n'
        'define "InlineFirstFamily": First(Patient.name.family as List<String>)\n'
        'define "InlineCastIsNull": (Patient.name.given as List<String>) is null\n'
    )
    columns = {"InlineFirst": "InlineFirst", "InlineUpperFirst": "InlineUpperFirst",
               "InlineFirstFamily": "InlineFirstFamily", "InlineCastIsNull": "InlineCastIsNull"}
    for label, con in _engines():
        answers, _ = _population(con, cql, columns)
        assert answers["InlineFirst"]["p1"] in {"Jane", "Ann"}, f"[{label}] {answers}"
        assert answers["InlineUpperFirst"]["p1"] in {"JANE", "ANN"}, f"[{label}] {answers}"
        # The empty list has no first element: null, not an error.
        assert answers["InlineFirst"]["p2"] is None, f"[{label}] {answers}"
        assert answers["InlineFirst"]["p3"] == "Zoe", f"[{label}] {answers}"
        assert answers["InlineFirstFamily"] == {"p1": "Doe", "p2": None, "p3": None}, f"[{label}] {answers}"
        assert answers["InlineCastIsNull"] == _FALSE, f"[{label}] {answers}"


def test_a_strict_cast_to_a_type_the_navigation_does_not_have_fails() -> None:
    cql = _HEADER + 'define "Bad": cast Patient.name.given as List<Integer>\n'
    for label, con in _engines():
        with pytest.raises(duckdb.InvalidInputException, match="CQL strict cast failed"):
            _population(con, cql, {"Bad": "Bad"}), f"[{label}] the strict cast did not fail"


def test_the_define_spelling_agrees_where_the_list_is_not_empty() -> None:
    """The define spelling already returns the list for patients that have names.

    Its EMPTY case (NULL today, where the card wants an empty list) is carded separately and
    is deliberately not asserted here.
    """
    cql = _HEADER + 'define "G": Patient.name.given\ndefine "AliasGiven": "G" as List<String>\n'
    for label, con in _engines():
        answers, _ = _population(con, cql, {"AliasGiven": "AliasGiven"})
        alias = answers["AliasGiven"]
        assert alias["p1"] == ["Ann", "Jane"] and alias["p3"] == ["Zoe"], f"[{label}] {alias}"


def test_a_resource_path_cast_still_behaves() -> None:
    """Control, expected green before AND after: `O.value as FHIR.string` keeps its choice logic."""
    cql = _HEADER + 'define "ResourceCast": [Observation] O return O.value as FHIR.string\n'
    expected = {"p1": ["5", None], "p2": [], "p3": ["7"]}
    for label, con in _engines():
        answers, _ = _population(con, cql, {"ResourceCast": "ResourceCast"})
        assert answers["ResourceCast"] == expected, f"[{label}] {answers}"


def test_the_inline_cast_is_the_plain_navigation_not_a_runtime_probe() -> None:
    """Relative shape: the cast's define body IS the plain navigation's body."""
    for label, con in _engines():
        _, sql = _population(con, INLINE, {"PlainGiven": "PlainGiven", "InlineGiven": "InlineGiven"})
        cast = _define_body(sql, "InlineGiven")
        assert cast == _define_body(sql, "PlainGiven"), f"[{label}] {cast!r}"
        assert "from_json(fhirpath(_pt.patient_resource, 'name.given'), '[\"VARCHAR\"]')" in cast, (
            f"[{label}] {cast!r}"
        )
        assert "'$.resourceType') = 'List<" not in sql, f"[{label}] a runtime type-name probe survived"
