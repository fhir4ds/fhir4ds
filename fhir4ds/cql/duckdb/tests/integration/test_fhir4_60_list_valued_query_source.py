"""FHIR4-60 — a list-valued query source binds its alias to ELEMENTS.

CQL 1.5 §Query: ``<source> <alias> <clauses>`` binds ``<alias>`` to EACH ELEMENT
of the source collection. When the source lowers to a one-row scalar LIST
projection — ``(SELECT list(<element>) FROM ...)``, the shape a fluent function
whose body is a query with a ``return`` clause produces — the translator bound
the alias to the LIST itself, so every ``<alias>.<property>`` access became a
list-valued ``fhirpath_text(JSON[], '<property>')`` call:

    -- CMS986, before the fix (Binder Error: No function matches the given
    -- name and argument types 'fhirpath_text(JSON[], STRING_LITERAL)')
    EXISTS (SELECT 1 FROM (SELECT unnest(...) AS _lt_D) AS _lt_unnest
             WHERE fhirpath_text((SELECT list(CASE WHEN ... END) FROM (...)),
                                 'verificationStatus') IS NOT NULL)

    -- after: the alias iterates the ELEMENTS and the query stays a
    -- one-column scalar list for its consumers
    EXISTS (SELECT 1 FROM (SELECT unnest((SELECT list(_lt_A) FROM
                     (SELECT unnest(<list>) AS _lt_A) AS _lt_unnest))
                   AS _lt_A) AS _lt_unnest
             WHERE fhirpath_text(_lt_A, 'verificationStatus') IS NOT NULL)

Two reachable shapes needed the fix; both are covered below:

1. ``FHIRCommon.verified(List<FHIR.Condition>)``'s body (``conditions C where
   ...``) inlined over a fluent-call ARGUMENT
   (``Encounter.encounterDiagnosis()``) — the argument arrives as a
   ``ParameterPlaceholder`` carrying the translated list into the INCLUDED
   library's body.
2. The same body expanded from the SAME library, where the argument is a nested
   ``MethodInvocation`` instead of a placeholder.

The query must also stay a ONE-COLUMN scalar: the failed prototype un-nested
into a ``patient_id``/``resource`` row projection, which scalar consumers
(``in_valueset(...)``, ``coding_matches(...)``) reject with
``Subquery returns 2 columns - expected 1``. The assertions below therefore
check the element binding AND that the SQL binds+runs on a connection that
keeps DuckDB's default ``scalar_subquery_error_on_multiple_rows``, with the
filter provably applied PER ELEMENT (two of the three conditions carry a
``verificationStatus``).
"""

from __future__ import annotations

import json
import re

import duckdb
import pytest

from .wasm_runtime_helpers import no_python_connection

VERIFICATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-ver-status"

#: ``fhirpath_text(<list-valued expression>, ...)`` — the defect's signature.
_LIST_VALUE_ARG = re.compile(r"fhirpath_text\(\s*\(SELECT\s+list\s*\(", re.IGNORECASE)
_SUBQUERY_ARG = re.compile(r"fhirpath_text\(\s*\(SELECT", re.IGNORECASE)

#: FHIR4-60 shape 1: the list-consuming body lives in an INCLUDED library, so
#: the argument reaches it as a ``ParameterPlaceholder`` (the CMS986 path).
_INCLUDED_LIBRARY = """library F60Lib version '1.0.0'
using FHIR version '4.0.1'
context Patient

/*
Mirrors FHIRCommon.verified(List<FHIR.Condition>): the query alias C must bind
to each CONDITION, not to the whole list.
*/
define fluent function verified(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus is not null
"""

#: FHIR4-60 shape 2: both functions in ONE library — the argument is expanded as
#: a nested MethodInvocation instead of a ParameterPlaceholder.
_SINGLE_LIBRARY = """library F60Main version '1.0.0'
using FHIR version '4.0.1'
context Patient

/* Mirrors CQMCommon.encounterDiagnosis: a query whose return clause resolves
   each reference to a Condition; as a query source it is one LIST per row. */
define function diagnosis(E Encounter):
  E.reasonReference D
    return singleton from (["Condition"] C where D.references(C.id))

define function verified(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus is not null

define "Numerator":
  exists (["Encounter"] E where E.status = 'finished'
    and exists (E.diagnosis().verified() V where V.id = 'c2'))

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
"""

