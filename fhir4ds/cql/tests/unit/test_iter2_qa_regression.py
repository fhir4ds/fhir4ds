"""Regression tests for iteration-2 QA findings.

QA-002 — intervalIncludes precision mismatch (HIGH):
    Confirms the CQL §18 / CqlIntervalOperatorsTest.xml
    ``DateTimeIncludedInNull`` precedent: when two temporal bounds share
    the same wall-clock value but differ in precision (e.g. millisecond
    vs second), the comparison is uncertain and propagates as NULL.
    This is the spec-compliant behavior, not a bug.

QA-004 — ``exists from [Resource].field C where ...`` (LOW):
    The unsupported retrieve-then-navigate query source form must raise
    a typed TranslationError early instead of emitting SQL that produces
    an opaque DuckDB Binder Error at execution time.
"""

import pytest

from ...errors import TranslationError
from ...parser import parse_cql
from ...translator import CQLToSQLTranslator


def _translate(cql: str) -> str:
    ast = parse_cql(cql)
    translator = CQLToSQLTranslator()
    return translator.translate_library_to_sql(ast)


class TestIntervalPrecisionAwareCompare:
    """QA-002: confirm precision mismatch returns None (uncertain).

    Per CQL §18.4 and the official CQL conformance test
    ``DateTimeIncludedInNull`` (CqlIntervalOperatorsTest.xml:914-918),
    when two temporal bounds share the same wall-clock value but differ
    in precision, the comparison is uncertain → NULL — not certain-equal
    as the original QA report conjectured.
    """

    def test_precision_aware_compare_returns_none_for_ms_vs_second(self):
        """When precisions differ, the helper returns None (uncertain)."""
        from ...duckdb.udf.interval import _precision_aware_compare

        result = _precision_aware_compare(
            "2026-01-01T00:00:00.000",
            "2026-01-01T00:00:00",
        )
        assert result is None

    def test_precision_aware_compare_returns_zero_for_same_precision(self):
        """Same precision comparisons remain certain."""
        from ...duckdb.udf.interval import _precision_aware_compare

        result = _precision_aware_compare(
            "2026-01-01T00:00:00",
            "2026-01-01T00:00:00",
        )
        assert result == 0

    def test_precision_aware_compare_returns_zero_for_same_ms_precision(self):
        """Millisecond-precision bounds compare certain-equal when identical."""
        from ...duckdb.udf.interval import _precision_aware_compare

        result = _precision_aware_compare(
            "2026-01-01T00:00:00.000",
            "2026-01-01T00:00:00.000",
        )
        assert result == 0


class TestRetrieveAsQuerySourceRaisesTranslationError:
    """QA-004: ``[Resource].field`` query source must fail with a typed error."""

    def test_exists_from_retrieve_field_raises_translation_error(self):
        """``exists from [Observation].code C where C.code = 'X'`` raises."""
        cql = """
        library Q4 version '1.0.0'
        using FHIR version '4.0.1'
        context Patient
        define "T6":
          exists from [Observation].code C where C.code = '12345-6'
        """
        with pytest.raises(TranslationError, match=r"\[Resource\]\.field"):
            _translate(cql)

    def test_retrieve_field_query_source_error_mentions_rewrite(self):
        """Error message guides the author toward the supported form."""
        cql = """
        library Q4 version '1.0.0'
        using FHIR version '4.0.1'
        context Patient
        define "T6":
          exists from [Condition].code C where C.code = '72166-2'
        """
        with pytest.raises(TranslationError) as exc_info:
            _translate(cql)
        # Must mention the resource type and the rewrite suggestion
        message = str(exc_info.value)
        assert "Condition" in message
        assert "rewrite" in message.lower() or "where" in message.lower()
