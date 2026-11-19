"""Authoring layer: generates every packaged PIQI resource as JSON.

Run ``python3 -m fhir4ds.piqi.authoring`` to (re)generate
``fhir4ds/piqi/resources/{views,sams,rubrics}/``. Resources are plain
ViewDefinitions and SQLQuery Libraries — no sqlquery/viewdef core
changes (FDD invariant 3).

Representation decisions (documented in FDD §7):

* SAM result schema is uniform (FDD invariant 2):
  ``patient_id, element_id, data_class, entity, sam_mnemonic, result,
  detail`` with ``result in ('pass','fail')``; could-not-assess is row
  absence (invariant 4).
* SAM bodies carry NO parameters: runner parameters bind only in the
  MAIN SQLQuery body, never in materialized dependency views
  (SOF-SQ-03 doctrine). Patient scoping is applied by the rubric body
  and by the ``run_sam`` facade wrapper — always via bound parameters.
* Prerequisite SAMs [HB p.21, SG p.8] are ``depends-on`` edges with
  label ``prereq_<instance>``; the SAM body joins the prerequisite's
  result view on ``result = 'pass'`` so prerequisite failures surface
  only as the prerequisite's own FAIL rows.
* Codings columns (``type: "Coding"``, ``collection: true``) are only
  authored where FHIR actually carries Coding collections; concept
  attributes without a FHIR coded source keep their ``_text`` column
  only.
"""

from __future__ import annotations

import base64
import json
import typing as _t
from pathlib import Path

CANONICAL_BASE = "https://fhir4ds.org/piqi/"
PIQI_EXT = CANONICAL_BASE + "StructureDefinition/"
LIBRARY_TYPES_SYSTEM = "http://sql-on-fhir.org/ig/CodeSystem/LibraryTypesCodes"
SQLQUERY_PROFILE = "https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery"

# ---------------------------------------------------------------------------
# Data-class views (FDD §3.1 attribute-shape convention)
# ---------------------------------------------------------------------------
_RES_DIR = Path(__file__).parent / "resources"


def _concept_columns(attr: str, text_path: str, codings_path: str | None):
    cols = [{"name": f"{attr}_text", "path": text_path, "type": "string"}]
    if codings_path is not None:
        cols.append({"name": f"{attr}_codings", "path": codings_path,
                     "type": "Coding", "collection": True})
    return cols


_ID_COLS_OBS = [
    {"name": "element_id", "path": "id", "type": "id"},
    {"name": "patient_id",
     "path": "subject.reference.replace('urn:uuid:', '').split('/').last()",
     "type": "string"},
]

_VALUE_TEXT_CHAIN = (
    "iif(value.ofType(Quantity).exists(), value.ofType(Quantity).value.toString(), "
    "iif(value.ofType(CodeableConcept).exists(), value.ofType(CodeableConcept).text, "
    "iif(value.ofType(string).exists(), value.ofType(string), "
    "iif(value.ofType(boolean).exists(), value.ofType(boolean).toString(), ''))))"
)
_VALUE_TYPE_CHAIN = (
    "iif(value.ofType(Quantity).exists(), 'NM', "
    "iif(value.ofType(CodeableConcept).exists(), 'CE', "
    "iif(value.ofType(string).exists(), 'ST', "
    "iif(value.ofType(boolean).exists(), 'ST', ''))))"
)
_RESULT_STATUS = "iif(status = 'final', 'F', status)"

_SYSTOLIC = ("component.where(code.coding.code = '8480-5').first()"
             ".value.ofType(Quantity).value")
_DIASTOLIC = ("component.where(code.coding.code = '8462-4').first()"
              ".value.ofType(Quantity).value")

VIEWS: dict[str, dict] = {}

VIEWS["piqi_demographics"] = {
    "resource": "Patient",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id", "path": "id", "type": "id"},
        # toString keeps the RAW lexical text assessable by date SAMs
        # (declared "date" would TRY_CAST invalid dates to NULL).
        {"name": "birthDate", "path": "birthDate.toString()", "type": "string"},
        {"name": "deathDate",
         "path": f"extension.where(url='{PIQI_EXT}deathDate').first()"
                 ".value.ofType(string)",
         "type": "string"},
        *[_c for name in ("birthSex", "deceased", "ethnicity", "genderIdentity",
                          "primaryLanguage", "maritalStatus", "race")
          for _c in _concept_columns(
              name,
              f"extension.where(url='{PIQI_EXT}{name}').first()"
              ".value.ofType(CodeableConcept).text",
              f"extension.where(url='{PIQI_EXT}{name}').first()"
              ".value.ofType(CodeableConcept).coding")],
    ],
}

VIEWS["piqi_labresult"] = {
    "resource": "Observation",
    "where": [{"path": "category.where(coding.code = 'laboratory').exists()"}],
    "columns": [
        *_ID_COLS_OBS,
        *_concept_columns("test", "code.text", "code.coding"),
        {"name": "resultValue_text", "path": _VALUE_TEXT_CHAIN, "type": "string"},
        {"name": "resultValue_type", "path": _VALUE_TYPE_CHAIN, "type": "string"},
        {"name": "resultValue_number", "path": "value.ofType(Quantity).value",
         "type": "decimal"},
        {"name": "resultValue_number2",
         "path": "component.first().value.ofType(Quantity).value", "type": "decimal"},
        {"name": "resultValue_codings", "path": "value.ofType(CodeableConcept).coding",
         "type": "Coding", "collection": True},
        {"name": "resultUnit_text", "path": "value.ofType(Quantity).unit",
         "type": "string"},
        *_concept_columns("interpretation", "interpretation.first().text",
                          "interpretation.first().coding"),
        {"name": "referenceRange_text", "path": "referenceRange.first().text",
         "type": "string"},
        {"name": "referenceRange_low_value",
         "path": "referenceRange.first().low.value", "type": "decimal"},
        {"name": "referenceRange_high_value",
         "path": "referenceRange.first().high.value", "type": "decimal"},
        {"name": "specimenType_text", "path": "specimen.display", "type": "string"},
        {"name": "resultStatus_text", "path": _RESULT_STATUS, "type": "string"},
        {"name": "performingSite_text", "path": "performer.first().display",
         "type": "string"},
        {"name": "performedDateTime",
         "path": "effective.ofType(dateTime).toString()", "type": "string"},
    ],
}

