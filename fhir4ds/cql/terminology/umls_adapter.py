"""UMLS (Unified Medical Language System) terminology adapter.

Implements the structural :class:`TerminologyEndpoint` Protocol against
the NLM UTS REST API (``https://uts-ws.nlm.nih.gov/rest``) for value-set
building: search concepts by name, then extract source codes (SNOMED CT,
LOINC, ICD-10-CM, RxNorm, CPT) for the picked concept.

Design highlights:
    * Auth: the UTS REST API authenticates with the ``apiKey`` QUERY
      PARAMETER (``?...&apiKey=<key>``) — NOT HTTP Basic, which the UTS
      REST endpoint rejects with 401 (verified live; the VSAC FHIR
      endpoint uses Basic — the two surfaces differ). The key is resolved
      LAZILY at call time (explicit constructor arg >
      ``FHIR4DS_UMLS_API_KEY`` > ``UMLS_API_KEY``) and is NEVER logged or
      included in exception text.
    * ``search_text``: GET ``/rest/search/current?string=<q>`` returns
      CUIs with Metathesaurus-preferred names. The UTS search endpoint's
      ``rootSource``/``sabs`` filter params DO NOT reliably restrict
      results (probed live), so source filtering happens at the ATOMS
      step instead. When a ``system`` hint is supplied via the ``category``
      argument (a canonical system URL or UMLS rootSource abbreviation),
      results are filtered to atoms from that source.
    * Code extraction: for each CUI, GET
      ``/rest/content/<version>/CUI/<cui>/atoms?language=ENG`` and keep
      atoms whose ``code`` field is a source code (the API frequently
      returns a URI in ``code`` — the actual code is the tail segment
      and the SAB is the segment before it; both shapes are handled).
    * ``expand`` / ``expand_intensional``: documented no-ops returning
      ``[]`` — UMLS is not a FHIR ValueSet expansion service (that is
      the VSAC adapter's job; both can coexist behind the Protocol).
    * Disk cache: atom extractions cached under
      ``~/.cache/fhir4ds/umls/`` (override ``FHIR4DS_UMLS_CACHE_DIR``),
      keyed by ``sha256(version|cui|system)`` so new releases get fresh
      keys, TTL 24h by default (override ``FHIR4DS_UMLS_CACHE_TTL``
      seconds; ``0`` means always revalidate). Writes are atomic
      (tmp + rename); corrupt entries are deleted and refetched.
    * Zero-dependency: stdlib ``urllib.request`` only (INV-1/INV-3 —
      module import requires nothing beyond fhir4ds + stdlib).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from .types import CodeRef, SearchResult

_logger = logging.getLogger(__name__)

DEFAULT_UTS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"
DEFAULT_UTS_VERSION = "current"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h — UMLS releases are infrequent.
DEFAULT_PAGE_SIZE = 25
ATOM_PAGE_SIZE = 50
MAX_CUIS = 15  # search results probed for codes per query

# UMLS rootSource abbreviation → canonical FHIR system URI.
# Only widely-used value-set-building sources are mapped; unmapped
# sources still surface in results with system="" so the UI can label
# them by rootSource.
ROOT_SOURCE_TO_SYSTEM: dict[str, str] = {
    "SNOMEDCT_US": "http://snomed.info/sct",
    "SNOMEDCT": "http://snomed.info/sct",
    "LOINC": "http://loinc.org",
    "ICD10CM": "http://hl7.org/fhir/sid/icd-10-cm",
    "ICD10": "http://hl7.org/fhir/sid/icd-10-cm",
    "RXNORM": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "CPT": "http://www.ama-assn.org/go/cpt",
    "HCPCS": "urn:oid:2.16.840.1.113883.6.14",
    "CVX": "urn:oid:1.2.840.10008.2.6.1",
    "ICD9CM": "http://hl7.org/fhir/sid/icd-9-cm",
}

# Canonical FHIR system URI → preferred UMLS rootSource (for filtering).
SYSTEM_TO_ROOT_SOURCE: dict[str, str] = {
    "http://snomed.info/sct": "SNOMEDCT_US",
    "http://loinc.org": "LOINC",
    "http://hl7.org/fhir/sid/icd-10-cm": "ICD10CM",
    "http://www.nlm.nih.gov/research/umls/rxnorm": "RXNORM",
    "http://www.ama-assn.org/go/cpt": "CPT",
}

# rootSource abbreviations that never carry useful member codes for
# value-set building (Metathesaurus administrative sources).
_EXCLUDED_ROOT_SOURCES = {
    "MTH",
    "MTHSCT",
    "NCI_FDA",
    "NCIM",
    "LNC",
    "MED-RT",
}


class UMLSTerminologyEndpointError(RuntimeError):
    """Raised when the UTS REST endpoint cannot satisfy a request.

    Message content policy: includes the HTTP status and a short body
    excerpt when available, but NEVER the API key or the full query
    string (which embeds the key).
    """


class UMLSTerminologyEndpoint:
    """TerminologyEndpoint implementation backed by the NLM UTS REST API.

    Structural Protocol conformance — no inheritance from
    :class:`fhir4ds.cql.terminology.endpoint.TerminologyEndpoint`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_UTS_BASE_URL,
        version: str = DEFAULT_UTS_VERSION,
        timeout_seconds: float = 15.0,
        cache_dir: Optional[Path] = None,
        cache_ttl_seconds: Optional[float] = None,
    ) -> None:
        self._api_key_arg = api_key
        self._base_url = base_url.rstrip("/")
        self._version = version or DEFAULT_UTS_VERSION
        self._timeout = max(0.5, float(timeout_seconds))
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        # None = defer to FHIR4DS_UMLS_CACHE_TTL / default at read time.
        self._cache_ttl = None if cache_ttl_seconds is None else max(0.0, float(cache_ttl_seconds))

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def expand(self, valueset_url: str) -> list[CodeRef]:
        """Not supported by UMLS — documented no-op (returns ``[]``).

        UMLS is not a FHIR ValueSet expansion service; use
        :class:`VCACTerminologyEndpoint` for canonical expansion.
        """
        _logger.debug("UMLS adapter does not implement expand (use VSAC adapter)")
        return []

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        """Not supported by UMLS — documented no-op (returns ``[]``)."""
        _logger.debug("UMLS adapter does not implement expand_intensional (use VSAC adapter)")
        return []

    def search_text(
        self,
        query: str,
        category: Optional[str] = None,
        mode: str = "words",
    ) -> list[SearchResult]:
        """Search UMLS concepts by name and extract member codes.

        Two-step pipeline (one UTS search + bounded atom fetches):

        1. ``GET /rest/search/<version>?string=<query>`` → ranked CUIs
           with Metathesaurus-preferred names.
        2. For each CUI (capped at ``MAX_CUIS``), fetch English atoms and
           keep code-bearing atoms grouped by source, mapped to canonical
           FHIR system URIs. When ``category`` names a known system
           (canonical URI or rootSource abbreviation), only that source's
           atoms are kept.

        Args:
            query: Free-text concept name (e.g. ``"myocardial infarction"``).
            category: Optional system filter — a canonical FHIR system
                URI (``http://snomed.info/sct``) or UMLS rootSource
                abbreviation (``SNOMEDCT_US``). ``None``/unknown keeps
                all mapped sources.
            mode: ``"words"`` (default, partial word match) or
                ``"exact"`` — maps to the UTS ``searchType`` parameter.

        Returns:
            Bounded list of :class:`SearchResult` — one per
            ``(system, code)`` pair, deduplicated, best-match CUI first.

        Raises:
            UMLSTerminologyEndpointError: missing key, authentication
                failure, or upstream server error.
        """
        if not isinstance(query, str) or not query.strip():
            return []
        search_type = "exact" if mode == "exact" else "words"
        root_filter = self._root_source_for_category(category)

        payload = self._get_json(
            "/search/" + urllib.parse.quote(self._version, safe=""),
            {
                "string": query.strip(),
                "searchType": search_type,
                "pageSize": str(DEFAULT_PAGE_SIZE),
            },
        )
        cuis = self._cuis_from_search(payload)
        if not cuis:
            return []

        results: list[SearchResult] = []
        seen: set[tuple[str, str]] = set()
        for rank, entry in enumerate(cuis[:MAX_CUIS]):
            cui = entry.get("ui") or ""
            preferred = entry.get("name") or ""
            if not cui.startswith("C"):
                continue
            atoms = self._atoms_for_cui(cui, root_filter)
            for system, code, display in atoms:
                key = (system, code)
                if key in seen:
                    continue
                seen.add(key)
                results.append(
                    SearchResult(
                        system=system,
                        code=code,
                        display=display or preferred,
                        score=1.0 / (rank + 1),
                        match_grade="probable",
                        search_mode=search_type,
                    )
                )
                if len(results) >= DEFAULT_PAGE_SIZE:
                    return results
        return results

    def search_batch(
        self, queries: list[str], mode: str = "words"
    ) -> list[list[SearchResult]]:
        """Run multiple :meth:`search_text` calls sequentially."""
        return [self.search_text(q, None, mode=mode) for q in queries]

    def is_healthy(self) -> bool:
        """Cheap liveness probe: a one-term exact search.

        Returns True on any successful authenticated response; False on
        auth/network failure. Never raises.
        """
        try:
            self._get_json(
                "/search/" + urllib.parse.quote(self._version, safe=""),
                {"string": "diabetes", "searchType": "exact", "pageSize": "1"},
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
        for var in ("FHIR4DS_UMLS_API_KEY", "UMLS_API_KEY"):
            value = os.getenv(var)
            if value:
                return value
        raise UMLSTerminologyEndpointError(
            "UMLS API key not found — pass api_key= or set "
            "FHIR4DS_UMLS_API_KEY / UMLS_API_KEY"
        )

    def _get_json(self, path: str, params: dict[str, str]) -> dict:
        """GET ``<base><path>?<params>&apiKey=<key>`` → parsed JSON.

        The key rides as a query parameter (UTS REST contract) and is
        stripped from every diagnostic path.
        """
        query = dict(params)
        query["apiKey"] = self._api_key()
        url = f"{self._base_url}{path}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, method="GET")
        request.add_header("Accept", "application/json")
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
                raise UMLSTerminologyEndpointError(
                    "UTS authentication failed — check UMLS_API_KEY"
                ) from e
            raise UMLSTerminologyEndpointError(
                f"UTS request failed: HTTP {e.code} for {path}: {body_head}"
            ) from e
        except urllib.error.URLError as e:
            raise UMLSTerminologyEndpointError(
                f"UTS network error for {path}: {e.reason}"
            ) from e

    @staticmethod
    def _cuis_from_search(payload: object) -> list[dict]:
        """Extract the ranked CUI result list from a search payload.

        UTS wraps results as ``result.results``; some versions return a
        bare list — both shapes are handled.
        """
        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if not isinstance(payload, dict):
            return []
        result = payload.get("result")
        if isinstance(result, dict):
            results = result.get("results")
        else:
            results = result
        if isinstance(results, dict):
            results = results.get("results")
        if not isinstance(results, list):
            return []
        return [r for r in results if isinstance(r, dict)]

    def _atoms_for_cui(
        self, cui: str, root_filter: Optional[str]
    ) -> list[tuple[str, str, str]]:
        """Fetch English atoms for a CUI and extract ``(system, code, display)``.

        Cached on disk keyed by ``(version, cui, filter)``. The UTS atom
        ``code`` field is frequently a content URI
        (``.../source/<SAB>/<CODE>``); both plain-code and URI shapes
        are normalized to the plain code with the SAB taken from the
        ``rootSource`` field.
        """
        cache_key = self._cache_key(f"{self._version}|{cui}|{root_filter or ''}")
        cached = self._cache_read(cache_key)
        if cached is not None:
            return [(str(r[0]), str(r[1]), r[2] if len(r) > 2 else None) for r in cached]

        payload = self._get_json(
            f"/content/{urllib.parse.quote(self._version, safe='')}/CUI/"
            f"{urllib.parse.quote(cui, safe='')}/atoms",
            {"language": "ENG", "pageSize": str(ATOM_PAGE_SIZE)},
        )
        atoms = self._cuis_from_search(payload)  # same dict/list wrapping

        rows: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for atom in atoms:
            sab = str(atom.get("rootSource") or "")
            if not sab or sab in _EXCLUDED_ROOT_SOURCES:
                continue
            if root_filter and sab != root_filter:
                continue
            system = ROOT_SOURCE_TO_SYSTEM.get(sab)
            if not system:
                continue
            code = self._plain_code(atom.get("code"))
            if not code:
                continue
            key = (system, code)
            if key in seen:
                continue
            seen.add(key)
            rows.append((system, code, atom.get("name")))
        self._cache_write(cache_key, [[s, c, d] for s, c, d in rows])
        return rows

    @staticmethod
    def _plain_code(raw: object) -> str:
        """Normalize an atom ``code`` field to the plain source code.

        UTS frequently returns a content URI whose tail segment is the
        code (``.../source/SNOMEDCT_US/22298006``); a plain code passes
        through. URI-encoded characters are decoded.
        """
        if raw is None:
            return ""
        text = str(raw)
        if not text:
            return ""
        if "://" in text or text.startswith("/"):
            tail = text.rstrip("/").rsplit("/", 1)[-1]
            return urllib.parse.unquote(tail)
        return text

    @staticmethod
    def _root_source_for_category(category: Optional[str]) -> Optional[str]:
        """Resolve a category hint (system URI or rootSource) to a SAB."""
        if not category:
            return None
        if category in SYSTEM_TO_ROOT_SOURCE:
            return SYSTEM_TO_ROOT_SOURCE[category]
        if category in ROOT_SOURCE_TO_SYSTEM:
            return category
        return None

    # ------------------------------------------------------------------
    # Disk cache
    # ------------------------------------------------------------------

    def _cache_root(self) -> Path:
        if self._cache_dir is not None:
            root = self._cache_dir
        else:
            override = os.getenv("FHIR4DS_UMLS_CACHE_DIR")
            root = Path(override) if override else Path.home() / ".cache" / "fhir4ds" / "umls"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _cache_ttl_value(self) -> float:
        if self._cache_ttl is not None:
            return self._cache_ttl
        raw = os.getenv("FHIR4DS_UMLS_CACHE_TTL")
        if raw is None:
            return DEFAULT_CACHE_TTL_SECONDS
        try:
            return max(0.0, float(raw))
        except ValueError:
            return DEFAULT_CACHE_TTL_SECONDS

    @staticmethod
    def _cache_key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

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
            _logger.warning("UMLS cache entry corrupt — refetching: %s", path.name)
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
            _logger.warning("UMLS cache write failed (continuing uncached): %s", path.name)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_cache(self) -> int:
        """Delete every cached atom file. Returns the number removed."""
        removed = 0
        root = self._cache_root()
        for path in root.glob("*.json"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        return removed


def clear_umls_cache() -> int:
    """Module-level convenience: clear the default UMLS cache location."""
    return UMLSTerminologyEndpoint().clear_cache()
