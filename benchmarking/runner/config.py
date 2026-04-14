"""
Measure configuration and paths.
"""
from pathlib import Path
from typing import List
from dataclasses import dataclass

# Base paths
BENCHMARKING_DIR = Path(__file__).parent.parent
DATA_DIR = BENCHMARKING_DIR / "data"
OUTPUT_DIR = BENCHMARKING_DIR / "output"

# Output subdirs
OUTPUT_CQL_PY_DIR = OUTPUT_DIR / "cql-py"
OUTPUT_CLINICAL_REASONING_DIR = OUTPUT_DIR / "clinical-reasoning"

# Suite roots (now inside data/)
SUITE_2025_DIR = DATA_DIR / "ecqm-content-qicore-2025"
SUITE_2026_DIR = DATA_DIR / "dqm-content-qicore-2026"

# Default suite (2025)
SUBMODULE_DIR = SUITE_2025_DIR

# Shared paths (default to 2025 suite)
CQL_DIR = SUBMODULE_DIR / "input" / "cql"
VALUESET_DIR = SUBMODULE_DIR / "input" / "vocabulary" / "valueset" / "external"
VALIDATOR_VALUESET_DIR = BENCHMARKING_DIR / "cql-execution-validator" / "output" / "valuesets"
SUPPLEMENTAL_VALUESET_DIR = DATA_DIR / "valuesets"
TESTS_DIR = SUBMODULE_DIR / "input" / "tests" / "measure"
BUNDLE_DIR = SUBMODULE_DIR / "bundles" / "measure"


def get_suite_paths(suite: str = "2025") -> dict:
    """
    Return path configuration for a specific content suite year.

    Args:
        suite: "2025" (ecqm-content-qicore-2025) or "2026" (dqm-content-qicore-2026)

    Returns:
        Dict with keys: suite_dir, cql_dir, valueset_dir, tests_dir, bundle_dir
    """
    if suite == "2026":
        suite_dir = SUITE_2026_DIR
    else:
        suite_dir = SUITE_2025_DIR
    return {
        "suite_dir": suite_dir,
        "cql_dir": suite_dir / "input" / "cql",
        "valueset_dir": suite_dir / "input" / "vocabulary" / "valueset" / "external",
        "tests_dir": suite_dir / "input" / "tests" / "measure",
        "bundle_dir": suite_dir / "bundles" / "measure",
    }


# Measures that may fail and should be skipped
SKIP_ON_FAILURE = {
    "CMS139",   # Not in submodule
    "CMS1218",  # cql-py translator infinite loop (50+ min at 99% CPU)
}

# Known failures with documented root causes (all external test-data issues).
# These are tracked separately in the benchmark summary so CI can assert 42/47.
# Each entry maps measure ID -> { mismatches: int, reason: str, upstream: str }.
KNOWN_FAILURES = {
    "CMS135": {
        "mismatches": 3,
        "reason": "MADIE-2124: MeasureReport has denominator-exception=0 for DENEXCEPPass test cases",
        "upstream": "https://oncprojectracking.healthit.gov/support/projects/MADIE/issues/MADIE-2124",
    },
    "CMS145": {
        "mismatches": 2,
        "reason": "MADIE-2124: MeasureReport has denominator-exception=0 for DENEXCEPPass test cases",
        "upstream": "https://oncprojectracking.healthit.gov/support/projects/MADIE/issues/MADIE-2124",
    },
    "CMS996": {
        "mismatches": 2,
        "reason": "Valueset 2.16.840.1.113883.3.3157.4056 (Major Surgical Procedure) absent from submodule",
        "upstream": "https://github.com/cqframework/ecqm-content-qicore-2025",
    },
    "CMS157": {
        "mismatches": 3,
        "reason": "Test data uses 2025 dates but measurement period is 2026",
        "upstream": "https://github.com/cqframework/ecqm-content-qicore-2025",
    },
    "CMS1017": {
        "mismatches": 3,
        "reason": "Test data bugs: non-UUID IDs, contradictory MeasureReports, missing valueset codes",
        "upstream": "https://github.com/cqframework/ecqm-content-qicore-2025",
    },
}

@dataclass
class MeasureConfig:
    """Configuration for a single measure."""
    id: str                              # e.g., "CMS165"
    name: str                            # e.g., "Controlling High Blood Pressure"
    cql_path: Path                       # Path to main CQL file
    test_dir: Path                       # Directory with test bundles
    include_paths: List[Path]            # Paths for included libraries
    valueset_paths: List[Path]           # Paths for ValueSets
    population_definitions: List[str]    # e.g., ["Initial Population", "Denominator", "Numerator"]
