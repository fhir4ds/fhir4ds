"""QA-019 / QA-020 failing-first regression tests (iteration 3, CQL HISTORIAN).

QA-019: `[Observation: "8480-6" in "LOINC"]` with a declared codesystem must
  translate to the direct-code membership predicate
  (`urn:cql:code:http://loinc.org|8480-6`), NOT an in_valueset call against a
  fabricated NLM ValueSet URL. Both engines currently mistranslate identically
  (translator layer).

QA-020: `Count(flatten((from [Observation] O return O.code.coding)))` must
  execute; the query source lowers rows-shaped (scalar fhirpath_text per row)
  so DuckDB's flatten() receives VARCHAR[] instead of VARCHAR[][] — a
  BinderException on all three engine modes. Fix mirrors the CQL-19 EXPLORER
  `_list_operator_full_list_source` materialization.
"""

from __future__ import annotations

import duckdb

from .wasm_runtime_helpers import no_python_connection


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    from fhir4ds.cql.duckdb.extension import _register_python_supplements

    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    from fhir4ds.cql.duckdb import register

    register(con)
    return con


# ---------------------------------------------------------------------------
# QA-019: code-in-CodeSystem retrieve translates to direct-code membership
# ---------------------------------------------------------------------------

_QA019_CQL = """library RetrieveCodes version '1.0.0'
using FHIR version '4.0.1'
codesystem "LOINC": 'http://loinc.org'
context Patient
define R: [Observation: "8480-6" in "LOINC"]
"""


def test_qa019_code_in_codesystem_retrieve_emits_direct_code() -> None:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_QA019_CQL), output_columns={"R": "R"}
    )
    # QA-019: direct-code membership lowers to a coding_matches predicate
    # against the declared codesystem URL + code (cte_builder's
    # `urn:cql:code:` lowering), NOT an in_valueset call against a
    # fabricated NLM ValueSet URL.
    assert "coding_matches(r.resource, 'code', 'http://loinc.org', '8480-6')" in sql
    assert "in_valueset" not in sql
    assert "cts.nlm.nih.gov" not in sql


_QA019_RESOURCES = """
CREATE TABLE IF NOT EXISTS resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR);
DELETE FROM resources;
INSERT INTO resources VALUES
('P1','Patient','{"resourceType":"Patient","id":"P1","active":true}',NULL),
('P2','Patient','{"resourceType":"Patient","id":"P2","active":true}',NULL),
('O1','Observation','{"resourceType":"Observation","id":"O1","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"8480-6"}]},"subject":{"reference":"Patient/P1"}}','P1'),
('O2','Observation','{"resourceType":"Observation","id":"O2","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"8462-4"}]},"subject":{"reference":"Patient/P2"}}','P2')
"""


def test_qa019_code_in_codesystem_retrieve_filters_correctly() -> None:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_QA019_CQL), output_columns={"R": "R"}
    )
    results = {}
    for label, con in (
        ("py", _python_only_connection()),
        ("cpp", _cpp_connection()),
    ):
        con.execute(_QA019_RESOURCES)
        results[label] = con.execute(sql).fetchall()
        con.close()
    assert results["py"] == results["cpp"]
    # O1 (code 8480-6 in LOINC) passes; O2 (8462-4) does not. The
    # population output projects the matched resource refs per patient.
    assert results["py"] == [("P1", ["Observation/O1"]), ("P2", [])]


# ---------------------------------------------------------------------------
# QA-020: flatten over a query source materializes the per-patient list
# ---------------------------------------------------------------------------

_QA020_CQL = """library FlattenQuery version '1.0.0'
using FHIR version '4.0.1'
context Patient
define R: Count(flatten((from [Observation] O return O.component.code.coding)))
"""


def test_qa020_flatten_over_query_source_executes() -> None:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    resources = """
CREATE TABLE IF NOT EXISTS resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR);
DELETE FROM resources;
INSERT INTO resources VALUES
('P1','Patient','{"resourceType":"Patient","id":"P1","active":true}',NULL),
('P2','Patient','{"resourceType":"Patient","id":"P2","active":true}',NULL),
('O1','Observation','{"resourceType":"Observation","id":"O1","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"29463-7"}]},"component":[{"code":{"coding":[{"system":"http://loinc.org","code":"8480-6"}]}},{"code":{"coding":[{"system":"http://loinc.org","code":"8462-4"}]}}],"subject":{"reference":"Patient/P1"}}','P1'),
('O2','Observation','{"resourceType":"Observation","id":"O2","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"8867-4"}]},"component":[{"code":{"coding":[{"system":"http://loinc.org","code":"8480-6"}]}}],"subject":{"reference":"Patient/P2"}}','P2')
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_QA020_CQL), output_columns={"R": "R"}
    )
    results = {}
    cons = []
    no_py_cm = no_python_connection()
    no_py = no_py_cm.__enter__()
    try:
        for label, con in (
            ("py", _python_only_connection()),
            ("cpp", _cpp_connection()),
            ("nopy", no_py),
        ):
            con.execute(resources)
            results[label] = con.execute(sql).fetchall()
            if label != "nopy":
                cons.append(con)
        assert results["py"] == results["cpp"] == results["nopy"]
        # O1 has 2 component codings, O2 has 1.
        assert results["py"] == [("P1", 2), ("P2", 1)]
    finally:
        no_py_cm.__exit__(None, None, None)
        for con in cons:
            con.close()


_QA020B_CQL = """library FlattenQueryB version '1.0.0'
using FHIR version '4.0.1'
context Patient
define R: Count(flatten((from [Observation] O return O.code.coding)))
"""


def test_qa020_flatten_over_query_source_multi_coding() -> None:
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    resources = """
CREATE TABLE IF NOT EXISTS resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR);
DELETE FROM resources;
INSERT INTO resources VALUES
('P1','Patient','{"resourceType":"Patient","id":"P1","active":true}',NULL),
('O1','Observation','{"resourceType":"Observation","id":"O1","status":"final","code":{"coding":[{"system":"http://loinc.org","code":"8480-6"},{"system":"http://loinc.org","code":"8462-4"}]},"subject":{"reference":"Patient/P1"}}','P1')
"""
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_QA020B_CQL), output_columns={"R": "R"}
    )
    con = _python_only_connection()
    try:
        con.execute(resources)
        rows = con.execute(sql).fetchall()
        # One observation with 2 codings flattened -> 2.
        assert rows == [("P1", 2)]
    finally:
        con.close()
