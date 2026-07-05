"""Step 5 — NotesPipeline multiprocessing pool (slow / opt-in).

These tests exercise the parallel path. They are gated by
``pytest.mark.slow`` and additionally skip when ``medterm4ds`` is not
importable. The pool is exercised via a mocked ``medterm4ds`` module so
the tests are hermetic.
"""

from __future__ import annotations

import pickle
import sys
import types
from dataclasses import dataclass

import pytest

from fhir4ds.cql.loader.notes_pipeline import (
    NotesPipeline,
    NotesPipelineConfig,
    _init_worker,
    _worker_extract_fragments,
    _WORKER_ENGINE,
    _WORKER_EXTRACT_KWARGS,
)


pytestmark = [pytest.mark.slow]


@dataclass
class _MockConcept:
    code: str
    source: str
    display: str
    matched_text: str
    status: str = "affirmed"
    confidence: float = 0.95
    match_grade: str = "certain"
    span_start: int = 0
    span_end: int = 0


# ── Picklability regression (audit S1) ────────────────────────────────


def test_worker_function_has_no_self_closure():
    """The worker function MUST be module-level — no closure over self.

    If a future refactor moves it inside NotesPipeline, ``self`` (and
    the parent's DuckDB connection) would be pickled into workers,
    breaking fork-safety.
    """
    # ``_worker_extract_fragments`` must be a module-level function.
    # Methods are detected by checking for ``__self__``.
    assert not hasattr(_worker_extract_fragments, "__self__"), (
        "Worker function must not be bound to a class instance"
    )
    # It must be picklable.
    try:
        pickle.dumps(_worker_extract_fragments)
    except Exception as exc:
        pytest.fail(f"Worker function not picklable: {exc}")


def test_init_worker_has_no_self_closure():
    assert not hasattr(_init_worker, "__self__")
    try:
        pickle.dumps(_init_worker)
    except Exception as exc:
        pytest.fail(f"_init_worker not picklable: {exc}")


# ── Worker function contract (with mocked medterm4ds) ────────────────


def test_worker_returns_per_fragment_grouping(monkeypatch):
    """Worker output shape: outer list = fragments, inner = concepts."""
    @dataclass
    class _Engine:
        def extract(self, text, **kw):
            return [_MockConcept(
                code="C-1", source="SNOMEDCT_US",
                display=text[:10], matched_text=text,
                span_start=0, span_end=len(text),
            )]

    monkeypatch.setattr(
        "fhir4ds.cql.loader.notes_pipeline._WORKER_ENGINE", _Engine()
    )
    monkeypatch.setattr(
        "fhir4ds.cql.loader.notes_pipeline._WORKER_EXTRACT_KWARGS",
        {"format": "codes"},
    )

    @dataclass
    class _Fragment:
        text: str
        source_ref: str
        path: str

    fragments = [_Fragment(text="hello", source_ref="Obs/1", path="note[0].text")]
    out = _worker_extract_fragments(({"resourceType": "Observation"}, fragments))
    assert len(out) == 1  # one fragment
    assert len(out[0]) == 1  # one concept
    assert isinstance(out[0][0], dict)  # dict at process boundary
    assert out[0][0]["code"] == "C-1"


def test_worker_converts_dataclass_to_dict():
    """Worker output is plain dicts, not dataclasses."""
    @dataclass
    class _MockEngine:
        def extract(self, text, **kw):
            return [_MockConcept(
                code="X", source="S", display="D", matched_text="m",
            )]

    # Use the global engine; this test sets it directly.
    import fhir4ds.cql.loader.notes_pipeline as np_mod
    original_engine = np_mod._WORKER_ENGINE
    original_kwargs = np_mod._WORKER_EXTRACT_KWARGS
    np_mod._WORKER_ENGINE = _MockEngine()
    np_mod._WORKER_EXTRACT_KWARGS = {"format": "codes"}
    try:
        @dataclass
        class _F:
            text: str
            source_ref: str
            path: str
        out = np_mod._worker_extract_fragments(
            ({"resourceType": "Observation"}, [_F(text="t", source_ref="r", path="p")])
        )
        assert isinstance(out[0][0], dict)
        # Pickle round-trip must succeed (process-boundary safety)
        pickle.loads(pickle.dumps(out[0][0]))
    finally:
        np_mod._WORKER_ENGINE = original_engine
        np_mod._WORKER_EXTRACT_KWARGS = original_kwargs


