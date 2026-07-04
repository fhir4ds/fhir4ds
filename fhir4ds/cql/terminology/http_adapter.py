"""HTTP adapter for the terminology endpoint abstraction.

Talks to a medterm4ds (or any FHIR R4-compatible) terminology sidecar.
``httpx`` is imported lazily inside ``_client`` (and never at module
top), so simply importing this module does NOT require ``httpx`` to be
installed. The factory's try/except around importing this module can
therefore surface the user-facing install hint.

Invariant INV-6 (bounded HTTP timeouts):
    Every ``httpx.Client`` is constructed with ``timeout=self._timeout``
    where ``self._timeout`` is always a finite float. Never ``None``,
    never a positional argument.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..duckdb.udf.system_resolver import SystemResolver
from .types import CodeRef, SearchResult

_logger = logging.getLogger(__name__)

# FHIR R4 paths relative to the sidecar's FHIR root. The caller provides
# the FHIR root as `base_url` (e.g. "http://127.0.0.1:8001/fhir"), and
# these paths are joined directly — so they must NOT include the FHIR
# prefix themselves. Doubling the prefix here would produce
# ".../fhir/fhir/ValueSet/$expand" 404s against a real sidecar.
_VALUESET_EXPAND_PATH = "/ValueSet/$expand"
_CODESYSTEM_SEARCH_PATH = "/CodeSystem/$search"


class HTTPTerminologyEndpoint:
    """Terminology adapter that talks to a medterm4ds HTTP sidecar.

    Implements the :class:`~fhir4ds.cql.terminology.endpoint.TerminologyEndpoint`
    protocol via FHIR R4 ``ValueSet $expand`` and the medterm4ds
    ``CodeSystem $search`` extension.

    Args:
        base_url: Sidecar **FHIR root** URL — i.e. the URL at which the
            server's FHIR R4 API begins (e.g. ``http://127.0.0.1:8001/fhir``
            or ``http://127.0.0.1:7860/fhir`` for the medterm4ds Docker
            container). Adapter paths like ``/ValueSet/$expand`` are
            joined directly to this base, so do NOT include a trailing
            slash. Trailing slashes are stripped automatically.
        timeout_seconds: Bounded HTTP timeout for every request. Defaults
            to 5.0 seconds. Must be a finite positive float.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        if not base_url:
            raise ValueError("base_url is required for HTTPTerminologyEndpoint")
        if timeout_seconds is None or timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be a positive float (INV-6: no infinite hangs)"
            )
        # Strip trailing slash so path join produces clean URLs.
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout_seconds)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_httpx():
        """Import httpx lazily, raising an actionable error if missing.

        httpx is only needed at request time. Deferring the import to
        call sites means the factory's try/except can convert a missing
        dependency into the user-facing ``pip install`` hint instead of
        the bare ``import of httpx halted; None in sys.modules`` error.
        """
        try:
            import httpx  # type: ignore
        except ImportError as e:
            raise ImportError(
                "httpx is required for HTTP terminology mode. "
                "Install with: pip install 'fhir4ds-v2[terminology]'"
            ) from e
        return httpx

    def _client(self):
        """Construct a fresh httpx.Client with an explicit timeout.

        A new client per call avoids holding sockets open across the
        lifetime of the resolver and guarantees the timeout is always
        explicit (INV-6).
        """
        httpx = self._require_httpx()
        # Keyword form — never positional, never None.
        return httpx.Client(timeout=self._timeout)

    @staticmethod
    def _parse_contains(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Walk a FHIR R4 ValueSet $expand response body.

        Returns the raw ``expansion.contains[]`` list (possibly empty).
        """
        if not isinstance(payload, dict):
            return []
        expansion = payload.get("expansion")
        if not isinstance(expansion, dict):
            return []
        contains = expansion.get("contains")
        if not isinstance(contains, list):
            return []
        return contains

    @classmethod
    def _contains_to_coderefs(cls, contains: list[dict[str, Any]]) -> list[CodeRef]:
        """Convert raw FHIR contains dicts into normalized CodeRef dataclasses.

        System normalization (INV-5): every ``system`` value flows through
        ``SystemResolver.normalize()`` so SNOMED module URLs reduce to
        ``http://snomed.info/sct`` before they leave the adapter.
        """
        refs: list[CodeRef] = []
        for item in contains:
            if not isinstance(item, dict):
                continue
            system = SystemResolver.normalize(item.get("system"))
            code = item.get("code")
            if system is None or code is None:
                # Skip half-formed entries — they cannot join against
                # any valueset_codes row downstream.
                continue
            refs.append(
                CodeRef(
                    system=system,
                    code=str(code),
                    display=item.get("display"),
                )
            )
        return refs

    @staticmethod
    def _search_payload_to_results(
        payload: dict[str, Any],
        mode: str,
    ) -> list[SearchResult]:
        """Convert a $search Bundle into ranked SearchResult dataclasses."""
        if not isinstance(payload, dict):
            return []
        entries: list[dict[str, Any]] = []
        bundle_entry = payload.get("entry")
        if isinstance(bundle_entry, list):
            entries = bundle_entry
        else:
            # Some implementations may return a flat contains[] instead.
            contains = payload.get("contains")
            if isinstance(contains, list):
                entries = contains

        results: list[SearchResult] = []
        for entry in entries:
            # Entry may be wrapped as {"resource": {...}} (Bundle) or flat.
            resource = entry.get("resource", entry) if isinstance(entry, dict) else None
            if not isinstance(resource, dict):
                continue
            system = SystemResolver.normalize(resource.get("system"))
            code = resource.get("code")
            if system is None or code is None:
                continue
            results.append(
                SearchResult(
                    system=system,
                    code=str(code),
                    display=resource.get("display") or resource.get("name"),
                    score=float(resource.get("score", 0.0)),
                    match_grade=str(
                        resource.get("matchGrade", resource.get("match_grade", "ambiguous"))
                    ),
                    search_mode=str(resource.get("searchMode", mode)),
                    index_version=resource.get("indexVersion"),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def expand(self, valueset_url: str) -> list[CodeRef]:
        """GET <base_url>/ValueSet/$expand?url=<valueset_url>."""
        url = f"{self._base_url}{_VALUESET_EXPAND_PATH}"
        with self._client() as client:
            response = client.get(url, params={"url": valueset_url})
            response.raise_for_status()
            payload = response.json()
        return self._contains_to_coderefs(self._parse_contains(payload))

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        """POST <base_url>/ValueSet/$expand with an intensional ValueSet body."""
        url = f"{self._base_url}{_VALUESET_EXPAND_PATH}"
        with self._client() as client:
            response = client.post(url, json=value_set)
            response.raise_for_status()
            payload = response.json()
        return self._contains_to_coderefs(self._parse_contains(payload))

    def search_text(
        self,
        query: str,
        category: str,
        *,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        """GET <base_url>/CodeSystem/$search?<query, category, mode>."""
        url = f"{self._base_url}{_CODESYSTEM_SEARCH_PATH}"
        params = {
            "query": query,
            "category": category,
            "mode": mode,
        }
        with self._client() as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        return self._search_payload_to_results(payload, mode=mode)

    def search_batch(
        self,
        queries: list[tuple[str, str]],
        *,
        mode: str = "hybrid",
    ) -> list[list[SearchResult]]:
        """Run search_text per query.

        medterm4ds does not yet expose a native batch $search endpoint,
        so this is a sequential loop. Phase 4 may add a true batch
        endpoint; the Protocol signature is stable either way.
        """
        results: list[list[SearchResult]] = []
        for query, category in queries:
            results.append(self.search_text(query, category, mode=mode))
        return results
