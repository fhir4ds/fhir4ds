"""Output formats: negotiation, flat encoders, parquet, and ``_format=fhir``.

Covers both the pure encoders (unit) and the endpoint matrix that the
SQL-on-FHIR IG mandates (integration).
"""

from __future__ import annotations

import io
import json
from decimal import Decimal

import pytest

from fhir4ds.operations.capabilities.tabular import (
    ResultColumn,
    TabularResult,
    fhir_value_type_for_sql_type,
    normalize_sql_type,
)
from fhir4ds.serve import formats
from fhir4ds.serve.errors import ServeError

from ._helpers import (
    SQLONFHIR_PARAMETERS,
    parameters,
    parameters_resource,
    sqlquery_library,
)

MIXED_SQL = """
SELECT
  CAST(1 AS INTEGER) AS i,
  CAST(9223372036854775807 AS BIGINT) AS big,
  CAST(1.5 AS DECIMAL(18,3)) AS d,
  CAST(true AS BOOLEAN) AS b,
  CAST(NULL AS VARCHAR) AS s,
  CAST('2024-01-15' AS DATE) AS dt,
  CAST('10:00:00' AS TIME) AS t,
  CAST('2024-01-15 10:30:00' AS TIMESTAMP) AS ts
"""


def _mixed_client(client):
    library = sqlquery_library("mixed", MIXED_SQL)
    assert client.post("/Library", json=library).status_code == 201
    return client


# -- type mapping (unit) ----------------------------------------------------


@pytest.mark.parametrize(
    ("sql_type", "expected"),
    [
        ("BOOLEAN", "valueBoolean"),
        ("TINYINT", "valueInteger"),
        ("SMALLINT", "valueInteger"),
        ("INTEGER", "valueInteger"),
        ("BIGINT", "valueInteger64"),
        ("DECIMAL(18,3)", "valueDecimal"),
        ("NUMERIC(10,2)", "valueDecimal"),
        ("REAL", "valueDecimal"),
        ("DOUBLE", "valueDecimal"),
        ("VARCHAR", "valueString"),
        ("CHAR(4)", "valueString"),
        ("BLOB", "valueBase64Binary"),
        ("DATE", "valueDate"),
        ("TIME", "valueTime"),
        ("TIME WITH TIME ZONE", "valueTime"),
        ("TIMESTAMP", "valueDateTime"),
        ("TIMESTAMP WITH TIME ZONE", "valueInstant"),
    ],
)
def test_ig_sql_to_fhir_type_mapping(sql_type, expected):
    assert fhir_value_type_for_sql_type(sql_type) == expected


@pytest.mark.parametrize("sql_type", ["INTERVAL", "HUGEINT", "STRUCT(a INTEGER)", "JSON", "UUID"])
def test_unmapped_sql_types_have_no_fhir_mapping(sql_type):
    assert fhir_value_type_for_sql_type(sql_type) is None


def test_normalize_sql_type_strips_length_and_keeps_timezone_qualifier():
    assert normalize_sql_type("DECIMAL(18,3)") == "DECIMAL"
    assert normalize_sql_type("timestamp with time zone") == "TIMESTAMP WITH TIME ZONE"


# -- negotiation (unit) -----------------------------------------------------


def test_format_precedence():
    assert formats.negotiate_format("csv", "application/json") == "csv"
    assert formats.negotiate_format(None, "application/json") == "json"
    assert formats.negotiate_format(None, None) == "ndjson"
    assert formats.negotiate_format(None, "text/csv;q=0.9") == "csv"
    assert formats.negotiate_format(None, "application/xml") == "ndjson"


def test_unknown_explicit_format_is_rejected():
    with pytest.raises(ServeError) as caught:
        formats.negotiate_format("xlsx", None)
    assert caught.value.status_code == 400
    assert caught.value.issues[0].code == "not-supported"


# -- fhir encoding (unit) ---------------------------------------------------


def _result(columns, rows):
    return TabularResult(
        columns=tuple(ResultColumn(name=name, sql_type=type_) for name, type_ in columns),
        rows=tuple(rows),
    )


def test_parameters_omit_null_parts():
    result = _result(
        [("a", "VARCHAR"), ("b", "INTEGER")],
        [("x", None), (None, 2)],
    )
    document = formats.to_parameters(result)
    assert document == {
        "resourceType": "Parameters",
        "parameter": [
            {"name": "row", "part": [{"name": "a", "valueString": "x"}]},
            {"name": "row", "part": [{"name": "b", "valueInteger": 2}]},
        ],
    }


def test_parameters_with_zero_rows_have_no_parameter_element():
    document = formats.to_parameters(_result([("a", "VARCHAR")], []))
    assert document == {"resourceType": "Parameters"}


def test_integer64_encodes_as_a_json_string():
    document = formats.to_parameters(_result([("big", "BIGINT")], [(2**62,)]))
    part = document["parameter"][0]["part"][0]
    assert part == {"name": "big", "valueInteger64": str(2**62)}


def test_instant_rounds_to_milliseconds_and_keeps_an_offset():
    import datetime

    naive = datetime.datetime(2024, 1, 15, 10, 30, 0, 123_600)
    assert formats.fhir_value("valueInstant", naive) == "2024-01-15T10:30:00.124"

    aware = datetime.datetime(2024, 1, 15, 10, 30, 0, 123_600, tzinfo=datetime.timezone.utc)
    assert formats.fhir_value("valueInstant", aware) == "2024-01-15T10:30:00.124Z"


