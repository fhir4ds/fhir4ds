"""Resource-type mapping for NER-derived resources.

The extractor reports a ``result_type`` per concept (condition / symptom /
medication / drug_class / vaccine / procedure / lab / vital). Every concept
used to become a ``Condition``, which filed vaccines as diagnoses and
medications as problems. These tests pin the mapping itself and the shape of
each derived resource, without needing medterm4ds installed (the extractor is
mocked, as in ``test_notes_pipeline.py``).
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

import pytest

from fhir4ds.cql.loader.derived_from_text_extension import (
    DERIVED_FROM_TEXT_EXTENSION_URL,
    build_derived_from_text_extension,
)
from fhir4ds.cql.loader.derived_resources import (
    CODE_FIELD,
    DEFAULT_RESOURCE_TYPE,
    RESULT_TYPE_TO_RESOURCE,
    STATUS_FIELDS,
    SUBJECT_FIELD,
    code_field_for,
    resource_type_for,
    status_fields_for,
    subject_field_for,
)
from fhir4ds.cql.loader.notes_pipeline import NotesPipeline, NotesPipelineConfig


@dataclass
class _Concept:
    code: str
    source: str
    display: str
    matched_text: str
    status: str = "affirmed"
    confidence: float = 0.95
    match_grade: str = "certain"
    result_type: str = "condition"
    span_start: int = 10
    span_end: int = 20


@pytest.fixture
def fake_medterm4ds(monkeypatch):
    fake = types.ModuleType("medterm4ds")
    fake.__index_version__ = "test-index"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "medterm4ds", fake)
    return fake


def _source_resource() -> dict:
    return {
        "resourceType": "ClinicalImpression",
        "id": "ci-1",
        "subject": {"reference": "Patient/pat-1"},
        "summary": "note text",
    }


def _derive(fake_module, **concept_overrides) -> dict:
    """Run the pipeline over a note whose single concept has these overrides."""
    fake_module.extract = lambda text, **kw: [
        _Concept(
            code=concept_overrides.pop("code", "123456"),
            source=concept_overrides.pop("source", "SNOMEDCT_US"),
            display=concept_overrides.pop("display", "Something"),
            matched_text=concept_overrides.pop("matched_text", "something"),
            **concept_overrides,
        )
    ]
    pipeline = NotesPipeline(NotesPipelineConfig())
    derived = pipeline.extract_resources(_source_resource())
    assert len(derived) == 1, f"expected exactly one derived resource, got {derived!r}"
    return derived[0]


class TestResultTypeMapping:
    @pytest.mark.parametrize(
        ("result_type", "expected"),
        [
            ("condition", "Condition"),
            ("symptom", "Condition"),
            ("medication", "MedicationStatement"),
            ("drug_class", "MedicationStatement"),
            ("vaccine", "Immunization"),
            ("procedure", "Procedure"),
            ("lab", "Observation"),
            ("vital", "Observation"),
        ],
    )
    def test_known_result_types_map_to_their_resource(self, result_type, expected):
        assert resource_type_for(result_type) == expected

    @pytest.mark.parametrize("unknown", ["", None, "not-a-real-type"])
    def test_unknown_result_type_falls_back_to_condition(self, unknown):
        assert resource_type_for(unknown) == DEFAULT_RESOURCE_TYPE == "Condition"

    def test_mapping_is_case_insensitive(self):
        assert resource_type_for("  VACCINE ") == "Immunization"

    @pytest.mark.parametrize(
        ("result_type", "code", "source", "expected"),
        [
            # Live $extract output: "influenza vaccine" resolves to ATC J07BB
            # and reports drug_class, not vaccine. ATC J07 is the VACCINES
            # chapter, so the code system overrides to Immunization.
            ("drug_class", "J07BB", "ATC", "Immunization"),
            ("medication", "J07AX", "ATC", "Immunization"),
            # other ATC chapters stay medications
            ("drug_class", "C10AA", "ATC", "MedicationStatement"),
            # a J07-looking code from a non-ATC source proves nothing
            ("drug_class", "J07BB", "RXNORM", "MedicationStatement"),
            # vaccines that arrive already typed stay Immunizations
            ("vaccine", "140", "CVX", "Immunization"),
        ],
    )
    def test_atc_vaccine_chapter_maps_to_immunization(
        self, result_type, code, source, expected
    ):
        assert resource_type_for(result_type, code, source) == expected

    def test_every_mapped_type_has_a_code_field_and_subject_field(self):
        for resource_type in set(RESULT_TYPE_TO_RESOURCE.values()):
            assert resource_type in CODE_FIELD
            assert resource_type in SUBJECT_FIELD

    def test_immunization_uses_patient_not_subject(self):
        assert subject_field_for("Immunization") == "patient"
        assert subject_field_for("Condition") == "subject"

    def test_non_condition_types_require_a_status(self):
        for resource_type in ("MedicationStatement", "Immunization", "Procedure", "Observation"):
            assert status_fields_for(resource_type), f"{resource_type} needs a status"
        assert status_fields_for("Condition") == {}  # clinicalStatus is set separately


class TestDerivedResourceShape:
    def test_condition_keeps_clinical_and_verification_status(self, fake_medterm4ds):
        derived = _derive(fake_medterm4ds, result_type="condition")
        assert derived["resourceType"] == "Condition"
        assert "code" in derived
        assert derived["clinicalStatus"]["coding"][0]["code"] == "active"
        assert derived["verificationStatus"]["coding"][0]["code"] == "unconfirmed"

    def test_symptom_is_a_condition(self, fake_medterm4ds):
        assert _derive(fake_medterm4ds, result_type="symptom")["resourceType"] == "Condition"

    @pytest.mark.parametrize("result_type", ["medication", "drug_class"])
    def test_medications_become_medication_statements(self, fake_medterm4ds, result_type):
        derived = _derive(
            fake_medterm4ds,
            result_type=result_type,
            source="RXNORM",
            display="Metformin",
        )
        assert derived["resourceType"] == "MedicationStatement"
        # the coded concept must live on `medication`, not `code`
        assert derived["medication"]["coding"][0]["code"] == "123456"
        assert "code" not in derived
        assert derived["status"] == "active"
        assert derived["subject"]["reference"] == "Patient/pat-1"

    def test_vaccines_become_immunizations(self, fake_medterm4ds):
        derived = _derive(
            fake_medterm4ds,
            result_type="vaccine",
            source="CVX",
            display="Influenza vaccine",
        )
        assert derived["resourceType"] == "Immunization"
        assert derived["vaccineCode"]["coding"][0]["code"] == "123456"
        assert derived["status"] == "completed"
        # Immunization references the patient through `patient`, not `subject`
        assert derived["patient"]["reference"] == "Patient/pat-1"
        assert "subject" not in derived

    def test_procedures_become_procedures(self, fake_medterm4ds):
        derived = _derive(fake_medterm4ds, result_type="procedure", display="Appendectomy")
        assert derived["resourceType"] == "Procedure"
        assert derived["code"]["coding"][0]["code"] == "123456"
        assert derived["status"] == "completed"

    @pytest.mark.parametrize("result_type", ["lab", "vital"])
    def test_labs_and_vitals_become_observations(self, fake_medterm4ds, result_type):
        derived = _derive(fake_medterm4ds, result_type=result_type, source="LNC")
        assert derived["resourceType"] == "Observation"
        assert derived["code"]["coding"][0]["code"] == "123456"
        assert derived["status"] == "final"

    def test_every_derived_resource_carries_provenance(self, fake_medterm4ds):
        for result_type in RESULT_TYPE_TO_RESOURCE:
            derived = _derive(fake_medterm4ds, result_type=result_type)
            urls = [e.get("url") for e in derived.get("extension") or []]
            assert DERIVED_FROM_TEXT_EXTENSION_URL in urls, result_type
            coding = derived[code_field_for(derived["resourceType"])]["coding"][0]
            autocoding = [e.get("url") for e in coding.get("extension") or []]
            assert any("autocoding" in (u or "") for u in autocoding), result_type

    def test_ids_are_deterministic_across_runs(self, fake_medterm4ds):
        first = _derive(fake_medterm4ds, result_type="vaccine")
        second = _derive(fake_medterm4ds, result_type="vaccine")
        assert first["id"] == second["id"]
        assert len(first["id"]) == 32


class TestLoopPrevention:
    def test_already_derived_resources_are_not_reprocessed(self, fake_medterm4ds):
        fake_medterm4ds.extract = lambda text, **kw: [
            _Concept(code="1", source="SNOMEDCT_US", display="x", matched_text="x")
        ]
        pipeline = NotesPipeline(NotesPipelineConfig())
        derived = _derive(fake_medterm4ds, result_type="vaccine")
        # Feed the derived Immunization back in: it carries our marker, so the
        # pipeline must refuse to derive from it (INV-4) for ANY mapped type.
        assert pipeline.extract_resources(derived) == []

    def test_source_condition_without_marker_is_skipped(self, fake_medterm4ds):
        fake_medterm4ds.extract = lambda text, **kw: [
            _Concept(code="1", source="SNOMEDCT_US", display="x", matched_text="x")
        ]
        pipeline = NotesPipeline(NotesPipelineConfig())
        assert pipeline.extract_resources({"resourceType": "Condition", "id": "c1"}) == []

    def test_extract_conditions_is_a_working_alias(self, fake_medterm4ds):
        derived = _derive(fake_medterm4ds, result_type="medication", source="RXNORM")
        fake_medterm4ds.extract = lambda text, **kw: [
            _Concept(code="123456", source="RXNORM", display="Something",
                     matched_text="something", result_type="medication")
        ]
        pipeline = NotesPipeline(NotesPipelineConfig())
        via_alias = pipeline.extract_conditions(_source_resource())
        assert via_alias and via_alias[0]["resourceType"] == "MedicationStatement"
        assert via_alias[0]["id"] == derived["id"]
