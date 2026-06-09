"""Integration tests for the local FHIR $cql facade."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from fhir4ds.cql.fhir_server import CQLServerConfig, create_http_server, handle_cql_operation


def _body(expression: str) -> dict:
    return {
        "resourceType": "Parameters",
        "parameter": [{"name": "expression", "valueString": expression}],
    }


def test_handle_cql_operation_evaluates_scalar_expression():
    status, body = handle_cql_operation(_body("1 + 2"), CQLServerConfig(use_cpp_extensions=False))

    assert status == 200
    assert body == {
        "resourceType": "Parameters",
        "parameter": [{"name": "return", "valueInteger": 3}],
    }


def test_handle_cql_operation_serializes_complex_values():
    status, body = handle_cql_operation(
        _body("Tuple { a: 1, b: @2024-01-01 }"),
        CQLServerConfig(use_cpp_extensions=False),
    )

    assert status == 200
    assert body["parameter"][0]["part"] == [
        {"name": "a", "valueInteger": 1},
        {"name": "b", "valueDate": "2024-01-01"},
    ]


def test_handle_cql_operation_returns_evaluation_error_parameter():
    status, body = handle_cql_operation(
        _body("1 and 2"),
        CQLServerConfig(use_cpp_extensions=False),
    )

    assert status == 200
    assert body["parameter"][0]["name"] == "evaluation error"
    assert body["parameter"][0]["resource"]["resourceType"] == "OperationOutcome"


def test_handle_cql_operation_serializes_uncertainty_interval():
    status, body = handle_cql_operation(
        _body("years between DateTime(2005) and DateTime(2010)"),
        CQLServerConfig(use_cpp_extensions=False),
    )

    assert status == 200
    assert body["parameter"][0]["part"] == [
        {"name": "lowClosed", "valueBoolean": True},
        {"name": "low", "valueInteger": 4},
        {"name": "highClosed", "valueBoolean": True},
        {"name": "high", "valueInteger": 5},
    ]


def test_handle_cql_operation_reconciles_quantity_aggregate_metadata():
    status, body = handle_cql_operation(
        _body("Sum({1 'ml',2 'ml',3 'ml',4 'ml',5 'ml'})"),
        CQLServerConfig(use_cpp_extensions=False),
    )

    assert status == 200
    assert body["parameter"][0]["valueQuantity"] == {
        "value": 15.0,
        "unit": "ml",
        "system": "http://unitsofmeasure.org",
        "code": "ml",
    }


def test_handle_cql_operation_preserves_long_result_metadata():
    cases = {
        "1L + 2L": "3L",
        "maximum Long": "9223372036854775807L",
        "Product({5L, 4L, 5L})": "100L",
    }

    for expression, expected in cases.items():
        status, body = handle_cql_operation(
            _body(expression),
            CQLServerConfig(use_cpp_extensions=False),
        )

        assert status == 200
        param = body["parameter"][0]
        assert param["valueString"] == expected
        assert param["extension"][0]["valueString"] == "System.Long"


def test_handle_cql_operation_serializes_code_only_concept():
    status, body = handle_cql_operation(
        _body("ToConcept(Code { code: '8480-6' })"),
        CQLServerConfig(use_cpp_extensions=False),
    )

    assert status == 200
    assert body["parameter"][0]["valueCodeableConcept"] == {
        "coding": [{"code": "8480-6"}]
    }


def test_http_server_accepts_fhir_base_cql_path():
    server = create_http_server(CQLServerConfig(host="127.0.0.1", port=0, use_cpp_extensions=False))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        request = urllib.request.Request(
            f"http://{host}:{port}/fhir/$cql",
            data=json.dumps(_body("1 + 2")).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            body = json.loads(response.read().decode("utf-8"))
        assert body["parameter"][0]["valueInteger"] == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_server_rejects_oversized_request():
    server = create_http_server(
        CQLServerConfig(
            host="127.0.0.1",
            port=0,
            use_cpp_extensions=False,
            max_request_bytes=4,
        )
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        request = urllib.request.Request(
            f"http://{host}:{port}/$cql",
            data=b"{}{}{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 413
        else:
            raise AssertionError("Expected oversized request to be rejected")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