VIEWS["piqi_vital_sign"] = {
    "resource": "Observation",
    "where": [{"path": "category.where(coding.code = 'vital-signs').exists()"}],
    "columns": [
        *_ID_COLS_OBS,
        *_concept_columns("vitalSign", "code.text", "code.coding"),
        {"name": "resultValue_text",
         "path": f"({_SYSTOLIC}.toString()) & '/' & ({_DIASTOLIC}.toString())",
         "type": "string"},
        {"name": "resultValue_type",
         "path": "iif(component.exists(), 'SN', '')", "type": "string"},
        {"name": "resultValue_number", "path": _SYSTOLIC, "type": "decimal"},
        {"name": "resultValue_number2", "path": _DIASTOLIC, "type": "decimal"},
        {"name": "resultUnit_text",
         "path": "component.first().value.ofType(Quantity).unit", "type": "string"},
        *_concept_columns("interpretation", "interpretation.first().text",
                          "interpretation.first().coding"),
        {"name": "referenceRange_text", "path": "referenceRange.first().text",
         "type": "string"},
        {"name": "referenceRange_low_value",
         "path": "referenceRange.first().low.value", "type": "decimal"},
        {"name": "referenceRange_high_value",
         "path": "referenceRange.first().high.value", "type": "decimal"},
        {"name": "resultStatus_text", "path": _RESULT_STATUS, "type": "string"},
        {"name": "performingSite_text", "path": "performer.first().display",
         "type": "string"},
        {"name": "performedDateTime",
         "path": "effective.ofType(dateTime).toString()", "type": "string"},
    ],
}

VIEWS["piqi_health_assessment"] = {
    "resource": "Observation",
    "where": [{"path": "category.where(coding.code = 'social-history').exists()"}],
    "columns": [
        *_ID_COLS_OBS,
        *_concept_columns("assessment", "code.text", "code.coding"),
        {"name": "resultValue_text", "path": _VALUE_TEXT_CHAIN, "type": "string"},
        {"name": "resultValue_type", "path": _VALUE_TYPE_CHAIN, "type": "string"},
        {"name": "resultValue_codings", "path": "value.ofType(CodeableConcept).coding",
         "type": "Coding", "collection": True},
        {"name": "resultUnit_text", "path": "value.ofType(Quantity).unit",
         "type": "string"},
        {"name": "performedDatetime",
         "path": "effective.ofType(dateTime).toString()", "type": "string"},
    ],
}

VIEWS["piqi_allergy"] = {
    "resource": "AllergyIntolerance",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id",
         "path": "patient.reference.replace('urn:uuid:', '').split('/').last()",
         "type": "string"},
        *_concept_columns("substance", "code.text", "code.coding"),
        {"name": "category_text", "path": "category.first()", "type": "code"},
        *_concept_columns("reaction",
                          "reaction.first().manifestation.first().text",
                          "reaction.first().manifestation.first().coding"),
        {"name": "effectiveDate",
         "path": "onset.ofType(dateTime).toString()", "type": "string"},
        {"name": "severity_text",
         "path": f"extension.where(url='{PIQI_EXT}severity').first()"
                 ".value.ofType(CodeableConcept).text",
         "type": "string"},
        {"name": "severity_codings",
         "path": f"extension.where(url='{PIQI_EXT}severity').first()"
                 ".value.ofType(CodeableConcept).coding",
         "type": "Coding", "collection": True},
    ],
}

VIEWS["piqi_condition"] = {
    "resource": "Condition",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id",
         "path": "subject.reference.replace('urn:uuid:', '').split('/').last()",
         "type": "string"},
        *_concept_columns("condition", "code.text", "code.coding"),
        *_concept_columns("conditionStatus", "clinicalStatus.text",
                          "clinicalStatus.coding"),
        *_concept_columns("conditionType", "category.first().text",
                          "category.first().coding"),
        {"name": "onsetDate", "path": "onset.ofType(dateTime).toString()",
         "type": "string"},
        {"name": "resolutionDate", "path": "abatement.ofType(dateTime).toString()",
         "type": "string"},
    ],
}

VIEWS["piqi_immunization"] = {
    "resource": "Immunization",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id",
         "path": "patient.reference.replace('urn:uuid:', '').split('/').last()",
         "type": "string"},
        *_concept_columns("immunization", "vaccineCode.text", "vaccineCode.coding"),
        {"name": "lotNumber", "path": "lotNumber", "type": "string"},
        {"name": "administrationDate", "path": "occurrence.ofType(dateTime).toString()",
         "type": "string"},
        {"name": "expirationDate", "path": "expirationDate.toString()",
         "type": "string"},
        {"name": "reaction_text", "path": "reaction.first().detail.display",
         "type": "string"},
    ],
}

