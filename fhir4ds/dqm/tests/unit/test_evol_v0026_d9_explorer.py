"""Evolution v0.0.26 — Domain 9 EXPLORER regression battery.

QA-D9E-001 (MEDIUM): audit evidence loses resource attribution whenever a
count feeds arithmetic or a retrieve-union count is aliased — three walker
blind spots, all silent degradation (never a wrong claim):

1. ``_extract_cte_names_from_ast`` never traversed ``SQLUnion`` operands nor
   ``SQLSelect.joins`` — the count subquery lives inside a LEFT JOIN LATERAL
   after lateral dedup (arithmetic-wrapped counts), and the union count's
   retrieve CTE references live inside a ``SQLUnion`` FROM. Zero source
   resource CTEs resolved -> population-mode evidence disappeared entirely.
2. ``_extract_audit_target`` never recursed into ``SQLBinaryOp`` — the
   ``+ 0`` / ``- count`` arithmetic wrapper hid the count subquery from the
   synthesized audit-target twin -> full-mode evidence carried target=null.
3. ``_count_unnest_row_select`` / the define-wrap twin synthesis only
   recognized the single-arm count-unnest shape — ``Count((A where ...)
   union (B where ...))`` (the canonical eCQM union numerator shape) stored
   no twin -> full-mode evidence lost targets even when population mode
   worked.

Covers both audit modes end-to-end through MeasureEvaluator with synthetic
patients (winners + out-of-window decoys).
"""

import json
import os
import sys
import tempfile

import duckdb
import pytest

sys.path.insert(0, os.path.expanduser("~/src/fhir4ds"))

from fhir4ds import register
from fhir4ds.dqm.evaluator import MeasureEvaluator

SNOMED = "http://snomed.info/sct"

CQL = """library D9E version '1.0.0'
using FHIR version '4.0.1'
valueset "NumProc VS": 'http://example.org/ValueSet/numproc'
valueset "Num2Proc VS": 'http://example.org/ValueSet/numproc2'
parameter "Measurement Period" Interval<DateTime>
context Patient

define "QualEnc": exists (Patient)
define "Initial Population": "QualEnc"
define "Denominator": "QualEnc"

define "NumCount":
  Count([Procedure: "NumProc VS"] P where P.performed during day of "Measurement Period")
define "Num2Count":
  Count([Procedure: "Num2Proc VS"] P where P.performed during day of "Measurement Period")
define "UnionCount":
  Count(([Procedure: "NumProc VS"] P where P.performed during day of "Measurement Period")
    union ([Procedure: "Num2Proc VS"] P where P.performed during day of "Measurement Period"))

define "ArithAlias": "NumCount" + 0
define "NumeratorArithAlias": "ArithAlias" >= 1
define "NumeratorArithInline":
  (Count([Procedure: "NumProc VS"] P where P.performed during day of "Measurement Period") + 0) >= 1
define "NumeratorArithTwoCounts":
  ("NumCount" + "Num2Count") >= 3
define "NumeratorUnion": "UnionCount" >= 3
"""

NUM_POPULATIONS = {
    "arith-alias": ("NumeratorArithAlias", {"pr-num-w1", "pr-num-w2"}),
    "arith-inline": ("NumeratorArithInline", {"pr-num-w1", "pr-num-w2"}),
    "arith-two-counts": (
        "NumeratorArithTwoCounts",
        {"pr-num-w1", "pr-num-w2", "pr-num2-w1"},
    ),
    "union-count": ("NumeratorUnion", {"pr-num-w1", "pr-num-w2", "pr-num2-w1"}),
}
DECOY = "pr-num-decoy"


def _rows():
    def proc(pid, rid, day, code):
        return {
            "resourceType": "Procedure", "id": rid, "status": "completed",
            "subject": {"reference": f"Patient/{pid}"},
            "performedDateTime": day,
            "code": {"coding": [{"system": SNOMED, "code": code}]},
        }
    return [
        {"resourceType": "Patient", "id": "p1", "birthDate": "1980-01-01",
         "gender": "female"},
        proc("p1", "pr-num-w1", "2026-03-10", "44493007"),
        proc("p1", "pr-num-w2", "2026-04-11", "44493007"),
        proc("p1", "pr-num-decoy", "2025-12-31", "44493007"),  # out of MP
        proc("p1", "pr-num2-w1", "2026-05-01", "73761001"),
    ]


def _measure(numerator_expr):
    return {
        "resourceType": "Measure", "id": "d9e",
        "library": ["http://example.org/Library/D9E|1.0.0"],
        "group": [{"id": "g1", "population": [
            {"code": {"coding": [{"code": "initial-population"}]},
             "criteria": {"expression": "Initial Population"}},
            {"code": {"coding": [{"code": "denominator"}]},
             "criteria": {"expression": "Denominator"}},
            {"code": {"coding": [{"code": "numerator"}]},
             "criteria": {"expression": numerator_expr}},
        ]}],
    }


