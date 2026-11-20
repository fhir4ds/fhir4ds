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

# AMUX-152 #19: FHIRPath ``&`` renders an empty operand as '' (never as
# 'null'), so the bare BP-pair projection rendered '/' for every vital
# WITHOUT a systolic/diastolic component pair — an empty or scalar
# valueQuantity vital then falsely PASSED Attr_IsPopulated (TRIM('/') is
# non-empty). The text projection is therefore guarded: a BP panel
# renders 'sys/dias' only when BOTH components carry a value; a scalar
# vital renders its valueQuantity value; everything else renders ''.
_VS_TEXT = (
    "iif(component.exists(), "
    f"iif(({_SYSTOLIC}).exists() and ({_DIASTOLIC}).exists(), "
    f"({_SYSTOLIC}).toString() & '/' & ({_DIASTOLIC}).toString(), ''), "
    "iif(value.ofType(Quantity).exists(), "
    "value.ofType(Quantity).value.toString(), "
    "iif(value.ofType(string).exists(), value.ofType(string), "
    "iif(value.ofType(boolean).exists(), "
    "value.ofType(boolean).toString(), ''))))"
)
_VS_NUMBER = (f"iif(component.exists(), {_SYSTOLIC}, "
              "value.ofType(Quantity).value)")
_VS_UNIT = ("iif(component.exists(), "
            "component.first().value.ofType(Quantity).unit, "
            "value.ofType(Quantity).unit)")

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
        {"name": "resultValue_text", "path": _VS_TEXT, "type": "string"},
        {"name": "resultValue_type",
         "path": "iif(component.exists(), 'SN', '')", "type": "string"},
        {"name": "resultValue_number", "path": _VS_NUMBER, "type": "decimal"},
        {"name": "resultValue_number2", "path": _DIASTOLIC, "type": "decimal"},
        {"name": "resultUnit_text", "path": _VS_UNIT, "type": "string"},
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
         # AMUX-152 #26: spelled 'performedDatetime' (lowercase t) ON
         # PURPOSE — the PIQI Handbook v1.1 and the IG PCDM both use
         # this exact spelling for HealthAssessment (p.13), while
         # LabResult (p.15) and VitalSign (p.20) use
         # 'performedDateTime'. No SAM binds this column today; keep the
         # guide spellings verbatim (documented, not churned).
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
# the SQLQueryRunner's prepared-statement binding exclusively. The one
# PUBLIC entry point that accepts caller-supplied fields is
# build_rubric(); it validates before interpolation (AMUX-152 #17):
# scoring_effect is allowlisted (_SCORING_EFFECTS) and quoted via
# quote_sql_literal, sequence/weight are int()-coerced with typed
# ValueErrors, and duplicate sequences are rejected (#21).
# ---------------------------------------------------------------------------
def _q(label: str) -> str:
    """Quote a view/SAM label for SQL.

    Delegates to the canonical viewdef helper so PIQI authoring and the
    rest of the codebase cannot drift on quoting behavior.
    """
    from ..viewdef.utils import quote_identifier

    return quote_identifier(label)


def _sql_literal(value: str) -> str:
    """Quote a SQL string literal (AMUX-152 #17 defense in depth).

    ``scoring_effect`` is allowlisted, but every caller-supplied string
    that reaches the rubric SQL is quoted anyway so a future vocabulary
    widening cannot reopen the injection surface.
    """
    from ..sources.base import quote_sql_literal

    return quote_sql_literal(value)


def _recognized_systems_lazy() -> "tuple[str, ...]":
    """[HB p.15] closure of recognized code-system identifier spellings."""
    from .codesystems import recognized_system_strings  # noqa: PLC0415

    return recognized_system_strings()


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
    """[SG p.14] 'a timestamp including a date and time' — AMUX-152 #25:
    date-only values FAIL (that is Attr_IsValidDate's domain; DuckDB's
    TRY_CAST alone happily accepts a bare date)."""
    ok = ("TRY_CAST(COALESCE(CAST(v." + column + " AS VARCHAR), '') "
          "AS TIMESTAMP) IS NOT NULL "
          "AND regexp_matches(COALESCE(CAST(v." + column + " AS VARCHAR), ''), "
          "'^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}')")
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