def test_unmapped_column_is_422_under_fhir_format():
    with pytest.raises(ServeError) as caught:
        formats.to_parameters(_result([("iv", "INTERVAL")], [("1 day",)]))
    assert caught.value.status_code == 422


def test_decimal_encoding_is_json_numeric():
    document = formats.to_parameters(_result([("d", "DECIMAL(18,3)")], [(Decimal("1.500"),)]))
    assert document["parameter"][0]["part"][0] == {"name": "d", "valueDecimal": 1.5}


# -- endpoint matrix (integration) ------------------------------------------


def test_fhir_format_matches_the_ig_row_part_shape(client):
    _mixed_client(client)
    response = client.post(
        "/Library/mixed/$sqlquery-run",
        json=parameters({"name": "_format", "valueCode": "fhir"}),
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")

    document = response.json()
    assert document["resourceType"] == "Parameters"
    assert len(document["parameter"]) == 1

    row = document["parameter"][0]
    assert row["name"] == "row"
    parts = {part["name"]: part for part in row["part"]}
    assert parts["i"] == {"name": "i", "valueInteger": 1}
    assert parts["big"] == {"name": "big", "valueInteger64": "9223372036854775807"}
    assert parts["d"] == {"name": "d", "valueDecimal": 1.5}
    assert parts["b"] == {"name": "b", "valueBoolean": True}
    assert parts["dt"] == {"name": "dt", "valueDate": "2024-01-15"}
    assert parts["t"] == {"name": "t", "valueTime": "10:00:00"}
    assert parts["ts"] == {"name": "ts", "valueDateTime": "2024-01-15T10:30:00"}
    # SQL NULL omits the part entirely.
    assert "s" not in parts


def test_fhir_format_rejects_an_unmapped_column_with_422(client):
    library = sqlquery_library("interval", "SELECT CAST(INTERVAL 1 DAY AS INTERVAL) AS iv")
    assert client.post("/Library", json=library).status_code == 201

    response = client.post(
        "/Library/interval/$sqlquery-run",
        json=parameters({"name": "_format", "valueCode": "fhir"}),
    )
    assert response.status_code == 422
    assert response.json()["resourceType"] == "OperationOutcome"

    # The same query is fine for the flat formats.
    assert client.post("/Library/interval/$sqlquery-run").status_code == 200


def test_csv_has_a_header_row_by_default(client):
    body = parameters(
        {
            "name": "parameters",
            "resource": parameters_resource(
                *[{"name": name, "valueString": value} for name, value in SQLONFHIR_PARAMETERS]
            ),
        },
        {"name": "_format", "valueCode": "csv"},
    )
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0] == "patient_id,name,systolic,diastolic,effective_date"
    assert len(lines) == 3


def test_csv_header_can_be_disabled(client):
    body = parameters(
        {
            "name": "parameters",
            "resource": parameters_resource(
                *[{"name": name, "valueString": value} for name, value in SQLONFHIR_PARAMETERS]
            ),
        },
        {"name": "_format", "valueCode": "csv"},
        {"name": "header", "valueBoolean": False},
    )
    response = client.post("/Library/SqlOnFhirExample/$sqlquery-run", json=body)
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("Patient/pt-1,")


def test_json_format_returns_an_array_of_objects(client):
    _mixed_client(client)
    response = client.post(
        "/Library/mixed/$sqlquery-run",
        json=parameters({"name": "_format", "valueCode": "json"}),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    rows = response.json()
    assert isinstance(rows, list)
    assert rows[0]["i"] == 1
    assert rows[0]["s"] is None


def test_parquet_body_is_a_valid_parquet_file(client):
    import pyarrow.parquet as pq

    _mixed_client(client)
    response = client.post(
        "/Library/mixed/$sqlquery-run",
        json=parameters({"name": "_format", "valueCode": "parquet"}),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"

    table = pq.read_table(io.BytesIO(response.content))
    assert table.num_rows == 1
    assert table.column_names == ["i", "big", "d", "b", "s", "dt", "t", "ts"]
    assert table.column("i").to_pylist() == [1]
    assert table.column("b").to_pylist() == [True]
    assert table.column("s").to_pylist() == [None]


def test_accept_header_selects_the_format_when_format_is_absent(client):
    response = client.post(
        "/ViewDefinition/patient-view/$run", headers={"Accept": "text/csv"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_format_parameter_beats_accept_header(client):
    response = client.post(
        "/ViewDefinition/patient-view/$run",
        headers={"Accept": "text/csv"},
        json=parameters({"name": "_format", "valueCode": "json"}),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


def test_ndjson_empty_result_is_an_empty_body(client):
    library = sqlquery_library(
        "empty", "SELECT 1 AS one WHERE false"
    )
    assert client.post("/Library", json=library).status_code == 201
    response = client.post("/Library/empty/$sqlquery-run")
    assert response.status_code == 200
    assert response.text == ""


def test_json_empty_result_is_an_empty_array(client):
    library = sqlquery_library("empty2", "SELECT 1 AS one WHERE false")
    assert client.post("/Library", json=library).status_code == 201
    response = client.post(
        "/Library/empty2/$sqlquery-run", json=parameters({"name": "_format", "valueCode": "json"})
    )
    assert json.loads(response.text) == []


def test_fhir_empty_result_is_a_parameters_resource_without_rows(client):
    library = sqlquery_library("empty3", "SELECT 1 AS one WHERE false")
    assert client.post("/Library", json=library).status_code == 201
    response = client.post(
        "/Library/empty3/$sqlquery-run", json=parameters({"name": "_format", "valueCode": "fhir"})
    )
    assert response.json() == {"resourceType": "Parameters"}
