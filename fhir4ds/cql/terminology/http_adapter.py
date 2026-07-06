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

Circuit breaker:
    Tracks consecutive failures per-instance. After ``breaker_threshold``
    failures in a row, subsequent calls are short-circuited (returning
    ``[]`` for protocol methods) for ``breaker_cooldown_seconds``. Once
    the cooldown elapses, a single half-open probe call is permitted; a
    success closes the breaker, a failure re-trips it. The breaker is
    thread-safe under an internal ``threading.Lock`` (FDD Step 4 / INV-A5);
    safe for use by :meth:`HTTPTerminologyEndpoint.search_batch`'s
    internal thread pool. Callers using their own threads on the same
    instance remain supported but should not also call ``search_batch``
    concurrently — that path is untested.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional
from urllib.parse import urlparse

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

# Default probe timeout for is_healthy() — short and bounded so factory
# startup validation never blocks for long on an unreachable sidecar.
_HEALTH_PROBE_TIMEOUT_SECONDS = 2.0

# Extension URL used by medterm4ds to carry the match-grade enum on each
# $search hit. The same URL is reused by fhir4ds's autocoding extension
# downstream, so any consumer that already understands our extension
# shape understands the sidecar's response too.
_MATCH_GRADE_URL = "http://fhir4ds.org/fhir/StructureDefinition/match-grade"

# Cap on concurrent HTTP calls in search_batch. Most medterm4ds sidecars
# handle ~8 concurrent requests before saturating the SapBERT inference
# pool; raising this risks sidecar backpressure. (FDD Step 4 / audit S3.)
HTTP_SEARCH_BATCH_MAX_WORKERS = 8


def _extract_score(resource: dict, search_meta: dict | None) -> float:
    """Pull the relevance score from one of three locations."""
    for src in (search_meta, resource):
        if not isinstance(src, dict):
            continue
        raw = src.get("score")
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _extract_match_grade(resource: dict, search_meta: dict | None) -> str:
    """Pull match-grade from one of four locations.

    Order:
        1. Top-level ``matchGrade`` on resource (FHIR standard).
        2. Top-level ``match_grade`` snake_case on resource.
        3. ``search.extension[]`` value where url matches ``_MATCH_GRADE_URL``.
        4. Fallback ``"ambiguous"`` so callers see "unranked" rather than crash.
    """
    if isinstance(resource, dict):
        for key in ("matchGrade", "match_grade"):
            v = resource.get(key)
            if isinstance(v, str) and v:
                return v
    if isinstance(search_meta, dict):
        ext = search_meta.get("extension")
        if isinstance(ext, list):
            for entry in ext:
                if (
                    isinstance(entry, dict)
                    and entry.get("url") == _MATCH_GRADE_URL
                    and isinstance(entry.get("valueCode"), str)
                ):
                    return entry["valueCode"]
    return "ambiguous"


