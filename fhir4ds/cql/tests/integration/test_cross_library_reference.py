"""Regression tests for cross-library CQL define references.

Tracks the fix for the issue where a CQL library using ``include`` to
reference another library generated broken SQL for qualified define
references like ``A."PatientAge"`` in scalar contexts. The CTE was
created correctly with the qualified name, but the *reference* to it
was emitted as ``SELECT * FROM "A.PatientAge"`` — missing column
projection, patient-id correlation, and LIMIT 1. The query failed at
bind time with ``Binder Error: Subquery returns 2 columns - expected 1``.

The fix is usage-aware: BOOLEAN/EXISTS references emit EXISTS, SCALAR
references emit a correlated subquery with LIMIT 1, and LIST references
(query sources) preserve the legacy ``SELECT *`` pattern. The LIST case
matters because DQM measures like CMS0334, CMS145, and CMS190 consume
cross-library defines as row sources — forcing a scalar subquery there
truncated multi-row defines and regressed DQM accuracy.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator
from fhir4ds.cql import FHIRDataLoader, evaluate_measure
from fhir4ds.cql.duckdb import register


_LIB_A_CQL = """
library LibA version '1.0'
using FHIR version '4.0.1'
context Patient
define "PatientAge": AgeInYearsAt(Today())
"""

_LIB_B_CQL = """
library LibB version '1.0'
using FHIR version '4.0.1'
include LibA version '1.0' called A
context Patient
define "AgeEligible": A."PatientAge" >= 18
"""

_LIB_C_CQL = """
library LibC version '1.0'
using FHIR version '4.0.1'
codesystem "SNOMED": 'http://snomed.info/sct'
code "HIV": '86406008' from "SNOMED"
context Patient
define "HasHIV": exists ([Condition: "HIV"])
"""

_LIB_D_CQL = """
library LibD version '1.0'
using FHIR version '4.0.1'
include LibC version '1.0' called C
context Patient
define "Action": case when C."HasHIV" then 'exclude' else 'screen' end
"""

# LibE returns a *list* (multi-row) define. LibF consumes it as a query
# source. This is the pattern DQM measures use — CMS0334/CMS145/CMS190
# broke when the initial fix routed query sources through the scalar
# subquery path. This test pins the LIST case so we don't regress it again.
_LIB_E_CQL = """
library LibE version '1.0'
using FHIR version '4.0.1'
context Patient
define "Conditions": [Condition]
"""

_LIB_F_CQL = """
library LibF version '1.0'
using FHIR version '4.0.1'
include LibE version '1.0' called E
context Patient
define "ConditionCount": Count(E."Conditions")
"""


def _library_loader_factory(lib_dir: Path):
    """Build a library_loader callable that resolves includes from lib_dir."""
    cache: dict[str, object] = {}

    def load(alias: str):
        if alias in cache:
            return cache[alias]
        path = lib_dir / f"{alias}.cql"
        if not path.exists():
            return None
        parsed = parse_cql(path.read_text())
        cache[alias] = parsed
        return parsed

    return load


def test_cross_library_scalar_define_emits_correlated_subquery(tmp_path):
    """``A."PatientAge"`` in scalar context must emit a correlated scalar
    subquery, not SELECT *.

    Bug shape: ``SELECT * FROM "A.PatientAge"`` returned 2 columns
    (patient_id + resource) in a scalar context, raising a binder error.
    Fix: emit ``SELECT sub.<col> FROM "A.PatientAge" AS sub WHERE
    sub.patient_id = ... LIMIT 1``.
    """
    (tmp_path / "LibA.cql").write_text(_LIB_A_CQL)
    (tmp_path / "LibB.cql").write_text(_LIB_B_CQL)
    library = parse_cql(_LIB_B_CQL)
    translator = CQLToSQLTranslator(library_loader=_library_loader_factory(tmp_path))
    sql = translator.translate_library_to_population_sql(library)

    assert 'SELECT * FROM "A.PatientAge"' not in sql, (
        "Translator still emits `SELECT * FROM \"A.PatientAge\"` for cross-library "
        "define reference in scalar context. SQL:\n" + sql
    )
    assert (
        'SELECT sub.resource FROM "A.PatientAge"' in sql
        or 'SELECT sub.value FROM "A.PatientAge"' in sql
    ), (
        "Expected correlated subquery `SELECT sub.<col> FROM \"A.PatientAge\" AS "
        "sub WHERE sub.patient_id = ... LIMIT 1`. SQL:\n" + sql
    )
    assert "LIMIT 1" in sql, (
        f"Cross-library scalar reference missing LIMIT 1. SQL:\n{sql}"
    )


def test_cross_library_scalar_define_executes_correctly(tmp_path):
    """End-to-end: ``A."PatientAge" >= 18`` must execute and return True for
    an adult patient. Before the fix this raised a binder error.
    """
    (tmp_path / "LibA.cql").write_text(_LIB_A_CQL)
    (tmp_path / "LibB.cql").write_text(_LIB_B_CQL)

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    try:
        loader = FHIRDataLoader(con)
        loader.load_resource({
            "resourceType": "Patient", "id": "p1",
            "gender": "female", "birthDate": "1990-01-01",
        })
        df = evaluate_measure(
            str(tmp_path / "LibB.cql"),
            con,
            output_columns={"eligible": "AgeEligible"},
            include_paths=[str(tmp_path)],
        )
        rows = df.set_index("patient_id").to_dict("index")
        assert bool(rows["p1"]["eligible"]) is True, (
            f"Patient born 1990 should be age-eligible (>= 18); got: {rows}"
        )
    finally:
        con.close()


def test_cross_library_boolean_define_in_case_when_uses_exists(tmp_path):
    """Boolean cross-library define referenced in CASE WHEN must emit EXISTS,
    not a value/resource column lookup.
    """
    (tmp_path / "LibC.cql").write_text(_LIB_C_CQL)
    (tmp_path / "LibD.cql").write_text(_LIB_D_CQL)

    library = parse_cql(_LIB_D_CQL)
    translator = CQLToSQLTranslator(library_loader=_library_loader_factory(tmp_path))
    sql = translator.translate_library_to_population_sql(library)

    assert 'EXISTS' in sql.upper() and '"C.HasHIV"' in sql, (
        f"Expected EXISTS subquery referencing \"C.HasHIV\"; got:\n{sql}"
    )
    assert 'sub.value FROM "C.HasHIV"' not in sql, (
        f"Cross-library boolean define leaked `sub.value` pattern. SQL:\n{sql}"
    )


def test_cross_library_boolean_define_executes_correctly(tmp_path):
    """End-to-end: ``case when C."HasHIV" then 'exclude' else 'screen' end``
    must return 'exclude' for a patient with the SNOMED 86406008 condition.
    """
    (tmp_path / "LibC.cql").write_text(_LIB_C_CQL)
    (tmp_path / "LibD.cql").write_text(_LIB_D_CQL)

    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con)
    try:
        loader = FHIRDataLoader(con)
        for resource in [
            {"resourceType": "Patient", "id": "p1", "birthDate": "1990-01-01"},
            {
                "resourceType": "Condition", "id": "c1",
                "subject": {"reference": "Patient/p1"},
                "code": {"coding": [{"system": "http://snomed.info/sct",
                                     "code": "86406008"}]},
                "clinicalStatus": {"coding": [{"code": "active"}]},
            },
        ]:
            loader.load_resource(resource)

        df = evaluate_measure(
            str(tmp_path / "LibD.cql"),
            con,
            output_columns={"action": "Action"},
            include_paths=[str(tmp_path)],
        )
        rows = df.set_index("patient_id").to_dict("index")
        assert rows["p1"]["action"] == "exclude", (
            f"Patient with HIV condition should get action='exclude'; got: {rows}"
        )
    finally:
        con.close()


def test_cross_library_list_query_source_preserves_select_star(tmp_path):
    """Cross-library define used as a *query source* must keep the SELECT *
    pattern. The initial fix (commit 3ba87aa0, reverted in 06544fbf)
    incorrectly routed query sources through the scalar subquery path,
    which truncated multi-row defines and regressed DQM accuracy on
    CMS0334, CMS145, and CMS190. This test pins the LIST case so that
    bug class doesn't recur.
    """
    (tmp_path / "LibE.cql").write_text(_LIB_E_CQL)
    (tmp_path / "LibF.cql").write_text(_LIB_F_CQL)

    library = parse_cql(_LIB_F_CQL)
    translator = CQLToSQLTranslator(library_loader=_library_loader_factory(tmp_path))
    sql = translator.translate_library_to_population_sql(library)

    assert '"E.Conditions"' in sql, (
        f"Test setup wrong — no reference to E.Conditions found. SQL:\n{sql}"
    )
    # The LIMIT 1 / correlated subquery pattern is what broke DQM. Make
    # sure the E.Conditions reference doesn't use it.
    bad_pattern = 'sub.resource FROM "E.Conditions" AS sub WHERE sub.patient_id'
    assert bad_pattern not in sql, (
        f"Cross-library LIST/query-source reference is using the correlated "
        f"scalar subquery pattern (with LIMIT 1). This truncates multi-row "
        f"defines and regressed DQM CMS0334/CMS145/CMS190. SQL:\n{sql}"
    )
