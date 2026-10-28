"""S22d-1 (AM5–AM8): the FHIR-type workspace — migration + helpers.

The workspace root IS the resource map: every top-level directory is a
FHIR resource type (exact FHIR casing) — ``Library/`` (both ``.cql``
source and FHIR Library ``.json``), ``ValueSet/``, ``Parameters/``,
``Patient/<patientId>/`` (one folder per patient: the Patient resource
+ their clinical resources BY TYPE under subfolders), root type folders
for unattributed resources, and ``Measure/<m>/`` per-measure dirs
(Measure/<name>.json, Parameters/overrides.json, List/TestCases.json,
MeasureReport/<patientId>.json, ViewDefinition/…).

This module holds the LEGACY -> TYPE migration (one-time on first
boot; originals archived to ``_attic/``) plus shared knowledge:
the FHIR resource-type name set, the type-folder read helpers, and
the FHIR ``List`` (test-set membership) shape.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

# Exact-FHIR-casing resource types recognized as workspace ROOT folders
# (the reserved-name list per AM7; `cql/` is legacy — `Library/` is the
# type-cased home). This is the discovery allowlist: any OTHER root
# directory (except _attic/ and dot-dirs) is IGNORED by type discovery.
FHIR_TYPE_FOLDERS: frozenset[str] = frozenset(
    {
        "Account", "ActivityDefinition", "AdverseEvent", "AllergyIntolerance",
        "Appointment", "AppointmentResponse", "AuditEvent", "Basic", "Binary",
        "BiologicallyDerivedProduct", "BodyStructure", "Bundle", "CapabilityStatement",
        "CarePlan", "CareTeam", "CatalogEntry", "ChargeItem", "ChargeItemDefinition",
        "Claim", "ClaimResponse", "ClinicalImpression", "CodeSystem", "Communication",
        "CommunicationRequest", "CompartmentDefinition", "Composition", "ConceptMap",
        "Condition", "Consent", "Contract", "Coverage", "CoverageEligibilityRequest",
        "CoverageEligibilityResponse", "DetectedIssue", "Device", "DeviceDefinition",
        "DeviceMetric", "DeviceRequest", "DeviceUseStatement", "DiagnosticReport",
        "DocumentManifest", "DocumentReference", "EffectEvidenceSynthesis",
        "Encounter", "Endpoint", "EnrollmentRequest", "EnrollmentResponse",
        "EpisodeOfCare", "EventDefinition", "Evidence", "EvidenceVariable",
        "ExampleScenario", "ExplanationOfBenefit", "FamilyMemberHistory", "Flag",
        "Goal", "GraphDefinition", "Group", "GuidanceResponse", "HealthcareService",
        "ImagingStudy", "Immunization", "ImmunizationEvaluation",
        "ImmunizationRecommendation", "ImplementationGuide", "InsurancePlan",
        "Invoice", "Library", "Linkage", "List", "Location", "Measure",
        "MeasureReport", "Media", "Medication", "MedicationAdministration",
        "MedicationDispense", "MedicationKnowledge", "MedicationRequest",
        "MedicationStatement", "MedicinalProduct", "MedicinalProductAuthorization",
        "MedicinalProductContraindication", "MedicinalProductIndication",
        "MedicinalProductIngredient", "MedicinalProductInteraction",
        "MedicinalProductManufactured", "MedicinalProductPackaged",
        "MedicinalProductPharmaceutical", "MedicinalProductUndesirableEffect",
        "MessageDefinition", "MessageHeader", "MolecularSequence", "NamingSystem",
        "NutritionOrder", "Observation", "ObservationDefinition", "OperationDefinition",
        "OperationOutcome", "Organization", "OrganizationAffiliation", "Parameters",
        "Patient", "PaymentNotice", "PaymentReconciliation", "Person", "PlanDefinition",
        "Practitioner", "PractitionerRole", "Procedure", "Provenance", "Questionnaire",
        "QuestionnaireResponse", "RelatedPerson", "RequestGroup", "ResearchDefinition",
        "ResearchElementDefinition", "ResearchStudy", "ResearchSubject",
        "RiskAssessment", "RiskEvidenceSynthesis", "Schedule", "SearchParameter",
        "ServiceRequest", "Slot", "Specimen", "SpecimenDefinition", "StructureDefinition",
        "StructureMap", "Subscription", "Substance", "SubstanceDefinition",
        "SubstanceNucleicAcid", "SubstancePolymer", "SubstanceProtein",
        "SubstanceReferenceInformation", "SubstanceSourceMaterial", "SupplyDelivery",
        "SupplyRequest", "Task", "TerminologyCapabilities", "TestReport", "TestScript",
        "ValueSet", "VerificationResult", "VisionPrescription",
    }
)

# AM5(2): measure-dir inner layout (under Measure/<m>/).
MEASURE_INNER_TYPES = ("Measure", "Parameters", "List", "MeasureReport", "ViewDefinition")

# Patient-reference fields consulted when attributing a resource to a
# patient folder (mirrors the loader's typed patient-ref doctrine).
_PATIENT_REF_FIELDS = ("subject", "patient", "beneficiary")


def _patient_ref_target(resource: dict) -> str | None:
    """Id tail of a Patient-typed reference, or None."""
    for field in _PATIENT_REF_FIELDS:
        value = resource.get(field)
        if not isinstance(value, dict):
            continue
        ref = value.get("reference")
        if not isinstance(ref, str) or not ref:
            continue
        parts = [p for p in ref.split("/") if p]
        if len(parts) >= 2 and parts[-2] == "Patient":
            return parts[-1]
    return None


def read_resource(path: Path) -> dict | None:
    """Lenient JSON resource read (None on unreadable/malformed)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            resource = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return resource if isinstance(resource, dict) else None


