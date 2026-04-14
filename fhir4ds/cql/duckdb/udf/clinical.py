"""
Vectorized CQL Clinical Operator UDFs

Implements CQL clinical operators:
- Latest(resources, date_path) - Returns resource with most recent date
- Earliest(resources, date_path) - Returns resource with oldest date

Supports both scalar (row-by-row) and Arrow vectorized implementations.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Any

import orjson
import pyarrow as pa

if TYPE_CHECKING:
    import duckdb


import logging

_logger = logging.getLogger(__name__)
# Feature flag for rollback
_USE_ARROW = os.environ.get("CQL_USE_ARROW_UDFS", "1") == "1"


def _arrow_scalar_as_py(scalar: pa.Scalar) -> Any:
    """Convert an Arrow scalar to a Python value without batch materialization."""
    return scalar.as_py() if scalar.is_valid else None


def _extract_date(resource: dict, path: str) -> datetime | None:
    """Extract date from resource at given path.

    Args:
        resource: Parsed FHIR resource as dict
        path: Path to the date field (e.g., "effectiveDateTime", "onsetDateTime")

    Returns:
        datetime object or None if extraction fails
    """
    try:
        value = resource.get(path)
        if value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        _logger.warning("_extract_date failed: %s", e)
    return None


def _parse_resource(resource: Any) -> dict | None:
    """Parse a FHIR resource from JSON string or return dict as-is.

    Args:
        resource: JSON string or dict

    Returns:
        Parsed dict or None on failure
    """
    if resource is None:
        return None
    if isinstance(resource, dict):
        return resource
    if isinstance(resource, str):
        try:
            return orjson.loads(resource)
        except orjson.JSONDecodeError as e:
            _logger.warning("_parse_resource failed: %s", e)
            return None
    return None


def _select_resource_by_date(
    resources: list[Any] | None,
    date_path: str | None,
    *,
    select_latest: bool,
) -> str | None:
    """Return the resource with the selected boundary date for the given path."""
    if resources is None or not date_path:
        return None

    selected_resource = None
    selected_date = None

    for resource in resources:
        parsed = _parse_resource(resource)
        if not parsed:
            continue

        date_val = _extract_date(parsed, date_path)
        if not date_val:
            continue

        if selected_date is None:
            selected_date = date_val
            selected_resource = parsed
            continue

        if select_latest and date_val > selected_date:
            selected_date = date_val
            selected_resource = parsed
        elif not select_latest and date_val < selected_date:
            selected_date = date_val
            selected_resource = parsed

    if selected_resource is None:
        return None

    return orjson.dumps(selected_resource).decode("utf-8")


# ========================================
# Scalar versions (fallback)
# ========================================

def latest_scalar(resources: list[Any] | None, date_path: str | None) -> str | None:
    """CQL Latest() - scalar version.

    Returns the resource with the most recent date at the given path.

    Args:
        resources: List of FHIR resources (JSON strings or dicts)
        date_path: Path to the date field (e.g., "effectiveDateTime")

    Returns:
        JSON string of the resource with the latest date, or None
    """
    return _select_resource_by_date(resources, date_path, select_latest=True)


def earliest_scalar(resources: list[Any] | None, date_path: str | None) -> str | None:
    """CQL Earliest() - scalar version.

    Returns the resource with the oldest (earliest) date at the given path.

    Args:
        resources: List of FHIR resources (JSON strings or dicts)
        date_path: Path to the date field (e.g., "effectiveDateTime")

    Returns:
        JSON string of the resource with the earliest date, or None
    """
    return _select_resource_by_date(resources, date_path, select_latest=False)


# ========================================
# Arrow vectorized versions
# ========================================

def latest_arrow(
    resources_array: pa.ListArray,
    date_paths: pa.StringArray
) -> pa.StringArray:
    """CQL Latest() - vectorized Arrow version.

    Args:
        resources_array: Array of lists of FHIR resources (as JSON strings or structs)
        date_paths: Array of date field paths

    Returns:
        Array of JSON strings with the latest resource per row
    """
    results = [
        _select_resource_by_date(
            _arrow_scalar_as_py(resources_scalar),
            _arrow_scalar_as_py(date_path_scalar),
            select_latest=True,
        )
        for resources_scalar, date_path_scalar in zip(resources_array, date_paths)
    ]

    return pa.array(results, type=pa.string())


def earliest_arrow(
    resources_array: pa.ListArray,
    date_paths: pa.StringArray
) -> pa.StringArray:
    """CQL Earliest() - vectorized Arrow version.

    Args:
        resources_array: Array of lists of FHIR resources (as JSON strings or structs)
        date_paths: Array of date field paths

    Returns:
        Array of JSON strings with the earliest resource per row
    """
    results = [
        _select_resource_by_date(
            _arrow_scalar_as_py(resources_scalar),
            _arrow_scalar_as_py(date_path_scalar),
            select_latest=False,
        )
        for resources_scalar, date_path_scalar in zip(resources_array, date_paths)
    ]

    return pa.array(results, type=pa.string())


# ========================================
# Claim principal diagnosis extraction
# ========================================

_PRINCIPAL_DIAG_SYSTEM = "http://terminology.hl7.org/CodeSystem/ex-diagnosistype"


def _claim_principal_diagnosis_scalar(
    claim_resource: str | None,
    encounter_id: str | None,
) -> str | None:
    """Extract the principal diagnosis from a Claim for a specific encounter.

    Implements the CQL ``claimDiagnosis`` → ``principalDiagnosis`` chain:
    1. Find claim items whose encounter reference ends with *encounter_id*.
    2. Collect their ``diagnosisSequence`` values.
    3. Find diagnosis entries whose ``sequence`` is in that set **and**
       whose ``type`` includes code ``principal`` from the ex-diagnosistype
       code system.
    4. Return the first such diagnosis entry as JSON (or ``None``).

    Args:
        claim_resource: Claim FHIR resource as JSON string.
        encounter_id: The target Encounter resource ID.

    Returns:
        JSON string of the matching diagnosis BackboneElement, or None.
    """
    if not claim_resource or not encounter_id:
        return None

    claim = _parse_resource(claim_resource)
    if claim is None:
        return None

    # Step 1 & 2: collect diagnosisSequence values from matching items
    diag_seqs: set[int] = set()
    for item in claim.get("item", []):
        for enc_ref in item.get("encounter", []):
            ref_str = enc_ref.get("reference", "")
            if ref_str.endswith(encounter_id):
                for seq in item.get("diagnosisSequence", []):
                    diag_seqs.add(seq)

    if not diag_seqs:
        return None

    # Step 3: find principal diagnosis with matching sequence
    for diag in claim.get("diagnosis", []):
        seq = diag.get("sequence")
        if seq not in diag_seqs:
            continue
        # Check for principal type
        for type_cc in diag.get("type", []):
            for coding in type_cc.get("coding", []):
                if (
                    coding.get("system") == _PRINCIPAL_DIAG_SYSTEM
                    and coding.get("code") == "principal"
                ):
                    return orjson.dumps(diag).decode("utf-8")

    return None


def _claim_principal_diagnosis_arrow(
    claim_resources: pa.StringArray,
    encounter_ids: pa.StringArray,
) -> pa.StringArray:
    """Vectorized Arrow version of claim_principal_diagnosis."""
    results = [
        _claim_principal_diagnosis_scalar(
            _arrow_scalar_as_py(claim_scalar),
            _arrow_scalar_as_py(encounter_scalar),
        )
        for claim_scalar, encounter_scalar in zip(claim_resources, encounter_ids)
    ]
    return pa.array(results, type=pa.string())


# ========================================
# Claim principal procedure extraction
# ========================================

_PRINCIPAL_PROC_SYSTEM = "http://terminology.hl7.org/CodeSystem/ex-procedure-type"


def _claim_principal_procedure_scalar(
    claim_resource: str | None,
    encounter_id: str | None,
) -> str | None:
    """Extract the principal procedure from a Claim for a specific encounter.

    Mirrors ``claim_principal_diagnosis`` but for the ``Claim.procedure``
    backbone element.  Used by the CQL ``principalProcedure`` fluent function.

    Args:
        claim_resource: Claim FHIR resource as JSON string.
        encounter_id: The target Encounter resource ID.

    Returns:
        JSON string of the matching procedure BackboneElement, or None.
    """
    if not claim_resource or not encounter_id:
        return None

    claim = _parse_resource(claim_resource)
    if claim is None:
        return None

    # Collect procedureSequence values from items matching the encounter
    proc_seqs: set[int] = set()
    for item in claim.get("item", []):
        for enc_ref in item.get("encounter", []):
            ref_str = enc_ref.get("reference", "")
            if ref_str.endswith(encounter_id):
                for seq in item.get("procedureSequence", []):
                    proc_seqs.add(seq)

    if not proc_seqs:
        return None

    for proc in claim.get("procedure", []):
        seq = proc.get("sequence")
        if seq not in proc_seqs:
            continue
        for type_cc in proc.get("type", []):
            for coding in type_cc.get("coding", []):
                if (
                    coding.get("system") == _PRINCIPAL_PROC_SYSTEM
                    and coding.get("code") == "primary"
                ):
                    return orjson.dumps(proc).decode("utf-8")

    return None


def _claim_principal_procedure_arrow(
    claim_resources: pa.StringArray,
    encounter_ids: pa.StringArray,
) -> pa.StringArray:
    """Vectorized Arrow version of claim_principal_procedure."""
    results = [
        _claim_principal_procedure_scalar(
            _arrow_scalar_as_py(claim_scalar),
            _arrow_scalar_as_py(encounter_scalar),
        )
        for claim_scalar, encounter_scalar in zip(claim_resources, encounter_ids)
    ]
    return pa.array(results, type=pa.string())


# ========================================
# Registration with feature flag
# ========================================

def registerClinicalUdfs(con: "duckdb.DuckDBPyConnection") -> None:
    """Register clinical UDFs with Arrow or scalar based on feature flag."""
    if _USE_ARROW:
        # Register Arrow versions with proper casing
        # null_handling="special" needed because Arrow functions handle NULL values internally
        con.create_function(
            "Latest",
            latest_arrow,
            type="arrow",
            return_type="VARCHAR",
            null_handling="special"
        )
        con.create_function(
            "Earliest",
            earliest_arrow,
            type="arrow",
            return_type="VARCHAR",
            null_handling="special"
        )
        con.create_function(
            "claim_principal_diagnosis",
            _claim_principal_diagnosis_arrow,
            type="arrow",
            return_type="VARCHAR",
            null_handling="special",
        )
        con.create_function(
            "claim_principal_procedure",
            _claim_principal_procedure_arrow,
            type="arrow",
            return_type="VARCHAR",
            null_handling="special",
        )
    else:
        # Scalar versions
        con.create_function("Latest", latest_scalar, null_handling="special")
        con.create_function("Earliest", earliest_scalar, null_handling="special")
        con.create_function(
            "claim_principal_diagnosis",
            _claim_principal_diagnosis_scalar,
            null_handling="special",
        )
        con.create_function(
            "claim_principal_procedure",
            _claim_principal_procedure_scalar,
            null_handling="special",
        )


# Legacy aliases for backward compatibility
Latest = latest_scalar
Earliest = earliest_scalar


__all__ = [
    # Feature flag
    "_USE_ARROW",
    # Registration
    "registerClinicalUdfs",
    # Scalar functions
    "latest_scalar",
    "earliest_scalar",
    "_claim_principal_diagnosis_scalar",
    # Arrow functions
    "latest_arrow",
    "earliest_arrow",
    "_claim_principal_diagnosis_arrow",
    # Legacy aliases
    "Latest",
    "Earliest",
]
