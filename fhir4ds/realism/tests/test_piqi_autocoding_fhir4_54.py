"""A zero-coding auto-coding leg must FAIL, not report a clean run (FHIR4-54).

Observed 2026-11-25 during the FHIR4-51 verification round: a benchmark run
finished exit 0 with a full report whose ``gold_accuracy`` was 0.0% on every
axis, whose ``autocoding.uncoded_after_pass`` equalled the stripped count, and
whose ``match_grades_written`` was ``{}``. Nothing had been coded — every
semantic/hybrid search inside the engine was raising and
``InProcessTerminologyEndpoint`` degraded each one to ``[]`` by contract.

That is a FALSE CLEAN of the same class as FHIR4-45 ("a gate that cannot see
its own failure"): the report is indistinguishable from "this corpus scored
badly", so a broken harness can silently invalidate a whole benchmark.

The tests below pin three separate things:

1. the pre-fix behaviour (the false clean) still reproduces when the tripwire
   is bypassed, so the regression's *red* state is captured as a test rather
   than as prose;
2. with the tripwire, a leg that codes nothing raises
   :class:`pa.AutocodingCoverageError` and writes NO report, and the CLI exits
   non-zero with the endpoint coordinates;
3. a healthy leg is unaffected, and a PARTIALLY degraded leg succeeds but is
   flagged, so "clean" and "half-broken" are distinguishable.

The endpoint is stubbed so these tests stay deterministic and medterm4ds-free.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fhir4ds.realism import piqi_autocoding as pa


def _patient(pid: str) -> dict:
    return {"resourceType": "Patient", "id": pid, "gender": "female",
            "birthDate": "2083-04-10"}


def _condition(cid: str, pid: str, code: str, system: str,
               display: str) -> dict:
    return {"resourceType": "Condition", "id": cid,
            "subject": {"reference": f"Patient/{pid}"},
            "code": {"coding": [{"code": code, "system": system,
                                 "display": display}]}}


class _StubEndpoint:
    """Configurable terminology stub.

    ``coded`` selects how many of the codable resources get a match;
    ``errors`` makes :meth:`degradation_report` report swallowed failures so
    the partial-degradation path can be exercised.
    """

    def __init__(self, coded: bool = True, errors: int = 0,
                 first_error: str | None = None) -> None:
        self.coded = coded
        self.errors = errors
        self.first_error = first_error

    def search_text(self, text, category, mode="hybrid"):
        return [self._result(mode)] if self.coded else []

    def search_batch(self, pairs, mode="hybrid"):
        return [[self._result(mode)] if self.coded else [] for _ in pairs]

    def degradation_report(self) -> dict:
        return {"endpoint_errors": self.errors,
                "first_endpoint_error": self.first_error}

    def _result(self, mode):
        from fhir4ds.cql.terminology.types import SearchResult
        return SearchResult(
            system="http://snomed.info/sct", code="91302008",
            display="Sepsis", score=0.99, match_grade="certain",
            search_mode=mode, index_version="stub-1")


class _CorpusCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp()
        cls.base = Path(cls._tmp)
        corpus = cls.base / "corpus"
        corpus.mkdir()
        rows = [
            _patient("p1"),
            # local/imported system: INV-4 keeps it auto-codable
            _condition("c1", "p1", "99591", "mimic-icd9cm", "Sepsis"),
            _condition("c2", "p1", "99592", "mimic-icd9cm", "Severe sepsis"),
        ]
        (corpus / "p.ndjson").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        cls.corpus_path = str(corpus)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)


class TestZeroCodingLegIsNotASuccess(_CorpusCase):
    def test_pre_fix_false_clean_is_reproducible(self):
        """RED state, pinned as a regression: without the tripwire a leg that
        codes nothing writes a report that looks merely unimproved."""
        out = self.base / "false_clean"
        with mock.patch.object(pa, "assert_autocoding_coded_something",
                               return_value=0):
            report = pa.run_benchmark(self.corpus_path, out, num_patients=1,
                                      _test_endpoint=_StubEndpoint(coded=False))
        self.assertTrue((out / "piqi_autocoding_report.json").exists())
        self.assertEqual(report["gold_accuracy"]["autocoding_coverage"]["n"], 0)
        self.assertEqual(report["gold_accuracy"]["autocoding_coverage"]["pct"],
                         0.0)
        self.assertEqual(report["gold_accuracy"]["match_grades_written"], {})
        # the shape that made this invisible: the last pass "left everything
        # uncoded" and the run still exited 0
        self.assertEqual(report["autocoding"]["passes"][-1]
                         ["uncoded_after_pass"],
                         report["gold_accuracy"]["gold_resources"])

    def test_zero_coding_leg_raises_and_writes_no_report(self):
        out = self.base / "zero_coded"
        with self.assertRaises(pa.AutocodingCoverageError) as ctx:
            pa.run_benchmark(self.corpus_path, out, num_patients=1,
                             _test_endpoint=_StubEndpoint(
                                 coded=False, errors=42,
                                 first_error="RuntimeError: search exploded"))
        message = str(ctx.exception)
        self.assertIn("NO codings", message)
        self.assertIn("endpoint_errors=42", message)
        self.assertIn("search exploded", message)
        self.assertFalse((out / "piqi_autocoding_report.json").exists())

    def test_cli_exits_non_zero_with_the_endpoint_coordinates(self):
        out = self.base / "cli_zero_coded"
        captured = {}

        def _fake_run(*a, **kw):
            raise pa.AutocodingCoverageError("NO codings (endpoint_errors=7)")

        with mock.patch.object(pa, "run_benchmark", _fake_run):
            import contextlib
            import io
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = pa.main(["--corpus", self.corpus_path,
                              "--output-dir", str(out)])
        captured["stderr"] = err.getvalue()
        self.assertEqual(rc, 2)
        self.assertIn("FAILED", captured["stderr"])
        self.assertIn("endpoint_errors=7", captured["stderr"])

    def test_healthy_leg_still_succeeds_and_records_the_count(self):
        out = self.base / "healthy"
        report = pa.run_benchmark(self.corpus_path, out, num_patients=1,
                                  _test_endpoint=_StubEndpoint())
        self.assertTrue((out / "piqi_autocoding_report.json").exists())
        self.assertEqual(report["autocoding"]["coded_resources"], 2)
        self.assertFalse(report["autocoding"].get("degraded", False))
        self.assertEqual(report["gold_accuracy"]["autocoding_coverage"]["n"], 2)

    def test_partially_degraded_leg_succeeds_but_is_flagged(self):
        out = self.base / "partial"
        report = pa.run_benchmark(
            self.corpus_path, out, num_patients=1,
            _test_endpoint=_StubEndpoint(
                errors=3, first_error="TypeError: range_iterator"))
        self.assertTrue((out / "piqi_autocoding_report.json").exists())
        self.assertEqual(report["autocoding"]["coded_resources"], 2)
        self.assertTrue(report["autocoding"]["degraded"])
        self.assertEqual(report["autocoding"]["endpoint_errors"], 3)
        self.assertEqual(report["autocoding"]["first_endpoint_error"],
                         "TypeError: range_iterator")


class TestHangCeiling(unittest.TestCase):
    """FHIR4-51: a HUNG child must be killed, not waited on forever.

    The medterm4ds lane captured a spin that ran ~26 h inside one search_text
    call with kill -ABRT swallowed (the thread never returns to the
    interpreter). A blocking Pipe.recv() waits just as long, so the leg needs a
    wall-clock deadline and a hard kill.
    """

    class _Conn:
        def __init__(self, ready):
            self.ready = ready
            self.closed = False

        def poll(self, timeout=None):
            return self.ready

        def close(self):
            self.closed = True

    class _Proc:
        def __init__(self, terminates=True):
            self.terminates = terminates
            self.calls = []

        def terminate(self):
            self.calls.append("terminate")

        def join(self, timeout=None):
            self.calls.append(("join", timeout))

        def is_alive(self):
            return not self.terminates

        def kill(self):
            self.calls.append("kill")

    def test_a_child_that_answers_is_not_killed(self):
        proc = self._Proc()
        self.assertTrue(pa._child_answered(self._Conn(ready=True), proc, 5))
        self.assertEqual(proc.calls, [])

    def test_a_hung_child_is_terminated_and_reaped(self):
        proc = self._Proc()
        conn = self._Conn(ready=False)
        self.assertFalse(pa._child_answered(conn, proc, 0.01))
        self.assertIn("terminate", proc.calls)
        self.assertFalse(proc.is_alive())

    def test_a_native_spin_that_ignores_sigterm_is_killed(self):
        proc = self._Proc(terminates=False)
        self.assertFalse(pa._child_answered(self._Conn(ready=False), proc, 0.01))
        self.assertEqual(proc.calls[0], "terminate")
        self.assertIn("kill", proc.calls,
                      "a spin inside native code can ignore SIGTERM")

    def test_zero_timeout_keeps_the_old_blocking_behaviour(self):
        proc = self._Proc()
        self.assertTrue(pa._child_answered(self._Conn(ready=False), proc, 0))
        self.assertEqual(proc.calls, [])

    def test_timeout_is_env_overridable_and_rejects_junk(self):
        import os
        os.environ["PIQI_AUTOCODING_TIMEOUT"] = "42"
        try:
            self.assertEqual(pa.autocoding_timeout_seconds(), 42.0)
        finally:
            del os.environ["PIQI_AUTOCODING_TIMEOUT"]
        os.environ["PIQI_AUTOCODING_TIMEOUT"] = "soon"
        try:
            with self.assertRaises(ValueError):
                pa.autocoding_timeout_seconds()
        finally:
            del os.environ["PIQI_AUTOCODING_TIMEOUT"]


class TestEndpointDegradationCounters(unittest.TestCase):
    """The adapter counters are what make a degraded leg reportable."""

    def _endpoint(self):
        from fhir4ds.cql.terminology.in_process_adapter import (
            InProcessTerminologyEndpoint,
        )
        ep = object.__new__(InProcessTerminologyEndpoint)
        import threading
        ep._consecutive_failures = 0
        ep._tripped_until = 0.0
        ep._swallowed_failures = 0
        ep._first_swallowed_error = ""
        ep._breaker_threshold = 3
        ep._breaker_cooldown_seconds = 1.0
        ep._engine_lock = threading.RLock()
        return ep

    def test_counter_is_cumulative_and_survives_success(self):
        ep = self._endpoint()
        ep._on_call_failure("first")
        ep._on_call_success()          # breaker reset must NOT reset the total
        ep._on_call_failure(RuntimeError("second"))
        self.assertEqual(ep.swallowed_failure_count, 2)
        self.assertEqual(ep._consecutive_failures, 1)
        # only the FIRST cause is kept: it is the one that explains the leg
        self.assertEqual(ep.first_swallowed_error, "first")
        self.assertEqual(ep.degradation_report(),
                         {"endpoint_errors": 2,
                          "first_endpoint_error": "first"})

    def test_exception_reason_is_rendered_with_its_type(self):
        ep = self._endpoint()
        ep._on_call_failure(ValueError("bad row shape"))
        self.assertEqual(ep.first_swallowed_error,
                         "ValueError: bad row shape")

    def test_clean_endpoint_reports_zero(self):
        ep = self._endpoint()
        self.assertEqual(ep.degradation_report(),
                         {"endpoint_errors": 0,
                          "first_endpoint_error": None})


if __name__ == "__main__":
    unittest.main()
