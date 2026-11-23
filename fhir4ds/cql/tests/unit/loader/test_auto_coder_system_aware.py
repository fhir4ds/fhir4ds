"""FHIR4-24 acceptance tests: system-aware query precedence as AutoCoder DEFAULT.

Rule (Joel, 2026-11-20) — query text per CodeableConcept:
1. ``code.text`` when present.
2. ``display`` of a coding entry that is code-less OR coded in a
   NON-STANDARD system.
3. ``code`` string of a coding entry coded in a NON-STANDARD system
   (the MIMIC name-code case).
Concepts with ANY entry coded in a STANDARD system (SNOMED, LOINC,
RxNorm, CVX, ICD-9/10, CPT, UCUM, ...) are skipped entirely — the
concept is terminologically asserted. ``strict_coded_skip=True``
restores the legacy INV-4-everywhere behavior (any coded entry skips).

Writes APPEND standard codings alongside local originals
(userSelected=False) and the autocoding extension provenance records
the query source ('text'|'display'|'code') and the non-standard system
URI that justified legs 2/3.
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
    build_autocoding_extension,
    parse_autocoding_extension,
)


MIMIC_SYSTEM = "mimic-medication-name"
SNOMED = "http://snomed.info/sct"
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"


@dataclass(frozen=True)
class _StubSearchResult:
    system: str
    code: str
    display: Optional[str]
    score: float
    match_grade: str
    search_mode: str
    index_version: Optional[str]


class _StubEndpoint:
    """Records queries; returns one canned result for any query."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, str]] = []

    def expand(self, valueset_url: str):
        raise NotImplementedError

    def expand_intensional(self, value_set: dict):
        raise NotImplementedError

    def search_text(self, query: str, category: str, *, mode: str = "hybrid"):
        self.queries.append((query, category))
        return []

    def search_batch(self, queries, *, mode: str = "hybrid"):
        out = []
        for q, category in queries:
            self.queries.append((q, category))
            out.append([
                _StubSearchResult(
                    system=RXNORM,
                    code="310798",
                    display="insulin, regular, human",
                    score=0.97,
                    match_grade="certain",
                    search_mode="hybrid",
                    index_version="2026AA-bm25-v3",
                )
            ])
        return out


def _med_request(coding: list[dict], text: Optional[str] = None) -> dict:
    cc: dict = {"coding": coding}
    if text is not None:
        cc["text"] = text
    return {
        "resourceType": "MedicationRequest",
        "id": "m1",
        "medicationCodeableConcept": cc,
    }


def _autocoded_entries(resource: dict) -> list[dict]:
    coding = resource["medicationCodeableConcept"]["coding"]
    return [c for c in coding if parse_autocoding_extension(c) is not None]


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def endpoint():
    return _StubEndpoint()


def _coder(endpoint, **config_kwargs) -> AutoCoder:
    # index_version pinned so the one-shot "diabetes" probe never fires
    # and pollutes endpoint.queries.
    config_kwargs.setdefault("index_version", "test-index")
    return AutoCoder(endpoint, duckdb.connect(":memory:"), config=AutoCoderConfig(**config_kwargs))


# ── Leg 1: code.text wins (unchanged) ────────────────────────────────


def test_text_present_searches_from_text(con, endpoint):
    resource = _med_request(
        [{"system": MIMIC_SYSTEM, "code": "Insulin Regular"}], text="Insulin Regular"
    )
    original = copy.deepcopy(resource)
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == [("Insulin Regular", "medication")]
    # original coding preserved verbatim alongside the appended one
    assert resource["medicationCodeableConcept"]["coding"][:1] == original["medicationCodeableConcept"]["coding"]


# ── Leg 2a: code-less display entry (unchanged behavior) ─────────────


def test_codeless_display_entry_searches_from_display(con, endpoint):
    resource = _med_request([{"display": "Insulin Regular"}])
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == [("Insulin Regular", "medication")]


# ── Leg 2b: NON-standard coding with display → display ───────────────


