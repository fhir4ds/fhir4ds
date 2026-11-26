"""FHIR4-65 — membership over a MULTI-ROW list-valued define must test the list.

CQL 1.5 §10.9 In / §10.1 Contains apply to a LIST operand. A define whose body
is a query with a ``return`` clause

    define "Ids": ([Condition] C return C.id) X

materializes as ``RowShape.PATIENT_MULTI_VALUE`` — ONE ROW PER ELEMENT, with
the element in ``meta.value_column``. The generic SCALAR identifier lookup
consumed such a define as

    (SELECT sub.value FROM "Ids" AS sub
      WHERE sub.patient_id = _pt.patient_id LIMIT 1)

so membership inspected exactly ONE element. With Conditions c1/c2/c3 on p1:

    Ids    = ['c2', 'c1', 'c3']      (row order is not a CQL guarantee)
    'c1' in "Ids"   ->  FALSE        WRONG, c1 IS in Ids
    'c2' in "Ids"   ->  true         right by luck: c2 happened to be row #1

That is a SILENT WRONG ANSWER — matching row order makes the bug look like a
pass, and a shifted row order makes it look like a cross-engine parity break
(both engines consumed the same one row). The fix belongs at the CONSUMER site
(membership lowering), NOT in identifier resolution: coercing every list-typed
define reference to a list breaks DQM population SQL (patient_id / GROUP BY).

The tests below pin the whole membership surface over the define:
  * ``in`` with a NON-FIRST element (the defect's signature),
  * ``in`` with a first element and with an absent element,
  * the mirrored ``contains`` direction (lowered separately),
  * a NULL/absent element (CQL §10.9 null-element rule via the contains macro),
  * a patient with NO Conditions (empty list),
  * the generated SQL: no ``LIMIT 1`` scalar consumption of this define.
"""

from __future__ import annotations

import json
import re

import duckdb

from .wasm_runtime_helpers import no_python_connection

#: The defect's signature: a scalar consumption of the define's row CTE.
_LIMIT_ONE_CONSUMPTION = re.compile(
    r'FROM\s+"Ids"\s+AS\s+sub\b[^)]*\bLIMIT\s+1\b', re.IGNORECASE
)

_LIBRARY = """library F65Membership version '1.0.0'
using FHIR version '4.0.1'
include Common version '1.0.0' called Common
context Patient

define "Ids": ([Condition] C return C.id) X
define "Codes": ([Condition] C return C.verificationStatus.coding.code) X

define "HasC1": 'c1' in "Ids"
define "HasC2": 'c2' in "Ids"
define "HasZZ": 'zz' in "Ids"
define "HasNullOnIds": null in "Ids"
define "HasNullOnCodes": null in "Codes"
define "ContainsC1": "Ids" contains 'c1'
define "ContainsZZ": "Ids" contains 'zz'
define "InWhereClause": Count(([Condition] C where 'c1' in "Ids"))

// The same defect one level over: an included library's list-valued define is
// registered under its DOTTED name (CTE `"Common.SharedIds"`) and had the
// identical one-row lowering.
define "QualifiedC1": 'c1' in Common."SharedIds"
define "QualifiedContainsC2": Common."SharedIds" contains 'c2'

define "Initial Population": exists (Patient)
define "Denominator": "Initial Population"
define "Numerator": "HasC1"
"""

#: Included library served by the in-memory library_loader. It declares the
#: same multi-row element define as the main library.
_INCLUDED_LIBRARIES = {
    "Common": """library Common version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "SharedIds": ([Condition] C return C.id) X
""",
}

_COLUMNS = {
    "Initial Population": "Initial Population",
    "Denominator": "Denominator",
    "Numerator": "Numerator",
    "Ids": "Ids",
    "Codes": "Codes",
    "HasC1": "HasC1",
    "HasC2": "HasC2",
    "HasZZ": "HasZZ",
    "HasNullOnIds": "HasNullOnIds",
    "HasNullOnCodes": "HasNullOnCodes",
    "ContainsC1": "ContainsC1",
    "ContainsZZ": "ContainsZZ",
    "QualifiedC1": "QualifiedC1",
    "QualifiedContainsC2": "QualifiedContainsC2",
    "InWhereClause": "InWhereClause",
}

#: p1 carries three Conditions, c1 (with a verificationStatus coding), c2 and
#: c3 (no verificationStatus ⇒ a NULL element in `Codes`). p2 carries none, so
#: the empty-list projection is exercised for the same defines.
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


def _translate(cql_text: str, con) -> str:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    def library_loader(alias: str, version=None):
        text = _INCLUDED_LIBRARIES.get(alias)
        return parse_cql(text) if text is not None else None

    library = parse_cql(cql_text)
    translator = CQLToSQLTranslator(connection=con, library_loader=library_loader)
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


def _run_both_engines():
    """Yield ``(label, sql, by_patient)`` for each engine."""
    for ctx, label in _connections():
        with ctx as con:
            sql = _translate(_LIBRARY, con)
            # Keep DuckDB's default strictness: a shape defect must not be
            # masked by a harness flag (FHIR4-48/53 doctrine).
            con.execute("SET scalar_subquery_error_on_multiple_rows=true")
            _load(con)
            cursor = con.execute(sql)
            names = [d[0] for d in cursor.description]
            by_patient = {row[0]: dict(zip(names[1:], row[1:])) for row in cursor.fetchall()}
            yield label, sql, by_patient


