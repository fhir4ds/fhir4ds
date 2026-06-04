"""Tests for FHIR $cql Parameters parsing."""

from __future__ import annotations

import pytest

from fhir4ds.cql.fhir_server.parameters import parse_cql_request
from fhir4ds.cql.fhir_server.types import CQLFacadeError


def test_parse_runner_expression_request():
    request = parse_cql_request(
        {
            "resourceType": "Parameters",
            "parameter": [{"name": "expression", "valueString": "1 + 2"}],
        }
    )

    assert request.expression == "1 + 2"
    assert request.parameters == ()


def test_parse_nested_input_parameters_to_cql_defaults():
    request = parse_cql_request(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "expression", "valueString": "P + Count(L)"},
                {
                    "name": "parameters",
                    "part": [
                        {"name": "P", "valueInteger": 5},
                        {"name": "L", "valueString": "a"},
                        {"name": "L", "valueString": "b"},
                    ],
                },
            ],
        }
    )

    assert request.parameters[0].name == "P"
    assert request.parameters[0].cql_type == "Integer"
    assert request.parameters[0].literal == "5"
    assert request.parameters[1].name == "L"
    assert request.parameters[1].cql_type == "List<String>"
    assert request.parameters[1].literal == "{'a', 'b'}"


def test_parse_tuple_input_parameter():
    request = parse_cql_request(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "expression", "valueString": "P"},
                {
                    "name": "parameters",
                    "part": [
                        {
                            "name": "P",
                            "part": [
                                {"name": "a", "valueInteger": 1},
                                {"name": "b", "valueString": "x"},
                            ],
                        }
                    ],
                },
            ],
        }
    )

    assert request.parameters[0].cql_type == "Tuple{a: Integer, b: String}"
    assert request.parameters[0].literal == "Tuple { a: 1, b: 'x' }"


def test_rejects_unsupported_data_endpoint():
    with pytest.raises(CQLFacadeError) as exc_info:
        parse_cql_request(
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "expression", "valueString": "1"},
                    {"name": "dataEndpoint", "valueString": "http://example.org"},
                ],
            }
        )

    assert exc_info.value.category == "unsupported-feature"


def test_requires_single_expression():
    with pytest.raises(CQLFacadeError):
        parse_cql_request({"resourceType": "Parameters", "parameter": []})


def test_rejects_malformed_nested_parameter_values():
    for malformed in (
        {"name": "P", "valueDecimal": "not-a-number"},
        {"name": "P", "valueBoolean": "true"},
        {"name": "P", "valuePeriod": "2024-01-01/2024-02-01"},
        {"name": "P", "part": "not-an-array"},
        {"name": "P", "valueCodeableConcept": {"coding": "not-an-array"}},
    ):
        with pytest.raises(CQLFacadeError) as exc_info:
            parse_cql_request(
                {
                    "resourceType": "Parameters",
                    "parameter": [
                        {"name": "expression", "valueString": "P"},
                        {"name": "parameters", "part": [malformed]},
                    ],
                }
            )

        assert exc_info.value.category == "invalid-request"
