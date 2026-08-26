"""FP-08 spec-compliance campaign (2026-08-17) regression coverage.

Dual-path (native C++ extension vs forced Python fallback) parity plus
spec-value assertions for:
- §5.5.7 toQuantity/convertsToQuantity calendar conversion-factor table
  (QA-001): 1 year = 12 months or 365 days, 1 month = 30 days — calendar
  keyword cross conversions must succeed via the direct table factors.
- §4.1.4 Decimal precision (QA-002): non-terminating conversions render at
  28 significant digits in BOTH engines.
- §5.5.9 toTime + §6.1 equality (QA-003): T-prefixed partial times parse
  and compare equal to their canonical forms in the fallback.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath

RESOURCE = json.dumps({"resourceType": "Patient", "id": "p1"})


def _native_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def _assert_dual_path(con, fallback, cases) -> None:
    try:
        for expression, expected in cases:
            query = "SELECT fhirpath_text(?::JSON, ?)"
            cpp = con.execute(query, [RESOURCE, expression]).fetchone()[0]
            py = fallback.execute(query, [RESOURCE, expression]).fetchone()[0]
            assert cpp == py, (
                f"native vs fallback mismatch on {expression}: {cpp!r} vs {py!r}"
            )
            assert cpp == expected, (
                f"expected {expected!r} for {expression}, got {cpp!r}"
            )
    finally:
        con.close()
        fallback.close()


def test_toquantity_calendar_table_bridging_fp08_skeptic(monkeypatch) -> None:
    """§5.5.7 canonical conversion-factor table (QA-001)."""
    cases = [
        # Direct table rows
        ("(1 year).toQuantity('month').toString()", "12 month"),
        ("(1 year).toQuantity('day').toString()", "365 day"),
        ("(1 month).toQuantity('day').toString()", "30 day"),
        ("(2 months).toQuantity('days').toString()", "60 days"),
        ("(1 month).toQuantity('year').toString()",
         "0.08333333333333333333333333333 year"),
        ("(1 day).toQuantity('month').toString()",
         "0.03333333333333333333333333333 month"),
        ("(1 day).toQuantity('year').toString()",
         "0.002739726027397260273972602740 year"),
        # year->month must use the DIRECT factor 12 (365/30 != 12)
        ("(1 year).toQuantity('months').toString()", "12 months"),
        # Composed through days for sub-day targets
        ("(1 month).toQuantity('hours').toString()", "720 hours"),
        ("(1 year).toQuantity('hours').toString()", "8760 hours"),
        # Non-terminating bridge renders at 28 significant digits (QA-002)
        ("(1 year).toQuantity('week').toString()",
         "52.14285714285714285714285714 week"),
        # Within-group conversions keep working
        ("(1 week).toQuantity('day').toString()", "7 day"),
        ("(1 day).toQuantity('hour').toString()", "24 hour"),
        ("(1 'a').toQuantity('mo').toString()", "12 'mo'"),
        # §6.1 category rejection preserved for UCUM cross pairs
        ("(1 year).toQuantity('s')", None),
        ("(1 year).convertsToQuantity('s')", "false"),
        ("(1 month).toQuantity('min')", None),
        ("(1 's').toQuantity('year')", None),
        ("(1 's').convertsToQuantity('year')", "false"),
        # Incompatible dimensions still reject
        ("(1 year).toQuantity('kg')", None),
        ("(1 year).convertsToQuantity('kg')", "false"),
    ]
    con = _native_connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _native_connection()
    _assert_dual_path(con, fallback, cases)


def test_toquantity_decimal_precision_parity_fp08_skeptic(monkeypatch) -> None:
    """§4.1.4: 28-significant-digit Decimal rendering (QA-002)."""
    cases = [
        ("(1 's').toQuantity('min').toString()",
         "0.01666666666666666666666666667 'min'"),
        ("(1 day).toQuantity('week').toString()",
         "0.1428571428571428571428571429 week"),
        ("(1 'min').toQuantity('h').toString()",
         "0.01666666666666666666666666667 'h'"),
        # Exact conversions stay exact/integral
        ("(1 'min').toQuantity('s').toString()", "60 's'"),
        ("(1 'h').toQuantity('min').toString()", "60 'min'"),
        ("(1 'm').toQuantity('cm').toString()", "100 'cm'"),
        ("(90 's').toQuantity('min').toString()", "1.5 'min'"),
    ]
    con = _native_connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _native_connection()
    _assert_dual_path(con, fallback, cases)


def test_totime_t_prefixed_partial_forms_fp08_skeptic(monkeypatch) -> None:
    """§5.5.9/§6.1: T-prefixed partial times parse and compare correctly
    in the fallback (QA-003)."""
    cases = [
        ("'T14:34'.toTime() = @T14:34", "true"),
        ("'T14'.toTime() = @T14", "true"),
        ("'14'.toTime() = @T14", "true"),
        ("'14:34'.toTime() = @T14:34", "true"),
        ("'T14:34:28'.toTime() = @T14:34:28", "true"),
        ("'T14:34'.toTime() < @T15:00", "true"),
        ("'T14'.toTime() <= @T14", "true"),
        ("'T14:34'.convertsToTime()", "true"),
        ("'T14'.convertsToTime()", "true"),
        ("'T14:34:28.123'.toTime() = @T14:34:28.123", "true"),
    ]
    con = _native_connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _native_connection()
    _assert_dual_path(con, fallback, cases)


def test_toquantity_terminating_conversion_no_scale_artifacts_fp08_historian(
    monkeypatch,
) -> None:
    """FP-08 HISTORIAN QA-001: terminating §5.5.7 conversions render the
    exact trimmed value in BOTH engines — Decimal division/multiplication
    scale artifacts ("1.80 'm'", "6.0 'min'", "1.000 'ms'") are internal
    factor scale, not authored precision, and no fixture pins them."""
    cases = [
        ("180 'cm'.toQuantity('m').toString()", "1.8 'm'"),
        ("0.1 'h'.toQuantity('min').toString()", "6 'min'"),
        ("(0.001 's').toQuantity('ms').toString()", "1 'ms'"),
        ("(0.3333333333333333333333333333 day).toQuantity('hour').toString()",
         "8 hour"),
        ("(1 's').toQuantity('min').toQuantity('s').toString()", "1 's'"),
        # non-terminating 28-digit rendering is unchanged by normalization
        ("(1 's').toQuantity('min').toString()",
         "0.01666666666666666666666666667 'min'"),
        ("(1 year).toQuantity('day').toString()", "365 day"),
    ]
    con = _native_connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _native_connection()
    _assert_dual_path(con, fallback, cases)


def test_direct_helper_toquantity_duration_table_fp08_historian() -> None:
    """FP-08 HISTORIAN QA-002: the exported direct helper follows the same
    §5.5.7 conversion-factor table as the core engine (1 year = 365 days)."""
    from fhir4ds.fhirpath.duckdb.functions.conversion import to_quantity

    assert to_quantity("1 'year'", "day") == {"value": 365.0, "unit": "day"}
    assert to_quantity("1 year", "day") == {"value": 365.0, "unit": "day"}
    assert to_quantity("180 'cm'", "m") == {"value": 1.8, "unit": "m"}
    assert to_quantity("5 'mg'", "g") == {"value": 0.005, "unit": "g"}
    # §6.1 category rejection preserved: UCUM cross pairs stay empty
    assert to_quantity("1 'year'", "s") is None
    assert to_quantity("1 'kg'", "cm") is None


def test_toquantity_derived_and_direct_key_base_bridge_fp08_explorer(
    monkeypatch,
) -> None:
    """FP-08 EXPLORER QA-001: direct-table-key units ('J'/'kJ', 'N'/'kN',
    'W'/'kW', 'm2'/'cm2') and direct<->expression pairs ('kJ' ->
    'kg.m2/s2') must convert through base reduction in BOTH engines — the
    Python fallback's `_unit_reduces_to_base` guard previously skipped
    direct keys entirely, returning empty while native converted."""
    cases = [
        ("(1000 'J').toQuantity('kJ').toString()", "1 'kJ'"),
        ("(1 'kJ').toQuantity('J').toString()", "1000 'J'"),
        ("(1000 'N').toQuantity('kN').toString()", "1 'kN'"),
        ("(1000 'W').toQuantity('kW').toString()", "1 'kW'"),
        ("(1 'kJ').toQuantity('kg.m2/s2').toString()", "1000 'kg.m2/s2'"),
        ("(1 'm2').toQuantity('cm2').toString()", "10000 'cm2'"),
        ("(10000 'cm2').toQuantity('m2').toString()", "1 'm2'"),
        ("(1 'mV').toQuantity('V').toString()", "0.001 'V'"),
        ("(1 'J').convertsToQuantity('kJ')", "true"),
        ("(1 'm2').convertsToQuantity('cm2')", "true"),
        ("(1 'kJ').convertsToQuantity('kg.m2/s2')", "true"),
        # Doctrine guards: time-domain and incompatible pairs stay rejected
        ("(1 year).toQuantity('s')", None),
        ("(1 'a').convertsToQuantity('s')", "false"),
        ("1 'month' = 1 'mo'", None),
        ("(1 'kg').toQuantity('m')", None),
        ("(1 'Cel').toQuantity('K')", None),
    ]
    con = _native_connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _native_connection()
    _assert_dual_path(con, fallback, cases)


def test_toquantity_metric_conversion_28_digit_decimal_parity_fp08_explorer(
    monkeypatch,
) -> None:
    """FP-08 EXPLORER QA-002: non-terminating metric conversions render with
    Decimal semantics (§4.1.4: 28 significant digits, ROUND_HALF_EVEN) on
    BOTH engines, not the native binary64 15-significant-digit mask."""
    cases = [
        ("(1 'kPa').toQuantity('mm[Hg]').toString()",
         "7.500637554192106329037968227 'mm[Hg]'"),
        # terminating conversions trim trailing scale zeros
        ("(1 'mm[Hg]').toQuantity('Pa').toString()", "133.322 'Pa'"),
        ("(1 'cm[H2O]').toQuantity('Pa').toString()", "98.0665 'Pa'"),
        ("(3.5 'ft').toQuantity('m').toString()", "1.0668 'm'"),
        ("(1 'oz').toQuantity('g').toString()", "28.349523 'g'"),
        ("(1 '[in_i]').toQuantity('cm').toString()", "2.54 'cm'"),
        # FP-08 SKEPTIC 2026-06-28 binary64-noise mask case stays clean
        ("(0.1 'g' + 0.2 'g').toQuantity('mg').toString()", "300 'mg'"),
    ]
    con = _native_connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _native_connection()
    _assert_dual_path(con, fallback, cases)
