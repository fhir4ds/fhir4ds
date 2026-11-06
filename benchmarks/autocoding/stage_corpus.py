"""Stage the Synthea autocoding workload corpus (one pass, cached NDJSON).

Scans Synthea s100k patient bundles, collects CodeableConcept-bearing
resources, strips coding[] conceptually (we keep (resource_type, text)
pairs), and writes a cached workload file reused by the ladder runs.
"""
import json, sys, time
from pathlib import Path

SYNTHEA = Path("/mnt/d/scaling-data/omop-scaling/s100k/output/fhir")
OUT = Path(__file__).parent / "workload.ndjson"

# resourceType -> CodeableConcept path holding Synthea-populated text
PATHS = {
    "Condition": ("code", "condition"),
    "MedicationRequest": ("medicationCodeableConcept", "medication"),
    "Observation": ("code", "observation"),
    "Procedure": ("code", "procedure"),
    "Immunization": ("vaccineCode", "medication"),
    "AllergyIntolerance": ("code", "condition"),
}

TARGET_ROWS = 130_000

def main():
    t0 = time.time()
    rows = []
    files = sorted(SYNTHEA.iterdir())
    for i, f in enumerate(files):
        if len(rows) >= TARGET_ROWS:
            break
        try:
            bundle = json.loads(f.read_text())
        except Exception:
            continue
        for e in bundle.get("entry", []):
            r = e.get("resource", {})
            rt = r.get("resourceType")
            spec = PATHS.get(rt)
            if not spec:
                continue
            path, _cat = spec
            cc = r.get(path)
            if isinstance(cc, dict) and cc.get("text"):
                rows.append({"rt": rt, "text": cc["text"]})
        if i % 2000 == 0 and i:
            print(f"  {i} files -> {len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    with OUT.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    from collections import Counter
    c = Counter(r["rt"] for r in rows)
    d = {rt: len({r["text"] for r in rows if r["rt"] == rt}) for rt in c}
    print(f"staged {len(rows)} rows to {OUT.name} in {time.time()-t0:.0f}s")
    print("by type:", dict(c))
    print("distinct texts by type:", d)
    print("distinct overall:", len({r['text'] for r in rows}))

if __name__ == "__main__":
    main()
