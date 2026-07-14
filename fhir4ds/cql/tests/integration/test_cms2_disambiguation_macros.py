"""Regression tests for CMS2 disambiguation SQL macros (Option D / BENCH-001).

Background: ``_translate_is_type_check`` (fhir4ds/cql/translator/expressions/
_query.py) historically emitted inline ``CASE WHEN starts_with(LTRIM(value),
'{') THEN json_extract_string(value, '$.start') IS NOT NULL ... ELSE FALSE END``
blocks for ``is Interval<DateTime>``, ``is Interval<Quantity>``, ``is Period``,
and ``is Range``. CMS2 referenced the same ``value`` 510+ times per CTE,
producing ~150 KB of duplicated CASE blocks (~10% of CMS2's noaudit SQL).

Option D replaces those inline CASEs with calls to globally-resolvable SQL
macros (``cql_value_is_period``, ``cql_value_is_range``,
``cql_value_is_interval_like``, ``cql_quantity_value``) defined in
``fhir4ds/cql/duckdb/macros/clinical.py``. Unlike Option A/C (which hoisted
the CASE into LATERAL aliases), SQL macros survive the audit emission path's
verbatim fragment-copying because they are globally resolvable from any
scope, including ``__pre_...`` audit pre-compute CTEs.

These tests assert:
1. CMS2 noaudit SQL shrank below 1.4 MB (was 1.55 MB; the inline-CASE
   refactor alone brought it to 1.32 MB).
2. The emitted SQL contains the new macro names.
3. CMS2 FULL audit SQL still executes and returns rows.
4. Macro outputs match the equivalent inline CASE for a hand-crafted set
   of inputs (Period JSON, Range JSON, non-JSON string, NULL, empty JSON).
"""
from __future__ import annotations

import pytest


def _cms2_sql(audit_mode: bool):
    """Translate CMS2 with the conformance test harness and return the SQL."""
    from pathlib import Path

    from fhir4ds.dqm.tests.conformance.config import (
        get_suite_paths,
        MeasureConfig,
    )
    from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase
    from fhir4ds.dqm.tests.conformance.runner import (
        _normalize_population_definitions,
        _translate_measure,
    )
    from fhir4ds.dqm.tests.conformance.loader import load_test_suite
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.parser.ast_nodes import Definition

    suite = get_suite_paths("2025")
    cql_path = suite["cql_dir"] / "CMS2FHIRPCSDepressionScreenAndFollowUp.cql"
    test_dir = (
        suite["bundle_dir"] / cql_path.stem / f"{cql_path.stem}-files"
    )
    db = BenchmarkDatabase()
    mc = MeasureConfig(
        id="CMS2",
        name=cql_path.stem,
        cql_path=cql_path,
        test_dir=test_dir,
        include_paths=[suite["cql_dir"]],
        valueset_paths=[suite["valueset_dir"]],
        population_definitions=[
            "Initial Population",
            "Denominator",
            "Denominator Exceptions",
            "Numerator",
            "Numerator Exclusions",
        ],
    )
    db.load_all_test_data([mc])
    db.unscope_resources()
    library = parse_cql(cql_path.read_text())
    actual_defs = {
        stmt.name
        for stmt in library.statements
        if isinstance(stmt, Definition)
    }
    npd, _ = _normalize_population_definitions(
        mc.population_definitions, actual_defs
    )
    output_columns = {n: n for n in npd}
    ts = load_test_suite(mc)
    mp = {"Measurement Period": ts.measurement_period}
    pids = [tc.patient_id for tc in ts.test_cases]
    sql, _, _ = _translate_measure(
        db.conn,
        library,
        mc,
        output_columns,
        mp,
        pids,
        audit_mode=audit_mode,
        audit_expressions=audit_mode,
    )
    return sql, db


@pytest.mark.timeout(600)
def test_cms2_noaudit_uses_disambiguation_macros_and_shrinks():
    """CMS2 noaudit SQL uses the new macros and is below 1.4 MB."""
    sql, _ = _cms2_sql(audit_mode=False)

    # Size regression: was 1,552,792 bytes before Option D.
    assert len(sql) < 1_400_000, (
        f"CMS2 noaudit SQL grew or did not shrink enough: {len(sql):,} bytes "
        f"(expected < 1,400,000; baseline was 1,552,792)"
    )

    # Macro presence: the emitted SQL must reference the new macros.
    # CMS2's ``is Interval<DateTime>`` checks lower to cql_value_is_interval_like.
    assert "cql_value_is_interval_like(" in sql, (
        "CMS2 noaudit SQL does not contain cql_value_is_interval_like macro "
        "calls — disambiguation CASE emission was not refactored."
    )


@pytest.mark.timeout(600)
def test_cms2_noaudit_has_no_inline_period_range_case():
    """CMS2 noaudit SQL contains no inline ``$.start``/``$.low`` CASE blocks."""
    import re

    sql, _ = _cms2_sql(audit_mode=False)

    # The inline CASE shape that was replaced. It should be entirely gone.
    inline_pattern = re.compile(
        r"CASE WHEN starts_with\(LTRIM\([^)]+\), '\{'\) "
        r"THEN json_extract_string\([^,]+, '\$\.start'\) IS NOT NULL.*?END",
        re.DOTALL,
    )
    matches = inline_pattern.findall(sql)
    assert not matches, (
        f"CMS2 noaudit SQL still contains {len(matches)} inline Period/Range "
        f"disambiguation CASE blocks — macro refactor incomplete."
    )


