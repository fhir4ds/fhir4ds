"""FHIR ``$cql`` ``terminologyEndpoint`` parameter handling.

Phase 1.5 (medterm4ds) integration: the ``terminologyEndpoint`` parameter is
no longer in ``_UNSUPPORTED_TOP_LEVEL`` and is parsed into a URL string on
``CQLRequest``. The expression service converts it to an
``HTTPTerminologyEndpoint`` lazily (zero-dep default preserved).
"""

from __future__ import annotations

import pytest

from fhir4ds.cql.fhir_server.expression_service import _build_endpoint
from fhir4ds.cql.fhir_server.parameters import parse_cql_request
from fhir4ds.cql.fhir_server.types import CQLFacadeError, CQLRequest


# ---------------------------------------------------------------------------
# Parameter parsing
# ---------------------------------------------------------------------------


def test_terminology_endpoint_not_in_unsupported_set():
    """``terminologyEndpoint`` must have been removed from the reject-list."""
    from fhir4ds.cql.fhir_server.parameters import _UNSUPPORTED_TOP_LEVEL

    assert "terminologyEndpoint" not in _UNSUPPORTED_TOP_LEVEL


def test_request_accepts_terminology_endpoint():
    """``terminologyEndpoint`` is parsed onto CQLRequest without error."""
    request = parse_cql_request(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "expression", "valueString": "1 + 2"},
                {
                    "name": "terminologyEndpoint",
                    "valueUrl": "http://localhost:8001",
                },
            ],
        }
    )
    assert request.expression == "1 + 2"
    assert request.terminology_endpoint_url == "http://localhost:8001"


def test_request_without_terminology_endpoint_defaults_to_none():
    """Absent ``terminologyEndpoint`` → None on CQLRequest."""
    request = parse_cql_request(
        {
            "resourceType": "Parameters",
            "parameter": [{"name": "expression", "valueString": "1 + 2"}],
        }
    )
    assert request.terminology_endpoint_url is None


def test_request_with_disabled_endpoint_yields_none():
    """``terminologyEndpoint=disabled`` → None (literal-match fallback)."""
    request = parse_cql_request(
        {
            "resourceType": "Parameters",
            "parameter": [
                {"name": "expression", "valueString": "1 + 2"},
                {"name": "terminologyEndpoint", "valueUrl": "disabled"},
            ],
        }
    )
    assert request.terminology_endpoint_url is None


def test_request_with_disabled_endpoint_case_insensitive():
    """``DISABLED`` and ``Disabled`` also map to None."""
    for variant in ("DISABLED", "Disabled", "  disabled  "):
        request = parse_cql_request(
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "expression", "valueString": "1 + 2"},
                    {"name": "terminologyEndpoint", "valueUrl": variant},
                ],
            }
        )
        assert request.terminology_endpoint_url is None, variant


def test_request_rejects_multiple_terminology_endpoints():
    """At most one ``terminologyEndpoint`` parameter."""
    with pytest.raises(CQLFacadeError) as exc_info:
        parse_cql_request(
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "expression", "valueString": "1 + 2"},
                    {
                        "name": "terminologyEndpoint",
                        "valueUrl": "http://a",
                    },
                    {
                        "name": "terminologyEndpoint",
                        "valueUrl": "http://b",
                    },
                ],
            }
        )
    assert exc_info.value.category == "invalid-request"


def test_request_rejects_empty_terminology_endpoint_url():
    """``valueUrl`` must be a non-empty string."""
    with pytest.raises(CQLFacadeError) as exc_info:
        parse_cql_request(
            {
                "resourceType": "Parameters",
                "parameter": [
                    {"name": "expression", "valueString": "1 + 2"},
                    {"name": "terminologyEndpoint", "valueUrl": "  "},
                ],
            }
        )
    assert exc_info.value.category == "invalid-request"


# ---------------------------------------------------------------------------
# URL → HTTPTerminologyEndpoint conversion
# ---------------------------------------------------------------------------


def test_build_endpoint_none_for_none_url():
    assert _build_endpoint(None) is None


def test_build_endpoint_none_for_empty_url():
    assert _build_endpoint("") is None


def test_build_endpoint_returns_http_terminology_endpoint():
    """A URL string yields an HTTPTerminologyEndpoint instance."""
    endpoint = _build_endpoint("http://localhost:8001")
    # Don't import HTTPTerminologyEndpoint at module top to keep zero-dep.
    from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint

    assert isinstance(endpoint, HTTPTerminologyEndpoint)


def test_build_endpoint_strips_trailing_slash():
    """Trailing slash in URL is stripped by HTTPTerminologyEndpoint."""
    endpoint = _build_endpoint("http://localhost:8001/")
    assert endpoint._base_url == "http://localhost:8001"


# ---------------------------------------------------------------------------
# Default request dataclass shape
# ---------------------------------------------------------------------------


def test_cql_request_dataclass_default_terminology_url_is_none():
    """Default ``terminology_endpoint_url`` is ``None``."""
    request = CQLRequest(expression="1")
    assert request.terminology_endpoint_url is None
