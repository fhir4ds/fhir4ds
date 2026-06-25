"""Regression tests for CASE-WHEN over a boolean define.

Tracks the fix for the issue where ``case when "BoolDefine" then ... end``
generated ``SELECT sub.value FROM "BoolDefine" ...`` even though boolean-define
CTEs only expose ``patient_id``. The translator must emit ``EXISTS (SELECT 1
FROM "BoolDefine" ...)`` in that position instead.
"""

from __future__ import annotations

import duckdb

from ...parser import parse_cql
from ...translator import CQLToSQLTranslator
from fhir4ds.cql import FHIRDataLoader, evaluate_measure
from fhir4ds.cql.duckdb import register


_CQL_TEMPLATE = """
library TestCaseBoolDefine version '1.0'
using FHIR version '4.0.1'

codesystem "SNOMED": 'http://snomed.info/sct'
code "HIV": '86406008' from "SNOMED"

context Patient

define "HasHIV":
    exists ([Condition: "HIV"])

define "PatientAge":
    AgeInYearsAt(Today())

define "RecommendedAction":
    case
        when "HasHIV" then 'exclude'
        when "PatientAge" > 65 then 'too_old'
        else 'screen'
    end
"""


def test_case_when_boolean_define_emits_exists_not_sub_value():
    """CASE WHEN over a promoted boolean define must emit EXISTS, not sub.value.

    The boolean-define CTE only has ``patient_id`` (no ``value`` column), so the
    ``SELECT sub.value FROM "HasHIV" ... LIMIT 1`` pattern raises a Binder error.
    The translator must use ``EXISTS (SELECT 1 FROM "HasHIV" ...)`` instead.
    """
    library = parse_cql(_CQL_TEMPLATE)
    translator = CQLToSQLTranslator()
    sql = translator.translate_library_to_population_sql(library)

    assert 'EXISTS' in sql.upper() and '"HasHIV"' in sql, (
        "Expected EXISTS subquery referencing \"HasHIV\"; got:\n" + sql
    )
    # The buggy pattern references a non-existent column on the boolean CTE.
    assert 'sub.value FROM "HasHIV"' not in sql, (
        "Translator still emits `sub.value FROM \"HasHIV\"` "
        "(boolean CTE has no value column). SQL:\n" + sql
    )
    # Spot-check the CASE WHEN clause itself contains the EXISTS form.
    assert 'CASE WHEN EXISTS' in sql.upper(), (
        "Expected `CASE WHEN EXISTS (SELECT 1 FROM \"HasHIV\" ...)`; got:\n" + sql
    )


def test_case_when_boolean_define_executes_correctly(tmp_path):
    """End-to-end: the CASE over a boolean define must bind and return correctly.

    Patient p1 has the HIV condition -> action='exclude', has_hiv=True.
    Patient p2 has no condition and is under 65 -> action='screen', has_hiv=False.
    Patient p3 has no condition and is over 65 -> action='too_old', has_hiv=False.
    """
    cql_path = tmp_path / "case_bool_define.cql"
    cql_path.write_text(_CQL_TEMPLATE)

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
            {"resourceType": "Patient", "id": "p2", "birthDate": "1985-01-01"},
            {"resourceType": "Patient", "id": "p3", "birthDate": "1950-01-01"},
        ]:
            loader.load_resource(resource)

        df = evaluate_measure(
            str(cql_path),
            con,
            output_columns={
                "action": "RecommendedAction",
                "has_hiv": "HasHIV",
            },
        )
        rows = df.set_index("patient_id").to_dict("index")

        assert rows["p1"]["action"] == "exclude", rows
        assert bool(rows["p1"]["has_hiv"]) is True, rows
        assert rows["p2"]["action"] == "screen", rows
        assert bool(rows["p2"]["has_hiv"]) is False, rows
        assert rows["p3"]["action"] == "too_old", rows
        assert bool(rows["p3"]["has_hiv"]) is False, rows
    finally:
        con.close()