VIEWS["piqi_medication_request"] = {
    "resource": "MedicationRequest",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id",
         "path": "subject.reference.replace('urn:uuid:', '').split('/').last()",
         "type": "string"},
        *_concept_columns("medication", "medication.ofType(CodeableConcept).text",
                          "medication.ofType(CodeableConcept).coding"),
        {"name": "startDate", "path": "authoredOn.toString()", "type": "string"},
        {"name": "doseAmount",
         "path": "dosageInstruction.first().doseAndRate.first()"
                 ".doseQuantity.value", "type": "decimal"},
        {"name": "doseAmountUnit_text",
         "path": "dosageInstruction.first().doseAndRate.first().doseQuantity.unit",
         "type": "string"},
        *_concept_columns("doseRoute", "dosageInstruction.first().route.text",
                          "dosageInstruction.first().route.coding"),
        {"name": "doseQuantity", "path": "dispenseRequest.quantity.value",
         "type": "decimal"},
        {"name": "doseQuantityUnit", "path": "dispenseRequest.quantity.unit",
         "type": "string"},
        {"name": "instructions", "path": "dosageInstruction.first().text",
         "type": "string"},
        *_concept_columns("indication", "reasonCode.first().text",
                          "reasonCode.first().coding"),
        {"name": "fillStatus_text", "path": "status", "type": "code"},
    ],
}

VIEWS["piqi_procedure"] = {
    "resource": "Procedure",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id",
         "path": "subject.reference.replace('urn:uuid:', '').split('/').last()",
         "type": "string"},
        *_concept_columns("procedure", "code.text", "code.coding"),
        {"name": "procedureDateTime", "path": "performed.ofType(dateTime).toString()",
         "type": "string"},
        *_concept_columns("procedureReason", "reasonCode.first().text",
                          "reasonCode.first().coding"),
    ],
}

VIEWS["piqi_medical_device"] = {
    "resource": "Device",
    "columns": [
        {"name": "element_id", "path": "id", "type": "id"},
        {"name": "patient_id",
         "path": "patient.reference.replace('urn:uuid:', '').split('/').last()",
         "type": "string"},
        *_concept_columns("deviceType", "type.text", "type.coding"),
        {"name": "deviceID_text",
         "path": "udiCarrier.first().deviceIdentifier.toString()",
         "type": "string"},
        {"name": "implantationDate",
         "path": f"extension.where(url='{PIQI_EXT}implantationDate').first()"
                 ".value.ofType(string)",
         "type": "string"},
        {"name": "deviceStatus_text", "path": "status", "type": "code"},
    ],
}

DATA_CLASS_TO_VIEW = {
    "Demographics": "piqi_demographics",
    "LabResult": "piqi_labresult",
    "VitalSign": "piqi_vital_sign",
    "HealthAssessment": "piqi_health_assessment",
    "Allergy": "piqi_allergy",
    "Condition": "piqi_condition",
    "Immunization": "piqi_immunization",
    "Medication": "piqi_medication_request",
    "Procedure": "piqi_procedure",
    "MedicalDevice": "piqi_medical_device",
}


def view_canonical(view_name: str) -> str:
    return CANONICAL_BASE + "ViewDefinition/" + view_name


def build_view(name: str) -> dict:
    spec = VIEWS[name]
    vd: dict = {
        "name": name,
        "status": "draft",
        "resource": spec["resource"],
        "select": [{"column": [dict(c) for c in spec["columns"]]}],
    }
    if spec.get("where"):
        vd["where"] = [dict(w) for w in spec["where"]]
    return vd


# ---------------------------------------------------------------------------
# SAM SQL builders
#
# SECURITY: the f-string SQL below interpolates ONLY author-time catalog
# constants (column names, data classes, entities, mnemonics, patterns
# from the packaged PIQI spec tables). NO caller/runtime data may ever
# reach these builders — runtime values (patient ids etc.) go through
# the SQLQueryRunner's prepared-statement binding exclusively.
# ---------------------------------------------------------------------------
def _q(label: str) -> str:
    """Quote a view/SAM label for SQL.

    Delegates to the canonical viewdef helper so PIQI authoring and the
    rest of the codebase cannot drift on quoting behavior.
    """
    from ..viewdef.utils import quote_identifier

    return quote_identifier(label)


def _populated(col: str) -> str:
    return f"COALESCE(TRIM(CAST(v.{col} AS VARCHAR)), '') <> ''"


def sam_attr_is_populated(view_label: str, data_class: str, entity: str,
                          column: str) -> str:
    ok = _populated(column)
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'Attr_IsPopulated' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} is populated' "
        f"ELSE '{entity} is not populated' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def _prereq_join(prereq_label: str) -> str:
    return (
        f"JOIN {_q(prereq_label)} p ON p.patient_id = v.patient_id "
        f"AND p.element_id = v.element_id AND p.result = 'pass'"
    )


def sam_attr_regex(view_label, data_class, entity, column, mnemonic,
                   pattern: str, prereq_label: str | None,
                   extra_condition: str = "") -> str:
    ok = f"regexp_matches(COALESCE(CAST(v.{column} AS VARCHAR), ''), '{pattern}')"
    if extra_condition:
        ok = f"({ok} AND {extra_condition})"
    join = _prereq_join(prereq_label) + "\n" if prereq_label else ""
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'{mnemonic}' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} satisfies {mnemonic}' "
        f"ELSE '{entity} does not satisfy {mnemonic}' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{join}"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_attr_is_valid_date(view_label, data_class, entity, column,
                           prereq_label: str) -> str:
    ok = (
        f"TRY_CAST(COALESCE(CAST(v.{column} AS VARCHAR), '') AS DATE) IS NOT NULL "
        f"AND regexp_matches(COALESCE(CAST(v.{column} AS VARCHAR), ''), "
        f"'^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$')"
    )
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'Attr_IsValidDate' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} is a valid date' "
        f"ELSE '{entity} is not a valid date' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_attr_is_timestamp(view_label, data_class, entity, column,
                          prereq_label: str) -> str:
    ok = ("TRY_CAST(COALESCE(CAST(v." + column + " AS VARCHAR), '') "
          "AS TIMESTAMP) IS NOT NULL")
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'Attr_IsTimestamp' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} is a valid timestamp' "
        f"ELSE '{entity} is not a valid timestamp' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def _coding_agg(codings_col: str, part: str) -> str:
    return (
        f"len(list_filter(COALESCE(v.{codings_col}, []), "
        f"c -> COALESCE(json_extract_string(c, '$.{part}'), '') <> '')) > 0"
    )


