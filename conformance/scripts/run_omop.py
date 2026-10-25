#!/usr/bin/env python3
"""OMOP mapping conformance suite (sectioned, spec-comp doctrine).

Sections per the design §7:
- schema: exact column-name sets per OMOP table view
- required: required-CDM-field non-null policy (ids, dates, concepts)
- grain: one-row-per-resource; union = sum of children
- mapping: concept resolution through the ConceptMap join (hits + 0-defaults),
  the measurement/observation value-type split, hash stability
- vd-conformance: every library VD parses + generates + executes against
  the demo bundle
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import fhir4ds  # noqa: E402
from fhir4ds.viewdef.omop_runner import OMOP_DIR, create_omop_views  # noqa: E402
from fhir4ds.viewdef.runner import load_manifest  # noqa: E402
from fhir4ds.viewdef.parser import parse_view_definition  # noqa: E402
from fhir4ds.viewdef.generator import SQLGenerator  # noqa: E402

# CDM 5.5 required fields per table (the columns that MUST be non-null
# given conformant input; concept ids may be 0 = no-map, never null).
REQUIRED_NON_NULL = {
    "person": ["person_id", "year_of_birth", "person_source_value"],
    "visit_occurrence": ["visit_occurrence_id", "person_id", "visit_start_date", "visit_end_date", "visit_source_value"],
    "condition_occurrence": ["condition_occurrence_id", "person_id", "condition_start_date", "condition_source_value"],
    "procedure_occurrence": ["procedure_occurrence_id", "person_id", "procedure_date", "procedure_source_value"],
    "drug_exposure": ["drug_exposure_id", "person_id", "drug_exposure_start_date", "drug_exposure_end_date", "drug_source_value"],
    "measurement": ["measurement_id", "person_id", "measurement_date", "measurement_source_value"],
    "observation": ["observation_id", "person_id", "observation_date", "observation_source_value"],
    "death": ["person_id", "death_date"],
}


def build_connection():
    con = fhir4ds.create_connection()
    con.execute("CREATE TABLE resources (resource JSON)")
    for line in (OMOP_DIR / "demo" / "resources.ndjson").read_text().splitlines():
        if line.strip():
            con.execute("INSERT INTO resources VALUES (?)", [line.strip()])
    create_omop_views(con, source_table="resources")
    return con


def main():
    results = {"total": 0, "passed": 0, "failed": 0, "sections": {}}

    def check(section, name, fn):
        results["total"] += 1
        try:
            fn()
            results["sections"].setdefault(section, []).append({"name": name, "ok": True})
            results["passed"] += 1
        except AssertionError as exc:
            results["sections"].setdefault(section, []).append(
                {"name": name, "ok": False, "error": str(exc)[:300]})
            results["failed"] += 1
        except Exception as exc:  # noqa: BLE001
            results["sections"].setdefault(section, []).append(
                {"name": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
            results["failed"] += 1

    expected = json.loads((OMOP_DIR / "demo" / "expected-rows.json").read_text())
    con = build_connection()

    # -- schema section ----------------------------------------------------
    for table, spec in expected.items():
        def schema_check(table=table, cols=spec["columns"]):
            got = [d[0] for d in con.execute(f"SELECT * FROM omop.{table} LIMIT 0").description]
            assert got == cols, f"{table}: {got} != {cols}"
        check("schema", f"{table} column set", schema_check)

    # -- required section --------------------------------------------------
    for table, reqs in REQUIRED_NON_NULL.items():
        def required_check(table=table, reqs=reqs):
            cols = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL)" for c in reqs)
            nulls = dict(zip(reqs, con.execute(f"SELECT {cols} FROM omop.{table}").fetchone()))
            bad = {k: v for k, v in nulls.items() if v}
            assert not bad, f"{table} null violations: {bad}"
        check("required", f"{table} required non-null", required_check)

    # concept columns never NULL (0 allowed)
    def concept_not_null():
        for table, cols in [
            ("person", ["gender_concept_id"]),
            ("visit_occurrence", ["visit_concept_id", "visit_type_concept_id"]),
            ("condition_occurrence", ["condition_concept_id", "condition_type_concept_id"]),
            ("drug_exposure", ["drug_concept_id", "drug_type_concept_id"]),
            ("measurement", ["measurement_concept_id", "measurement_type_concept_id"]),
            ("observation", ["observation_concept_id", "observation_type_concept_id"]),
            ("death", ["death_type_concept_id"]),
        ]:
            sel = ", ".join(f"count(*) FILTER (WHERE {c} IS NULL)" for c in cols)
            nulls = dict(zip(cols, con.execute(f"SELECT {sel} FROM omop.{table}").fetchone()))
            bad = {k: v for k, v in nulls.items() if v}
            assert not bad, f"{table} concept nulls: {bad}"
    check("required", "concept columns never null", concept_not_null)

    # -- grain section ------------------------------------------------------
    def grain_check():
        counts = {}
        for table in expected:
            counts[table] = con.execute(f"SELECT count(*) FROM omop.{table}").fetchone()[0]
        assert counts == {k: v["row_count"] for k, v in expected.items()}, counts
    check("grain", "row counts match fixture", grain_check)

    def union_sum_check():
        n = con.execute("SELECT count(*) FROM omop.drug_exposure").fetchone()[0]
        children = sum(
            con.execute(f"SELECT count(*) FROM omop.drug_exposure__{s}").fetchone()[0]
            for s in ("medication_request", "medication_statement", "medication_administration", "immunization")
        )
        assert n == children, f"{n} != {children}"
    check("grain", "union = sum of children", union_sum_check)

    def ri_check():
        orphans = con.execute("""
            SELECT count(*) FROM omop.condition_occurrence c
            LEFT JOIN omop.person p ON p.person_id = c.person_id
            WHERE p.person_id IS NULL
        """).fetchone()[0]
        assert orphans == 0, f"{orphans} orphaned conditions"
    check("grain", "referential integrity person<->events", ri_check)

    # -- mapping section ----------------------------------------------------
    def concept_hits():
        assert con.execute(
            "SELECT gender_concept_id FROM omop.person WHERE person_source_value='pat-001'"
        ).fetchone()[0] == 8507
        assert con.execute("SELECT drug_concept_id FROM omop.drug_exposure WHERE src='MedicationRequest'").fetchone()[0] == 1128940
        assert con.execute("SELECT measurement_concept_id FROM omop.measurement").fetchone()[0] == 3024929
    check("mapping", "concept hits resolve", concept_hits)

    def split_check():
        m = con.execute("SELECT count(*) FROM omop.measurement").fetchone()[0]
        o = con.execute("SELECT count(*) FROM omop.observation").fetchone()[0]
        obs_total = con.execute(
            "SELECT count(*) FROM resources WHERE json_extract_string(resource,'$.resourceType')='Observation'"
        ).fetchone()[0]
        assert m + o == obs_total, f"{m}+{o} != {obs_total}"
    check("mapping", "measurement+observation = observations", split_check)

    def hash_check():
        v1 = con.execute(
            "SELECT person_id FROM omop.person WHERE person_source_value='pat-001'").fetchone()[0]
        v2 = con.execute("SELECT hash('pat-001') & 9223372036854775807").fetchone()[0]
        assert v1 == v2 and 0 < v1 < 2**63
    check("mapping", "stable positive 63-bit keys", hash_check)

    # -- vd-conformance section ---------------------------------------------
    manifest = load_manifest(OMOP_DIR / "manifest.json")
    all_stems = sorted(manifest.get("views", {}))
    for stem in all_stems:
        def vd_check(stem=stem):
            vd = parse_view_definition(json.loads((OMOP_DIR / f"{stem}.json").read_text()))
            gen = SQLGenerator(source_table="resources")
            gen.view_schema = "omop"
            sql = gen.generate(vd)
            con.execute(f"SELECT * FROM ({sql}) LIMIT 1").fetchall()
        check("vd-conformance", f"{stem} parse+generate+execute", vd_check)

    ok = results["failed"] == 0
    # Standard report shape: {suite: {tests: [{name, result: {passed, error}}]}}
    # so run_all/_collect_stats fold this suite into the master summary.
    # Section names are prefixed onto test names to preserve the sectioning.
    all_tests = []
    for section, items in results["sections"].items():
        for item in items:
            all_tests.append({
                "name": f"{section}::{item['name']}",
                "result": {"passed": item["ok"], **({"error": item["error"]} if not item["ok"] else {})},
            })
    report = {
        "omop-mapping": {"tests": all_tests},
        "_meta": {
            "suite": "omop-mapping",
            "omop_version": "5.5",
            "total": results["total"],
            "passed": results["passed"],
            "failed": results["failed"],
            "sections": {k: {"passed": sum(1 for x in v if x["ok"]), "failed": sum(1 for x in v if not x["ok"])} for k, v in results["sections"].items()},
        },
    }
    out = REPO / "conformance" / "reports" / "omop_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nOMOP mapping conformance: {results['passed']}/{results['total']}")
    for section, agg in report["_meta"]["sections"].items():
        print(f"  {section}: {agg['passed']}/{agg['passed'] + agg['failed']}")
    if not ok:
        for section, items in results["sections"].items():
            for item in items:
                if not item["ok"]:
                    print(f"  FAIL [{section}] {item['name']}: {item.get('error', '')}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
