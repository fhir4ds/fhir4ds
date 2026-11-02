"""Library CRUD round-trip and the ``$sqlquery-run`` operation."""

from __future__ import annotations

import json

import pytest

from ._helpers import (
    LIBRARY_FIXTURES,
    SQLONFHIR_PARAMETERS,
    TEST_ADMIN_KEY,
    TEST_WRITE_KEY,
    keyed_client,
    library_with_dependency,
    load_json_directory,
    parameter_body,
    parameters,
    parameters_resource,
    sqlquery_library,
)


def sqlonfhir_body(*extra: dict) -> dict:
    return parameters(
        {
            "name": "parameters",
            "resource": parameters_resource(
                *[{"name": name, "valueString": value} for name, value in SQLONFHIR_PARAMETERS]
            ),
        },
        *extra,
    )


# -- CRUD -------------------------------------------------------------------


def test_library_round_trip(client):
    library = load_json_directory(LIBRARY_FIXTURES)[0]
    created = client.post("/Library", json=library)
    assert created.status_code == 201
    assert created.json()["id"] == library["id"]

    read = client.get(f"/Library/{library['id']}")
    assert read.status_code == 200
    assert read.json() == library


def test_library_post_assigns_an_id_when_omitted(client):
    created = client.post("/Library", json={"resourceType": "Library", "status": "active"})
    assert created.status_code == 201
    assert created.json()["id"]


def test_library_post_rejects_the_wrong_resource_type(client):
    response = client.post("/Library", json={"resourceType": "Patient", "id": "p1"})
    assert response.status_code == 400
    assert response.json()["resourceType"] == "OperationOutcome"


def test_library_post_rejects_an_invalid_id(client):
    response = client.post("/Library", json={"resourceType": "Library", "id": "bad_id"})
    assert response.status_code == 400


def test_library_read_unknown_id_is_404_with_outcome(client):
    response = client.get("/Library/nope")
    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-found"


def test_library_search_returns_a_searchset_bundle(client):
    response = client.get("/Library")
    assert response.status_code == 200
    bundle = response.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] == len(load_json_directory(LIBRARY_FIXTURES))
    assert len(bundle["entry"]) == bundle["total"]


def test_library_search_honours_count_and_offset(client):
    total = client.get("/Library").json()["total"]
    first = client.get("/Library?_count=1").json()
    assert first["total"] == total
    assert len(first["entry"]) == 1

    second = client.get("/Library?_count=1&_offset=1").json()
    assert first["entry"][0]["resource"]["id"] != second["entry"][0]["resource"]["id"]


def test_library_search_rejects_a_non_integer_count(client):
    assert client.get("/Library?_count=lots").status_code == 400


# -- $sqlquery-run ----------------------------------------------------------


def test_instance_run_defaults_to_ndjson(client):
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=sqlonfhir_body())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")

    lines = [json.loads(line) for line in response.text.strip().splitlines()]
    assert len(lines) == 2
    assert lines[0]["patient_id"] == "Patient/pt-1"
    assert {"systolic", "diastolic", "effective_date"} <= set(lines[0])


def test_instance_run_accepts_an_absent_body(client):
    """A Library that declares no parameters runs with no request body."""
    library = sqlquery_library("no-params", "SELECT 1 AS one, 'two' AS two")
    assert client.post("/Library", json=library).status_code == 201

    response = client.post("/Library/no-params/$sqlquery-run")
    assert response.status_code == 200
    assert json.loads(response.text.strip()) == {"one": 1, "two": "two"}


def test_type_level_run_with_query_reference(client):
    body = parameters(
        {
            "name": "queryReference",
            "valueReference": {"reference": "Library/SqlOnFhirExample"},
        },
        *[entry for entry in sqlonfhir_body()["parameter"] if entry["name"] == "parameters"],
    )
    response = client.post("/Library/$sqlquery-run", json=body)
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 2


def test_type_level_run_with_query_resource(client):
    library = client.get("/Library/SqlOnFhirExample").json()
    body = parameters(
        {"name": "queryResource", "resource": library},
        *[entry for entry in sqlonfhir_body()["parameter"] if entry["name"] == "parameters"],
    )
    response = client.post("/Library/$sqlquery-run", json=body)
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 2


def test_system_level_run_requires_a_query(client):
    response = client.post("/$sqlquery-run", json=parameters())
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "required"


def test_system_level_run_with_query_resource(client):
    library = client.get("/Library/UniquePatientAddressesQuery").json()
    body = parameters(
        {"name": "queryResource", "resource": library},
        {
            "name": "parameters",
            "resource": parameters_resource({"name": "city", "valueString": "Boston"}),
        },
    )
    response = client.post("/$sqlquery-run", json=body)
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 2


def test_instance_level_rejects_query_reference(client):
    body = parameters(
        {"name": "queryReference", "valueReference": {"reference": "Library/SqlOnFhirExample"}}
    )
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=body)
    assert response.status_code == 400


def test_type_level_rejects_both_query_parameters(client):
    body = parameters(
        {"name": "queryReference", "valueReference": {"reference": "Library/SqlOnFhirExample"}},
        {"name": "queryResource", "resource": client.get("/Library/SqlOnFhirExample").json()},
    )
    response = client.post("/Library/$sqlquery-run", json=body)
    assert response.status_code == 400