def sam_concept_part(view_label, data_class, entity, codings_col, mnemonic,
                     part: str, prereq_label: str) -> str:
    ok = _coding_agg(codings_col, part)
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'{mnemonic}' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} has at least one coding with {part}' "
        f"ELSE '{entity} has no coding with {part}' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_concept_is_complete(view_label, data_class, entity, codings_col,
                            prereq_label: str) -> str:
    ok = (
        f"len(list_filter(COALESCE(v.{codings_col}, []), c -> "
        f"COALESCE(json_extract_string(c, '$.code'), '') <> '' "
        f"AND COALESCE(json_extract_string(c, '$.system'), '') <> '' "
        f"AND COALESCE(json_extract_string(c, '$.display'), '') <> '')) > 0"
    )
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'Concept_IsComplete' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} has at least one complete coding' "
        f"ELSE '{entity} has no complete coding "
        f"(code, system and display)' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_range_complete(view_label, data_class, entity, low_col, high_col,
                       prereq_label: str) -> str:
    ok = f"v.{low_col} IS NOT NULL AND v.{high_col} IS NOT NULL"
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'RangeValue_IsComplete' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} has both numeric components' "
        f"ELSE '{entity} is missing a numeric component' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_range_valid(view_label, data_class, entity, low_col, high_col,
                    prereq_label: str) -> str:
    ok = f"v.{low_col} <= v.{high_col}"
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'RangeValue_IsValid' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} low <= high' "
        f"ELSE '{entity} low > high' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_element_is_clean_lab(view_label, prereq_label: str | None = None) -> str:
    """[SG p.23] Element_IsClean for LabResult.

    Approximation (documented): clean = the core scorable attributes are
    populated and the test concept is complete.
    """
    complete = (
        "len(list_filter(COALESCE(v.test_codings, []), c -> "
        "COALESCE(json_extract_string(c, '$.code'), '') <> '' "
        "AND COALESCE(json_extract_string(c, '$.system'), '') <> '' "
        "AND COALESCE(json_extract_string(c, '$.display'), '') <> '')) > 0"
    )
    ok = (
        f"{_populated('test_text')} AND {_populated('resultValue_text')} "
        f"AND {_populated('performedDateTime')} AND {complete}"
    )
    join = _prereq_join(prereq_label) + "\n" if prereq_label else ""
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  'LabResult' AS data_class, 'LabResult' AS entity, "
        f"'Element_IsClean' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN 'lab result element is clean' "
        f"ELSE 'lab result element is not clean "
        f"(core attributes incomplete)' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{join}"
        f"ORDER BY v.patient_id, v.element_id"
    )


# Placeholder content tables (FDD §8 Q5): curated MINIMALLY for the
# guide fixtures; real LOINC/SNOMED tables are pending content.
_UNIT_CONTENT = "(code 2345-7 -> mg/dL; code 742-7 -> 10*3/uL)"
_VALUE_CONTENT = "(code 2345-7, mg/dL -> [0, 10000])"


