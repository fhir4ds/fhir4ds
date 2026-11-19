"""CQL 2.0 terminological membership (campaign cql20_spec_campaign, chunk CQL20-C).

Dual-backend parity tests for the CQL 2.0 EquivalentIn / EquivalentContains
terminological overloads (FHIR-31675 / FHIR-33247 / FHIR-31392):

  * ``Code/Concept/String/List ~in ValueSet`` and the converse
    ``ValueSet ~contains <code>`` — equivalent-based membership (Code `~`
    semantics: code + system compared case-insensitively with whitespace
    normalization), distinct from the 1.5 ``in`` exact-match surface.
  * ``Code ~in CodeSystem`` / ``CodeSystem ~contains Code`` — the CodeSystem
    static fold equivalence-normalizes the system element.
  * Retrieve comparators (FHIR-31392): ``[X: code ~in "VS"]`` (equivalent
    ValueSet membership on the code path) and
    ``[X: path ~contains "DeclaredCode"]`` (the element at the path
    equivalently-contains the declared code) — end-to-end population SQL
    with real FHIR resources (the CQL-18 lesson: static-literal probes hide
    dynamic-path breakage).

Semantics ground truth: CQL 2.0 (R2 STU 1) Appendix B, Clinical Operators —
EquivalentContains (CodeSystem/ValueSet), EquivalentIn (CodeSystem/ValueSet),
https://cql.hl7.org/09-b-cqlreference.html.

Null semantics (spec): "If the code argument is null, the result is false."
An unresolved/unloaded ValueSet reference surfaces as SQL NULL (membership
unknown, three-valued logic) consistent with the pinned in_valueset doctrine
(CQL-21 EXPLORER).
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
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql

VS_URL = "http://example.org/fhir/ValueSet/vs20c"
VS_MULTI_URL = "http://example.org/fhir/ValueSet/vs20c-multi"
VS_UNLOADED_URL = "http://example.org/fhir/ValueSet/vs20c-unloaded"

# Case-mixed cache entries: the EQUIVALENT surface must match
# '8867-4'-vs-'8867-4'-style case/whitespace variants; the exact `in`
# surface must not.
_CACHE = {
    VS_URL: {
        ("http://loinc.org", "8867-4"),
        ("http://loinc.org", "HearTRate"),
        ("http://snomed.info/sct", "  DiabeTes "),
    },
    VS_MULTI_URL: {
        ("http://loinc.org", "12345"),
        ("http://snomed.info/sct", "12345"),
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


def _translate(expression: str) -> str:
    result = translate_cql(f"library Probe version '1.0.0'\ndefine Probe: {expression}")
    sql = result["Probe"]
    return str(sql.to_sql() if hasattr(sql, "to_sql") else sql)


def _both_engines():
    return _py_con(), _cpp_con()


# ---------------------------------------------------------------------------
# EquivalentIn / EquivalentContains (ValueSet) — FHIR-31675 / FHIR-33247
# ---------------------------------------------------------------------------

VALUESET_EQUIVALENCE_CASES = [
    # String overload: case-insensitive match against the cache entry.
    ("'8867-4' ~in \"VS\"", True),
    ("'heartrate' ~in \"VS\"", True),  # cache holds 'HearTRate'
    ("'8867  -4' ~in \"VS\"", False),  # whitespace INSIDE the code is normalized, not stripped
    # Code overload: equivalent code+system (case/whitespace variants of
    # code and/or system match).
    ("Code { code: '8867-4', system: 'http://loinc.org' } ~in \"VS\"", True),
    ("Code { code: '8867-4', system: 'HTTP://LOINC.ORG' } ~in \"VS\"", True),
    ("Code { code: '  diabetes ', system: 'http://snomed.info/sct' } ~in \"VS\"", True),
    ("Code { code: 'HEARTRATE', system: 'http://loinc.org' } ~in \"VS\"", True),
    # Equivalent code but system genuinely absent from the ValueSet → false.
    ("Code { code: '8867-4', system: 'http://example.org/other' } ~in \"VS\"", False),
    # Spec: "If the code argument is null, the result is false."
    ("null as String ~in \"VS\"", False),
    ("null as Code ~in \"VS\"", False),
    # Converse operator (ValueSet ~contains) — "A ~in B will always result
    # in the same value as B ~contains A".
    ("\"VS\" ~contains '8867-4'", True),
    ("\"VS\" ~contains Code { code: '8867-4', system: 'http://loinc.org' }", True),
    ("\"VS\" ~contains Code { code: '9999-9', system: 'http://loinc.org' }", False),
    ("\"VS\" ~contains null as String", False),
    # List<Code> overload: any equivalent member.
    ("{ Code { code: '9999-9', system: 'http://loinc.org' }, Code { code: '8867-4', system: 'http://loinc.org' } } ~in \"VS\"", True),
    # Concept overload: any code of the concept equivalently in the set.
    ("Concept { codes: { Code { code: '9999-9', system: 'http://loinc.org' }, Code { code: '  diabetes ', system: 'http://snomed.info/sct' } } } ~in \"VS\"", True),
    ("Concept { codes: { Code { code: '9999-9', system: 'http://loinc.org' } } } ~in \"VS\"", False),
    # Unloaded ValueSet → membership unknown (SQL NULL), pinned doctrine.
    ("'8867-4' ~in \"Unloaded\"", None),
]


class TestEquivalentInValueSet:
    @pytest.mark.parametrize("expression,expected", VALUESET_EQUIVALENCE_CASES)
    def test_values_and_dual_backend_parity(self, expression, expected):
        cql = f"""library VS20C version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "Unloaded": '{VS_UNLOADED_URL}'
