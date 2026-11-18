"""D3 HISTORIAN regression: contains/in closed-null-interval mirror consistency.

Official fixture TestIntegerInMaxIntervalTrue pins `5 in Interval[null, null]`
as true (closed null bounds = maximum interval per CQL §9.14/§9.15 Start/End
sentinels). `contains` is the mirror of `in`, so both spellings must agree.
The old `_interval_selector_is_untyped_null_interval` early-false guard in
`_translate_contains_op` folded the closed selector to False (QA-018 lost-work
class). Re-landed 2026-11-17.
"""
from __future__ import annotations

import duckdb

from fhir4ds.cql import translate_cql

CQL = """library D3HistorianMirror version '1.0.0'
using FHIR version '4.0.1'
context Patient
define InClosed: 5 in Interval[null, null]
define ContainsClosed: Interval[null, null] contains 5
define InUnboundedLow: 5 in Interval[null, 10]
define ContainsUnboundedLow: Interval[null, 10] contains 5
define InUnboundedHigh: 5 in Interval[0, null]
define ContainsUnboundedHigh: Interval[0, null] contains 5
define NullContains: null contains 5
define InNullInterval: 5 in (null as Interval<Integer>)
"""


def test_contains_in_closed_null_interval_mirror_consistency() -> None:
    translated = translate_cql(CQL)
    cons = [
        duckdb.connect(),                                    # python fallback
        duckdb.connect(config={"allow_unsigned_extensions": True}),  # native
    ]
    try:
        from fhir4ds import register

        for con in cons:
            register(con)
            results = {
                name: con.execute(f"SELECT {sql.to_sql()}").fetchone()[0]
                for name, sql in translated.items()
            }
            # Fixture-pinned: closed null-null = [min, max]
            assert results["InClosed"] is True
            assert results["ContainsClosed"] is True
            # Sentinels on one side only still contain interior points
            assert results["InUnboundedLow"] is True
            assert results["ContainsUnboundedLow"] is True
            assert results["InUnboundedHigh"] is True
            assert results["ContainsUnboundedHigh"] is True
            # A genuinely null interval operand is false per CQL §19.3/§19.12
            assert results["NullContains"] is False
            assert results["InNullInterval"] is False
    finally:
        for con in cons:
            con.close()


CQL_COLLAPSE = """library D3ExplorerCollapseListOps version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EqPer: collapse { Interval[1, 3], Interval[4, 6] } per 1 = { Interval[1, 6] }
define EqNoPer: collapse { Interval[1, 3], Interval[4, 6] } = { Interval[1, 6] }
define EqFalse: collapse { Interval[1, 3], Interval[7, 9] } = { Interval[1, 6] }
define InCollapse: Interval[1, 6] in collapse { Interval[1, 3], Interval[4, 6] } per 1
define InCollapseFalse: Interval[2, 6] in collapse { Interval[1, 3], Interval[4, 6] } per 1
define UnionLit: collapse { Interval[1, 3], Interval[4, 6] } per 1 union { Interval[10, 12] } = { Interval[1, 6], Interval[10, 12] }
define CountStill: Count(collapse { Interval[1, 3], Interval[4, 6] } per 1) = 1
"""


def test_collapse_list_sources_feed_list_operators() -> None:
    """D3 EXPLORER: `=`/`in`/`union` over collapse results must not binder-error.

    collapse_intervals[_per] return JSON array text (VARCHAR); the list
    equality/membership/union lowering sites emitted array_length /
    CQLListEqualEq / list_concat directly over the VARCHAR, raising
    BinderException. Fixed via _coerce_json_list_source (CQL-15 JSON-list
    doctrine extended to these sites).
    """
    translated = translate_cql(CQL_COLLAPSE)
    con = duckdb.connect()
    try:
        from fhir4ds import register

        register(con)
        row = con.execute(
            "SELECT " + ", ".join(
                f"{sql.to_sql()} AS {name}" for name, sql in translated.items()
            )
        ).fetchone()
        results = dict(zip(translated.keys(), row))
        assert results["EqPer"] is True
        assert results["EqNoPer"] is True
        assert results["EqFalse"] is False
        assert results["InCollapse"] is True
        assert results["InCollapseFalse"] is False
        assert results["UnionLit"] is True
        assert results["CountStill"] is True
    finally:
        con.close()
