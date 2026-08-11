"""Public data types for the terminology abstraction layer.

These dataclasses are the wire format returned by
:class:`fhir4ds.cql.terminology.endpoint.TerminologyEndpoint` implementations.
They are deliberately minimal so the Protocol can be implemented by both an
HTTP sidecar adapter and an in-process library adapter without coupling.

References:
    FHIR R4 ValueSet $expand operation:
        https://hl7.org/fhir/R4/valueset-operation-expand.html
    FHIR R4 ValueSet.expansion.contains:
        https://hl7.org/fhir/R4/valueset-definitions.html#ValueSet.expansion.contains
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CodeRef:
    """A single normalized code reference.

    Attributes:
        system: Canonical code system URL (already normalized via
            :meth:`fhir4ds.cql.duckdb.udf.system_resolver.SystemResolver.normalize`).
            SNOMED module-specific URLs (e.g.
            ``http://snomed.info/sct/731000124108``) MUST be reduced to their
            base form (``http://snomed.info/sct``) before construction.
        code: The code value as a string.
        display: Optional human-readable display string.
    """

    system: str
    code: str
    display: Optional[str] = None


@dataclass(frozen=True)
class SearchResult(CodeRef):
    """A ranked terminology-discovery result.

    Returned by ``TerminologyEndpoint.search_text`` /
    ``TerminologyEndpoint.search_batch``. Extends :class:`CodeRef` with
    search metadata from medterm4ds's ``$search`` operation (a medterm4ds
    extension to FHIR R4).

    Attributes:
        score: Relevance score from the underlying ranking engine.
            Higher is more relevant.
        match_grade: Coarse-grained match bucket. One of ``"certain"``,
            ``"probable"``, ``"ambiguous"``, or ``"no-match"``.
        search_mode: Ranking strategy used. One of ``"lexical"``,
            ``"hybrid"``, or ``"semantic"``.
        index_version: Optional version tag of the underlying terminology
            index at search time. Propagated for audit / reproducibility.
    """

    score: float = 0.0
    match_grade: str = "ambiguous"
    search_mode: str = "hybrid"
    index_version: Optional[str] = None


@dataclass(frozen=True)
class TerminologyConfig:
    """Configuration for :func:`get_terminology_endpoint`.

    All fields have safe defaults so a freshly-constructed
    ``TerminologyConfig()`` describes the disabled (zero-dependency) mode.
    The factory reads this from environment variables when no explicit
    config is supplied.

    Attributes:
        mode: Adapter selection. One of ``"disabled"`` (default),
            ``"http"``, or ``"in_process"``.
        url: Base URL for the HTTP sidecar (HTTP mode only). The adapter
            appends FHIR R4 paths (e.g. ``/fhir/ValueSet/$expand``).
        timeout_seconds: Bounded HTTP timeout in seconds. Every ``httpx``
            call uses ``timeout=timeout_seconds`` (never ``None``).
        medterm4ds_db_path: Optional DuckDB path for the in-process
            medterm4ds engine. When ``None`` the engine uses its default.
        search_index_dir: Optional directory containing prebuilt search
            indexes for the in-process adapter.
    """

    mode: str = "disabled"
    url: Optional[str] = None
    timeout_seconds: float = 5.0
    medterm4ds_db_path: Optional[str] = None
    search_index_dir: Optional[str] = None
