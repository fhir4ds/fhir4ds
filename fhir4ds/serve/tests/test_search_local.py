"""Search and conditional writes: the honest subset, and the refusals.

Unknown search parameters must be a 400 rather than a silently unfiltered
answer — that is the property most of these tests exist to pin.
"""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from fhir4ds.serve.app import create_app
from fhir4ds.serve.config import ServeConfig

FHIR_JSON = {"Content-Type": "application/fhir+json"}


@pytest.fixture()
def connection():
    con = duckdb.connect()
    try:
        yield con
    finally:
        con.close()


@pytest.fixture()
def client(connection, tmp_path):
    app = create_app(
        ServeConfig(publish_dir=str(tmp_path / "publish"), flush_autostart=False),
        connection=connection,
    )
    return TestClient(app)


def patient(resource_id: str, *, system: str | None = "urn:mrn", value: str = "A1") -> dict:
    identifier: dict = {"value": value}
    if system is not None:
        identifier["system"] = system
    return {"resourceType": "Patient", "id": resource_id, "identifier": [identifier]}


def seed(client) -> None:
    for resource in (
        patient("p1", value="A1"),
        patient("p2", value="B2"),
        patient("p3", system=None, value="C3"),
    ):
        assert client.post("/Patient", json=resource, headers=FHIR_JSON).status_code == 201


# -- search ------------------------------------------------------------------


def test_search_returns_a_searchset_bundle(client):
    seed(client)

    response = client.get("/Patient")

    assert response.status_code == 200
    bundle = response.json()
    assert bundle["type"] == "searchset"
    assert bundle["total"] == 3
    assert {entry["resource"]["id"] for entry in bundle["entry"]} == {"p1", "p2", "p3"}


def test_search_pages_with_count_and_offset(client):
    seed(client)

    page = client.get("/Patient", params={"_count": 1, "_offset": 1}).json()

    assert page["total"] == 3
    assert len(page["entry"]) == 1
    assert page["entry"][0]["resource"]["id"] == "p2"


def test_search_filters_by_id_list(client):
    seed(client)
    bundle = client.get("/Patient", params={"_id": "p1,p3"}).json()
    assert bundle["total"] == 2
    assert {entry["resource"]["id"] for entry in bundle["entry"]} == {"p1", "p3"}


def test_search_filters_by_identifier_system_and_value(client):
    seed(client)

    assert client.get("/Patient", params={"identifier": "urn:mrn|A1"}).json()["total"] == 1
    assert client.get("/Patient", params={"identifier": "B2"}).json()["total"] == 1
    # ``|value`` means "identifier with no system"
    assert client.get("/Patient", params={"identifier": "|C3"}).json()["total"] == 1
    assert client.get("/Patient", params={"identifier": "urn:mrn|C3"}).json()["total"] == 0


def test_repeated_identifier_parameters_are_anded(client):
    seed(client)
    bundle = client.get(
        "/Patient", params=[("identifier", "urn:mrn|A1"), ("identifier", "urn:mrn|B2")]
    ).json()
    assert bundle["total"] == 0, "one resource cannot match both identifiers"


def test_unknown_search_parameter_is_400_not_silently_ignored(client):
    seed(client)

    response = client.get("/Patient", params={"name": "Smith"})

    assert response.status_code == 400
    issue = response.json()["issue"][0]
    assert issue["code"] == "not-supported"
    assert "identifier" in issue["diagnostics"]


def test_search_excludes_tombstones(client):
    seed(client)
    client.delete("/Patient/p1", headers=FHIR_JSON)

    bundle = client.get("/Patient").json()

    assert bundle["total"] == 2
    assert "p1" not in {entry["resource"]["id"] for entry in bundle["entry"]}


def test_search_of_an_empty_type_is_an_empty_bundle(client):
    bundle = client.get("/Observation").json()
    assert bundle["total"] == 0
    assert "entry" not in bundle


def test_search_rejects_an_invalid_resource_type(client):
    assert client.get("/patient").status_code == 400


# -- conditional create ------------------------------------------------------


def test_conditional_create_returns_the_existing_resource(client):
    seed(client)

    response = client.post(
        "/Patient",
        json=patient("p9", value="A1"),
        headers={**FHIR_JSON, "If-None-Exist": "identifier=urn:mrn|A1"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "p1", "no second resource is created"
    assert len(client.get("/Patient/p1/_history").json()["entry"]) == 1


def test_conditional_create_creates_when_nothing_matches(client):
    seed(client)

    response = client.post(
        "/Patient",
        json=patient("p9", value="Z9"),
        headers={**FHIR_JSON, "If-None-Exist": "identifier=urn:mrn|Z9"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "p9"
    assert client.get("/Patient").json()["total"] == 4


def test_conditional_create_with_many_matches_is_412(client):
    seed(client)

    response = client.post(
        "/Patient",
        json=patient("p9"),
        headers={**FHIR_JSON, "If-None-Exist": "_id=p1,p2"},
    )

    assert response.status_code == 412
    assert client.get("/Patient").json()["total"] == 3, "nothing was created"


def test_conditional_create_without_a_filter_is_400(client):
    # Paging parameters are not a filter: a conditional create needs one.
    response = client.post(
        "/Patient", json=patient("p9"), headers={**FHIR_JSON, "If-None-Exist": "_count=1"}
    )
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "required"


# -- conditional update ------------------------------------------------------


def test_conditional_update_updates_the_single_match(client):
    seed(client)

    response = client.put(
        "/Patient",
        params={"identifier": "urn:mrn|B2"},
        json={"resourceType": "Patient", "identifier": [{"system": "urn:mrn", "value": "B2"}],
              "active": True},
        headers=FHIR_JSON,
    )

    assert response.status_code == 200
    assert response.json()["id"] == "p2"
    # Version ids are the global `_seq`, so the three seeds consumed 1-3 and
    # this update is version 4.
    assert response.headers["etag"] == 'W/"4"'
    assert client.get("/Patient/p2").json()["active"] is True


def test_conditional_update_creates_when_nothing_matches(client):
    seed(client)

    response = client.put(
        "/Patient",
        params={"identifier": "urn:mrn|NEW"},
        json=patient("pnew", value="NEW"),
        headers=FHIR_JSON,
    )

    assert response.status_code == 201
    assert client.get("/Patient").json()["total"] == 4


def test_conditional_update_with_many_matches_is_412(client):
    seed(client)

    response = client.put(
        "/Patient",
        params={"_id": "p1,p2"},
        json=patient("px"),
        headers=FHIR_JSON,
    )

    assert response.status_code == 412


def test_conditional_update_without_a_filter_is_400(client):
    response = client.put("/Patient", json=patient("px"), headers=FHIR_JSON)
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "required"


# -- guards ------------------------------------------------------------------


def test_generic_writes_refuse_registry_owned_types(client):
    put = client.put(
        "/Library/x", json={"resourceType": "Library", "id": "x"}, headers=FHIR_JSON
    )
    assert put.status_code == 400
    assert put.json()["issue"][0]["code"] == "not-supported"

    delete = client.delete("/Library/x", headers=FHIR_JSON)
    assert delete.status_code == 400
    assert delete.json()["issue"][0]["code"] == "not-supported"
