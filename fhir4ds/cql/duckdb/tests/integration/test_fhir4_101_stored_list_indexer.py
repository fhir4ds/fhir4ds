"""FHIR4-101 — the indexer reads a stored-list define's LIST, never one character.

CQL 1.5 §17.6 has two Indexer signatures:

    Indexer(source List<T>, index Integer) T
    Indexer(source String,  index Integer) String

A define whose value column holds the WHOLE element list in one row per patient
(`DefinitionMeta.stores_list_value`) is the FIRST: element 0 is the whole element,
element 1 does not exist. The indexer used to disagree, for exactly one class:

    define "Fam": First([Patient]).name.family       -- meta List<Any>
    "Fam"[0]  ->  'M'          (!)  Indexer(array_extract(value, 1), 0)
    "Fam"[3]  ->  't'          (!)  a CHARACTER of 'Montavon'

`_stored_list_define_is_a_list` kept a "navigation is the exception" carve-out
(`body is not Property`) from FHIR4-81, when the translator could not type a
navigation define. FHIR4-89 removed the reason for the exception
(`Patient.name.family` is `List<String>` — 0..1 in R4, flattened through the
repeated `name` — and `First([Patient]).name.family` is that same element), so
the carve-out now only mis-handles the classes typing still leaves `List<Any>`:

* an untypeable chain (`First([Patient]).name.family`),
* a single-valued navigation (`Patient.active`, `Patient.extension.value`).

All three answered a character. All three are LIST-valued; the fix claims the
list for EVERY stored-list define, with no type change.

The assertions below are values AND shapes, on both engines, because a value-only
test passes a half fix (the FHIR4-91 lesson).
"""

from __future__ import annotations

import json

import pytest

from fhir4ds.cql import translate_cql

from .wasm_runtime_helpers import no_python_connection

_PREAMBLE = """library F101 version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Fam": First([Patient]).name.family
define "Flag": Patient.active
define "ExtV": Patient.extension.value
define "Family": Patient.name.family
define "Given": Patient.name.given
define "S": 'Montavon'
define "Gender": Patient.gender
define "FamAlias": "Fam"
define "Nums": {10, 20, 30}

define "Fam0": "Fam"[0]
define "Fam1": "Fam"[1]
define "Fam3": "Fam"[3]
define "Fam99": "Fam"[99]
define "FamNeg": "Fam"[-1]
define "FamNull": "Fam"[null]
define "Flag0": "Flag"[0]
define "ExtV0": "ExtV"[0]
define "Family0": "Family"[0]
define "Given0": "Given"[0]
define "Given1": "Given"[1]
define "S0": "S"[0]
define "S1": "S"[1]
define "Gender0": "Gender"[0]
define "FamAlias0": "FamAlias"[0]
define "Nums1": "Nums"[1]

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": true
"""

_CONSUMERS = [
    "Fam0", "Fam1", "Fam3", "Fam99", "FamNeg", "FamNull",
    "Flag0", "ExtV0", "Family0", "Given0", "Given1", "S0", "S1",
    "Gender0", "FamAlias0", "Nums1",
]

#: consumer -> expected value. `None` means SQL NULL.
_EXPECTED = {
    # the class this card fixes: a stored-list define with a List<Any> meta
    "Fam0": "Montavon",
    "Fam1": None,
    "Fam3": None,
    "Fam99": None,
    "FamNeg": None,
    "FamNull": None,
    "Flag0": "true",
    "ExtV0": "hello",
    # already correct (typed lists) — regression guards
    "Family0": "Montavon",
    "Given0": "Joel",
    "Given1": "Ann",
    # a genuine scalar String define keeps CHARACTER indexing (CQL §17.6)
    "S0": "M",
    "S1": "o",
    # more of the same class: a single-valued navigation, an alias of the chain,
    # and an already-correct list literal (control)
    "Gender0": "female",
    "FamAlias0": "Montavon",
    "Nums1": 20,
}

_RESOURCES = [
    {
        "resourceType": "Patient",
        "id": "p1",
        "active": True,
        "gender": "female",
        "name": [{"family": "Montavon", "given": ["Joel", "Ann"]}],
        "extension": [{"url": "http://example.org/x", "valueString": "hello"}],
    },
]


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for resource in _RESOURCES:
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [resource["id"], resource["resourceType"], json.dumps(resource), resource["id"]],
        )


def _engine_context(engine: str):
    """A connection context manager for the requested engine."""
    if engine == "no_python":
        return no_python_connection()

    from contextlib import contextmanager

    import duckdb

    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    @contextmanager
    def _ctx():
        con = duckdb.connect()
        _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
        try:
            yield con
        finally:
            con.close()

    return _ctx()


def _values(con) -> dict:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(_PREAMBLE)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    sql = translator.translate_library_to_population_sql(
        library=library, output_columns={name: name for name in _CONSUMERS}
    )
    _load(con)
    # FHIR4-48/53 doctrine: keep DuckDB's strictness, a shape defect must not be
    # masked by a harness flag.
    con.execute("SET scalar_subquery_error_on_multiple_rows=true")
    cursor = con.execute(sql)
    names = [d[0] for d in cursor.description]
    row = dict(zip(names, cursor.fetchone()))
    out = {}
    for want in _CONSUMERS:
        for name in (want, f'"{want}"'):
            if name in row:
                out[want] = row[name]
                break
    return out


@pytest.mark.parametrize("engine", ["python", "no_python"])
def test_stored_list_define_indexes_the_list_not_a_character(engine):
    """`"Fam"[0]` is the element, `[1]`/`[3]` are NULL — not characters."""
    with _engine_context(engine) as con:
        values = _values(con)
    for name, expected in _EXPECTED.items():
        got = values.get(name)
        if expected is None:
            assert got is None, f"{engine} {name}: expected NULL, got {got!r}"
        else:
            assert got == expected, f"{engine} {name}: expected {expected!r}, got {got!r}"


def test_indexer_lowering_shape():
    """The lowerings themselves: list indexing for a stored list, character
    indexing only for a genuine String source."""
    translated = translate_cql(_PREAMBLE)

    for name in ("Fam0", "Fam1", "Fam3", "Flag0", "ExtV0"):
        sql = translated[name].to_sql()
        assert "LIST_EXTRACT" in sql.upper(), (name, sql)
        # the "unwrap element 1, then string-index" shortcut must be gone
        assert "array_extract" not in sql, (name, sql)
        assert "Indexer(" not in sql, (name, sql)

    # a scalar String define keeps the public Indexer macro (CQL §17.6 String)
    for name in ("S0", "S1"):
        sql = translated[name].to_sql()
        assert "Indexer(" in sql, (name, sql)
        assert "LIST_EXTRACT" not in sql.upper(), (name, sql)

    # typed navigation defines were already list-indexed
    for name in ("Family0", "Given0"):
        assert "LIST_EXTRACT" in translated[name].to_sql().upper(), name
