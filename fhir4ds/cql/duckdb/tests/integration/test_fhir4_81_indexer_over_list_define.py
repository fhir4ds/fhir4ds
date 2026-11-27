"""FHIR4-81 — the indexer must index a list-valued define, never slice a character.

CQL 1.5 §17.6 Indexer has two signatures: ``Indexer(source List<T>, index Integer) T`` and
``Indexer(source String, index Integer) String``. A define can hold a list in two shapes:

* an ELEMENT-ROWS define (``define Ids: ([Condition] C return C.id) X``): one CTE row per
  element, ``RowShape.PATIENT_MULTI_VALUE``;
* a STORED-LIST define: one CTE row per patient whose value column holds the whole list,
  with a known element type (``define Words: {'abc', 'd'}``, ``define Nums: {10, 20, 30}``)
  or produced by a query (``define Picked: ({1, 2, 3}) X return X``, typed ``List<Any>``).

FHIR4-70 moved First/Last/IndexOf and the set operators onto the whole-list gate for the first
shape, but the indexer was left on the generic SCALAR lookup and on a "unwrap element 1, then
string-index" shortcut:

    "Ids"[0]      LIMIT-less scalar lookup  -> "More than one row returned by a subquery"
    "Words"[0]    LIST_EXTRACT('abc', 1)    -> 'a'      (character slice!)
    "Nums"[1]     list_extract(INTEGER, …)  -> Binder Error

Each is wrong for every index, on both engines, because both consume the same lowered SQL.
The element-rows case asserts order-INDEPENDENT properties (a query's row order is not a CQL
guarantee): the three indexed values are exactly the list's members.
"""

from __future__ import annotations

import json
import re

import duckdb

from fhir4ds.cql import translate_cql

from .wasm_runtime_helpers import no_python_connection

_PREAMBLE = """library F81 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Ids": ([Condition] C return C.id) X
define "Nums": {10, 20, 30}
define "Words": {'abc', 'd', 'efgh'}
define "Picked": ({1, 2, 3}) X return X
define "S": 'Montavon'
define "Rows": [Condition]
"""