def test_membership_over_multi_row_define_uses_the_whole_list():
    """`x in <multi-row define>` must find elements that are not row #1."""
    for label, _sql, by_patient in _run_both_engines():
        assert set(by_patient) == {"p1", "p2"}, f"{label}: patients {sorted(by_patient)}"
        p1 = by_patient["p1"]
        # The list itself: every Condition id, order not a CQL guarantee.
        assert sorted(p1["Ids"]) == ["c1", "c2", "c3"], (
            f"{label}: expected every Condition id, got {p1['Ids']!r}"
        )
        # THE DEFECT: 'c1' is a NON-FIRST element. A one-row consumption can
        # only answer true here by luck (or on shifted data).
        assert p1["HasC1"] is True, (
            f"{label}: 'c1' in Ids must be TRUE — c1 IS an element of "
            f"{sorted(p1['Ids'])!r}; a FALSE here means membership inspected "
            f"only one row"
        )
        assert p1["HasC2"] is True, f"{label}: 'c2' in Ids must be TRUE"
        assert p1["HasZZ"] is False, f"{label}: 'zz' is not in Ids"
        # Member alignment inside a query WHERE clause (patient correlation of
        # the materialized list must not be lost): all three Conditions match.
        assert p1["InWhereClause"] == 3, (
            f"{label}: expected 3 matching Conditions, got {p1['InWhereClause']!r}"
        )


def test_contains_direction_over_multi_row_define_uses_the_whole_list():
    """`<define> contains x` is lowered separately and must match `in`."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["ContainsC1"] is True, (
            f"{label}: Ids contains 'c1' must be TRUE (c1 is an element of "
            f"{sorted(p1['Ids'])!r})"
        )
        assert p1["ContainsZZ"] is False, f"{label}: Ids does not contain 'zz'"


def test_included_library_list_define_membership_uses_the_whole_list():
    """The qualified (included-library) spelling has the same semantics."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        assert p1["QualifiedC1"] is True, (
            f"{label}: 'c1' in Common.\"SharedIds\" must be TRUE "
            f"(c1 is an element of {sorted(p1['Ids'])!r})"
        )
        assert p1["QualifiedContainsC2"] is True, (
            f"{label}: Common.\"SharedIds\" contains 'c2' must be TRUE"
        )
        p2 = by_patient["p2"]
        assert p2["QualifiedC1"] is False, f"{label}: p2 has no c1"
        assert p2["QualifiedContainsC2"] is False, f"{label}: p2 has no c2"


def test_null_and_absent_elements_over_multi_row_define():
    """NULL elements are members (§10.9); an empty list contains nothing."""
    for label, _sql, by_patient in _run_both_engines():
        p1 = by_patient["p1"]
        p2 = by_patient["p2"]
        # `Codes` projects verificationStatus.coding.code, absent on c2/c3 ⇒
        # NULL elements. CQL 1.5 §10.9: `null in L` is true iff L has a null
        # element (the contains macro the list paths route through).
        assert sorted(p2.get("Codes") or []) == [], (
            f"{label}: p2 has no Conditions, got {p2.get('Codes')!r}"
        )
        assert p1["HasNullOnCodes"] is True, (
            f"{label}: the Codes list holds NULL elements (c2/c3 have no "
            f"verificationStatus), so `null in Codes` must be TRUE; got "
            f"{p1['HasNullOnCodes']!r}"
        )
        assert p1["HasNullOnIds"] is False, (
            f"{label}: Ids has no NULL elements, so `null in Ids` is FALSE"
        )


def test_patient_with_no_conditions_over_multi_row_define():
    """An empty element list is a member of nothing and contains nothing."""
    for label, _sql, by_patient in _run_both_engines():
        p2 = by_patient["p2"]
        assert not p2["Ids"], f"{label}: p2 has no Conditions, got {p2['Ids']!r}"
        assert p2["HasC1"] is False, f"{label}: p2 has no c1"
        assert p2["HasC2"] is False, f"{label}: p2 has no c2"
        assert p2["ContainsC1"] is False, f"{label}: p2's Ids contains nothing"
        assert p2["HasNullOnCodes"] is False, (
            f"{label}: an EMPTY list contains no null element"
        )
        assert p2["InWhereClause"] == 0, (
            f"{label}: p2 matches no Conditions, got {p2['InWhereClause']!r}"
        )


def test_no_limit_one_scalar_consumption_of_the_multi_row_define():
    """The generated SQL must not scalarize the define for membership."""
    for label, sql, _by_patient in _run_both_engines():
        hit = _LIMIT_ONE_CONSUMPTION.search(sql)
        assert hit is None, (
            f"{label}: membership consumed the row CTE as a scalar "
            f"({hit.group(0)[:120]!r}) — a list operand must be materialized "
            f"per patient, not truncated with LIMIT 1"
        )
        # Positive control: the membership does reach a list comparison over
        # the aggregated define rows (not just "no LIMIT anywhere").
        assert re.search(
            r'list\(_lst_src\.value\)\s+FROM\s+"Ids"\s+AS\s+_lst_src', sql,
            re.IGNORECASE,
        ), f"{label}: expected the define's rows to be aggregated into a list"
        assert "CQLListContainsEq" in sql, (
            f"{label}: membership must route through the CQL list-contains macro"
        )
