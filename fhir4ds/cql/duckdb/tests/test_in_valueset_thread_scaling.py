"""Phase 2 Item 2 regression: in_valueset scales with threads (shared_mutex).

The pre-fix binary serialized on a global std::mutex taken twice per row,
making in_valueset SLOWER with more threads. The shared_mutex chunk-level
read lock restores linear scaling to the extractCodes floor.

This test exercises the REAL C++ extension path: the bundled
cql.duckdb_extension is loaded explicitly and its g_valueset_cache is
populated via cql_valueset_cache_add (review finding 2.1 — the previous
version registered a pure-Python closure UDF and guarded nothing).
"""
import shutil
import tempfile
import time
from pathlib import Path

import duckdb
import pytest


def _repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "extensions").exists() and (parent / "fhir4ds").exists():
            return parent
    raise RuntimeError("Could not locate repository root")


@pytest.fixture
def cpp_con():
    ext = (
        _repo_root()
        / "extensions"
        / "cql"
        / "build"
        / "release"
        / "extension"
        / "cql"
        / "cql.duckdb_extension"
    )
    if not ext.exists():
        pytest.skip(f"CQL extension is not built: {ext}")

    with tempfile.TemporaryDirectory() as tmpdir:
        load_path = Path(tmpdir) / "cql.duckdb_extension"
        shutil.copy2(ext, load_path)
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": "true"})
        con.execute(f"LOAD '{load_path}'")
        try:
            yield con
        finally:
            con.close()


def test_in_valueset_thread_scaling_cpp(cpp_con):
    con = cpp_con
    # 20k observations, half with a LOINC code that IS in the valueset
    rows = []
    for i in range(20000):
        code = "8867-4" if i % 2 == 0 else "1234-5"
        rows.append(
            f'{{"resourceType":"Observation","id":"obs-{i}","status":"final",'
            f'"code":{{"coding":[{{"system":"http://loinc.org","code":"{code}"}}]}}}}'
        )
    con.execute("CREATE TABLE obs (resource VARCHAR)")
    con.executemany("INSERT INTO obs VALUES (?)", [(r,) for r in rows])

    VS = "http://cts.nlm.nih.gov/fhir/ValueSet/test-vs-thread-scaling"
    assert con.execute("SELECT cql_valueset_cache_clear()").fetchone()[0] is True
    assert con.execute(
        "SELECT cql_valueset_cache_add(?, ?, ?)",
        [VS, "http://loinc.org", "8867-4"],
    ).fetchone()[0] is True

    q = f"SELECT count(*) FROM obs WHERE in_valueset(resource, 'code', '{VS}')"
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

    # With the shared_mutex fix, 4 threads must not be SLOWER than 1 thread
    # (pre-fix: per-row exclusive mutex made multi-threaded runs slower —
    # measured 573ms @1thr vs 774ms @4thr on 501k rows).
    assert times[4] <= times[1] * 1.15, (
        f"in_valueset thread serialization regression: 1thr={times[1]:.3f}s "
        f"4thr={times[4]:.3f}s"
    )
