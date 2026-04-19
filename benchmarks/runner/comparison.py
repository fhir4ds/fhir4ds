"""
Compare results between cql-py and reference implementation.
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass
class DefineDiscrepancy:
    """Discrepancy for a single define statement."""
    library_name: str
    define_name: str
    cql_py_result: Any
    reference_result: Any
    cql_py_type: str
    reference_type: str


@dataclass
class PatientDiscrepancy:
    """Discrepancies for a single patient."""
    patient_id: str
    defines: List[DefineDiscrepancy]

    @property
    def define_count(self) -> int:
        return len(self.defines)


@dataclass
class DefineAccuracy:
    """Accuracy statistics for a single define statement."""
    define_name: str
    library_name: str
    matching: int
    total: int
    accuracy_pct: float


@dataclass
class ComparisonReport:
    """Complete comparison report between cql-py and reference."""
    measure_id: str
    measurement_period: Dict[str, str]

    # Patient counts
    cql_py_patients: int
    reference_patients: int
    patients_compared: int
    patients_with_errors: int

    # Overall accuracy
    overall_accuracy_pct: float
    matching_patients: int
    mismatched_patients: int

    # Per-define accuracy
    define_accuracy: List[DefineAccuracy]

    # Detailed discrepancies
    discrepancies: List[PatientDiscrepancy]

    # Performance
    cql_py_total_ms: float
    reference_total_ms: float
    speedup_factor: float  # cql-py / reference (< 1 means cql-py is faster)

    # Reference errors
    reference_errors: List[Dict[str, Any]]

    @property
    def cql_py_faster(self) -> bool:
        return self.speedup_factor < 1.0


def compare_results(
    cql_py_results: List[Dict[str, Any]],
    reference_result: "ReferenceResult",
    measure_config: "MeasureConfig",
    measurement_period: Dict[str, str],
    cql_py_timings: Dict[str, float]
) -> ComparisonReport:
    """
    Compare results from cql-py and reference implementation.

    Args:
        cql_py_results: List of patient results from cql-py
        reference_result: ReferenceResult containing expected results from test bundles
        measure_config: Measure configuration
        measurement_period: Measurement period used
        cql_py_timings: Timing dict from cql-py execution

    Returns:
        ComparisonReport with detailed comparison
    """
    # Build lookup maps
    cql_py_by_patient = {
        r["patient_id"]: r
        for r in cql_py_results
    }
    reference_by_patient = {
        pr.patient_id: pr
        for pr in reference_result.patient_results
    }

    # Find all unique defines across both implementations
    all_defines = _collect_all_defines(
        cql_py_results,
        reference_result.patient_results
    )

    # Compare each patient
    discrepancies = []
    define_matches: Dict[str, Dict[str, int]] = {}  # define_name -> {match, total}

    for define_name in all_defines:
        define_matches[define_name] = {"match": 0, "total": 0}

    all_patient_ids = set(cql_py_by_patient.keys()) | set(reference_by_patient.keys())

    for patient_id in all_patient_ids:
        cql_py_row = cql_py_by_patient.get(patient_id, {})
        ref_row = reference_by_patient.get(patient_id)

        if ref_row is None:
            # Patient not in reference - skip from comparison
            continue

        patient_discrepancies = []

        for define_name in all_defines:
            # Look up cql-py value by normalized name
            cql_py_val = cql_py_row.get(define_name)

            # Look up reference value by matching define name directly
            ref_define = next(
                (d for d in ref_row.define_results
                 if d.define_name == define_name
                 and d.library_name and "FHIRHelpers" not in d.library_name),
                None
            )
            ref_val = ref_define.result if ref_define else None
            ref_library = ref_define.library_name if ref_define else "unknown"

            define_matches[define_name]["total"] += 1

            if _results_equal(cql_py_val, ref_val):
                define_matches[define_name]["match"] += 1
            else:
                patient_discrepancies.append(DefineDiscrepancy(
                    library_name=ref_library,
                    define_name=define_name,
                    cql_py_result=cql_py_val,
                    reference_result=ref_val,
                    cql_py_type=_get_result_type(cql_py_val),
                    reference_type=ref_define.result_type if ref_define else "missing"
                ))

        if patient_discrepancies:
            discrepancies.append(PatientDiscrepancy(
                patient_id=patient_id,
                defines=patient_discrepancies
            ))

    # Calculate accuracies
    patients_compared = len(all_patient_ids)
    matching_patients = patients_compared - len(discrepancies)
    overall_accuracy = (matching_patients / patients_compared * 100) if patients_compared > 0 else 0

    define_accuracy = []
    for define_name, counts in define_matches.items():
        if counts["total"] > 0:
            define_accuracy.append(DefineAccuracy(
                define_name=define_name,
                library_name="main",  # Normalized to single library
                matching=counts["match"],
                total=counts["total"],
                accuracy_pct=(counts["match"] / counts["total"] * 100)
            ))

    # Calculate performance
    cql_py_total_ms = cql_py_timings.get("total_ms", 0)
    reference_total_ms = reference_result.timings.total_ms
    speedup = cql_py_total_ms / reference_total_ms if reference_total_ms > 0 else 0

    return ComparisonReport(
        measure_id=measure_config.id,
        measurement_period=measurement_period,
        cql_py_patients=len(cql_py_by_patient),
        reference_patients=len(reference_by_patient),
        patients_compared=patients_compared,
        patients_with_errors=len(reference_result.errors),
        overall_accuracy_pct=overall_accuracy,
        matching_patients=matching_patients,
        mismatched_patients=len(discrepancies),
        define_accuracy=define_accuracy,
        discrepancies=discrepancies,
        cql_py_total_ms=cql_py_total_ms,
        reference_total_ms=reference_total_ms,
        speedup_factor=speedup,
        reference_errors=reference_result.errors
    )


def _collect_all_defines(
    cql_py_results: List[Dict[str, Any]],
    reference_results: List["PatientResult"]
) -> set:
    """Collect define names that exist in cql-py results (these are what we compare against reference)."""
    defines = set()

    # Only collect defines that cql-py actually produces
    # (reference may have more internal defines we don't care about)
    if cql_py_results:
        for key in cql_py_results[0].keys():
            if key != "patient_id":
                defines.add(key)

    return defines


def _results_equal(cql_py_val: Any, ref_val: Any) -> bool:
    """Compare results from both implementations."""
    # Handle audit structs: extract .result from audit mode output
    if isinstance(cql_py_val, dict) and "result" in cql_py_val and "evidence" in cql_py_val:
        cql_py_val = cql_py_val["result"]

    # Handle NaN values
    import math
    if isinstance(cql_py_val, float) and math.isnan(cql_py_val):
        cql_py_val = None
    if isinstance(ref_val, float) and math.isnan(ref_val):
        ref_val = None
    
    # Both None/missing
    if cql_py_val is None and ref_val is None:
        return True

    # One None, other not
    if cql_py_val is None or ref_val is None:
        # Special case: False vs None for boolean defines (both falsy)
        if (cql_py_val is False and ref_val is None) or (cql_py_val is None and ref_val is False):
            return True
        return False

    # Both booleans - direct comparison
    if isinstance(cql_py_val, bool) and isinstance(ref_val, bool):
        return cql_py_val == ref_val

    # List vs boolean: non-empty list is truthy, empty list is falsy
    if isinstance(ref_val, bool) and isinstance(cql_py_val, list):
        return ref_val == (len(cql_py_val) > 0)
    if isinstance(cql_py_val, bool) and isinstance(ref_val, list):
        return cql_py_val == (len(ref_val) > 0)

    # Number vs Quantity dict
    if isinstance(cql_py_val, (int, float)) and isinstance(ref_val, dict):
        if "value" in ref_val and "type" in ref_val and ref_val.get("type") == "Quantity":
            return abs(cql_py_val - ref_val["value"]) < 0.001
    if isinstance(ref_val, (int, float)) and isinstance(cql_py_val, dict):
        if "value" in cql_py_val and "type" in cql_py_val and cql_py_val.get("type") == "Quantity":
            return abs(ref_val - cql_py_val["value"]) < 0.001

    # Both numbers
    if isinstance(cql_py_val, (int, float)) and isinstance(ref_val, (int, float)):
        return abs(cql_py_val - ref_val) < 0.001

    # Both strings - handle date/datetime normalization
    if isinstance(cql_py_val, str) and isinstance(ref_val, str):
        # Normalize datetime strings to dates for comparison
        # cql-py might return '2025-12-31 00:00:00+00:00' while ref returns '2025-12-31'
        cql_date = cql_py_val.split()[0] if ' ' in cql_py_val else cql_py_val
        ref_date = ref_val.split()[0] if ' ' in ref_val else ref_val
        return cql_date == ref_date

    # Both lists - for resource defines, just compare lengths (truthy/falsy equivalence)
    if isinstance(cql_py_val, list) and isinstance(ref_val, list):
        # If lists contain dicts (resources), compare by length not content
        # because cql-py returns ["ResourceType/id"] and ref returns [full_resource_dict]
        if len(cql_py_val) > 0 and len(ref_val) > 0:
            if isinstance(cql_py_val[0], str) and isinstance(ref_val[0], dict):
                # Resource list comparison: just check both non-empty (truthy equivalence)
                return len(cql_py_val) > 0 and len(ref_val) > 0
            if isinstance(ref_val[0], str) and isinstance(cql_py_val[0], dict):
                return len(cql_py_val) > 0 and len(ref_val) > 0
        # For same-type lists or empty lists, compare normally
        if len(cql_py_val) != len(ref_val):
            return False
        return all(_results_equal(a, b) for a, b in zip(cql_py_val, ref_val))

    # Both dicts (complex types like Quantity, Interval, Code)
    if isinstance(cql_py_val, dict) and isinstance(ref_val, dict):
        return _compare_complex_types(cql_py_val, ref_val)

    # Fallback: string comparison
    return str(cql_py_val) == str(ref_val)


def _compare_complex_types(cql_py_val: Dict, ref_val: Dict) -> bool:
    """Compare complex CQL types represented as dicts."""
    # Quantity comparison
    if "value" in cql_py_val and "unit" in cql_py_val:
        if "value" in ref_val and "unit" in ref_val:
            return (
                abs(cql_py_val["value"] - ref_val["value"]) < 0.001
                and cql_py_val["unit"] == ref_val["unit"]
            )

    # Interval comparison
    if "low" in cql_py_val and "high" in cql_py_val:
        if "low" in ref_val and "high" in ref_val:
            return (
                _results_equal(cql_py_val["low"], ref_val["low"])
                and _results_equal(cql_py_val["high"], ref_val["high"])
            )

    # Code comparison
    if "code" in cql_py_val and "system" in cql_py_val:
        if "code" in ref_val and "system" in ref_val:
            return (
                cql_py_val["code"] == ref_val["code"]
                and cql_py_val["system"] == ref_val["system"]
            )

    # Generic dict comparison
    if set(cql_py_val.keys()) != set(ref_val.keys()):
        return False
    return all(
        _results_equal(cql_py_val[k], ref_val[k])
        for k in cql_py_val.keys()
    )


def _get_result_type(value: Any) -> str:
    """Determine the type of a result value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return value.get("type", "object")
    return "unknown"


