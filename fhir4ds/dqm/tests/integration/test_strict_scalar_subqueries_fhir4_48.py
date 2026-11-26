"""FHIR4-48 — generated SQL must be single-row BY CONSTRUCTION.

DuckDB's default is ``scalar_subquery_error_on_multiple_rows=true``: a scalar
subquery that produces more than one row is an error.  The desktop DQM harness
turned that rule OFF (``fhir4ds/dqm/tests/conformance/database.py``), so the
gate could not see the defect; every non-masked consumer — duckdb-wasm in all
web apps, any user connection — got

    Invalid Input Error: More than one row returned by a subquery used as an
    expression

on the whole measure.  The wasm-parity lane found it; this file pins the fix.

Two lowering defects produced multi-row scalar subqueries:

1. A query-return alias referenced from a nested scope (``with ... such that``
   over ``( <query> ) X``) was re-materialised as the WHOLE source query —
   ``intervalStart((SELECT <projection> FROM "<cte>" AS inner))`` — with no
   singleton narrowing and no patient predicate, so it could also return
   another patient's row (CMS56).
2. A multi-source query's ``return`` was not de-duplicated, so the definition
   kept one row per joined source row instead of one row per CQL tuple.  The
   promoted function CTE derived from it was therefore not unique on
   ``(patient_id, _row_key)`` and its ``(SELECT value ... WHERE patient_id AND
   _row_key)`` lookup returned several rows (CMS832).

Neither may be "fixed" by relaxing the connection: the assertions below run on
a strict connection and on purpose-built data, so a masking flag cannot make
them pass.
"""

import json
import os
import tempfile

import duckdb
import pytest

from fhir4ds import register
from fhir4ds.dqm.evaluator import MeasureEvaluator

SNOMED = "http://snomed.info/sct"
QI_CORE_SUITE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "tests", "data",
    "ecqm-content-qicore-2025",
)
US_CORE_SUITE = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "tests", "data",
    "dqm-content-cms-2025",
)
STRICT_SETTING = "scalar_subquery_error_on_multiple_rows"


def _strict_connection():
    """A connection that keeps DuckDB's DEFAULT scalar-subquery rule."""
    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    register(con)
    assert con.execute(f"SELECT current_setting('{STRICT_SETTING}')").fetchone()[0], (
        "test premise: this connection must NOT mask multi-row scalar subqueries"
    )
    return con


# ---------------------------------------------------------------------------
# 1. Lowering shape: query-return alias referenced from a nested scope
# ---------------------------------------------------------------------------

#: ``TotalProc`` is a query-return alias (an interval) referenced from the
#: ``with ... such that`` clause.  Before the fix that reference lowered to
#: ``(SELECT <interval> FROM "Procedures" AS P)`` — every patient's row, no
#: LIMIT — so it raised on a strict connection and, when permissive, answered
#: with the FIRST patient's procedure for everybody.
CQL_QUERY_RETURN_ALIAS = """library F48A version '1.0.0'
using FHIR version '4.0.1'
valueset "Proc VS": 'http://example.org/ValueSet/proc'
valueset "Obs VS": 'http://example.org/ValueSet/obs'
parameter "Measurement Period" Interval<DateTime>
context Patient

define "Assessments":
  from ( ["Observation": "Obs VS"] ) O
  return date from start of O.effective

define "Procedures":
  ( ["Procedure": "Proc VS"] ) P
    where P.status = 'completed'
      and P.performed.toInterval ( ) starts during day of "Measurement Period"

define "Qualifying":
  exists ( ( "Procedures" P return P.performed.toInterval ( ) ) TotalProc
      with "Assessments" A
        such that TotalProc starts 90 days or less on or after day of A
  )

define "Initial Population": exists ( Patient )
define "Denominator": "Initial Population"
define "Numerator": "Qualifying"
"""

