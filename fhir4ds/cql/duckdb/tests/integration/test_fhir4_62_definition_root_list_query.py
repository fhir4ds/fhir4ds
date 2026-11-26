"""FHIR4-62 — a DEFINITION-ROOT list-valued query must not emit a doubled alias.

CQL 1.5 §Query lets a query source be any expression, so ``( <query> ) X`` binds
``X`` to each ELEMENT of the inner query's result. The translator preserves the
inner ``return`` projection by materialising the source as a nested
``SELECT <expr> AS <alias>`` (``_query.py`` nested-query-source value
projection). When that select is then the BODY of a definition,
``CTEManager._wrap_definition_cte`` relabels every define-body column to
``value`` (downstream reads go through ``"<C>".value``) and it did so by
*appending* to whatever column was there:

    -- before: the existing SQLAlias is re-aliased, not unwrapped
    "Ids" AS MATERIALIZED (
        SELECT C.patient_id, fhirpath_text(C.resource, 'id') AS X AS value
        FROM "Condition" AS C
    )
    Parser Error: syntax error at or near "AS"

    -- after (same shape, existing alias unwrapped)
    "Ids" AS MATERIALIZED (
        SELECT C.patient_id, fhirpath_text(C.resource, 'id') AS value
        FROM "Condition" AS C
    )

Why the obvious shapes do NOT hit it (they were tried and stay clean):
``({1,2,3}) X return X`` and ``from {1,2,3} X return X`` never build the aliased
column at all (a literal-list source lowers to an array/UNNEST rather than to a
value projection), and a query-over-a-define-alias bounds the alias inside an
inner select, so no ``SELECT <expr> AS <alias>`` reaches
``_wrap_definition_cte``. The shape that does is a query whose SOURCE is a
query over a RETRIEVE with a ``return`` of a scalar projection — the branch
gated on the source query having a single non-row column
(``_query.py:4856-4891``).
"""

from __future__ import annotations

import json
import re

import duckdb

from .wasm_runtime_helpers import no_python_connection

#: The defect's signature: an already-aliased column re-aliased to ``value``.
_DOUBLED_ALIAS = re.compile(r"\bAS\s+[A-Za-z_]\w*\s+AS\s+value\b", re.IGNORECASE)

_LIBRARY = """library F62Def version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Ids": ([Condition] C return C.id) X
define "HowMany": Count(([Condition] C return C.id) X)

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "HowMany" = 3
"""

_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "Ids": "Ids",
    "HowMany": "HowMany",
}

#: ``p1`` carries three Conditions; ``p2`` carries none, so the per-patient list
#: projection is exercised for a populated AND an empty patient.
_RESOURCES = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "birthDate": "1990-01-01",
     "gender": "male"},
    {"resourceType": "Condition", "id": "c1", "subject": {"reference": "Patient/p1"},
     "verificationStatus": {"coding": [
         {"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
          "code": "confirmed"}]}},
    {"resourceType": "Condition", "id": "c2", "subject": {"reference": "Patient/p1"}},
    {"resourceType": "Condition", "id": "c3", "subject": {"reference": "Patient/p1"}},
]


def _connections():
    """Python-supplement and no-Python engines (both must bind the shape)."""
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


def _translate(cql_text: str, con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=_COLUMNS,
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for r in _RESOURCES:
        patient_ref = (r.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [r["id"], r["resourceType"], json.dumps(r), patient_ref],
        )


def test_definition_root_list_query_has_no_doubled_alias():
    """The define body's value column must be aliased ONCE (``AS value``)."""
    for ctx, label in _connections():
        with ctx as con:
            sql = _translate(_LIBRARY, con)

            hit = _DOUBLED_ALIAS.search(sql)
            assert hit is None, (
                f"{label}: the definition body re-aliased an already-aliased "
                f"column ({hit.group(0) if hit else ''}) — DuckDB rejects it with "
                f'a Parser Error near "AS"'
            )
            # The relabelled column must still be the one downstream reads.
            assert re.search(r"\bAS\s+value\b", sql), (
                f"{label}: the definition body lost its `AS value` projection"
            )
            # The inner query's RETURN projection is preserved per element: the
            # define body must extract the scalar path, not project the resource.
            assert "fhirpath_text(C.resource, 'id') AS value" in sql, (
                f"{label}: expected the inner return projection to be preserved"
            )

            # Keep DuckDB's default strictness: a shape defect must not be
            # masked by a harness flag.
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            rows = cursor.fetchall()
            names = [d[0] for d in cursor.description]
            by_patient = {row[0]: dict(zip(names[1:], row[1:])) for row in rows}

            assert set(by_patient) == {"p1", "p2"}, (
                f"{label}: patients {sorted(by_patient)}"
            )
            p1 = by_patient["p1"]
            # Values must be the inner query's RETURN projection, per element.
            # (`Ids` row order is not deterministic, so compare sorted; the
            # order-independent `HowMany`/`Numerator` pair proves the count.)
            assert sorted(p1["Ids"]) == ["c1", "c2", "c3"], (
                f"{label}: expected every Condition id, got {p1['Ids']!r}"
            )
            assert p1["HowMany"] == 3, f"{label}: expected 3, got {p1['HowMany']!r}"
            assert p1["Numerator"] is True, f"{label}: expected Numerator true"
            assert p1["Initial Population"] is True, f"{label}: initial population"

            p2 = by_patient["p2"]
            assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"
            assert p2["HowMany"] == 0, f"{label}: expected 0, got {p2['HowMany']!r}"
            assert p2["Numerator"] is False, f"{label}: expected Numerator false"
