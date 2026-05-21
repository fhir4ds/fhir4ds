"""HEDIS hospice exclusion parity checks."""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection
from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql.translator import CQLToSQLTranslator


LTI_URL = "http://example.org/lti"


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_hospice_multi_source_or_extension_and_temporal_bounds_match_surfaces() -> None:
    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_hospice_probe_cql()),
        output_columns={"HasHospice": "HasHospice"},
    )
    rows = _hospice_resources()
    expected = [
        ("p1", False),  # LTI coverage is outside the measurement period.
        ("p2", True),   # Single matching LTI coverage extension in period.
        ("p3", True),   # Encounter branch is true while Claim is empty.
        ("p4", False),  # Empty sources short-circuit to false.
        ("p5", True),   # LTI extension is the second extension, not the first.
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            _load_resources(con, rows, create_table=True)
            assert con.execute(sql).fetchall() == expected
        with no_python_connection() as no_py:
            _load_resources(no_py, rows, create_table=False)
            assert no_py.execute(sql).fetchall() == expected
    finally:
        py.close()
        cpp.close()


def _load_resources(
    con: duckdb.DuckDBPyConnection,
    rows: list[tuple[str, str, str, str]],
    *,
    create_table: bool,
) -> None:
    if create_table:
        con.execute(
            "CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR)"
        )
    con.executemany("INSERT INTO resources VALUES (?, ?, ?::JSON, ?)", rows)


def _hospice_resources() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for patient_id in ("p1", "p2", "p3", "p4", "p5"):
        rows.append((
            patient_id,
            "Patient",
            json.dumps({"resourceType": "Patient", "id": patient_id}),
            patient_id,
        ))

    rows.extend([
        (
            "cov-2023",
            "Coverage",
            json.dumps({
                "resourceType": "Coverage",
                "id": "cov-2023",
                "beneficiary": {"reference": "Patient/p1"},
                "period": {"start": "2023-01-01", "end": "2023-12-31"},
                "extension": [{"url": LTI_URL, "valueBoolean": True}],
            }),
            "p1",
        ),
        (
            "cov-2025",
            "Coverage",
            json.dumps({
                "resourceType": "Coverage",
                "id": "cov-2025",
                "beneficiary": {"reference": "Patient/p2"},
                "period": {"start": "2025-01-01", "end": "2025-12-31"},
                "extension": [{"url": LTI_URL, "valueBoolean": True}],
            }),
            "p2",
        ),
        (
            "enc-2025",
            "Encounter",
            json.dumps({
                "resourceType": "Encounter",
                "id": "enc-2025",
                "subject": {"reference": "Patient/p3"},
                "period": {"start": "2025-06-01", "end": "2025-06-02"},
            }),
            "p3",
        ),
        (
            "cov-multi",
            "Coverage",
            json.dumps({
                "resourceType": "Coverage",
                "id": "cov-multi",
                "beneficiary": {"reference": "Patient/p5"},
                "period": {"start": "2025-01-01", "end": "2025-12-31"},
                "extension": [
                    {"url": "http://example.org/other", "valueBoolean": True},
                    {"url": LTI_URL, "valueBoolean": True},
                ],
            }),
            "p5",
        ),
    ])
    return rows


def _hospice_probe_cql() -> str:
    return f"""library HedisHospiceProbe version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Measurement Period": Interval[@2025-01-01T00:00:00, @2025-12-31T23:59:59]
define HasHospice:
  exists([Claim] Cl where Cl.created during day of "Measurement Period")
  or exists([Encounter] E where E.period overlaps day of "Measurement Period")
  or exists([Coverage] C
    where exists(C.extension Ext where Ext.url = '{LTI_URL}')
      and C.period overlaps day of "Measurement Period")
"""