def sam_unit_is_plausible(view_label, prereq_label: str) -> str:
    ok = (
        "len(list_filter(COALESCE(v.test_codings, []), c ->\n"
        "     (json_extract_string(c, '$.code') = '2345-7' "
        "AND COALESCE(v.resultUnit_text, '') IN ('mg/dL', 'mg/dl'))\n"
        "  OR (json_extract_string(c, '$.code') = '742-7' "
        "AND COALESCE(v.resultUnit_text, '') IN ('10*3/uL'))\n"
        "  OR json_extract_string(c, '$.code') IS NULL\n"
        "  OR json_extract_string(c, '$.code') NOT IN ('2345-7', '742-2')"
        ")) > 0"
    )
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  'LabResult' AS data_class, 'LabResult' AS entity, "
        f"'LabResult_UnitIsPlausible' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN 'unit is plausible for the test code' "
        f"ELSE 'unit is implausible for the test code' END AS detail "
        f"-- placeholder content {_UNIT_CONTENT}\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_value_is_plausible(view_label, prereq_label: str) -> str:
    ok = (
        "NOT (\n"
        "  len(list_filter(COALESCE(v.test_codings, []), c -> "
        "json_extract_string(c, '$.code') = '2345-7')) > 0\n"
        "  AND COALESCE(v.resultUnit_text, '') IN ('mg/dL', 'mg/dl')\n"
        "  AND (v.resultValue_number IS NULL OR v.resultValue_number < 0 "
        "OR v.resultValue_number > 10000)\n"
        ")"
    )
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  'LabResult' AS data_class, 'LabResult' AS entity, "
        f"'LabResult_ValueIsPlausible' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN 'value is plausible for the test/unit' "
        f"ELSE 'value is implausible for the test/unit' END AS detail "
        f"-- placeholder content {_VALUE_CONTENT}\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_condition_sex_plausible(view_label, demo_label: str,
                                prereq_label: str | None = None) -> str:
    """[SG p.24] Condition_SexPlausible — joins the Demographics view for
    birth sex. Placeholder content: SNOMED 77386006 (pregnant) is
    implausible for birth sex 'M'."""
    ok = (
        f"NOT EXISTS (SELECT 1 FROM {_q(demo_label)} d "
        f"WHERE d.patient_id = v.patient_id AND d.birthSex_text = 'M' "
        f"AND len(list_filter(COALESCE(v.condition_codings, []), c -> "
        f"json_extract_string(c, '$.code') = '77386006')) > 0)"
    )
    join = _prereq_join(prereq_label) + "\n" if prereq_label else ""
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  'Condition' AS data_class, 'Condition' AS entity, "
        f"'Condition_SexPlausible' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN 'condition is plausible for patient birth sex' "
        f"ELSE 'condition is implausible for patient birth sex' END AS detail "
        f"-- placeholder content (77386006 vs birth sex M)\n"
        f"FROM {_q(view_label)} v\n"
        f"{join}"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_class_has_duplicates(view_label: str, data_class: str,
                             key_cols: list[str]) -> str:
    """[SG p.25] Class_HasDuplicates.

    Guide aliases: SUCCESS = "Has duplicates" — ``pass`` means duplicate
    elements were found. Identity attributes are authored per instance
    (runner parameters cannot bind inside materialized dependency
    views). One row PER PATIENT (element_id NULL — class-level SAM).
    """
    keys = ", ".join(key_cols)
    return (
        f"WITH grp AS (\n"
        f"  SELECT v.patient_id AS patient_id, {keys}, "
        f"count(*) AS c, string_agg(v.element_id, ', ' "
        f"ORDER BY v.element_id) AS ids\n"
        f"  FROM {_q(view_label)} v GROUP BY v.patient_id, {keys}\n"
        f")\n"
        f"SELECT g.patient_id AS patient_id, NULL AS element_id,\n"
        f"  '{data_class}' AS data_class, '{data_class}' AS entity, "
        f"'Class_HasDuplicates' AS sam_mnemonic,\n"
        f"  CASE WHEN SUM(CASE WHEN g.c > 1 THEN 1 ELSE 0 END) > 0 "
        f"THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN SUM(CASE WHEN g.c > 1 THEN 1 ELSE 0 END) > 0 "
        f"THEN 'duplicate elements: ' || string_agg(CASE WHEN g.c > 1 "
        f"THEN g.ids END, '; ' ORDER BY g.ids) "
        f"ELSE 'no duplicate elements detected' END AS detail\n"
        f"FROM grp g GROUP BY g.patient_id ORDER BY g.patient_id"
    )


# ---------------------------------------------------------------------------
# SAM instance catalog
# ---------------------------------------------------------------------------
class SAMSpec:
    def __init__(self, instance_id: str, data_class: str, entity: str,
                 mnemonic: str, sql: str, prereq: str | None = None,
                 extra_deps: dict[str, str] | None = None):
        self.instance_id = instance_id
        self.data_class = data_class
        self.entity = entity
        self.mnemonic = mnemonic
        self.sql = sql
        self.prereq = prereq          # instance id of the prerequisite SAM
        self.extra_deps = extra_deps or {}  # label -> view name


def _view_label(data_class: str) -> str:
    return "view_" + DATA_CLASS_TO_VIEW[data_class]


def _prereq_label(instance_id: str) -> str:
    # sql-name forbids hyphens
    return "prereq_" + instance_id.replace("-", "_")