def sam_attr_is_timestamp_tz(view_label, data_class, entity, column,
                             prereq_label: str) -> str:
    """[SG p.14] Attr_IsTimestampTz — 'a timestamp including a date,
    time and time-zone'. Timestamp WITHOUT a trailing Z|±hh:mm offset
    fails (that is Attr_IsTimestamp's domain)."""
    ok = ("TRY_CAST(COALESCE(CAST(v." + column + " AS VARCHAR), '') "
          "AS TIMESTAMPTZ) IS NOT NULL "
          "AND regexp_matches(COALESCE(CAST(v." + column + " AS VARCHAR), ''), "
          "'^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}"
          "(Z|[+-][0-9]{2}:[0-9]{2})$')")
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'Attr_IsTimestampTz' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} is a timestamp with time zone' "
        f"ELSE '{entity} is not a timestamp with time zone' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_attr_temporal_direction(view_label, data_class, entity, column,
                                mnemonic: str, direction: str,
                                prereq_label: str) -> str:
    """[SG pp.13-14] Attr_IsFutureDate / Attr_IsPastDate — pure logic,
    NO terminology dependency. A value that does not parse as a date
    FAILS (invalid input is not a future/past date)."""
    cmp_op = ">" if direction == "future" else "<"
    ok = (f"TRY_CAST(COALESCE(CAST(v.{column} AS VARCHAR), '') AS DATE) "
          f"{cmp_op} CURRENT_DATE")
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'{mnemonic}' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} is a {direction} date' "
        f"ELSE '{entity} is not a {direction} date' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_obsvalue_is_qualitative(view_label, data_class, entity,
                                type_col: str,
                                prereq_label: str) -> str:
    """[SG p.21] ObservationValue_IsQualitative — hardwired CE/CWE/CD/ST
    value-type set ('coded entry' + 'structured text' types).

    Our views render value types as NM (Quantity), CE (CodeableConcept),
    ST (string/boolean) and SN (BP struct) — CE/ST are the qualitative
    arms present in the model."""
    ok = (f"COALESCE(CAST(v.{type_col} AS VARCHAR), '') "
          f"IN ('CE', 'CWE', 'CD', 'ST')")
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'ObservationValue_IsQualitative' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} is qualitative' "
        f"ELSE '{entity} is not qualitative' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_obsvalue_matches_type(view_label, data_class, entity, text_col: str,
                              type_col: str, prereq_label: str) -> str:
    """[SG p.21] ObservationValue_MatchesType — value shape consistent
    with the expressed value type (NM ⇒ numeric text, ST ⇒ non-empty
    text, CE ⇒ non-empty text; SN ⇒ numeric). A missing/unknown type
    FAILS (the guide's HasType prerequisite ghost is NOT implemented —
    Joel decision pending; Attr_IsPopulated stands in)."""
    text = f"COALESCE(CAST(v.{text_col} AS VARCHAR), '')"
    numeric = f"regexp_matches({text}, '^-?[0-9]+(\\.[0-9]+)?$')"
    nonempty = f"{text} <> ''"
    ok = (
        f"CASE COALESCE(CAST(v.{type_col} AS VARCHAR), '')\n"
        f"    WHEN 'NM' THEN {numeric}\n"
        f"    WHEN 'SN' THEN {numeric}\n"
        f"    WHEN 'ST' THEN {nonempty}\n"
        f"    WHEN 'CE' THEN {nonempty}\n"
        f"    ELSE FALSE END"
    )
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'ObservationValue_MatchesType' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} matches its value type' "
        f"ELSE '{entity} does not match its value type' END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"{_prereq_join(prereq_label)}\n"
        f"ORDER BY v.patient_id, v.element_id"
    )