@pytest.mark.timeout(600)
def test_cms2_full_audit_executes_and_returns_rows():
    """CMS2 FULL audit SQL still executes and returns rows at the smaller size."""
    sql, db = _cms2_sql(audit_mode=True)

    # Raise DuckDB's expression depth limit so the deeply-nested audit
    # AND/OR chains parse. This is a CMS2-scale concern, not a macro concern.
    db.conn.execute("SET max_expression_depth TO 10000")
    rows = db.conn.execute(sql).fetchall()
    assert len(rows) > 0, "CMS2 FULL audit returned zero rows"


def test_disambiguation_macros_match_inline_case_semantics():
    """The disambiguation macros produce identical results to the inline CASE."""
    import duckdb

    from fhir4ds.cql.duckdb.macros.clinical import registerClinicalMacros

    con = duckdb.connect()
    registerClinicalMacros(con)

    test_inputs = [
        '{"start":"2020","end":"2021"}',  # Period JSON
        '{"start":"2020"}',               # Period start-only
        '{"end":"2021"}',                 # Period end-only
        '{"low":{"value":1},"high":{"value":2}}',  # Range JSON
        '{"low":{"value":1}}',            # Range low-only
        '{"high":{"value":2}}',           # Range high-only
        '{"foo":"bar"}',                  # Other JSON object
        '{}',                             # Empty JSON object
        'not-json',                       # Bare string
        '2020-01-01',                     # Date string
    ]

    # cql_value_is_period vs inline CASE
    for val in test_inputs:
        macro = con.execute(
            f"SELECT cql_value_is_period('{val}')"
        ).fetchone()[0]
        inline = con.execute(
            f"""SELECT CASE WHEN starts_with(LTRIM('{val}'), '{{')
            THEN json_extract_string('{val}', '$.start') IS NOT NULL
            OR json_extract_string('{val}', '$.end') IS NOT NULL
            ELSE FALSE END"""
        ).fetchone()[0]
        assert macro == inline, (
            f"cql_value_is_period mismatch for {val!r}: "
            f"macro={macro}, inline={inline}"
        )

    # cql_value_is_range vs inline CASE
    for val in test_inputs:
        macro = con.execute(
            f"SELECT cql_value_is_range('{val}')"
        ).fetchone()[0]
        inline = con.execute(
            f"""SELECT CASE WHEN starts_with(LTRIM('{val}'), '{{')
            THEN json_extract_string('{val}', '$.low') IS NOT NULL
            OR json_extract_string('{val}', '$.high') IS NOT NULL
            ELSE FALSE END"""
        ).fetchone()[0]
        assert macro == inline, (
            f"cql_value_is_range mismatch for {val!r}: "
            f"macro={macro}, inline={inline}"
        )

    # cql_value_is_interval_like vs inline CASE (combined Period OR Range)
    for val in test_inputs:
        macro = con.execute(
            f"SELECT cql_value_is_interval_like('{val}')"
        ).fetchone()[0]
        inline = con.execute(
            f"""SELECT CASE WHEN starts_with(LTRIM('{val}'), '{{')
            THEN json_extract_string('{val}', '$.start') IS NOT NULL
            OR json_extract_string('{val}', '$.end') IS NOT NULL
            OR json_extract_string('{val}', '$.low') IS NOT NULL
            OR json_extract_string('{val}', '$.high') IS NOT NULL
            ELSE FALSE END"""
        ).fetchone()[0]
        assert macro == inline, (
            f"cql_value_is_interval_like mismatch for {val!r}: "
            f"macro={macro}, inline={inline}"
        )

    # cql_quantity_value vs inline CASE (Quantity $.value extraction)
    for val in test_inputs:
        macro = con.execute(
            f"SELECT cql_quantity_value('{val}')"
        ).fetchone()[0]
        inline = con.execute(
            f"""SELECT CASE WHEN starts_with(LTRIM('{val}'), '{{')
            THEN json_extract_string('{val}', '$.value')
            ELSE '{val}' END"""
        ).fetchone()[0]
        assert macro == inline, (
            f"cql_quantity_value mismatch for {val!r}: "
            f"macro={macro}, inline={inline}"
        )

    # NULL handling: all macros return FALSE (boolean) or NULL (value extraction)
    null_period = con.execute(
        "SELECT cql_value_is_period(NULL)"
    ).fetchone()[0]
    null_range = con.execute(
        "SELECT cql_value_is_range(NULL)"
    ).fetchone()[0]
    null_interval = con.execute(
        "SELECT cql_value_is_interval_like(NULL)"
    ).fetchone()[0]
    null_quantity = con.execute(
        "SELECT cql_quantity_value(NULL)"
    ).fetchone()[0]
    assert null_period is False or null_period is None
    assert null_range is False or null_range is None
    assert null_interval is False or null_interval is None
    assert null_quantity is None  # value extraction propagates NULL
