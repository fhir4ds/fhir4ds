"""Single-pass, in-process PIQI auto-coding benchmark (FHIR4-25).

The benchmark used to be split into three ``--phase`` invocations
(``piqi`` / ``autocode`` / ``after``) with JSONL + partial-report
artifacts carrying state between them, because the medterm4ds inference
stack (torch/SapBERT) and the DuckDB native extension were believed not
to coexist in one process. That belief is retired (medterm4ds PR #24 /
FHIR4-23): the historical same-process segfaults were concurrent native
inference, now serialized inside medterm4ds 0.0.14, and in-process is the
SUPPORTED embedding pattern.

These tests pin the replacement contract:

* one call runs every leg — no ``phase`` parameter, no ``--phase`` flag,
  no inter-phase artifacts;
* the auto-coding leg defaults to the IN-PROCESS endpoint
  (``InProcessTerminologyEndpoint``); the HTTP adapter stays available as
  an explicit escape hatch for a remote/isolated server;
* the full pipeline (PIQI legs + auto-coding + after) runs in ONE
  process — the ordering the phase scaffolding existed to forbid.

The real-engine evidence (same rows / same autocoding extensions as the
pre-switch phase-isolated run, plus the recovery numbers) is recorded in
the FHIR4-25 handoff; these tests use a stub endpoint so they stay
deterministic and medterm4ds-free.
"""

from __future__ import annotations

import inspect
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


class StubEndpoint:
    """TerminologyEndpoint stub: one fixed certain SNOMED match."""

    def __init__(self, code: str = "91302008") -> None:
        self.code = code

    def search_text(self, text, category, mode="hybrid"):
        return [self._result(mode)]

    def search_batch(self, pairs, mode="hybrid"):
        return [[self._result(mode)] for _ in pairs]

    def _result(self, mode):
        from fhir4ds.cql.terminology.types import SearchResult
        return SearchResult(
            system="http://snomed.info/sct", code=self.code,
            display="Sepsis", score=0.99, match_grade="certain",
            search_mode=mode, index_version="stub-1")


class _CorpusCase(unittest.TestCase):
    """Corpus fixture shared by the single-pass classes.

    One full ``run_benchmark`` costs several PIQI evaluations, so each
    class computes its report ONCE (``setUpClass``) and the tests assert
    against it.
    """

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
            # standard terminology system: INV-4 skips it
            _condition("c2", "p1", "91302008", "http://snomed.info/sct",
                       "Sepsis"),
        ]
        (corpus / "p.ndjson").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        cls.corpus_path = str(corpus)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)


class TestNoPhaseScaffolding(unittest.TestCase):
    """The phase machinery is gone, not merely unused."""

    def test_run_benchmark_has_no_phase_parameter(self):
        params = inspect.signature(pa.run_benchmark).parameters
        self.assertNotIn("phase", params)

    def test_cli_exposes_no_phase_flag(self):
        with mock.patch("sys.stdout", new_callable=lambda: _Sink()) as out:
            with self.assertRaises(SystemExit):
                pa.main(["--help"])
        help_text = out.getvalue()
        self.assertNotIn("--phase", help_text)
        # the escape hatch for a remote/isolated server stays documented
        self.assertIn("--http-base-url", help_text)
        self.assertIn("in-process", help_text.lower())

    def test_interphase_artifact_helpers_are_gone(self):
        for name in ("_load_jsonl", "_load_partial",
                     "_require_partial_leg", "_check_artifact_corpus"):
            self.assertFalse(hasattr(pa, name), name)


class _Sink:
    def __init__(self) -> None:
        self._buf: list[str] = []

    def write(self, text: str) -> int:
        self._buf.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False

    def getvalue(self) -> str:
        return "".join(self._buf)


