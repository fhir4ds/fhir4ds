"""FHIR4-75 — an empty list is empty: existence, counting and `empty` over stored-list defines.

A define can hold its list in ONE row per patient (a "stored list": a list literal, a typed list
cast such as ``({} as List<String>)``, or a dynamic multi-valued property such as
``Patient.name.given``). Consumers that only asked whether that row EXISTS answered for the row,
not the list:

- ``exists(X)`` was TRUE and ``not exists(X)`` FALSE for an EMPTY stored list;
- ``Count(X)`` was 1 for ``({} as List<String>)``, whose define was filed as a resource;
- ``Count`` / ``Sum`` of a typed null list lowered to row aggregates over the patient table and
  broke population SQL.

The converse operator did not exist at all: ``empty(X)``, ``X.empty()`` and ``X is [not] empty``
all failed. They are implemented here as the negation of the same non-emptiness test.

The element-rows define (a query) is the control: row presence IS non-emptiness there.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import duckdb
import pytest

from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection

_EMPTY_SHAPES = {
    "TypedEmpty": "({} as List<String>)",
    "TypedNull": "(null as List<String>)",
    "EmptyLit": "{}",
    "GivenNames": "Patient.name.given",
    "Codes": "([Condition] C return C.id) X",
}

#: The shapes that carry data for the patient who has a name and a condition.
_DATA_SHAPES = ("GivenNames", "Codes")

_PATIENTS = {
    "p3": [{"resourceType": "Patient", "id": "p3", "gender": "female"}],
    "p1": [
        {
            "resourceType": "Patient",
            "id": "p1",
            "gender": "male",
            "name": [{"family": "Doe", "given": ["Jane", "Ann"]}],
        },
        {
            "resourceType": "Condition",
            "id": "c1",
            "subject": {"reference": "Patient/p1"},
            "code": {"text": "cold"},
        },
    ],
}

_EMPTY_SPELLINGS = {
    "function": 'empty("{name}")',
    "method": '"{name}".empty()',
    "is_empty": '"{name}" is empty',
    "is_not_empty": '"{name}" is not empty',
}


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


def _translate(con, defines: dict) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    lines = ["library FHIR75 version '1.0.0'", "using FHIR version '4.0.1'", "context Patient"]
    lines += [f'define "{name}": {expression}' for name, expression in defines.items()]
    lines.append('define "Initial Population": exists (Patient)')
    library = parse_cql("\n".join(lines) + "\n")
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library,
        output_columns={name: name for name in defines}
        | {"Initial Population": "Initial Population"},
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, "
        "patient_ref VARCHAR)"
    )
    for patient_id, resources in _PATIENTS.items():
        for resource in resources:
            subject = (resource.get("subject") or {}).get("reference", "")
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [
                    resource["id"],
                    resource["resourceType"],
                    json.dumps(resource),
                    subject.split("/")[-1] if subject else patient_id,
                ],
            )


def _evaluate(con, defines: dict) -> dict:
    """``{patient_id: {define: value}}`` for the population SQL of ``defines``."""
    sql = _translate(con, defines)
    _load(con)
    cursor = con.execute(sql)
    names = [column[0] for column in cursor.description]
    return {str(row[0]): dict(zip(names, row, strict=True)) for row in cursor.fetchall()}


def _shapes_and(defines: dict) -> dict:
    return dict(_EMPTY_SHAPES) | defines


# --------------------------------------------------------------------------- exists / Count


def test_exists_over_an_empty_stored_list_define_is_false():
    """Row presence is not non-emptiness: every empty shape answers FALSE for the patient with no
    data, in the operator form, the function form and under ``not``."""
    defines = _shapes_and(
        {
            f"{name}{suffix}": template.format(name=name)
            for name in _EMPTY_SHAPES
            for suffix, template in (
                ("Op", 'exists("{name}")'),
                ("Fn", 'Exists("{name}")'),
                ("Not", 'not exists("{name}")'),
            )
        }
    )
    for con in _engines():
        got = _evaluate(con, defines)["p3"]
        for name in _EMPTY_SHAPES:
            assert got[f"{name}Op"] is False, (name, got[f"{name}Op"])
            assert got[f"{name}Fn"] is False, (name, got[f"{name}Fn"])
            assert got[f"{name}Not"] is True, (name, got[f"{name}Not"])


def test_exists_over_a_list_with_data_is_true():
    defines = _shapes_and(
        {f"{name}Op": f'exists("{name}")' for name in _DATA_SHAPES}
        | {f"{name}Not": f'not exists("{name}")' for name in _DATA_SHAPES}
    )
    for con in _engines():
        got = _evaluate(con, defines)["p1"]
        for name in _DATA_SHAPES:
            assert got[f"{name}Op"] is True, (name, got[f"{name}Op"])
            assert got[f"{name}Not"] is False, (name, got[f"{name}Not"])


def test_count_of_an_empty_stored_list_define_is_zero():
    """``Count`` counts elements: 0 for every empty shape, including the typed null list (official
    ``CountNullSource``), and the element counts for the patient with data."""
    defines = _shapes_and({f"{name}Count": f'Count("{name}")' for name in _EMPTY_SHAPES})
    expected_data = {"GivenNamesCount": 2, "CodesCount": 1}
    for con in _engines():
        result = _evaluate(con, defines)
        for name in _EMPTY_SHAPES:
            assert result["p3"][f"{name}Count"] == 0, (name, result["p3"][f"{name}Count"])
        for define, expected in expected_data.items():
            assert result["p1"][define] == expected, (define, result["p1"][define])


def test_a_typed_list_cast_define_is_a_stored_list():
    """``({} as List<String>)`` and ``(null as List<String>)`` store their list in the ``value``
    column; they were filed as resources (``resource`` column), which made ``Count`` count the
    row."""
    for con in _engines():
        sql = _translate(
            con, {"TypedEmpty": _EMPTY_SHAPES["TypedEmpty"], "TypedNull": _EMPTY_SHAPES["TypedNull"]}
        )
        for name, stored in (
            ("TypedEmpty", "CAST([] AS VARCHAR[]) AS value"),
            ("TypedNull", "CAST(NULL AS VARCHAR[]) AS value"),
        ):
            start = sql.index(f'"{name}" AS MATERIALIZED (')
            body = sql[start : sql.index("FROM _patients", start)]
            assert stored in body, (name, body[:200])
            assert " AS resource" not in body, (name, body[:200])


def test_an_alias_of_a_typed_empty_list_is_empty():
    """The stored-list marker reaches a define that only aliases the list."""
    defines = _shapes_and(
        {"Alias": '"TypedEmpty"', "AliasExists": 'exists("Alias")', "AliasCount": 'Count("Alias")'}
    )
    for con in _engines():
        got = _evaluate(con, defines)["p3"]
        assert got["AliasExists"] is False, got["AliasExists"]
        assert got["AliasCount"] == 0, got["AliasCount"]


def test_aggregates_of_a_null_list_literal_are_not_row_aggregates():
    """``Count(null as List<Integer>)`` is 0 and the other aggregates are null. In population SQL
    they lowered to ``COUNT(...)`` / ``SUM(...)`` over the patient table and did not bind."""
    defines = {
        "CountNull": "Count(null as List<Integer>)",
        "CountEmptyCast": "Count({} as List<Integer>)",
        "SumNull": "Sum(null as List<Integer>)",
        "AvgNull": "Avg(null as List<Integer>)",
        "MinNull": "Min(null as List<Integer>)",
        "MaxNull": "Max(null as List<Integer>)",
    }
    for con in _engines():
        sql = _translate(con, defines)
        assert "COUNT(" not in sql and "SUM(" not in sql, sql[sql.index("WITH") :][:600]
        got = _evaluate(con, defines)["p3"]
        assert got["CountNull"] == 0 and got["CountEmptyCast"] == 0, got
        assert all(got[name] is None for name in ("SumNull", "AvgNull", "MinNull", "MaxNull")), got


# --------------------------------------------------------------------------- empty


@pytest.mark.parametrize("spelling", list(_EMPTY_SPELLINGS))
def test_empty_answers_for_every_spelling_and_shape(spelling):
    """``empty`` is TRUE for every empty shape and FALSE when the list has data; ``is not empty`` is
    its negation. The result is one Boolean per patient, never a one-element list.

    The typed null list is the exception: ``empty`` of null is null (see
    ``test_empty_of_a_null_list_is_null``), and a Boolean define reports null as FALSE at the
    population surface for either spelling."""
    template = _EMPTY_SPELLINGS[spelling]
    defines = _shapes_and({f"{name}E": template.format(name=name) for name in _EMPTY_SHAPES})
    empty_answer = spelling != "is_not_empty"
    for con in _engines():
        result = _evaluate(con, defines)
        for name in _EMPTY_SHAPES:
            value = result["p3"][f"{name}E"]
            expected = False if name == "TypedNull" else empty_answer
            assert value is expected, (spelling, name, value)
            assert isinstance(value, bool), (spelling, name, value)
        for name in _DATA_SHAPES:
            assert result["p1"][f"{name}E"] is (not empty_answer), (spelling, name)


def test_empty_of_a_null_list_is_null():
    """CQL 1.5 §Empty: a null argument gives null. (A Boolean define reports null as FALSE at the
    population surface, so read it through ``Coalesce``.)"""
    defines = _shapes_and(
        {
            "NullIsEmpty": 'Coalesce("TypedNull".empty(), 42)',
            "NullIsNotEmpty": 'Coalesce("TypedNull" is not empty, 42)',
            "EmptyIsEmpty": 'Coalesce("TypedEmpty".empty(), 42)',
        }
    )
    for con in _engines():
        got = _evaluate(con, defines)["p3"]
        assert got["NullIsEmpty"] == 42, got
        assert got["NullIsNotEmpty"] == 42, got
        assert bool(got["EmptyIsEmpty"]) is True, got


def test_empty_composes_as_a_boolean():
    defines = _shapes_and(
        {
            "WithAnd": '"Codes".empty() and true',
            "Negated": 'not "GivenNames".empty()',
            "WithOr": 'empty("Codes") or false',
            "Conditional": 'if "Codes".empty() then 1 else 2',
            "CaseExpr": 'case when "Codes" is empty then 10 else 20 end',
            "IsTrue": '("GivenNames".empty()) is true',
        }
    )
    expected = {
        "p3": {"WithAnd": True, "Negated": False, "WithOr": True, "Conditional": 1, "CaseExpr": 10, "IsTrue": True},
        "p1": {"WithAnd": False, "Negated": True, "WithOr": False, "Conditional": 2, "CaseExpr": 20, "IsTrue": False},
    }
    for con in _engines():
        result = _evaluate(con, defines)
        for patient_id, values in expected.items():
            for define, value in values.items():
                assert result[patient_id][define] == value, (patient_id, define, result[patient_id][define])


def test_empty_of_a_list_literal():
    defines = {
        "EmptyLiteral": "empty({})",
        "NonEmptyLiteral": "empty({'a'})",
        "OnlyNulls": "empty({null})",
        "LiteralIs": "{1, 2, 3} is empty",
        "LiteralCast": "empty({} as List<String>)",
    }
    for con in _engines():
        got = _evaluate(con, defines)["p3"]
        assert {name: got[name] for name in defines} == {
            "EmptyLiteral": True,
            "NonEmptyLiteral": False,
            "OnlyNulls": True,
            "LiteralIs": False,
            "LiteralCast": True,
        }, got