#: The included-library variant of shape 2's main library.
_INCLUDE_USER = """library F60Use version '1.0.0'
using FHIR version '4.0.1'
include F60Lib version '1.0.0' called Lib
context Patient

define function diagnosis(E Encounter):
  E.reasonReference D
    return singleton from (["Condition"] C where D.references(C.id))

define "Numerator":
  exists (["Encounter"] E where E.status = 'finished'
    and exists (E.diagnosis().verified() V where V.id = 'c2'))

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
"""

#: Encounter ``e1`` references three Conditions; TWO carry a verificationStatus
#: and one does not, so a per-element filter keeps ``c1``/``c2`` and drops
#: ``c3``. Selecting ``V.id = 'c2'`` therefore answers TRUE only when the alias
#: iterates ELEMENTS:
#:
#:   * alias bound to the LIST  -> `fhirpath_text(JSON[], ...)` (Binder Error);
#:   * alias bound to a ROW     -> no such element, answers FALSE;
#:   * alias bound per ELEMENT  -> TRUE.
_CONDITIONS = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Encounter", "id": "e1", "status": "finished",
     "subject": {"reference": "Patient/p1"},
     "period": {"start": "2026-02-01", "end": "2026-02-05"},
     "reasonReference": [
         {"reference": "Condition/c1"},
         {"reference": "Condition/c2"},
         {"reference": "Condition/c3"},
     ]},
    {"resourceType": "Condition", "id": "c1",
     "subject": {"reference": "Patient/p1"},
     "verificationStatus": {"coding": [
         {"system": VERIFICATION_SYSTEM, "code": "confirmed"}]}},
    {"resourceType": "Condition", "id": "c2",
     "subject": {"reference": "Patient/p1"},
     "verificationStatus": {"coding": [
         {"system": VERIFICATION_SYSTEM, "code": "unconfirmed"}]}},
    {"resourceType": "Condition", "id": "c3",
     "subject": {"reference": "Patient/p1"}},
]

_COLUMNS = {"Initial Population": "Initial Population",
            "Denominator": "Denominator", "Numerator": "Numerator"}


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


def _translate(cql_text: str, columns: dict[str, str], con, includes=None) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    libraries = dict(includes or {})

    def loader(name, version=None):
        text = libraries.get(name)
        return parse_cql(text) if text else None

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=loader)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=columns,
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for r in _CONDITIONS:
        if r["resourceType"] == "Patient":
            patient_ref = r["id"]
        else:
            patient_ref = (r.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [r["id"], r["resourceType"], json.dumps(r), patient_ref],
        )


@pytest.mark.parametrize(
    "shape,cql,includes",
    [
        ("include_parameter_placeholder", _INCLUDE_USER,
         {"F60Lib": _INCLUDED_LIBRARY}),
        ("same_library_nested_call", _SINGLE_LIBRARY, None),
    ],
)
def test_list_valued_query_source_binds_alias_per_element(shape, cql, includes):
    """`conditions C where C.<prop> ...` must iterate the list's ELEMENTS."""
    for ctx, engine in _connections():
        with ctx as con:
            sql = _translate(cql, _COLUMNS, con, includes=includes)
            label = f"{shape}/{engine}"

            assert not _LIST_VALUE_ARG.search(sql), (
                f"{label}: the query alias is bound to the LIST — "
                "fhirpath_text() received a JSON array expression"
            )
            assert not _SUBQUERY_ARG.search(sql), (
                f"{label}: fhirpath_text() received a subquery instead of an "
                "element expression"
            )
            # The alias iterates an UNNESTed element (`_lt_<alias>`), which is
            # what makes `C.verificationStatus` a per-element extraction.
            assert "fhirpath_text(_lt_" in sql, (
                f"{label}: expected a per-element `_lt_<alias>` property access"
            )

            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            row = cursor.fetchone()
            assert row is not None, f"{label}: no patient row"
            pop = dict(zip([d[0] for d in cursor.description][1:], row[1:]))
            assert pop["Numerator"] is True, (
                f"{label}: the per-element filter must keep the two verified "
                f"Conditions so `V.id = 'c2'` is reachable; got {pop}"
            )
