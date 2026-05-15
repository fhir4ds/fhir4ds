"""Parity tests for numeric simple-path fast paths in DuckDB UDFs."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import fhirpath_number_udf


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_number_fast_path_enforces_singleton_through_repeating_objects() -> None:
    resource = json.dumps(
        {
            "resourceType": "Patient",
            "a": [
                {"v": 1},
                {"v": 2},
            ],
            "single": [
                {"v": 3},
            ],
        }
    )

    con = _connection()
    try:
        for expression in ["a.v", "Patient.a.v"]:
            cpp = con.execute(
                "SELECT fhirpath_number(?::JSON, ?)",
                [resource, expression],
            ).fetchone()[0]
            assert cpp == fhirpath_number_udf(resource, expression)
            assert cpp is None

        cpp_single = con.execute(
            "SELECT fhirpath_number(?::JSON, 'single.v')",
            [resource],
        ).fetchone()[0]
        assert cpp_single == 3.0
    finally:
        con.close()
