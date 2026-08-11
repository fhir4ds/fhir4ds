"""Unit tests for notes_text_extractor.

Reference: FDD §3 (SCOPE REDUCTION block) and Phase 4 INV-3 (missing
paths return empty list, never raise).
"""

from __future__ import annotations

import base64

from fhir4ds.cql.loader.notes_text_extractor import (
    DEFAULT_NOTE_PATHS,
    NoteText,
    extract_note_texts,
)


# ----------------------------------------------------------------------
# Plain string path
# ----------------------------------------------------------------------

def test_plain_string_path_observation_note_text():
    """Observation.note[].text yields one NoteText per note element."""
    resource = {
        "resourceType": "Observation",
        "id": "obs-1",
        "note": [
            {"text": "Patient reports chest pain."},
            {"text": "Follow up in 1 week."},
        ],
    }
    notes = extract_note_texts(resource)
    assert len(notes) == 2
    assert all(isinstance(n, NoteText) for n in notes)
    assert notes[0].path == "note[0].text"
    assert notes[0].text == "Patient reports chest pain."
    assert notes[0].source_ref == "Observation/obs-1"
    assert notes[1].path == "note[1].text"
    assert notes[1].text == "Follow up in 1 week."


def test_default_note_paths_covers_required_resource_types():
    """DEFAULT_NOTE_PATHS includes the resource types listed in the FDD."""
    expected = {
        "DocumentReference", "ClinicalImpression", "Encounter",
        "Observation", "AllergyIntolerance", "MedicationRequest",
        "DiagnosticReport", "CarePlan",
    }
    assert expected.issubset(set(DEFAULT_NOTE_PATHS.keys()))


# ----------------------------------------------------------------------
# Nested path with base64 data
# ----------------------------------------------------------------------

def test_nested_base64_data_path_document_reference():
    """DocumentReference.content[].attachment.data is base64-decoded."""
    payload = "Patient has a history of hypertension."
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    resource = {
        "resourceType": "DocumentReference",
        "id": "doc-1",
        "content": [
            {"attachment": {"data": encoded}},
            {"attachment": {"data": ""}},  # empty data is skipped
        ],
    }
    notes = extract_note_texts(resource)
    assert len(notes) == 1
    assert notes[0].path == "content[0].attachment.data"
    assert notes[0].text == payload
    assert notes[0].source_ref == "DocumentReference/doc-1"


def test_base64_invalid_payload_is_skipped_silently():
    """Bad base64 padding logs WARNING and skips the field (INV-3)."""
    resource = {
        "resourceType": "DocumentReference",
        "id": "doc-bad",
        "content": [
            {"attachment": {"data": "this-is-not!!valid!!base64!!"}},
        ],
    }
    notes = extract_note_texts(resource)
    assert notes == []


# ----------------------------------------------------------------------
# List-valued path
# ----------------------------------------------------------------------

def test_list_valued_path_encounter_reasons():
    """Encounter.reason[].valueString fans out across all list elements."""
    resource = {
        "resourceType": "Encounter",
        "id": "enc-1",
        "reason": [
            {"valueString": "Routine checkup"},
            {"valueString": "Follow-up for hypertension"},
        ],
        "hospitalization": {
            "dischargeDisposition": {"text": "Discharged home"},
        },
    }
    notes = extract_note_texts(resource)
    paths = [n.path for n in notes]
    texts = [n.text for n in notes]
    assert "reason[0].valueString" in paths
    assert "reason[1].valueString" in paths
    assert "hospitalization.dischargeDisposition.text" in paths
    assert "Routine checkup" in texts
    assert "Discharged home" in texts


def test_empty_list_yields_no_notes():
    """An empty list at a wildcard step produces zero notes."""
    resource = {
        "resourceType": "Observation",
        "id": "obs-empty",
        "note": [],
    }
    notes = extract_note_texts(resource)
    assert notes == []


# ----------------------------------------------------------------------
# Missing path returns empty list (not exception)
# ----------------------------------------------------------------------

def test_missing_path_returns_empty_list():
    """A resource missing the configured path yields an empty list."""
    resource = {
        "resourceType": "Observation",
        "id": "obs-no-note",
        # No 'note' field at all
    }
    notes = extract_note_texts(resource)
    assert notes == []


def test_missing_intermediate_key_returns_empty_list():
    """Missing intermediate dict key yields an empty list."""
    resource = {
        "resourceType": "Encounter",
        "id": "enc-no-hosp",
        # hospitalization is missing
    }
    # Default Encounter paths include hospitalization.dischargeDisposition.text;
    # missing intermediate key should yield [] for that path, but other
    # matching paths (e.g. reason[]) still contribute.
    notes = extract_note_texts(resource)
    assert notes == []  # no reason[] either


# ----------------------------------------------------------------------
# Resource type not in note_paths -> empty list
# ----------------------------------------------------------------------

def test_resource_type_not_in_note_paths_returns_empty():
    """A resource type with no configured note paths yields empty list."""
    resource = {
        "resourceType": "Patient",
        "id": "pat-1",
        "text": {"div": "Patient narrative not in note paths"},
    }
    notes = extract_note_texts(resource)
    assert notes == []


def test_custom_note_paths_override_defaults():
    """Caller-supplied note_paths override DEFAULT_NOTE_PATHS."""
    custom = {"Patient": ["text.div"]}
    resource = {
        "resourceType": "Patient",
        "id": "pat-1",
        "text": {"div": "Some narrative"},
    }
    notes = extract_note_texts(resource, note_paths=custom)
    assert len(notes) == 1
    assert notes[0].text == "Some narrative"
    assert notes[0].path == "text.div"


# ----------------------------------------------------------------------
# Source-ref provenance
# ----------------------------------------------------------------------

def test_source_ref_includes_resource_type_and_id():
    """source_ref is '{ResourceType}/{id}'."""
    resource = {
        "resourceType": "CarePlan",
        "id": "care-42",
        "note": [{"text": "Patient agrees with plan."}],
    }
    notes = extract_note_texts(resource)
    assert notes[0].source_ref == "CarePlan/care-42"


def test_source_ref_empty_when_resource_has_no_id():
    """source_ref is '' when the resource has no id field."""
    resource = {
        "resourceType": "Observation",
        "note": [{"text": "id-less note"}],
    }
    notes = extract_note_texts(resource)
    assert len(notes) == 1
    assert notes[0].source_ref == ""


def test_index_out_of_bounds_returns_empty():
    """An explicit [N] index out of bounds yields no notes (silent skip)."""
    custom = {"Observation": ["note[5].text"]}
    resource = {
        "resourceType": "Observation",
        "id": "obs-1",
        "note": [{"text": "only one"}],
    }
    notes = extract_note_texts(resource, note_paths=custom)
    assert notes == []
