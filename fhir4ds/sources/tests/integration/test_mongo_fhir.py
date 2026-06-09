"""Environment-gated integration tests for MongoFhirServerSource."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import duckdb
import pytest

from fhir4ds.sources import MongoFhirServerSchema, MongoFhirServerSource

pytestmark = pytest.mark.integration


def _mongo_env() -> tuple[str, str]:
    if os.environ.get("FHIR4DS_RUN_MONGO_INTEGRATION") != "1":
        pytest.skip("Set FHIR4DS_RUN_MONGO_INTEGRATION=1 to run Mongo integration tests")
    uri = os.environ.get("FHIR4DS_MONGO_URI", "mongodb://localhost:27017")
    database = os.environ.get("FHIR4DS_MONGO_DATABASE", "fhir")
    return uri, database


def _load_mongo_extension(con: duckdb.DuckDBPyConnection) -> None:
    try:
        con.execute("INSTALL mongo FROM community")
        con.execute("LOAD mongo")
    except Exception as exc:
        pytest.skip(f"DuckDB community mongo extension unavailable: {exc}")


def _seed_with_mongosh(uri: str, database: str) -> None:
    mongosh = shutil.which("mongosh")
    if not mongosh:
        pytest.skip("mongosh is not available for Mongo integration seeding")
    db_name = json.dumps(database)
    script = f"""
        const fhir4dsDb = db.getSiblingDB({db_name});
        fhir4dsDb.Patient_4_0_0.deleteMany({{id: /^fhir4ds-mongo-/}});
        fhir4dsDb.Observation_4_0_0.deleteMany({{id: /^fhir4ds-mongo-/}});
        fhir4dsDb.Patient_4_0_0.insertOne({{
          resourceType: 'Patient',
          id: 'fhir4ds-mongo-patient',
          active: true
        }});
        fhir4dsDb.Observation_4_0_0.insertOne({{
          resourceType: 'Observation',
          id: 'fhir4ds-mongo-observation',
          subject: {{reference: 'Patient/fhir4ds-mongo-patient'}},
          status: 'final'
        }});
    """
    result = subprocess.run(
        [mongosh, uri, "--quiet", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"Mongo fixture seed failed: {result.stderr.strip()}")


def test_duckdb_mongo_extension_loads_when_enabled():
    _mongo_env()
    con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
    _load_mongo_extension(con)


def test_mongo_backed_resources_view_smoke():
    uri, database = _mongo_env()
    _seed_with_mongosh(uri, database)
    con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
    _load_mongo_extension(con)

    source = MongoFhirServerSource(
        uri,
        schema=MongoFhirServerSchema(
            database_name=database,
            resource_types=("Patient", "Observation"),
            include_hidden=True,
            sample_size=-1,
        ),
        install_extension=False,
    )
    source.register(con)

    rows = con.execute("""
        SELECT id, resourceType, patient_ref
        FROM resources
        WHERE id LIKE 'fhir4ds-mongo-%'
        ORDER BY id
    """).fetchall()
    assert rows == [
        ("fhir4ds-mongo-observation", "Observation", "fhir4ds-mongo-patient"),
        ("fhir4ds-mongo-patient", "Patient", "fhir4ds-mongo-patient"),
    ]
