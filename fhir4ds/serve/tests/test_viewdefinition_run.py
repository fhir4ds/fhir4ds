"""ViewDefinition CRUD plus the ``$run`` operation (type and instance level)."""

from __future__ import annotations

import json

from ._helpers import (
    VIEWDEFINITION_FIXTURES,
    load_json_directory,
    parameters,
)


def test_viewdefinition_round_trip(client):
    view = load_json_directory(VIEWDEFINITION_FIXTURES)[0]
    created = client.post("/ViewDefinition", json=view)
    assert created.status_code == 201

    read = client.get(f"/ViewDefinition/{view['id']}")
    assert read.status_code == 200
    assert read.json() == view


def test_viewdefinition_search_returns_a_bundle(client):
    bundle = client.get("/ViewDefinition").json()
    assert bundle["total"] == len(load_json_directory(VIEWDEFINITION_FIXTURES))
    assert bundle["entry"]


def test_viewdefinition_read_unknown_id_is_404(client):
    assert client.get("/ViewDefinition/nope").status_code == 404


def test_instance_run_returns_ndjson_by_default(client):
    response = client.post("/ViewDefinition/patient-view/$run")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")

    rows = [json.loads(line) for line in response.text.strip().splitlines()]
    # Row order is not part of the contract (ViewDefinition imposes none, and
    # phase 3 reads through a windowed latest-wins view), so assert membership.
    assert sorted(row["name"] for row in rows) == ["Johnson", "Smith", "Williams"]
    assert {row["id"] for row in rows} == {"Patient/pt-1", "Patient/pt-2", "Patient/pt-3"}


def test_instance_run_rejects_view_reference_and_resource(client):
    for entry in (
        {"name": "viewReference", "valueReference": {"reference": "ViewDefinition/patient-view"}},
        {"name": "viewResource", "resource": {"resourceType": "ViewDefinition"}},
    ):
        response = client.post("/ViewDefinition/patient-view/$run", json=parameters(entry))
        assert response.status_code == 400


def test_type_level_run_with_view_resource(client):
    view = client.get("/ViewDefinition/patient-address-view").json()
    body = parameters(
        {"name": "viewResource", "resource": view},
        {"name": "_format", "valueCode": "json"},
    )
    response = client.post("/ViewDefinition/$run", json=body)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 4
    assert {row["city"] for row in rows} == {"Boston", "Chicago"}
    assert [row["address_id"] for row in rows if row["patient_id"] == "Patient/pt-2"] == [0, 1]


def test_type_level_run_with_view_reference(client):
    body = parameters(
        {"name": "viewReference", "valueReference": {"reference": "ViewDefinition/patient-view"}}
    )
    response = client.post("/ViewDefinition/$run", json=body)
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 3


def test_type_level_run_requires_a_view(client):
    response = client.post("/ViewDefinition/$run", json=parameters())
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "required"


def test_type_level_run_rejects_both_view_parameters(client):
    body = parameters(
        {"name": "viewReference", "valueReference": {"reference": "ViewDefinition/patient-view"}},
        {"name": "viewResource", "resource": client.get("/ViewDefinition/patient-view").json()},
    )
    assert client.post("/ViewDefinition/$run", json=body).status_code == 400


def test_view_reference_that_does_not_resolve_is_404(client):
    body = parameters(
        {"name": "viewReference", "valueReference": {"reference": "ViewDefinition/absent"}}
    )
    assert client.post("/ViewDefinition/$run", json=body).status_code == 404


def test_view_reference_to_a_library_is_404(client):
    body = parameters(
        {
            "name": "viewReference",
            "valueReference": {"reference": "Library/SqlOnFhirExample"},
        }
    )
    assert client.post("/ViewDefinition/$run", json=body).status_code == 404


def test_unsupported_ig_parameters_are_400_not_silently_ignored(client):
    for name, value in (
        ("patient", {"valueReference": {"reference": "Patient/pt-1"}}),
        ("_since", {"valueInstant": "2024-01-01T00:00:00Z"}),
    ):
        response = client.post(
            "/ViewDefinition/patient-view/$run",
            json=parameters({"name": name, **value}),
        )
        assert response.status_code == 400
        assert response.json()["issue"][0]["code"] == "not-supported"


def test_invalid_view_definition_is_400(client):
    response = client.post(
        "/ViewDefinition/$run",
        json=parameters(
            {"name": "viewResource", "resource": {"resourceType": "ViewDefinition", "resource": "Patient"}}
        ),
    )
    assert response.status_code == 400


def test_limit_caps_viewdefinition_rows(client):
    response = client.post(
        "/ViewDefinition/patient-view/$run",
        json=parameters({"name": "_limit", "valueInteger": 2}),
    )
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 2
