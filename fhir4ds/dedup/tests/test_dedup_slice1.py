"""AMUX-142 slice 1 — temporal dedup normalization core tests.

Grounding: FEATURE_TEMPORAL_DEDUP.md §1.2, §2a, §2e, §5.3 (signature × TZ
property matrix), §9 (checkpoint resolution: UCUM cross-unit value keys are
v1, default TZ America/Chicago).
"""

from __future__ import annotations

import pytest

from fhir4ds.dedup import (
    Category,
    US_CORE_VITAL_LOINC,
    categorize,
    normalize_code,
    normalize_temporal,
    normalize_value,
    secondary_timestamp,
)
from fhir4ds.dedup.temporal import Signature, _format_instant


def _obs(temporal_field, value):
    resource = {"resourceType": "Observation", "status": "final",
                "code": {"coding": [{"system": "http://loinc.org",
                                     "code": "8867-4"}]}}
    resource[temporal_field] = value
    return resource


# ---------------------------------------------------------------------------
# Signature matrix: all 6 signatures × Z / offset / naive, pinned default TZ
# ---------------------------------------------------------------------------


class TestSignatureMatrix:
    def test_year(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024"))
        assert result is not None
        assert result.signature == Signature.YEAR
        assert result.local_date == "2024"
        assert result.dt_utc is None
        assert result.start_utc == "2024-01-01T06:00:00.000Z"  # Chicago = UTC-6 (Jan)
        assert result.end_utc == "2025-01-01T06:00:00.000Z"

    def test_month(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024-03"))
        assert result.signature == Signature.MONTH
        assert result.local_date == "2024-03"
        assert result.start_utc == "2024-03-01T06:00:00.000Z"
        assert result.end_utc == "2024-04-01T05:00:00.000Z"  # DST starts Mar 10

    def test_date_only(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024-03-05"))
        assert result.signature == Signature.DATE_ONLY
        assert result.local_date == "2024-03-05"
        assert result.dt_utc is None
        assert result.start_utc == "2024-03-05T06:00:00.000Z"
        assert result.end_utc == "2024-03-06T06:00:00.000Z"

    def test_dt_naive(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024-03-05T23:30:00"))
        assert result.signature == Signature.DT_NAIVE
        assert result.local_date == "2024-03-05"
        assert result.dt_utc is None  # design §2a: naive never gets an instant
        assert result.start_utc is None
        assert result.end_utc is None

    def test_dt_z(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024-07-04T12:00:00Z"))
        assert result.signature == Signature.DT_Z
        # M1: _format_instant always renders 3 fraction digits so the
        # uniform-format strings order lexicographically == chronologically.
        assert result.dt_utc == "2024-07-04T12:00:00.000Z"
        # Z instants render local_date in the configured default TZ (CDT, UTC-5)
        assert result.local_date == "2024-07-04"
        assert result.start_utc == result.dt_utc
        assert result.end_utc == result.dt_utc

    def test_dt_z_crosses_midnight_in_default_tz(self):
        # 04:30Z on Mar 6 is 22:30 on Mar 5 in Chicago (CST, UTC-6).
        result = normalize_temporal(_obs("effectiveDateTime", "2024-03-06T04:30:00Z"))
        assert result.local_date == "2024-03-05"

    def test_dt_offset(self):
        result = normalize_temporal(_obs("effectiveDateTime",
                                         "2024-03-05T23:30:00-05:00"))
        assert result.signature == Signature.DT_OFFSET
        # PARTITION key uses the AUTHORED LOCAL date (design §2a rationale)
        assert result.local_date == "2024-03-05"
        assert result.dt_utc == "2024-03-06T04:30:00.000Z"

    def test_offset_and_z_same_instant_same_partition(self):
        # The design's motivating pair: authored-local 23:30-05:00 and naive
        # 23:30 partition together (same local_date); both also match the Z
        # form rendered in the default TZ.
        a = normalize_temporal(_obs("effectiveDateTime", "2024-03-05T23:30:00-05:00"))
        b = normalize_temporal(_obs("effectiveDateTime", "2024-03-05T23:30:00"))
        c = normalize_temporal(_obs("effectiveDateTime", "2024-03-06T04:30:00Z"))
        assert a.local_date == b.local_date == c.local_date == "2024-03-05"
        assert a.dt_utc == c.dt_utc == "2024-03-06T04:30:00.000Z"

    def test_dt_offset_positive(self):
        result = normalize_temporal(_obs("effectiveDateTime",
                                         "2024-03-05T10:00:00+05:30"))
        assert result.signature == Signature.DT_OFFSET
        assert result.local_date == "2024-03-05"
        assert result.dt_utc == "2024-03-05T04:30:00.000Z"

    def test_dt_partial_time_hour_only(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024-03-05T23Z"))
        assert result is not None
        assert result.signature == Signature.DT_Z
        assert result.dt_utc == "2024-03-05T23:00:00.000Z"

    def test_dt_fractional_seconds(self):
        result = normalize_temporal(_obs("effectiveDateTime",
                                         "2024-03-05T10:00:00.123Z"))
        assert result.dt_utc == "2024-03-05T10:00:00.123Z"

    def test_custom_default_tz(self):
        result = normalize_temporal(
            _obs("effectiveDateTime", "2024-03-06T04:30:00Z"), default_tz="UTC")
        assert result.local_date == "2024-03-06"

    def test_effective_instant(self):
        result = normalize_temporal(_obs("effectiveInstant",
                                         "2024-03-05T10:00:00.500Z"))
        assert result is not None
        assert result.signature == Signature.DT_Z
        assert result.dt_utc == "2024-03-05T10:00:00.500Z"


class TestInvalidDates:
    @pytest.mark.parametrize("bad", [
        "2024-13", "2024-02-30", "2023-02-29", "2024-1-1", "24-01-01",
        "2024-03-05T25:00:00", "2024-03-05T10:60:00", "2024-03-05T10:00:61",
        "2024-03-05T10:00:00+15:00", "2024-03-05T10:00:00+14:01",
        "2024-03-05T10:00:00.1234567890123", "2024-03-05T", "not-a-date",
        "2024-03-05 10:00:00", "", None, 123,
        # M2: year 0000 has no datetime representation; must stay on the
        # None-on-malformed contract instead of raising ValueError.
        "0000", "0000-01", "0000-01-01",
    ])
    def test_invalid_yields_none(self, bad):
        assert normalize_temporal(_obs("effectiveDateTime", bad)) is None

    def test_year_zero_onset_none_not_crash(self):
        # M2 regression: birthDate-style Condition.onsetDateTime "0000"
        # previously raised ValueError from datetime(0, 1, 1).
        assert normalize_temporal({"resourceType": "Condition",
                                   "onsetDateTime": "0000"}) is None


class TestInstantFormatOrdering:
    def test_format_instant_lexicographic_equals_chronological(self):
        # M1 invariant: _format_instant emits a UNIFORM format (always 3
        # fraction digits), so lexicographic string comparison equals
        # chronological comparison across mixed fraction forms.
        from datetime import datetime, timezone
        dts = [
            datetime(2024, 3, 5, 10, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 3, 5, 10, 0, 0, 500000, tzinfo=timezone.utc),
            datetime(2024, 3, 5, 9, 59, 59, 999000, tzinfo=timezone.utc),
            datetime(2024, 3, 5, 23, 0, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 3, 5, 10, 0, 1, 0, tzinfo=timezone.utc),
        ]
        texts = [_format_instant(d) for d in dts]
        # uniform width: exactly 3 fraction digits before the Z suffix
        import re as _re
        assert all(_re.fullmatch(r".*\.\d{3}Z", t) for t in texts)
        assert sorted(texts) == [t for _, t in
                                 sorted(zip(dts, texts), key=lambda p: p[0])]

    def test_absent_all_variants_yields_none(self):
        assert normalize_temporal(_obs("status", "final")) is None

    def test_unsupported_resource_type_none(self):
        assert normalize_temporal({"resourceType": "Encounter",
                                   "period": {"start": "2024-01-01"}}) is None

    def test_non_temporal_variant_not_matched(self):
        assert normalize_temporal(_obs("performedString", "last week")) is None
        # onsetAge etc. are not mapped in v1
        assert normalize_temporal({"resourceType": "Condition",
                                   "onsetAge": {"value": 3}}) is None


class TestPeriods:
    def _period(self, start, end):
        return _obs("effectivePeriod", {"start": start, "end": end})

    def test_period_both_dt_bounds(self):
        result = normalize_temporal(self._period(
            "2024-03-05T10:00:00Z", "2024-03-05T12:00:00Z"))
        assert result is not None
        assert result.signature == Signature.DT_Z
        assert result.dt_utc is None  # periods carry bounds, not a point
        assert result.start_utc == "2024-03-05T10:00:00.000Z"
        assert result.end_utc == "2024-03-05T12:00:00.000Z"
        assert result.local_date == "2024-03-05"

    def test_period_signature_is_more_precise_bound(self):
        # Start is DATE_ONLY, end is a datetime → pair signature is DT_*.
        result = normalize_temporal(self._period(
            "2024-03-05", "2024-03-05T12:00:00Z"))
        assert result.signature == Signature.DT_Z  # DT flavor tie-break
        assert result.start_utc is None  # date-level start has no authored instant
        assert result.end_utc == "2024-03-05T12:00:00.000Z"

    def test_period_signature_date_level_when_both_date_level(self):
        result = normalize_temporal(self._period("2024-03", "2024-03-15"))
        assert result.signature == Signature.DATE_ONLY

    def test_period_open_end(self):
        result = normalize_temporal({"resourceType": "Observation",
                                     "effectivePeriod": {"start": "2024-03-05"}})
        assert result is not None
        assert result.start_utc is None  # date-level bound → no authored instant
        assert result.end_utc is None

    def test_period_missing_start_none(self):
        assert normalize_temporal({"resourceType": "Observation",
                                   "effectivePeriod": {"end": "2024-03-05"}}) is None

    def test_period_invalid_bound_none(self):
        assert normalize_temporal(self._period("2024-03-05",
                                               "2024-03-32")) is None


class TestChoiceVariantOrder:
    def test_datetime_preferred_over_period(self):
        resource = _obs("effectiveDateTime", "2024-03-05")
        resource["effectivePeriod"] = {"start": "2024-01-01"}
        assert normalize_temporal(resource).local_date == "2024-03-05"

    def test_period_used_when_datetime_absent(self):
        resource = _obs("effectivePeriod", {"start": "2024-01-01T00:00:00Z"})
        # DT_Z local_date renders in the default TZ: midnight UTC is still
        # Dec 31 evening in Chicago.
        assert normalize_temporal(resource).local_date == "2023-12-31"

    def test_procedure_variants(self):
        assert normalize_temporal({"resourceType": "Procedure",
                                   "performedDateTime": "2024-06-01"}) \
            .local_date == "2024-06-01"
        assert normalize_temporal(
            {"resourceType": "Procedure",
             "performedPeriod": {"start": "2024-06-01T08:00:00Z",
                                 "end": "2024-06-01T09:00:00Z"}}).dt_utc is None

    def test_condition_onset(self):
        assert normalize_temporal({"resourceType": "Condition",
                                   "onsetDateTime": "2024-06"}) \
            .signature == Signature.MONTH

    def test_immunization_occurrence(self):
        assert normalize_temporal({"resourceType": "Immunization",
                                   "occurrenceDateTime": "2024-06-01"}) \
            .signature == Signature.DATE_ONLY

    def test_malformed_first_arm_falls_to_next(self):
        resource = _obs("effectiveDateTime", "garbage")
        resource["effectivePeriod"] = {"start": "2024-01-01T00:00:00Z"}
        result = normalize_temporal(resource)
        assert result is not None
        assert result.start_utc == "2024-01-01T00:00:00.000Z"


class TestSecondaryTimestamp:
    def test_observation_issued(self):
        result = secondary_timestamp(_obs("issued", "2024-03-05T10:00:00Z"))
        assert result is not None
        assert result.dt_utc == "2024-03-05T10:00:00.000Z"

    def test_condition_recorded_date(self):
        result = secondary_timestamp({"resourceType": "Condition",
                                      "recordedDate": "2024-03-05"})
        assert result is not None
        assert result.signature == Signature.DATE_ONLY

    def test_absent(self):
        assert secondary_timestamp(_obs("status", "final")) is None

    def test_unsupported_type(self):
        assert secondary_timestamp({"resourceType": "Procedure"}) is None

    def test_primary_absent_secondary_still_works(self):
        resource = _obs("issued", "2024-03-05")
        assert normalize_temporal(resource) is None
        assert secondary_timestamp(resource) is not None


# ---------------------------------------------------------------------------
# Code normalization
# ---------------------------------------------------------------------------


class TestNormalizeCode:
    def _coded(self, system, code, rtype="Observation"):
        # FHIR element name is per-type: Immunization carries its vaccine
        # code on ``vaccineCode`` (FHIR R4), every other in-scope type on
        # ``code``.
        field = "vaccineCode" if rtype == "Immunization" else "code"
        return {"resourceType": rtype,
                field: {"coding": [{"system": system, "code": code}]}}

    def test_oid_loinc_to_canonical(self):
        assert normalize_code(self._coded("urn:oid:2.16.840.1.113883.6.1",
                                          "8867-4")) \
            == ("http://loinc.org", "8867-4")

    def test_oid_snomed_module_url_folding(self):
        assert normalize_code(self._coded(
            "http://snomed.info/sct/731000124108", "386661006")) \
            == ("http://snomed.info/sct", "386661006")

    def test_mnemonic_lnc(self):
        assert normalize_code(self._coded("LNC", "8867-4")) \
            == ("http://loinc.org", "8867-4")

    def test_mnemonic_rxnorm(self):
        assert normalize_code(self._coded("RXNORM", "1234")) \
            == ("http://www.nlm.nih.gov/research/umls/rxnorm", "1234")

    def test_canonical_passthrough(self):
        assert normalize_code(self._coded("http://loinc.org", "8867-4")) \
            == ("http://loinc.org", "8867-4")

    def test_first_coding_with_system_wins(self):
        resource = {"resourceType": "Observation", "code": {"coding": [
            {"code": "no-system"}, {"system": "LNC", "code": "first-with"},
            {"system": "http://snomed.info/sct", "code": "second"}]}}
        assert normalize_code(resource) == ("http://loinc.org", "first-with")

    def test_missing_code_none(self):
        assert normalize_code({"resourceType": "Observation"}) is None
        assert normalize_code({"resourceType": "Observation",
                               "code": {"text": "uncoded"}}) is None
        assert normalize_code(self._coded("http://loinc.org", "")) is None
        assert normalize_code({"resourceType": "Observation",
                               "code": {"coding": [{"code": "x"}]}}) is None

    def test_procedure_codeableconcept(self):
        assert normalize_code(self._coded("http://snomed.info/sct", "73761001",
                                          rtype="Procedure")) \
            == ("http://snomed.info/sct", "73761001")

    def test_condition_and_immunization(self):
        assert normalize_code(self._coded("urn:oid:2.16.840.1.113883.6.96",
                                          "123456", rtype="Condition")) \
            == ("http://snomed.info/sct", "123456")
        assert normalize_code(self._coded("urn:oid:2.16.840.1.113883.12.292",
                                          "08", rtype="Immunization")) \
            == ("http://hl7.org/fhir/sid/cvx", "08")

    def test_unsupported_resource_type_none(self):
        assert normalize_code(self._coded("http://loinc.org", "8867-4",
                                          rtype="Encounter")) is None


# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------


class TestNormalizeValueQuantity:
    def _qobs(self, value, code):
        return _obs("valueQuantity", {"value": value, "unit": code,
                                      "code": code,
                                      "system": "http://unitsofmeasure.org"})

    def test_cross_unit_mm_cm_same_key(self):
        a = normalize_value(self._qobs(180, "mm"))
        b = normalize_value(self._qobs(18, "cm"))
        assert a == b == "18.00|cm"

    def test_cross_unit_mg_g(self):
        assert normalize_value(self._qobs(500, "mg")) == "0.50|g"
        assert normalize_value(self._qobs(0.5, "g")) == "0.50|g"

    def test_rounding_after_conversion(self):
        # 0.125 g → 125 mg would round differently BEFORE conversion.
        assert normalize_value(self._qobs(0.125, "g")) == "0.13|g"
        assert normalize_value(self._qobs(1.005, "g")) == "1.01|g"

    def test_unit_display_fallback_to_code(self):
        resource = _obs("valueQuantity", {"value": 18, "unit": "cm"})
        assert normalize_value(resource) == "18.00|cm"

    def test_unitless_quantity(self):
        assert normalize_value(self._qobs(3, "1")) == "3.00|1"

    def test_failed_conversion_fallback(self):
        # 'xyz' is not UCUM: fall back to rounded value + raw unit lowercased.
        assert normalize_value(self._qobs(5, "XYZ")) == "5.00|xyz"
        # Temperature (offset units) takes the fallback key too.
        assert normalize_value(self._qobs(36.6, "Cel")) == "36.60|cel"

    def test_incommensurable_never_false_merges(self):
        # 5 cm and 5 g convert to DIFFERENT canonical dimensions.
        assert normalize_value(self._qobs(5, "cm")) == "5.00|cm"
        assert normalize_value(self._qobs(5, "g")) == "5.00|g"
        assert normalize_value(self._qobs(5, "cm")) != \
            normalize_value(self._qobs(5, "g"))

    def test_pressure_canonical(self):
        assert normalize_value(self._qobs(120, "mm[Hg]")) == "120.00|mm[Hg]"


class TestNormalizeValueOtherArms:
    def test_value_codeable_concept(self):
        resource = _obs("valueCodeableConcept",
                        {"coding": [{"system": "http://loinc.org",
                                     "code": "LA9634-2"}]})
        assert normalize_value(resource) == "concept:LA9634-2"

    def test_value_string_normalized(self):
        assert normalize_value(_obs("valueString", "  Absent   Proof ")) \
            == "str:absent proof"
        assert normalize_value(_obs("valueString", "Trace")) \
            == normalize_value(_obs("valueString", "  TRACE "))

    def test_value_boolean(self):
        assert normalize_value(_obs("valueBoolean", True)) == "bool:true"
        assert normalize_value(_obs("valueBoolean", False)) == "bool:false"

    def test_dar_sentinel(self):
        resource = _obs("dataAbsentReason",
                        {"coding": [{"system": "http://terminology.hl7.org/"
                                           "CodeSystem/data-absent-reason",
                                     "code": "unknown"}]})
        assert normalize_value(resource) == "DAR:unknown"

    def test_absent_value_dar_null(self):
        assert normalize_value(_obs("status", "final")) == "DAR:null"

    def test_non_observation_na(self):
        assert normalize_value({"resourceType": "Condition"}) == "n/a"
        assert normalize_value({"resourceType": "Procedure"}) == "n/a"

    def test_quantity_preferred_over_concept(self):
        resource = _obs("valueQuantity", {"value": 120, "code": "mm[Hg]"})
        resource["valueCodeableConcept"] = {"coding": [{"code": "x"}]}
        assert normalize_value(resource) == "120.00|mm[Hg]"

    def test_malformed_quantity_falls_through_to_dar(self):
        assert normalize_value(_obs("valueQuantity", {"value": None,
                                                      "code": "mg"})) \
            == "DAR:null"


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


def _obs_with_category(categories, loinc=None):
    codings = ([{"system": "http://loinc.org", "code": loinc}]
               if loinc else [{"system": "http://loinc.org", "code": "12345"}])
    return {"resourceType": "Observation",
            "category": categories,
            "code": {"coding": codings}}


def _cat(code):
    return {"coding": [{"system":
                        "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": code}]}


class TestCategorize:
    def test_vital_signs_category(self):
        assert categorize(_obs_with_category([_cat("vital-signs")])) \
            == Category.VITAL

    def test_laboratory_category(self):
        assert categorize(_obs_with_category([_cat("laboratory")])) \
            == Category.LAB

    def test_laboratory_beats_vital(self):
        # LAB checked first; a lab-categorized vital LOINC is LAB.
        assert categorize(_obs_with_category([_cat("laboratory")],
                                             loinc="8867-4")) == Category.LAB

    def test_social_history_other(self):
        assert categorize(_obs_with_category([_cat("social-history")])) \
            == Category.OTHER

    def test_imaging_other(self):
        assert categorize(_obs_with_category([_cat("imaging")])) == Category.OTHER

    def test_uncategorized_observation_other(self):
        assert categorize(_obs_with_category([])) == Category.OTHER

    def test_vital_loinc_rescues_uncategorized(self):
        assert categorize(_obs_with_category([_cat("exam")],
                                             loinc="8867-4")) == Category.VITAL
        assert categorize(_obs_with_category([],
                                             loinc="85353-1")) == Category.VITAL

    def test_non_vital_loinc_uncategorized_other(self):
        assert categorize(_obs_with_category([],
                                             loinc="21636-6")) == Category.OTHER

    def test_oid_loinc_system_recognized(self):
        resource = {"resourceType": "Observation",
                    "code": {"coding": [
                        {"system": "urn:oid:2.16.840.1.113883.6.1",
                         "code": "8480-6"}]}}
        assert categorize(resource) == Category.VITAL

    def test_oid_category_system_recognized(self):
        resource = {"resourceType": "Observation",
                    "category": [{"coding": [
                        {"system": "urn:oid:2.16.840.1.113883.4.642.1.1125",
                         "code": "laboratory"}]}],
                    "code": {"coding": [{"system": "http://loinc.org",
                                         "code": "123"}]}}
        assert categorize(resource) == Category.LAB

    def test_non_observation_other(self):
        assert categorize({"resourceType": "Condition"}) == Category.OTHER
        assert categorize({"resourceType": "Procedure"}) == Category.OTHER
        assert categorize({"resourceType": "Immunization"}) == Category.OTHER

    def test_vendored_list_contents(self):
        assert "85353-1" in US_CORE_VITAL_LOINC
        assert "8480-6" in US_CORE_VITAL_LOINC
        assert len(US_CORE_VITAL_LOINC) >= 15


# ---------------------------------------------------------------------------
# Determinism / public surface
# ---------------------------------------------------------------------------


class TestPublicSurface:
    def test_import_package_clean(self):
        import fhir4ds
        import fhir4ds.dedup
        # Release-neutral (see the matching twin): a hardcoded release string
        # went stale at the 0.0.26 bump and reddened an import test.
        assert fhir4ds.dedup.__version__ == fhir4ds.__version__

    def test_normalized_date_is_frozen(self):
        result = normalize_temporal(_obs("effectiveDateTime", "2024-03-05"))
        with pytest.raises(Exception):
            result.local_date = "2025-01-01"

    def test_repeat_calls_identical(self):
        resource = _obs("effectiveDateTime", "2024-03-05T23:30:00-05:00")
        a = normalize_temporal(resource)
        b = normalize_temporal(resource)
        assert a == b
