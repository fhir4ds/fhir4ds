#!/usr/bin/env python3
"""Generate the AMUX-142 temporal-dedup golden corpus (v1).

Deterministic (fixed seed) labeled corpus of ~150 duplicate CLUSTERS over the
four v1 resource types (Observation, Procedure, Condition, Immunization) plus
~60 labeled hard NON-duplicate cases:

duplicate axes (design §1.2/§2/§9/§10):
- cross-unit values (180 mm / 18 cm, 82 kg / 82000 g, 250 mg / 0.25 g);
- LOINC+SNOMED translation pairs (canonical code-set intersection);
- tz-variant authoring: the SAME instant authored as Z / authored-offset /
  naive local wall clock (offset derived via the default TZ, America/
  Chicago — both CST and CDT dates);
- MONTH/MONTH same-date and YEAR-subsumes-MONTH (OTHER subsumption);
- troponin serial POC/troponin LOINCs within the 5-minute window;
- height/weight/BMI within the 30-minute extended VITAL window;
- exact effective==issued cross-field merge (full datetime vs DATE_ONLY+issued);
- signature-tier survivorship (Z/offset beats naive; DT beats DATE_ONLY;
  MONTH beats YEAR; earliest-instant and richness tie-breaks).

hard negatives (each must NEVER merge):
- same code+date, different value;
- sibling LAB observations 35 minutes apart (outside the 30-min window);
- vitals 6 minutes apart (outside the 5-min window; non-extended codes);
- troponin 6 minutes apart (outside the 5-min serial window);
- different codes, same patient/instant/value (disjoint canonical code sets);
- cross-patient identical everything;
- Conditions: different local dates, disjoint months, different years.

Labels: cluster membership ground truth plus ``expectedSurvivorRid`` wherever
the survivorship intent is determinable by authoring (a strictly higher
signature tier, a strictly earlier instant at equal tier, or deliberate
richness). Uniform clusters with no distinguishing level carry null.

Generator discipline (mirrors scripts/gen_matching_golden.py): the self-check
requires precision == 1.0, recall/survivorship at 1.0, and zero predicted
pairs outside the labels; if the engine legitimately cannot separate a
scenario, the GENERATOR is adjusted, not the engine.

Every cluster scenario allocates ONE shared patient per cluster (fresh across
scenarios), so unrelated scenarios can never share a Stage-1 partition.

Usage:
    PYTHONPATH=. python3 scripts/gen_dedup_golden.py \
        [--out fhir4ds/dedup/tests/fixtures/dedup_golden_corpus.json] [--seed 1420]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.dedup.temporal import DEFAULT_TZ  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "fhir4ds/dedup/tests/fixtures/dedup_golden_corpus.json"
DEFAULT_SEED = 1420

LOINC = "http://loinc.org"
SNOMED = "http://snomed.info/sct"
SNOMED_OID = "urn:oid:2.16.840.1.113883.6.96"
CVX = "http://hl7.org/fhir/sid/cvx"
OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"

_TZ = ZoneInfo(DEFAULT_TZ)

LAB_CODES = ["2160-0", "4548-4", "2093-3", "1751-7", "2951-2", "17861-6"]
TROPONIN_CODES = ["10839-9", "89579-7", "42637-9", "10501-5", "106733-9", "106906-1"]
SNOMED_TRANSLATION = "109811008"  # pairing partner for the LOINC lab family
VITAL_CODES = ["8480-6", "8462-4", "8867-4", "8310-5", "9279-1", "59408-5"]
PROC_CODES = ["70507-7", "49013-2", "38469-3", "8677-4", "70708-7", "39157-3"]
CONDITION_CODES = ["195967001", "386761003", "155322008", "64859006",
                   "19581007", "49436004"]
CVX_CODES = ["208", "140", "141", "10", "106", "62"]


def _fmt_z(dt: datetime) -> str:
    utc = dt.astimezone(timezone.utc)
    text = utc.strftime("%Y-%m-%dT%H:%M:%S")
    if utc.microsecond:
        text += f".{utc.microsecond // 1000:03d}"
    return text + "Z"


def _tz_forms(instant_utc: datetime) -> dict[str, str]:
    """The same instant authored three ways: Z, authored offset (default-TZ
    wall clock), naive local wall clock. Naive represents the fold=0 mapping
    (the engine's Stage-2 convention for ambiguous local times)."""
    local = instant_utc.astimezone(_TZ)
    offset = local.strftime("%z")
    return {
        "z": _fmt_z(instant_utc),
        "offset": local.strftime("%Y-%m-%dT%H:%M:%S")
        + f"{offset[:3]}:{offset[3:]}",
        "naive": local.strftime("%Y-%m-%dT%H:%M:%S"),
    }


class CorpusBuilder:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.resources: list[dict] = []
        self.clusters: list[dict] = []
        self.negatives: list[dict] = []
        self._used_ids: set[str] = set()
        self._patient_n = 0

    # -- primitives ----------------------------------------------------------
    def _rid(self, base: str) -> str:
        n = 1
        while f"{base}-{n:03d}" in self._used_ids:
            n += 1
        rid = f"{base}-{n:03d}"
        self._used_ids.add(rid)
        return rid

    def _patient(self) -> str:
        self._patient_n += 1
        return f"Patient/gp{self._patient_n:03d}"

    # -- resource assembly ----------------------------------------------------
    def obs(self, rid: str, subject: str, *, effective=None, issued=None,
            category=None, codings=None, loinc=None, value=None, unit=None,
            extra=None) -> dict:
        if codings is None:
            codings = [{"system": LOINC, "code": loinc}]
        resource: dict = {
            "resourceType": "Observation",
            "id": rid,
            "status": "final",
            "code": {"coding": codings},
            "subject": {"reference": subject},
        }
        if effective is not None:
            resource["effectiveDateTime"] = effective
        if issued is not None:
            resource["issued"] = issued
        if category is not None:
            resource["category"] = [
                {"coding": [{"system": OBS_CATEGORY, "code": category}]}
            ]
        if value is not None:
            resource["valueQuantity"] = {
                "value": value, "code": unit, "unit": unit}
        if extra:
            resource.update(extra)
        self.resources.append(resource)
        return resource

    def condition(self, rid: str, subject: str, onset: str, *,
                  coding: dict) -> dict:
        resource = {
            "resourceType": "Condition",
            "id": rid,
            "subject": {"reference": subject},
            "code": {"coding": [coding]},
            "onsetDateTime": onset,
        }
        self.resources.append(resource)
        return resource

    def procedure(self, rid: str, subject: str, performed: str, *,
                  coding: dict, extra: dict | None = None) -> dict:
        resource: dict = {
            "resourceType": "Procedure",
            "id": rid,
            "status": "completed",
            "subject": {"reference": subject},
            "code": {"coding": [coding]},
            "performedDateTime": performed,
        }
        if extra:
            resource.update(extra)
        self.resources.append(resource)
        return resource

    def immunization(self, rid: str, subject: str, occurrence: str, *,
                     cvx_code: str) -> dict:
        resource = {
            "resourceType": "Immunization",
            "id": rid,
            "status": "completed",
            "vaccineCode": {"coding": [{"system": CVX, "code": cvx_code}]},
            "occurrenceDateTime": occurrence,
        }
        self.resources.append(resource)
        return resource

    def _cluster(self, members: list[str], kind: str,
                 survivor: str | None) -> None:
        self.clusters.append({
            "kind": kind,
            "members": sorted(members),
            "expectedSurvivorRid": survivor,
        })

    def _negative(self, a: str, b: str, kind: str) -> None:
        self.negatives.append({"a": a, "b": b, "kind": kind})

    # -- duplicate scenarios ----------------------------------------------------
    def vital_clusters(self) -> None:
        rng = self.rng
        # 12x cross-unit height/weight within the extended (30-min) window.
        for i in range(6):
            base = datetime(2024, 1, 8, 9, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 7, minutes=17 * i)
            off = timedelta(minutes=rng.choice([3, 8, 15, 29]))
            subject = self._patient()
            a = self.obs(self._rid("vu"), subject, effective=_fmt_z(base),
                         loinc="8302-2", value=180, unit="mm",
                         category="vital-signs",
                         extra={"note": [{"text": "measured at intake"}]})
            b = self.obs(self._rid("vu"), subject, effective=_fmt_z(base + off),
                         loinc="8302-2", value=18, unit="cm",
                         category="vital-signs")
            # equal tier, strictly earlier instant.
            self._cluster([a["id"], b["id"]], "vital_cross_unit", a["id"])
        for i in range(6):
            base = datetime(2024, 2, 12, 14, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 11)
            off = timedelta(minutes=rng.choice([5, 12, 21, 28]))
            subject = self._patient()
            a = self.obs(self._rid("vu"), subject, effective=_fmt_z(base),
                         loinc="29463-7", value=82000, unit="g",
                         category="vital-signs",
                         extra={"performer": [{"display": "nurse r"}]})
            b = self.obs(self._rid("vu"), subject, effective=_fmt_z(base + off),
                         loinc="29463-7", value=82, unit="kg",
                         category="vital-signs")
            self._cluster([a["id"], b["id"]], "vital_cross_unit", a["id"])

        # 12x tz-variant 3-way (same instant authored Z/offset/naive), winter
        # (CST, -06:00) and summer (CDT, -05:00) dates.
        slots = [(1, 16, 4), (1, 23, 5), (6, 11, 2), (6, 18, 3),
                 (2, 14, 6), (7, 9, 1), (1, 30, 7), (6, 25, 8),
                 (2, 21, 9), (7, 16, 12), (3, 6, 10), (8, 13, 22)]
        for i, (month, day, hour) in enumerate(slots):
            instant = datetime(2024, month, day, hour, 30,
                               tzinfo=timezone.utc) + timedelta(days=i)
            forms = _tz_forms(instant)
            loinc = VITAL_CODES[i % len(VITAL_CODES)]
            subject = self._patient()
            rid_a = self._rid("vt")
            a = self.obs(rid_a, subject, effective=forms["offset"],
                         loinc=loinc, value=120, unit="mmHg",
                         category="vital-signs",
                         extra={"note": [{"text": "rich record"}]})
            b = self.obs(self._rid("vt"), subject, effective=forms["z"],
                         loinc=loinc, value=120, unit="mmHg",
                         category="vital-signs")
            c = self.obs(self._rid("vt"), subject, effective=forms["naive"],
                         loinc=loinc, value=120, unit="mmHg",
                         category="vital-signs")
            # offset member: top tier, equal instant, deliberate richness.
            self._cluster([a["id"], b["id"], c["id"]], "vital_tz_variant",
                          rid_a)

        # 6x plain vitals within the 5-minute window (non-extended codes).
        for i in range(6):
            base = datetime(2024, 3, 4, 8, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 9)
            off = timedelta(minutes=rng.choice([1, 2, 3, 4, 5]))
            loinc = ["8480-6", "8462-4", "8867-4", "8310-5", "9279-1",
                     "59408-5"][i]
            subject = self._patient()
            a = self.obs(self._rid("vp"), subject, effective=_fmt_z(base),
                         loinc=loinc, value=60 + i, unit="{beats}/min",
                         category="vital-signs")
            b = self.obs(self._rid("vp"), subject, effective=_fmt_z(base + off),
                         loinc=loinc, value=60 + i, unit="{beats}/min",
                         category="vital-signs")
            self._cluster([a["id"], b["id"]], "vital_window", a["id"])

        # 4x height/weight/BMI 25-29 min apart (extended window fires).
        for i in range(4):
            base = datetime(2024, 4, 9, 10, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 13)
            off = timedelta(minutes=[25, 26, 27, 29][i])
            loinc = ["8302-2", "29463-7", "39156-5", "8302-2"][i]
            subject = self._patient()
            a = self.obs(self._rid("vx"), subject, effective=_fmt_z(base),
                         loinc=loinc, value=170 + i, unit="cm",
                         category="vital-signs")
            b = self.obs(self._rid("vx"), subject, effective=_fmt_z(base + off),
                         loinc=loinc, value=1.70 + i / 100, unit="m",
                         category="vital-signs")
            self._cluster([a["id"], b["id"]], "vital_extended_window", a["id"])

    def lab_clusters(self) -> None:
        rng = self.rng
        # 10x cross-unit LAB values (mg/g canonicalize to grams).
        for i in range(5):
            base = datetime(2024, 1, 19, 7, 30, tzinfo=timezone.utc) + \
                timedelta(days=i * 6, minutes=11 * i)
            off = timedelta(minutes=rng.choice([2, 6, 14, 23]))
            subject = self._patient()
            a = self.obs(self._rid("lu"), subject, effective=_fmt_z(base),
                         loinc=LAB_CODES[i], value=250, unit="mg",
                         category="laboratory",
                         extra={"referenceRange": [{"low": {"value": 60}}]})
            b = self.obs(self._rid("lu"), subject, effective=_fmt_z(base + off),
                         loinc=LAB_CODES[i], value=0.25, unit="g",
                         category="laboratory")
            self._cluster([a["id"], b["id"]], "lab_cross_unit", a["id"])
        for i in range(5):
            base = datetime(2024, 5, 21, 16, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 5)
            off = timedelta(minutes=rng.choice([1, 4, 9, 19]))
            subject = self._patient()
            a = self.obs(self._rid("lu"), subject, effective=_fmt_z(base),
                         loinc=LAB_CODES[i], value=1250, unit="mg",
                         category="laboratory")
            b = self.obs(self._rid("lu"), subject, effective=_fmt_z(base + off),
                         loinc=LAB_CODES[i], value=1.25, unit="g",
                         category="laboratory",
                         extra={"note": [{"text": "repeat draw"}]})
            self._cluster([a["id"], b["id"]], "lab_cross_unit", a["id"])

        # 10x LOINC + SNOMED translation pairs (code-set intersection).
        for i in range(10):
            base = datetime(2024, 2, 6, 11, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 4, minutes=3 * i)
            off = timedelta(minutes=rng.choice([3, 5, 7, 10]))
            subject = self._patient()
            pair_loinc = LAB_CODES[i % len(LAB_CODES)]
            a = self.obs(self._rid("lt"), subject, effective=_fmt_z(base),
                         codings=[{"system": LOINC, "code": pair_loinc},
                                  {"system": SNOMED,
                                   "code": SNOMED_TRANSLATION}],
                         value=140, unit="mg/dL", category="laboratory")
            snomed_only = [{"system": SNOMED, "code": SNOMED_TRANSLATION}] \
                if i % 2 == 0 else [{"system": SNOMED_OID,
                                     "code": SNOMED_TRANSLATION}]
            b = self.obs(self._rid("lt"), subject, effective=_fmt_z(base + off),
                         codings=snomed_only,
                         value=140, unit="mg/dL", category="laboratory")
            self._cluster([a["id"], b["id"]], "lab_translation_pair", a["id"])

        # 10x troponin serial within the 5-minute POC window.
        for i in range(10):
            base = datetime(2024, 3, 12, 13, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 3, minutes=2 * i)
            off = timedelta(minutes=rng.choice([1, 2, 3, 4, 5]))
            subject = self._patient()
            code = TROPONIN_CODES[i % len(TROPONIN_CODES)]
            a = self.obs(self._rid("tp"), subject, effective=_fmt_z(base),
                         loinc=code, value=0.05 + i * 0.01, unit="ng/mL",
                         category="laboratory")
            b = self.obs(self._rid("tp"), subject, effective=_fmt_z(base + off),
                         loinc=code, value=0.05 + i * 0.01, unit="ng/mL",
                         category="laboratory")
            self._cluster([a["id"], b["id"]], "lab_troponin_serial", a["id"])

        # 8x exact effective==issued cross-field (full datetime vs
        # DATE_ONLY + issued carrying the partner's authored instant).
        for i in range(8):
            instant = datetime(2024, 4, 3, 9, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 6, hours=i)
            subject = self._patient()
            code = LAB_CODES[i % len(LAB_CODES)]
            a = self.obs(self._rid("xe"), subject, effective=_fmt_z(instant),
                         loinc=code, value=6.5 + i, unit="mg/dL",
                         category="laboratory")
            b = self.obs(self._rid("xe"), subject,
                         effective=instant.astimezone(_TZ).strftime("%Y-%m-%d"),
                         issued=_fmt_z(instant),
                         loinc=code, value=6.5 + i, unit="mg/dL",
                         category="laboratory")
            # DT_Z member outranks the DATE_ONLY member.
            self._cluster([a["id"], b["id"]], "lab_effective_eq_issued",
                          a["id"])

        # 8x plain LAB duplicates within the 30-minute window.
        for i in range(8):
            base = datetime(2024, 6, 4, 12, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 5)
            off = timedelta(minutes=rng.choice([7, 11, 18, 24, 29]))
            subject = self._patient()
            code = LAB_CODES[(i + 2) % len(LAB_CODES)]
            a = self.obs(self._rid("lp"), subject, effective=_fmt_z(base),
                         loinc=code, value=200 + i, unit="mg/dL",
                         category="laboratory")
            b = self.obs(self._rid("lp"), subject, effective=_fmt_z(base + off),
                         loinc=code, value=200 + i, unit="mg/dL",
                         category="laboratory")
            self._cluster([a["id"], b["id"]], "lab_window", a["id"])

    def other_observation_clusters(self) -> None:
        # 6x uncategorized (OTHER) Observations merging on authored local
        # date: same-date merge, DT+DATE_ONLY, naive vs Z same local date.
        for i in range(2):
            day = datetime(2024, 3, 20, tzinfo=timezone.utc) + \
                timedelta(days=i * 17)
            subject = self._patient()
            a = self.obs(self._rid("oo"), subject,
                         effective=day.strftime("%Y-%m-%d"),
                         codings=[{"system": SNOMED, "code": "160245001"}],
                         value=1, unit="1")
            b = self.obs(self._rid("oo"), subject,
                         effective=day.strftime("%Y-%m-%d"),
                         codings=[{"system": SNOMED_OID,
                                   "code": "160245001"}], value=1, unit="1")
            self._cluster([a["id"], b["id"]], "other_obs_same_date", None)
        for i in range(2):
            day = datetime(2024, 5, 14, tzinfo=timezone.utc) + \
                timedelta(days=i * 21)
            subject = self._patient()
            a = self.obs(self._rid("od"), subject,
                         effective=day.strftime("%Y-%m-%dT14:30:00"),
                         codings=[{"system": SNOMED, "code": "160245001"}],
                         value=2, unit="1")
            b = self.obs(self._rid("od"), subject,
                         effective=day.strftime("%Y-%m-%d"),
                         codings=[{"system": SNOMED, "code": "160245001"}],
                         value=2, unit="1")
            # DT_NAIVE outranks DATE_ONLY.
            self._cluster([a["id"], b["id"]], "other_obs_dt_vs_date", a["id"])
        for i in range(2):
            instant = datetime(2024, 7, 2, 15, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 12)
            forms = _tz_forms(instant)
            subject = self._patient()
            a = self.obs(self._rid("oz"), subject, effective=forms["z"],
                         codings=[{"system": SNOMED, "code": "160245001"}],
                         value=3, unit="1")
            b = self.obs(self._rid("oz"), subject, effective=forms["naive"],
                         codings=[{"system": SNOMED, "code": "160245001"}],
                         value=3, unit="1")
            # Z outranks naive at survivorship.
            self._cluster([a["id"], b["id"]], "other_obs_tz_pair", a["id"])

    def procedure_clusters(self) -> None:
        # 6x tz-variant 3-way performedDateTime.
        for i in range(6):
            instant = datetime(2024, 2, 8, 20, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 23, hours=i)
            forms = _tz_forms(instant)
            subject = self._patient()
            rid_a = self._rid("pz")
            a = self.procedure(rid_a, subject, forms["offset"],
                               coding={"system": SNOMED,
                                       "code": PROC_CODES[i]},
                               extra={"bodySite": {"display": "left arm"}})
            b = self.procedure(self._rid("pz"), subject, forms["z"],
                               coding={"system": SNOMED,
                                       "code": PROC_CODES[i]})
            c = self.procedure(self._rid("pz"), subject, forms["naive"],
                               coding={"system": SNOMED,
                                       "code": PROC_CODES[i]})
            self._cluster([a["id"], b["id"], c["id"]],
                          "procedure_tz_variant", rid_a)
        # 4x SNOMED system-spelling pairs (OID vs canonical URL).
        for i in range(4):
            instant = datetime(2024, 4, 17, 18, 30, tzinfo=timezone.utc) + \
                timedelta(days=i * 15)
            forms = _tz_forms(instant)
            subject = self._patient()
            code = PROC_CODES[i + 2]
            a = self.procedure(self._rid("ps"), subject, forms["z"],
                               coding={"system": SNOMED, "code": code})
            b = self.procedure(self._rid("ps"), subject, forms["offset"],
                               coding={"system": SNOMED_OID, "code": code},
                               extra={"note": [{"text": "same procedure"}]})
            self._cluster([a["id"], b["id"]], "procedure_system_spelling",
                          b["id"])
        # 6x performedPeriod vs performedDateTime same local day (OTHER).
        for i in range(6):
            day = datetime(2024, 8, 6, tzinfo=timezone.utc) + \
                timedelta(days=i * 9)
            subject = self._patient()
            code = PROC_CODES[i % len(PROC_CODES)]
            rid_a = self._rid("pw")
            resource = {
                "resourceType": "Procedure",
                "id": rid_a,
                "status": "completed",
                "subject": {"reference": subject},
                "code": {"coding": [{"system": SNOMED, "code": code}]},
                "performedPeriod": {
                    "start": _fmt_z(day + timedelta(hours=10)),
                    "end": _fmt_z(day + timedelta(hours=11)),
                },
            }
            self.resources.append(resource)
            b = self.procedure(
                self._rid("pw"), subject,
                _fmt_z(day + timedelta(hours=10, minutes=30)),
                coding={"system": SNOMED, "code": code})
            # period start instant (10:00Z) beats the 10:30Z member.
            self._cluster([rid_a, b["id"]], "procedure_period_vs_datetime",
                          rid_a)

    def condition_clusters(self) -> None:
        # 8x same-local-date merge.
        for i in range(8):
            day = datetime(2024, 1, 25, tzinfo=timezone.utc) + \
                timedelta(days=i * 12)
            code = CONDITION_CODES[i % len(CONDITION_CODES)]
            subject = self._patient()
            a = self.condition(self._rid("cs"), subject,
                               day.strftime("%Y-%m-%d"),
                               coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("cs"), subject,
                               day.strftime("%Y-%m-%d"),
                               coding={"system": SNOMED_OID, "code": code})
            self._cluster([a["id"], b["id"]], "condition_same_date", None)
        # 6x same-MONTH merge.
        for i in range(6):
            month = f"2024-{(i % 12) + 1:02d}"
            code = CONDITION_CODES[(i + 2) % len(CONDITION_CODES)]
            subject = self._patient()
            a = self.condition(self._rid("cm"), subject, month,
                               coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("cm"), subject, month,
                               coding={"system": SNOMED, "code": code})
            self._cluster([a["id"], b["id"]], "condition_same_month", None)
        # 6x YEAR subsumes MONTHs.
        for i in range(6):
            year = f"{2015 + i}"
            code = CONDITION_CODES[(i + 4) % len(CONDITION_CODES)]
            subject = self._patient()
            rid_year = self._rid("cy")
            self.condition(rid_year, subject, year,
                           coding={"system": SNOMED, "code": code})
            m1 = self.condition(self._rid("cy"), subject, f"{year}-03",
                                coding={"system": SNOMED, "code": code})
            m2 = self.condition(self._rid("cy"), subject, f"{year}-09",
                                coding={"system": SNOMED_OID, "code": code})
            # MONTH outranks YEAR at survivorship.
            self._cluster([rid_year, m1["id"], m2["id"]],
                          "condition_year_subsumption", m1["id"])
        # 4x tz-variant onset pairs.
        for i in range(4):
            instant = datetime(2024, 9, 10, 22, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 19)
            forms = _tz_forms(instant)
            code = CONDITION_CODES[(i + 1) % len(CONDITION_CODES)]
            subject = self._patient()
            a = self.condition(self._rid("ct"), subject, forms["z"],
                               coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("ct"), subject, forms["offset"],
                               coding={"system": SNOMED, "code": code})
            self._cluster([a["id"], b["id"]], "condition_tz_variant", None)
        # 6x DT + DATE_ONLY same authored local date.
        for i in range(6):
            day = datetime(2024, 10, 15, tzinfo=timezone.utc) + \
                timedelta(days=i * 8)
            code = CONDITION_CODES[(i + 3) % len(CONDITION_CODES)]
            subject = self._patient()
            rid_dt = self._rid("cd")
            self.condition(rid_dt, subject,
                           day.strftime("%Y-%m-%dT09:15:00"),
                           coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("cd"), subject,
                               day.strftime("%Y-%m-%d"),
                               coding={"system": SNOMED, "code": code})
            # DT_NAIVE outranks DATE_ONLY.
            self._cluster([rid_dt, b["id"]], "condition_dt_vs_date", rid_dt)

    def immunization_clusters(self) -> None:
        # 8x tz-variant 3-way occurrenceDateTime.
        for i in range(8):
            instant = datetime(2024, 2, 20, 16, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 26)
            forms = _tz_forms(instant)
            subject = self._patient()
            code = CVX_CODES[i % len(CVX_CODES)]
            rid_a = self._rid("iz")
            self.immunization(rid_a, subject, forms["offset"], cvx_code=code)
            b = self.immunization(self._rid("iz"), subject, forms["z"],
                                  cvx_code=code)
            c = self.immunization(self._rid("iz"), subject, forms["naive"],
                                  cvx_code=code)
            self._cluster([rid_a, b["id"], c["id"]], "immunization_tz_variant",
                          rid_a)
        # 10x same-instant identical duplicates (different record ids).
        for i in range(10):
            instant = datetime(2024, 5, 8, 14, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 7, hours=(i % 3))
            forms = _tz_forms(instant)
            subject = self._patient()
            code = CVX_CODES[i % len(CVX_CODES)]
            a = self.immunization(self._rid("im"), subject, forms["z"],
                                  cvx_code=code)
            b = self.immunization(self._rid("im"), subject, forms["offset"],
                                  cvx_code=code)
            self._cluster([a["id"], b["id"]], "immunization_same_instant",
                          None)

    # -- hard negatives -----------------------------------------------------
    def hard_negatives(self) -> None:
        rng = self.rng
        # 10x same code+date, different value.
        for i in range(10):
            base = datetime(2024, 3, 18, 9, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 5)
            subject = self._patient()
            code = LAB_CODES[i % len(LAB_CODES)]
            a = self.obs(self._rid("nv"), subject, effective=_fmt_z(base),
                         loinc=code, value=140, unit="mg/dL",
                         category="laboratory")
            b = self.obs(self._rid("nv"), subject, effective=_fmt_z(
                base + timedelta(minutes=rng.choice([2, 9, 20]))),
                loinc=code, value=80, unit="mg/dL", category="laboratory")
            self._negative(a["id"], b["id"], "same_code_date_diff_value")
        # 8x sibling LAB observations 35 minutes apart (outside 30-min window).
        for i in range(8):
            base = datetime(2024, 4, 22, 8, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 6)
            subject = self._patient()
            code = LAB_CODES[(i + 1) % len(LAB_CODES)]
            a = self.obs(self._rid("ns"), subject, effective=_fmt_z(base),
                         loinc=code, value=110 + i, unit="mg/dL",
                         category="laboratory")
            b = self.obs(self._rid("ns"), subject,
                         effective=_fmt_z(base + timedelta(minutes=35)),
                         loinc=code, value=110 + i, unit="mg/dL",
                         category="laboratory")
            self._negative(a["id"], b["id"], "lab_sibling_35min")
        # 8x vitals 6 minutes apart (outside 5-min window, non-extended codes).
        for i in range(8):
            base = datetime(2024, 5, 27, 15, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 4)
            loinc = ["8480-6", "8462-4", "8867-4", "8310-5", "9279-1",
                     "59408-5", "8480-6", "8462-4"][i]
            subject = self._patient()
            a = self.obs(self._rid("nv6"), subject, effective=_fmt_z(base),
                         loinc=loinc, value=72 + i, unit="mmHg",
                         category="vital-signs")
            b = self.obs(self._rid("nv6"), subject,
                         effective=_fmt_z(base + timedelta(minutes=6)),
                         loinc=loinc, value=72 + i, unit="mmHg",
                         category="vital-signs")
            self._negative(a["id"], b["id"], "vital_6min_apart")
        # 6x troponin 6 minutes apart (outside the 5-min serial window).
        for i in range(6):
            base = datetime(2024, 6, 17, 11, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 8)
            code = TROPONIN_CODES[i % len(TROPONIN_CODES)]
            subject = self._patient()
            a = self.obs(self._rid("nt"), subject, effective=_fmt_z(base),
                         loinc=code, value=0.04 + i * 0.02, unit="ng/mL",
                         category="laboratory")
            b = self.obs(self._rid("nt"), subject,
                         effective=_fmt_z(base + timedelta(minutes=6)),
                         loinc=code, value=0.04 + i * 0.02, unit="ng/mL",
                         category="laboratory")
            self._negative(a["id"], b["id"], "troponin_6min_apart")
        # 8x different codes, same patient/instant/value.
        for i in range(8):
            base = datetime(2024, 7, 23, 10, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 3)
            subject = self._patient()
            left = LAB_CODES[i % len(LAB_CODES)]
            right = LAB_CODES[(i + 3) % len(LAB_CODES)]
            if right == left:
                right = "6299-2"
            a = self.obs(self._rid("nd"), subject, effective=_fmt_z(base),
                         loinc=left, value=99, unit="mg/dL",
                         category="laboratory")
            b = self.obs(self._rid("nd"), subject, effective=_fmt_z(base),
                         loinc=right, value=99, unit="mg/dL",
                         category="laboratory")
            self._negative(a["id"], b["id"], "different_codes_same_rest")
        # 10x cross-patient identical everything.
        for i in range(10):
            base = datetime(2024, 8, 19, 13, 0, tzinfo=timezone.utc) + \
                timedelta(days=i * 2)
            code = LAB_CODES[i % len(LAB_CODES)]
            subject_a = self._patient()
            subject_b = self._patient()
            a = self.obs(self._rid("np"), subject_a, effective=_fmt_z(base),
                         loinc=code, value=101, unit="mg/dL",
                         category="laboratory")
            b = self.obs(self._rid("np"), subject_b, effective=_fmt_z(base),
                         loinc=code, value=101, unit="mg/dL",
                         category="laboratory")
            self._negative(a["id"], b["id"], "cross_patient_identical")
        # 3x Conditions: different local dates (same patient/code).
        for i in range(3):
            code = CONDITION_CODES[i]
            subject = self._patient()
            a = self.condition(self._rid("nc"), subject, f"2024-09-1{i}",
                               coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("nc"), subject, f"2024-09-2{i}",
                               coding={"system": SNOMED, "code": code})
            self._negative(a["id"], b["id"], "condition_diff_dates")
        # 3x Conditions: disjoint months, no containment (same patient/code).
        for i in range(3):
            code = CONDITION_CODES[i + 3]
            subject = self._patient()
            a = self.condition(self._rid("nm"), subject, f"2024-0{i + 1}",
                               coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("nm"), subject, f"2024-1{i + 1}",
                               coding={"system": SNOMED, "code": code})
            self._negative(a["id"], b["id"], "condition_disjoint_months")
        # 4x Conditions: different years (YEAR rows never share a bucket).
        for i in range(4):
            code = CONDITION_CODES[i]
            subject = self._patient()
            a = self.condition(self._rid("ny"), subject, f"{2020 + i}",
                               coding={"system": SNOMED, "code": code})
            b = self.condition(self._rid("ny"), subject, f"{2021 + i}",
                               coding={"system": SNOMED, "code": code})
            self._negative(a["id"], b["id"], "condition_diff_years")

    def build(self) -> dict:
        self.vital_clusters()              # 34
        self.lab_clusters()                # 46
        self.other_observation_clusters()  # 6
        self.procedure_clusters()          # 16
        self.condition_clusters()          # 30
        self.immunization_clusters()       # 18
        self.hard_negatives()              # 60 negative cases
        return {
            "description": (
                "AMUX-142 temporal-dedup golden corpus v1 — labeled duplicate "
                "clusters + hard non-duplicate cases over Observation, "
                "Procedure, Condition, Immunization. Regenerate with "
                "scripts/gen_dedup_golden.py."
            ),
            "resources": sorted(self.resources, key=lambda r: r["id"]),
            "clusters": sorted(self.clusters, key=lambda c: c["members"]),
            "negatives": sorted(self.negatives,
                                key=lambda n: (n["a"], n["b"])),
        }


def selfcheck(corpus: dict) -> None:
    from fhir4ds.dedup.evaluation import evaluate_dedup_golden

    metrics = evaluate_dedup_golden(corpus)
    if metrics.false_positives:
        raise SystemExit(
            "SELF-CHECK FAILED: false merges: "
            + json.dumps(metrics.false_positives[:10], indent=2)
        )
    if metrics.misses:
        raise SystemExit(
            "SELF-CHECK FAILED: missed duplicate pairs: "
            + json.dumps(metrics.misses[:10], indent=2)
        )
    if metrics.survivorship_errors:
        raise SystemExit(
            "SELF-CHECK FAILED: survivorship mismatches: "
            + json.dumps(metrics.survivorship_errors[:10], indent=2)
        )
    print(
        f"self-check OK: precision={metrics.precision:.4f} "
        f"recall={metrics.recall:.4f} survivorship="
        f"{metrics.survivorship_accuracy:.4f} "
        f"(clusters={metrics.labeled_clusters} "
        f"negatives={metrics.labeled_negatives} "
        f"pairs={metrics.positive_pairs})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-selfcheck", action="store_true")
    args = parser.parse_args()

    builder = CorpusBuilder(args.seed)
    corpus = builder.build()
    corpus["seed"] = args.seed
    corpus["generator"] = f"scripts/gen_dedup_golden.py --seed {args.seed}"

    if not args.no_selfcheck:
        selfcheck(corpus)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(corpus, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    labeled_members = sum(len(c["members"]) for c in corpus["clusters"])
    print(
        f"wrote {args.out}: {len(corpus['resources'])} resources, "
        f"{len(corpus['clusters'])} clusters ({labeled_members} members), "
        f"{len(corpus['negatives'])} negative cases"
    )


if __name__ == "__main__":
    main()
