"""The TerminologyEndpoint structural Protocol.

This is a ``typing.Protocol`` so test doubles and adapter implementations
do not need to inherit from it — they only need to provide the four
methods with matching signatures (structural / duck typing).

Design rationale:
    * All ``expand`` variants return ``list[CodeRef]`` (not generators) so
      Phase 3's closure-table loader can iterate the result multiple
      times without re-invoking the endpoint.
    * System URIs returned by adapters MUST be normalized via
      :class:`fhir4ds.cql.duckdb.udf.system_resolver.SystemResolver` so
      SNOMED module URLs (``http://snomed.info/sct/731000124108``) reduce
      to ``http://snomed.info/sct`` and join cleanly with rows from
      ``loader.load_valuesets()``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import CodeRef, SearchResult


@runtime_checkable
class TerminologyEndpoint(Protocol):
    """Structural protocol for terminology service adapters.

    Two reference implementations ship with fhir4ds:

    * :class:`fhir4ds.cql.terminology.http_adapter.HTTPTerminologyEndpoint`
      — talks to a medterm4ds (or any FHIR R4-compatible) HTTP sidecar.
    * :class:`fhir4ds.cql.terminology.in_process_adapter.InProcessTerminologyEndpoint`
      — calls ``medterm4ds`` services in-process.

    Test doubles may implement this protocol with stubbed returns.
    """

    def expand(self, valueset_url: str) -> list[CodeRef]:
        """Expand a ValueSet by its canonical URL.

        Covers three medterm4ds expansion modes:
            1. Plain canonical (``url=http://example.org/ValueSet/Foo``).
            2. ``fhir_vs`` shorthand (e.g.
               ``http://snomed.info/sct?fhir_vs=isa/73211009``).
            3. Filter expansion (text autocomplete).

        Args:
            valueset_url: Canonical ValueSet URL (or ``fhir_vs`` pattern).

        Returns:
            Bounded list of normalized :class:`CodeRef`. Empty list when
            the endpoint returns no codes.

        Raises:
            Exception: Network / parse / timeout failures. The
                :class:`~fhir4ds.cql.dependency.resolver.DependencyResolver`
                fallback path catches and degrades these to ``None``;
                direct callers decide their own error policy.
        """
        ...

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        """Expand an intensional ValueSet resource.

        Used when the caller already has a ValueSet resource with
        ``compose.include[].filter[op=is-a|descendant-of]`` rules.

        Args:
            value_set: A FHIR R4 ValueSet resource dict (must contain a
                ``compose`` key).

        Returns:
            Bounded list of normalized :class:`CodeRef`.
        """
        ...

    def search_text(
        self,
        query: str,
        category: str,
        *,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        """Search terminology names by free text.

        Backed by medterm4ds's ``$search`` operation on
        ``/fhir/CodeSystem/$search``. NOT a FHIR R4 standard operation —
        medterm4ds extension for auto-coding (Phase 2) and NER (Phase 4).

        Args:
            query: Free-text search query (e.g. ``"diabetes"``).
            category: Coarse category hint (e.g. ``"condition"``,
                ``"medication"``, ``"lab"``). Mapped to source filters
                inside the adapter.
            mode: Ranking mode (``"lexical"``, ``"hybrid"``,
                ``"semantic"``). Defaults to ``"hybrid"``.

        Returns:
            Bounded list of ranked :class:`SearchResult`.
        """
        ...

    def search_batch(
        self,
        queries: list[tuple[str, str]],
        *,
        mode: str = "hybrid",
    ) -> list[list[SearchResult]]:
        """Run multiple ``search_text`` calls efficiently.

        Args:
            queries: List of ``(query, category)`` pairs.
            mode: Ranking mode (forwarded to ``search_text``).

        Returns:
            Parallel list of result lists (one per input query).
        """
        ...
