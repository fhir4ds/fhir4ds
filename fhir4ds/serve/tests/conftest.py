"""Shared fixtures for the serve-layer tests.

One DuckDB connection per session (creating one loads the bundled extensions,
which is slow on the Windows mount); the resource registry is cleared and
re-seeded for each test so tests stay isolated without paying that cost
repeatedly.
"""

from __future__ import annotations

import pytest

from ._helpers import (
    LIBRARY_FIXTURES,
    RESOURCE_BUNDLE,
    VIEWDEFINITION_FIXTURES,
    load_json_directory,
)


@pytest.fixture(scope="session")
def connection():
    """A DuckDB connection with the UDFs registered and the synthetic data loaded."""
    from fhir4ds.connection import create_connection
    from fhir4ds.cql.loader import FHIRDataLoader

    con = create_connection(":memory:")
    loaded = FHIRDataLoader(con).load_file(RESOURCE_BUNDLE)
    assert loaded == 9, f"expected 9 synthetic resources, loaded {loaded}"
    yield con
    con.close()


@pytest.fixture()
def store(connection):
    """A resource store seeded with the IG example Libraries and the views they use."""
    from fhir4ds.serve.store import ResourceStore

    registry = ResourceStore(connection)
    registry.ensure_schema()
    connection.execute("DELETE FROM serve_resource_registry")
    for resource in load_json_directory(VIEWDEFINITION_FIXTURES):
        registry.put(resource)
    for resource in load_json_directory(LIBRARY_FIXTURES):
        registry.put(resource)
    return registry


@pytest.fixture()
def app(connection, store):
    """The FastAPI application bound to the session connection."""
    from fhir4ds.serve.app import create_app

    return create_app(connection=connection)


@pytest.fixture()
def client(app):
    """A TestClient over the application."""
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
