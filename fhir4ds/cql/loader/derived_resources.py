"""Map medterm4ds extraction results to the right FHIR resource type.

The NER extractor returns a ``result_type`` per concept, derived from the
resolved anchor's canonical-id prefix (medterm4ds ``docs/RESULT_TYPES.md``):

    condition | symptom | lab | vital | medication | drug_class | procedure | vaccine

Mapping every one of those onto a ``Condition`` loses that distinction: a
vaccine becomes a diagnosis, a medication becomes a problem-list item. This
module is the single source of truth for the translation, shared by
:class:`~fhir4ds.cql.loader.notes_pipeline.NotesPipeline` and mirrored (by
hand, with a pointer back here) in the website's NLP demo.

Design notes:

* ``condition`` and ``symptom`` both map to ``Condition`` — FHIR has no
  separate symptom resource, and a symptom recorded during a visit is a
  problem-list/diagnosis entry with its own code.
* ``medication`` and ``drug_class`` map to ``MedicationStatement`` ("patient is
  taking X"), not ``MedicationRequest`` ("X was ordered") — the note is a
  record of what is happening, not an order. ``drug_class`` lands on the class
  concept (e.g. statins) and is still a statement about the patient.
* ``lab`` and ``vital`` map to ``Observation``: both are measurements (a vital
  is a laboratory-class observation in FHIR terms).
* An empty/unknown ``result_type`` falls back to ``Condition``, which is what
  the pipeline emitted before this mapping existed; the concept is still
  useful and dropping it would silently lose data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

#: medterm4ds ``result_type`` -> FHIR ``resourceType``.
RESULT_TYPE_TO_RESOURCE: Dict[str, str] = {
    "condition": "Condition",
    "symptom": "Condition",
    "medication": "MedicationStatement",
    "drug_class": "MedicationStatement",
    "vaccine": "Immunization",
    "procedure": "Procedure",
    "lab": "Observation",
    "vital": "Observation",
}

#: Resource used when ``result_type`` is empty or unrecognized.
DEFAULT_RESOURCE_TYPE = "Condition"

#: Element that carries the coded concept, per resource type.
CODE_FIELD: Dict[str, str] = {
    "Condition": "code",
    "MedicationStatement": "medication",
    "Immunization": "vaccineCode",
    "Procedure": "code",
    "Observation": "code",
}

#: Element that references the patient, per resource type.
SUBJECT_FIELD: Dict[str, str] = {
    "Condition": "subject",
    "MedicationStatement": "subject",
    "Immunization": "patient",
    "Procedure": "subject",
    "Observation": "subject",
}

#: Status fields required by each resource type, for an AFFIRMED mention. The
#: pipeline only emits affirmed concepts unless the caller opts into negated /
#: uncertain / historical / family mentions, so these describe "this is part of
#: the patient's record".
STATUS_FIELDS: Dict[str, Dict[str, Any]] = {
    "MedicationStatement": {"status": "active"},
    "Immunization": {"status": "completed"},
    "Procedure": {"status": "completed"},
    "Observation": {"status": "final"},
}

#: Derived resources we emit; a resource already carrying our derived-from-text
#: marker is never re-processed (loop prevention, see notes_pipeline INV-4).
DERIVED_RESOURCE_TYPES = frozenset(CODE_FIELD)


#: ATC chapter J07 is "VACCINES". A vaccine mention resolved to an ATC group
#: (e.g. "influenza vaccine" -> J07BB) comes back with ``result_type``
#: ``drug_class``, because the type axis describes the ANCHOR, not the clinical
#: category. Filing that as a MedicationStatement would put a vaccine in the
#: medication list, so the code system gets a say here.
VACCINE_ATC_PREFIXES = ("J07",)

#: Source mnemonics that carry ATC codes.
_ATC_SOURCES = frozenset({"ATC", "ATC_"})  # pragma: no cover - documentation


def _is_vaccine_code(code: Optional[str], source: Optional[str]) -> bool:
    """True when an ATC code sits in the vaccine chapter (J07)."""
    if not code:
        return False
    if str(source or "").strip().upper() != "ATC":
        return False
    return str(code).strip().upper().startswith(VACCINE_ATC_PREFIXES)


def resource_type_for(
    result_type: Optional[str],
    code: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """Return the FHIR resource type for an extracted concept.

    ``result_type`` drives the mapping; ``code``/``source`` are consulted only
    for the vaccine case, where an ATC J07 anchor reports ``drug_class``.

    Unknown or missing values fall back to :data:`DEFAULT_RESOURCE_TYPE`.
    """
    if not result_type:
        return DEFAULT_RESOURCE_TYPE
    resource_type = RESULT_TYPE_TO_RESOURCE.get(
        str(result_type).strip().lower(), DEFAULT_RESOURCE_TYPE
    )
    if resource_type == "MedicationStatement" and _is_vaccine_code(code, source):
        return "Immunization"
    return resource_type


def code_field_for(resource_type: str) -> str:
    """Return the element name that carries the coded concept."""
    return CODE_FIELD[resource_type]


def subject_field_for(resource_type: str) -> str:
    """Return the element name that references the patient."""
    return SUBJECT_FIELD[resource_type]


def status_fields_for(resource_type: str) -> Dict[str, Any]:
    """Return the status element(s) the resource type requires."""
    return dict(STATUS_FIELDS.get(resource_type, {}))