def test_nonstandard_system_coding_with_display_searches_display(con, endpoint):
    resource = _med_request(
        [{"system": MIMIC_SYSTEM, "code": "ins-reg-abc", "display": "Insulin Regular"}]
    )
    original = copy.deepcopy(resource)
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == [("Insulin Regular", "medication")]
    # append-not-replace: original local coding still present verbatim
    assert resource["medicationCodeableConcept"]["coding"][0] == original["medicationCodeableConcept"]["coding"][0]
    auto = _autocoded_entries(resource)
    assert len(auto) == 1
    assert auto[0]["userSelected"] is False


# ── Leg 3: NON-standard coding with NO display → the code string (NEW) ─


def test_nonstandard_system_coding_without_display_searches_code(con, endpoint):
    """MIMIC name-code meds: the local code IS the medication name."""
    resource = _med_request([{"system": MIMIC_SYSTEM, "code": "Insulin Regular"}])
    original = copy.deepcopy(resource)
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == [("Insulin Regular", "medication")]
    assert resource["medicationCodeableConcept"]["coding"][0] == original["medicationCodeableConcept"]["coding"][0]
    assert len(_autocoded_entries(resource)) == 1


# ── Standard systems: untouched in default mode; strict legacy skip ──


def test_standard_system_coding_untouched_in_default_mode(con, endpoint):
    resource = _med_request([{"system": SNOMED, "code": "69647003"}])  # no display
    snapshot = copy.deepcopy(resource)
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == []  # never searched
    assert resource == snapshot


def test_strict_coded_skip_restores_legacy_behavior(con, endpoint):
    # Legacy INV-4-everywhere: ANY coded entry (even non-standard) skips.
    resource = _med_request([{"system": MIMIC_SYSTEM, "code": "Insulin Regular"}])
    snapshot = copy.deepcopy(resource)
    _coder(endpoint, strict_coded_skip=True).augment_resource(resource)
    assert endpoint.queries == []
    assert resource == snapshot

    # code-less display entries were still queried under legacy rules
    endpoint2 = _StubEndpoint()
    resource2 = _med_request([{"display": "Insulin Regular"}])
    _coder(endpoint2, strict_coded_skip=True).augment_resource(resource2)
    assert endpoint2.queries == [("Insulin Regular", "medication")]


# ── Provenance: query source + justifying system ─────────────────────


def test_provenance_records_query_source_and_system(con, endpoint):
    # leg 3 (code): source='code', system=MIMIC_SYSTEM
    resource = _med_request([{"system": MIMIC_SYSTEM, "code": "Insulin Regular"}])
    _coder(endpoint).augment_resource(resource)
    prov = parse_autocoding_extension(_autocoded_entries(resource)[0])
    assert prov["query_source"] == "code"
    assert prov["query_system"] == MIMIC_SYSTEM

    # leg 2b (display): source='display', system=MIMIC_SYSTEM
    endpoint2 = _StubEndpoint()
    resource = _med_request(
        [{"system": MIMIC_SYSTEM, "code": "x", "display": "Insulin Regular"}]
    )
    _coder(endpoint2).augment_resource(resource)
    prov = parse_autocoding_extension(_autocoded_entries(resource)[0])
    assert prov["query_source"] == "display"
    assert prov["query_system"] == MIMIC_SYSTEM

    # leg 1 (text): source='text', no justifying system
    endpoint3 = _StubEndpoint()
    resource = _med_request([{"display": "ignored"}], text="Insulin Regular")
    _coder(endpoint3).augment_resource(resource)
    prov = parse_autocoding_extension(_autocoded_entries(resource)[0])
    assert prov["query_source"] == "text"
    assert prov["query_system"] is None


# ── Mixed concepts: any standard entry ⇒ terminologically asserted ───