#: Both patients have ONE in-window procedure, so the nested reference sees two
#: rows overall: the pre-fix ``(SELECT ... FROM "Procedures" AS P)`` therefore
#: (a) raises on a strict connection, and (b) under a permissive connection
#: answers with whichever row it happens to read first.  That makes the two
#: answers discriminating in both directions:
#:
#:   p1: procedure 2026-06-01, assessment 2026-05-25 -> 7 days after  -> TRUE
#:   p2: procedure 2026-01-02, assessment 2026-05-25 -> BEFORE it     -> FALSE
#:
#: A fix that merely appends ``LIMIT 1`` without correlating the patient would
#: answer BOTH from one patient's procedure and fail the opposite assertion.
QUERY_RETURN_ALIAS_PATIENTS = [
    {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Patient", "id": "p2", "birthDate": "1980-01-01",
     "gender": "female"},
    {"resourceType": "Procedure", "id": "proc-p1", "status": "completed",
     "subject": {"reference": "Patient/p1"},
     "performedDateTime": "2026-06-01",
     "code": {"coding": [{"system": SNOMED, "code": "11111"}]}},
    {"resourceType": "Procedure", "id": "proc-p2", "status": "completed",
     "subject": {"reference": "Patient/p2"},
     "performedDateTime": "2026-01-02",
     "code": {"coding": [{"system": SNOMED, "code": "11111"}]}},
    {"resourceType": "Observation", "id": "obs-p1", "status": "final",
     "subject": {"reference": "Patient/p1"},
     "effectiveDateTime": "2026-05-20",
     "code": {"coding": [{"system": SNOMED, "code": "22222"}]},
     "valueQuantity": {"value": 1}},
    {"resourceType": "Observation", "id": "obs-p2", "status": "final",
     "subject": {"reference": "Patient/p2"},
     "effectiveDateTime": "2026-05-20",
     "code": {"coding": [{"system": SNOMED, "code": "22222"}]},
     "valueQuantity": {"value": 1}},
]


def _measure(numerator: str) -> dict:
    return {
        "resourceType": "Measure", "id": "f48a",
        "library": ["http://example.org/Library/F48A|1.0.0"],
        "group": [{"id": "g1", "population": [
            {"code": {"coding": [{"code": "initial-population"}]},
             "criteria": {"expression": "Initial Population"}},
            {"code": {"coding": [{"code": "denominator"}]},
             "criteria": {"expression": "Denominator"}},
            {"code": {"coding": [{"code": "numerator"}]},
             "criteria": {"expression": numerator}},
        ]}],
    }


def _valuesets(tmpdir: str) -> list[str]:
    paths = []
    for key, code in (("proc", "11111"), ("obs", "22222")):
        vs = {
            "resourceType": "ValueSet", "id": key,
            "url": f"http://example.org/ValueSet/{key}",
            "compose": {"include": [
                {"system": SNOMED, "concept": [{"code": code}]}]},
        }
        p = os.path.join(tmpdir, f"vs_{key}.json")
        with open(p, "w") as f:
            json.dump(vs, f)
        paths.append(p)
    return paths


def _rows():
    return list(QUERY_RETURN_ALIAS_PATIENTS)


def test_query_return_alias_in_nested_scope_is_single_row_and_patient_scoped():
    """The reference must be answered from the CURRENT row, on a strict
    connection, with no cross-patient leakage."""
    tmpdir = tempfile.mkdtemp(prefix="f48_query_alias_")
    cql_path = os.path.join(tmpdir, "f48a.cql")
    with open(cql_path, "w") as f:
        f.write(CQL_QUERY_RETURN_ALIAS)

    con = _strict_connection()
    try:
        con.execute(
            "CREATE OR REPLACE TABLE resources ("
            "id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
        )
        for r in _rows():
            patient_ref = (
                r["id"] if r["resourceType"] == "Patient"
                else r["subject"]["reference"].split("/")[1]
            )
            con.execute(
                "INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [r["id"], r["resourceType"], json.dumps(r), patient_ref],
            )
        result = MeasureEvaluator(con).evaluate(
            measure_bundle=_measure("Numerator"),
            cql_library_path=cql_path,
            parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
            valueset_paths=_valuesets(tmpdir),
        )
    finally:
        con.close()

    df = result.dataframe
    by_patient = {
        row["patient_id"]: bool(row["numerator"]) for _, row in df.iterrows()
    }
    assert set(by_patient) == {"p1", "p2"}, by_patient
    assert by_patient["p1"] is True, (
        "p1's own procedure starts 7 days after its assessment"
    )
    assert by_patient["p2"] is False, (
        "p2's procedure starts BEFORE its assessment; a True here means the "
        "nested reference was answered from p1's row (or from an arbitrary row)"
    )


# ---------------------------------------------------------------------------
# 2. Real measures: the generated SQL must run untouched
# ---------------------------------------------------------------------------


