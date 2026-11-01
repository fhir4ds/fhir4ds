"""Capability layer and resource store (no HTTP in this module)."""

from __future__ import annotations

import pytest

from fhir4ds.operations.capabilities.sqlquery import sqlquery_run
from fhir4ds.operations.capabilities.viewdefinition_run import (
    normalize_view_definition,
    viewdefinition_run,
)
from fhir4ds.serve.store import ResourceNotFound, split_reference

from ._helpers import SQLONFHIR_PARAMETERS, view_fixture

# -- capabilities -----------------------------------------------------------


def test_sqlquery_run_returns_typed_columns(connection, store):
    library = store.get("Library", "SqlOnFhirExample")
    result = sqlquery_run(
        library,
        connection=connection,
        resolver=store.resolver(),
        parameters=dict(SQLONFHIR_PARAMETERS),
    )
    assert result.ok
    assert result.column_names == (
        "patient_id",
        "name",
        "systolic",
        "diastolic",
        "effective_date",
    )
    by_name = {column.name: column for column in result.columns}
    assert by_name["systolic"].normalized_sql_type == "DOUBLE"
    assert by_name["systolic"].fhir_type == "valueDecimal"
    assert by_name["effective_date"].fhir_type == "valueDate"
    assert by_name["patient_id"].fhir_type == "valueString"
    assert len(result.rows) == 2


def test_sqlquery_run_envelope_is_serializable(connection, store):
    library = store.get("Library", "OmopFhirPatientJoin")
    result = sqlquery_run(
        library,
        connection=connection,
        resolver=store.resolver(),
        parameters={"source_system": "EPIC"},
    )
    payload = result.to_dict()
    assert payload["schema"] == 1
    assert payload["ok"] is True
    assert len(payload["columns"]) == 5
    assert len(payload["rows"]) == 2


def test_sqlquery_run_reports_a_parse_error(connection, store):
    result = sqlquery_run(
        {"resourceType": "Library", "status": "active"},
        connection=connection,
        resolver=store.resolver(),
    )
    assert not result.ok
    assert result.rows == ()
    assert result.diagnostics[0].code.value == "parse_error"


def test_sqlquery_run_maps_a_resolver_miss_to_not_found(connection, store):
    library = store.get("Library", "UniquePatientAddressesQuery")

    def missing(canonical):
        raise ResourceNotFound(canonical)

    result = sqlquery_run(library, connection=connection, resolver=missing)
    assert not result.ok
    assert result.diagnostics[0].code.value == "not_found"


def test_sqlquery_run_applies_a_limit(connection, store):
    library = store.get("Library", "UniquePatientAddressesQuery")
    result = sqlquery_run(
        library,
        connection=connection,
        resolver=store.resolver(),
        parameters={"city": "Boston"},
        limit=1,
    )
    assert len(result.rows) == 1


def test_viewdefinition_run_returns_typed_columns(connection):
    view = view_fixture("patient-view")
    result = viewdefinition_run(view, connection=connection)
    assert result.ok
    by_name = {column.name: column for column in result.columns}
    assert by_name["active"].fhir_type == "valueBoolean"
    assert by_name["id"].fhir_type == "valueString"
    assert len(result.rows) == 3


def test_viewdefinition_run_reports_parse_errors(connection):
    result = viewdefinition_run({"resource": "Patient"}, connection=connection)
    assert not result.ok
    assert result.diagnostics[0].code.value == "parse_error"


def test_viewdefinition_run_reports_execution_errors(connection):
    """A generated query against a missing table is an execution error."""
    result = viewdefinition_run(
        view_fixture("patient-view"), connection=connection, source_table="missing_table"
    )
    assert not result.ok
    assert result.diagnostics[0].code.value == "evaluation_error"


def test_viewdefinition_run_reports_declaration_errors(connection):
    view = {
        "resourceType": "ViewDefinition",
        "resource": "Patient",
        "select": [{"column": [{"name": "id", "type": "not-a-type", "path": "id"}]}],
    }
    result = viewdefinition_run(view, connection=connection)
    assert not result.ok
    assert result.diagnostics[0].code.value in {"translation_error", "parse_error"}


def test_normalize_view_definition_drops_the_fhir_resource_type_spelling():
    view = {"resourceType": "ViewDefinition", "resource": "Patient", "select": []}
    assert normalize_view_definition(view) == {"resource": "Patient", "select": []}


def test_normalize_view_definition_keeps_a_canonical_resource_type():
    view = {
        "resourceType": "https://sql-on-fhir.org/ig/StructureDefinition/ViewDefinition",
        "resource": "Patient",
    }
    assert normalize_view_definition(view) is view


# -- store ------------------------------------------------------------------


def test_store_round_trips_a_resource(store):
    library = store.get("Library", "SqlOnFhirExample")
    assert library["resourceType"] == "Library"


def test_store_lists_resources_deterministically(store):
    first = [resource["id"] for resource in store.search("Library")]
    second = [resource["id"] for resource in store.search("Library")]
    assert first == second == sorted(first)


@pytest.mark.parametrize(
    "canonical",
    [
        "https://sql-on-fhir.org/ig/Library/SqlOnFhirExample",
        "https://sql-on-fhir.org/ig/Library/SqlOnFhirExample|1.0.0",
        "Library/SqlOnFhirExample",
        "SqlOnFhirExample",
    ],
)
def test_store_resolves_canonical_forms(store, canonical):
    resource = store.find_by_canonical(canonical)
    assert resource is not None
    assert resource["id"] == "SqlOnFhirExample"


def test_store_returns_none_for_an_unknown_canonical(store):
    assert store.find_by_canonical("https://example.org/ViewDefinition/nope") is None


def test_store_resolver_raises_lookup_error(store):
    with pytest.raises(ResourceNotFound) as caught:
        store.resolver()("https://example.org/ViewDefinition/nope")
    assert isinstance(caught.value, LookupError)


def test_store_resolver_hands_the_engine_a_parseable_view_definition(store):
    resolved = store.resolve_dependency("https://example.org/ViewDefinition/patient_view")
    assert "resourceType" not in resolved


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("ViewDefinition/abc", ("ViewDefinition", "abc")),
        ("Library/abc", ("Library", "abc")),
        ("https://example.org/fhir/Library/abc", ("Library", "abc")),
        ("https://example.org/fhir/ViewDefinition/abc|2.0", ("ViewDefinition", "abc|2.0")),
        ("abc", (None, None)),
    ],
)
def test_split_reference(reference, expected):
    assert split_reference(reference) == expected
