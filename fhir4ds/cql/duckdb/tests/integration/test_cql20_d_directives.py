"""CQL 2.0 directives + parameter enhancements (chunk CQL20-D).

Covers: the ``#DefaultComparisonPrecision`` directive (FHIR-41326) including
``default included libraries`` propagation machinery, parameter constraints
(FHIR-48682, ``@constraint``/``@message`` annotations with error/warning
severities), and parameter binding in includes (FHIR-33126, ``include ...
bind { P: expr }``). Ground truth: cql.hl7.org/03-developersguide.html
#directives / #defaultcomparisonprecision / #parameter-constraints
/#parameter-binding.

End-to-end include-inline behavior (child define SQL appearing inside the
parent's) is exercised by the DQM conformance suites on real eCQM includes;
here the propagation machinery is pinned at the mechanism level.
"""

from __future__ import annotations

import logging

import duckdb
import pytest

from fhir4ds.cql.errors import ParseError, TranslationError
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator.translator import CQLToSQLTranslator


def _registered_connection():
    from fhir4ds.cql.duckdb.extension import register

    con = duckdb.connect()
    register(con)
    return con


def _translate(cql: str, con=None):
    translator = (
        CQLToSQLTranslator(connection=con) if con is not None else CQLToSQLTranslator()
    )
    result = translator.translate_library(parse_cql(cql))
    return translator, result