def test_query_reference_that_does_not_resolve_is_404(client):
    body = parameters(
        {"name": "queryReference", "valueReference": {"reference": "Library/absent"}}
    )
    assert client.post("/Library/$sqlquery-run", json=body).status_code == 404


def test_missing_required_library_parameter_is_400(client):
    body = parameters(
        {
            "name": "parameters",
            "resource": parameters_resource(
                {"name": "patient_id", "valueString": "Patient/pt-1"},
                {"name": "from_date", "valueString": "2024-01-01"},
            ),
        }
    )
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=body)
    assert response.status_code == 400
    assert "Missing required parameter" in response.json()["issue"][0]["diagnostics"]


def test_unknown_library_parameter_is_400(client):
    body = sqlonfhir_body()
    body["parameter"][0]["resource"]["parameter"].append({"name": "typo", "valueString": "x"})
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=body)
    assert response.status_code == 400
    assert "typo" in response.json()["issue"][0]["diagnostics"]


def test_unknown_operation_parameter_is_400(client):
    body = parameters({"name": "not_a_parameter", "valueString": "x"})
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=body)
    assert response.status_code == 400
    assert response.json()["issue"][0]["expression"] == ["not_a_parameter"]


def test_wrong_value_type_is_400(client):
    response = client.post(
        "/Library/SqlOnFhirExample/$sqlquery-run",
        json=sqlonfhir_body({"name": "_limit", "valueString": "1"}),
    )
    assert response.status_code == 400
    assert "_limit" in response.json()["issue"][0]["diagnostics"]


def test_unknown_format_is_400(client):
    response = client.post(
        "/Library/SqlOnFhirExample/$sqlquery-run",
        json=sqlonfhir_body({"name": "_format", "valueCode": "xml"}),
    )
    assert response.status_code == 400
    assert response.json()["issue"][0]["code"] == "not-supported"


def test_unknown_source_is_400(client):
    response = client.post(
        "/Library/SqlOnFhirExample/$sqlquery-run",
        json=sqlonfhir_body({"name": "source", "valueString": "warehouse"}),
    )
    assert response.status_code == 400
    assert response.json()["issue"][0]["expression"] == ["source"]


def test_limit_caps_rows_after_evaluation(client):
    full = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=sqlonfhir_body())
    assert len(full.text.strip().splitlines()) == 2

    capped = client.post(
        "/Library/SqlOnFhirExample/$sqlquery-run",
        json=sqlonfhir_body({"name": "_limit", "valueInteger": 1}),
    )
    assert capped.status_code == 200
    assert len(capped.text.strip().splitlines()) == 1


def test_limit_above_the_server_cap_is_not_an_error(connection, store):
    """Capping is silent: fewer rows, still 200."""
    from fhir4ds.serve.app import create_app
    from fhir4ds.serve.config import ServeConfig

    capped_app = create_app(ServeConfig(
        admin_key=TEST_ADMIN_KEY,
        write_key=TEST_WRITE_KEY,
max_rows=1), connection=connection)
    with keyed_client(capped_app) as capped_client:
        response = capped_client.post(
            "/Library/SqlOnFhirExample/$sqlquery-run",
            json=sqlonfhir_body({"name": "_limit", "valueInteger": 500}),
        )
    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 1


def test_sql_execution_error_is_422(client):
    library = sqlquery_library("broken", "SELECT * FROM no_such_table")
    assert client.post("/Library", json=library).status_code == 201

    response = client.post("/Library/broken/$sqlquery-run")
    assert response.status_code == 422
    assert response.json()["resourceType"] == "OperationOutcome"


def test_dangling_dependency_is_404(client):
    """A resolver miss is a missing resource, not an execution failure."""
    library = library_with_dependency("https://example.org/ViewDefinition/absent")
    assert client.post("/Library", json=library).status_code == 201

    response = client.post("/Library/dangling/$sqlquery-run")
    assert response.status_code == 404
    assert response.json()["issue"][0]["code"] == "not-found"


def test_parameter_values_are_bound_not_interpolated(client):
    """Injection probe: the payload round-trips verbatim and nothing is dropped."""
    payload = "'; DROP TABLE resources; --"
    library = sqlquery_library(
        "echo",
        "SELECT :value AS echoed, (SELECT count(*) FROM resources) AS resource_count",
        parameters_declared=(("value", "string"),),
    )
    assert client.post("/Library", json=library).status_code == 201

    before = client.get("/ViewDefinition/patient-view/$run").text
    response = client.post("/Library/echo/$sqlquery-run", json=parameter_body({"value": payload}))
    assert response.status_code == 200

    row = json.loads(response.text.strip())
    assert row["echoed"] == payload
    assert row["resource_count"] == 9

    assert client.get("/ViewDefinition/patient-view/$run").text == before


# -- the IG example Libraries ----------------------------------------------


@pytest.mark.parametrize(
    ("library_id", "values", "expected_rows"),
    [
        ("SqlOnFhirExample", dict(SQLONFHIR_PARAMETERS), 2),
        ("UniquePatientAddressesQuery", {"city": "Boston"}, 2),
        ("OmopFhirPatientJoin", {"source_system": "EPIC"}, 2),
    ],
)
def test_ig_example_libraries_execute(client, library_id, values, expected_rows):
    assert client.get(f"/Library/{library_id}").status_code == 200

    response = client.post(f"/Library/{library_id}/$sqlquery-run", json=parameter_body(values))
    assert response.status_code == 200, response.text
    assert len(response.text.strip().splitlines()) == expected_rows