def test_mixed_concept_with_standard_entry_skipped_entirely(con, endpoint):
    """DESIGN DECISION (documented): one local + one standard entry means
    the concept IS terminologically asserted — skip, do not augment."""
    resource = _med_request(
        [
            {"system": MIMIC_SYSTEM, "code": "Insulin Regular"},
            {"system": SNOMED, "code": "69647003", "display": "Insulin"},
        ]
    )
    snapshot = copy.deepcopy(resource)
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == []
    assert resource == snapshot


# ── Determinism ──────────────────────────────────────────────────────


def test_augment_twice_identical_results(con, endpoint):
    base = _med_request([{"system": MIMIC_SYSTEM, "code": "Insulin Regular"}])
    r1 = copy.deepcopy(base)
    r2 = copy.deepcopy(base)
    _coder(_StubEndpoint()).augment_resource(r1)
    _coder(_StubEndpoint()).augment_resource(r2)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)

    # re-augmenting an already-augmented resource is a no-op (appended
    # codings are in standard systems → concept now asserted)
    coder = _coder(_StubEndpoint())
    coder.augment_resource(r1)
    snapshot = copy.deepcopy(r1)
    coder.augment_resource(r1)
    assert r1 == snapshot


# ── Config validation ────────────────────────────────────────────────


def test_strict_coded_skip_must_be_bool():
    with pytest.raises(ValueError):
        AutoCoderConfig(strict_coded_skip="yes")


def test_default_config_has_system_aware_default():
    assert AutoCoderConfig().strict_coded_skip is False


# ── Extension backward compatibility ─────────────────────────────────


def test_v1_extension_rows_still_parse():
    """Old (pre-FHIR4-24) extensions lack query-source/query-system —
    parse must return None for the new fields, not raise."""
    legacy_coding = {
        "system": RXNORM,
        "code": "310798",
        "extension": [
            {
                "url": AUTOCODING_EXTENSION_URL,
                "extension": [
                    {"url": "engine", "valueString": "medterm4ds"},
                    {"url": "engine-version", "valueString": "0.0.9"},
                    {"url": "search-mode", "valueCode": "hybrid"},
                    {"url": "score", "valueDecimal": 0.97},
                    {"url": "match-grade", "valueCode": "certain"},
                    {"url": "index-version", "valueString": "2026AA-bm25-v3"},
                ],
            }
        ],
    }
    prov = parse_autocoding_extension(legacy_coding)
    assert prov is not None
    assert prov["engine"] == "medterm4ds"
    assert prov["query_source"] is None
    assert prov["query_system"] is None


def test_builder_rejects_unknown_query_source():
    with pytest.raises(ValueError):
        build_autocoding_extension(
            engine="medterm4ds",
            engine_version="0.0.9",
            search_mode="hybrid",
            score=0.9,
            match_grade="certain",
            index_version=None,
            query_source="bogus",
        )


# ── Standard-system registry coverage (derived from existing knowledge) ─


@pytest.mark.parametrize(
    "system",
    [
        "http://snomed.info/sct",
        "http://snomed.info/sct/731000124108",  # module URL
        "urn:oid:2.16.840.1.113883.6.96",       # SNOMED OID
        "http://loinc.org",
        "http://www.nlm.nih.gov/research/umls/rxnorm",
        "http://hl7.org/fhir/sid/icd-10-cm",
        "http://hl7.org/fhir/sid/icd-9-cm",
        "http://hl7.org/fhir/sid/cvx",
        "http://www.ama-assn.org/go/cpt",
        "http://unitsofmeasure.org",            # UCUM
    ],
)
def test_standard_systems_recognized(con, endpoint, system):
    resource = _med_request([{"system": system, "code": "x"}])
    snapshot = copy.deepcopy(resource)
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == []
    assert resource == snapshot


@pytest.mark.parametrize("system", ["", None, "mimic-medication-name", "http://example.org/local"])
def test_unknown_systems_default_nonstandard(con, endpoint, system):
    entry: dict = {"code": "Insulin Regular"}
    if system is not None:
        entry["system"] = system
    resource = _med_request([entry])
    _coder(endpoint).augment_resource(resource)
    assert endpoint.queries == [("Insulin Regular", "medication")]
