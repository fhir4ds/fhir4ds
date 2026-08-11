"""Unit tests for NotesPipeline.

medterm4ds is mocked via monkeypatch so these tests run without the
``[ner]`` extra installed. Each test injects a fake ``extract`` function
returning canned :class:`_MockConcept` instances.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

import pytest

from fhir4ds.cql.loader.autocoding_extension import (
    parse_autocoding_extension,
    AUTOCODING_EXTENSION_URL,
)
from fhir4ds.cql.loader.derived_from_text_extension import (
    DERIVED_FROM_TEXT_EXTENSION_URL,
    parse_derived_from_text_extension,
)
from fhir4ds.cql.loader.notes_pipeline import (
    NotesPipeline,
    NotesPipelineConfig,
)


@dataclass
class _MockConcept:
    """Mirror of medterm4ds ExtractedConcept (subset used by the pipeline)."""
    code: str
    source: str
    display: str
    matched_text: str
    status: str = "affirmed"
    section: str | None = None
    confidence: float = 0.95
    match_grade: str = "certain"
    category: str = "condition"
    span_start: int = 0
    span_end: int = 0


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def mock_medterm4ds(monkeypatch):
    """Install a fake ``medterm4ds`` module whose ``extract`` returns canned concepts.

    Each test assigns ``fake_module.extract`` to a custom callable.
    """
    fake = types.ModuleType("medterm4ds")
    fake.__index_version__ = "test-index-2026AA"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "medterm4ds", fake)
    return fake


def _observation(note_text: str = "Patient has diabetes.") -> dict:
    return {
        "resourceType": "Observation",
        "id": "obs-1",
        "subject": {"reference": "Patient/pat-1"},
        "note": [{"text": note_text}],
    }


# ----------------------------------------------------------------------
# affirmed concept -> Condition created with correct shape
# ----------------------------------------------------------------------

def test_affirmed_concept_creates_condition(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes mellitus",
        matched_text="diabetes", status="affirmed",
        confidence=0.93, match_grade="certain",
        span_start=12, span_end=20,
    )]

    pipeline = NotesPipeline(NotesPipelineConfig())
    conditions = pipeline.extract_conditions(_observation())
    assert len(conditions) == 1
    cond = conditions[0]
    assert cond["resourceType"] == "Condition"
    # id is deterministic sha256, length 32
    assert isinstance(cond["id"], str) and len(cond["id"]) == 32
    # subject propagated
    assert cond["subject"] == {"reference": "Patient/pat-1"}
    # code/CodeableConcept
    code = cond["code"]["coding"][0]
    assert code["code"] == "73211009"
    assert code["system"] == "http://snomed.info/sct"  # mnemonic normalized
    assert code["display"] == "Diabetes mellitus"
    assert code["userSelected"] is False
    # status defaults
    assert cond["clinicalStatus"]["coding"][0]["code"] == "active"
    assert cond["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    # evidence points back at source
    assert cond["evidence"][0]["detail"][0]["reference"] == "Observation/obs-1"


# ----------------------------------------------------------------------
# negated concept -> NO Condition (default)
# ----------------------------------------------------------------------

def test_negated_concept_skipped_by_default(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="negated",
        span_start=0, span_end=8,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())  # include_negated=False
    assert pipeline.extract_conditions(_observation()) == []


# ----------------------------------------------------------------------
# uncertain concept -> NO Condition (default)
# ----------------------------------------------------------------------

def test_uncertain_concept_skipped_by_default(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="uncertain",
        span_start=0, span_end=8,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())
    assert pipeline.extract_conditions(_observation()) == []


# ----------------------------------------------------------------------
# include_negated=True -> Condition created
# ----------------------------------------------------------------------

def test_include_negated_creates_condition(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="negated",
        span_start=0, span_end=8,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig(include_negated=True))
    conditions = pipeline.extract_conditions(_observation())
    assert len(conditions) == 1


# ----------------------------------------------------------------------
# Source resource is Condition -> skipped (no infinite loop, INV-4)
# ----------------------------------------------------------------------

def test_source_resource_condition_is_skipped(mock_medterm4ds):
    """INV-4: never derive Conditions from Conditions."""
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        span_start=0, span_end=8,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())
    source = {
        "resourceType": "Condition",
        "id": "cond-source",
        "note": [{"text": "Patient has diabetes."}],
    }
    assert pipeline.extract_conditions(source) == []


# ----------------------------------------------------------------------
# medterm4ds.extract raises -> no Conditions, no exception escapes (INV-3)
# ----------------------------------------------------------------------

def test_medterm4ds_extract_raises_returns_empty(mock_medterm4ds):
    """INV-3: medterm4ds.extract raising is contained to a warning."""
    def boom(text, **kw):
        raise RuntimeError("medterm4ds internal error")
    mock_medterm4ds.extract = boom
    pipeline = NotesPipeline(NotesPipelineConfig())
    # No exception should escape
    result = pipeline.extract_conditions(_observation())
    assert result == []


def test_extract_conditions_never_raises_on_bad_resource(mock_medterm4ds):
    """INV-3: even a structurally-broken input never raises."""
    mock_medterm4ds.extract = lambda text, **kw: []
    pipeline = NotesPipeline(NotesPipelineConfig())
    # Wrong type
    assert pipeline.extract_conditions(["not", "a", "dict"]) == []  # type: ignore[arg-type]
    # None
    assert pipeline.extract_conditions(None) == []  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Deterministic id: same source + same concept -> same Condition id
# ----------------------------------------------------------------------

def test_deterministic_id_same_source_same_concept(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        span_start=12, span_end=20,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())
    cond_a = pipeline.extract_conditions(_observation())[0]
    cond_b = pipeline.extract_conditions(_observation())[0]
    assert cond_a["id"] == cond_b["id"]


def test_deterministic_id_differs_across_different_sources(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        span_start=12, span_end=20,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())
    a = pipeline.extract_conditions(_observation())[0]
    other = _observation()
    other["id"] = "obs-2"
    b = pipeline.extract_conditions(other)[0]
    assert a["id"] != b["id"]


def test_deterministic_id_differs_across_code_systems_at_same_span(mock_medterm4ds):
    """REV-005: same code + same span + DIFFERENT system -> different id.

    Regression: previously the digest omitted ``system``, so two
    concepts from different code systems at the same span on the same
    source produced byte-identical Condition ids and the loader's
    (id, resourceType) dedup silently dropped the second. The hash now
    includes the post-normalization canonical URL.
    """
    mock_medterm4ds.extract = lambda text, **kw: [
        _MockConcept(
            code="73211009", source="SNOMEDCT_US", display="Diabetes",
            matched_text="diabetes", status="affirmed",
            span_start=12, span_end=20,
        ),
        _MockConcept(
            # Same code + same span, but a different code system.
            code="73211009", source="LNC", display="Diabetes lab",
            matched_text="diabetes", status="affirmed",
            span_start=12, span_end=20,
        ),
    ]
    pipeline = NotesPipeline(NotesPipelineConfig())
    conditions = pipeline.extract_conditions(_observation())
    assert len(conditions) == 2
    ids = [c["id"] for c in conditions]
    assert ids[0] != ids[1], (
        "Condition ids must differ when only the code system differs — "
        "REV-005 regression"
    )


def test_medterm4ds_engine_version_cached_per_instance(mock_medterm4ds):
    """REV-006: ``importlib.metadata.version`` lookup is cached on first use."""
    mock_medterm4ds.extract = lambda text, **kw: []
    pipeline = NotesPipeline(NotesPipelineConfig())
    # First call populates the cache.
    v1 = pipeline._medterm4ds_engine_version()
    # Mutate the cache to a sentinel and confirm subsequent reads use it.
    pipeline._medterm4ds_engine_version_cached = "sentinel-from-test"
    v2 = pipeline._medterm4ds_engine_version()
    assert v2 == "sentinel-from-test"
    # Initial value was a real string (either installed version or "unknown").
    assert isinstance(v1, str) and v1


# ----------------------------------------------------------------------
# System URL normalization: SNOMEDCT_US -> http://snomed.info/sct
# ----------------------------------------------------------------------

@pytest.mark.parametrize("mnemonic,expected_url", [
    ("SNOMEDCT_US", "http://snomed.info/sct"),
    ("RXNORM", "http://www.nlm.nih.gov/research/umls/rxnorm"),
    ("LNC", "http://loinc.org"),
    ("ICD10CM", "http://hl7.org/fhir/sid/icd-10-cm"),
    ("CPT", "http://www.ama-assn.org/go/cpt"),
])
def test_system_url_normalization(mock_medterm4ds, mnemonic, expected_url):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="X", source=mnemonic, display="x",
        matched_text="x", status="affirmed",
        span_start=0, span_end=1,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())
    cond = pipeline.extract_conditions(_observation())[0]
    assert cond["code"]["coding"][0]["system"] == expected_url


# ----------------------------------------------------------------------
# Derived Condition carries autocoding extension with engine="medterm4ds-ner"
# ----------------------------------------------------------------------

def test_derived_condition_carries_autocoding_extension(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        confidence=0.88, match_grade="certain",
        span_start=12, span_end=20,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig(mode="hybrid"))
    cond = pipeline.extract_conditions(_observation())[0]
    coding = cond["code"]["coding"][0]
    parsed = parse_autocoding_extension(coding)
    assert parsed is not None
    assert parsed["engine"] == "medterm4ds-ner"
    assert parsed["search_mode"] == "hybrid"
    assert parsed["match_grade"] == "certain"
    assert parsed["score"] == pytest.approx(0.88)


# ----------------------------------------------------------------------
# Derived Condition carries derived-from-text extension with all 5 fields
# ----------------------------------------------------------------------

def test_derived_condition_carries_derived_from_text_extension(mock_medterm4ds):
    mock_medterm4ds.extract = lambda text, **kw: [_MockConcept(
        code="73211009", source="SNOMEDCT_US", display="Diabetes",
        matched_text="diabetes", status="affirmed",
        span_start=12, span_end=20,
    )]
    pipeline = NotesPipeline(NotesPipelineConfig())
    cond = pipeline.extract_conditions(_observation())[0]
    parsed = parse_derived_from_text_extension(cond)
    assert parsed is not None
    assert parsed["source_ref"] == "Observation/obs-1"
    assert parsed["source_path"] == "note[0].text"
    assert parsed["span_start"] == 12
    assert parsed["span_end"] == 20
    assert parsed["matched_text"] == "diabetes"


def test_two_extensions_distinct_urls(mock_medterm4ds):
    """The autocoding and derived-from-text extensions have distinct URLs."""
    assert AUTOCODING_EXTENSION_URL != DERIVED_FROM_TEXT_EXTENSION_URL
