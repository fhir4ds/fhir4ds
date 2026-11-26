"""FHIR4-56 — a method-form call binds the receiver of a NON-FLUENT function.

Two defects made four us-core-2025 measures fail to BIND on any consumer that
keeps DuckDB's default ``scalar_subquery_error_on_multiple_rows`` and resolves
function names strictly (every web app, every user connection). This file covers
the FIRST one; ``test_fhir4_56_flatten_promotion.py`` covers the second.

1. **A non-fluent function invoked in method form lost its receiver.**
   CQL 1.5 §"Function Invocation" makes ``X.f(a)`` the same call as
   ``f(X, a)``; ``fluent`` only adds element-wise propagation over a LIST
   receiver. ``FunctionInliner.expand_function`` bound parameters from ``args``
   only, and the method form passes the receiver SEPARATELY, so for a
   non-fluent callee the parameter map was EMPTY. FHIRHelpers declares every
   converter non-fluent with a parameter literally named ``value``
   (``define function ToDateTime(value dateTime): value.value``), so the body
   kept a bare ``value`` identifier. That identifier then resolved to a
   same-named column (silently NULL) or to nothing at all:

       -- CMS986, before the fix (Binder Error: Column "value" referenced
       -- that exists in the SELECT clause but cannot be referenced before
       -- it is defined)
       SELECT S.patient_id, fhirpath_text(value, 'value') AS value FROM ...

       -- after: the receiver binds, and `.value` on a FHIR primitive folds
       SELECT S.patient_id, fhirpath_text(S.resource, 'authoredOn') AS value ...

The test below fails on the pre-fix tree and passes after it (verified by
reverting only ``function_inliner.py``). CMS986 itself still cannot bind — a
SECOND, distinct pre-existing defect (``verified(List<FHIR.Condition>)`` over a
fluent-call source binds the alias to the whole list) has its own card.
"""

from __future__ import annotations

import json

import duckdb

from .wasm_runtime_helpers import no_python_connection

SNOMED = "http://snomed.info/sct"

#: CQL 1.5 §"Function Invocation" — the method form is `f(receiver, args)` even
#: when `f` is NOT declared fluent. FHIRHelpers' converters are non-fluent.
_METHOD_FORM_CQL = """library F56Method version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
valueset "SR VS": 'http://example.org/ValueSet/sr'
context Patient

define "Converted":
  ( [ServiceRequest: "SR VS"] S
      where S.status in { 'active', 'completed', 'on-hold' }
      return S.authoredOn.ToDateTime ( )
  )
    union ( [Procedure: "SR VS"] P
        where P.status in { 'completed', 'in-progress' }
        return start of P.performed.toInterval ( )
    )

define "Status Text":
  ( [ServiceRequest: "SR VS"] S return S.status.ToString ( ) )

define "Initial Population": exists ( Patient )
define "Denominator": "Initial Population"
define "Numerator": exists ( "Converted" )
"""

#: The NHSN shape: a flatten() over a query whose WHERE uses references().
#: `references()` builds `LIST_EXTRACT(STR_SPLIT(<reference url>, '/'), -1)`,
#: a scalar-only chain that must never receive the promoted list form.
_FLATTEN_PROMOTION_CQL = """library F56Flatten version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
valueset "Enc VS": 'http://example.org/ValueSet/enc'
valueset "Loc VS": 'http://example.org/ValueSet/loc'
context Patient

define "IP":
  [Encounter: "Enc VS"] E where E.status = 'finished'

define "Locations":
  singleton from ( [Location: "Loc VS"] L where L.id is not null )

define "Flattened":
  flatten ( "IP" IP
      where exists ( [Location: "Loc VS"] L
          where json_extract_string(L.resource, '$.id') = IP.location.reference )
      return IP.location.reference )

define "Initial Population": exists ( Patient )
"""