def build_sam_catalog() -> list[SAMSpec]:
    sams: list[SAMSpec] = []

    def pop(dc, ent, col):
        iid = f"{dc}-{ent}".lower() + "-ispopulated"
        sams.append(SAMSpec(
            iid, dc, ent, "Attr_IsPopulated",
            sam_attr_is_populated(_view_label(dc), dc, ent, col)))
        return iid

    def part(dc, ent, col, mnemonic, part_name, prereq):
        # mnemonic is the full guide mnemonic (Concept_HasCode, ...);
        # the instance id uses its lowercase short form.
        iid = f"{dc}-{ent}".lower() + f"-{mnemonic.split('_', 1)[1].lower()}"
        sams.append(SAMSpec(
            iid, dc, ent, mnemonic,
            sam_concept_part(_view_label(dc), dc, ent, col, mnemonic,
                             part_name, _prereq_label(prereq)),
            prereq=prereq))
        return iid

    def complete(dc, ent, col, prereq):
        iid = f"{dc}-{ent}".lower() + "-iscomplete"
        sams.append(SAMSpec(
            iid, dc, ent, "Concept_IsComplete",
            sam_concept_is_complete(_view_label(dc), dc, ent, col,
                                    _prereq_label(prereq)),
            prereq=prereq))
        return iid

    # -- Demographics (full binding) --
    for ent, col in [("birthDate", "birthDate"), ("deathDate", "deathDate")]:
        p = pop("Demographics", ent, col)
        sams.append(SAMSpec(
            f"demographics-{ent.lower()}-isvaliddate", "Demographics", ent,
            "Attr_IsValidDate",
            sam_attr_is_valid_date(_view_label("Demographics"), "Demographics",
                                   ent, col, _prereq_label(p)),
            prereq=p))
    for ent in ("birthSex", "deceased", "ethnicity", "genderIdentity",
                "primaryLanguage", "maritalStatus", "race"):
        pop("Demographics", ent, f"{ent}_text")
    complete("Demographics", "birthSex", "birthSex_codings",
             "demographics-birthsex-ispopulated")
    complete("Demographics", "race", "race_codings",
             "demographics-race-ispopulated")

    # -- LabResult (full binding) --
    p = pop("LabResult", "resultValue", "resultValue_text")
    for short, mnemonic, pattern, extra in [
        ("isnumeric", "Attr_IsNumeric", r"^-?[0-9]+(\.[0-9]+)?$", ""),
        ("isinteger", "Attr_IsInteger", r"^-?[0-9]+$", ""),
        ("isdecimal", "Attr_IsDecimal", r"^-?[0-9]+\.[0-9]+$", ""),
        ("ispositivenumber", "Attr_IsPositiveNumber", r"^-?[0-9]+(\.[0-9]+)?$",
         "COALESCE(TRY_CAST(v.resultValue_text AS DOUBLE), -1) > 0"),
    ]:
        sams.append(SAMSpec(
            f"labresult-resultvalue-{short}", "LabResult", "resultValue",
            mnemonic,
            sam_attr_regex(_view_label("LabResult"), "LabResult", "resultValue",
                           "resultValue_text", mnemonic, pattern,
                           _prereq_label(p), extra),
            prereq=p))
    tp = pop("LabResult", "test", "test_text")
    part("LabResult", "test", "test_codings", "Concept_HasCode", "code", tp)
    part("LabResult", "test", "test_codings", "Concept_HasCodeSystem",
         "system", tp)
    part("LabResult", "test", "test_codings", "Concept_HasDisplay",
         "display", tp)
    complete("LabResult", "test", "test_codings", tp)
    pop("LabResult", "resultUnit", "resultUnit_text")
    pop("LabResult", "interpretation", "interpretation_text")
    rp = pop("LabResult", "referenceRange", "referenceRange_text")
    sams.append(SAMSpec(
        "labresult-referencerange-rangeiscomplete", "LabResult",
        "referenceRange", "RangeValue_IsComplete",
        sam_range_complete(_view_label("LabResult"), "LabResult",
                           "referenceRange", "referenceRange_low_value",
                           "referenceRange_high_value", _prereq_label(rp)),
        prereq=rp))
    sams.append(SAMSpec(
        "labresult-referencerange-rangeisvalid", "LabResult",
        "referenceRange", "RangeValue_IsValid",
        sam_range_valid(_view_label("LabResult"), "LabResult",
                        "referenceRange", "referenceRange_low_value",
                        "referenceRange_high_value",
                        _prereq_label("labresult-referencerange-rangeiscomplete")),
        prereq="labresult-referencerange-rangeiscomplete"))
    pop("LabResult", "specimenType", "specimenType_text")
    pop("LabResult", "resultStatus", "resultStatus_text")
    pdt = pop("LabResult", "performedDateTime", "performedDateTime")
    sams.append(SAMSpec(
        "labresult-performeddatetime-istimestamp", "LabResult",
        "performedDateTime", "Attr_IsTimestamp",
        sam_attr_is_timestamp(_view_label("LabResult"), "LabResult",
                              "performedDateTime", "performedDateTime",
                              _prereq_label(pdt)),
        prereq=pdt))
    sams.append(SAMSpec(
        "labresult-elementisclean", "LabResult", "LabResult",
        "Element_IsClean", sam_element_is_clean_lab(_view_label("LabResult"))))
    sams.append(SAMSpec(
        "labresult-hasduplicates", "LabResult", "LabResult",
        "Class_HasDuplicates",
        sam_class_has_duplicates(_view_label("LabResult"), "LabResult",
                                 ["test_text", "performedDateTime"])))
    clean = "labresult-elementisclean"
    sams.append(SAMSpec(
        "labresult-unitplausible", "LabResult", "LabResult",
        "LabResult_UnitIsPlausible",
        sam_unit_is_plausible(_view_label("LabResult"),
                              _prereq_label(clean)), prereq=clean))
    sams.append(SAMSpec(
        "labresult-valueplausible", "LabResult", "LabResult",
        "LabResult_ValueIsPlausible",
        sam_value_is_plausible(_view_label("LabResult"),
                               _prereq_label("labresult-unitplausible")),
        prereq="labresult-unitplausible"))

    # -- VitalSign (full binding, mirrored subset) --
    vp = pop("VitalSign", "vitalSign", "vitalSign_text")
    part("VitalSign", "vitalSign", "vitalSign_codings", "Concept_HasCode",
         "code", vp)
    part("VitalSign", "vitalSign", "vitalSign_codings", "Concept_HasDisplay",
         "display", vp)
    complete("VitalSign", "vitalSign", "vitalSign_codings", vp)
    pop("VitalSign", "resultValue", "resultValue_text")
    pop("VitalSign", "resultUnit", "resultUnit_text")
    pop("VitalSign", "interpretation", "interpretation_text")
    vrp = pop("VitalSign", "referenceRange", "referenceRange_text")
    sams.append(SAMSpec(
        "vital-sign-referencerange-rangeiscomplete", "VitalSign",
        "referenceRange", "RangeValue_IsComplete",
        sam_range_complete(_view_label("VitalSign"), "VitalSign",
                           "referenceRange", "referenceRange_low_value",
                           "referenceRange_high_value", _prereq_label(vrp)),
        prereq=vrp))
    sams.append(SAMSpec(
        "vital-sign-referencerange-rangeisvalid", "VitalSign",
        "referenceRange", "RangeValue_IsValid",
        sam_range_valid(_view_label("VitalSign"), "VitalSign",
                        "referenceRange", "referenceRange_low_value",
                        "referenceRange_high_value",
                        _prereq_label("vital-sign-referencerange-rangeiscomplete")),
        prereq="vital-sign-referencerange-rangeiscomplete"))
    pop("VitalSign", "resultStatus", "resultStatus_text")
    pop("VitalSign", "performedDateTime", "performedDateTime")
    sams.append(SAMSpec(
        "vital-sign-hasduplicates", "VitalSign", "VitalSign",
        "Class_HasDuplicates",
        sam_class_has_duplicates(_view_label("VitalSign"), "VitalSign",
                                 ["vitalSign_text", "performedDateTime"])))

    # -- Core bindings for the remaining 7 classes --
    core = [
        ("Allergy", "piqi_allergy", "substance", "substance_text",
         "substance_codings"),
        ("Condition", "piqi_condition", "condition", "condition_text",
         "condition_codings"),
        ("HealthAssessment", "piqi_health_assessment", "assessment",
         "assessment_text", "assessment_codings"),
        ("Immunization", "piqi_immunization", "immunization",
         "immunization_text", "immunization_codings"),
        ("Medication", "piqi_medication_request", "medication",
         "medication_text", "medication_codings"),
        ("Procedure", "piqi_procedure", "procedure", "procedure_text",
         "procedure_codings"),
        ("MedicalDevice", "piqi_medical_device", "deviceType",
         "deviceType_text", "deviceType_codings"),
    ]
    for dc, view, ent, text_col, codings_col in core:
        p = pop(dc, ent, text_col)
        complete(dc, ent, codings_col, p)

    # Condition sex plausibility (placeholder content, FDD §8 Q5)
    sams.append(SAMSpec(
        "condition-sexplausible", "Condition", "Condition",
        "Condition_SexPlausible",
        sam_condition_sex_plausible(_view_label("Condition"),
                                    _view_label("Demographics")),
        extra_deps={_view_label("Demographics"): "piqi_demographics"}))

    return sams