context Unfiltered
define Probe: {expression}
"""
        py, cpp = _both_engines()
        try:
            result = translate_cql(cql)
            sql = result["Probe"].to_sql()
            py_val = py.execute(f"SELECT ({sql})").fetchone()[0]
            cpp_val = cpp.execute(f"SELECT ({sql})").fetchone()[0]
            assert py_val == cpp_val == expected, (
                f"{expression}: py={py_val!r} cpp={cpp_val!r} expected={expected!r}"
            )
        finally:
            py.close()
            cpp.close()

    def test_equivalent_membership_differs_from_exact_in(self):
        """The 2.0 `~in` surface must be equivalence-based while the 1.5 `in`
        keeps exact matching — the distinction the chunk exists for."""
        cql = f"""library VS20D version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
context Unfiltered
define EquivIn: 'heartrate' ~in "VS"
define ExactIn: 'heartrate' in "VS"
define EquivContains: "VS" ~contains 'HEARTRATE'
"""
        py, cpp = _both_engines()
        try:
            result = translate_cql(cql)
            for con in (py, cpp):
                row = con.execute(
                    f"SELECT ({result['EquivIn'].to_sql()}), "
                    f"({result['ExactIn'].to_sql()}), "
                    f"({result['EquivContains'].to_sql()})"
                ).fetchone()
                assert row == (True, False, True)
        finally:
            py.close()
            cpp.close()

    def test_string_overload_multi_system_ambiguity_is_null(self):
        """Spec (ValueSet String overload): the code present in multiple code
        systems makes the operation ambiguous → SQL NULL (3VL), mirroring the
        exact-match UDF doctrine."""
        cql = f"""library VS20E version '1.0.0'
using FHIR version '4.0.1'
valueset "Multi": '{VS_MULTI_URL}'
context Unfiltered
define Probe: '12345' ~in "Multi"
"""
        py, cpp = _both_engines()
        try:
            result = translate_cql(cql)
            sql = result["Probe"].to_sql()
            assert py.execute(f"SELECT ({sql})").fetchone()[0] is None
            assert cpp.execute(f"SELECT ({sql})").fetchone()[0] is None
        finally:
            py.close()
            cpp.close()

    def test_dynamic_fhir_path_equivalent_membership_population_sql(self):
        """Dynamic FHIR code path (CQL-18 lesson): `O.code ~in "VS"` on a
        retrieve row must route the ROW's coding through the equivalence UDF
        end-to-end through population SQL."""
        cql = f"""library VS20F version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
