"""AutoCoder scaling ladder — in-process semantic search (the production path).

Measures the fhir4ds AutoCoder (dev tree) driven by a benchmark-only
endpoint that wraps medterm4ds.services.search.search(mode='semantic')
— the scored semantic engine the public HTTP surface serves. (The
shipped in_process adapter currently routes to the unscored discovery
service; see the baseline doc's findings section.)

Rungs:
  natural     — Synthea text-only concepts, 1k / 10k / 100k rows
                (realistic duplicate-heavy profile), cold + warm cache
  mixed       — 10k rows, 50% already coded (skip-cost rung)
  distinct    — adversarial all-distinct terminology names, 1k / 10k
Output: results JSON next to this script.
"""
import json, random, statistics, sys, time
from pathlib import Path

sys.path.insert(0, "/home/jmontavon/src/fhir4ds")

import duckdb
from fhir4ds.cql.loader.auto_coder import AutoCoder, AutoCoderConfig
from fhir4ds.cql.terminology.system_mappings import SOURCE_MNEMONIC_TO_URL
from fhir4ds.cql.terminology.types import SearchResult

HERE = Path(__file__).parent
WORKLOAD = HERE / "workload.ndjson"
TERM_NAMES = Path.home() / ".cache/medterm4ds/terminology/2026.11.05.1/lexical/2026.11.05.1/condition.json"

# resourceType -> (CodeableConcept path, category)
PATHS = {
    "Condition": ("code", "condition"),
    "MedicationRequest": ("medicationCodeableConcept", "medication"),
    "Observation": ("code", "observation"),
    "Procedure": ("code", "procedure"),
    "Immunization": ("vaccineCode", "medication"),
    "AllergyIntolerance": ("code", "condition"),
}


class BenchSemanticEndpoint:
    """TerminologyEndpoint wrapping the scored medterm4ds semantic engine."""

    def __init__(self):
        from medterm4ds.services.search import search
        self._search = search
        self.engine_calls = 0
        self.latencies: list[float] = []
        self.grades: list[str] = []

    def _one(self, text: str, category: str) -> list[SearchResult]:
        from medterm4ds.services.search import get_search_service
        srcs = None  # category filter is engine-side (result_types); keep all
        t0 = time.perf_counter()
        raw = self._search(text, mode="semantic", count=25,
                           result_types=self._result_types(category))
        self.latencies.append(time.perf_counter() - t0)
        self.engine_calls += 1
        out = []
        for r in raw:
            system = SOURCE_MNEMONIC_TO_URL.get(getattr(r, "source", None), None)
            out.append(SearchResult(
                system=system,
                code=getattr(r, "code", None),
                display=getattr(r, "display", None),
                score=float(getattr(r, "score", 0.0) or 0.0),
                match_grade=str(getattr(r, "match_grade", "ambiguous") or "ambiguous"),
                search_mode="semantic",
                index_version="2026.11.05.1",
            ))
            self.grades.append(out[-1].match_grade)
        return out

    @staticmethod
    def _result_types(category: str):
        rt = {"condition": "condition", "medication": "medication",
              "observation": "lab"}.get(category)
        return rt

    def search_text(self, query, category, *, mode="semantic"):
        return self._one(query, category)

    def search_batch(self, queries, *, mode="semantic"):
        return [self._one(q, c) for q, c in queries]


def rss_peak_mb() -> float:
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmHWM"):
                return float(line.split()[1]) / 1024
    except Exception:
        pass
    return -1.0


def make_resource(rt: str, text: str, precoded: bool = False) -> dict:
    path = PATHS[rt][0]
    cc: dict = {"text": text}
    if precoded:
        cc["coding"] = [{"system": "http://snomed.info/sct", "code": "000000",
                         "display": text}]
    return {"resourceType": rt, "id": "x", path: cc}


def run_rung(label, rows, *, warm_cache_coder=None, precoded_fraction=0.0):
    """One rung. rows: list[(rt, text)]. Returns metrics dict."""
    coder = warm_cache_coder
    if coder is None:
        ep = BenchSemanticEndpoint()
        con = duckdb.connect()  # fresh in-memory cache
        coder = AutoCoder(ep, con, config=AutoCoderConfig(
            search_mode="semantic", min_match_grade="probable", top_k=1))
    ep = coder._endpoint
    ep.latencies = []
    ep.engine_calls = 0

    n = len(rows)
    n_precoded = int(n * precoded_fraction)
    t0 = time.perf_counter()
    n_coded = 0
    for i, (rt, text) in enumerate(rows):
        r = make_resource(rt, text, precoded=(i < n_precoded))
        coder.augment_resource(r)
        path = PATHS[rt][0]
        if (r.get(path) or {}).get("coding"):
            n_coded += 1
    wall = time.perf_counter() - t0

    lat = sorted(ep.latencies)
    def pct(p):
        return lat[min(len(lat) - 1, int(len(lat) * p))] * 1000 if lat else None
    m = {
        "label": label,
        "rows": n,
        "precoded_rows": n_precoded,
        "wall_s": round(wall, 2),
        "rows_per_s": round(n / wall, 1) if wall else None,
        "engine_calls": ep.engine_calls,
        "distinct_texts": len({t for _, t in rows}),
        "dedup_hit_rate": round(1 - ep.engine_calls / max(1, n - n_precoded), 4),
        "engine_ms_p50": round(pct(0.50), 1) if lat else None,
        "engine_ms_p95": round(pct(0.95), 1) if lat else None,
        "engine_throughput_per_s": round(ep.engine_calls / wall, 1) if wall and ep.engine_calls else None,
        "coded_resources": n_coded - n_precoded,
        "rss_peak_mb": round(rss_peak_mb(), 0),
    }
    print(json.dumps(m), flush=True)
    return m, coder


def main():
    random.seed(42)
    rows_all = [(r["rt"], r["text"]) for r in
                (json.loads(l) for l in WORKLOAD.open())]
    random.shuffle(rows_all)  # stable type mix across rungs

    # Adversarial distinct terminology names
    names = json.load(TERM_NAMES.open())["names"]
    distinct_rows = [("Condition", t) for t in random.sample(names, 10_000)]

    results = []
    for n in (1_000, 10_000, 100_000):
        m, coder = run_rung(f"natural_{n}_cold", rows_all[:n])
        results.append(m)
        m2, _ = run_rung(f"natural_{n}_warm", rows_all[:n], warm_cache_coder=coder)
        results.append(m2)

    m, _ = run_rung("mixed_10k_50pct_coded", rows_all[:10_000],
                    precoded_fraction=0.5)
    results.append(m)

    for n in (1_000, 10_000):
        m, _ = run_rung(f"distinct_{n}", distinct_rows[:n])
        results.append(m)

    out = {
        "benchmark": "autocoding_scaling",
        "date": time.strftime("%Y-%m-%d"),
        "engine": "medterm4ds services.search.search(mode='semantic') "
                  "via BenchSemanticEndpoint (scored semantic, in-process)",
        "medterm4ds_version": "0.0.10",
        "terminology_release": "fhir4ds/terminology 2026.11.05.1",
        "config": {"search_mode": "semantic", "min_match_grade": "probable",
                   "top_k": 1},
        "runs": results,
    }
    (HERE / "results_autocoding.json").write_text(json.dumps(out, indent=1))
    print("\nwrote", HERE / "results_autocoding.json")


if __name__ == "__main__":
    main()
