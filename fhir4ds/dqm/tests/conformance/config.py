"""
Measure configuration and paths.
"""
from dataclasses import dataclass
from pathlib import Path

# Base paths
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent.parent.absolute()
TESTS_ROOT = WORKSPACE_ROOT / "tests"
DATA_DIR = TESTS_ROOT / "data"
BENCHMARKING_DIR = WORKSPACE_ROOT / "benchmarks"

# Conformance runner output (per-measure SQL, CSV, stats)
OUTPUT_CQL_PY_DIR = TESTS_ROOT / "output"

# Suite roots (now inside data/)
SUITE_2025_DIR = DATA_DIR / "ecqm-content-qicore-2025"
SUITE_2026_DIR = DATA_DIR / "dqm-content-qicore-2026"
SUITE_CMS_2025_DIR = DATA_DIR / "dqm-content-cms-2025"

# Canonical suite NAMES (what users type) are independent of the submodule
# directory names. `qi-core` is ecqm-content-qicore-2025 and `us-core` is
# dqm-content-cms-2025 (the CMS US Core suite). The old year-style spellings
# stay accepted so existing scripts, CI jobs and docs keep working.
# Names are VERSIONED because more content releases are expected: a bare
# "qi-core" would silently mean a different suite next year.
SUITE_QI_CORE_2025 = "qi-core-2025"
SUITE_US_CORE_2025 = "us-core-2025"
SUITE_QI_CORE_2026 = "qi-core-2026"

CANONICAL_SUITES = (SUITE_QI_CORE_2025, SUITE_US_CORE_2025, SUITE_QI_CORE_2026)

_SUITE_ALIASES = {
    "qi-core-2025": SUITE_QI_CORE_2025,
    "us-core-2025": SUITE_US_CORE_2025,
    "qi-core-2026": SUITE_QI_CORE_2026,
    # legacy (pre-rename) spellings
    "2025": SUITE_QI_CORE_2025,
    "cms2025": SUITE_US_CORE_2025,
    "2026": SUITE_QI_CORE_2026,
    # unversioned aliases introduced briefly during the rename; kept so a
    # script written against them does not silently break. They mean the 2025
    # release and are NOT a "latest" selector.
    "qi-core": SUITE_QI_CORE_2025,
    "us-core": SUITE_US_CORE_2025,
}


def normalize_suite(suite: str | None) -> str:
    """Map a suite name (canonical or legacy) to its canonical spelling.

    Legacy year spellings ('2025', 'cms2025', '2026') are accepted so that
    existing invocations and the historical docs keep working.
    """
    if suite is None:
        return SUITE_QI_CORE_2025
    key = str(suite).strip().lower()
    try:
        return _SUITE_ALIASES[key]
    except KeyError:
        raise ValueError(
            f"Unknown suite {suite!r}. Expected one of {list(CANONICAL_SUITES)} "
            f"or a legacy alias {sorted(_SUITE_ALIASES)}."
        ) from None

# Default suite (2025)
SUBMODULE_DIR = SUITE_2025_DIR

# Shared paths (default to 2025 suite)
CQL_DIR = SUBMODULE_DIR / "input" / "cql"
VALUESET_DIR = SUBMODULE_DIR / "input" / "vocabulary" / "valueset" / "external"
VALIDATOR_VALUESET_DIR = BENCHMARKING_DIR / "cql-execution-validator" / "output" / "valuesets"
SUPPLEMENTAL_VALUESET_DIR = DATA_DIR / "valuesets"
TESTS_DIR = SUBMODULE_DIR / "input" / "tests" / "measure"
BUNDLE_DIR = SUBMODULE_DIR / "bundles" / "measure"


def get_suite_paths(suite: str = SUITE_QI_CORE_2025) -> dict:
    """
    Return path configuration for a content suite.

    Args:
        suite: canonical name — "qi-core-2025" (ecqm-content-qicore-2025,
            default), "us-core-2025" (dqm-content-cms-2025, the CMS US Core
            measures), or "qi-core-2026" (dqm-content-qicore-2026). Legacy
            spellings "2025", "cms2025", "2026" and the unversioned
            "qi-core"/"us-core" are accepted as aliases.

    Returns:
        Dict with keys: suite_dir, cql_dir, valueset_dir, tests_dir, bundle_dir
    """
    suite_dir = {
        SUITE_QI_CORE_2025: SUITE_2025_DIR,
        SUITE_US_CORE_2025: SUITE_CMS_2025_DIR,
        SUITE_QI_CORE_2026: SUITE_2026_DIR,
    }[normalize_suite(suite)]
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
}

# Known failures with documented root causes (all external test-data issues).
# These are tracked separately in the benchmark summary.
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
        "mismatches": 0,
        "reason": "Fixed: cqlSameAsP now handles interval JSON; Condition profiles and valueset codes corrected in test data",
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
    include_paths: list[Path]            # Paths for included libraries
    valueset_paths: list[Path]           # Paths for ValueSets
    population_definitions: list[str]    # e.g., ["Initial Population", "Denominator", "Numerator"]