def sam_canonical(instance_id: str) -> str:
    return CANONICAL_BASE + "Library/piqi-sam-" + instance_id


def build_sam_library(spec: SAMSpec, catalog_ids: set[str]) -> dict:
    related = [{
        "type": "depends-on",
        "label": _view_label(spec.data_class),
        "resource": view_canonical(DATA_CLASS_TO_VIEW[spec.data_class]),
    }]
    if spec.prereq is not None:
        assert spec.prereq in catalog_ids, spec.prereq
        related.append({
            "type": "depends-on",
            "label": _prereq_label(spec.prereq),
            "resource": sam_canonical(spec.prereq),
        })
    for label, view_name in spec.extra_deps.items():
        related.append({
            "type": "depends-on", "label": label,
            "resource": view_canonical(view_name),
        })
    pascal = "PIQI_SAM_" + "".join(
        w.capitalize() for w in spec.instance_id.replace("-", "_").split("_"))
    return {
        "resourceType": "Library",
        "id": "piqi-sam-" + spec.instance_id,
        "url": sam_canonical(spec.instance_id),
        "name": pascal,
        "status": "active",
        "type": {"coding": [{"system": LIBRARY_TYPES_SYSTEM,
                             "code": "sql-query"}]},
        "meta": {"profile": [SQLQUERY_PROFILE]},
        "relatedArtifact": related,
        "parameter": [],  # SAM bodies are parameter-free (see module docstring)
        "content": [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode(spec.sql.encode("utf-8")).decode("ascii"),
        }],
    }


# ---------------------------------------------------------------------------
# Rubrics
# ---------------------------------------------------------------------------
def _sam_by_id(catalog: list[SAMSpec]) -> dict[str, SAMSpec]:
    return {s.instance_id: s for s in catalog}


