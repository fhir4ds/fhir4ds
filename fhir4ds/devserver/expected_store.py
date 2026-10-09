"""S3 (c-cleanroom-ux5 item 3): per-patient expected-results store.

Expected results are persisted as MeasureReports in the MADiE
cqfm-test-cases shape (one file per patient under
``measures/expected/patients/<measure>/<patientId>.json``):

* ``meta.profile`` = ``http://hl7.org/fhir/us/cqf-measures/StructureDefinition/...``
  style profile marker is intentionally OMITTED (MADiE sets it on export;
  we accept it on import, omit on write — additive compatibility).
* modifierExtension ``isTestCases = true`` — the MADiE marker; carried so
  MADiE tooling recognizes our files and OUR loader can defensively skip
  them if one ever lands in a data dir.
* extension ``cqfm-inputParameters`` → ``contained[0]`` Parameters with
  the period used at capture time.
* ``group[].population[].count`` = expected counts (what the user edits).

Compatibility note (design §0.3): our loader-side guard skips
MeasureReport entries carrying the isTestCases marker, so these files
never pollute the kernel resources table even if copied into data/.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IS_TEST_CASES_URL = "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-isTestCases"
CQFM_INPUT_PARAMETERS_URL = (
    "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-inputParameters"
)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _safe(name: str) -> bool:
    return bool(name) and bool(_SAFE_NAME.match(name)) and not name.startswith(".")


def expected_patients_dir(expected_root: Path, measure: str) -> Path:
    """Per-patient expected dir for a measure (no mkdir)."""
    return expected_root / "patients" / measure


def is_test_case_report(resource: dict[str, Any] | None) -> bool:
    """True when a resource carries the MADiE isTestCases marker.

    Used BOTH by the expected-store (to stamp our own files) and by the
    dataset loader defensive guard (S4) — single source of truth.
    """
    if not isinstance(resource, dict):
        return False
    if resource.get("resourceType") != "MeasureReport":
        return False
    for ext in resource.get("modifierExtension") or []:
        if isinstance(ext, dict) and ext.get("url") == IS_TEST_CASES_URL:
            return True
    meta = resource.get("meta") or {}
    for prof in meta.get("profile") or []:
        if isinstance(prof, str) and "cqfm-test-cases" in prof:
            return True
    return False


def build_expected_report(
    patient_id: str,
    groups: list[dict[str, Any]],
    *,
    period_start: str | None = None,
    period_end: str | None = None,
    library_url: str | None = None,
) -> dict[str, Any]:
    """Build a cqfm-test-cases-style expected MeasureReport.

    ``groups``: [{id, population: [{code, count}]}] — the editable
    expectation payload.
    """
    report: dict[str, Any] = {
        "resourceType": "MeasureReport",
        "id": f"expected-{patient_id}",
        "status": "complete",
        "type": "individual",
        "measure": library_url or "urn:cleanroom:measure",
        "subject": {"reference": f"Patient/{patient_id}"},
        "contained": [
            {
                "resourceType": "Parameters",
                "id": "input",
                "parameter": [
                    *({"name": "periodStart", "valueString": period_start} for _ in [0] if period_start),
                    *({"name": "periodEnd", "valueString": period_end} for _ in [0] if period_end),
                ],
            }
        ],
        "modifierExtension": [{"url": IS_TEST_CASES_URL, "valueBoolean": True}],
        "extension": [
            {"url": CQFM_INPUT_PARAMETERS_URL, "valueReference": {"reference": "#input"}}
        ],
        "group": groups,
    }
    return report


def parse_expected_groups(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the editable [{id, population:[{code,count}]}] from a report.

    Accepts BOTH our shape and MADiE's (population code under
    ``code.coding[0].code`` or a bare string ``code``; MADiE also carries
    ``id`` display ids — preserved as ``display_id`` when present).
    """
    groups: list[dict[str, Any]] = []
    for g in report.get("group") or []:
        if not isinstance(g, dict):
            continue
        pops = []
        for p in g.get("population") or []:
            if not isinstance(p, dict):
                continue
            code = None
            c = p.get("code")
            if isinstance(c, str):
                code = c
            elif isinstance(c, dict):
                codings = c.get("coding") or []
                if codings and isinstance(codings[0], dict):
                    code = codings[0].get("code")
            if code is None:
                continue
            count = p.get("count")
            if not isinstance(count, int):
                continue
            pop: dict[str, Any] = {"code": code, "count": count}
            if p.get("id"):
                pop["display_id"] = p["id"]
            pops.append(pop)
        entry: dict[str, Any] = {"population": pops}
        if g.get("id"):
            entry["id"] = g["id"]
        groups.append(entry)
    return groups


def patient_from_report(report: dict[str, Any]) -> str | None:
    """Patient id from subject.reference (Patient/<id> or bare id)."""
    subject = report.get("subject") or {}
    ref = subject.get("reference") if isinstance(subject, dict) else None
    if not isinstance(ref, str) or not ref:
        return None
    tail = ref.rsplit("/", 1)[-1]
    return tail or None


def save_expected_report(
    expected_root: Path,
    measure: str,
    report: dict[str, Any],
) -> Path:
    """Persist one per-patient expected report (atomic write)."""
    if not _safe(measure):
        raise ValueError(f"invalid measure name: {measure!r}")
    pid = patient_from_report(report)
    if pid is None or not _safe(pid):
        raise ValueError("report has no usable subject patient id")
    target_dir = expected_patients_dir(expected_root, measure)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{pid}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def load_expected_reports(
    expected_root: Path,
    measure: str,
) -> list[dict[str, Any]]:
    """All per-patient expected reports for a measure, sorted by patient."""
    d = expected_patients_dir(expected_root, measure)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(d.glob("*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(doc, dict) and doc.get("resourceType") == "MeasureReport":
            out.append(doc)
    return out


def delete_expected_report(expected_root: Path, measure: str, patient_id: str) -> bool:
    """Delete one patient's expected report. Returns True when removed."""
    if not _safe(measure) or not _safe(patient_id):
        return False
    target = expected_patients_dir(expected_root, measure) / f"{patient_id}.json"
    if target.is_file():
        target.unlink()
        return True
    return False


def stamp_capture(report: dict[str, Any]) -> dict[str, Any]:
    """Add capture metadata (additive extension, MADiE-compatible)."""
    ext = report.setdefault("extension", [])
    ext.append(
        {
            "url": "http://fhir4ds.org/devserver/StructureDefinition/captured-at",
            "valueDateTime": datetime.now(timezone.utc).isoformat(),
        }
    )
    return report