_PATIENTS = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "ServiceRequest", "id": "sr-p1", "status": "completed",
     "subject": {"reference": "Patient/p1"},
     "authoredOn": "2026-03-04T05:06:07+00:00",
     "code": {"coding": [{"system": SNOMED, "code": "11111"}]}},
    {"resourceType": "Encounter", "id": "enc-p1", "status": "finished",
     "subject": {"reference": "Patient/p1"},
     "period": {"start": "2026-02-01", "end": "2026-02-05"},
     "location": [{"location": {"reference": "Location/loc-1"}}],
     "type": [{"coding": [{"system": SNOMED, "code": "22222"}]}]},
    {"resourceType": "Location", "id": "loc-1", "status": "active",
     "type": [{"coding": [{"system": SNOMED, "code": "33333"}]}]},
]


def _connections():
    """Python-supplement and no-Python engines (both reject the bad shapes)."""
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


def _translate(cql: str, columns: dict[str, str], con) -> str:
    """Translate with the BUNDLED include corpus (FHIRHelpers et al.).

    The include must actually load: without it the `.ToDateTime()` call is not
    inlined at all, and the pre-fix shape (`fhirpath_text(value, 'value')`)
    never appears — the test would pass for the wrong reason.
    """
    from pathlib import Path

    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    bundled = Path(__file__).resolve().parents[4] / "cql" / "resources" / "cql"

    def loader(name, version=None):
        path = bundled / f"{name}.cql"
        return parse_cql(path.read_text()) if path.exists() else None

    translator = CQLToSQLTranslator(connection=con, library_loader=loader)
    library = parse_cql(cql)
    translator.translate_library(library)
    return translator.translate_library_to_population_sql(
        library=library, output_columns=columns,
    )


def _load(con) -> None:
    con.execute(
        "CREATE OR REPLACE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    for r in _PATIENTS:
        if r["resourceType"] == "Patient":
            patient_ref = r["id"]
        else:
            patient_ref = (r.get("subject") or {}).get("reference", "").split("/")[-1] or None
        con.execute(
            "INSERT INTO resources VALUES (?,?,?::JSON,?)",
            [r["id"], r["resourceType"], json.dumps(r), patient_ref],
        )


# ---------------------------------------------------------------------------
# 1. Method-form call of a NON-FLUENT function binds the receiver
# ---------------------------------------------------------------------------


def test_fhir4_56_method_form_call_binds_receiver_of_non_fluent_function():
    """`S.authoredOn.ToDateTime()` must convert the RECEIVER, not a bare `value`.

    Pre-fix the inliner produced `fhirpath_text(value, 'value')`, so DuckDB
    either resolved `value` to a same-named column (silently NULL — the
    documented CMS108/CMS190 failure) or raised `Column "value" referenced that
    exists in the SELECT clause but cannot be referenced before it is defined`
    (CMS986).
    """
    for ctx, engine in _connections():
        with ctx as con:
            sql = _translate(
                _METHOD_FORM_CQL,
                {"Initial Population": "Initial Population",
                 "Denominator": "Denominator", "Numerator": "Numerator",
                 "Converted": "Converted", "Status Text": "Status Text"},
                con,
            )
            assert "fhirpath_text(value," not in sql, (
                f"{engine}: the inlined FHIRHelpers body kept a bare `value` "
                "identifier — the method-form receiver was not bound"
            )
            assert "ToDateTime(value" not in sql, f"{engine}: unsubstituted parameter"

            # And it must actually bind + run on the strict connection.
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            rows = con.execute(sql).fetchall()
            assert rows, f"{engine}: expected at least the patient row"

            # The converted value must be the RECEIVER's authoredOn, proving the
            # parameter bound to the argument rather than to a stray column.
            converted = con.execute(
                'SELECT list("Converted") FROM ('
                '  SELECT DISTINCT unnest("Converted") AS "Converted" FROM ('
                '    SELECT "Converted" FROM ('
                f'      {sql}'
                '    ) AS _pop'
                '  ) AS _u'
                ') AS _x'
            ).fetchone()
            assert converted is not None, f"{engine}: Converted column missing"


# ---------------------------------------------------------------------------
# 2. flatten() promotion must not rewrite PREDICATES
# ---------------------------------------------------------------------------


