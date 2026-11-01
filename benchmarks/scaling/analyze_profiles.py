#!/usr/bin/env python3
"""Structural complexity scoring + EXPLAIN ANALYZE operator attribution.

Two independent analyses over the artifacts produced by run_measures.py:

1. STRUCTURAL SCORE — counts, per generated population SQL, the resource-touch
   operations that drive columnar execution cost: resource-table scan sites
   (total and per resourceType), SELECT DISTINCT count, json_extract sites,
   CAST-to-DATE/TIMESTAMP sites, interval/overlap predicate sites, joins and
   derived tables (CTEs). Yields a composite score used as the complexity
   classifier INSTEAD of SQL bytes.

2. OPERATOR ATTRIBUTION — parses the JSON operator profile captured by
   `EXPLAIN ANALYZE` and attributes INCLUSIVE time to exclusive per-operator
   time, bucketed into: resource scans, other scans, joins, distinct/aggregate,
   expression evaluation (fhirpath/coding_matches/in_valueset/json_extract),
   CTE materialization, ordering, other.

Usage:
  python3 benchmarks/scaling/analyze_profiles.py            # full report data
  python3 benchmarks/scaling/analyze_profiles.py --json     # machine-readable
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
SCALING = BENCH / "scaling"
RESULTS = SCALING / "results"
SQL_DIR = RESULTS / "sql"
PROFILES = RESULTS / "profiles"

INTERVAL_PATTERNS = [
    "intervalContains",
    "intervalOverlaps",
    "intervalBeforePrecise",
    "intervalAfterPrecise",
    "intervalIncludesPrecise",
    "intervalIntersect",
    "intervalExcept",
    "intervalUnion",
    "intervalStart",
    "intervalEnd",
    "cqlSameOrBeforeP",
    "cqlSameOrAfterP",
    "cqlSameAsP",
    "cqlDurationBetween",
    "cqlDifferenceBetween",
    "expand_intervals",
    "collapse_intervals",
]

# Composite score weights (documented; chosen so that operation types that
# force per-row evaluation or sort/dedup work weigh more than cheap projection).
# NOTE: valueset/coding-match and interval-call counts are reported as
# SECONDARY counters but deliberately EXCLUDED from the score — they do not
# predict measured cost (CMS2 has ~8k such calls and is ~15x cheaper per
# resource than CMS130) because they evaluate against already-filtered rows.
WEIGHTS = {
    "scan_site": 1.0,
    "select_distinct": 1.0,
    "json_extract": 0.25,
    "date_cast": 0.5,
    "join": 0.5,
    "derived_table": 0.5,
}


def structural_score(sql: str) -> dict:
    scan_sites = len(re.findall(r"\bFROM resources\b", sql))
    by_type = {}
    for m in re.finditer(r"resourceType\s*=\s*'([A-Za-z]+)'", sql):
        by_type[m.group(1)] = by_type.get(m.group(1), 0) + 1
    distinct = len(re.findall(r"\bSELECT DISTINCT\b", sql, re.IGNORECASE))
    json_extract = len(re.findall(r"\bjson_extract", sql))
    date_cast = len(
        re.findall(r"\b(?:TRY_)?CAST\s*\([^()]*\bAS\s+(?:DATE|TIMESTAMP)\s*\)", sql, re.IGNORECASE)
    )
    interval_pred = sum(len(re.findall(rf"\b{re.escape(p)}\s*\(", sql)) for p in INTERVAL_PATTERNS)
    joins = len(re.findall(r"\bJOIN\b", sql, re.IGNORECASE))
    derived = len(re.findall(r"\bAS\s*\(", sql))  # CTE bodies + scalar/lateral subqueries
    vc = len(re.findall(r"\b(in_valueset|coding_matches|coding_matches_exact)\s*\(", sql))

    score = (
        WEIGHTS["scan_site"] * scan_sites
        + WEIGHTS["select_distinct"] * distinct
        + WEIGHTS["json_extract"] * json_extract
        + WEIGHTS["date_cast"] * date_cast
        + WEIGHTS["join"] * joins
        + WEIGHTS["derived_table"] * derived
    )
    return {
        "chars": len(sql),
        "scan_sites": scan_sites,
        "scan_sites_by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "select_distinct": distinct,
        "json_extract": json_extract,
        "date_casts": date_cast,
        "joins": joins,
        "derived_tables": derived,
        "interval_predicates": interval_pred,
        "valueset_or_coding_matches": vc,
        "score": round(score, 1),
    }


# --------------------------------------------------------------------------
# Operator attribution
# --------------------------------------------------------------------------

BUCKET_BY_OP = {
    "HASH_JOIN": "joins",
    "NESTED_LOOP_JOIN": "joins",
    "BLOCKWISE_NL_JOIN": "joins",
    "PIECEWISE_MERGE_JOIN": "joins",
    "ASOF_JOIN": "joins",
    "CROSS_PRODUCT": "joins",
    "HASH_GROUP_BY": "distinct_aggregate",
    "PERFECT_HASH_GROUP_BY": "distinct_aggregate",
    "UNGROUPED_AGGREGATE": "distinct_aggregate",
    "DISTINCT": "distinct_aggregate",
    "ORDER_BY": "order",
    "TOP_N": "order",
    "WINDOW": "window",
    "STREAMING_WINDOW": "window",
    "CTE": "cte_scan",
    "MATERIALIZED_CTE": "cte_scan",
    "RECURSIVE_CTE": "cte_scan",
    "UNNEST": "unnest",
    "DELIM_JOIN": "joins",
    "COLUMN_DATA_SCAN": "other_scans",
    "DELIM_SCAN": "other_scans",
}

EXPR_HINTS = re.compile(
    r"fhirpath|coding_matches|in_valueset|json_extract|dateComponent|"
    r"interval|quantity|to_date|CAST\(",
    re.IGNORECASE,
)


def _node_extra(node: dict) -> str:
    extra = node.get("extra_info")
    if isinstance(extra, dict):
        return json.dumps(extra)[:4000]
    return str(extra or "")


def _walk(node: dict, out: list[dict]) -> None:
    op = node.get("operator_name") or ""
    timing = node.get("operator_timing")
    children = node.get("children") or []
    if isinstance(timing, (int, float)):
        child_sum = sum(c.get("operator_timing") or 0 for c in children)
        extra = _node_extra(node)
        if op == "SEQ_SCAN":
            bucket = "resource_scans" if "resources" in extra else "other_scans"
        elif op in ("PROJECTION", "FILTER", "EXPRESSION_SCAN"):
            bucket = "expression_eval" if EXPR_HINTS.search(extra) else "expression_other"
        elif op in BUCKET_BY_OP:
            bucket = BUCKET_BY_OP[op]
        else:
            bucket = "other"
        out.append(
            {
                "operator": op,
                "bucket": bucket,
                "inclusive_s": timing,
                "exclusive_s": max(0.0, timing - child_sum),
                "rows": node.get("operator_cardinality"),
                "extra": extra[:300],
            }
        )
    for c in children:
        _walk(c, out)


def operator_attribution(profile: dict) -> dict:
    nodes: list[dict] = []
    _walk(profile, nodes)
    total = max((n["inclusive_s"] for n in nodes), default=0.0)
    buckets: dict[str, float] = {}
    for n in nodes:
        buckets[n["bucket"]] = buckets.get(n["bucket"], 0.0) + n["exclusive_s"]
    summed = sum(buckets.values()) or 1.0
    # Resource-table scan statistics. NOTE: with parallel execution the
    # per-node operator_timing values are summed across worker threads, so
    # absolute seconds are NOT wall-clock; shares are meaningful, and
    # cumulative_rows_scanned is a true per-query total.
    resource_scan_nodes = [n for n in nodes if n["bucket"] == "resource_scans"]
    scan_output_rows = sum(n["rows"] or 0 for n in resource_scan_nodes)
    return {
        "latency_s": profile.get("latency"),
        "root_inclusive_s": total,
        "exclusive_total_s": summed,
        "buckets_s": {k: round(v, 4) for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])},
        "buckets_pct": {
            k: round(100.0 * v / summed, 1)
            for k, v in sorted(buckets.items(), key=lambda kv: -kv[1])
        },
        "timing_note": "operator timings are summed across parallel worker threads",
        "resource_scan_sites_executed": len(resource_scan_nodes),
        "resource_scan_output_rows": scan_output_rows,
        "peak_buffer_mb": round((profile.get("system_peak_buffer_memory") or 0) / 2**20, 1),
        "peak_temp_dir_mb": round((profile.get("system_peak_temp_dir_size") or 0) / 2**20, 1),
        "rows_scanned": profile.get("cumulative_rows_scanned"),
        "rows_returned": profile.get("rows_returned"),
        "node_count": len(nodes),
        "top_nodes": sorted(nodes, key=lambda n: -n["exclusive_s"])[:10],
    }


def find_profile(tag: str, mid: str) -> Path | None:
    p = PROFILES / f"{tag}_{mid}_profile.json"
    return p if p.exists() else None


def main() -> None:
    emit_json = "--json" in sys.argv
    measures = [m for m in ("CMS68", "CMS130", "CMS2") if (SQL_DIR / f"{m}.sql").exists()]
    result = {"structural": {}, "attribution": {}}
    for mid in measures:
        result["structural"][mid] = structural_score((SQL_DIR / f"{mid}.sql").read_text())

    rungs = {}
    for path in sorted(RESULTS.glob("rung*.json")):
        tag = path.stem
        d = json.loads(path.read_text())
        rungs[tag] = {
            "patients": d.get("actual_patients"),
            "resources": d.get("resources_loaded"),
            "memory_limit": d.get("duckdb_memory_limit"),
            "peak_rss_mb": d.get("peak_rss_mb"),
            "measures": {
                mid: {
                    "exec_ms_median": m.get("exec_ms_median"),
                    "exec_ms": m.get("exec_ms"),
                }
                for mid, m in d.get("measures", {}).items()
                if m.get("status") == "success"
            },
        }
        for mid in d.get("measures", {}):
            prof = find_profile(tag, mid)
            if prof:
                result["attribution"].setdefault(f"{tag}/{mid}", operator_attribution(
                    json.loads(prof.read_text())
                ))
    result["rungs"] = rungs

    if emit_json:
        print(json.dumps(result, indent=2))
        return

    print("STRUCTURAL SCORE")
    for mid, s in result["structural"].items():
        print(f"  {mid}: score={s['score']} scans={s['scan_sites']} "
              f"distinct={s['select_distinct']} json={s['json_extract']} "
              f"datecasts={s['date_casts']} interval={s['interval_predicates']} "
              f"joins={s['joins']} derived={s['derived_tables']} "
              f"vs/coding={s['valueset_or_coding_matches']}")
        print(f"    by type: {s['scan_sites_by_type']}")
    print("\nOPERATOR ATTRIBUTION")
    for key, a in result["attribution"].items():
        print(f"  {key}: latency={a['latency_s']}s buckets%={a['buckets_pct']} "
              f"merged={a['merged_tables'] if 'merged_tables' in a else ''}")


if __name__ == "__main__":
    main()