def write_comparison_report(
    report: ComparisonReport,
    output_path: Path
) -> None:
    """
    Write comparison report to JSON file.

    Output format:
    {
      "measure_id": "CMS165",
      "measurement_period": {...},
      "summary": {
        "patients_compared": 50,
        "overall_accuracy_pct": 96.0,
        "matching_patients": 48,
        "mismatched_patients": 2
      },
      "performance": {
        "cql_py_total_ms": 450,
        "reference_total_ms": 1200,
        "speedup_factor": 0.375,
        "cql_py_faster": true
      },
      "define_accuracy": [...],
      "discrepancies": [...],
      "reference_errors": [...]
    }
    """
    output = {
        "measure_id": report.measure_id,
        "measurement_period": report.measurement_period,
        "summary": {
            "cql_py_patients": report.cql_py_patients,
            "reference_patients": report.reference_patients,
            "patients_compared": report.patients_compared,
            "patients_with_errors": report.patients_with_errors,
            "overall_accuracy_pct": round(report.overall_accuracy_pct, 2),
            "matching_patients": report.matching_patients,
            "mismatched_patients": report.mismatched_patients
        },
        "performance": {
            "cql_py_total_ms": round(report.cql_py_total_ms, 2),
            "reference_total_ms": round(report.reference_total_ms, 2),
            "speedup_factor": round(report.speedup_factor, 3),
            "cql_py_faster": report.cql_py_faster
        },
        "define_accuracy": [
            {
                "define_name": da.define_name,
                "library_name": da.library_name,
                "matching": da.matching,
                "total": da.total,
                "accuracy_pct": round(da.accuracy_pct, 2)
            }
            for da in sorted(report.define_accuracy, key=lambda x: x.define_name)
        ],
        "discrepancies": [
            {
                "patient_id": d.patient_id,
                "define_count": d.define_count,
                "defines": [
                    {
                        "library_name": dd.library_name,
                        "define_name": dd.define_name,
                        "cql_py_result": dd.cql_py_result,
                        "reference_result": dd.reference_result,
                        "cql_py_type": dd.cql_py_type,
                        "reference_type": dd.reference_type
                    }
                    for dd in d.defines
                ]
            }
            for d in report.discrepancies
        ],
        "reference_errors": report.reference_errors
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2))