def sam_concept_has_recognized_system(view_label, data_class, entity,
                                      codings_col: str,
                                      recognized: "list[str] | tuple[str, ...]",
                                      prereq_label: str) -> str:
    """[SG p.18] Concept_HasRecognizedCodeSystem — at least one coding's
    system resolves through the HB p.15 code-system registry (any
    identifier/alias/OID spelling of a registered system). The
    recognized-string closure is embedded at AUTHOR time (constant list
    from :func:`fhir4ds.piqi.codesystems.recognized_system_strings`)."""
    in_list = ", ".join(_sql_literal(s) for s in recognized)
    ok = (
        f"len(list_filter(COALESCE(v.{codings_col}, []), c -> "
        f"COALESCE(json_extract_string(c, '$.system'), '') "
        f"IN ({in_list}))) > 0"
    )
    return (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'Concept_HasRecognizedCodeSystem' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN '{entity} has a recognized code system' "
        f"ELSE '{entity} has no recognized code system' END AS detail\n"
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
    """[SG p.23] LabResult_UnitIsPlausible (placeholder content, FDD §8 Q5).

    AMUX-152 #18: plausibility is judged on the CODED arm — the concept
    FAILS when any governed coding (2345-7 -> mg/dL; 742-7 -> 10*3/uL)
    carries an implausible unit. Multi-coding concepts carrying local
    codes alongside a governed code are judged by the governed arm, not
    by the mere existence of a non-governed coding (exists-nonmatching
    let wrong units pass); un-governed test codes stay plausible.
    """
    ok = (
        "len(list_filter(COALESCE(v.test_codings, []), c ->\n"
        "     (json_extract_string(c, '$.code') = '2345-7' "
        "AND COALESCE(v.resultUnit_text, '') NOT IN ('mg/dL', 'mg/dl'))\n"
        "  OR (json_extract_string(c, '$.code') = '742-7' "
        "AND COALESCE(v.resultUnit_text, '') NOT IN ('10*3/uL'))\n"
        ")) = 0"
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
    views). One row PER PATIENT (element_id NULL — class-level SAM, the
    deterministic class-level emission; duplicate element ids surface
    deterministically in the detail, ordered).

    AMUX-152 #25: NULL identity keys are NOT duplicates (house 3VL
    doctrine — unknown identity is not equal identity): rows with any
    NULL key are excluded from the duplicate grouping, while every
    patient keeps exactly one class row.
    """
    keys = ", ".join(key_cols)
    non_null = " AND ".join(f"v.{c} IS NOT NULL" for c in key_cols)
    return (
        f"WITH elems AS (\n"
        f"  SELECT v.patient_id AS patient_id, {keys}, v.element_id\n"
        f"  FROM {_q(view_label)} v WHERE {non_null}\n"
        f"),\n"
        f"grp AS (\n"
        f"  SELECT e.patient_id AS patient_id, {keys}, "
        f"count(*) AS c, string_agg(e.element_id, ', ' "
        f"ORDER BY e.element_id) AS ids\n"
        f"  FROM elems e GROUP BY e.patient_id, {keys}\n"
        f"),\n"
        f"per_pat AS (\n"
        f"  SELECT g.patient_id AS patient_id, "
        f"SUM(CASE WHEN g.c > 1 THEN 1 ELSE 0 END) AS dup_groups, "
        f"string_agg(CASE WHEN g.c > 1 THEN g.ids END, '; ' "
        f"ORDER BY g.ids) AS dup_ids\n"
        f"  FROM grp g GROUP BY g.patient_id\n"
        f")\n"
        f"SELECT p.patient_id AS patient_id, NULL AS element_id,\n"
        f"  '{data_class}' AS data_class, '{data_class}' AS entity, "
        f"'Class_HasDuplicates' AS sam_mnemonic,\n"
        f"  CASE WHEN COALESCE(pp.dup_groups, 0) > 0 THEN 'pass' "
        f"ELSE 'fail' END AS result,\n"
        f"  CASE WHEN COALESCE(pp.dup_groups, 0) > 0 "
        f"THEN 'duplicate elements: ' || pp.dup_ids "
        f"ELSE 'no duplicate elements detected' END AS detail\n"
        f"FROM (SELECT DISTINCT patient_id FROM {_q(view_label)}) p\n"
        f"LEFT JOIN per_pat pp ON pp.patient_id = p.patient_id\n"
        f"ORDER BY p.patient_id"
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

    # [HB p.15] recognized-code-system closure — embedded at author time
    _rec = _recognized_systems_lazy()

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

    def recognized(dc, ent, col, prereq):
        iid = f"{dc}-{ent}".lower() + "-hasrecognizedcodesystem"
        sams.append(SAMSpec(
            iid, dc, ent, "Concept_HasRecognizedCodeSystem",
            sam_concept_has_recognized_system(
                _view_label(dc), dc, ent, col, _rec,
                _prereq_label(prereq)),
            prereq=prereq))
        return iid

    def regex(dc, ent, col, short, mnemonic, pattern, prereq, extra=""):
        iid = f"{dc}-{ent}".lower() + f"-{short}"
        sams.append(SAMSpec(
            iid, dc, ent, mnemonic,
            sam_attr_regex(_view_label(dc), dc, ent, col, mnemonic,
                           pattern, _prereq_label(prereq), extra),
            prereq=prereq))
        return iid

    def valid_date(dc, ent, col, prereq):
        iid = f"{dc}-{ent}".lower() + "-isvaliddate"
        sams.append(SAMSpec(
            iid, dc, ent, "Attr_IsValidDate",
            sam_attr_is_valid_date(_view_label(dc), dc, ent, col,
                                   _prereq_label(prereq)),
            prereq=prereq))
        return iid

    def date_direction(dc, ent, col, direction, prereq):
        mnemonic = ("Attr_IsFutureDate" if direction == "future"
                    else "Attr_IsPastDate")
        iid = f"{dc}-{ent}".lower() + f"-is{direction}date"
        sams.append(SAMSpec(
            iid, dc, ent, mnemonic,
            sam_attr_temporal_direction(_view_label(dc), dc, ent, col,
                                        mnemonic, direction,
                                        _prereq_label(prereq)),
            prereq=prereq))
        return iid

    def timestamp(dc, ent, col, prereq):
        iid = f"{dc}-{ent}".lower() + "-istimestamp"
        sams.append(SAMSpec(
            iid, dc, ent, "Attr_IsTimestamp",
            sam_attr_is_timestamp(_view_label(dc), dc, ent, col,
                                  _prereq_label(prereq)),
            prereq=prereq))
        return iid

    def hasduplicates(dc, key_cols):
        iid = dc.lower() + "-hasduplicates"
        sams.append(SAMSpec(
            iid, dc, dc, "Class_HasDuplicates",
            sam_class_has_duplicates(_view_label(dc), dc, key_cols)))
        return iid

    # -- Demographics (full binding) --
    for ent, col in [("birthDate", "birthDate"), ("deathDate", "deathDate")]:
        p = pop("Demographics", ent, col)
        valid_date("Demographics", ent, col, p)
        date_direction("Demographics", ent, col, "past", p)
    for ent in ("birthSex", "deceased", "ethnicity", "genderIdentity",
                "primaryLanguage", "maritalStatus", "race"):
        p = pop("Demographics", ent, f"{ent}_text")
        part("Demographics", ent, f"{ent}_codings", "Concept_HasCode",
             "code", p)
        part("Demographics", ent, f"{ent}_codings", "Concept_HasCodeSystem",
             "system", p)
        part("Demographics", ent, f"{ent}_codings", "Concept_HasDisplay",
             "display", p)
    complete("Demographics", "birthSex", "birthSex_codings",
             "demographics-birthsex-ispopulated")
    complete("Demographics", "race", "race_codings",
             "demographics-race-ispopulated")
    for ent in ("birthSex", "race", "ethnicity"):
        recognized("Demographics", ent, f"{ent}_codings",
                   f"demographics-{ent.lower()}-ispopulated")

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
    sams.append(SAMSpec(
        "labresult-resultvalue-isqualitative", "LabResult", "resultValue",
        "ObservationValue_IsQualitative",
        sam_obsvalue_is_qualitative(_view_label("LabResult"), "LabResult",
                                    "resultValue", "resultValue_type",
                                    _prereq_label(p)),
        prereq=p))
    sams.append(SAMSpec(
        "labresult-resultvalue-matchestype", "LabResult", "resultValue",
        "ObservationValue_MatchesType",
        sam_obsvalue_matches_type(_view_label("LabResult"), "LabResult",
                                  "resultValue", "resultValue_text",
                                  "resultValue_type", _prereq_label(p)),
        prereq=p))
    tp = pop("LabResult", "test", "test_text")
    part("LabResult", "test", "test_codings", "Concept_HasCode", "code", tp)
    part("LabResult", "test", "test_codings", "Concept_HasCodeSystem",
         "system", tp)
    part("LabResult", "test", "test_codings", "Concept_HasDisplay",
         "display", tp)
    complete("LabResult", "test", "test_codings", tp)
    recognized("LabResult", "test", "test_codings", tp)
    pop("LabResult", "resultUnit", "resultUnit_text")
    ip = pop("LabResult", "interpretation", "interpretation_text")
    part("LabResult", "interpretation", "interpretation_codings",
         "Concept_HasCode", "code", ip)
    part("LabResult", "interpretation", "interpretation_codings",
         "Concept_HasCodeSystem", "system", ip)
    part("LabResult", "interpretation", "interpretation_codings",
         "Concept_HasDisplay", "display", ip)
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
    timestamp("LabResult", "performedDateTime", "performedDateTime", pdt)
    sams.append(SAMSpec(
        "labresult-elementisclean", "LabResult", "LabResult",
        "Element_IsClean", sam_element_is_clean_lab(_view_label("LabResult"))))
    hasduplicates("LabResult", ["test_text", "performedDateTime"])
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
    recognized("VitalSign", "vitalSign", "vitalSign_codings", vp)
    vvp = pop("VitalSign", "resultValue", "resultValue_text")
    regex("VitalSign", "resultValue", "resultValue_text", "isnumeric",
          "Attr_IsNumeric", r"^-?[0-9]+(\.[0-9]+)?$", vvp)
    sams.append(SAMSpec(
        "vitalsign-resultvalue-isqualitative", "VitalSign", "resultValue",
        "ObservationValue_IsQualitative",
        sam_obsvalue_is_qualitative(_view_label("VitalSign"), "VitalSign",
                                    "resultValue", "resultValue_type",
                                    _prereq_label(vvp)),
        prereq=vvp))
    pop("VitalSign", "resultUnit", "resultUnit_text")
    vip = pop("VitalSign", "interpretation", "interpretation_text")
    part("VitalSign", "interpretation", "interpretation_codings",
         "Concept_HasCode", "code", vip)
    part("VitalSign", "interpretation", "interpretation_codings",
         "Concept_HasCodeSystem", "system", vip)
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
    vpdt = pop("VitalSign", "performedDateTime", "performedDateTime")
    timestamp("VitalSign", "performedDateTime", "performedDateTime", vpdt)
    hasduplicates("VitalSign", ["vitalSign_text", "performedDateTime"])

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
        part(dc, ent, codings_col, "Concept_HasCode", "code", p)
        part(dc, ent, codings_col, "Concept_HasCodeSystem", "system", p)
        part(dc, ent, codings_col, "Concept_HasDisplay", "display", p)
        complete(dc, ent, codings_col, p)
        recognized(dc, ent, codings_col, p)

    # -- Widened date/temporal/numeric/duplicates bindings --
    cop = pop("Condition", "onsetDate", "onsetDate")
    valid_date("Condition", "onsetDate", "onsetDate", cop)
    date_direction("Condition", "onsetDate", "onsetDate", "past", cop)
    crp = pop("Condition", "resolutionDate", "resolutionDate")
    valid_date("Condition", "resolutionDate", "resolutionDate", crp)
    date_direction("Condition", "resolutionDate", "resolutionDate",
                   "past", crp)
    hasduplicates("Condition", ["condition_text", "onsetDate"])
    aep = pop("Allergy", "effectiveDate", "effectiveDate")
    valid_date("Allergy", "effectiveDate", "effectiveDate", aep)
    date_direction("Allergy", "effectiveDate", "effectiveDate", "past", aep)
    hasduplicates("Allergy", ["substance_text", "effectiveDate"])
    iap = pop("Immunization", "administrationDate", "administrationDate")
    valid_date("Immunization", "administrationDate", "administrationDate",
               iap)
    date_direction("Immunization", "administrationDate",
                   "administrationDate", "past", iap)
    iep = pop("Immunization", "expirationDate", "expirationDate")
    valid_date("Immunization", "expirationDate", "expirationDate", iep)
    date_direction("Immunization", "expirationDate", "expirationDate",
                   "future", iep)
    hasduplicates("Immunization",
                  ["immunization_text", "administrationDate"])
    pop("Medication", "startDate", "startDate")
    dap = pop("Medication", "doseAmount", "doseAmount")
    regex("Medication", "doseAmount", "doseAmount", "isnumeric",
          "Attr_IsNumeric", r"^-?[0-9]+(\.[0-9]+)?$", dap)
    hasduplicates("Medication", ["medication_text", "startDate"])
    pop("Procedure", "procedureDateTime", "procedureDateTime")
    hasduplicates("Procedure", ["procedure_text", "procedureDateTime"])
    dip = pop("MedicalDevice", "implantationDate", "implantationDate")
    valid_date("MedicalDevice", "implantationDate", "implantationDate", dip)
    date_direction("MedicalDevice", "implantationDate", "implantationDate",
                   "past", dip)
    hasduplicates("MedicalDevice", ["deviceType_text", "deviceID_text"])
    hap = pop("HealthAssessment", "resultValue", "resultValue_text")
    regex("HealthAssessment", "resultValue", "resultValue_text", "isnumeric",
          "Attr_IsNumeric", r"^-?[0-9]+(\.[0-9]+)?$", hap)
    sams.append(SAMSpec(
        "healthassessment-resultvalue-isqualitative", "HealthAssessment",
        "resultValue", "ObservationValue_IsQualitative",
        sam_obsvalue_is_qualitative(_view_label("HealthAssessment"),
                                    "HealthAssessment", "resultValue",
                                    "resultValue_type", _prereq_label(hap)),
        prereq=hap))
    hpdt = pop("HealthAssessment", "performedDatetime", "performedDatetime")
    timestamp("HealthAssessment", "performedDatetime", "performedDatetime",
              hpdt)
    hasduplicates("HealthAssessment",
                  ["assessment_text", "performedDatetime"])

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


#: The authored scoring_effect vocabulary [RG p.7] — the ONLY values the
#: rubric SQL may interpolate (AMUX-152 #17: ``scoring_effect`` is a
#: PUBLIC build_rubric argument; anything outside this allowlist raises
#: a typed ValueError instead of reaching the generated SQL).
_SCORING_EFFECTS = ("scoring", "informational")


def _int_criterion_field(criterion: dict, field: str) -> int:
    """AMUX-152 #17: int()-coerce public numeric criterion fields.

    ``sequence`` reaches ``{seq} AS sequence`` and the dependency labels;
    ``weight`` reaches the projection — a SQL fragment in either slot is
    an injection, not a number.
    """
    raw = criterion[field]
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"rubric criterion {field!r} must be an integer; got {raw!r}"
        ) from None


def _prereq_chain(spec: SAMSpec, by_id: dict[str, SAMSpec]) -> list[SAMSpec]:
    """AMUX-152 #20: the FULL prerequisite chain of ``spec``, root-first
    (execution order — [HB p.21] 'prerequisites can stack').

    ``chain[0]`` is the ROOT prerequisite (the one with no prerequisite
    of its own); its result view contains every element pass/fail, so it
    can drive rubric row identity. ``chain[-1]`` is the DIRECT
    prerequisite of the assigned SAM.
    """
    chain: list[SAMSpec] = []
    seen: set[str] = set()
    cur = spec
    while cur.prereq is not None:
        if cur.prereq in seen:  # batch-4 review: a cyclic catalog must
            raise ValueError(  # fail loudly, not hang the build
                f"cyclic prerequisite chain at {cur.prereq!r}")
        seen.add(cur.prereq)
        cur = by_id[cur.prereq]
        chain.append(cur)
    chain.reverse()
    return chain


#: [RG p.5] the sequence is "assigned automatically based on the data
#: class and entity" — this is the deterministic class order (IG p.8
#: listing order), then entity, then SAM instance id.
_IG_CLASS_ORDER = ("Demographics", "Allergy", "Condition",
                   "HealthAssessment", "Immunization", "LabResult",
                   "MedicalDevice", "Medication", "Procedure", "VitalSign")


def _auto_sequence_key(criterion: dict) -> tuple:
    dc = criterion["data_class"]
    cls_idx = (_IG_CLASS_ORDER.index(dc) if dc in _IG_CLASS_ORDER
               else len(_IG_CLASS_ORDER))
    return (cls_idx, str(criterion["entity"]).lower(),
            str(criterion["sam"]).lower())


def _assign_sequences(criteria: list[dict]) -> list[dict]:
    """Auto-assign sequence numbers [RG p.5] when omitted.

    All-or-none: a mix of authored and missing sequences is ambiguous
    and rejected with a typed ValueError.
    """
    have = [c for c in criteria if "sequence" in c]
    if have and len(have) != len(criteria):
        raise ValueError(
            "rubric criteria must either ALL carry an explicit "
            "'sequence' or ALL omit it (automatic assignment mixes "
            "badly with authored sequences)")
    if not have:
        ordered = sorted(criteria, key=_auto_sequence_key)
        for i, c in enumerate(ordered, start=1):
            c["sequence"] = i
        # preserve the caller's criteria order for metadata emission;
        # the build sorts by sequence anyway
        return criteria
    return criteria


def _criterion_weight(criterion: dict, effect: str) -> int:
    """[RG p.6] informational ⇒ 0; scoring defaults to 1."""
    if "weight" not in criterion or criterion["weight"] is None:
        return 0 if effect == "informational" else 1
    weight = _int_criterion_field(criterion, "weight")
    if effect == "informational" and weight != 0:
        raise ValueError(
            "rubric criterion weight must be 0 for informational "
            f"criteria [RG p.6]; got {weight!r}")
    return weight


def _criterion_criticality(criterion: dict, effect: str) -> bool:
    """[RG p.6] criticality is 'false' for informational criteria."""
    crit = bool(criterion["criticality"])
    if effect == "informational" and crit:
        raise ValueError(
            "rubric criterion criticality must be false for "
            "informational criteria [RG p.6]")
    return crit


def build_rubric(name: str, description: str,
                 criteria: list[dict], *, mnemonic: str | None = None,
                 version: str | None = None, authority: str | None = None,
                 model: dict | None = None, source: dict | None = None,
                 creation_datetime: str | None = None,
                 modified_datetime: str | None = None,
                 ) -> tuple[dict, list[dict]]:
    """Build a rubric SQLQuery Library from criterion dicts.

    Criterion fields: sequence (optional — auto-assigned per RG p.5
    when omitted by every criterion), data_class, entity, sam (instance
    id), scoring_effect ('scoring'|'informational'), weight (optional —
    defaults 1 scoring / enforced 0 informational), criticality (false
    for informational), condition_sam (optional instance id), and the
    [RG p.5] success_name_override / failure_name_override detail-name
    overrides. The prerequisite chain is derived from the assigned SAM
    instance's own ``prereq`` edges.

    Rubric-level metadata kwargs ([RG pp.4-5]): ``mnemonic``, ``version``,
    ``authority``, ``model`` (versionMnemonic/mnemonic/version/
    extensionMnemonic), ``source`` (organizationUid/organizationName),
    ``creation_datetime``, ``modified_datetime`` — emitted on the
    Library's ``piqiRubric`` block (plus the FHIR-native ``version``).

    Returns ``(library_dict, criteria_metadata)``.
    """
    # AMUX-152 #25: public-input validation is typed ValueError (an
    # ``assert`` vanishes under ``python -O``) — and an empty criteria
    # list would generate invalid SQL (empty UNION), not a rubric.
    if not criteria:
        raise ValueError(
            "rubric criteria must contain at least one criterion "
            "(empty criteria list)")
    catalog = build_sam_catalog()
    by_id = _sam_by_id(catalog)
    related: list[dict] = []
    selects: list[str] = []
    meta: list[dict] = []
    criteria = _assign_sequences([dict(c) for c in criteria])

    # AMUX-152 #21: duplicate sequence values would collide in the UNION
    # (same ``{seq} AS sequence`` for two criteria) — reject at build time.
    seqs = [_int_criterion_field(c, "sequence") for c in criteria]
    dupes = sorted({s for s in seqs if seqs.count(s) > 1})
    if dupes:
        raise ValueError(
            f"rubric criteria have duplicate sequence values: {dupes}")

    for c in sorted(criteria, key=lambda x: _int_criterion_field(x, "sequence")):
        seq = _int_criterion_field(c, "sequence")
        sam_id = c["sam"]
        sam_id = sam_id[len("piqi-sam-"):] if sam_id.startswith("piqi-sam-") else sam_id
        if c.get("condition_sam"):
            c = {**c, "condition_sam": (
                c["condition_sam"][len("piqi-sam-"):]
                if c["condition_sam"].startswith("piqi-sam-")
                else c["condition_sam"])}
        spec = by_id[sam_id]
        # AMUX-152 #25: caller-supplied criterion fields are validated
        # with typed errors (asserts vanish under ``python -O``).
        if spec.data_class != c["data_class"]:
            raise ValueError(
                f"criterion {seq}: data_class {c['data_class']!r} does "
                f"not match assigned SAM {spec.instance_id!r} "
                f"({spec.data_class!r})")
        if spec.entity.lower() != c["entity"].lower():
            raise ValueError(
                f"criterion {seq}: entity {c['entity']!r} does not match "
                f"assigned SAM {spec.instance_id!r} ({spec.entity!r})")
        sam_label = f"sam_{seq}"
        related.append({"type": "depends-on", "label": sam_label,
                        "resource": sam_canonical(spec.instance_id)})
        cond_label = ""
        if c.get("condition_sam"):
            cond_spec = by_id[c["condition_sam"]]
            if cond_spec.data_class != spec.data_class:
                raise ValueError(
                    f"criterion {seq}: condition_sam "
                    f"{c['condition_sam']!r} is a "
                    f"{cond_spec.data_class!r} SAM; the assigned SAM's "
                    f"data class is {spec.data_class!r}")
            cond_label = f"cond_{seq}"
            related.append({"type": "depends-on", "label": cond_label,
                            "resource": sam_canonical(cond_spec.instance_id)})

        # AMUX-152 #20: materialize the FULL prerequisite chain as rubric
        # dependencies. A level-k SAM view contains a row for an element
        # only when every DEEPER level passed (the SAM bodies inner-join
        # their direct prerequisite on result = 'pass'), so a LEFT-JOIN
        # chain from the ROOT view keeps every element addressable: a
        # root failure surfaces as the ROOT SAM's FAIL [HB p.23 — prereq
        # failure = denominator +1, numerator +0, attributed to the
        # PREREQUISITE's dimension] instead of dropping the element.
        chain = _prereq_chain(spec, by_id)
        prereq_labels = []
        for k, lvl in enumerate(chain):
            lbl = f"prereq_{seq}_{k}"
            prereq_labels.append(lbl)
            related.append({"type": "depends-on", "label": lbl,
                            "resource": sam_canonical(lvl.instance_id)})

        mnem, dc, ent = spec.mnemonic, spec.data_class, spec.entity
        effect = c["scoring_effect"]
        if effect not in _SCORING_EFFECTS:
            raise ValueError(
                "rubric criterion 'scoring_effect' must be one of "
                f"{_SCORING_EFFECTS}; got {effect!r}")
        weight = _criterion_weight(c, effect)
        crit_bool = _criterion_criticality(c, effect)
        crit = "TRUE" if crit_bool else "FALSE"
        # [RG p.5] success/failure name overrides replace the
        # SAM-authored detail strings (quoted; public input).
        succ_override = c.get("success_name_override")
        fail_override = c.get("failure_name_override")
        if succ_override is not None and not isinstance(succ_override, str):
            raise ValueError(
                f"criterion {seq}: success_name_override must be a string")
        if fail_override is not None and not isinstance(fail_override, str):
            raise ValueError(
                f"criterion {seq}: failure_name_override must be a string")

        # FROM shape: the ROOT prerequisite view sees every element, so
        # it drives row identity; deeper levels LEFT JOIN in (row present
        # iff every shallower level passed). Without a chain the assigned
        # SAM view drives.
        if chain:
            frm = f"FROM {_q(prereq_labels[0])} p0\n"
            for k in range(1, len(chain)):
                frm += (f"LEFT JOIN {_q(prereq_labels[k])} p{k} ON "
                        f"p{k}.patient_id = p0.patient_id "
                        f"AND p{k}.element_id = p0.element_id "
                        f"AND p{k}.data_class = p0.data_class "
                        f"AND p{k}.entity = p0.entity\n")
            frm += (f"LEFT JOIN {_q(sam_label)} a ON "
                    f"a.patient_id = p0.patient_id "
                    f"AND a.element_id = p0.element_id "
                    f"AND a.data_class = p0.data_class "
                    f"AND a.entity = p0.entity")
            pid, eid = "p0.patient_id", "p0.element_id"
            # First failure in EXECUTION order (root → … → direct) wins
            # the attribution; the assigned SAM only speaks when the
            # whole chain passed.
            result_case = "CASE " + " ".join(
                f"WHEN p{k}.result = 'fail' THEN 'fail'"
                for k in range(len(chain)))
            detail_case = "CASE " + " ".join(
                f"WHEN p{k}.result = 'fail' THEN p{k}.detail"
                for k in range(len(chain)))
            attrib_case = "CASE " + " ".join(
                f"WHEN p{k}.result = 'fail' THEN {_sql_literal(lvl.mnemonic)}"
                for k, lvl in enumerate(chain))
            result_case += " WHEN a.result IS NOT NULL THEN a.result ELSE NULL END"
            detail_case += (" WHEN a.result IS NOT NULL THEN a.detail "
                            "ELSE NULL END")
            attrib_case += f" ELSE {_sql_literal(mnem)} END"
        else:
            frm = f"FROM {_q(sam_label)} a"
            pid, eid = "a.patient_id", "a.element_id"
            result_case = "a.result"
            detail_case = "a.detail"
            attrib_case = _sql_literal(mnem)

        cond_join = ""
        cond_where = ""
        if cond_label:
            cond_join = (f'JOIN {_q(cond_label)} c ON c.patient_id = {pid} '
                         f'AND c.element_id = {eid}')
            cond_where = "AND c.result = 'pass'"

        # [RG p.5] name overrides: replace the SAM-authored detail text
        # on the matching result arm (no override -> original detail).
        detail_proj = "detail"
        if succ_override is not None or fail_override is not None:
            succ = (_sql_literal(succ_override) if succ_override is not None
                    else "detail")
            fail = (_sql_literal(fail_override) if fail_override is not None
                    else "detail")
            detail_proj = (f"CASE WHEN t.result = 'pass' THEN {succ} "
                           f"ELSE {fail} END AS detail")
        selects.append(
            f"SELECT patient_id, element_id, "
            f"{seq} AS sequence, {_sql_literal(dc)} AS data_class, "
            f"{_sql_literal(ent)} AS entity, "
            f"result, {detail_proj}, attributed_mnemonic, "
            f"{_sql_literal(effect)} AS scoring_effect, "
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
            "criticality": crit_bool,
            "condition_sam": c.get("condition_sam") or "",
            "prereq_sam": spec.prereq or "",
            "success_name_override": succ_override or "",
            "failure_name_override": fail_override or "",
        })

    piqi_rubric = {
        "mnemonic": mnemonic or name,
        "name": name,
        "description": description,
        "version": version or "",
        "authority": authority or "",
        "model": dict(model or {}),
        "source": dict(source or {}),
        "creationDateTime": creation_datetime or "",
        "modifiedDateTime": modified_datetime or "",
    }

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
        **({"version": version} if version else {}),
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
        "piqiRubric": piqi_rubric,
    }
    return library, meta


# ---------------------------------------------------------------------------
# Parameterized SAMs (matrix batch 5)
#
# Runner parameters bind ONLY in the MAIN SQLQuery body (SOF-SQ-03
# doctrine), so parameter-taking SAM instances are NOT packaged under
# resources/sams/ (those are materialized dependency views). They are
# built on demand via :func:`build_parameterized_sam` and executed as
# the MAIN body through :func:`fhir4ds.piqi.run_parameterized_sam`,
# which binds the parameter VALUES through DuckDB prepared statements
# (never interpolation).
# ---------------------------------------------------------------------------
def _param_default_column(mnemonic: str, entity: str) -> str:
    if mnemonic == "ObservationValueType_InList":
        return f"{entity}_type"
    return f"{entity}_text"


_PARAMETER_SPECS: dict[str, dict] = {
    # mnemonic -> {param name, SQL ok-expression (uses {column} and $param)}
    "Attr_MatchesRegex": {
        "param": "pattern",
        "ok": "regexp_matches(COALESCE(CAST(v.{column} AS VARCHAR), ''), "
              "$pattern)",
        "pass_detail": "'{entity} matches the configured pattern'",
        "fail_detail": "'{entity} does not match the configured pattern'",
    },
    "Attr_InList": {
        "param": "values",
        "ok": "list_contains(string_split($values, ','), "
              "COALESCE(CAST(v.{column} AS VARCHAR), ''))",
        "pass_detail": "'{entity} is in the configured list'",
        "fail_detail": "'{entity} is not in the configured list'",
    },
    "ObservationValueType_InList": {
        "param": "valueTypes",
        "ok": "list_contains(string_split($valueTypes, ','), "
              "COALESCE(CAST(v.{column} AS VARCHAR), ''))",
        "pass_detail": "'{entity} value type is in the configured list'",
        "fail_detail": "'{entity} value type is not in the configured list'",
    },
}


def build_parameterized_sam(mnemonic: str, data_class: str, entity: str,
                            column: str | None = None) -> dict:
    """Build a PARAMETER-TAKING SAM Library [SG property tables].

    The returned Library declares its SAM parameter (e.g. ``pattern``
    for Attr_MatchesRegex) and its SQL body references it as a named
    placeholder; execute it with
    :func:`fhir4ds.piqi.run_parameterized_sam`, which binds values via
    prepared statements. Supported mnemonics:
    ``Attr_MatchesRegex`` (param ``pattern``), ``Attr_InList``
    (param ``values``, comma-separated), ``ObservationValueType_InList``
    (param ``valueTypes``, comma-separated).
    """
    try:
        spec = _PARAMETER_SPECS[mnemonic]
    except KeyError:
        raise ValueError(
            f"unsupported parameterized SAM {mnemonic!r}; supported: "
            f"{sorted(_PARAMETER_SPECS)}") from None
    if data_class not in DATA_CLASS_TO_VIEW:
        raise ValueError(
            f"unknown data class {data_class!r}; known: "
            f"{sorted(DATA_CLASS_TO_VIEW)}")
    col = column or _param_default_column(mnemonic, entity)
    ok = spec["ok"].format(column=col)
    view_label = _view_label(data_class)
    body = (
        f"SELECT v.patient_id AS patient_id, v.element_id AS element_id,\n"
        f"  '{data_class}' AS data_class, '{entity}' AS entity, "
        f"'{mnemonic}' AS sam_mnemonic,\n"
        f"  CASE WHEN {ok} THEN 'pass' ELSE 'fail' END AS result,\n"
        f"  CASE WHEN {ok} THEN {spec['pass_detail'].format(entity=entity)} "
        f"ELSE {spec['fail_detail'].format(entity=entity)} END AS detail\n"
        f"FROM {_q(view_label)} v\n"
        f"ORDER BY v.patient_id, v.element_id"
    )
    iid = f"param-{mnemonic}-{data_class}-{entity}".lower()
    pascal = "PIQI_SAM_" + "".join(
        w.capitalize() for w in iid.replace("-", "_").split("_"))
    return {
        "resourceType": "Library",
        "id": "piqi-sam-" + iid,
        "url": sam_canonical(iid),
        "name": pascal,
        "status": "active",
        "type": {"coding": [{"system": LIBRARY_TYPES_SYSTEM,
                             "code": "sql-query"}]},
        "meta": {"profile": [SQLQUERY_PROFILE]},
        "relatedArtifact": [{
            "type": "depends-on", "label": view_label,
            "resource": view_canonical(DATA_CLASS_TO_VIEW[data_class]),
        }],
        "parameter": [{
            "name": spec["param"], "use": "in", "min": 1, "max": "1",
            "type": "string",
        }],
        "content": [{
            "contentType": "application/sql;dialect=duckdb",
            "data": base64.b64encode(body.encode("utf-8")).decode("ascii"),
        }],
    }


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
    from .codesystems import registry_document  # noqa: PLC0415 — lazy

    out: dict[str, str] = {
        # [HB p.15] code-system identifier registry (FHIR4-24-backed)
        "codesystems.json": json.dumps(registry_document(), indent=2) + "\n",
    }
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
