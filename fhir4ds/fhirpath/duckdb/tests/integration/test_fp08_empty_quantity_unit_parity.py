"""FP-08 parity tests for empty optional Quantity unit arguments."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath


RESOURCE = json.dumps({"resourceType": "Observation", "id": "fp08-empty-unit"})


def _connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register_fhirpath(con)
    return con


def test_empty_quantity_unit_argument_propagates_empty_in_native_and_fallback(monkeypatch) -> None:
    expressions = [
        "1.toQuantity({})",
        "1.convertsToQuantity({})",
    ]
    query = """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_quantity(?::JSON, ?),
          fhirpath_is_valid(?)
    """

    con = _connection()
    monkeypatch.setattr(duckdb, "__version__", "0.0.0-forced-python-fallback")
    fallback = _connection()
    try:
        for expression in expressions:
            params = [
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                RESOURCE,
                expression,
                expression,
            ]
            expected = ([], None, None, None, None, True)
            assert con.execute(query, params).fetchone() == expected
            assert fallback.execute(query, params).fetchone() == expected
    finally:
        con.close()
        fallback.close()