context Patient
define Hit: exists ([Observation] O where O.code ~in "VS")
define Miss: exists ([Observation] O where 'zzz-nope' ~in "VS")
"""
        sql = CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql), output_columns={"Hit": "Hit", "Miss": "Miss"},
        )
        obs = json.dumps({
            "resourceType": "Observation", "id": "o1",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
            "subject": {"reference": "Patient/p1"},
        })
        patient = json.dumps({"resourceType": "Patient", "id": "p1"})
        py, cpp = _both_engines()
        try:
            for con in (py, cpp):
                con.execute(
                    "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
                    "resource JSON, patient_ref VARCHAR)"
                )
                con.execute("DELETE FROM resources")
                con.execute(
                    "INSERT INTO resources VALUES ('p1', 'Patient', ?::JSON, 'p1')",
                    [patient],
                )
                con.execute(
                    "INSERT INTO resources VALUES ('o1', 'Observation', ?::JSON, 'p1')",
                    [obs],
                )
                row = con.execute(sql).fetchone()
                values = dict(zip([d[0] for d in con.execute(sql).description], row))
                assert values["Hit"] is True
                assert values["Miss"] is False
        finally:
            py.close()
            cpp.close()


# ---------------------------------------------------------------------------
# EquivalentIn / EquivalentContains (CodeSystem)
# ---------------------------------------------------------------------------

class TestEquivalentInCodeSystem:
    def test_code_system_fold_is_equivalence_based(self):
        """Static Code ~in CodeSystem folds with the system element compared
        case-insensitively (Code `~` semantics); the exact `in` stays
        case-sensitive."""
        cql = """library CS20C version '1.0.0'
using FHIR version '4.0.1'
codesystem "SNOMED": 'http://snomed.info/sct'
context Unfiltered
define EquivIn: Code { code: 'x', system: 'HTTP://SNOMED.INFO/SCT' } ~in "SNOMED"
define ExactIn: Code { code: 'x', system: 'HTTP://SNOMED.INFO/SCT' } in "SNOMED"
define EquivContains: "SNOMED" ~contains Code { code: 'x', system: ' http://snomed.info/sct ' }
define NullIn: null as Code ~in "SNOMED"
"""
        py, cpp = _both_engines()
        try:
            result = translate_cql(cql)
            assert result["EquivIn"].to_sql() == "TRUE"
            assert result["ExactIn"].to_sql() == "FALSE"
            assert result["EquivContains"].to_sql() == "TRUE"
            assert result["NullIn"].to_sql() == "FALSE"
        finally:
            py.close()
            cpp.close()

    def test_string_in_codesystem_still_raises_typed_error(self):
        """String CodeSystem membership needs a terminology service in both
        the 1.5 `in` and the 2.0 `~in` spelling (pinned CQL-02 SKEPTIC
        doctrine)."""
        from fhir4ds.cql.errors import TranslationError

        cql = """library CS20D version '1.0.0'
using FHIR version '4.0.1'
codesystem "SNOMED": 'http://snomed.info/sct'
context Unfiltered
define Probe: '12345' ~in "SNOMED"
"""
        with pytest.raises(TranslationError):
            translate_cql(cql)


# ---------------------------------------------------------------------------
# Retrieve comparators — FHIR-31392
# ---------------------------------------------------------------------------

class TestRetrieveComparators:
    def _population_setup(self, con, resources):
        con.execute(
            "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, "
            "resource JSON, patient_ref VARCHAR)"
        )
        con.execute("DELETE FROM resources")
        patient = {
            "resourceType": "Patient", "id": "p1",
            "patient_ref": "p1",
        }
        for r in [patient, *resources]:
            con.execute(
                "INSERT INTO resources VALUES (?, ?, ?::JSON, ?)",
                [r["id"], r["resourceType"], json.dumps(r), r["patient_ref"]],
            )

    def test_retrieve_tilde_in_valueset_end_to_end(self):
        """`[Condition: code ~in "VS"]` keeps resources whose coding is
        EQUIVALENT to a cache member (case-mismatched code), while the exact
        `in` retrieve on the same ValueSet excludes it."""
        cql = f"""library RT20A version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
