"""
Load test cases from FHIR bundles.
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class TestCase:
    """A single test case with patient data and expected results."""
    patient_id: str
    resources: List[Dict[str, Any]]  # Patient, Encounter, Observation, etc.
    expected_results: Dict[str, bool]  # definition_name -> expected value
    description: Optional[str] = None

@dataclass
class TestSuite:
    """Collection of test cases for a measure."""
    measure_id: str
    test_cases: List[TestCase]
    total_patients: int
    measurement_period: Optional[Dict[str, str]] = None

def load_test_suite(measure_config: "MeasureConfig") -> TestSuite:
    """
    Load all test cases for a measure from test bundles.

    Structure A (2025 — bundle files):
        input/tests/measure/<MeasureName>/tests-<patient-id>-bundle.json

    Structure B (2026 — directory per patient):
        input/tests/measure/<MeasureName>/<TestCase>/Patient-*.json
        input/tests/measure/<MeasureName>/<TestCase>/MeasureReport-*.json
        input/tests/measure/<MeasureName>/<TestCase>/Encounter-*.json
        ...
    """
    test_cases = []
    measurement_period = None

    # Strategy A: bundle files
    bundle_files = list(measure_config.test_dir.glob("tests-*-bundle.json"))
    if bundle_files:
        for bundle_path in bundle_files:
            test_case = _parse_test_bundle(bundle_path, measure_config)
            if test_case:
                test_cases.append(test_case)
                if measurement_period is None:
                    measurement_period = _extract_measurement_period(bundle_path)
    else:
        # Strategy B: directory-based (each subdirectory is a test case)
        for subdir in sorted(measure_config.test_dir.iterdir()):
            if not subdir.is_dir():
                continue
            test_case = _parse_test_directory(subdir, measure_config)
            if test_case:
                test_cases.append(test_case)
                if measurement_period is None:
                    measurement_period = _extract_measurement_period_from_dir(subdir)

    return TestSuite(
        measure_id=measure_config.id,
        test_cases=test_cases,
        total_patients=len(test_cases),
        measurement_period=measurement_period,
    )

def _parse_test_bundle(
    bundle_path: Path,
    measure_config: "MeasureConfig"
) -> Optional[TestCase]:
    """
    Parse a single test bundle file.

    Extracts:
    - Patient ID from Patient resource
    - All resources for loading into DB
    - Expected results from MeasureReport
    """
    with open(bundle_path) as f:
        bundle = json.load(f)

    resources = []
    patient_id = None
    expected_results = {}
    description = None

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")

        if resource_type == "Patient":
            patient_id = resource.get("id")
            resources.append(resource)

        elif resource_type == "MeasureReport":
            # Extract expected population results
            extensions = resource.get("extension", [])
            if extensions:
                description = extensions[0].get("valueMarkdown", None)

            groups = resource.get("group", [])
            num_groups = len(groups)

            for group_idx, group in enumerate(groups):
                for pop in group.get("population", []):
                    coding = pop.get("code", {}).get("coding", [])
                    code = coding[0].get("code", "") if coding else ""
                    count = pop.get("count", 0)

                    # Map population codes to definition names
                    def_name = _population_code_to_definition(code)
                    if def_name:
                        if num_groups > 1:
                            # Multi-group: store numbered populations
                            # e.g. "Denominator 1", "Denominator 2"
                            numbered = f"{def_name} {group_idx + 1}"
                            expected_results[numbered] = (count >= 1)
                        else:
                            expected_results[def_name] = (count >= 1)

        elif resource_type in ("Encounter", "Observation", "Condition",
                               "Procedure", "MedicationRequest", "Medication",
                               "DiagnosticReport", "DocumentReference", "Location",
                               "Organization", "Practitioner", "PractitionerRole",
                               "Device", "Immunization", "AllergyIntolerance",
                               "ServiceRequest", "DeviceRequest", "Coverage",
                               "MedicationAdministration", "MedicationDispense",
                               "Claim", "Task", "Communication", "AdverseEvent"):
            resources.append(resource)

    if not patient_id:
        return None

    return TestCase(
        patient_id=patient_id,
        resources=resources,
        expected_results=expected_results,
        description=description,
    )

def _population_code_to_definition(code: str) -> Optional[str]:
    """Map FHIR population codes to CQL definition names."""
    mapping = {
        "initial-population": "Initial Population",
        "denominator": "Denominator",
        "denominator-exclusion": "Denominator Exclusion",
        "denominator-exception": "Denominator Exception",
        "numerator": "Numerator",
        "numerator-exclusion": "Numerator Exclusion",
    }
    return mapping.get(code)


def _parse_test_directory(
    test_dir: Path,
    measure_config: "MeasureConfig",
) -> Optional[TestCase]:
    """Parse a directory-based test case (2026 format).

    Each directory contains individual resource JSON files:
        Patient-<id>.json, Encounter-<id>.json, MeasureReport-<id>.json, ...
    """
    resources = []
    patient_id = None
    expected_results = {}
    description = None

    for json_file in sorted(test_dir.glob("*.json")):
        try:
            resource = json.loads(json_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        resource_type = resource.get("resourceType")
        if not resource_type:
            continue

        if resource_type == "Patient":
            patient_id = resource.get("id")
            resources.append(resource)
        elif resource_type == "MeasureReport":
            extensions = resource.get("extension", [])
            if extensions:
                description = extensions[0].get("valueMarkdown", None)
            groups = resource.get("group", [])
            num_groups = len(groups)
            for group_idx, group in enumerate(groups):
                for pop in group.get("population", []):
                    coding = pop.get("code", {}).get("coding", [])
                    code = coding[0].get("code", "") if coding else ""
                    count = pop.get("count", 0)
                    def_name = _population_code_to_definition(code)
                    if def_name:
                        if num_groups > 1:
                            expected_results[f"{def_name} {group_idx + 1}"] = (count >= 1)
                        else:
                            expected_results[def_name] = (count >= 1)
        else:
            resources.append(resource)

    if not patient_id:
        return None
    return TestCase(
        patient_id=patient_id,
        resources=resources,
        expected_results=expected_results,
        description=description,
    )


def _extract_measurement_period_from_dir(test_dir: Path) -> Optional[Dict[str, str]]:
    """Extract measurement period from a directory-based test case."""
    for f in test_dir.glob("MeasureReport-*.json"):
        try:
            data = json.loads(f.read_text())
            period = data.get("period")
            if period:
                return {"start": period.get("start"), "end": period.get("end")}
        except Exception:
            pass
    return None


def _extract_measurement_period(bundle_path: Path) -> Optional[Dict[str, str]]:
    """Extract measurement period from the first MeasureReport in a test bundle."""
    # Test bundles have a directory per patient with MeasureReport files
    test_dir = bundle_path.parent
    patient_dirs = [d for d in test_dir.iterdir() if d.is_dir()]
    for patient_dir in patient_dirs:
        for f in patient_dir.glob("MeasureReport-*.json"):
            try:
                data = json.load(open(f))
                period = data.get("period")
                if period:
                    return {"start": period.get("start"), "end": period.get("end")}
            except Exception:
                pass
    return None
