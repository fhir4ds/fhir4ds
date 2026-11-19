"""CQL 2.0 model definitions (campaign cql20_spec_campaign, chunk CQL20-E).

Multi-filter retrieves (FHIR-31397), ``define type`` (FHIR-34014 named types),
``define context`` and ``define conversion`` — the CQL 2.0 "Defining Models"
surface (https://cql.hl7.org/03-developersguide.html#defining-models).

Multi-filter retrieves are tested END-TO-END through population SQL with real
FHIR resources on both the Python-fallback and native C++ registrations (the
CQL-18 lesson: static-literal probes hide dynamic-path breakage).

Ground truth for the filter semantics: CQL 2.0 Logical Specification,
Retrieve.codeFilter/otherFilter — "When multiple codeFilters are present,
they are all applied (i.e. ANDed)." (FHIR-31397 resolution documents the ELM
multi-filter capability; the author-facing surface is the comma-separated
additional filters in the retrieve.)
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.valueset import (
    createEquivalentValuesetMembershipUdf,
    createValuesetMembershipUdf,
)
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.parser.parser import ParseError
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql

VS_URL = "http://example.org/fhir/ValueSet/vs20e"
VS_STATUS_URL = "http://example.org/fhir/ValueSet/vs20e-active"

_CACHE = {
    VS_URL: {
        ("http://loinc.org", "8867-4"),
        ("http://snomed.info/sct", "195967001"),
    },
    VS_STATUS_URL: {
        ("http://terminology.hl7.org/CodeSystem/condition-clinical", "active"),
        ("http://terminology.hl7.org/CodeSystem/condition-clinical", "recurrence"),
    },
}


def _py_con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    con.remove_function("in_valueset")
    con.create_function("in_valueset", createValuesetMembershipUdf(_CACHE), null_handling="special")
    con.remove_function("cql_equivalent_in_valueset")
    con.create_function(
        "cql_equivalent_in_valueset",
        createEquivalentValuesetMembershipUdf(_CACHE),
        null_handling="special",
    )
    return con


def _cpp_con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    con.execute("SELECT cql_valueset_cache_clear()")
    for url, entries in _CACHE.items():
        for system, code in entries:
            con.execute("SELECT cql_valueset_cache_add(?, ?, ?)", [url, system, code])
    return con


def _both_engines():
    return _py_con(), _cpp_con()


def _population_setup(con, resources):
    con.execute(
        "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
        "resource JSON, patient_ref VARCHAR)"
    )
    con.execute("DELETE FROM resources")
    patient = {"resourceType": "Patient", "id": "p1", "patient_ref": "p1"}
    for r in [patient, *resources]:
        con.execute(
            "INSERT INTO resources VALUES (?, ?, ?::JSON, ?)",
            [r["id"], r["resourceType"], json.dumps(r), r.get("patient_ref", "p1")],
        )


def _run_population(cql: str, resources: list, columns: dict) -> dict:
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql), output_columns=columns,
    )
    py, cpp = _both_engines()
    try:
        results = {}
        for name, con in (("py", py), ("cpp", cpp)):
            _population_setup(con, resources)
            cur = con.execute(sql)
            row = cur.fetchone()
            results[name] = dict(zip([d[0] for d in cur.description], row))
        return results
    finally:
        py.close()
        cpp.close()


# ---------------------------------------------------------------------------
# Multi-filter retrieves — FHIR-31397
# ---------------------------------------------------------------------------

class TestMultiFilterRetrieves:
    def _condition(self, cid: str, code: str, system: str, clinical_status: str) -> dict:
        return {
            "resourceType": "Condition", "id": cid,
            "code": {"coding": [{"system": system, "code": code}]},
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": clinical_status,
                }]
            },
            "subject": {"reference": "Patient/p1"},
            "patient_ref": "p1",
        }

    def test_two_code_filters_are_anded_end_to_end(self):
        """`[Condition: code in "VS", clinicalStatus in "ActiveVS"]` keeps only
        resources matching BOTH filters (logical spec: multiple filters are
        ANDed)."""
        cql = f"""library MF20A version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
context Patient
define BothCount: Count([Condition: code in "VS", clinicalStatus in "ActiveVS"])
define CodeOnlyCount: Count([Condition: code in "VS"])
"""
        resources = [
            # Matches both filters.
            self._condition("c1", "8867-4", "http://loinc.org", "active"),
            # Matches the code filter only — must be excluded by the
            # clinicalStatus filter.
            self._condition("c2", "195967001", "http://snomed.info/sct", "inactive"),
            # Matches the status filter only — excluded by the code filter.
            self._condition("c3", "nope-code", "http://loinc.org", "active"),
        ]
        results = _run_population(
            cql, resources,
            {"BothCount": "BothCount", "CodeOnlyCount": "CodeOnlyCount"},
        )
        for engine in ("py", "cpp"):
            assert results[engine]["BothCount"] == 1, (engine, results[engine])
            assert results[engine]["CodeOnlyCount"] == 2, (engine, results[engine])

    def test_primary_terminology_without_path_composes_with_filter(self):
        """`[Condition: "VS", clinicalStatus in "ActiveVS"]` — the primary
        filter may use the default code path (no explicit path)."""
        cql = f"""library MF20B version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
