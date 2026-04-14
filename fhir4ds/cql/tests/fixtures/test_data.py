"""Test fixtures for context-aware translation tests."""

import json
from pathlib import Path
from typing import Dict, Any


def load_fixture_data() -> Dict[str, Any]:
    """Load fixture data from patients.json."""
    fixture_path = Path(__file__).parent / "patients.json"
    with open(fixture_path) as f:
        return json.load(f)


def get_expected_results() -> Dict[str, Dict[str, Any]]:
    """Expected results for test cases."""
    return {
        "exists_diabetes": {
            "P1": False,
            "P2": True,
            "P3": True,
        },
        "count_diabetes": {
            "P1": 0,
            "P2": 1,
            "P3": 2,  # Only diabetes, not hypertension
        },
        "count_all_conditions": {
            "P1": 0,
            "P2": 1,
            "P3": 3,  # All conditions
        },
        "first_diabetes": {
            "P2": "C1",
            "P3": "C2",  # Earliest by onset_date (2019-03-20)
        },
        "has_multiple_hba1c": {
            "P1": False,
            "P2": False,
            "P3": True,
        },
    }


def get_patient_ids() -> list:
    """Get list of test patient IDs."""
    return ["P1", "P2", "P3"]


def get_resource_counts() -> Dict[str, Dict[str, int]]:
    """Get expected resource counts per patient."""
    return {
        "P1": {"Condition": 0, "Observation": 0},
        "P2": {"Condition": 1, "Observation": 1},
        "P3": {"Condition": 3, "Observation": 2},
    }