def _render(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return " ".join(
            v.to_sql() if hasattr(v, "to_sql") else str(v) for v in result.values()
        )
    return result.to_sql() if hasattr(result, "to_sql") else str(result)


class TestDirectives:
    def test_default_comparison_precision_changes_lowering(self) -> None:
        body = (
            "library X version '1.0'\nusing FHIR version '4.0.1'\n"
            "context Patient\ndefine T: @2024-01-01T10:30:00 before "
            "@2024-01-01T10:45:59\n"
        )
        _, plain = _translate(body)
        assert "cqlBeforeP" not in _render(plain)  # no precision, no directive

        _, directed = _translate("#DefaultComparisonPrecision: minutes\n" + body)
        assert "cqlBeforeP" in _render(directed)  # precision-aware lowering

    def test_directive_normalized_value(self) -> None:
        lib = parse_cql(
            "#DefaultComparisonPrecision: minutes default included libraries\n"
            "library X version '1.0'\ncontext Patient\ndefine T: 1\n"
        )
        directive = lib.directives[0]
        assert directive.name == "DefaultComparisonPrecision"
        assert directive.value == "minute"  # normalized singular
        assert directive.inclusion_behavior is not None

    def test_unknown_directive_rejected(self) -> None:
        with pytest.raises(ParseError):
            parse_cql(
                "#BogusDirective: xyz\nlibrary X version '1.0'\n"
                "context Patient\ndefine T: 1\n"
            )

    def test_directive_propagation_machinery(self) -> None:
        # Mechanism: a child translator constructed WITH an inherited
        # precision directive lowers precision-less comparisons
        # precision-aware; the parent's `default included libraries` clause
        # is what feeds that inheritance (end-to-end include-inline coverage
        # lives in the DQM conformance suites on real eCQM includes).
        child_body = (
            "library Child version '1.0'\nusing FHIR version '4.0.1'\n"
            "context Patient\ndefine C: @2024-01-01T10:30:00 before "
            "@2024-01-01T10:45:59\n"
        )
        _, plain = _translate(child_body)
        assert "cqlBeforeP" not in _render(plain)

        tr = CQLToSQLTranslator()
        tr._inherited_comparison_precision = ("minute", "default")
        result = tr.translate_library(parse_cql(child_body))
        assert "cqlBeforeP" in _render(result)


class TestParameterConstraints:
    def _lib(self, default: str) -> str:
        return (
            "library C version '1.0'\nusing FHIR version '4.0.1'\n"
            f'parameter "Measurement Period" Interval<DateTime> default {default}\n'
            "/*\n@constraint: error\n"
            "@message: Measurement period must be a year\n*/\n"
            'define IsYearly: start of "Measurement Period" same year as '
            'end of "Measurement Period"\n'
            "context Patient\ndefine T: 1\n"
        )

    def test_satisfied_constraint_translates(self) -> None:
        con = _registered_connection()
        try:
            _translate(self._lib("Interval[@2024-01-01, @2024-12-31]"), con)
        finally:
            con.close()

    def test_violated_error_constraint_raises(self) -> None:
        con = _registered_connection()
        try:
            with pytest.raises(TranslationError, match="[Yy]ear"):
                _translate(self._lib("Interval[@2024-01-01, @2025-12-31]"), con)
        finally:
            con.close()

    def test_violated_warning_constraint_logs_not_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        lib = self._lib("Interval[@2024-01-01, @2025-12-31]").replace(
            "@constraint: error", "@constraint: warning"
        )
        con = _registered_connection()
        try:
            with caplog.at_level(logging.WARNING):
                _translate(lib, con)  # must NOT raise
        finally:
            con.close()
        assert any("year" in r.message.lower() for r in caplog.records)


class TestParameterBindingInIncludes:
    def test_bind_parses_into_ast(self) -> None:
        host = parse_cql(
            "library Host version '1.0'\nusing FHIR version '4.0.1'\n"
            "include Child called C bind { AsOf: @2024-07-01 }\n"
            "context Patient\ndefine T: 1\n"
        )
        inc = host.includes[0]
        bound = getattr(inc, "bind", None) or getattr(inc, "bindings", None)
        assert bound is not None
        assert "AsOf" in bound

    def test_bind_expression_lowering_does_not_crash(self) -> None:
        # Pins the _translate_expression -> translate_expression fix: bind
        # expression lowering must use the public method.
        host = parse_cql(
            "library Host version '1.0'\nusing FHIR version '4.0.1'\n"
            "include Child called C bind { AsOf: @2024-07-01 }\n"
            "context Patient\ndefine T: 1\n"
        )
        child = parse_cql(
            "library Child version '1.0'\nusing FHIR version '4.0.1'\n"
            'parameter "AsOf" DateTime\ncontext Patient\ndefine C: 1\n'
        )
        inc = host.includes[0]
        tr = CQLToSQLTranslator()
        assert hasattr(tr, "_translate_include_bindings")
        # Lowering the bind map (bind expressions evaluate in the INCLUDING
        # library's context per spec) must succeed for a literal.
        bindings = tr._translate_include_bindings(inc, child, host)
        assert "AsOf" in bindings


class TestAmux152Batch3:
    """AMUX-152 batch 3: include-cache bind key (#6) and context reset (#16)."""

    def test_distinct_bind_clauses_do_not_share_cached_translation_amux152_6(self):
        """AMUX-152 #6 (FHIR-33126): two includes of the SAME library with
        DIFFERENT bind clauses must not share one cached translation — the
        cache key must include the include's own bind clause, or the second
        include silently reuses the first's bound expressions."""
        child = parse_cql(
            "library Child version '1.0'\nusing FHIR version '4.0.1'\n"
            'parameter "AsOf" DateTime\ncontext Patient\ndefine Mark: AsOf\n'
        )
        libs = {"Child": child}

        def loader(name):
            return libs.get(name)

        parent = parse_cql(
            "library Host version '1.0'\nusing FHIR version '4.0.1'\n"
            "include Child called C1 bind { AsOf: @2024-07-01 }\n"
            "include Child called C2 bind { AsOf: @2025-03-01 }\n"
            "context Patient\n"
            "define A: C1.Mark\ndefine B: C2.Mark\n"
        )
        translator = CQLToSQLTranslator(library_loader=loader)
        translator.translate_library(parent)
        a_sql = translator._included_definitions["C1.Mark"].to_sql()
        b_sql = translator._included_definitions["C2.Mark"].to_sql()
        assert "2024-07-01" in a_sql and "2025-03-01" not in a_sql, a_sql
        assert "2025-03-01" in b_sql and "2024-07-01" not in b_sql, b_sql

    def test_context_clear_resets_active_context_info_amux152_16(self):
        """AMUX-152 #16: SQLTranslationContext.clear() must reset
        active_context_info — a reused context otherwise leaks the previous
        library's declared-context binding across translations."""
        from fhir4ds.cql.translator.context import SQLTranslationContext

        ctx = SQLTranslationContext(resource_type="Patient")
        assert ctx.active_context_info is None
        ctx.active_context_info = {
            "name": "Facility",
            "context_type": "Facility",
            "key_elements": [{"path": "id"}],
        }
        ctx.clear()
        assert ctx.active_context_info is None, (
            "clear() leaks the stale declared-context binding"
        )