context Patient
define BothCount: Count([Condition: "VS", clinicalStatus in "ActiveVS"])
"""
        resources = [
            self._condition("c1", "8867-4", "http://loinc.org", "active"),
            self._condition("c2", "8867-4", "http://loinc.org", "recurrence"),
            self._condition("c3", "8867-4", "http://loinc.org", "inactive"),
        ]
        results = _run_population(cql, resources, {"BothCount": "BothCount"})
        for engine in ("py", "cpp"):
            assert results[engine]["BothCount"] == 2, (engine, results[engine])

    def test_three_filters_and_tilde_in_comparator(self):
        """Three filters ANDed, including a `~in` equivalent-membership
        additional filter (case-mismatched code matches under equivalence)."""
        cql = f"""library MF20C version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
codesystem "SNOMED": 'http://snomed.info/sct'
codesystem "VER": 'http://terminology.hl7.org/CodeSystem/condition-ver-status'
code "Confirmed": 'confirmed' from "VER"
context Patient
define AllThree: exists (
  [Condition: code in "VS", clinicalStatus in "ActiveVS", verificationStatus ~contains "Confirmed"]
)
"""
        def cond(cid, code, clin, verif):
            c = self._condition(cid, code, "http://loinc.org", clin)
            c["verificationStatus"] = {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": verif,
                }]
            }
            return c

        resources = [
            # verificationStatus case-flipped: matches under ~contains
            # equivalence but not exact.
            cond("c1", "8867-4", "active", "CONFIRMED"),
        ]
        results = _run_population(cql, resources, {"AllThree": "AllThree"})
        for engine in ("py", "cpp"):
            assert results[engine]["AllThree"] is True, (engine, results[engine])

    def test_additional_filter_with_declared_code_equality(self):
        """`[Condition: code in "VS", clinicalStatus = "ActiveCode"]` — an
        additional `=` filter against a DECLARED CODE resolves to direct-code
        membership on the property."""
        cql = f"""library MF20D version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
codesystem "CLIN": 'http://terminology.hl7.org/CodeSystem/condition-clinical'
code "ActiveCode": 'active' from "CLIN"
context Patient
define HitCount: Count([Condition: code in "VS", clinicalStatus = "ActiveCode"])
"""
        resources = [
            self._condition("c1", "8867-4", "http://loinc.org", "active"),
            self._condition("c2", "8867-4", "http://loinc.org", "inactive"),
        ]
        results = _run_population(cql, resources, {"HitCount": "HitCount"})
        for engine in ("py", "cpp"):
            assert results[engine]["HitCount"] == 1, (engine, results[engine])

    def test_multi_filter_retrieve_inside_query_where(self):
        """A multi-filter retrieve used as a query source with an explicit
        WHERE clause composes (filter predicates AND the where)."""
        cql = f"""library MF20E version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
context Patient
define FilteredCount: Count(
  [Condition: code in "VS", clinicalStatus in "ActiveVS"] C where C.id != 'c1'
)
"""
        resources = [
            self._condition("c1", "8867-4", "http://loinc.org", "active"),
            self._condition("c2", "195967001", "http://snomed.info/sct", "recurrence"),
        ]
        results = _run_population(cql, resources, {"FilteredCount": "FilteredCount"})
        for engine in ("py", "cpp"):
            assert results[engine]["FilteredCount"] == 1, (engine, results[engine])

    def test_distinct_ctes_for_distinct_filter_sets(self):
        """Two retrieves over the same type+valueset that differ only in
        additional filters must get DISTINCT CTEs (both filter sets applied,
        no cross-contamination in one library)."""
        cql = f"""library MF20F version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
context Patient
define WithActive: Count([Condition: code in "VS", clinicalStatus in "ActiveVS"])
define NoActive: Count([Condition: code in "VS"])
"""
        resources = [
            self._condition("c1", "8867-4", "http://loinc.org", "active"),
            self._condition("c2", "8867-4", "http://loinc.org", "inactive"),
        ]
        results = _run_population(
            cql, resources, {"WithActive": "WithActive", "NoActive": "NoActive"},
        )
        for engine in ("py", "cpp"):
            assert results[engine]["WithActive"] == 1, (engine, results[engine])
            assert results[engine]["NoActive"] == 2, (engine, results[engine])

    def test_parser_requires_path_for_additional_filters(self):
        """An additional filter must be `path comparator terminology`; a bare
        terminology after the comma is a ParseError (the grammar's
        comma-separated items carry explicit [property][comparator][value]
        shape — Logical Spec CodeFilterElement)."""
        cql = f"""library MF20G version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "Other": '{VS_STATUS_URL}'
context Patient
define Probe: exists([Condition: code in "VS", "Other"])
"""
        from fhir4ds.cql.errors import TranslationError

        with pytest.raises((ParseError, TranslationError)):
            CQLToSQLTranslator().translate_library_to_population_sql(parse_cql(cql))

    def test_ast_carries_additional_filters(self):
        """Parser-level shape probe: the Retrieve AST node carries the
        additional filters (property, comparator, terminology)."""
        lib = parse_cql(
            f"""library MF20H version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
context Patient
define Probe: [Condition: code in "VS", clinicalStatus in "ActiveVS"]
"""
        )
        (define,) = [d for d in lib.statements if getattr(d, "name", "") == "Probe"]
        retrieve = define.expression
        assert type(retrieve).__name__ == "Retrieve"
        filters = getattr(retrieve, "additional_filters", None)
        assert filters, "Retrieve.additional_filters missing"
        assert len(filters) == 1
        assert filters[0].property == "clinicalStatus"
        assert filters[0].comparator == "in"
        assert getattr(filters[0].terminology, "name", None) == "ActiveVS"
