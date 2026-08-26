"""Iteration 6 / Domain 8 — regression tests for QA-012 and QA-015.

QA-012: ``FHIRDataLoader.load_file`` previously leaked raw
``json.JSONDecodeError`` without file-path attribution, asymmetric with
the sibling ``load_ndjson`` which wraps malformed JSON into a typed
``ValueError`` with line/path context. This module exercises the
symmetric wrap on ``load_file``.

QA-015: ``register`` and ``FHIRDataLoader.load_resource`` previously
leaked the raw DuckDB ``ConnectionException`` ("Connection Error:
Connection already closed!") on closed connections, asymmetric with
``evaluate_measure``'s typed wrap. This module exercises the symmetric
typed messages on both surfaces.
"""

from __future__ import annotations

import json

import duckdb
import pytest

import fhir4ds
from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader


@pytest.fixture
def duckdb_con():
    con = duckdb.connect()
    yield con
    con.close()


@pytest.fixture
def loader(duckdb_con):
    return FHIRDataLoader(duckdb_con)


# ======================================================================
# QA-012: load_file wraps malformed JSON with file-path context
# ======================================================================


def test_qa012_load_file_malformed_json_wraps_with_path(loader, tmp_path):
    """Truncated JSON must raise ValueError citing the file path."""
    bad_file = tmp_path / "truncated.json"
    bad_file.write_text('{"resourceType": "Patient", "id": "p1",')

    with pytest.raises(ValueError, match=r"Malformed JSON in .*truncated\.json") as exc:
        loader.load_file(bad_file)

    msg = str(exc.value)
    # Path attribution is the load-bearing assertion (mirrors load_ndjson).
    assert "truncated.json" in msg


def test_qa012_load_file_malformed_json_chains_cause(loader, tmp_path):
    """Original json.JSONDecodeError must be chained for debuggability."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not json}")

    with pytest.raises(ValueError) as exc:
        loader.load_file(bad_file)

    assert isinstance(exc.value.__cause__, json.JSONDecodeError)


def test_qa012_load_file_valid_json_still_loads(loader, tmp_path):
    """Positive control: well-formed JSON must continue to load normally."""
    resource_file = tmp_path / "patient.json"
    resource_file.write_text(json.dumps({
        "resourceType": "Patient",
        "id": "p1",
    }))

    count = loader.load_file(resource_file)
    assert count == 1
    assert loader.count("Patient") == 1


def test_qa012_load_file_rejects_string_path_with_attribution(loader, tmp_path):
    """The wrap must apply when ``path`` is a str (not just Path)."""
    bad_file = tmp_path / "str-path.json"
    bad_file.write_text('{"resourceType": "Patient",')  # truncated
    bad_path_str = str(bad_file)

    with pytest.raises(ValueError, match=r"Malformed JSON in ") as exc:
        loader.load_file(bad_path_str)

    assert "str-path.json" in str(exc.value)


# ======================================================================
# QA-015: register / load_resource wrap closed-connection errors with
# actionable fhir4ds-typed messages (mirrors evaluate_measure).
# ======================================================================


def test_qa015_load_resource_on_closed_connection_wraps():
    """Closed-connection error in load_resource must be wrapped."""
    con = duckdb.connect()
    loader = FHIRDataLoader(con)
    loader.load_resource({"resourceType": "Patient", "id": "p1"})
    con.close()

    with pytest.raises(duckdb.ConnectionException, match=r"Cannot load FHIR resource"):
        loader.load_resource({"resourceType": "Patient", "id": "p2"})


def test_qa015_register_on_closed_connection_wraps():
    """Closed-connection error in fhir4ds.register must be wrapped."""
    con = duckdb.connect()
    con.close()

    with pytest.raises(duckdb.ConnectionException, match=r"Cannot register fhir4ds UDFs"):
        fhir4ds.register(con)


def test_qa015_load_resource_still_works_on_open_connection(loader):
    """Positive control: open connection must continue to load normally."""
    loader.load_resource({"resourceType": "Patient", "id": "open-1"})
    assert loader.count("Patient") == 1

