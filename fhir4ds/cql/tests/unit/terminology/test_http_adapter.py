"""Unit tests for HTTPTerminologyEndpoint.

The httpx transport is mocked so these tests are hermetic and run
without a live medterm4ds sidecar.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fhir4ds.cql.terminology import CodeRef, SearchResult
from fhir4ds.cql.terminology.http_adapter import HTTPTerminologyEndpoint


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _expand_payload(contains: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a FHIR R4 ValueSet $expand response body."""
    return {
        "resourceType": "ValueSet",
        "expansion": {"contains": contains},
    }


def _search_bundle(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a $search Bundle response body."""
    return {
        "resourceType": "Bundle",
        "entry": [{"resource": e} for e in entries],
    }


class _MockResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _MockClient:
    """Captures calls and returns canned responses."""

    def __init__(self, response: _MockResponse, records: list[tuple[str, str, dict]]):
        self._response = response
        self._records = records

    def __enter__(self) -> "_MockClient":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def get(self, url: str, params: dict | None = None) -> _MockResponse:
        self._records.append(("GET", url, params or {}))
        return self._response

    def post(self, url: str, json: dict | None = None) -> _MockResponse:
        self._records.append(("POST", url, json or {}))
        return self._response


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------


def test_constructor_strips_trailing_slash():
    adapter = HTTPTerminologyEndpoint("http://localhost:8001/", timeout_seconds=3.0)
    assert adapter._base_url == "http://localhost:8001"


def test_constructor_requires_base_url():
    with pytest.raises(ValueError, match="base_url"):
        HTTPTerminologyEndpoint("", timeout_seconds=3.0)


def test_constructor_requires_finite_timeout():
    with pytest.raises(ValueError, match="positive float"):
        HTTPTerminologyEndpoint("http://localhost:8001", timeout_seconds=0)
    with pytest.raises(ValueError, match="positive float"):
        HTTPTerminologyEndpoint("http://localhost:8001", timeout_seconds=-1)


def test_constructor_rejects_none_timeout():
    """INV-6: no infinite hangs."""
    with pytest.raises(ValueError, match="positive float"):
        HTTPTerminologyEndpoint("http://localhost:8001", timeout_seconds=None)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# expand()
# ----------------------------------------------------------------------


def test_expand_invokes_get_with_canonical_url():
    payload = _expand_payload(
        [{"system": "http://snomed.info/sct", "code": "73211009", "display": "Diabetes"}]
    )
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001", timeout_seconds=5.0)
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        refs = adapter.expand("http://example.org/ValueSet/Foo")
    assert refs == [CodeRef("http://snomed.info/sct", "73211009", "Diabetes")]
    assert records == [
        (
            "GET",
            "http://localhost:8001/fhir/ValueSet/$expand",
            {"url": "http://example.org/ValueSet/Foo"},
        )
    ]


def test_expand_normalizes_snomed_module_url():
    """INV-5 regression: SNOMED module URLs reduce to base."""
    payload = _expand_payload(
        [
            {
                "system": "http://snomed.info/sct/731000124108",
                "code": "73211009",
            }
        ]
    )
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001")
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        refs = adapter.expand("http://example.org/ValueSet/Foo")
    assert len(refs) == 1
    assert refs[0].system == "http://snomed.info/sct"


def test_expand_empty_payload_returns_empty_list():
    payload = _expand_payload([])
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001")
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        assert adapter.expand("http://example.org/ValueSet/Empty") == []


def test_expand_skips_entries_missing_system_or_code():
    payload = _expand_payload(
        [
            {"system": "http://snomed.info/sct", "code": "73211009"},
            {"system": "http://snomed.info/sct"},  # missing code
            {"code": "12345"},  # missing system
        ]
    )
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001")
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        refs = adapter.expand("http://example.org/ValueSet/Foo")
    assert len(refs) == 1
    assert refs[0].code == "73211009"


# ----------------------------------------------------------------------
# expand_intensional()
# ----------------------------------------------------------------------


def test_expand_intensional_posts_value_set_body():
    payload = _expand_payload(
        [{"system": "http://snomed.info/sct", "code": "73211009"}]
    )
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001")
    body = {"resourceType": "ValueSet", "compose": {"include": []}}
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        refs = adapter.expand_intensional(body)
    assert refs == [CodeRef("http://snomed.info/sct", "73211009", None)]
    assert records[0][0] == "POST"
    assert records[0][1] == "http://localhost:8001/fhir/ValueSet/$expand"
    assert records[0][2] == body


# ----------------------------------------------------------------------
# search_text() / search_batch()
# ----------------------------------------------------------------------


def test_search_text_returns_search_results():
    payload = _search_bundle(
        [
            {
                "system": "http://snomed.info/sct",
                "code": "73211009",
                "display": "Diabetes mellitus",
                "score": 0.95,
                "matchGrade": "certain",
            }
        ]
    )
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001")
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        results = adapter.search_text("diabetes", "condition", mode="hybrid")
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, SearchResult)
    assert r.system == "http://snomed.info/sct"
    assert r.code == "73211009"
    assert r.score == pytest.approx(0.95)
    assert r.match_grade == "certain"
    assert r.search_mode == "hybrid"


def test_search_batch_loops_over_queries():
    payload = _search_bundle([])
    response = _MockResponse(payload)
    records: list[tuple[str, str, dict]] = []
    adapter = HTTPTerminologyEndpoint("http://localhost:8001")
    with patch.object(adapter, "_client", return_value=_MockClient(response, records)):
        results = adapter.search_batch([("diabetes", "condition"), ("metformin", "medication")])
    assert len(results) == 2
    assert results[0] == []
    assert results[1] == []
    assert len(records) == 2


# ----------------------------------------------------------------------
# Timeout behavior (INV-6)
# ----------------------------------------------------------------------


def test_client_passes_explicit_timeout():
    """Every httpx.Client constructor must receive a non-None timeout (INV-6)."""
    captured: dict[str, Any] = {}
    adapter = HTTPTerminologyEndpoint("http://localhost:8001", timeout_seconds=4.5)

    # httpx is imported lazily inside _client(); patch the real httpx
    # module attribute since the adapter no longer keeps it at module
    # top level (lazy-import discipline — see REV-001).
    import httpx as _httpx_mod

    class _ClientShim:
        def __init__(self, client_kwargs: dict[str, Any]) -> None:
            captured.update(client_kwargs)

        def __enter__(self) -> "_ClientShim":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, url: str, params: dict | None = None) -> _MockResponse:
            return _MockResponse(_expand_payload([]))

        def post(self, url: str, json: dict | None = None) -> _MockResponse:
            return _MockResponse(_expand_payload([]))

    with patch.object(_httpx_mod, "Client", side_effect=lambda **kwargs: _ClientShim(kwargs)):
        adapter.expand("http://example.org/ValueSet/Foo")

    assert captured.get("timeout") == 4.5
    assert captured.get("timeout") is not None


def test_client_called_with_timeout_kwarg_only():
    """Verify httpx.Client is constructed with keyword timeout= (INV-6)."""
    adapter = HTTPTerminologyEndpoint("http://localhost:8001", timeout_seconds=2.0)
    import httpx as _httpx_mod

    mock_client = MagicMock()
    mock_client.__enter__.return_value.get.return_value = _MockResponse(_expand_payload([]))
    with patch.object(_httpx_mod, "Client", return_value=mock_client) as mock_factory:
        adapter.expand("http://example.org/ValueSet/Foo")

    mock_factory.assert_called_once_with(timeout=2.0)