class TestSinglePassStripMode(_CorpusCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.out = cls.base / "strip_out"
        cls.report = pa.run_benchmark(cls.corpus_path, cls.out,
                                      num_patients=1,
                                      _test_endpoint=StubEndpoint())

    def test_one_call_runs_every_leg(self):
        for leg in ("baseline", "before", "ceiling", "autocoding",
                    "gold_accuracy", "after", "recovery"):
            self.assertIn(leg, self.report, leg)
        self.assertEqual(self.report["mode"], "strip")
        self.assertEqual(self.report["autocoding"]["endpoint"], "test_stub")
        self.assertEqual(self.report["autocoding"]["min_match_grade"],
                         "certain")
        self.assertEqual(self.report["autocoding"]["top_k"], 3)

    def test_autocoded_corpus_reaches_the_after_leg(self):
        gold = self.report["gold_accuracy"]
        # both Conditions are stripped; the stub codes both
        self.assertEqual(gold["gold_resources"], 2)
        self.assertEqual(gold["autocoding_coverage"]["n"], 2)
        # the AFTER leg is scored over the AUGMENTED corpus, in the same
        # process as the PIQI legs (what the phase split used to forbid)
        self.assertGreater(self.report["after"]["total_item_score"],
                           self.report["before"]["total_item_score"])
        self.assertGreater(self.report["recovery"]["total_fails_recovered"],
                           0)
        self.assertEqual(self.report["recovery"]["total_new_failures"], 0)
        # the ceiling is the original codings re-attached; the stub's
        # SNOMED code can score HIGHER than the stripped local coding
        # (recognized-system SAM), so only the floor is pinned.
        self.assertGreaterEqual(self.report["ceiling"]["total_item_score"],
                                self.report["before"]["total_item_score"])

    def test_no_interphase_artifacts_are_written(self):
        self.assertEqual(
            sorted(p.name for p in self.out.iterdir()),
            ["piqi_autocoding_report.json"])

    def test_report_on_disk_matches_returned_report(self):
        on_disk = json.loads(
            (self.out / "piqi_autocoding_report.json").read_text())
        self.assertEqual(json.dumps(on_disk, sort_keys=True),
                         json.dumps(self.report, sort_keys=True))

    def test_rerun_is_deterministic(self):
        again = pa.run_benchmark(self.corpus_path, self.base / "strip_out2",
                                 num_patients=1,
                                 _test_endpoint=StubEndpoint())
        self.assertEqual(json.dumps(again, sort_keys=True),
                         json.dumps(self.report, sort_keys=True))


class TestSinglePassSkipAutocoding(_CorpusCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.report = pa.run_benchmark(cls.corpus_path,
                                      cls.base / "skip_out", num_patients=1,
                                      skip_autocoding=True)

    def test_skip_autocoding_leaves_autocoding_legs_null(self):
        self.assertIsNone(self.report["autocoding"])
        self.assertIsNone(self.report["after"])
        self.assertIsNone(self.report["recovery"])
        self.assertIn("before", self.report)
        self.assertIn("ceiling", self.report)


class TestSinglePassNoStripMode(_CorpusCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.out = cls.base / "nostrip_out"
        cls.report = pa.run_benchmark(cls.corpus_path, cls.out,
                                      num_patients=1, no_strip=True,
                                      _test_endpoint=StubEndpoint())

    def test_one_call_runs_every_leg(self):
        for leg in ("baseline", "autocoding", "augmentation",
                    "append_invariants", "after", "recovery"):
            self.assertIn(leg, self.report, leg)
        self.assertEqual(self.report["mode"], "no_strip")
        self.assertIsNone(self.report["gold_accuracy"])
        self.assertEqual(self.report["stripped"]["total"], 0)
        self.assertNotIn("before", self.report)
        self.assertNotIn("ceiling", self.report)

    def test_augmentation_only_touches_non_standard_codings(self):
        cond = self.report["augmentation"]["per_class"]["Condition"]
        self.assertEqual(cond["resources"], 2)
        self.assertEqual(cond["augmented"], 1)
        self.assertEqual(cond["inv4_skipped_standard"], 1)
        inv = self.report["append_invariants"]
        self.assertEqual(inv["originals_replaced_or_removed"], 0)
        self.assertEqual(inv["appended_without_user_selected_false"], 0)
        self.assertEqual(inv["appended_without_provenance"], 0)

    def test_after_leg_scores_the_augmented_corpus(self):
        self.assertGreaterEqual(self.report["after"]["total_item_score"],
                                self.report["baseline"]["total_item_score"])
        self.assertEqual(self.report["recovery"]["total_new_failures"], 0)

    def test_no_interphase_artifacts_are_written(self):
        self.assertEqual(
            sorted(p.name for p in self.out.iterdir()),
            ["piqi_autocoding_report.json"])


class TestDefaultEndpointIsInProcess(_CorpusCase):
    def test_default_endpoint_is_the_in_process_adapter(self):
        constructed: list[tuple] = []

        class _FakeInProcess:
            def __init__(self, *args, **kwargs):
                constructed.append((args, kwargs))

            def search_text(self, text, category, mode="hybrid"):
                return []

            def search_batch(self, pairs, mode="hybrid"):
                return [[] for _ in pairs]

        with mock.patch(
            "fhir4ds.cql.terminology.in_process_adapter"
            ".InProcessTerminologyEndpoint",
            _FakeInProcess,
        ):
            endpoint = pa._make_endpoint(None)
        self.assertIsInstance(endpoint, _FakeInProcess)
        self.assertEqual(len(constructed), 1)

    def test_http_escape_hatch_still_constructs_the_http_adapter(self):
        endpoint = pa._make_endpoint("http://127.0.0.1:8012/fhir")
        from fhir4ds.cql.terminology.http_adapter import (
            HTTPTerminologyEndpoint,
        )
        self.assertIsInstance(endpoint, HTTPTerminologyEndpoint)

    def test_default_run_records_in_process_provenance(self):
        # _make_endpoint is what the default path calls; stub it so the
        # test stays medterm4ds-free while exercising the provenance code.
        with mock.patch.object(pa, "_make_endpoint",
                               return_value=StubEndpoint()):
            report = pa.run_benchmark(self.corpus_path,
                                      self.base / "prov_out",
                                      num_patients=1, no_strip=True)
        stats = report["autocoding"]
        self.assertEqual(stats["endpoint"], "in_process")
        self.assertIn("medterm4ds_layout", stats)


class TestAutocodingIsolationWiring(unittest.TestCase):
    """The auto-coding leg defaults to the child process; the flag flips it.

    The child hop is a resilience measure for the native ML stack (see
    ``AUTOCODING_ATTEMPTS``), not an HTTP sidecar: the child uses the same
    IN-PROCESS endpoint. The leg itself is exercised by the real benchmark
    run (spawning torch inside a unit test is not appropriate), so here we
    pin the wiring only.
    """

    def _run(self, **kwargs):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            corpus = base / "corpus"
            corpus.mkdir()
            rows = [_patient("p1"),
                    _condition("c1", "p1", "99591", "mimic-icd9cm", "Sepsis")]
            (corpus / "p.ndjson").write_text(
                "".join(json.dumps(r) + "\n" for r in rows),
                encoding="utf-8")
            def _fake_leg(resources, **kwargs):
                return resources, {"endpoint": "test_stub"}

            with mock.patch.object(pa, "_autocoding_leg",
                                   side_effect=_fake_leg) as leg:
                pa.run_benchmark(corpus, base / "out", num_patients=1,
                                 no_strip=True, **kwargs)
        return leg.call_args.kwargs

    def test_default_isolates_the_leg(self):
        self.assertIs(self._run()["isolate"], True)

    def test_flag_runs_it_inline(self):
        self.assertIs(self._run(isolate_autocoding=False)["isolate"], False)

    def test_inline_autocoding_flag_is_a_cli_option(self):
        parser_help = None
        with mock.patch("sys.stdout", new_callable=lambda: _Sink()) as out:
            with self.assertRaises(SystemExit):
                pa.main(["--help"])
            parser_help = out.getvalue()
        self.assertIn("--inline-autocoding", parser_help)


class TestDuckdbThreadPin(unittest.TestCase):
    """FHIR4-25: DuckDB's executor is pinned by default.

    The auto-coding leg runs torch + faiss IN THIS PROCESS. With DuckDB's
    default multi-threaded executor co-resident, this host segfaults
    (`segfault at 0 ip 0000000000000000`, a null call) part-way through
    the auto-coding leg; the same workload at one thread completes. The
    pin is therefore the default, overridable, and recorded in the
    report so the numbers stay self-describing.
    """

    def test_default_is_single_threaded(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop(pa.DUCKDB_THREADS_ENV, None)
            self.assertEqual(pa.default_duckdb_threads(), 1)
            self.assertEqual(pa.DEFAULT_DUCKDB_THREADS, 1)

    def test_env_override_and_validation(self):
        with mock.patch.dict("os.environ",
                             {pa.DUCKDB_THREADS_ENV: "4"}):
            self.assertEqual(pa.default_duckdb_threads(), 4)
        with mock.patch.dict("os.environ",
                             {pa.DUCKDB_THREADS_ENV: "many"}):
            with self.assertRaises(ValueError) as ctx:
                pa.default_duckdb_threads()
            self.assertIn(pa.DUCKDB_THREADS_ENV, str(ctx.exception))
        with mock.patch.dict("os.environ",
                             {pa.DUCKDB_THREADS_ENV: "0"}):
            with self.assertRaises(ValueError):
                pa.default_duckdb_threads()

    def test_fresh_connection_passes_threads_to_duckdb(self):
        import duckdb
        seen: list[dict] = []

        class _Conn:
            def execute(self, *a, **k):
                return None

            def close(self):
                return None

        def _connect(*args, **kwargs):
            seen.append(kwargs)
            return _Conn()

        with mock.patch.object(duckdb, "connect", _connect), \
                mock.patch("fhir4ds.fhirpath.duckdb.register_fhirpath",
                           lambda conn: True):
            pa._fresh_connection(3)
        self.assertEqual(seen[0]["config"]["threads"], 3)
        self.assertTrue(seen[0]["config"]["allow_unsigned_extensions"])


class TestDuckdbThreadsAreRecorded(_CorpusCase):
    def test_report_records_effective_thread_count(self):
        with mock.patch.dict("os.environ", {pa.DUCKDB_THREADS_ENV: "2"}):
            rep = pa.run_benchmark(self.corpus_path, self.base / "thr_out",
                                   num_patients=1, skip_autocoding=True)
        self.assertEqual(rep["duckdb_threads"], 2)

    def test_explicit_argument_wins_over_env(self):
        with mock.patch.dict("os.environ", {pa.DUCKDB_THREADS_ENV: "2"}):
            rep = pa.run_benchmark(self.corpus_path, self.base / "thr_out2",
                                   num_patients=1, skip_autocoding=True,
                                   duckdb_threads=5)
        self.assertEqual(rep["duckdb_threads"], 5)

    def test_invalid_argument_rejected(self):
        with self.assertRaises(ValueError):
            pa.run_benchmark(self.corpus_path, self.base / "thr_out3",
                             num_patients=1, skip_autocoding=True,
                             duckdb_threads=0)


if __name__ == "__main__":
    unittest.main()