def test_worker_handles_engine_failure():
    """If medterm4ds.extract raises, worker returns empty fragment list."""
    @dataclass
    class _BadEngine:
        def extract(self, text, **kw):
            raise RuntimeError("boom")

    import fhir4ds.cql.loader.notes_pipeline as np_mod
    original_engine = np_mod._WORKER_ENGINE
    np_mod._WORKER_ENGINE = _BadEngine()
    np_mod._WORKER_EXTRACT_KWARGS = {"format": "codes"}
    try:
        @dataclass
        class _F:
            text: str
            source_ref: str
            path: str
        out = np_mod._worker_extract_fragments(
            ({"resourceType": "Observation"}, [_F(text="t", source_ref="r", path="p")])
        )
        assert out == [[]]
    finally:
        np_mod._WORKER_ENGINE = original_engine


# ── extract_kwargs centralization ────────────────────────────────────


def test_extract_kwargs_matches_call_medterm4ds(monkeypatch):
    """_extract_kwargs must produce the same dict as _call_medterm4ds."""
    cfg = NotesPipelineConfig(
        categories=["condition"],
        mode="hybrid",
        min_grade="certain",
        include_negated=True,
        include_uncertain=False,
        include_historical=True,
    )
    pipe = NotesPipeline(cfg)
    expected = {
        "format": "codes",
        "categories": ["condition"],
        "mode": "hybrid",
        "min_grade": "certain",
        "include_negated": True,
        "include_uncertain": False,
        "include_historical": True,
    }
    assert pipe._extract_kwargs() == expected


# ── Parallel dispatch via real Pool (medterm4ds mocked) ──────────────


def test_parallel_dispatch_with_mocked_engine(monkeypatch):
    """End-to-end test of _extract_batch_parallel with a mocked Pool.

    We monkeypatch ``multiprocessing.Pool`` to run in-process so the
    test doesn't fork (which would break the monkeypatched medterm4ds
    module reference).
    """
    @dataclass
    class _MockEngine:
        def extract(self, text, **kw):
            return [_MockConcept(
                code="C-1", source="SNOMEDCT_US",
                display=text[:5], matched_text=text,
                span_start=0, span_end=len(text),
            )]

    fake_module = types.ModuleType("medterm4ds")
    fake_module.connect = lambda: _MockEngine()
    fake_module.__index_version__ = "v1"
    monkeypatch.setitem(sys.modules, "medterm4ds", fake_module)

    # Replace multiprocessing.Pool with an in-process executor that
    # honors the same initializer contract.
    from multiprocessing import Pool as _RealPool
    from multiprocessing.pool import ThreadPool

    class _InProcessPool:
        def __init__(self, processes=None, *, initializer=None, initargs=()):
            self._initializer = initializer
            self._initargs = initargs
            if initializer:
                initializer(*initargs)

        def map(self, fn, iterable, chunksize=None):
            return [fn(x) for x in iterable]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("multiprocessing.Pool", _InProcessPool)

    cfg = NotesPipelineConfig(
        batch_size=10, workers=2, parallel_threshold=2,
    )
    pipe = NotesPipeline(cfg)

    resources = [
        {"resourceType": "Observation", "id": f"o-{i}",
         "subject": {"reference": "Patient/p1"},
         "note": [{"text": f"diabetes {i}"}]}
        for i in range(5)
    ]
    out = pipe.extract_conditions_batch(resources)
    assert len(out) == 5
    # Each resource has 1 derived Condition
    for conds in out:
        assert len(conds) == 1
        assert conds[0]["resourceType"] == "Condition"