def write_resource(path: Path, resource: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(resource, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def test_cases_list(patient_ids: list[str]) -> dict:
    """The FHIR List resource for measure test-set membership (AM5-2)."""
    return {
        "resourceType": "List",
        "status": "current",
        "mode": "working",
        "entry": [
            {"item": {"reference": f"Patient/{pid}"}} for pid in sorted(patient_ids)
        ],
    }


def list_patient_ids(list_resource: dict | None) -> list[str]:
    """Patient ids referenced by a TestCases List (sorted)."""
    if not isinstance(list_resource, dict):
        return []
    out: list[str] = []
    for entry in list_resource.get("entry") or []:
        item = entry.get("item") if isinstance(entry, dict) else None
        ref = item.get("reference") if isinstance(item, dict) else None
        if isinstance(ref, str) and ref.startswith("Patient/"):
            pid = ref[len("Patient/"):]
            if pid and pid not in out:
                out.append(pid)
    return sorted(out)


def is_legacy_workspace(root: Path) -> bool:
    """True when legacy convention shapes are present (migration trigger)."""
    legacy_markers = ("cql", "valuesets", "data", "measures", "views")
    return any((root / m).is_dir() for m in legacy_markers)


def migrate_workspace(root: Path, *, dry_run: bool = False) -> dict:
    """One-time legacy -> FHIR-type migration (AM5–AM8 §9 mapping).

    - ``cql/*.cql``                -> ``Library/*.cql``
    - ``valuesets/*.json``         -> ``ValueSet/<id>.json``
    - ``parameters/workspace.json``-> ``Parameters/workspace.json``
    - ``data/*.ndjson`` monolith   -> ``Patient/<id>/<Type>/<id>.json``
    - unattributed data resources  -> ``<Type>/<id>.json`` at the root
    - originals archived under ``_attic/<timestamp>/``

    Idempotent: a workspace without legacy markers returns unchanged.
    """
    root = Path(root)
    report: dict = {"migrated": False, "moves": [], "attic": None, "patients": 0}
    if not is_legacy_workspace(root):
        return report
    attic = root / "_attic" / "migration-legacy"
    report["attic"] = str(attic)

    def archive(rel: str) -> None:
        src = root / rel
        if src.exists():
            dst = attic / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dry_run:
                report["moves"].append(f"{rel} -> _attic/{rel}")
            else:
                shutil.move(str(src), str(dst))

    def place(resource: dict, suggested_path: Path) -> None:
        """Write one resource at its canonical type-folder path."""
        if dry_run:
            report["moves"].append(str(suggested_path.relative_to(root)))
            return
        # Collision policy: never overwrite — version the filename.
        target = suggested_path
        stem, suffix = suggested_path.stem, suggested_path.suffix
        n = 1
        while target.exists():
            target = suggested_path.with_name(f"{stem}-{n}{suffix}")
            n += 1
        write_resource(target, resource)

    # 1. Libraries.
    cql_dir = root / "cql"
    if cql_dir.is_dir():
        for path in sorted(cql_dir.glob("*.cql")):
            dest = root / "Library" / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dry_run:
                report["moves"].append(f"cql/{path.name} -> Library/{path.name}")
            else:
                shutil.copy2(path, dest)
        archive("cql")

    # 2. Valuesets.
    vs_dir = root / "valuesets"
    if vs_dir.is_dir():
        for path in sorted(vs_dir.glob("*.json")):
            resource = read_resource(path)
            rid = resource.get("id") if resource else None
            name = rid if isinstance(rid, str) and rid.strip() else path.stem
            place(resource or {"resourceType": "ValueSet"}, root / "ValueSet" / f"{name}.json")
        archive("valuesets")

    # 3. Parameters.
    params_legacy = root / "parameters" / "workspace.json"
    if params_legacy.is_file():
        resource = read_resource(params_legacy)
        if resource:
            place(resource, root / "Parameters" / "workspace.json")
        archive("parameters")

    # 4. Data monoliths + per-patient bundles -> Patient folders / type folders.
    data_dir = root / "data"
    if data_dir.is_dir():
        for path in sorted(data_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() == ".ndjson":
                try:
                    lines = path.read_text(encoding="utf-8-sig").splitlines()
                except OSError:
                    continue
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        resource = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(resource, dict):
                        continue
                    _place_by_reference(root, resource, place)
                archive(str(path.relative_to(root)))
            elif path.suffix.lower() == ".json":
                resource = read_resource(path)
                if resource is None:
                    continue
                rtype = resource.get("resourceType")
                if rtype == "Bundle":
                    for entry in resource.get("entry") or []:
                        inner = entry.get("resource") if isinstance(entry, dict) else None
                        if isinstance(inner, dict):
                            _place_by_reference(root, inner, place)
                elif isinstance(rtype, str) and rtype in FHIR_TYPE_FOLDERS:
                    _place_by_reference(root, resource, place)
                # non-FHIR JSON (config etc.) is left in place.
        # Remove emptied data dirs (files archived individually).
        if not dry_run:
            for path in sorted(data_dir.rglob("*"), reverse=True):
                if path.is_dir():
                    try:
                        path.rmdir()
                    except OSError:
                        pass
            try:
                data_dir.rmdir()
            except OSError:
                pass

    # 5. Legacy measures/ + views/ (flat) -> Measure dirs / ViewDefinition.
    measures_dir = root / "measures"
    if measures_dir.is_dir():
        for path in sorted(measures_dir.glob("*.json")):
            resource = read_resource(path)
            if not resource:
                continue
            rtype = resource.get("resourceType")
            if rtype == "Measure":
                mdir = resource.get("id") or path.stem
                if isinstance(mdir, str) and mdir:
                    place(resource, root / "Measure" / mdir / "Measure" / f"{mdir}.json")
            else:
                place(resource, root / "ViewDefinition" / path.name)
        archive("measures")
    views_dir = root / "views"
    if views_dir.is_dir():
        for path in sorted(views_dir.glob("*.json")):
            resource = read_resource(path)
            if resource:
                place(resource, root / "ViewDefinition" / path.name)
        archive("views")

    patients_dir = root / "Patient"
    if patients_dir.is_dir():
        report["patients"] = len([p for p in patients_dir.iterdir() if p.is_dir()])
    report["migrated"] = True
    return report


def _place_by_reference(root: Path, resource: dict, place) -> None:
    """Route one resource to its canonical folder (AM5(1))."""
    rtype = resource.get("resourceType")
    rid = resource.get("id")
    rid = rid if isinstance(rid, str) and rid else "unknown"
    if rtype == "Patient":
        # Single patient store: Patient/<id>/<id>.json
        place(resource, root / "Patient" / rid / f"{rid}.json")
        return
    pid = _patient_ref_target(resource)
    if pid is not None:
        # Attributed clinical resource: inside the patient's folder, by type.
        place(resource, root / "Patient" / pid / str(rtype) / f"{rid}.json")
        return
    if isinstance(rtype, str) and rtype in FHIR_TYPE_FOLDERS:
        # Unattributed: root type folder, one file per resource.
        place(resource, root / rtype / f"{rid}.json")


# ---------------------------------------------------------------------------
# S22e (§3): normalize-on-ingest — the ONGOING path (not first-boot)
# ---------------------------------------------------------------------------

def normalize_ndjson_ingest(data: Path, *, root: Path | None = None) -> dict:
    """Normalize any ``*.ndjson`` files under ``data/`` into the canonical shape.

    ndjson is TRANSPORT only: every monolith under the data dir is
    parsed once, split into ``Patient/<id>/`` folders (typed patient-ref
    doctrine) with unattributed resources in their root type folders,
    then archived to ``_attic/ingest/<name>`` (never deleted).
    ``root`` defaults to the data dir's parent (the workspace root).
    Returns ``{normalized: <file count>, patients: <ids>}``.
    """
    data = Path(data)
    if root is None:
        # Auto-detect: a dir named `data` IS the data dir; anything
        # containing one is the workspace root.
        if data.name == "data":
            root = data.parent
        elif (data / "data").is_dir():
            root = data
            data = data / "data"
        else:
            root = data.parent
    else:
        root = Path(root)
    if not data.is_dir():
        return {"normalized": 0, "patients": []}
    report = {"normalized": 0, "patients": []}
    seen_patients: set[str] = set()

    def place(resource: dict, suggested: Path) -> None:
        target = suggested
        stem, suffix = suggested.stem, suggested.suffix
        n = 1
        while target.exists():
            target = suggested.with_name(f"{stem}-{n}{suffix}")
            n += 1
        write_resource(target, resource)

    for path in sorted(data.rglob("*.ndjson")):
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                resource = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(resource, dict):
                continue
            rtype = resource.get("resourceType")
            rid = resource.get("id")
            rid = rid if isinstance(rid, str) and rid else "unknown"
            if rtype == "Patient":
                place(resource, root / "Patient" / rid / f"{rid}.json")
                seen_patients.add(rid)
                continue
            pid = _patient_ref_target(resource)
            if pid is not None:
                place(
                    resource,
                    root / "Patient" / pid / str(rtype) / f"{rid}.json",
                )
                seen_patients.add(pid)
            elif isinstance(rtype, str) and rtype in FHIR_TYPE_FOLDERS:
                place(resource, root / rtype / f"{rid}.json")
        attic = root / "_attic" / "ingest" / path.relative_to(data).parent
        attic.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(attic / path.name))
        report["normalized"] += 1
    report["patients"] = sorted(seen_patients)
    return report