def _measure_config(measure_id: str, suite: str = "qi-core-2025"):
    from fhir4ds.dqm.tests.conformance import cli as dqm_cli

    for cfg in dqm_cli._discover_measures(suite):
        if cfg.id == measure_id:
            return cfg
    return None


#: ``(suite, measure, all_columns)``. FHIR4-48 fixed CMS56/CMS832 in qi-core;
#: FHIR4-53 fixes the two shapes us-core still raised on:
#:
#: * CMS145 — fluent overload resolution fell back to the LAST-DECLARED
#:   ``overlapsDayOfEncounter`` overload (single ``Encounter``) for a
#:   ``List<Encounter>`` argument, so the whole list became an inline query
#:   source: one row per element read as a scalar.
#: * CMS156 — a promoted ``let`` CTE over a fluent-call source
#:   (``([MedicationRequest: VS]).moreThanOneOrder() AntiInfectives``) carried no
#:   ``_row_key``, so the sibling let that consumes it
#:   (``timing: dosage.timing``) looked its value up by ``patient_id`` alone.
#:
#: FHIR4-56 adds the two NHSN measures. Both BIND-FAILED (not merely
#: multi-row) on every strict consumer with
#: ``No function matches str_split(VARCHAR[], STRING_LITERAL)``: the flatten()
#: promotion pass rewrote ``fhirpath_text`` nodes living in a WHERE clause, so
#: the ``references()`` lowering (``LIST_EXTRACT(STR_SPLIT(<ref url>, '/'), -1)``)
#: was handed a LIST. They are kept here (rather than only in the translation
#: unit test) because the defect is only reachable through a real measure's
#: ``flatten(<query with references()>)`` shape.
#:
#: CMS986 is deliberately ABSENT: its assigned ``value``-column defect is fixed
#: (see ``fhir4ds/cql/tests/integration/test_fhir4_56_method_and_promotion.py``)
#: but a SECOND, distinct pre-existing defect still stops it binding —
#: ``verified(conditions List<FHIR.Condition>)`` inlined over a fluent-call
#: source binds ``C`` to the whole list, so ``C.verificationStatus`` lowers to
#: ``fhirpath_text(JSON[], 'verificationStatus')``. That is a list-valued
#: query-source alias-binding gap with its own card.
#:
#: ``all_columns=True`` on purpose: a column CTE that a population-only
#: projection never references still crashes a web app that asks for it.
STRICT_MEASURES = [
    ("qi-core-2025", "CMS56", False),
    ("qi-core-2025", "CMS832", False),
    ("us-core-2025", "CMS145", True),
    ("us-core-2025", "CMS156", True),
    ("us-core-2025", "NHSNAcuteCare", True),
    ("us-core-2025", "NHSNGlycemicControl", True),
]


@pytest.mark.slow
@pytest.mark.parametrize("suite,measure_id,all_columns", STRICT_MEASURES)
def test_generated_measure_sql_executes_on_strict_connection(
    suite, measure_id, all_columns
):
    """Full population SQL for the measures that raised the rule."""
    content_dir = QI_CORE_SUITE if suite.startswith("qi-core") else US_CORE_SUITE
    if not os.path.isdir(content_dir):
        pytest.skip(f"{suite} content package not present at {content_dir}")
    cfg = _measure_config(measure_id, suite)
    if cfg is None:
        pytest.skip(f"{measure_id} not present in the discovered suite")

    from fhir4ds.dqm.tests.conformance import database
    from fhir4ds.dqm.tests.conformance.loader import load_test_suite
    from fhir4ds.dqm.tests.conformance.runner import run_measure

    db = database.BenchmarkDatabase()
    try:
        db.load_all_test_data([cfg])
        db.load_all_valuesets(
            sorted({str(p): p for p in cfg.valueset_paths}.values(), key=str)
        )
        # Un-mask the harness for THIS connection: exactly what every browser
        # and any user connection does by default.
        db.conn.execute(f"SET {STRICT_SETTING}=true")
        assert db.conn.execute(
            f"SELECT current_setting('{STRICT_SETTING}')"
        ).fetchone()[0]
        result = run_measure(
            db.conn,
            cfg,
            load_test_suite(cfg),
            all_columns=all_columns,
            audit=False,
        )
    finally:
        db.conn.close()

    assert result.comparison is not None
    assert result.comparison.mismatched_patients == []
    assert result.comparison.accuracy_pct == 100.0
    assert result.patient_count > 0
