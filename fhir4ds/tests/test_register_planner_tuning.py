"""Engine 2.x planner tuning applied by fhir4ds.register() (2026-11-14).

On DuckDB >= 2.0, register() sets delim_join_as_cte=false (validated strict
win across the scaling matrix: CMS2 planning 35s -> sub-second; no measure
regressed at rungs 100/1,000/5,000). On 1.5.x the setting does not exist
and must be silently skipped. See fhir4ds/core.py
_apply_engine_2x_planner_tuning docstring for the measurement provenance.
"""

import duckdb

import fhir4ds


def _setting_is_false(con) -> bool:
    val = con.execute("SELECT current_setting('delim_join_as_cte')").fetchone()[0]
    # DuckDB 2.0 may return the boolean False directly or its string form.
    return val is False or str(val).strip().lower() == "false"


def test_register_applies_2x_planner_tuning_or_skips_on_1x():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        result = fhir4ds.register(con)
        # register must succeed on any supported engine version
        assert set(result) == {"fhirpath_cpp", "cql_cpp"}
        major = int(duckdb.__version__.split(".")[0])
        if major >= 2:
            assert _setting_is_false(con), (
                "register() must set delim_join_as_cte=false on DuckDB 2.x"
            )
        else:
            # 1.5.x: the setting does not exist; asking for it must raise
            # (proving we did NOT set it), and register must not have failed.
            try:
                con.execute("SET delim_join_as_cte=false")
            except duckdb.Error:
                pass
            else:
                raise AssertionError(
                    "1.5.x unexpectedly accepted delim_join_as_cte; "
                    "version guard in _apply_engine_2x_planner_tuning is wrong"
                )
    finally:
        con.close()


def test_register_idempotent_with_planner_tuning():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    try:
        fhir4ds.register(con)
        fhir4ds.register(con)  # idempotent, must not raise
    finally:
        con.close()


def test_parse_time_rejects_date_shaped_strings():
    """Python 3.11's relaxed time.fromisoformat parses '2014-06' as a time
    (20:14 with tz) — the shape gate in _parse_time prevents Date/DateTime
    inputs from falling into the Time branch of dateAddQuantity (the cause
    of 8 DuckDB-2.0 conformance failures, 2026-11-14)."""
    from fhir4ds.cql.duckdb.udf.datetime import _parse_time, dateAddQuantity

    for bad in ("2014-06", "2014-06-01", "2014", "2014-06-01T10:00"):
        assert _parse_time(bad) is None, bad
    for good in ("14:30", "T14:30:00", "T14:30:00.123", "23:59:59.999"):
        assert _parse_time(good) is not None, good
    q = '{"value": 1, "unit": "year", "system": "http://unitsofmeasure.org"}'
    assert dateAddQuantity("2014-06", q) == "2015-06"
