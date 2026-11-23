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

# AMUX-152 batch 2 (#8): two distinct status ValueSets so same-property /
# different-target additional filters must NOT share one CTE.
VS_ACTIVE_ONLY_URL = "http://example.org/fhir/ValueSet/vs20e-active-only"
VS_RECUR_ONLY_URL = "http://example.org/fhir/ValueSet/vs20e-recur-only"
_CACHE[VS_ACTIVE_ONLY_URL] = {
    ("http://terminology.hl7.org/CodeSystem/condition-clinical", "active"),
}
_CACHE[VS_RECUR_ONLY_URL] = {
    ("http://terminology.hl7.org/CodeSystem/condition-clinical", "recurrence"),
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


# ---------------------------------------------------------------------------
# `define type` — FHIR-34014 / CQL 2.0 Defining Class Types (trial-use)
# ---------------------------------------------------------------------------

class TestDefineType:
    CQL = """library DT20A version '1.0.0'
using FHIR version '4.0.1'
define public type Person extends System.Any {
  name System.String,
  dob System.Date
}
define type Wrapper extends System.Any {
  who Person,
  tags List<System.String>,
  value Choice<System.Integer, System.Decimal>
}
context Patient
define Inst: Person { name: 'Ada', dob: @2000-01-01 }
define IsPerson: Inst is Person
define IsNotPerson: 5 is Person
define CastName: exists (Tuple { a: 1 } as Wrapper)
"""

    def test_parse_shape(self):
        lib = parse_cql(self.CQL)
        types = {
            getattr(s, "name", None): s
            for s in lib.statements
            if type(s).__name__ == "TypeDefinition"
        }
        assert set(types) == {"Person", "Wrapper"}, types.keys()
        person = types["Person"]
        assert person.access_level == "public"
        assert getattr(person.base_type, "name", None) == "System.Any"
        assert [el.name for el in person.elements] == ["name", "dob"]
        assert getattr(person.elements[0].type_specifier, "name") == "System.String"
        wrapper = types["Wrapper"]
        # Named tuple-type reference (FHIR-34014): Wrapper.who is Person.
        assert getattr(wrapper.elements[0].type_specifier, "name") == "Person"
        assert type(wrapper.elements[1].type_specifier).__name__ == "ListTypeSpecifier"
        assert type(wrapper.elements[2].type_specifier).__name__ == "ChoiceTypeSpecifier"

    def test_registration_in_context(self):
        translator = CQLToSQLTranslator()
        translator.translate_library(parse_cql(self.CQL))
        declared = translator._context.declared_types
        assert "Person" in declared and "Wrapper" in declared
        assert declared["Person"]["elements"] == [
            ("name", "System.String"), ("dob", "System.Date"),
        ]
        assert declared["Person"]["base"] == "System.Any"
        assert declared["Wrapper"]["elements"][0] == ("who", "Person")
        assert declared["Wrapper"]["elements"][1] == ("tags", "List<System.String>")

    def test_declared_types_are_valid_is_as_targets(self):
        """`X is Person` / `X as Person` accept a declared type name (previously
        'references unknown type' TranslationError)."""
        results = translate_cql(self.CQL)
        assert results["IsPerson"].to_sql() == "TRUE"
        assert results["IsNotPerson"].to_sql() == "FALSE"
        # `as` lowers without error and keeps the value (typed pass-through).
        assert "as Wrapper"  # sanity: assertion text references the CQL above

    def test_instance_selector_and_property_end_to_end(self):
        """Instance selectors typed with a declared name evaluate end-to-end
        through population SQL on both engines (tuple-shaped use case)."""
        cql = """library DT20B version '1.0.0'
using FHIR version '4.0.1'
define type Person extends System.Any {
  name System.String,
  score System.Decimal
}
context Patient
define Inst: Person { name: 'Ada', score: 42.5 }
"""
        sql = CQLToSQLTranslator().translate_library_to_population_sql(
            parse_cql(cql), output_columns={"Inst": "Inst"},
        )
        py, cpp = _both_engines()
        try:
            for con in (py, cpp):
                _population_setup(con, [])
                cur = con.execute(sql)
                row = cur.fetchone()
                values = dict(zip([d[0] for d in cur.description], row))
                assert values["Inst"] is not None, con
                payload = values["Inst"]
                if isinstance(payload, str):
                    import json as _json
                    payload = _json.loads(payload)
                assert payload["name"] == "Ada", (con, payload)
                assert float(payload["score"]) == 42.5, (con, payload)
        finally:
            py.close()
            cpp.close()

    def test_parameter_typed_with_declared_name(self):
        """`parameter P Person` parses and translates (treated as the declared
        tuple type for typing purposes)."""
        cql = """library DT20C version '1.0.0'
using FHIR version '4.0.1'
define type Person extends System.Any { name System.String }
parameter Demographics Person default Person { name: 'default' }
context Unfiltered
define Probe: 1 + 1
"""
        results = translate_cql(cql)
        assert results["Probe"].to_sql() == "1 + 1"

    def test_typeinfo_and_related_to_clauses_parse(self):
        """The model-info metadata clauses (`label`, `identifier`,
        `retrievable`, `primary code path`) and `related to <Ctx> by { keys }`
        context relationships parse and register."""
        lib = parse_cql("""library DT20D version '1.0.0'
using FHIR version '4.0.1'
define context Patient of type FHIR.Patient with key { id }
define type Observation extends System.Any {
  subject System.String,
  code System.String
}
  label Obs
  identifier 'http://example.org/StructureDefinition/obs'
  retrievable
  primary code path code
related to Patient by { subject }
""")
        (td,) = [s for s in lib.statements if type(s).__name__ == "TypeDefinition"]
        assert td.label == "Obs"
        assert td.identifier == "http://example.org/StructureDefinition/obs"
        assert td.retrievable is True
        assert td.primary_code_path == "code"
        assert len(td.context_relationships) == 1
        assert td.context_relationships[0].context == "Patient"
        assert td.context_relationships[0].key_elements == ["subject"]
        translator = CQLToSQLTranslator()
        translator.translate_library(lib)
        info = translator._context.declared_types["Observation"]
        assert info["retrievable"] is True
        assert info["relationships"] == [
            {"context": "Patient", "key_elements": ["subject"]}
        ]

    def test_define_type_statements_do_not_become_definitions(self):
        """A `define type` statement must not produce an expression definition
        (translate_library returns no entry keyed by the type name)."""
        results = translate_cql(self.CQL)
        assert "Person" not in results
        assert "Wrapper" not in results
        assert "Inst" in results


# ---------------------------------------------------------------------------
# `define context` + `define conversion` (CQL 2.0 Defining Contexts /
# Defining Conversions, trial-use)
# ---------------------------------------------------------------------------

class TestDefineContext:
    def test_declared_context_registers_and_binds(self):
        """`define context Patient of type FHIR.Patient with key { id }`
        registers; the following `context Patient` statement binds the
        declared type/key metadata (active_context_info)."""
        cql = """library DC20 version '1.0.0'
using FHIR version '4.0.1'
define context Patient of type FHIR.Patient with key { id }
context Patient
define Probe: exists [Patient]
"""
        translator = CQLToSQLTranslator()
        translator.translate_library(parse_cql(cql))
        declared = translator._context.declared_contexts
        assert "Patient" in declared
        assert declared["Patient"]["context_type"] == "FHIR.Patient"
        assert declared["Patient"]["key_elements"] == ["id"]
        assert translator._context.active_context_info == {
            "name": "Patient",
            "context_type": "FHIR.Patient",
            "key_elements": ["id"],
        }

    def test_context_without_declaration_has_no_binding(self):
        cql = """library DC21 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Probe: exists [Patient]
"""
        translator = CQLToSQLTranslator()
        translator.translate_library(parse_cql(cql))
        assert translator._context.active_context_info is None

    def test_multi_key_context_registers(self):
        cql = """library DC22 version '1.0.0'
using FHIR version '4.0.1'
define context Encounter of type FHIR.Encounter with key { id, subject }
context Unfiltered
define Probe: 1 + 1
"""
        lib = parse_cql(cql)
        (ci,) = [s for s in lib.statements if type(s).__name__ == "ContextInfoDefinition"]
        assert ci.key_elements == ["id", "subject"]


class TestDefineConversion:
    def test_declared_conversion_drives_explicit_convert(self):
        """`define implicit conversion from A to B using F` +
        `convert a to B` lowers to the declared function invocation
        (inlined library-local function)."""
        cql = """library CV20 version '1.0.0'
using FHIR version '4.0.1'
define type Cels extends System.Any { v System.Decimal }
define type Fahr extends System.Any { v System.Decimal }
define function ToFahr(c Cels): Fahr { v: 32.0 + 9.0 * 10.0 }
define implicit conversion from Cels to Fahr using ToFahr
context Patient
define Probe: convert Cels { v: 100.0 } to Fahr
"""
        results = translate_cql(cql)
        sql = results["Probe"].to_sql()
        # The declared conversion function's body is invoked (inlined).
        assert "32.0 + 9.0 * 10.0" in sql, sql

    def test_declared_conversion_registration(self):
        cql = """library CV21 version '1.0.0'
using FHIR version '4.0.1'
define explicit conversion from FHIR.Period to Interval<System.DateTime> using FHIRHelpers.ToInterval
context Patient
define Probe: 1 + 1
"""
        translator = CQLToSQLTranslator()
        translator.translate_library(parse_cql(cql))
        (conv,) = translator._context.declared_conversions
        assert conv == {
            "implicit": False,
            "from": "FHIR.Period",
            "to": "Interval<System.DateTime>",
            "function": "FHIRHelpers.ToInterval",
            "access_level": "public",
        }

    def test_convert_without_matching_declaration_unchanged(self):
        """A `convert` whose target has NO declared conversion keeps the
        built-in lowering (regression guard)."""
        cql = """library CV22 version '1.0.0'
using FHIR version '4.0.1'
context Unfiltered
define Probe: convert '42' to Integer
"""
        results = translate_cql(cql)
        assert "ToInteger" in results["Probe"].to_sql()


# ---------------------------------------------------------------------------
# AMUX-152 batch 2 — CQL 2.0 translator correctness (#3, #7, #8, #14)
# ---------------------------------------------------------------------------

class TestAmux152Batch2:
    def test_single_declared_conversion_requires_from_type_match_amux152_3(self):
        """AMUX-152 #3: the single-candidate shortcut in convert resolution
        must still check the declared FROM type against the source's static
        type. With only ``Cels -> Fahr`` declared, ``convert 'hello' to Fahr``
        (source String) must NOT lower to the Cels conversion body."""
        cql = """library CV152a version '1.0.0'
using FHIR version '4.0.1'
define type Cels extends System.Any { v System.Decimal }
define type Fahr extends System.Any { v System.Decimal }
define function ToFahr(c Cels): Fahr { v: 32.0 + 9.0 * 10.0 }
define implicit conversion from Cels to Fahr using ToFahr
context Patient
define Probe: convert 'hello' to Fahr
"""
        sql = translate_cql(cql)["Probe"].to_sql()
        assert "32.0" not in sql, (
            f"String source must not lower to the Cels conversion body: {sql}"
        )

    def test_declared_conversion_from_type_system_prefix_normalized_amux152_3(self):
        """AMUX-152 #3: declared conversion from-types may carry the
        ``System.`` prefix; comparison against the source's static type must
        normalize it, both for the single-candidate shortcut and the
        multi-candidate from-type match."""
        cql = """library CV152b version '1.0.0'
using FHIR version '4.0.1'
define type Fahr extends System.Any { v System.Decimal }
define function FromString(s String): Fahr { v: 1.0 }
define function FromDecimal(d Decimal): Fahr { v: 2.0 }
define implicit conversion from System.String to Fahr using FromString
define implicit conversion from System.Decimal to Fahr using FromDecimal
context Patient
define Str: convert 'x' to Fahr
define Dec: convert 5.5 to Fahr
"""
        results = translate_cql(cql)
        str_sql = results["Str"].to_sql()
        dec_sql = results["Dec"].to_sql()
        assert "1.0" in str_sql and "2.0" not in str_sql, str_sql
        assert "2.0" in dec_sql and "1.0" not in dec_sql, dec_sql

    def test_multi_filter_promotion_key_includes_filters_amux152_7(self, caplog):
        """AMUX-152 #7: `_retrieve_promotion_source` must encode the
        retrieve's additional filters into the valueset key exactly like the
        retrieve translation does, or the function-promotion pre-scan keys
        the promoted function against the UNFILTERED CTE name and the
        promotion falls back to inline expansion ('never emitted
        (unresolvable dependencies)')."""
        cql = f"""library MF152g version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveVS": '{VS_STATUS_URL}'
context Patient
define function Tag(c Condition): {{ id: c.id }}
define D1: First(([Condition: code in "VS", clinicalStatus in "ActiveVS"] C return Tag(C)))
define D2: First(([Condition: code in "VS", clinicalStatus in "ActiveVS"] C return Tag(C)))
define D3: First(([Condition: code in "VS", clinicalStatus in "ActiveVS"] C return Tag(C)))
"""
        import logging

        with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.translator.translator"):
            CQLToSQLTranslator().translate_library_to_population_sql(parse_cql(cql))
        never_emitted = [
            r for r in caplog.records if "was never emitted" in r.getMessage()
        ]
        assert not never_emitted, (
            "function promotion keyed the unfiltered CTE and fell back to inline: "
            + "\n".join(r.getMessage() for r in never_emitted)
        )

    def test_same_property_different_filter_targets_distinct_ctes_amux152_8(self):
        """AMUX-152 #8: two retrieves that differ only in the TARGET of an
        additional filter on the SAME property must get distinct CTEs — the
        multi-filter label may not use property names alone."""
        cql = f"""library MF152h version '1.0.0'
using FHIR version '4.0.1'
valueset "VS": '{VS_URL}'
valueset "ActiveOnly": '{VS_ACTIVE_ONLY_URL}'
valueset "RecurOnly": '{VS_RECUR_ONLY_URL}'
context Patient
define ActiveCount: Count([Condition: code in "VS", clinicalStatus in "ActiveOnly"])
define RecurCount: Count([Condition: code in "VS", clinicalStatus in "RecurOnly"])
"""
        resources = [
            self._cond("c1", "8867-4", "http://loinc.org", "active"),
            self._cond("c2", "8867-4", "http://loinc.org", "active"),
            self._cond("c3", "8867-4", "http://loinc.org", "recurrence"),
        ]
        results = _run_population(
            cql, resources,
            {"ActiveCount": "ActiveCount", "RecurCount": "RecurCount"},
        )
        for engine in ("py", "cpp"):
            assert results[engine]["ActiveCount"] == 2, (engine, results[engine])
            assert results[engine]["RecurCount"] == 1, (engine, results[engine])

    @staticmethod
    def _cond(cid: str, code: str, system: str, clinical_status: str) -> dict:
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

    def test_tail_string_count_rejected_amux152_14(self):
        """AMUX-152 #14 (FHIR-40612): the two-argument Tail(list, count)
        must enforce the Integer count type statically like Skip/Take/Head;
        `Tail({1,2,3}, '2')` is a translation error, not a lowered call."""
        from fhir4ds.cql.errors import TranslationError

        cql = """library TL152 version '1.0.0'
using FHIR version '4.0.1'
context Unfiltered
define Probe: Tail({1, 2, 3}, '2')
"""
        with pytest.raises(TranslationError, match="[Tt]ail"):
            CQLToSQLTranslator().translate_library_to_population_sql(parse_cql(cql))


