"""VSAC (Value Set Authority Center) terminology adapter.

Implements the structural :class:`TerminologyEndpoint` Protocol against
the NLM VSAC FHIR R4 endpoint (``https://cts.nlm.nih.gov/fhir``).

Design highlights (see FEATURE_VSAC_ADAPTER.md):
    * Auth: HTTP Basic with username ``apikey`` and the UMLS API key as
      password. The key is resolved LAZILY at call time (explicit
      constructor arg > ``FHIR4DS_VSAC_API_KEY`` > ``UMLS_API_KEY``) and
      is NEVER logged or included in exception text.
    * Membership: the single reliable source is ``$expand`` on the
      VERSIONED ValueSet id (``/ValueSet/<oid>-<version>/$expand``).
      VSAC ``compose`` blocks frequently carry only nested ``valueSet``
      references, so compose is never trusted for membership. The
      unversioned canonical ``$expand`` form 400s on large sets, so
      ``expand()`` first resolves the canonical URL (optionally
      versioned as ``...|<version>``) to the newest-or-matching ValueSet
      entry via ``GET /ValueSet?url=<canonical>``, then pages the
      versioned-id expansion with ``count=1000`` until
      ``expansion.total`` (runaway cap: 50 pages; sets exceeding 10
      pages log a WARNING for observability).
    * ``search_text`` / ``search_batch``: documented no-ops returning
      ``[]`` — VSAC has no $search operation (that is a medterm4ds
      extension); the DependencyResolver only consumes ``expand``.
    * Disk cache: expansions cached under ``~/.cache/fhir4ds/vsac/``
      (override ``FHIR4DS_VSAC_CACHE_DIR``), keyed by
      ``sha256(url|version)`` so new publications get fresh keys, TTL
      24h by default (override ``FHIR4DS_VSAC_CACHE_TTL`` seconds; ``0``
      means always revalidate). Writes are atomic (tmp + rename);
      corrupt entries are deleted and refetched; negative results are
      never cached.
    * Zero-dependency: stdlib ``urllib.request`` only (INV-1/INV-3 —
      module import requires nothing beyond fhir4ds + stdlib).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .types import CodeRef, SearchResult

_logger = logging.getLogger(__name__)

DEFAULT_VSAC_BASE_URL = "https://cts.nlm.nih.gov/fhir"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h — VSAC quotas are daily.
DEFAULT_PAGE_SIZE = 1000
MAX_PAGES = 50  # runaway cap (50k codes at count=1000)
LARGE_SET_PAGE_THRESHOLD = 10  # >10 pages -> WARNING (observability)

_VERSION_IN_CANONICAL_RE = re.compile(r"^(?P<base>.+?)\|(?P<version>\d{8,})$")


class TerminologyEndpointError(RuntimeError):
    """Raised when the VSAC endpoint cannot satisfy a request.

    Message content policy: includes the HTTP status and an OperationOutcome
    diagnostics excerpt when available, but NEVER the API key or the raw
    Authorization header.
    """


class VCACTerminologyEndpoint:
    """TerminologyEndpoint implementation backed by NLM VSAC.

    Structural Protocol conformance — no inheritance from
    :class:`fhir4ds.cql.terminology.endpoint.TerminologyEndpoint`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_VSAC_BASE_URL,
        timeout_seconds: float = 15.0,
        cache_dir: Optional[Path] = None,
        cache_ttl_seconds: Optional[float] = None,
    ) -> None:
        self._api_key_arg = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = max(0.5, float(timeout_seconds))
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._cache_ttl = (
            DEFAULT_CACHE_TTL_SECONDS if cache_ttl_seconds is None else max(0.0, float(cache_ttl_seconds))
        )

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def expand(self, valueset_url: str) -> list[CodeRef]:
        """Expand a VSAC value set canonical URL to its code list.

        Args:
            valueset_url: Canonical URL, optionally versioned
                (``...|20180310``). Unversioned URLs resolve to the
                newest published version.

        Returns:
            List of normalized :class:`CodeRef` (deduped on
            ``(system, code)``), in server expansion order.

        Raises:
            TerminologyEndpointError: authentication failure, value set
                not found, or upstream server error.
        """
        cache_key = self._cache_key(valueset_url)
        cached = self._cache_read(cache_key)
        if cached is not None:
            return self._codes_from_rows(cached)

        entry = self._resolve_value_set_entry(valueset_url)
        versioned_id = entry["id"]
        version = entry.get("version") or ""
        rows = self._expand_versioned(versioned_id)

        self._cache_write(cache_key, rows)
        return self._codes_from_rows(rows)

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        """Expand an in-memory ValueSet dict LOCALLY (enumerated only).

        VSAC server-side resolution is unavailable for arbitrary
        intensional definitions, so only enumerated
        ``compose.include[].concept[]`` content is honored. Filter rules
        and nested value-set references raise — silently returning a
        partial list would under-report membership.
        """
        if not isinstance(value_set, dict):
            raise ValueError(
                f"value_set must be a dict, got {type(value_set).__name__}"
            )
        from fhir4ds.cql.duckdb.udf.system_resolver import SystemResolver

        codes: list[CodeRef] = []
        compose = value_set.get("compose") or {}
        includes = compose.get("include") or []
        for include in includes:
            if not isinstance(include, dict):
                continue
            if include.get("filter") or include.get("valueSet"):
                raise TerminologyEndpointError(
                    "VSAC adapter cannot resolve intensional compose "
                    "(filter/valueSet references require server-side "
                    "expansion); pass the value set canonical URL to "
                    "expand() instead"
                )
            system = include.get("system")
            for concept in include.get("concept") or []:
                if not isinstance(concept, dict):
                    continue
                code = concept.get("code")
                if not code:
                    continue
                codes.append(
                    CodeRef(
                        system=SystemResolver.normalize(system) or system or "",
                        code=str(code),
                        display=concept.get("display"),
                    )
                )
        return codes

    def search_text(
        self,
        query: str,
        category: Optional[str] = None,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        """Not supported by VSAC — documented no-op (returns ``[]``)."""
        _logger.debug("VSAC adapter does not implement search_text (no $search op)")
        return []

    def search_batch(
        self, queries: list[str], mode: str = "hybrid"
    ) -> list[list[SearchResult]]:
        """Not supported by VSAC — documented no-op (returns ``[]`` per query)."""
        return [[] for _ in queries]

    def is_healthy(self) -> bool:
        """Cheap liveness probe: fetch the newest OfficeVisit entry header.

        Returns True on any successful authenticated response; False on
        auth/network failure. Never raises.
        """
        try:
            self._resolve_value_set_entry(
                "http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001"
            )
            return True
        except Exception:  # noqa: BLE001 — probe contract: never raise
            return False

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def _api_key(self) -> str:
        if self._api_key_arg:
            return self._api_key_arg
        for var in ("FHIR4DS_VSAC_API_KEY", "UMLS_API_KEY"):
            value = os.getenv(var)
            if value:
                return value
        raise TerminologyEndpointError(
            "VSAC API key not found — pass api_key= or set "
            "FHIR4DS_VSAC_API_KEY / UMLS_API_KEY"
        )

    def _get_json(self, path: str) -> dict:
        url = f"{self._base_url}{path}"
        request = urllib.request.Request(url, method="GET")
        request.add_header("Accept", "application/fhir+json")
        import base64

        token = base64.b64encode(
            f"apikey:{self._api_key()}".encode("utf-8")
        ).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_head = ""
            try:
                body_head = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # noqa: BLE001 — best-effort diagnostics
                pass
            if e.code in (401, 403):
                raise TerminologyEndpointError(
                    "VSAC authentication failed — check UMLS_API_KEY"
                ) from e
            raise TerminologyEndpointError(
                f"VSAC request failed: HTTP {e.code} for {path}: {body_head}"
            ) from e
        except urllib.error.URLError as e:
            raise TerminologyEndpointError(
                f"VSAC network error for {path}: {e.reason}"
            ) from e

    def _resolve_value_set_entry(self, valueset_url: str) -> dict:
        """GET /ValueSet?url=<canonical> → the matching entry (newest if unversioned).

        VSAC's ``url=`` search does NOT honor the ``|version`` pipe suffix
        (verified live: 0 entries), so a versioned canonical is queried by
        its BASE URL and matched against entry ``version`` fields here.
        """
        match = _VERSION_IN_CANONICAL_RE.match(valueset_url)
        query_url = match.group("base") if match else valueset_url
        bundle = self._get_json(f"/ValueSet?url={urllib.request.quote(query_url, safe='')}")
        if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
            raise TerminologyEndpointError(
                f"VSAC returned unexpected payload for {valueset_url} "
                f"(resourceType={type(bundle).__name__})"
            )
        entries = [e.get("resource") for e in bundle.get("entry") or []]
        entries = [r for r in entries if isinstance(r, dict) and r.get("resourceType") == "ValueSet"]
        if not entries:
            raise TerminologyEndpointError(f"value set not found: {valueset_url}")

        if match:
            wanted = match.group("version")
            for resource in entries:
                if str(resource.get("version") or "") == wanted:
                    return resource
            raise TerminologyEndpointError(
                f"value set not found: {valueset_url}"
            )
        # Unversioned: VSAC returns newest-first; pick the first entry.
        return entries[0]

    def _expand_versioned(self, versioned_id: str) -> list[list[object]]:
        """Page $expand on /ValueSet/<versioned-id> until expansion.total."""
        rows: list[list[object]] = []
        total: Optional[int] = None
        page_index = 0
        while page_index < MAX_PAGES:
            offset = page_index * DEFAULT_PAGE_SIZE
            payload = self._get_json(
                f"/ValueSet/{urllib.request.quote(versioned_id, safe='')}/$expand"
                f"?count={DEFAULT_PAGE_SIZE}&offset={offset}"
            )
            expansion = (payload or {}).get("expansion") or {}
            total = expansion.get("total")
            contains = expansion.get("contains") or []
            if not contains:
                break  # server exhausted — stop paging
            for item in contains:
                if not isinstance(item, dict):
                    continue
                code = item.get("code")
                if not code:
                    continue
                rows.append([item.get("system") or "", str(code), item.get("display")])
            page_index += 1
            if total is not None and len(rows) >= int(total):
                break
        else:
            _logger.error(
                "VSAC expansion runaway cap hit for %s after %d pages (%d codes)",
                versioned_id,
                MAX_PAGES,
                len(rows),
            )
        pages_seen = (len(rows) + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE
        if pages_seen > LARGE_SET_PAGE_THRESHOLD:
            _logger.warning(
                "VSAC large value set %s: %d codes across ~%d pages",
                versioned_id,
                len(rows),
                pages_seen,
            )
        return rows

    def _codes_from_rows(self, rows: list[list[object]]) -> list[CodeRef]:
        from fhir4ds.cql.duckdb.udf.system_resolver import SystemResolver

        seen: set[tuple[str, str]] = set()
        codes: list[CodeRef] = []
        for system, code, display in rows:
            normalized = SystemResolver.normalize(system) or system or ""
            key = (normalized, str(code))
            if key in seen:
                continue
            seen.add(key)
            codes.append(CodeRef(system=normalized, code=str(code), display=display))
        return codes

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------

    def _cache_root(self) -> Path:
        if self._cache_dir is not None:
            root = self._cache_dir
        else:
            override = os.getenv("FHIR4DS_VSAC_CACHE_DIR")
            root = Path(override) if override else Path.home() / ".cache" / "fhir4ds" / "vsac"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _cache_ttl_value(self) -> float:
        if self._cache_ttl is not None:
            return self._cache_ttl
        raw = os.getenv("FHIR4DS_VSAC_CACHE_TTL")
        if raw is None:
            return DEFAULT_CACHE_TTL_SECONDS
        try:
            return max(0.0, float(raw))
        except ValueError:
            return DEFAULT_CACHE_TTL_SECONDS

    @staticmethod
    def _cache_key(valueset_url: str) -> str:
        return hashlib.sha256(valueset_url.encode("utf-8")).hexdigest()

    def _cache_read(self, key: str) -> Optional[list[list[object]]]:
        path = self._cache_root() / f"{key}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires_at = float(payload["expires_at"])
            if time.time() >= expires_at:
                path.unlink(missing_ok=True)
                return None
            rows = payload["codes"]
            if not isinstance(rows, list):
                raise ValueError("codes is not a list")
            return rows
        except (ValueError, KeyError, TypeError, OSError):
            _logger.warning("VSAC cache entry corrupt — refetching: %s", path.name)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def _cache_write(self, key: str, rows: list[list[object]]) -> None:
        path = self._cache_root() / f"{key}.json"
        payload = {
            "fetched_at": time.time(),
            "expires_at": time.time() + self._cache_ttl_value(),
            "codes": rows,
        }
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            _logger.warning("VSAC cache write failed (continuing uncached): %s", path.name)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_cache(self) -> int:
        """Delete every cached expansion file. Returns the number removed."""
        removed = 0
        root = self._cache_root()
        for path in root.glob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed


def clear_vsac_cache() -> int:
    """Module-level convenience: clear the default VSAC cache location."""
    return VCACTerminologyEndpoint().clear_cache()
