"""Shared utilities for the OMOP v5.5 ViewDefinition / SQLQuery scaling ladder.

Campaign (Joel, 2026-11-02): 1k -> 10k -> 100k Synthea patients, OMOP v5.5
ViewDefinition set + the drug-exposure SQLQuery sample, exec-only headline
metrics, peak-RSS probing with a hard cap, EXPLAIN-derived optimisation
candidates.

Corpus layout (durable, on /mnt/d/scaling-data):

  /mnt/d/scaling-data/omop-scaling/
    s100k/                     Synthea generation (seed 20261102, 100k patients,
                               per-patient bundle JSONs, OMOP-consumed types only
                               via exporter.fhir.included_resources)
    terminology/               chunked RxNorm ConceptMap + supplements (NDJSON)
    db/rung<N>.duckdb          staged resources table, one file per rung

Rung corpora are deterministic nested prefixes: the sorted patient bundle
files of s100k/output/fhir minus the *information* files.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BENCHMARKS_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SCALING_DATA = Path("/mnt/d/scaling-data/omop-scaling")
SYNTHEA_DIR = SCALING_DATA / "s100k" / "output" / "fhir"
TERMINOLOGY_DIR = SCALING_DATA / "terminology"
# Staged rung DBs are REGENERABLE artifacts (one staging pass from the
# durable corpus). They live on the local ext4 root, not drvfs: measured
# ~5x faster writes and the 100k rung projects >100GB.
DB_DIR = Path("/home/jmontavon/omop-scaling-db")
CONVERTED = DB_DIR / "converted"
RESULTS_DIR = BENCHMARKS_DIR / "scaling" / "results" / "omop"

# Resource types the OMOP v5.5 view set consumes. The corpus generation
# already restricts Synthea exports to this set (plus DeviceUseStatement,
# which the device-exposure VD targets as R5 "DeviceUsage" and therefore
# never matches on R4 data - staged anyway for faithfulness, cost ~0).
OMOP_RESOURCE_TYPES = frozenset({
    "Patient", "Encounter", "Condition", "Procedure", "Observation",
    "MedicationRequest", "MedicationAdministration", "MedicationDispense",
    "MedicationStatement", "Immunization", "DeviceUseStatement", "ConceptMap",
})

REPO = PROJECT_ROOT
OMOP_VD_DIR = REPO / "fhir4ds" / "viewdef" / "resources" / "omop"
MANIFEST = OMOP_VD_DIR / "manifest.json"
SAMPLE_DRUG_SQLQUERY = (
    REPO / "web" / "viewing-room" / "public" / "samples"
    / "omop-drug-exposure-sqlquery" / "viewdefinition.json"
)

FINAL_TABLES = [
    "person", "visit_occurrence", "condition_occurrence",
    "procedure_occurrence", "drug_exposure", "device_exposure",
    "measurement", "observation", "death",
]


def rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def corpus_files(n_patients: int, synthea_dir: Path = SYNTHEA_DIR) -> list[str]:
    """Deterministic nested prefix: sorted patient bundles, info files first
    (hospital metadata is not staged; kept for parity with run_measures)."""
    files = sorted(os.listdir(synthea_dir))
    patients = [f for f in files if "information" not in f.lower()
                and f.endswith(".json")]
    return [str(synthea_dir / f) for f in patients[:n_patients]]


def available_corpus_patients(synthea_dir: Path = SYNTHEA_DIR) -> int:
    files = sorted(os.listdir(synthea_dir))
    return sum(1 for f in files
               if "information" not in f.lower() and f.endswith(".json"))


# ---------------------------------------------------------------------------
# Terminology prep: monolithic RxNorm ConceptMap -> loadable chunks.
# The shipped transport (benchmarks/baselines/omop_v55_synthea_2026.md) uses
# 20-element chunks because a monolithic map exhausts DuckDB unnest memory.
# We probe chunk sizes at rung 1k and default to the largest safe one.
# ---------------------------------------------------------------------------

def prepare_terminology(elements_per_chunk: int = 200,
                        hf_snapshot_dir: str | None = None) -> dict:
    """Idempotently write terminology NDJSON; returns stats."""
    TERMINOLOGY_DIR.mkdir(parents=True, exist_ok=True)
    chunks_path = TERMINOLOGY_DIR / f"conceptmap-chunks-{elements_per_chunk}.ndjson"
    supp_path = TERMINOLOGY_DIR / "supplements.ndjson"
    if supp_path.exists() and chunks_path.exists():
        return {"chunks_file": str(chunks_path),
                "supplements_file": str(supp_path), "cached": True}

    if hf_snapshot_dir is None:
        from huggingface_hub import snapshot_download
        hf_snapshot_dir = snapshot_download("fhir4ds/omop-demo",
                                            repo_type="dataset")
    monolithic = None
    for line in open(Path(hf_snapshot_dir) / "medication-resources.ndjson"):
        r = json.loads(line)
        if r.get("resourceType") == "ConceptMap" and r.get("id") == \
                "fhir4ds-omop-conceptmap":
            monolithic = r
            break
    if monolithic is None:
        raise RuntimeError("monolithic fhir4ds-omop-conceptmap not found in "
                           "HF snapshot")

    n_chunks = 0
    n_elements = 0
    # Only RxNorm + CVX go into chunks. The monolithic map ALSO carries the
    # administrative-gender / v3-ActCode / condition-category groups, which
    # conceptmap-supplements.json already provides — staging both duplicated
    # those mappings and fanned person to 2 rows/patient (found 2026-11-03,
    # rung-1000 EXPLAIN: HASH_JOIN rows=2000 over 1000 patients).
    CHUNK_GROUP_SOURCES = {
        "http://www.nlm.nih.gov/research/umls/rxnorm",
        "http://hl7.org/fhir/sid/cvx",
    }
    with open(chunks_path, "w") as out:
        for group in monolithic.get("group", []):
            if group.get("source") not in CHUNK_GROUP_SOURCES:
                continue
            elements = group.get("element", [])
            n_elements += len(elements)
            for i in range(0, len(elements), elements_per_chunk):
                chunk = {
                    "resourceType": "ConceptMap",
                    "id": f"{monolithic['id']}-c{i // elements_per_chunk:05d}",
                    "status": "active",
                    "group": [{
                        "source": group.get("source"),
                        "target": group.get("target"),
                        "element": elements[i:i + elements_per_chunk],
                    }],
                }
                out.write(json.dumps(chunk, separators=(",", ":")) + "\n")
                n_chunks += 1
    supp = json.loads((OMOP_VD_DIR / "conceptmap-supplements.json").read_text())
    supp_path.write_text(json.dumps(supp, separators=(",", ":")) + "\n")
    return {"chunks_file": str(chunks_path), "supplements_file": str(supp_path),
            "cached": False, "chunks": n_chunks, "elements": n_elements,
            "elements_per_chunk": elements_per_chunk}


def terminology_files(elements_per_chunk: int = 200) -> list[str]:
    prepare_terminology(elements_per_chunk)
    return [str(TERMINOLOGY_DIR / f"conceptmap-chunks-{elements_per_chunk}.ndjson"),
            str(TERMINOLOGY_DIR / "supplements.ndjson")]


def _start_watchdog(cap_mb: float, system_floor_mb: float = 3072.0) -> None:
    """Two watchdogs:
    - RSS cap: os._exit(3) when this process exceeds cap_mb.
    - System floor (Joel, 2026-11-03: swap-inflated numbers are not
      measurements): os._exit(5) when host MemAvailable drops below
      system_floor_mb or SwapFree below 1GB — i.e. this leg is about to
      push the SHARED host into swapping, which silently inflates exec
      time and under-counts RSS. A clean abort beats a polluted number."""
    def _read_meminfo():
        avail = swap_free = None
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) / 1024.0
                elif line.startswith("SwapFree:"):
                    swap_free = int(line.split()[1]) / 1024.0
        return avail, swap_free

    def _loop():
        while True:
            r = rss_mb()
            if r > cap_mb:
                print(f"ABORT: RSS {r:,.0f}MB exceeded cap {cap_mb:,.0f}MB",
                      flush=True)
                os._exit(3)
            avail, swap_free = _read_meminfo()
            if avail is not None and avail < system_floor_mb:
                print(f"ABORT: host MemAvailable {avail:,.0f}MB < floor "
                      f"{system_floor_mb:,.0f}MB (other lanes) — stopping "
                      "before host swap pollutes the measurement", flush=True)
                os._exit(5)
            if swap_free is not None and swap_free < 1024.0:
                print(f"ABORT: host SwapFree {swap_free:,.0f}MB < 1024MB — "
                      "swap-risk window", flush=True)
                os._exit(5)
            time.sleep(5)

    threading.Thread(target=_loop, name="rss-watchdog", daemon=True).start()


def _meminfo_snapshot() -> dict:
    snap = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            key = line.split(":")[0]
            if key in ("MemAvailable", "SwapFree", "SwapTotal", "Cached"):
                snap[key + "_mb"] = round(int(line.split()[1]) / 1024.0, 1)
    return snap



# ---------------------------------------------------------------------------
# Subprocess leg runner with memory discipline.
# ---------------------------------------------------------------------------

def run_leg(cmd: list[str], *, rss_cap_mb: float, label: str,
            log_path: Path | None = None, timeout_s: float = 0,
            gate_mb: float | None = None) -> dict:
    """Run one leg as a subprocess. The child enforces its own RSS watchdog
    (cap) and RLIMIT_AS (1.6x cap) via omop_leg.py --self-guard; here we add
    a SYSTEM-WIDE free-memory gate (other lanes share this 62GB host; the
    2026-10-28 freeze was a host-level event, not a single-process one), a
    parent-side wall clock and returncode capture. A cap-abort (exit 3) is
    a CLEAN stop, not a harness failure."""
    # Pre-leg gate: wait for REAL host headroom (Joel 2026-11-03: never
    # launch into a swap-risk window): MemAvailable >= gate AND SwapFree
    # >= 3GB (healthy buffer), up to 2h, then give up cleanly.
    gate = max(8192.0, (gate_mb if gate_mb is not None else rss_cap_mb) * 0.5)
    deadline = time.time() + 7200
    while time.time() < deadline:
        avail = swap_free = 0.0
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) / 1024.0
                elif line.startswith("SwapFree:"):
                    swap_free = int(line.split()[1]) / 1024.0
        if avail >= gate and swap_free >= 3072.0:
            break
        print(f"[gate:{label}] MemAvailable {avail:,.0f}MB < {gate:,.0f}MB "
              f"or SwapFree {swap_free:,.0f}MB < 3,072MB; waiting "
              "(other lanes active)", flush=True)
        time.sleep(30)
    else:
        return {"label": label, "returncode": 4, "wall_s": 0.0,
                "cap_abort": False, "log": None,
                "stdout_tail": "MEM-GATE: never enough free memory within 2h"}

    t0 = time.perf_counter()
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as logf:
        logf.write(f"cmd: {cmd}\n")
        logf.flush()
        proc = subprocess.Popen(
            [sys.executable] + cmd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, env=env, bufsize=1)
        assert proc.stdout is not None
        for chunk in proc.stdout:
            logf.write(chunk)
            logf.flush()
        rc = proc.wait()
    wall_s = time.perf_counter() - t0
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"cmd: {cmd}\nrc: {proc.returncode}\n--- stdout ---\n{proc.stdout}"
            f"\n--- stderr ---\n{proc.stderr}\n")
    return {
        "label": label,
        "returncode": rc,
        "wall_s": round(wall_s, 1),
        "cap_abort": rc == 3,
        "log": str(log_path) if log_path else None,
        "stdout_tail": _tail(log_path, 2000),
    }


def _tail(path: Path, n: int) -> str:
    try:
        data = path.read_text()
        return data[-n:]
    except OSError:
        return ""