def build_rubric(name: str, description: str,
                 criteria: list[dict]) -> tuple[dict, list[dict]]:
    """Build a rubric SQLQuery Library from criterion dicts.

    Criterion fields: sequence, data_class, entity, sam (instance id),
    scoring_effect ('scoring'|'informational'), weight, criticality,
    condition_sam (optional instance id). The prerequisite SAM is derived
    from the assigned SAM instance's own ``prereq`` edge.

    Returns ``(library_dict, criteria_metadata)``.
    """
    catalog = build_sam_catalog()
    by_id = _sam_by_id(catalog)
    related: list[dict] = []
    selects: list[str] = []
    meta: list[dict] = []

    for c in sorted(criteria, key=lambda x: x["sequence"]):
        seq = c["sequence"]
        sam_id = c["sam"]
        sam_id = sam_id[len("piqi-sam-"):] if sam_id.startswith("piqi-sam-") else sam_id
        if c.get("condition_sam"):
            c = {**c, "condition_sam": (
                c["condition_sam"][len("piqi-sam-"):]
                if c["condition_sam"].startswith("piqi-sam-")
                else c["condition_sam"])}
        spec = by_id[sam_id]
        assert spec.data_class == c["data_class"], (spec.instance_id, c)
        assert spec.entity.lower() == c["entity"].lower(), (spec.instance_id, c)
        sam_label = f"sam_{seq}"
        related.append({"type": "depends-on", "label": sam_label,
                        "resource": sam_canonical(spec.instance_id)})
        cond_label = ""
        cond_spec = None
        if c.get("condition_sam"):
            cond_spec = by_id[c["condition_sam"]]
            assert cond_spec.data_class == spec.data_class
            cond_label = f"cond_{seq}"
            related.append({"type": "depends-on", "label": cond_label,
                            "resource": sam_canonical(cond_spec.instance_id)})
        prereq_label = ""
        prereq_mnemonic = ""
        if spec.prereq is not None:
            prereq_spec = by_id[spec.prereq]
            prereq_label = f"prereq_{seq}"
            prereq_mnemonic = prereq_spec.mnemonic
            related.append({"type": "depends-on", "label": prereq_label,
                            "resource": sam_canonical(prereq_spec.instance_id)})

        mnem, dc, ent = spec.mnemonic, spec.data_class, spec.entity
        weight = int(c["weight"])
        effect = c["scoring_effect"]
        crit = "TRUE" if c["criticality"] else "FALSE"

        # FROM shape: the prerequisite view (when present) sees every
        # element, so it drives row identity; otherwise the assigned SAM.
        if prereq_label:
            frm = (f'FROM {_q(prereq_label)} p\n'
                   f'LEFT JOIN {_q(sam_label)} a ON a.patient_id = p.patient_id '
                   f'AND a.element_id = p.element_id AND a.data_class = p.data_class '
                   f'AND a.entity = p.entity')
            pid, eid = "p.patient_id", "p.element_id"
            result_case = ("CASE WHEN a.result IS NOT NULL THEN a.result "
                           "WHEN p.result = 'fail' THEN 'fail' ELSE NULL END")
            detail_case = ("CASE WHEN a.result IS NOT NULL THEN a.detail "
                           "WHEN p.result = 'fail' THEN p.detail ELSE NULL END")
            attrib_case = (f"CASE WHEN a.result IS NOT NULL THEN '{mnem}' "
                           f"WHEN p.result = 'fail' THEN '{prereq_mnemonic}' "
                           f"ELSE NULL END")
        else:
            frm = f"FROM {_q(sam_label)} a"
            pid, eid = "a.patient_id", "a.element_id"
            result_case = "a.result"
            detail_case = "a.detail"
            attrib_case = f"'{mnem}'"

        cond_join = ""
        cond_where = ""
        if cond_label:
            cond_join = (f'JOIN {_q(cond_label)} c ON c.patient_id = {pid} '
                         f'AND c.element_id = {eid}')
            cond_where = "AND c.result = 'pass'"

        selects.append(
            f"SELECT patient_id, element_id, "
            f"{seq} AS sequence, '{dc}' AS data_class, '{ent}' AS entity, "
            f"result, detail, attributed_mnemonic, '{effect}' AS scoring_effect, "
            f"{weight} AS weight, {crit} AS criticality\n"
            f"FROM (\n"
            f"  SELECT {pid} AS patient_id, {eid} AS element_id, "
            f"{result_case} AS result, {detail_case} AS detail, "
            f"{attrib_case} AS attributed_mnemonic\n"
            f"  {frm}\n  {cond_join}\n"
            f"  WHERE TRUE {cond_where}\n"
            f") t\n"
            f"WHERE t.result IS NOT NULL"
        )
        meta.append({
            "sequence": seq, "description": c.get("description", ""),
            "data_class": dc, "entity": ent, "sam": spec.instance_id,
            "sam_mnemonic": mnem, "scoring_effect": effect, "weight": weight,
            "criticality": bool(c["criticality"]),
            "condition_sam": c.get("condition_sam") or "",
            "prereq_sam": spec.prereq or "",
        })

    body = (
        "WITH items AS (\n"
        + "\nUNION ALL\n".join(selects)
        + "\n)\n"
        "SELECT patient_id, element_id, sequence, data_class, entity, "
        "attributed_mnemonic, scoring_effect, weight, criticality, result, detail\n"
        "FROM items\n"
        "WHERE ($patient_id IS NULL OR patient_id = $patient_id)\n"
        "ORDER BY patient_id, sequence, element_id"
    )
    library = {
        "resourceType": "Library",
        "id": "piqi-rubric-" + name,
        "url": CANONICAL_BASE + "Library/piqi-rubric-" + name,
        "name": "PIQI_Rubric_" + "".join(
            w.capitalize() for w in name.replace("-", "_").split("_")),
        "title": description,
        "status": "active",
        "type": {"coding": [{"system": LIBRARY_TYPES_SYSTEM,
                             "code": "sql-query"}]},
        "meta": {"profile": [SQLQUERY_PROFILE]},
        "relatedArtifact": related,
        "parameter": [{"name": "patient_id", "use": "in", "min": 0,
                       "max": "1", "type": "string"}],
        "content": [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode(body.encode("utf-8")).decode("ascii"),
        }],
    }
    return library, meta


#: The [RG p.7] sample rubric, reproduced exactly (criterion 2's entity
#: reconciled to the IG v1.1 Demographics attribute ``genderIdentity`` —
#: the IG has no ``gender`` attribute; documented in FDD §7).
SAMPLE_RUBRIC_CRITERIA = [
    {
        "sequence": 1,
        "description": "Check if patient birth date is a valid date.",
        "data_class": "Demographics", "entity": "birthDate",
        "sam": "demographics-birthdate-isvaliddate",
        "condition_sam": "demographics-birthdate-ispopulated",
        "scoring_effect": "scoring", "weight": 1, "criticality": False,
    },
    {
        "sequence": 2,
        "description": "Verify if patient gender is populated.",
        "data_class": "Demographics", "entity": "genderIdentity",
        "sam": "demographics-genderidentity-ispopulated",
        "scoring_effect": "informational", "weight": 0, "criticality": False,
    },
]


def generate_all() -> dict[str, str]:
    """Generate every packaged PIQI resource (name -> JSON text)."""
    out: dict[str, str] = {}
    for name in VIEWS:
        out[f"views/{name}.json"] = json.dumps(build_view(name), indent=2) + "\n"
    catalog = build_sam_catalog()
    ids = {s.instance_id for s in catalog}
    for spec in catalog:
        out[f"sams/piqi-sam-{spec.instance_id}.sqlquery.json"] = (
            json.dumps(build_sam_library(spec, ids), indent=2) + "\n")
    library, meta = build_rubric("sample",
                                 "Sample Evaluation Rubric [RG p.7]",
                                 SAMPLE_RUBRIC_CRITERIA)
    library["piqiCriteria"] = meta
    out["rubrics/piqi-rubric-sample.sqlquery.json"] = (
        json.dumps(library, indent=2) + "\n")
    return out


def write_resources() -> list[str]:
    written = []
    for rel, text in sorted(generate_all().items()):
        path = _RES_DIR / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(str(path))
    return written


if __name__ == "__main__":
    for p in write_resources():
        print(p)
