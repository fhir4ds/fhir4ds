"""cqlDateTimeAdd native parity tests (v0.0.14 WASM parity campaign).

Desktop legs (native register() / forced Python) both resolve to the Python
authority because cqlDateTimeAdd is in _PYTHON_PREFERRED_CPP_CONFLICTS
(it delegates to the dateAddQuantity core, whose C++ nulls
sub-input-precision s/ms units where Python truncates-and-returns — the
documented family divergence). The no-Python leg exercises the true C++
implementation, which is byte-identical on all non-divergent classes
(including the Python-authority 0001-01-01T date-prefix rendering for
Time-value inputs).
"""

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register as register_cql
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.udf.datetime import cqlDateTimeAdd

CASES = [
    # (datetime, quantity, expected)
    ("2014-01-01", {"value": 1, "unit": "days"}, "2014-01-02"),
    ("2014-01-01", {"value": 1, "unit": "weeks"}, "2014-01-08"),
    ("2014-01", {"value": 1, "unit": "months"}, "2014-02"),
    ("2014", {"value": 24, "unit": "months"}, "2016"),
    ("2024-02-29", {"value": 1, "unit": "years"}, "2025-02-28"),
    ("2024-01-31", {"value": 1, "unit": "months"}, "2024-02-29"),
    ("2014-01-01T10", {"value": 90, "unit": "minutes"}, "2014-01-01T11"),
    ("2014-01-01T10:30:00", {"value": 1500, "unit": "milliseconds"}, "2014-01-01T10:30:01"),
    ("2014-01-01T10:30:00.000", {"value": 1, "unit": "seconds"}, "2014-01-01T10:30:01.000"),
    ("2014-01-01T10:30:00+05:00", {"value": 1, "unit": "hours"}, "2014-01-01T11:30:00+05:00"),
    ("2014-01-01T10:30:00Z", {"value": 30, "unit": "minutes"}, "2014-01-01T11:00:00Z"),
    # Python-authority Time-input rendering: 0001-01-01T date prefix.
    ("T10:30:00", {"value": 90, "unit": "minutes"}, "0001-01-01T12:00:00"),
    ("T23:59:59.999", {"value": 1, "unit": "milliseconds"}, "0001-01-01T00:00:00.000"),
    ("T10:30", {"value": 1, "unit": "minutes"}, "0001-01-01T10:31"),
    # CQL §8.1 unit restrictions -> NULL
    ("2014-01-01", {"value": 5, "unit": "hours"}, None),  # Date + sub-day
    ("T10:30:00", {"value": 1, "unit": "days"}, None),    # Time + day-level
    # Nulls
    (None, {"value": 1, "unit": "days"}, None),
    ("2014-01-01", None, None),
]

# Known-divergent class (C++ core nulls; Python truncates): excluded from
# no-Python assertions, documented as the dateAddQuantity-family divergence.
DIVERGENT_CLASS = [
    ("2024-01-01T10", {"value": 30, "unit": "s"}),
    ("2024-01-01T10:30", {"value": 1500, "unit": "ms"}),
]


def _native_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_cql(con, include_fhirpath=False)
    return con


def _python_con():
    con = duckdb.connect()
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=False)
    return con


def _no_python_con():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    con.execute(
        "LOAD '/mnt/d/fhir4ds/extensions/cql/build/release/extension/cql/cql.duckdb_extension'"
    )
    return con


@pytest.mark.parametrize(
    "con_factory",
    [
        pytest.param(_native_con, id="native"),
        pytest.param(_python_con, id="forced_python"),
    ],
)
@pytest.mark.parametrize("dt,qty,expected", CASES)
def test_python_authority_cases_on_desktop_legs(con_factory, dt, qty, expected):
    con = con_factory()
    try:
        if dt is None:
            row = con.execute(
                "SELECT cqlDateTimeAdd(NULL, ?)", [json.dumps(qty) if qty else None]
            ).fetchone()
        elif qty is None:
            row = con.execute("SELECT cqlDateTimeAdd(?, NULL)", [dt]).fetchone()
        else:
            row = con.execute(
                "SELECT cqlDateTimeAdd(?, ?)", [dt, json.dumps(qty)]
            ).fetchone()
        assert row[0] == expected
    finally:
        con.close()


@pytest.mark.parametrize("dt,qty,expected", CASES)
def test_no_python_cpp_matches_on_non_divergent_classes(dt, qty, expected):
    """The true C++ implementation is byte-identical to the Python
    authority everywhere except the documented sub-input-precision s/ms
    divergence class (inherited from the dateAddQuantity core)."""
    con = _no_python_con()
    try:
        if dt is None:
            row = con.execute(
                "SELECT cqlDateTimeAdd(NULL, ?)", [json.dumps(qty) if qty else None]
            ).fetchone()
        elif qty is None:
            row = con.execute("SELECT cqlDateTimeAdd(?, NULL)", [dt]).fetchone()
        else:
            row = con.execute(
                "SELECT cqlDateTimeAdd(?, ?)", [dt, json.dumps(qty)]
            ).fetchone()
        assert row[0] == expected
    finally:
        con.close()


def test_no_python_divergent_class_documented():
    """Pins the KNOWN divergence: sub-input-precision s/ms quantities where
    the C++ core nulls (per its unit-precision guard) while the Python
    authority truncates-and-returns. Same class as dateAddQuantity; WASM
    surfaces the C++ behavior."""
    con = _no_python_con()
    try:
        for dt, qty in DIVERGENT_CLASS:
            row = con.execute(
                "SELECT cqlDateTimeAdd(?, ?)", [dt, json.dumps(qty)]
            ).fetchone()
            assert row[0] is None
        py_con = _python_con()
        try:
            for dt, qty in DIVERGENT_CLASS:
                row = py_con.execute(
                    "SELECT cqlDateTimeAdd(?, ?)", [dt, json.dumps(qty)]
                ).fetchone()
                assert row[0] is not None  # Python truncates and returns
        finally:
            py_con.close()
    finally:
        con.close()


def test_python_authority_direct_agreement():
    """Direct function call agreement (bypassing DuckDB) on all cases."""
    for dt, qty, expected in CASES:
        if dt is None or qty is None:
            continue
        assert cqlDateTimeAdd(dt, json.dumps(qty)) == expected