def _extract_search_mode(resource: dict, search_meta: dict | None, default: str) -> str:
    """Pull the search mode (lexical/hybrid/semantic) from one of three locations."""
    if isinstance(search_meta, dict) and isinstance(search_meta.get("mode"), str):
        return search_meta["mode"]
    if isinstance(resource, dict) and isinstance(resource.get("searchMode"), str):
        return resource["searchMode"]
    return default



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
        breaker_threshold: Consecutive failures before the circuit breaker
            trips. Once tripped, protocol methods short-circuit to ``[]``
            for ``breaker_cooldown_seconds``. Defaults to 5.
        breaker_cooldown_seconds: Seconds the breaker stays tripped before
            a half-open probe call is permitted. Defaults to 60.0.

    Thread safety:
        The circuit breaker state is mutable and protected by an
        internal ``threading.Lock`` (FDD Step 4 / INV-A5). Safe for
        use by :meth:`search_batch`'s internal thread pool. Callers
        using their own threads on the same instance are also
        supported but should not also call ``search_batch``
        concurrently — that combined path is untested.
    """

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        *,
        breaker_threshold: int = 5,
        breaker_cooldown_seconds: float = 60.0,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required for HTTPTerminologyEndpoint")
        # Fail-fast URL validation (QA-014). Deferred failure at first
        # network call surfaces opaque httpx errors far from the
        # construction site. Reject non-URL / wrong-scheme inputs here so
        # common typos (``localhost:8001/fhir`` missing scheme, ``ftp://``,
        # plain strings) are caught with an actionable message.
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"base_url must be an http(s) URL with host, got {base_url!r}"
            )
        if timeout_seconds is None or timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be a positive float (INV-6: no infinite hangs)"
            )
        # Strip trailing slash so path join produces clean URLs.
        self._base_url = base_url.rstrip("/")
        self._timeout = float(timeout_seconds)
        self._breaker_threshold = int(breaker_threshold)
        self._breaker_cooldown_seconds = float(breaker_cooldown_seconds)
        # Breaker state — guarded by ``self._lock`` (FDD Step 4 / INV-A5).
        self._consecutive_failures: int = 0
        self._tripped_until: float = 0.0
        # ``threading.Lock`` (not RLock) — every acquisition is a single
        # critical section, no recursive entry needed. Stdlib only.
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Circuit breaker helpers (thread-safe under ``self._lock``).
    # ------------------------------------------------------------------

    def _is_breaker_open(self, now: float) -> bool:
        """Return True when the breaker is fully open (skip the call).

        Once the cooldown elapses, returns False so a single half-open
        probe call is permitted. The probe either trips the breaker
        again (failure) or closes it (success).

        Acquires ``self._lock`` for the duration of the reads so a
        concurrent :meth:`_on_call_failure` cannot leave us reading a
        torn counter/cooldown pair.
        """
        failures, tripped_until = self._breaker_snapshot()
        if failures < self._breaker_threshold:
            return False
        if now >= tripped_until:
            # Cooldown elapsed — half-open: allow one probe call.
            return False
        return True

    def _breaker_snapshot(self) -> tuple[int, float]:
        """Snapshot ``(failures, tripped_until)`` under the lock.

        Use this for log/diagnostic reads so the values are a
        consistent pair — calling ``self._consecutive_failures`` and
        ``self._tripped_until`` separately can produce a torn read
        when a concurrent failure trips the breaker between the two
        attribute reads (audit QA-001).
        """
        with self._lock:
            return self._consecutive_failures, self._tripped_until

    def _on_call_success(self) -> None:
        """Reset failure counters on a successful call (closes breaker)."""
        with self._lock:
            self._consecutive_failures = 0
            self._tripped_until = 0.0

    def _on_call_failure(self) -> None:
        """Increment failure counters and trip the breaker when threshold met."""
        with self._lock:
            self._consecutive_failures += 1
            tripped = self._consecutive_failures >= self._breaker_threshold
            if tripped:
                self._tripped_until = time.monotonic() + self._breaker_cooldown_seconds
                failure_count = self._consecutive_failures
                cooldown = self._breaker_cooldown_seconds
        if tripped:
            _logger.error(
                "terminology circuit breaker tripped after %d consecutive failures; "
                "fast-failing subsequent calls for %.1fs",
                failure_count,
                cooldown,
            )

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

            # Search metadata (score, mode, match-grade) can live in either:
            # (a) Standard FHIR Bundle entry: entry.search.{score, mode, extension}
            # (b) medterm4ds shape: nested inside resource.search.{...}
            # (c) Flat legacy shape: top-level on resource.{score, matchGrade, searchMode}
            # Try all three; first hit wins.
            entry_search = entry.get("search") if isinstance(entry, dict) else None
            inner_search = resource.get("search")
            search_meta = entry_search if isinstance(entry_search, dict) else None
            if search_meta is None and isinstance(inner_search, dict):
                search_meta = inner_search

            score = _extract_score(resource, search_meta)
            match_grade = _extract_match_grade(resource, search_meta)
            search_mode = _extract_search_mode(resource, search_meta, mode)
            index_version = resource.get("indexVersion") or (
                search_meta.get("indexVersion") if search_meta else None
            )

            results.append(
                SearchResult(
                    system=system,
                    code=str(code),
                    display=resource.get("display") or resource.get("name"),
                    score=score,
                    match_grade=match_grade,
                    search_mode=search_mode,
                    index_version=index_version,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def expand(self, valueset_url: str) -> list[CodeRef]:
        """GET <base_url>/ValueSet/$expand?url=<valueset_url>.

        Short-circuits to ``[]`` when the circuit breaker is open.
        """
        now = time.monotonic()
        if self._is_breaker_open(now):
            failures, tripped_until = self._breaker_snapshot()
            _logger.warning(
                "terminology circuit breaker open; skipping expand() call "
                "(failures=%d, cooldown_remaining=%.1fs)",
                failures,
                max(0.0, tripped_until - now),
            )
            return []
        try:
            url = f"{self._base_url}{_VALUESET_EXPAND_PATH}"
            with self._client() as client:
                response = client.get(url, params={"url": valueset_url})
                response.raise_for_status()
                payload = response.json()
            result = self._contains_to_coderefs(self._parse_contains(payload))
            self._on_call_success()
            return result
        except Exception:
            self._on_call_failure()
            raise

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        """POST <base_url>/ValueSet/$expand with an intensional ValueSet body.

        Short-circuits to ``[]`` when the circuit breaker is open.
        """
        now = time.monotonic()
        if self._is_breaker_open(now):
            failures, tripped_until = self._breaker_snapshot()
            _logger.warning(
                "terminology circuit breaker open; skipping expand_intensional() call "
                "(failures=%d, cooldown_remaining=%.1fs)",
                failures,
                max(0.0, tripped_until - now),
            )
            return []
        try:
            url = f"{self._base_url}{_VALUESET_EXPAND_PATH}"
            with self._client() as client:
                response = client.post(url, json=value_set)
                response.raise_for_status()
                payload = response.json()
            result = self._contains_to_coderefs(self._parse_contains(payload))
            self._on_call_success()
            return result
        except Exception:
            self._on_call_failure()
            raise

    def search_text(
        self,
        query: str,
        category: str,
        *,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        """GET <base_url>/CodeSystem/$search?<query, category, mode>.

        Short-circuits to ``[]`` when the circuit breaker is open.
        """
        now = time.monotonic()
        if self._is_breaker_open(now):
            failures, tripped_until = self._breaker_snapshot()
            _logger.warning(
                "terminology circuit breaker open; skipping search_text() call "
                "(failures=%d, cooldown_remaining=%.1fs)",
                failures,
                max(0.0, tripped_until - now),
            )
            return []
        try:
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
            result = self._search_payload_to_results(payload, mode=mode)
            self._on_call_success()
            return result
        except Exception:
            self._on_call_failure()
            raise

    def search_batch(
        self,
        queries: list[tuple[str, str]],
        *,
        mode: str = "hybrid",
    ) -> list[list[SearchResult]]:
        """Run search_text per query, concurrently when beneficial.

        For ``len(queries) <= 1`` or when the breaker is open at
        submission time, runs sequentially (today's behavior —
        byte-identical results). For larger batches, dispatches via
        :class:`concurrent.futures.ThreadPoolExecutor` with
        ``max_workers=min(HTTP_SEARCH_BATCH_MAX_WORKERS, len(queries))``.

        Thread safety (FDD Step 4 / INV-A5):
            The circuit breaker state is guarded by ``self._lock`` so
            concurrent failures from in-flight HTTP calls correctly
            increment ``_consecutive_failures`` without torn writes.
            If the breaker trips mid-flight, remaining futures still
            execute (already submitted) but their results are dropped
            if the breaker is open at result-collection time.

        medterm4ds does not yet expose a native batch $search endpoint;
        Phase 7 of the medterm4ds distribution plan may add one. The
        Protocol signature is stable either way.

        Note: the breaker is checked per-query inside ``search_text``;
        ``search_batch`` itself does not wrap the loop, so an open
        breaker short-circuits each sub-call to ``[]`` without raising.
        """
        if len(queries) <= 1:
            # Small batch — sequential is faster (no thread overhead).
            return [
                self.search_text(query, category, mode=mode)
                for query, category in queries
            ]
        # Parallel dispatch. ``concurrent.futures`` is stdlib, imported
        # lazily so the module remains import-isolation clean.
        import concurrent.futures
        max_workers = min(HTTP_SEARCH_BATCH_MAX_WORKERS, len(queries))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.search_text, query, category, mode=mode)
                for query, category in queries
            ]
            results: list[list[SearchResult]] = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as exc:  # pragma: no cover - defensive
                    _logger.warning(
                        "search_batch: query raised %s: %s; returning [] for that query.",
                        type(exc).__name__, exc,
                    )
                    results.append([])
            return results

    # ------------------------------------------------------------------
    # Health probe
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Probe the sidecar with a lightweight ``GET /metadata`` request.

        Returns ``True`` if the sidecar responds with HTTP < 500, ``False``
        otherwise. Never raises — failures (timeouts, connection refused,
        unexpected exceptions) are caught and logged at ``WARNING``.

        Useful for factory startup validation, pre-flight checks before
        heavy operations, and periodic health monitoring. Bounded by a
        short independent timeout so it never blocks for long on an
        unreachable sidecar.
        """
        try:
            httpx = self._require_httpx()
            url = f"{self._base_url}/metadata"
            with httpx.Client(timeout=_HEALTH_PROBE_TIMEOUT_SECONDS) as client:
                response = client.get(url)
            return response.status_code < 500
        except Exception as e:  # broad: probe must never raise
            _logger.warning(
                "terminology health probe failed for %s: %s: %s",
                self._base_url,
                type(e).__name__,
                e,
            )
            return False
