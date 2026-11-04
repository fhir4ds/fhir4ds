#!/usr/bin/env python3
"""Assemble the OMOP scaling ladder markdown report from result JSONs.

  python3 benchmarks/scaling/make_omop_report.py [--out benchmarks/baselines/omop_v55_scaling_2026.md]

Reads benchmarks/scaling/results/omop/*.json (per-rung staging + workload
results + ladder summary) and renders the capacity statement, exec tables,
rung ratios and EXPLAIN hot-operator digest. The narrative optimisation
ranking is authored in the report by the campaign operator; this script
provides the evidence tables.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results" / "omop"
FINAL_TABLES = ["person", "visit_occurrence", "condition_occurrence",
               "procedure_occurrence", "drug_exposure", "device_exposure",
               "measurement", "observation", "death"]


def load(name):
    p = RESULTS / name
    return json.loads(p.read_text()) if p.exists() else None


def render_profile_tree(node, depth=0):
    lines = [f"{'  ' * depth}{node.get('operator_name') or '<root>'}"
             f"  [{(node.get('operator_timing') or 0) * 1000:,.1f}ms]"
             f" rows={node.get('operator_cardinality')}"]
    for ch in node.get("children") or []:
        lines.extend(render_profile_tree(ch, depth + 1))
    return lines


def hot_operators(node, out):
    name = node.get("operator_name") or "<root>"
    t = (node.get("operator_timing") or 0) * 1000
    if name not in ("EXPLAIN_ANALYZE",) and t > 0:
        out.append((t, name, node.get("operator_cardinality")))
    for ch in node.get("children") or []:
        hot_operators(ch, out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",
                    default=str(Path(__file__).resolve().parent.parent
                                / "baselines" / "omop_v55_scaling_2026.md"))
    args = ap.parse_args()

    summary = load("ladder_summary.json") or {"rungs": {}}
    # Ratios can be derived from per-rung JSONs even when the summary was
    # written by a split invocation (--rungs subsets).
    rung_jsons = sorted(
        int(p.name.split("_")[0].removeprefix("rung"))
        for p in RESULTS.glob("rung*_omop.json"))
    rungs = [r for r in rung_jsons
             if (RESULTS / f"rung{r}_omop.json").exists()]

    lines: list[str] = []
    lines.append("# OMOP v5.5 ViewDefinition / SQLQuery — scaling ladder"
                 " (Synthea 1k→10k→100k)")
    lines.append("")
    lines.append("*Campaign 2026-11-02..05 (Joel). Harness:"
                 " `benchmarks/scaling/run_omop_ladder.py` — one command"
                 " runs stage → workload A (OMOP composition) → workload B"
                 " (drug-exposure SQLQuery sample) → EXPLAIN legs.*")
    lines.append("")
    lines.append("**Headline metric is EXEC-ONLY** (Joel ruling 2026-10-29):"
                 " median-of-3 CTAS wall time (`CREATE TABLE ... AS SELECT *`"
                 " — forces full evaluation, no column pruning)."
                 " Parse/generate/CREATE-VIEW are reported as compile"
                 " diagnostics and never folded into speedup or per-patient"
                 " figures. Staging is a separate, once-per-rung phase.")
    lines.append("")

    # ---- staging table
    lines.append("## Rung staging (diagnostics)")
    lines.append("")
    lines.append("| Rung | Patients | Resources staged | JSON MB | Stage wall (s) "
                 "| Stage peak RSS (MB) | DB file (MB) |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in rungs:
        s = load(f"rung{r}_staging.json")
        if not s:
            continue
        lines.append(
            f"| {r:,} | {s['patients_requested']:,} | {s['resources']:,} "
            f"| {s['json_bytes_staged'] / 2**20:,.0f} | {s['stage_wall_s']:,.0f} "
            f"| {s['stage_peak_rss_mb']:,.0f} | {s['db_file_mb']:,.1f} |")
    lines.append("")

    # ---- workload A exec
    lines.append("## Workload A — OMOP v5.5 composition (exec-only, ms)")
    lines.append("")
    header = "| Rung | " + " | ".join(FINAL_TABLES) + " | total | rows | peak RSS (MB) |"
    lines.append(header)
    lines.append("|" + "---|" * (len(FINAL_TABLES) + 4))
    for r in rungs:
        rec = load(f"rung{r}_omop.json")
        if not rec:
            continue
        cells = []
        for t in FINAL_TABLES:
            e = rec["exec_final_tables"].get(t)
            cells.append(f"{e['exec_ms_median']:,.0f}" if e else "-")
        total = sum(v["exec_ms_median"]
                    for v in rec["exec_final_tables"].values())
        rows_total = rec.get("rows_total") or sum(
            v["rows"] for v in rec["exec_final_tables"].values())
        lines.append(f"| {r:,} | " + " | ".join(cells)
                     + f" | {total:,.0f} | {rows_total:,} "
                     f"| {rec.get('peak_rss_mb', 0):,.0f} |")
    lines.append("")

    # ---- source-view exec (pure VD)
    lines.append("### Per-source ViewDefinition exec (pure-VD view, 1 pass)")
    lines.append("")
    src_stems = None
    for r in rungs:
        rec = load(f"rung{r}_omop.json")
        if rec:
            src_stems = list(rec["exec_source_views"])
            break
    if src_stems:
        lines.append("| Rung | " + " | ".join(s.replace("-source-view", "")
                                              for s in src_stems) + " |")
        lines.append("|" + "---|" * (len(src_stems) + 1))
        for r in rungs:
            rec = load(f"rung{r}_omop.json")
            if not rec:
                continue
            cells = [f"{rec['exec_source_views'][s]['exec_ms']:,.0f}"
                     for s in src_stems]
            lines.append(f"| {r:,} | " + " | ".join(cells) + " |")
        lines.append("")

    # ---- workload B exec
    lines.append("## Workload B — drug-exposure SQLQuery sample (exec-only)")
    lines.append("")
    lines.append("| Rung | exec ms (median of 3) | rows | peak RSS (MB) |")
    lines.append("|---|---|---|---|")
    for r in rungs:
        rec = load(f"rung{r}_drug_sqlquery.json")
        if not rec:
            continue
        e = rec["exec"]
        lines.append(f"| {r:,} | {e['exec_ms_median']:,.0f} | {e['rows']:,} "
                     f"| {rec['peak_rss_mb']:,.0f} |")
    lines.append("")

    # ---- ratios (superlinearity visibility), derived from per-rung JSONs
    # so split ladder invocations (--rungs subsets) still report correctly.
    ratios = {}
    for a, b in zip(rungs, rungs[1:]):
        ra = load(f"rung{a}_omop.json")
        rb_ = load(f"rung{b}_omop.json")
        if not (ra and rb_):
            continue
        ta = sum(v["exec_ms_median"] for v in ra["exec_final_tables"].values())
        tb = sum(v["exec_ms_median"] for v in rb_["exec_final_tables"].values())
        ratios[f"{a}->{b}"] = {
            "omop": {
                "patients_ratio": round(b / a, 2),
                "exec_time_ratio": round(tb / ta, 2) if ta else None,
                "per_patient_growth": round((tb / b) / (ta / a), 2)
                if ta else None,
                "peak_rss_ratio": round(
                    rb_["peak_rss_mb"] / ra["peak_rss_mb"], 2)
                if ra.get("peak_rss_mb") and rb_.get("peak_rss_mb")
                else None,
            }
        }
        da = load(f"rung{a}_drug_sqlquery.json")
        db_ = load(f"rung{b}_drug_sqlquery.json")
        if da and db_:
            dta = da["exec"]["exec_ms_median"]
            dtb = db_["exec"]["exec_ms_median"]
            ratios[f"{a}->{b}"]["drug_sqlquery"] = {
                "patients_ratio": round(b / a, 2),
                "exec_time_ratio": round(dtb / dta, 2) if dta else None,
                "per_patient_growth": round((dtb / b) / (dta / a), 2)
                if dta else None,
                "peak_rss_ratio": round(
                    db_["peak_rss_mb"] / da["peak_rss_mb"], 2),
            }
    if ratios:
        lines.append("## Rung ratios (superlinearity visibility)")
        lines.append("")
        lines.append("| Transition | workload | patients x | exec time x | "
                     "per-patient growth | peak RSS x |")
        lines.append("|---|---|---|---|---|---|")
        for tr, wl in ratios.items():
            for w, v in wl.items():
                lines.append(
                    f"| {tr} | {w} | {v['patients_ratio']} "
                    f"| {v['exec_time_ratio']} | {v['per_patient_growth']} "
                    f"| {v['peak_rss_ratio']} |")
        lines.append("")

    # ---- structural SQL metrics (deterministic; corpus-independent)
    lines.append("## Generated-SQL structural metrics")
    lines.append("")
    lines.append("Cost shape of each source ViewDefinition's generated SQL:"
                 " every `collection=false` column emits a runtime type-guard"
                 " CASE that re-evaluates the column's FHIRPath 1-3 extra"
                 " times (count check + `type().name` check + extraction),"
                 " and every `fhirpath()` call re-parses the resource JSON.")
    lines.append("")
    lines.append("| View | fhirpath() | fhirpath_text() | SQL KB |")
    lines.append("|---|---|---|---|")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from fhir4ds.viewdef.runner import generate_view_sql  # noqa: E402
    omop_dir = (Path(__file__).resolve().parent.parent.parent / "fhir4ds"
                / "viewdef" / "resources" / "omop")
    for stem in sorted(p.stem for p in omop_dir.glob("*-source-view.json")):
        sql = generate_view_sql(omop_dir / f"{stem}.json", "resources")
        lines.append(f"| {stem} | {sql.count('fhirpath(')} "
                     f"| {sql.count('fhirpath_text(')} "
                     f"| {len(sql) / 1024:,.0f} |")
    lines.append("")

    # ---- EXPLAIN digest
    lines.append("## EXPLAIN ANALYZE digest (hot operators)")
    lines.append("")
    for prof in sorted((RESULTS / "profiles").glob("*_profile.json")):
        tag = prof.name.replace("_profile.json", "")
        if "_explain" not in tag:
            continue
        payload = json.loads(prof.read_text())
        ops: list[tuple[float, str, int]] = []
        hot_operators(payload, ops)
        ops.sort(reverse=True)
        lines.append(f"### {tag} — latency "
                     f"{(payload.get('latency') or 0) * 1000:,.0f}ms")
        lines.append("")
        for t, name, card in ops[:8]:
            lines.append(f"- {name}: {t:,.1f}ms (rows={card})")
        lines.append("")
        (RESULTS / "profiles" / prof.name.replace("_profile.json",
                                                  "_explain.txt")
         ).write_text("\n".join(render_profile_tree(payload)) + "\n")

    # ---- capacity statement + optimisation candidates (campaign narrative)
    lines.append("## Capacity statement")
    lines.append("")
    lines.append(
        "Read as: patients vs exec-only time vs peak RSS, at DuckDB "
        "`memory_limit=8GB`, zstd-Parquet-backed source view (cold scan "
        "per query), 16 threads, shared 62GB host with swap-free guards. "
        "Exec = CTAS of each final OMOP table (median of reps; see tables "
        "above). RSS is the leg process peak — bounded by the 8GB DuckDB "
        "limit plus ~1-2GB overhead, INDEPENDENT of corpus size once past "
        "the buffer limit: at 100k patients the peak was ~4GB because "
        "DuckDB streams Parquet and spills CTAS results to temp rather "
        "than buffering. The wall for this workload is CPU (fhirpath "
        "extraction per row), not memory: 100k patients fit comfortably; "
        "the practical scaling limit is time (linear-ish in the "
        "corpus-linear component of exec) and host co-tenancy, not RSS.")
    lines.append("")
    lines.append("## Ranked optimisation candidates (EXPLAIN evidence)")
    lines.append("")
    lines.append(
        "Prior art noted, not rediscovered (CQL-translator side, from "
        "earlier reviews): (a) repeated per-retrieve scans wanting a shared "
        "CTE cache; (b) SELECT DISTINCT over the full resource JSON in "
        "every retrieve CTE; (c) correlated per-row subqueries in the "
        "shared `_patients` CTE. The candidates below are the "
        "ViewDefinition/SQLQuery path's own list.")
    lines.append("")
    lines.append(
        "1. **Guard/extract duplication in generated column SQL (HIGH).** "
        "Every `collection=false` column emits a CASE whose runtime type "
        "guard re-evaluates the column's FHIRPath 1-3 extra times (count "
        "check via `fhirpath()`, `type().name` check via `fhirpath()`, "
        "then `fhirpath_text()` extraction) — 47-72 `fhirpath()` calls per "
        "row per source view (see structural metrics). EXPLAIN at 10k: the "
        "nested PROJECTION layers dominate (119s operator-time in "
        "drug_exposure, 287s in observation, vs ~26-43s wall). Fix: emit "
        "each path ONCE into a lateral/projection and guard on its result. "
        "Expected: ~2-4x fewer fhirpath evaluations per row.")
    lines.append(
        "2. **Per-call JSON re-parse inside fhirpath UDFs (HIGH).** Each "
        "`fhirpath(resource, expr)` call parses the full resource JSON "
        "string from scratch; one MedicationRequest row parses its own "
        "JSON ~73 times across the view's columns (60 fhirpath() + 13 "
        "fhirpath_text()). Compounds with candidate 1. Fix options: a "
        "combined guard+extract UDF returning count/types/first-value in "
        "one parse, or generator-side single-evaluation.")
    lines.append(
        "3. **resourceType filter scans the decoded JSON of every row "
        "(MEDIUM).** Every source view starts `WHERE "
        "json_extract_string(resource,'$.resourceType')='X'` — EXPLAIN "
        "shows ~10s per scan at 10k (8.1M rows) for FILTER operators, "
        "multiplied by every view/table reference in the composition. "
        "Fix: persist `resourceType` as a real column beside the JSON (or "
        "partition the Parquet by resourceType) so the filter becomes "
        "metadata/zonemap pruning. Expected: eliminates ~10% of each "
        "scan and all json_extract filter cost.")
    lines.append(
        "4. **omop_conceptmap recomputed per referencing view (MEDIUM).** "
        "The flattened ConceptMap (108,683 rows via UNNEST of 546 chunk "
        "resources) is a VIEW; every event table's join re-runs the "
        "unnest chain (EXPLAIN: 656ms scan+unnest per reference at 10k; "
        "9 references per workload A pass). Fix: materialize once per "
        "composition (`CREATE TABLE omop.omop_conceptmap AS ...`) — the "
        "runner already infers materialization order.")
    lines.append(
        "5. **Terminology double-staging fan-out (found & fixed in the "
        "harness).** Staging both the monolithic map's gender/ActCode/"
        "condition-category groups AND conceptmap-supplements.json "
        "duplicated those mappings and fanned `person` to exactly 2 rows "
        "per patient (EXPLAIN HASH_JOIN rows=2N over N patients). The "
        "converter now chunks only RxNorm+CVX groups.")
    lines.append("")

    Path(args.out).write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}")
if __name__ == "__main__":
    main()
