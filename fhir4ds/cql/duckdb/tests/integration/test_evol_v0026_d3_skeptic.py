"""Domain 3 SKEPTIC (v0.0.26 iteration 9) regression coverage.

Covers:
* QA-D3S-002 (carry-in 2): tuple-list-field property query sources UNNEST
  per element instead of inlining the whole list into
  ``fhirpath(VARCHAR[], ...)`` calls.
* QA-D3S-004 (H3): CQL 2.0 ``~in``/``in`` ValueSet membership over a
  non-resource scalar operand (e.g. ``First([Observation] O return
  O.code) ~in "VS"``) must wrap the CodeableConcept-valued scalar into a
  synthetic resource for the membership UDF instead of silently
  returning False (extractCodes navigates resource+path).
* Carry-in adjudication pins: `1.5 ~ 1.55` → False (official fixture
  EquivFloat1Float1WithPrecision) live in
  test_comparison_operator_parity.py.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader
from fhir4ds.cql.duckdb.extension import register
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator

VS = {
    "resourceType": "ValueSet",
    "id": "vs1",
    "url": "http://example.org/vs",
    "expansion": {"contains": [
        {"system": "http://loinc.org", "code": "8867-4"},
        {"system": "http://loinc.org", "code": "29463-7"},
    ]},
}
OBS = {
    "resourceType": "Observation", "id": "o1", "status": "final",
    "subject": {"reference": "Patient/p1"},
    # The SECOND coding is the value-set member — proves full-coding
    # extraction rather than first-node truncation.
    "code": {"coding": [
        {"system": "http://snomed.info/sct", "code": "xxx"},
        {"system": "http://loinc.org", "code": "29463-7"},
    ]},
}


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    FHIRDataLoader(con).load_resources(
        [{"resourceType": "Patient", "id": "p1"}, OBS]
    )
    FHIRDataLoader(con).load_valuesets([VS])
    return con


class TestTupleListFieldQuerySource:
    def test_tuple_list_field_query_source_unnests_per_element(self) -> None:
        from fhir4ds.cql import translate_cql

        cql = """library T version '1.0.0'
using FHIR version '4.0.1'
context Patient
define TupleDayFilter:
  (Tuple {
    days: {
      Tuple { dayNumber: '1' },
      Tuple { dayNumber: '2' }
    }
  }.days) D
    where D.dayNumber > 1
    return D.dayNumber
"""
        sql = translate_cql(cql)["TupleDayFilter"].to_sql()
        assert "fhirpath_text(_lt_D, 'dayNumber')" in sql
        from fhir4ds.cql.duckdb.extension import _register_python_supplements

        for native in (True, False):
            con = duckdb.connect(config={"allow_unsigned_extensions": True})
            try:
                if native:
                    register(con, include_fhirpath=True)
                else:
                    _register_python_supplements(
                        con, cpp_loaded=False, include_fhirpath=True
                    )
                assert con.execute(f"SELECT ({sql})").fetchone() == (["2"],)
            finally:
                con.close()


class TestEquivalentInValuesetScalarOperand:
    LIB = """library H3 version '1.0'
using FHIR version '4.0.1'
valueset "VS": 'http://example.org/vs'
context Patient
"""

    @pytest.mark.parametrize("define", [
        # element-expression form (scalar subquery operand)
        "define A: First([Observation] O return O.code) ~in \"VS\"",
        # converse operator
        "define B: \"VS\" ~contains First([Observation] O return O.code)",
        # exact-match `in` shares the operand path
        "define C: First([Observation] O return O.code) in \"VS\"",
    ])
    def test_scalar_codeableconcept_operand_membership(self, define: str) -> None:
        name = define.split()[1].rstrip(":")
        con = _con()
        try:
            sql = CQLToSQLTranslator(connection=con).translate_library_to_population_sql(
                parse_cql(self.LIB + define),
                output_columns={name: name},
            )
            row = con.execute(sql).fetchone()
            assert row == ("p1", True), f"{define}: {row}"
        finally:
            con.close()

    def test_scalar_operand_nonmember_is_false(self) -> None:
        con = _con()
        try:
            sql = CQLToSQLTranslator(connection=con).translate_library_to_population_sql(
                parse_cql(
                    self.LIB
                    + 'define A: First([Observation] O return O.status) ~in "VS"'
                ),
                output_columns={"A": "A"},
            )
            # 'final' is a plain string status, not a member code → False
            assert con.execute(sql).fetchone() == ("p1", False)
        finally:
            con.close()