def _valueset_files(tmpdir):
    paths = []
    for key, code in (("numproc", "44493007"), ("numproc2", "73761001")):
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


def _evidence_targets(result, patient="p1", column="numerator"):
    import pandas as pd  # noqa: F401 — dataframe access below needs pandas
    df = result.dataframe
    row = df[df["patient_id"] == patient]
    if row.empty:
        return set(), None
    cell = row.iloc[0].get(column)
    if not isinstance(cell, dict):
        return set(), cell
    targets = set()
    for item in cell.get("evidence") or []:
        for finding in item.get("findings") or []:
            t = finding.get("target")
            if isinstance(t, str) and t.startswith("Procedure/"):
                targets.add(t.split("/", 1)[1])
    return targets, cell


@pytest.fixture()
def con():
    connection = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    register(connection)
    # FHIR4-53: DuckDB default (strict) — generated SQL must be single-row.
    connection.execute(
        "CREATE OR REPLACE TABLE resources ("
        "id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)")
    yield connection
    connection.close()


@pytest.mark.parametrize("audit_mode", ["population", "full"])
@pytest.mark.parametrize("case", sorted(NUM_POPULATIONS))
def test_count_evidence_survives_arithmetic_and_union_shapes(con, case, audit_mode):
    """QA-D9E-001: count attribution must survive arithmetic wrappers and
    union counts in BOTH audit modes (red-first: all 8 cells failed)."""
    numerator_expr, expected_ids = NUM_POPULATIONS[case]
    tmpdir = tempfile.mkdtemp(prefix="d9x_regr_")
    with open(os.path.join(tmpdir, "d9e.cql"), "w") as f:
        f.write(CQL)
    for r in _rows():
        pr = (r["id"] if r["resourceType"] == "Patient"
              else r["subject"]["reference"].split("/")[1])
        con.execute("INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [r["id"], r["resourceType"], json.dumps(r), pr])
    ev = MeasureEvaluator(con)
    res = ev.evaluate(
        measure_bundle=_measure(numerator_expr),
        cql_library_path=os.path.join(tmpdir, "d9e.cql"),
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
        valueset_paths=_valueset_files(tmpdir),
        audit_mode=audit_mode,
    )
    targets, cell = _evidence_targets(res)
    assert isinstance(cell, dict) and cell.get("result") is True, (
        f"{case}/{audit_mode}: numerator must be true (cell={cell!r})")
    assert targets == expected_ids, (
        f"{case}/{audit_mode}: evidence must cite exactly the winning "
        f"resources {sorted(expected_ids)}, got {sorted(targets)}")
    assert DECOY not in targets, (
        f"{case}/{audit_mode}: out-of-MP decoy must not be cited")


CQL_SHADOW = """library D9ES version '1.0.0'
using FHIR version '4.0.1'
valueset "NumProc VS": 'http://example.org/ValueSet/numproc'
parameter "Measurement Period" Interval<DateTime>
context Patient

define "QualEnc": exists (Patient)
define "Initial Population": "QualEnc"
define "Denominator": "QualEnc"
// A define whose NAME collides with the retrieve query alias below —
// the alias must stay locally bound (QA-D9E-001 cte_manager fix).
define "P": 1
define "Numerator":
  exists ([Procedure: "NumProc VS"] P where P.performed during day of "Measurement Period")
"""


@pytest.mark.parametrize("audit_mode", ["population", "full"])
def test_query_alias_shadowing_definition_name(con, audit_mode):
    """QA-D9E-001: ``_rewrite_cte_references`` must not rewrite alias-bound
    references that shadow a define name; ``referenced_definitions`` must not
    record the alias as a define reference (wrong-attribute evidence)."""
    tmpdir = tempfile.mkdtemp(prefix="d9x_shadow_")
    with open(os.path.join(tmpdir, "d9es.cql"), "w") as f:
        f.write(CQL_SHADOW)
    for r in _rows():
        pr = (r["id"] if r["resourceType"] == "Patient"
              else r["subject"]["reference"].split("/")[1])
        con.execute("INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [r["id"], r["resourceType"], json.dumps(r), pr])
    ev = MeasureEvaluator(con)
    measure = _measure("Numerator")
    res = ev.evaluate(
        measure_bundle=measure,
        cql_library_path=os.path.join(tmpdir, "d9es.cql"),
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
        valueset_paths=_valueset_files(tmpdir)[:1],
        audit_mode=audit_mode,
    )
    row = res.dataframe[res.dataframe["patient_id"] == "p1"].iloc[0]
    cell = row["numerator"]
    assert isinstance(cell, dict) and cell.get("result") is True, cell
    targets = {
        t.split("/", 1)[1]
        for item in cell.get("evidence") or []
        for finding in item.get("findings") or []
        if isinstance((t := finding.get("target")), str) and t.startswith("Procedure/")
    }
    assert targets == {"pr-num-w1", "pr-num-w2"}, targets
    assert "pr-num-decoy" not in targets


def test_subject_list_report_names_population_members(con):
    """QA-D9E-001: subject-list MeasureReports must carry population
    membership via contained List resources + subjectResults references
    (FHIR R4), honoring the same attribution masks as summary_report."""
    tmpdir = tempfile.mkdtemp(prefix="d9x_sl_")
    with open(os.path.join(tmpdir, "d9e.cql"), "w") as f:
        f.write(CQL)
    extra = {"resourceType": "Patient", "id": "p2", "birthDate": "1975-05-05",
             "gender": "male"}
    con.execute("INSERT INTO resources VALUES (?,?,?::JSON,?)",
                [extra["id"], extra["resourceType"], json.dumps(extra), "p2"])
    for r in _rows():
        pr = (r["id"] if r["resourceType"] == "Patient"
              else r["subject"]["reference"].split("/")[1])
        con.execute("INSERT INTO resources VALUES (?,?,?::JSON,?)",
                    [r["id"], r["resourceType"], json.dumps(r), pr])
    ev = MeasureEvaluator(con)
    res = ev.evaluate(
        measure_bundle=_measure("NumeratorArithAlias"),
        cql_library_path=os.path.join(tmpdir, "d9e.cql"),
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
        valueset_paths=_valueset_files(tmpdir),
        audit_mode="population",
    )
    report = ev.to_measure_report(
        res, period_start="2026-01-01", period_end="2026-12-31",
        report_type="subject-list")
    assert report["type"] == "subject-list"
    contained = {c["id"]: c for c in report.get("contained", [])}
    assert contained, "subject-list report must contain member Lists"
    by_code = {
        p["code"]["coding"][0]["code"]: p
        for g in report["group"] for p in g["population"]
    }
    for code in ("initial-population", "denominator", "numerator"):
        ref = by_code[code].get("subjectResults", {}).get("reference", "")
        assert ref.startswith("#") and ref[1:] in contained, (code, ref)
    def _members(code):
        ref = by_code[code]["subjectResults"]["reference"]
        return {e["item"]["reference"] for e in contained[ref[1:]]["entry"]}
    assert _members("initial-population") == {"Patient/p1", "Patient/p2"}
    assert _members("denominator") == {"Patient/p1", "Patient/p2"}
    assert _members("numerator") == {"Patient/p1"}, "p2 has no numerator evidence"


def test_subject_list_requires_patient_column(con):
    """QA-D9E-001: subject-list over a frame without patient_id fails typed."""
    import pandas as pd
    ev = MeasureEvaluator(con)
    from fhir4ds.dqm.evaluator import MeasureResult
    mr = MeasureResult(
        dataframe=pd.DataFrame([{"initial_population": True}]),
        populations={}, parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
        measure_url="u", pop_map=None)
    mr.pop_map = None
    from fhir4ds.dqm.errors import DQMError

    with pytest.raises(DQMError, match="No evaluation has been run yet"):
        ev.to_measure_report(mr, report_type="subject-list")


def test_mongo_jsonable_nat_renders_none_not_nat_string():
    """QA-D9E-002 twin: pandas NaT is a datetime SUBCLASS, so the datetime
    isoformat/str branch must run AFTER the isna guard — NaT renders None,
    never the string 'NaT'; datetimes render identically in both backends."""
    import numpy as np
    import pandas as pd

    from fhir4ds.dqm.hapi_materialization import _compact_row as _hapi_row
    from fhir4ds.dqm.mongo_materialization import _compact_row as _mongo_row
    from fhir4ds.dqm.mongo_materialization import _jsonable
    for nat in (pd.NaT, np.datetime64("NaT")):
        assert _jsonable(nat) is None, nat
    ts = pd.Timestamp("2026-03-10T08:30:00")
    assert _jsonable(ts) == str(ts.to_pydatetime())
    # compact-row twin parity on a NaN/NaT-bearing audit cell
    cell = {"result": True, "when": pd.NaT, "score": float("nan")}
    h = _hapi_row({"patient_id": "p1", "numerator": cell})
    m = _mongo_row({"patient_id": "p1", "numerator": cell})
    assert json.dumps(h, default=str, sort_keys=True) == json.dumps(
        m, default=str, sort_keys=True), (h, m)
    assert "NaN" not in json.dumps(m) and "NaT" not in json.dumps(m)