context Patient
define EquivCount: Count([Condition: code ~in "VS"])
define ExactCount: Count([Condition: code in "VS"])
"""
        sql = CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql),
            output_columns={"EquivCount": "EquivCount", "ExactCount": "ExactCount"},
        )
        # Coding code 'heartrate' (case-flipped from the cache member
        # 'HearTRate' under http://loinc.org): equivalent but not exactly
        # equal.
        cond = {
            "resourceType": "Condition", "id": "c1",
            "code": {"coding": [{"system": "http://loinc.org", "code": "heartrate"}]},
            "subject": {"reference": "Patient/p1"},
            "patient_ref": "p1",
        }
        py, cpp = _both_engines()
        try:
            for con in (py, cpp):
                self._population_setup(con, [cond])
                row = con.execute(sql).fetchone()
                values = dict(zip([d[0] for d in con.execute(sql).description], row))
                assert values["EquivCount"] == 1, con
                assert values["ExactCount"] == 0, con
        finally:
            py.close()
            cpp.close()

    def test_retrieve_tilde_contains_code_end_to_end(self):
        """`[Condition: code ~contains "DiabetesCode"]` keeps resources whose
        code element equivalently-contains the declared code (case-mismatched
        system+code in the resource); the exact `=` retrieve excludes it."""
        cql = """library RT20B version '1.0.0'
using FHIR version '4.0.1'
codesystem "SNOMED": 'http://snomed.info/sct'
code "DiabetesCode": 'Diabetes' from "SNOMED"
context Patient
define EquivCount: Count([Condition: code ~contains "DiabetesCode"])
define ExactCount: Count([Condition: code = "DiabetesCode"])
"""
        sql = CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql),
            output_columns={"EquivCount": "EquivCount", "ExactCount": "ExactCount"},
        )
        cond = {
            "resourceType": "Condition", "id": "c2",
            "code": {"coding": [{"system": "HTTP://SNOMED.INFO/SCT", "code": "diabetes"}]},
            "subject": {"reference": "Patient/p1"},
            "patient_ref": "p1",
        }
        py, cpp = _both_engines()
        try:
            for con in (py, cpp):
                self._population_setup(con, [cond])
                row = con.execute(sql).fetchone()
                values = dict(zip([d[0] for d in con.execute(sql).description], row))
                assert values["EquivCount"] == 1, con
                assert values["ExactCount"] == 0, con
        finally:
            py.close()
            cpp.close()

    def test_retrieve_tilde_contains_requires_declared_code(self):
        from fhir4ds.cql.errors import TranslationError

        cql = """library RT20C version '1.0.0'
using FHIR version '4.0.1'
codesystem "SNOMED": 'http://snomed.info/sct'
context Patient
define Probe: exists([Condition: code ~contains "NotACode"])
"""
        with pytest.raises(TranslationError):
            CQLToSQLTranslator().translate_library_to_population_sql(parse_cql(cql))

    def test_list_membership_tilde_still_works(self):
        """The pre-existing CQL 2.0 list `~in`/`~contains` surface must be
        unaffected by the terminological dispatch (regression guard)."""
        expression = "'ABC' ~in { 'abc' }"
        sql = _translate(expression)
        py, cpp = _both_engines()
        try:
            assert py.execute(f"SELECT ({sql})").fetchone()[0] is True
            assert cpp.execute(f"SELECT ({sql})").fetchone()[0] is True
        finally:
            py.close()
            cpp.close()
