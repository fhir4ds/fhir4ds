"""Unit tests for the DependencyResolver terminology-endpoint fallback hook.

These tests verify:
    * INV-2: ``terminology_endpoint=None`` preserves existing behavior.
    * INV-8: endpoint exceptions degrade to ``None`` + WARNING inside the
      resolver fallback path (no exceptions escape).
    * Local match always wins (endpoint is never consulted for a hit).
    * Endpoint-resolved ValueSets carry ``provenance="terminology_endpoint"``
      and ``source_path=None``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from fhir4ds.cql.dependency import DependencyResolver
from fhir4ds.cql.dependency.types import ResolvedValueSet
from fhir4ds.cql.terminology import CodeRef


class _StubEndpoint:
    """In-memory endpoint implementing the TerminologyEndpoint protocol."""

    def __init__(
        self,
        *,
        expand_result: Optional[list[CodeRef]] = None,
        expand_exception: Optional[Exception] = None,
    ) -> None:
        self.expand_result = expand_result
        self.expand_exception = expand_exception
        self.expand_calls: list[str] = []

    def expand(self, valueset_url: str) -> list[CodeRef]:
        self.expand_calls.append(valueset_url)
        if self.expand_exception is not None:
            raise self.expand_exception
        return self.expand_result or []

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        return []

    def search_text(
        self, query: str, category: str, *, mode: str = "hybrid"
    ):  # pragma: no cover - not exercised by resolver
        return []

    def search_batch(
        self, queries: list[tuple[str, str]], *, mode: str = "hybrid"
    ):  # pragma: no cover - not exercised by resolver
        return []


# ----------------------------------------------------------------------
# Regression: terminology_endpoint=None is the byte-identical default.
# ----------------------------------------------------------------------


def test_none_endpoint_preserves_existing_behavior(tmp_path: Path) -> None:
    """Without an endpoint, miss returns None exactly as before (INV-2)."""
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=None)
    assert resolver.resolve_valueset("http://example.org/ValueSet/Missing") is None


def test_default_construction_equivalent_to_none_endpoint(tmp_path: Path) -> None:
    """Omitting the kwarg is identical to passing None explicitly."""
    resolver_default = DependencyResolver(paths=[tmp_path])
    resolver_explicit = DependencyResolver(paths=[tmp_path], terminology_endpoint=None)
    # Local miss behavior identical.
    url = "http://example.org/ValueSet/Missing"
    assert resolver_default.resolve_valueset(url) is None
    assert resolver_explicit.resolve_valueset(url) is None


# ----------------------------------------------------------------------
# Fallback hit.
# ----------------------------------------------------------------------


def test_endpoint_returns_codes_synthesizes_resolved_valueset(tmp_path: Path) -> None:
    endpoint = _StubEndpoint(
        expand_result=[
            CodeRef(system="http://snomed.info/sct", code="73211009", display="Diabetes")
        ]
    )
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=endpoint)

    vs = resolver.resolve_valueset("http://example.org/ValueSet/Remote")
    assert vs is not None
    assert vs.url == "http://example.org/ValueSet/Remote"
    assert vs.provenance == "terminology_endpoint"
    assert vs.source_path is None
    assert vs.codes == [
        {
            "system": "http://snomed.info/sct",
            "code": "73211009",
            "display": "Diabetes",
        }
    ]
    assert endpoint.expand_calls == ["http://example.org/ValueSet/Remote"]


def test_endpoint_returns_empty_returns_none(tmp_path: Path) -> None:
    endpoint = _StubEndpoint(expand_result=[])
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=endpoint)
    assert resolver.resolve_valueset("http://example.org/ValueSet/Empty") is None


# ----------------------------------------------------------------------
# INV-8: failure degradation.
# ----------------------------------------------------------------------


def test_endpoint_exception_returns_none_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Any endpoint exception is swallowed and logged as WARNING (INV-8)."""
    endpoint = _StubEndpoint(expand_exception=RuntimeError("network down"))
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=endpoint)

    with caplog.at_level(logging.WARNING, logger="fhir4ds.cql.dependency.resolver"):
        result = resolver.resolve_valueset("http://example.org/ValueSet/Remote")
    assert result is None
    assert any(
        "terminology endpoint expand failed" in rec.message for rec in caplog.records
    ), f"expected WARNING in log; got: {[r.message for r in caplog.records]}"


def test_httpx_connect_error_returns_none(tmp_path: Path) -> None:
    """The factory's typical failure mode (httpx.ConnectError) is swallowed."""
    try:
        import httpx
        exc: Exception = httpx.ConnectError("connection refused")
    except ImportError:  # pragma: no cover - httpx should be installed
        exc = RuntimeError("connection refused")
    endpoint = _StubEndpoint(expand_exception=exc)
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=endpoint)
    assert resolver.resolve_valueset("http://example.org/ValueSet/Remote") is None


# ----------------------------------------------------------------------
# Local match always wins.
# ----------------------------------------------------------------------


def test_local_match_wins_over_endpoint(tmp_path: Path) -> None:
    """Pre-loaded local ValueSet must short-circuit the endpoint call."""
    vs_file = tmp_path / "LocalVS.json"
    vs_file.write_text(
        json.dumps(
            {
                "resourceType": "ValueSet",
                "url": "http://example.org/ValueSet/Local",
                "status": "active",
                "expansion": {
                    "contains": [
                        {"system": "http://loinc.org", "code": "12345", "display": "Local"}
                    ]
                },
            }
        )
    )
    endpoint = _StubEndpoint(
        expand_result=[CodeRef(system="http://snomed.info/sct", code="WRONG")]
    )
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=endpoint)
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Local")
    assert vs is not None
    assert vs.provenance == "local_file"
    assert vs.source_path == vs_file
    assert vs.codes == [{"system": "http://loinc.org", "code": "12345", "display": "Local"}]
    # Endpoint should never have been called.
    assert endpoint.expand_calls == []


# ----------------------------------------------------------------------
# source_path=None is a new, well-defined state.
# ----------------------------------------------------------------------


def test_endpoint_resolved_valueset_has_none_source_path(tmp_path: Path) -> None:
    endpoint = _StubEndpoint(
        expand_result=[CodeRef(system="http://snomed.info/sct", code="73211009")]
    )
    resolver = DependencyResolver(paths=[tmp_path], terminology_endpoint=endpoint)
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Remote")
    assert vs is not None
    assert vs.source_path is None
    # And provenance is set to mark the origin.
    assert vs.provenance == "terminology_endpoint"


def test_local_resolved_valueset_has_local_file_provenance(tmp_path: Path) -> None:
    """Existing local path keeps the default provenance marker."""
    vs_file = tmp_path / "Local.json"
    vs_file.write_text(
        json.dumps(
            {
                "resourceType": "ValueSet",
                "url": "http://example.org/ValueSet/Local",
                "status": "active",
                "expansion": {"contains": []},
            }
        )
    )
    resolver = DependencyResolver(paths=[tmp_path])
    vs = resolver.resolve_valueset("http://example.org/ValueSet/Local")
    assert vs is not None
    assert vs.provenance == "local_file"
    assert vs.source_path == vs_file
