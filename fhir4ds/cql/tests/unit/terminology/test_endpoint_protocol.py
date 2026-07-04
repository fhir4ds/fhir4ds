"""Test that TerminologyEndpoint is a structural (runtime-checkable) Protocol.

A plain stub class implementing the four required methods (without
inheriting from the Protocol) must satisfy ``isinstance`` via structural
typing.
"""

from __future__ import annotations

from fhir4ds.cql.terminology import (
    CodeRef,
    SearchResult,
    TerminologyEndpoint,
)


class _StubEndpoint:
    """Trivial stub that satisfies the Protocol surface."""

    def expand(self, valueset_url: str) -> list[CodeRef]:
        return [CodeRef(system="http://snomed.info/sct", code="73211009")]

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        return []

    def search_text(
        self, query: str, category: str, *, mode: str = "hybrid"
    ) -> list[SearchResult]:
        return []

    def search_batch(
        self, queries: list[tuple[str, str]], *, mode: str = "hybrid"
    ) -> list[list[SearchResult]]:
        return []


class _IncompleteEndpoint:
    """Missing search_batch — should NOT satisfy the Protocol."""

    def expand(self, valueset_url: str) -> list[CodeRef]:
        return []

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        return []

    def search_text(
        self, query: str, category: str, *, mode: str = "hybrid"
    ) -> list[SearchResult]:
        return []


def test_stub_satisfies_protocol():
    """Structural typing: stub WITHOUT inheritance is recognized."""
    endpoint = _StubEndpoint()
    assert isinstance(endpoint, TerminologyEndpoint)


def test_incomplete_does_not_satisfy_protocol():
    """A class missing methods is NOT recognized."""
    endpoint = _IncompleteEndpoint()
    assert not isinstance(endpoint, TerminologyEndpoint)


def test_none_is_not_an_endpoint():
    assert not isinstance(None, TerminologyEndpoint)


def test_protocol_has_four_methods():
    """Lock the public surface — adding/removing methods is a breaking change."""
    expected = {"expand", "expand_intensional", "search_text", "search_batch"}
    actual = {
        attr for attr in expected if hasattr(TerminologyEndpoint, attr)
    }
    assert actual == expected