_EPILOGUE = """
define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

#: consumer name -> CQL expression.
_CONSUMERS = {
    "Ids0": '"Ids"[0]',
    "Ids1": '"Ids"[1]',
    "Ids2": '"Ids"[2]',
    "IdsBeyond": '"Ids"[5]',
    "IdsNegative": '"Ids"[-1]',
    "IdsNullIndex": '"Ids"[null]',
    "IdsInIds": '"Ids"[0] in "Ids"',
    "Words0": '"Words"[0]',
    "Words1": '"Words"[1]',
    "WordsBeyond": '"Words"[9]',
    "Nums1": '"Nums"[1]',
    "NumsLast": '"Nums"[2]',
    "Picked1": '"Picked"[1]',
    "PickedLast": '"Picked"[2]',
    "PickedBeyond": '"Picked"[9]',
    # already-correct spellings (regression guards)
    "LiteralChar": "'Montavon'[1]",
    "DefineChar": '"S"[1]',
    "NavFirst": 'Patient.name.given[0]',
    "RowsDefine": '"Rows"[1].id',
    "InlineLiteral": "{'abc', 'd'}[1]",
    "InlineQuery": '(([Condition] C return C.id) X)[1]',
    "InlineRetrieve": '[Condition][1].id',
}

#: ``c2`` is inserted BEFORE ``c1``/``c3`` so no single kept row can satisfy the assertions.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "gender": "female",
     "name": [{"family": "Doe", "given": ["Jane", "Ann"]}]},
    {"resourceType": "Patient", "id": "p2", "gender": "male"},
    {"resourceType": "Patient", "id": "p3", "gender": "female",
     "name": [{"family": "Roe", "given": ["Zoe"]}]},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c9", "subject": {"reference": "Patient/p3"}},
]

_IDS = {"c1", "c2", "c3"}

#: The defect's signature: the generic scalar lookup of the define CTE inside the indexer.
_SCALAR_LOOKUP = re.compile(r'LIST_EXTRACT\(\s*\(SELECT\s+sub\.value\s+FROM\s+"(Ids|Words)"', re.IGNORECASE)
#: The "unwrap element 1, then index" shortcut over a list-valued define.
_UNWRAP_FIRST = re.compile(r'array_extract\(\s*\(SELECT\s+sub\.value\s+FROM\s+"(Words|Nums|Picked)"', re.IGNORECASE)


def _connections():
    """Python-supplement and no-Python engines (both must answer the same)."""
    from contextlib import contextmanager

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    @contextmanager
    def _py():
        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            yield con
        finally:
            con.close()

    yield from ((_py(), "python"), (no_python_connection(), "no_python"))


def _library_text() -> str:
    return _PREAMBLE + "".join(
        f'define "{name}": {expr}\n' for name, expr in _CONSUMERS.items()
    ) + _EPILOGUE


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        patient_ref = (resource.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), patient_ref],
        )


def _scalar(value):
    """Unwrap the population surface's one-element projection wrap.

    A define whose value comes from a resource property (``"Rows"[1].id``) is typed ``List<Any>``
    and the population projection wraps it as a one-element list (the pre-existing list-typed
    metadata issue FHIR4-70 recorded as separate). The ELEMENT is what this file tests.
    """
    return value[0] if isinstance(value, list) and len(value) == 1 else value


def _run_both_engines():
    """Yield ``(label, by_patient)`` with every consumer projected in ONE library."""
    cql_text = _library_text()
    for ctx, label in _connections():
        with ctx as con:
            from fhir4ds.cql.parser import parse_cql
            from fhir4ds.cql.translator.translator import CQLToSQLTranslator

            library = parse_cql(cql_text)
            translator = CQLToSQLTranslator(connection=con)
            translator.translate_library(library)
            sql = translator.translate_library_to_population_sql(
                library=library, output_columns={name: name for name in _CONSUMERS}
            )
            # Keep DuckDB's default strictness: a shape defect must not be masked
            # by a harness flag (FHIR4-48/53 doctrine).
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            by_patient = {row[0]: dict(zip(names[1:], row[1:], strict=True)) for row in cursor.fetchall()}
            yield label, by_patient


def test_an_element_rows_define_is_indexed_as_a_list():
    """``Ids[i]`` is the i-th ELEMENT of the whole list, never a slice of one kept row."""
    for label, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        got = [p1["Ids0"], p1["Ids1"], p1["Ids2"]]
        assert set(got) == _IDS, (
            f"{label}: Ids[0..2] = {got!r}; expected exactly the list's members {_IDS}"
        )
        assert all(isinstance(value, str) and len(value) == 2 for value in got), (
            f"{label}: {got!r} looks like character slices of one kept element"
        )
        assert p1["IdsInIds"] is True, f"{label}: Ids[0] in Ids must be TRUE"
        for column in ("IdsBeyond", "IdsNegative", "IdsNullIndex"):
            assert p1[column] is None, f"{label}: {column} must be null, got {p1[column]!r}"
        # One condition: the first index is its id, every later index is null.
        p3 = by_patient["p3"]
        assert p3["Ids0"] == "c9", f"{label}: Ids[0] for p3 = {p3['Ids0']!r}"
        assert p3["Ids1"] is None and p3["IdsBeyond"] is None, label
        # No condition: every index is null.
        p2 = by_patient["p2"]
        assert all(p2[column] is None for column in ("Ids0", "Ids1", "Ids2", "IdsBeyond")), label


def test_a_stored_list_define_is_indexed_as_a_list():
    """A define whose value column holds the whole list is indexed as that list."""
    for label, by_patient in _run_both_engines():
        for patient, by_column in by_patient.items():
            where = f"{label}/{patient}"
            assert by_column["Words0"] == "abc", f"{where}: Words[0] = {by_column['Words0']!r}"
            assert by_column["Words1"] == "d", f"{where}: Words[1] = {by_column['Words1']!r}"
            assert by_column["WordsBeyond"] is None, where
            assert by_column["Nums1"] == 20 and by_column["NumsLast"] == 30, where
            assert by_column["Picked1"] == 2 and by_column["PickedLast"] == 3, where
            assert by_column["PickedBeyond"] is None, where


def test_string_indexing_and_the_other_list_spellings_are_unchanged():
    """The regression guards: strings stay strings, the other list sources stay lists."""
    for label, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["LiteralChar"] == "o" and p1["DefineChar"] == "o", label
        assert p1["NavFirst"] == "Jane", f"{label}: chained navigation is LIST indexing"
        assert p1["InlineLiteral"] == "d", label
        for column in ("RowsDefine", "InlineQuery", "InlineRetrieve"):
            got = _scalar(p1[column])
            assert got in _IDS, f"{label}: {column} = {p1[column]!r}, expected a member of Ids"
        p2 = by_patient["p2"]
        for column in ("RowsDefine", "InlineQuery", "InlineRetrieve"):
            assert p2[column] is None, f"{label}: {column} must be null without data"


def test_the_indexer_lowers_list_defines_as_lists():
    """SQL shape: no scalar lookup of a list define, no unwrap-then-index shortcut."""
    sql = translate_cql(_library_text())
    for name in ("Ids0", "Ids1", "Words0", "Nums1", "Picked1"):
        assert not _SCALAR_LOOKUP.search(sql[name].to_sql()), (
            f"{name}: the generic scalar lookup of a list define feeds the indexer"
        )
        assert not _UNWRAP_FIRST.search(sql[name].to_sql()), (
            f"{name}: the indexer unwraps element 1 of a list-valued define before indexing"
        )
        assert "list_extract" in sql[name].to_sql().lower(), name
    # A String source keeps the public string Indexer.
    assert "Indexer(" in sql["DefineChar"].to_sql()
    assert "Indexer(" in sql["LiteralChar"].to_sql()
