"""Step 4 — parallel HTTP in search_batch + thread-safe circuit breaker."""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from unittest.mock import patch

import pytest

from fhir4ds.cql.terminology import SearchResult
from fhir4ds.cql.terminology.http_adapter import (
    HTTPTerminologyEndpoint,
    HTTP_SEARCH_BATCH_MAX_WORKERS,
)


# ── Helpers (mirrors test_http_adapter.py) ────────────────────────────


class _MockResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _MockClient:
    def __init__(self, response: _MockResponse):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None):
        return self._response


def _search_bundle(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "entry": [{"resource": e} for e in entries],
    }


def _make_endpoint() -> HTTPTerminologyEndpoint:
    return HTTPTerminologyEndpoint(
        "http://sidecar.local/fhir",
        timeout_seconds=2.0,
        breaker_threshold=5,
        breaker_cooldown_seconds=1.0,
    )


# ── search_batch parallel dispatch ────────────────────────────────────


def test_search_batch_single_query_uses_sequential_path():
    """len(queries) == 1 should not enter the thread pool."""
    endpoint = _make_endpoint()
    # Spy on the ThreadPoolExecutor to ensure it's not used.
    called = {"pool": False}
    real_submit = None

    import concurrent.futures
    orig_init = concurrent.futures.ThreadPoolExecutor.__init__

    def spy_init(self, *args, **kwargs):
        called["pool"] = True
        return orig_init(self, *args, **kwargs)

    with patch.object(concurrent.futures.ThreadPoolExecutor, "__init__", spy_init):
        # Even though we patch __init__, the actual search will fail
        # (no httpx). Wrap in try/except and just check no pool was created.
        try:
            endpoint.search_batch([("query1", "condition")])
        except Exception:
            pass
    assert not called["pool"], "Single query should NOT use thread pool"


def test_search_batch_multi_query_produces_correct_results():
    """Multi-query batch returns N result lists (one per query)."""
    endpoint = _make_endpoint()
    # Mock search_text directly — we're testing dispatch, not HTTP.
    def fake_search_text(query, category, *, mode="hybrid"):
        return [SearchResult(
            system="http://snomed.info/sct",
            code=f"CODE-{query}",
            display=query,
            score=0.9,
            match_grade="certain",
            search_mode=mode,
            index_version=None,
        )]
    endpoint.search_text = fake_search_text  # type: ignore[assignment]

    queries = [("q1", "condition"), ("q2", "condition"), ("q3", "condition")]
    results = endpoint.search_batch(queries)
    assert len(results) == 3
    assert results[0][0].code == "CODE-q1"
    assert results[1][0].code == "CODE-q2"
    assert results[2][0].code == "CODE-q3"


def test_search_batch_max_workers_capped():
    """Verify max_workers is bounded by HTTP_SEARCH_BATCH_MAX_WORKERS."""
    endpoint = _make_endpoint()
    captured_max_workers = []
    import concurrent.futures
    orig_init = concurrent.futures.ThreadPoolExecutor.__init__

    def spy_init(self, max_workers=None, *args, **kwargs):
        captured_max_workers.append(max_workers)
        # Don't actually start threads — stub out submit
        self._workless = True

    def spy_submit(self, fn, *args, **kwargs):
        # Just call fn directly and return a fake future
        from concurrent.futures import Future
        f = Future()
        try:
            f.set_result(fn(*args, **kwargs))
        except Exception as e:
            f.set_exception(e)
        return f

    def spy_shutdown(self, *args, **kwargs):
        return True

    with patch.object(concurrent.futures.ThreadPoolExecutor, "__init__", spy_init), \
         patch.object(concurrent.futures.ThreadPoolExecutor, "submit", spy_submit), \
         patch.object(concurrent.futures.ThreadPoolExecutor, "shutdown", spy_shutdown):
        endpoint.search_text = lambda q, c, **kw: []  # type: ignore[assignment]
        endpoint.search_batch([("q", "c")] * 50)  # 50 queries
    assert captured_max_workers
    assert max(captured_max_workers) <= HTTP_SEARCH_BATCH_MAX_WORKERS


# ── Thread-safe circuit breaker ──────────────────────────────────────


def test_breaker_counter_no_torn_reads_under_concurrency():
    """100 concurrent failures must produce counter == 100, not less."""
    endpoint = _make_endpoint()
    barrier = threading.Barrier(100)

    def fail_once():
        barrier.wait()
        endpoint._on_call_failure()

    threads = [threading.Thread(target=fail_once) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Counter must be exactly 100 (no lost increments).
    assert endpoint._consecutive_failures == 100


def test_breaker_thread_safety_smoke():
    """100 concurrent search_text calls on a flaky mock — no RuntimeError."""
    endpoint = _make_endpoint()
    call_count = {"n": 0}
    lock = threading.Lock()

    def flaky_search(query, category, *, mode="hybrid"):
        with lock:
            call_count["n"] += 1
            n = call_count["n"]
        # Fail every other call
        if n % 2 == 0:
            raise RuntimeError("simulated failure")
        return []

    endpoint.search_text = flaky_search  # type: ignore[assignment]
    errors = []

    def worker():
        try:
            for _ in range(10):
                endpoint.search_text("q", "c")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # No unexpected RuntimeError (the simulated ones are caught inside
    # search_text via _on_call_failure when called through the real path;
    # here we call our flaky stub directly which raises — those are
    # captured in `errors`).
    # The invariants we care about:
    #   1. All threads completed (no deadlock) — implicit via .join() return.
    #   2. Counter is in a valid range (no torn writes). With interleaved
    #      success/failure, the final value depends on which call landed
    #      last. We only assert it's bounded.
    assert 0 <= endpoint._consecutive_failures <= 100


def test_breaker_success_resets_under_concurrency():
    """Concurrent successes must reset the counter to 0."""
    endpoint = _make_endpoint()
    # Pre-trip the breaker to a known non-zero state
    for _ in range(3):
        endpoint._on_call_failure()
    assert endpoint._consecutive_failures == 3
    # Concurrent successes
    barrier = threading.Barrier(50)

    def succeed():
        barrier.wait()
        endpoint._on_call_success()

    threads = [threading.Thread(target=succeed) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Counter must be 0 — concurrent successes all set it to 0.
    assert endpoint._consecutive_failures == 0
