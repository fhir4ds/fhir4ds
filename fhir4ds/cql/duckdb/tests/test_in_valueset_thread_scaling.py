"""Phase 2 Item 2 regression: in_valueset scales with threads (shared_mutex).

The pre-fix binary serialized on a global std::mutex taken twice per row,
making in_valueset SLOWER with more threads. The shared_mutex chunk-level
read lock restores linear scaling to the extractCodes floor.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, "/mnt/d/fhir4ds-playground")

import duckdb
import fhir4ds
from fhir4ds.cql import FHIRDataLoader


def test_in_valueset_thread_scaling():
    con = fhir4ds.create_connection()
    loader = FHIRDataLoader(con)
    # 20k observations, half with a LOINC code
    resources = []
    for i in range(20000):
        code = "8867-4" if i % 2 == 0 else "1234-5"
        resources.append({
            "resourceType": "Observation",
            "id": f"obs-{i}",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
            "subject": {"reference": f"Patient/p{i % 100}"},
        })
    loader.load_resources(resources)
    VS = "http://cts.nlm.nih.gov/fhir/ValueSet/test-vs"
    # load the cache via the loader's valueset table + UDF registration path
    from fhir4ds.cql.duckdb.udf.valueset import createValuesetMembershipUdf
    udf = createValuesetMembershipUdf({VS: {("http://loinc.org", "8867-4")}})
    con.create_function("in_valueset_p2t", udf)

    q = ("SELECT count(*) FROM resources WHERE resourceType='Observation' "
         f"AND in_valueset_p2t(resource, 'code', '{VS}')")
    times = {}
    for threads in (1, 4):
        con.execute(f"SET threads={threads}")
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            n = con.execute(q).fetchone()[0]
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        times[threads] = best
        if threads == 1:
            assert n == 10000, f"expected 10000 matches, got {n}"
    # With the shared_mutex fix, 4 threads must not be SLOWER than 1
    # (pre-fix: mutex contention made multi-threaded runs slower).
    assert times[4] <= times[1] * 1.15, (
        f"in_valueset thread serialization regression: 1thr={times[1]:.3f}s "
        f"4thr={times[4]:.3f}s"
    )
