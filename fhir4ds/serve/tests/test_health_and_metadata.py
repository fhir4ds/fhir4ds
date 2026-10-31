"""Liveness and CapabilityStatement endpoints."""

from __future__ import annotations

from fhir4ds.serve.metadata import FHIR_VERSION


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metadata_serves_a_capability_statement(client):
    response = client.get("/metadata")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")
    document = response.json()
    assert document["resourceType"] == "CapabilityStatement"
    assert document["status"] == "active"
    assert document["kind"] == "instance"


def test_metadata_declares_fhir_version(client):
    assert client.get("/metadata").json()["fhirVersion"] == FHIR_VERSION == "4.0.1"


def test_metadata_declares_both_operations_on_both_resources(client):
    document = client.get("/metadata").json()
    resources = {entry["type"]: entry for entry in document["rest"][0]["resource"]}

    assert set(resources) == {"Library", "ViewDefinition"}

    library_operations = {entry["name"]: entry["definition"] for entry in resources["Library"]["operation"]}
    assert library_operations["sqlquery-run"] == (
        "http://sql-on-fhir.org/OperationDefinition/$sqlquery-run"
    )

    view_operations = {
        entry["name"]: entry["definition"] for entry in resources["ViewDefinition"]["operation"]
    }
    assert view_operations["run"] == (
        "http://sql-on-fhir.org/OperationDefinition/$viewdefinition-run"
    )


def test_metadata_declares_system_level_sqlquery_run(client):
    document = client.get("/metadata").json()
    system_operations = {entry["name"] for entry in document["rest"][0].get("operation", [])}
    # Phase 2 mounts the CQL facade by default, so it is a system operation too.
    assert system_operations == {"sqlquery-run", "cql"}


def test_metadata_interactions_come_from_the_route_table(client):
    document = client.get("/metadata").json()
    resources = {entry["type"]: entry for entry in document["rest"][0]["resource"]}
    for name in ("Library", "ViewDefinition"):
        codes = {entry["code"] for entry in resources[name]["interaction"]}
        assert codes == {"create", "read", "search-type"}


def test_metadata_is_derived_from_routes(app):
    """A route added without a declaration must not appear in the document."""
    from fhir4ds.serve.metadata import (
        RouteSpec,
        build_capability_statement,
        collect_route_specs,
    )

    declared = collect_route_specs(app)
    assert declared, "expected the route table to declare capability specs"
    assert all(isinstance(spec, RouteSpec) for spec in declared)

    document = build_capability_statement(app, title="test")
    advertised = {entry["type"] for entry in document["rest"][0]["resource"]}
    assert advertised == {spec.resource for spec in declared if spec.resource}


def test_openapi_and_docs_are_served(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
