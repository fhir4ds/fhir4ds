"""Unit tests for AutoCoder (uses stub endpoint, no medterm4ds).

Reference: FDD §5.1 — covers all 9 invariants (INV-1 through INV-9)
plus threshold filtering and top-k truncation.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Optional

import duckdb
import pytest

from fhir4ds.cql.loader.auto_coder import AutoCoder, AutoCoderConfig
from fhir4ds.cql.loader.autocoding_extension import (
    AUTOCODING_EXTENSION_URL,
    is_autocoded,
)


# ── Stub endpoint ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class _StubSearchResult:
    """Mirrors fhir4ds.cql.terminology.SearchResult shape."""
    system: str
    code: str
    display: Optional[str]
    score: float
    match_grade: str
    search_mode: str
    index_version: Optional[str]


class _StubEndpoint:
    """In-memory stub implementing the TerminologyEndpoint Protocol.

    Records every call to search_batch / search_text for assertion.
    """

    def __init__(self, results_by_query: Optional[dict[str, list]] = None,
                 default_results: Optional[list] = None,
                 raise_on_search: bool = False,
                 index_version: str = "2026AA-bm25-v3") -> None:
        self._results_by_query = results_by_query or {}
        self._default_results = default_results or []
        self._raise_on_search = raise_on_search
        self._index_version = index_version
        self.search_batch_calls: list[tuple[list, str]] = []
        self.search_text_calls: list[tuple[str, str, str]] = []

    def expand(self, valueset_url: str):
        raise NotImplementedError

    def expand_intensional(self, value_set: dict):
        raise NotImplementedError

    def search_text(self, query: str, category: str, *, mode: str = "hybrid"):
        self.search_text_calls.append((query, category, mode))
        if self._raise_on_search:
            raise RuntimeError("stub: forced search_text failure")
        # If we have a query-specific hit, return it; otherwise fall through
        # to the default list, padding with index_version from the stub.
        results = self._results_by_query.get(query, self._default_results)
        return [self._with_version(r) for r in results]

    def search_batch(self, queries, *, mode: str = "hybrid"):
        self.search_batch_calls.append((list(queries), mode))
        if self._raise_on_search:
            raise RuntimeError("stub: forced search_batch failure")
        out = []
        for q, category in queries:
            results = self._results_by_query.get(q, self._default_results)
            out.append([self._with_version(r) for r in results])
        return out

    def _with_version(self, r):
        # Make sure index_version is set on returned results (the stub
        # may be constructed without it).
        if isinstance(r, _StubSearchResult) and r.index_version is None:
            return _StubSearchResult(
                system=r.system, code=r.code, display=r.display,
                score=r.score, match_grade=r.match_grade,
                search_mode=r.search_mode, index_version=self._index_version,
            )
        return r


@pytest.fixture
def duckdb_con():
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def endpoint():
    """Default stub with a known-good result for 'Type 2 Diabetes Mellitus'.

    The stub keys match the RAW query text passed by AutoCoder (i.e. the
    original CodeableConcept.text, NOT the normalized form — AutoCoder
    normalizes only for the cache key, not for the endpoint call).
    """
    return _StubEndpoint(
        results_by_query={
            "Type 2 Diabetes Mellitus": [
                _StubSearchResult(
                    system="http://snomed.info/sct",
                    code="44054006",
                    display="Type 2 diabetes mellitus (disorder)",
                    score=0.95,
                    match_grade="certain",
                    search_mode="hybrid",
                    index_version=None,  # endpoint will stamp _index_version
                ),
                _StubSearchResult(
                    system="http://snomed.info/sct",
                    code="73211009",
                    display="Diabetes mellitus (disorder)",
                    score=0.78,
                    match_grade="probable",
                    search_mode="hybrid",
                    index_version=None,
                ),
            ],
            "Essential Hypertension": [
                _StubSearchResult(
                    system="http://snomed.info/sct",
                    code="59621000",
                    display="Essential hypertension (disorder)",
                    score=0.92,
                    match_grade="certain",
                    search_mode="hybrid",
                    index_version=None,
                ),
            ],
        }
    )


# ── Fixtures: simple text-only Condition builders ────────────────────


def _text_only_condition(text: str, rid: str = "c1") -> dict:
    return {
        "resourceType": "Condition",
        "id": rid,
        "subject": {"reference": "Patient/p1"},
        "code": {"text": text},
    }


# ── INV-2: text preserved unchanged ───────────────────────────────────


def test_inv2_text_preserved_after_augmentation(duckdb_con, endpoint):
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    text_before = resource["code"]["text"]
    ac.augment_resource(resource)
    assert resource["code"]["text"] == text_before  # byte-identical


# ── INV-3: resources without text are untouched ───────────────────────


@pytest.mark.parametrize(
    "code_value",
    [
        None,                # missing text
        "",                  # empty
        "   ",               # whitespace only
    ],
)
def test_inv3_text_absent_variants_untouched(duckdb_con, endpoint, code_value):
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = {
        "resourceType": "Condition", "id": "c1",
        "code": {} if code_value is None else {"text": code_value},
    }
    snapshot = copy.deepcopy(resource)
    ac.augment_resource(resource)
    assert resource == snapshot  # nothing mutated
    assert endpoint.search_batch_calls == []  # no endpoint call


def test_inv3_coding_only_no_text_untouched(duckdb_con, endpoint):
    """Resource with coding[] but no text is left untouched."""
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = {
        "resourceType": "Condition", "id": "c1",
        "code": {
            "coding": [
                {"system": "http://snomed.info/sct", "code": "73211009"}
            ]
        },
    }
    snapshot = copy.deepcopy(resource)
    ac.augment_resource(resource)
    assert resource == snapshot


# ── INV-4: existing coding[] is NOT re-coded ──────────────────────────


def test_inv4_existing_coding_not_replaced(duckdb_con, endpoint):
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = {
        "resourceType": "Condition", "id": "c1",
        "code": {
            "text": "Asthma",
            "coding": [
                {"system": "http://snomed.info/sct", "code": "195967001"}
            ],
        },
    }
    ac.augment_resource(resource)
    codings = resource["code"]["coding"]
    # Existing coding preserved, NO additional auto-coded entry appended.
    assert len(codings) == 1
    assert codings[0]["code"] == "195967001"
    assert not is_autocoded(codings[0])


# ── INV-5: every appended Coding has all 6 sub-extension fields ───────


def test_inv5_all_six_extension_fields_present(duckdb_con, endpoint):
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)

    codings = resource["code"]["coding"]
    assert len(codings) >= 1
    for coding in codings:
        assert "extension" in coding
        assert len(coding["extension"]) == 1
        ext = coding["extension"][0]
        assert ext["url"] == AUTOCODING_EXTENSION_URL
        sub_urls = {s["url"] for s in ext["extension"]}
        assert sub_urls == {
            "engine", "engine-version", "search-mode",
            "score", "match-grade", "index-version",
        }
        # Value types per FDD §3d
        by_url = {s["url"]: s for s in ext["extension"]}
        assert isinstance(by_url["engine"]["valueString"], str)
        assert isinstance(by_url["engine-version"]["valueString"], str)
        assert isinstance(by_url["search-mode"]["valueCode"], str)
        assert isinstance(by_url["score"]["valueDecimal"], float)
        assert isinstance(by_url["match-grade"]["valueCode"], str)
        assert isinstance(by_url["index-version"]["valueString"], str)


# ── INV-6: userSelected == False ──────────────────────────────────────


def test_inv6_user_selected_false(duckdb_con, endpoint):
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    for coding in resource["code"]["coding"]:
        assert coding["userSelected"] is False


# ── INV-7: cache hit determinism ──────────────────────────────────────


def test_inv7_identical_input_identical_output_across_runs(duckdb_con, endpoint):
    """Two runs on the same input produce identical coding[] bytes."""
    cfg = AutoCoderConfig(index_version="v1")
    ac1 = AutoCoder(endpoint, duckdb_con, config=cfg)
    r1 = _text_only_condition("Type 2 Diabetes Mellitus")
    ac1.augment_resource(r1)

    # Second run on a fresh connection so the cache is cold; the endpoint
    # stub returns identical results, so the appended Codings must be identical.
    con2 = duckdb.connect(":memory:")
    try:
        ac2 = AutoCoder(endpoint, con2, config=cfg)
        r2 = _text_only_condition("Type 2 Diabetes Mellitus")
        ac2.augment_resource(r2)
        # Compare only the appended Codings (id text may differ — we used the same).
        assert json.dumps(r1["code"]["coding"], sort_keys=True) == \
               json.dumps(r2["code"]["coding"], sort_keys=True)
    finally:
        con2.close()


def test_inv7_cache_hit_returns_byte_identical(duckdb_con, endpoint):
    """Same key on the SAME connection returns identical codings (cache hit)."""
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    r1 = _text_only_condition("Type 2 Diabetes Mellitus", "c1")
    ac.augment_resource(r1)
    first_codings = copy.deepcopy(r1["code"]["coding"])

    # Second call on the same resource — should hit cache (no new endpoint call).
    calls_before = len(endpoint.search_batch_calls)
    r2 = _text_only_condition("Type 2 Diabetes Mellitus", "c2")
    ac.augment_resource(r2)
    assert len(endpoint.search_batch_calls) == calls_before  # cache hit
    # Same coding bytes (cache hit deterministic).
    assert json.dumps(first_codings, sort_keys=True) == \
           json.dumps(r2["code"]["coding"], sort_keys=True)


# ── INV-8: index_version change forces cache miss ────────────────────


def test_inv8_index_version_change_invalidates_cache(duckdb_con, endpoint):
    """Pin v1, populate; switch to v2 — second call must hit endpoint again."""
    ac_v1 = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    r1 = _text_only_condition("Type 2 Diabetes Mellitus")
    ac_v1.augment_resource(r1)
    calls_after_first = len(endpoint.search_batch_calls)

    # Same connection, but a new AutoCoder with different pinned index_version.
    ac_v2 = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v2"))
    r2 = _text_only_condition("Type 2 Diabetes Mellitus")
    ac_v2.augment_resource(r2)
    # search_batch called again (cache miss due to PK change).
    assert len(endpoint.search_batch_calls) > calls_after_first


# ── INV-9: augment_resource never raises ──────────────────────────────


def test_inv9_endpoint_failure_does_not_raise(duckdb_con):
    """Endpoint raising mid-batch leaves resource unchanged; no exception escapes."""
    ep = _StubEndpoint(raise_on_search=True)
    ac = AutoCoder(ep, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    snapshot = copy.deepcopy(resource)
    # Must NOT raise.
    result = ac.augment_resource(resource)
    assert result is resource
    assert resource == snapshot  # left unchanged


def test_inv9_malformed_resource_does_not_raise(duckdb_con, endpoint):
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    # Malformed inputs.
    for bad in [
        None,
        "not a dict",
        42,
        [],
        {"no_resource_type": True},
        {"resourceType": "Condition"},  # no code
        {"resourceType": "Condition", "code": "not-a-dict"},
    ]:
        # Must not raise — augment_resource swallows everything.
        result = ac.augment_resource(bad)  # type: ignore[arg-type]
        # For dict inputs, the same reference is returned.
        if isinstance(bad, dict):
            assert result is bad


# ── Threshold filtering + top_k truncation ────────────────────────────


def test_threshold_filtering_drops_below_min_match_grade(duckdb_con, endpoint):
    """Default min_match_grade='certain' drops the 'probable' result."""
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    codings = resource["code"]["coding"]
    # 'type 2 diabetes mellitus' query returns 1 certain + 1 probable; only
    # the certain should survive (threshold='certain').
    assert len(codings) == 1
    assert codings[0]["code"] == "44054006"


def test_threshold_filtering_relaxed_to_probable(duckdb_con, endpoint):
    """Lowering threshold to 'probable' keeps both results."""
    cfg = AutoCoderConfig(index_version="v1", min_match_grade="probable", top_k=10)
    ac = AutoCoder(endpoint, duckdb_con, config=cfg)
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    codings = resource["code"]["coding"]
    # Both results should survive.
    codes = {c["code"] for c in codings}
    assert codes == {"44054006", "73211009"}


def test_top_k_truncation(duckdb_con, endpoint):
    """top_k caps the number of appended Codings."""
    cfg = AutoCoderConfig(index_version="v1", min_match_grade="probable", top_k=1)
    ac = AutoCoder(endpoint, duckdb_con, config=cfg)
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    assert len(resource["code"]["coding"]) == 1
    # Higher-score result wins (44054006 scored 0.95 > 0.78).
    assert resource["code"]["coding"][0]["code"] == "44054006"


# ── Cache round-trip ──────────────────────────────────────────────────


def test_cache_miss_then_hit_no_second_endpoint_call(duckdb_con, endpoint):
    """First call hits endpoint; second call with same text hits cache."""
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    r1 = _text_only_condition("Essential Hypertension", "c1")
    ac.augment_resource(r1)
    assert len(endpoint.search_batch_calls) == 1
    r2 = _text_only_condition("Essential Hypertension", "c2")
    ac.augment_resource(r2)
    # Still only 1 call — second hit the cache.
    assert len(endpoint.search_batch_calls) == 1


def test_cache_table_created(duckdb_con, endpoint):
    AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    row = duckdb_con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'autocoding_cache'"
    ).fetchone()
    assert row is not None


# ── Category skip for unknown resource types ──────────────────────────


def test_unknown_resource_type_skipped(duckdb_con, endpoint):
    """Patient has no category — skipped silently with DEBUG (no endpoint call)."""
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = {"resourceType": "Patient", "id": "p1", "name": [{"family": "Doe"}]}
    snapshot = copy.deepcopy(resource)
    ac.augment_resource(resource)
    assert resource == snapshot
    assert endpoint.search_batch_calls == []


# ── index_version probe-and-pin ───────────────────────────────────────


def test_probe_and_pin_resolves_index_version(duckdb_con):
    """When index_version=None in config, first batch probes and pins."""
    ep = _StubEndpoint(
        results_by_query={
            "Type 2 Diabetes Mellitus": [
                _StubSearchResult(
                    system="http://snomed.info/sct", code="44054006",
                    display=None, score=0.9, match_grade="certain",
                    search_mode="hybrid", index_version=None,
                )
            ],
        },
        index_version="2026AA-live",
    )
    ac = AutoCoder(ep, duckdb_con, config=AutoCoderConfig(index_version=None))
    r = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(r)
    # The probe call (search_text) should have fired.
    assert len(ep.search_text_calls) >= 1
    # Pinned version should be the live one.
    coding = r["code"]["coding"][0]
    ext = coding["extension"][0]
    iv = {s["url"]: s for s in ext["extension"]}["index-version"]["valueString"]
    assert iv == "2026AA-live"


# ── Resource with non-existent path skipped ───────────────────────────


def test_missing_codeable_path_skipped(duckdb_con, endpoint):
    """Condition with no 'code' field at all — skipped silently."""
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(index_version="v1"))
    resource = {"resourceType": "Condition", "id": "c1"}
    snapshot = copy.deepcopy(resource)
    ac.augment_resource(resource)
    assert resource == snapshot
    assert endpoint.search_batch_calls == []


# ── medterm4ds 0.0.9 alignment (it1 Domain 12 SKEPTIC) ────────────────


def test_match_grade_order_matches_medterm4ds_vocabulary_it1d12():
    """QA-002: 'possible'/'exact'/'broader' are real medterm4ds grades.

    medterm4ds services/extraction.py ``_GRADE_ORDER`` is the
    authoritative order: certain=exact=0, probable=1, possible=2,
    broader=3. 'ambiguous'/'no-match' are legacy fhir4ds aliases kept
    only for pre-alignment cache rows.
    """
    from fhir4ds.cql.loader.auto_coder import _MATCH_GRADE_ORDER as order

    assert order["certain"] == 0
    assert order["exact"] == 0
    assert order["probable"] == 1
    assert order["possible"] == 2
    assert order["broader"] == 3
    # Legacy aliases rank at the weakest tiers (cache-row compat only).
    assert order["ambiguous"] >= order["possible"]
    assert order["no-match"] >= order["broader"]


def test_possible_grade_survives_relaxed_threshold_it1d12(duckdb_con):
    """QA-002: min_match_grade='ambiguous'/'no-match' must keep 'possible'.

    Under medterm4ds 0.0.9 every hybrid row that is neither certain nor
    probable grades 'possible'. The pre-fix rank map defaulted unknown
    grades to 3, dropping them at the 'ambiguous' threshold.
    """
    endpoint = _StubEndpoint(default_results=[
        _StubSearchResult(
            system="http://snomed.info/sct", code="C", display=None,
            score=0.60, match_grade="possible",
            search_mode="hybrid", index_version=None,
        ),
    ])
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(
        index_version="v1", min_match_grade="ambiguous", top_k=3,
    ))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    codes = [c["code"] for c in resource["code"]["coding"]]
    assert "C" in codes


def test_exact_grade_survives_certain_threshold_it1d12(duckdb_con):
    """QA-002: 'exact' (canonical mode, rank 0) must survive min='certain'.

    medterm4ds ranks 'exact' EQUAL to 'certain'; the pre-fix map treated
    it as unknown (rank 3) and dropped it at every threshold.
    """
    endpoint = _StubEndpoint(default_results=[
        _StubSearchResult(
            system="http://snomed.info/sct", code="D", display=None,
            score=1.0, match_grade="exact",
            search_mode="canonical", index_version=None,
        ),
    ])
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(
        index_version="v1", min_match_grade="certain", top_k=3,
    ))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    codes = [c["code"] for c in resource["code"]["coding"]]
    assert "D" in codes


def test_engine_ranking_order_preserved_over_two_scale_scores_it1d12(duckdb_con):
    """QA-003: no score re-sort — 0.0.9 'score' is two-scaled.

    medterm4ds 0.0.9 hybrid returns RRF-fused order; score is the
    calibrated underlying value (cosine when semantic saw the row, else
    normalized BM25). A lexical-only BM25 row (score 1.0, 'possible')
    must NOT leapfrog an agreement-aware 'certain' row (cosine 0.93).
    """
    endpoint = _StubEndpoint(default_results=[
        _StubSearchResult(
            system="http://snomed.info/sct", code="FUSED-CERTAIN",
            display=None, score=0.93, match_grade="certain",
            search_mode="hybrid", index_version=None,
        ),
        _StubSearchResult(
            system="http://snomed.info/sct", code="LEX-ONLY-BM25",
            display=None, score=1.0, match_grade="possible",
            search_mode="hybrid", index_version=None,
        ),
    ])
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(
        index_version="v1", min_match_grade="no-match", top_k=2,
    ))
    resource = _text_only_condition("Type 2 Diabetes Mellitus")
    ac.augment_resource(resource)
    codes = [c["code"] for c in resource["code"]["coding"]]
    assert codes == ["FUSED-CERTAIN", "LEX-ONLY-BM25"], (
        "engine (RRF) order must be preserved; raw-score re-sort mixes "
        "cosine and BM25 scales"
    )


# -- AMUX-60 Gap 1: display-only codings --------------------------------------

def test_display_only_coding_is_coded_amux60_gap1(duckdb_con):
    """A coding[] whose entries all lack a code is a text carrier.

    The display becomes the query text; the original entry is preserved
    and the coded result is appended (legacy-export shape: the source
    knew the name but not the code).
    """
    endpoint = _StubEndpoint(default_results=[
        _StubSearchResult(
            system="http://snomed.info/sct", code="38341003",
            display="Hypertensive disorder", score=0.93,
            match_grade="certain", search_mode="semantic", index_version=None,
        ),
    ])
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(
        index_version="v1", min_match_grade="certain", top_k=3,
    ))
    resource = {
        "resourceType": "Condition", "id": "c1",
        "code": {"coding": [{"display": "Essential hypertension"}]},
    }
    ac.augment_resource(resource)
    codings = resource["code"]["coding"]
    assert codings[0] == {"display": "Essential hypertension"}  # preserved
    assert codings[1]["code"] == "38341003"  # coded from the display text


def test_genuinely_coded_concept_is_never_recoded_amux60_gap1(duckdb_con):
    """INV-4 intact: coding[] with at least one coded entry → untouched."""
    endpoint = _StubEndpoint(default_results=[
        _StubSearchResult(
            system="http://snomed.info/sct", code="X", display=None,
            score=1.0, match_grade="certain",
            search_mode="semantic", index_version=None,
        ),
    ])
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(
        index_version="v1", min_match_grade="certain", top_k=3,
    ))
    original = {"system": "http://snomed.info/sct", "code": "38341003"}
    resource = {
        "resourceType": "Condition", "id": "c2",
        "code": {"coding": [dict(original)], "text": "Essential hypertension"},
    }
    ac.augment_resource(resource)
    assert resource["code"]["coding"] == [original]


# -- AMUX-62: HTTP SearchResult dataclass contract -----------------------------

def test_http_dataclass_results_flow_through_autocoder_amux62(duckdb_con):
    """Pin the 0.0.21-bug contract: adapters may return SearchResult
    dataclasses (the HTTP adapter does); the AutoCoder must normalize
    them before its dict-API filtering/augmentation path.
    """
    import dataclasses

    from fhir4ds.cql.terminology.types import SearchResult

    @dataclasses.dataclass
    class _HTTPShapedEndpoint:
        default: list[SearchResult]

        def search_batch(self, queries, *, mode="hybrid"):
            return [list(self.default)]

        def search_text(self, query, category, *, mode="hybrid"):
            return list(self.default)

        def expand(self, valueset_url):
            return []

    endpoint = _HTTPShapedEndpoint(default=[
        SearchResult(
            system="http://snomed.info/sct", code="44054006",
            display="Type 2 diabetes mellitus", score=0.93,
            match_grade="certain", search_mode="hybrid", index_version="v1",
        ),
    ])
    ac = AutoCoder(endpoint, duckdb_con, config=AutoCoderConfig(
        index_version="v1", min_match_grade="certain", top_k=3,
    ))
    resource = _text_only_condition("uncontrolled type 2 diabetes")
    ac.augment_resource(resource)
    codes = [c["code"] for c in resource["code"]["coding"]]
    assert codes == ["44054006"]


def test_notes_pipeline_remote_extraction_amux60_gap2(monkeypatch):
    """extraction_endpoint routes $extract remotely; no medterm4ds import."""
    import json as _json

    import fhir4ds.cql.loader.notes_pipeline as np_mod
    from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

    bundle = {"resourceType": "Bundle", "type": "searchset", "entry": [
        {"resource": {"code": "44054006", "source": "SNOMEDCT_US",
                      "display": "Type 2 Diabetes", "matched_text": "diabetes",
                      "status": "affirmed", "confidence": 0.97,
                      "match_grade": "exact", "ner_label": "disorder",
                      "result_type": "condition", "span_start": 12, "span_end": 20}}]}
    calls = []
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return bundle
    def _get(url, params=None, timeout=None):
        calls.append((url, params))
        return _Resp()
    monkeypatch.setattr("httpx.get", _get)

    pipe = NotesPipeline(NotesPipelineConfig(
        extraction_endpoint="https://example.test/fhir", min_grade="probable"))
    resource = {"resourceType": "ClinicalImpression", "id": "ci",
                "subject": {"reference": "Patient/p"},
                "summary": "history of type 2 diabetes"}
    conds = pipe.extract_conditions(resource)
    assert calls and "$extract" in calls[0][0]
    assert len(conds) == 1
    assert conds[0]["code"]["coding"][0]["code"] == "44054006"
