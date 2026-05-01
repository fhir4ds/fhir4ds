"""Smoke tests for CI gate — measure SQL generation quality assertions."""
import re
import time
from pathlib import Path

import pytest

from ...parser import parse_cql, Library
from ...translator import CQLToSQLTranslator


_REPO_ROOT = Path(__file__).resolve().parents[4]
_CQL_DIR = _REPO_ROOT / "tests" / "data" / "ecqm-content-qicore-2025" / "input" / "cql"

MEASURES = [
    ("CMS165", str(_CQL_DIR / "CMS165FHIRControllingHighBloodPressure.cql")),
    ("CMS124", str(_CQL_DIR / "CMS124FHIRCervicalCancerScreening.cql")),
    ("CMS144", str(_CQL_DIR / "CMS144FHIRHFBetaBlockerTherapyforLVSD.cql")),
]

# Thresholds (tighten over time as correlated subquery optimizations land)
MAX_CORRELATED_SUBQUERIES = 100  # Safety net; current CMS165=70, CMS124=36, CMS144=26
MAX_LIST_FILTER_OCCURRENCES = 0
MAX_GENERATION_TIME_SECONDS = 30


class TestMeasureSmokeCI:
    """CI gate: measure SQL generation quality."""

    @pytest.fixture(params=MEASURES, ids=[m[0] for m in MEASURES])
    def measure_sql(self, request):
        """Generate SQL for a measure and return (name, sql, elapsed)."""
        name, cql_path = request.param
        from pathlib import Path
        from ...errors import TranslationError

        cql_text = Path(cql_path).read_text()
        library = parse_cql(cql_text)
        translator = CQLToSQLTranslator()
        start = time.monotonic()
        try:
            sql = translator.translate_library_to_sql(library)
        except TranslationError as e:
            if "no library_loader" in str(e):
                pytest.skip(f"{name}: requires library_loader for include resolution")
            raise
        elapsed = time.monotonic() - start
        return name, sql, elapsed

    @pytest.mark.integration
    def test_no_list_filter_patterns(self, measure_sql):
        """No list_filter(..., lambda) patterns in output SQL."""
        name, sql, _ = measure_sql
        count = sql.lower().count("list_filter")
        assert count <= MAX_LIST_FILTER_OCCURRENCES, (
            f"{name}: found {count} list_filter occurrences (max {MAX_LIST_FILTER_OCCURRENCES})"
        )

    @pytest.mark.integration
    def test_correlated_subquery_threshold(self, measure_sql):
        """Correlated subquery count below threshold."""
        name, sql, _ = measure_sql
        # Count correlated subquery indicators
        # Heuristic: count nested SELECT...WHERE patterns referencing outer aliases
        correlated_count = len(re.findall(
            r'SELECT\s.*?\bFROM\b.*?\bWHERE\b.*?\b(patient_id|p\.patient_id)\b',
            sql, re.IGNORECASE | re.DOTALL
        ))
        assert correlated_count <= MAX_CORRELATED_SUBQUERIES, (
            f"{name}: found {correlated_count} correlated subqueries (max {MAX_CORRELATED_SUBQUERIES})"
        )

    @pytest.mark.integration
    def test_generation_time(self, measure_sql):
        """SQL generation completes within time budget."""
        name, _, elapsed = measure_sql
        assert elapsed <= MAX_GENERATION_TIME_SECONDS, (
            f"{name}: generation took {elapsed:.1f}s (max {MAX_GENERATION_TIME_SECONDS}s)"
        )

    @pytest.mark.integration
    def test_sql_not_empty(self, measure_sql):
        """Generated SQL is non-trivial."""
        name, sql, _ = measure_sql
        assert len(sql) > 500, f"{name}: SQL too short ({len(sql)} chars)"
        assert "WITH" in sql.upper(), f"{name}: missing WITH clause (no CTEs)"
