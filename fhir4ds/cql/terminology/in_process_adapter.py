"""In-process adapter for the terminology endpoint abstraction.

Calls ``medterm4ds`` services directly without going through HTTP.
``medterm4ds`` is imported lazily inside ``__init__`` so that simply
having ``fhir4ds`` installed does NOT require ``medterm4ds``.

The module body itself only imports stdlib + fhir4ds internals; the
factory only imports this module when the user explicitly opts into
``in_process`` mode.

Circuit breaker:
    Tracks consecutive failures per-instance. After ``breaker_threshold``
    failures in a row, subsequent calls are short-circuited (returning
    ``[]``) for ``breaker_cooldown_seconds``. The in_process adapter
    catches underlying exceptions and returns ``[]`` by contract; the
    breaker is fed via an internal instrumented call wrapper so failure
    counting still works. The breaker is NOT thread-safe — assume
    single-threaded use. Multiple threads sharing one endpoint instance
    need an external lock.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..duckdb.udf.system_resolver import SystemResolver
from .system_mappings import (
    CATEGORY_TO_SOURCES,
    SOURCE_MNEMONIC_TO_URL,
    category_to_source_mnemonics,
)
from .types import CodeRef, SearchResult

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# medterm4ds source-mnemonic -> FHIR canonical URL translation.
#
# The map now lives in its canonical home at
# :mod:`fhir4ds.cql.terminology.system_mappings` so it can be shared
# with Phase 4's notes-pipeline without private-import coupling. The
# backward-compat alias below keeps existing internal references working.
# ----------------------------------------------------------------------

#: Backward-compat alias for code that pre-dates the system_mappings
#: refactor. New code should import ``SOURCE_MNEMONIC_TO_URL`` from
#: :mod:`fhir4ds.cql.terminology.system_mappings`.
_SOURCE_MNEMONIC_TO_URL: dict[str, str] = SOURCE_MNEMONIC_TO_URL


class InProcessTerminologyEndpoint:
    """Terminology adapter that calls ``medterm4ds`` in-process.

    Holds a single shared ``DiscoveryEngine`` so the underlying DuckDB
    connection and search indexes are constructed once per adapter
    instance.

    Args:
        medterm4ds_db_path: Optional path to a medterm4ds DuckDB file.
            When ``None`` medterm4ds's own default discovery applies.
        search_index_dir: Optional directory of prebuilt search indexes.
        breaker_threshold: Consecutive failures before the circuit breaker
            trips. Once tripped, protocol methods short-circuit to ``[]``
            for ``breaker_cooldown_seconds``. Defaults to 5. NOT thread-safe.
        breaker_cooldown_seconds: Seconds the breaker stays tripped before
            a half-open probe call is permitted. Defaults to 60.0.

    Raises:
        ImportError: ``medterm4ds`` is not installed. The factory wraps
            this in a clearer install hint, but the same error is raised
            here for callers that construct the adapter directly.

    Thread safety:
        The circuit breaker state is mutable and unprotected. Assume
        single-threaded use. Multiple threads sharing one instance need
        an external lock.
    """

    def __init__(
        self,
        medterm4ds_db_path: Optional[str] = None,
        search_index_dir: Optional[str] = None,
        *,
        breaker_threshold: int = 5,
        breaker_cooldown_seconds: float = 60.0,
    ) -> None:
        # Lazy import — INV-1 / INV-3: top-level `import fhir4ds` must
        # never pull medterm4ds. Only opt-in callers pay this cost.
        #
        # The published medterm4ds wheel exposes LocalDuckDBEngine via
        # the top-level re-export (``medterm4ds.LocalDuckDBEngine``) and
        # also at ``medterm4ds.engines.duckdb.engine.LocalDuckDBEngine``.
        # We try the canonical top-level path first; the full path is a
        # safety net in case a future medterm4ds drops the re-export.
        try:
            from medterm4ds import LocalDuckDBEngine  # type: ignore
        except ImportError:
            try:
                from medterm4ds.engines.duckdb.engine import (  # type: ignore
                    LocalDuckDBEngine,
                )
            except ImportError as e:  # pragma: no cover
                raise ImportError(
                    "Could not import LocalDuckDBEngine from medterm4ds. "
                    "Install with: pip install 'fhir4ds-v2[terminology]'"
                ) from e

        self._medterm4ds_db_path = medterm4ds_db_path
        self._search_index_dir = search_index_dir
        self._breaker_threshold = int(breaker_threshold)
        self._breaker_cooldown_seconds = float(breaker_cooldown_seconds)
        # Breaker state — single-threaded only (see class docstring).
        self._consecutive_failures: int = 0
        self._tripped_until: float = 0.0

        # Construct the shared engine. The published medterm4ds wheel
        # exposes ``connect(db_path=...)`` as the stable public entry
        # point — it provisions the cache, builds/loads indexes, and
        # returns a Terminology whose ``.engine`` is a DiscoveryEngine
        # we can drive. Constructing LocalDuckDBEngine directly was the
        # older pattern but the published 0.0.1 wheel changed its
        # signature to require a DuckDB connection, so going through
        # ``connect()`` is the supported path.
        #
        # We keep references to BOTH ``term`` (the Terminology facade)
        # and ``term.engine`` (the DiscoveryEngine). expand() goes
        # through the facade (Option B per the medterm4ds team —
        # ``term.expand_url(url)`` returns a flat list of CodeRefs);
        # search_text / search_batch drive the engine directly because
        # the facade does not expose them.
        self._terminology: Any = None
        try:
            import medterm4ds as _m  # type: ignore
            if search_index_dir is not None:
                # medterm4ds 0.0.2 connect() has no search_index_dir
                # param (indexes live inside the prepared cache). Kept
                # only for the TypeError fallback path below.
                _logger.debug(
                    "search_index_dir=%r ignored: medterm4ds connect() "
                    "does not accept it (only used on the legacy "
                    "LocalDuckDBEngine fallback path)",
                    search_index_dir,
                )
            try:
                self._terminology = _m.connect(
                    db_path=medterm4ds_db_path,
                    cache_indexes=True,
                )
            except TypeError:
                # medterm4ds without cache_indexes (pre-0.0.2 drift).
                self._terminology = _m.connect(db_path=medterm4ds_db_path)
            # Terminology.engine is a LocalDuckDBEngine (subclass of
            # DiscoveryEngine via the runtime-checkable Protocol).
            # cache_indexes=True: this adapter holds one long-lived
            # engine by design, so persisting BM25 indexes into the
            # prepared cache matches the architecture (no per-call
            # rebuild churn).
            self._engine = self._terminology.engine
        except RuntimeError as e:
            # medterm4ds 0.0.2 raises RuntimeError when db_path is set
            # but missing. This is a configuration error the user must
            # fix — surface a hint instead of the raw message.
            # factory.py intentionally leaves adapter errors uncaught,
            # so this re-raise IS the user-facing error.
            raise RuntimeError(
                f"medterm4ds terminology database unavailable: {e}. "
                "Check FHIR4DS_TERMINOLOGY_DB (must point to a DuckDB "
                "file built by medterm4ds). Remediation: build one via "
                "'medterm4ds data build-duckdb', auto-provision by "
                "omitting the db path, or — if the DB was provisioned "
                "by medterm4ds 0.0.1 — rebuild it for prepared-schema "
                "0.9 via 'medterm4ds data prepare-derived --db <path>'."
            ) from e
        except TypeError:
            # Older medterm4ds: ``connect()`` may not accept db_path
            # as kwarg. Fall back to direct engine construction.
            engine_kwargs: dict[str, Any] = {}
            if medterm4ds_db_path is not None:
                engine_kwargs["db_path"] = medterm4ds_db_path
            if search_index_dir is not None:
                engine_kwargs["search_index_dir"] = search_index_dir
            try:
                self._engine = LocalDuckDBEngine(**engine_kwargs)
            except TypeError:
                # Engine signature drift: fall back to no-kwargs construction
                # so a medterm4ds version that doesn't accept these kwargs
                # still works. Phase 1 favors robustness over strictness.
                self._engine = LocalDuckDBEngine()
        except ImportError as e:  # pragma: no cover - exercised via factory tests
            raise ImportError(
                "medterm4ds is required for InProcessTerminologyEndpoint. "
                "Install with: pip install 'fhir4ds-v2[terminology]'"
            ) from e

    # ------------------------------------------------------------------
    # Circuit breaker helpers (single-threaded — see class docstring).
    # ------------------------------------------------------------------

    def _is_breaker_open(self, now: float) -> bool:
        """Return True when the breaker is fully open (skip the call)."""
        if self._consecutive_failures < self._breaker_threshold:
            return False
        if now >= self._tripped_until:
            return False
        return True

    def _on_call_success(self) -> None:
        """Reset failure counters on a successful call."""
        self._consecutive_failures = 0
        self._tripped_until = 0.0

    def _on_call_failure(self) -> None:
        """Increment failure counters and trip the breaker when threshold met."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._breaker_threshold:
            self._tripped_until = time.monotonic() + self._breaker_cooldown_seconds
            _logger.error(
                "terminology circuit breaker tripped after %d consecutive failures; "
                "fast-failing subsequent calls for %.1fs",
                self._consecutive_failures,
                self._breaker_cooldown_seconds,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_system(system: Any) -> Optional[str]:
        """Normalize a system value to its FHIR canonical URL (INV-5).

        Two-pass normalization:
        1. If ``system`` is a medterm4ds source mnemonic
           (``SNOMEDCT_US``, ``RXNORM``, ``LNC``, ...), expand it to its
           FHIR canonical URL. medterm4ds exposes ``code.source`` as a
           UMLS mnemonic, not a URL, so without this pass CodeRef.system
           would silently fail to join against valueset_codes rows that
           use ``http://snomed.info/sct``.
        2. Flow the result through ``SystemResolver.normalize`` so OID
           and SNOMED module URL variants also reduce to canonical form.
        Unknown mnemonics pass through unchanged with a DEBUG log line.
        """
        if system is None:
            return None
        s = str(system)
        mapped = _SOURCE_MNEMONIC_TO_URL.get(s)
        if mapped is None:
            # Heuristic: medterm4ds source mnemonics are typically ALL-CAPS
            # with no scheme. If it looks like a mnemonic (ALL-CAPS, no
            # colon/slash) but isn't in the map, log for visibility.
            if s.isupper() and "/" not in s and ":" not in s and len(s) > 2:
                _logger.debug(
                    "Unknown medterm4ds source mnemonic %r — passing through "
                    "unchanged; add to _SOURCE_MNEMONIC_TO_URL if a FHIR "
                    "canonical URL exists.",
                    s,
                )
            mapped = s
        return SystemResolver.normalize(mapped)

    @classmethod
    def _to_coderef(cls, system: Any, code: Any, display: Any) -> Optional[CodeRef]:
        normalized_system = cls._normalize_system(system)
        if normalized_system is None or code is None:
            return None
        return CodeRef(
            system=normalized_system,
            code=str(code),
            display=str(display) if display is not None else None,
        )

    # ------------------------------------------------------------------
    # Protocol surface
    # ------------------------------------------------------------------

    def expand(self, valueset_url: str) -> list[CodeRef]:
        """Expand a ValueSet canonical URL via medterm4ds.

        Implements the same three modes as the HTTP adapter (plain
        canonical, ``fhir_vs`` shorthand, filter) by delegating to
        medterm4ds's FHIR $expand logic.

        Preferred path (MT-004):
        ``medterm4ds.apps.fhir_api.expand_url_pattern(engine, url,
        count=1000, include_retired=True)`` — the Terminology facade's
        ``expand_url()`` has no ``include_retired`` opt-in and medterm4ds
        0.0.2 defaults to active-only, which would silently drop codes
        retired since they were recorded in historical patient data.
        Expansion feeds membership resolution (CQL ``in ValueSet``,
        terminology_closure), so retired codes are included per the
        settled retired-code policy. Fallback: facade
        ``Terminology.expand_url(url)`` (flat CodeRefs; no
        include_retired — acceptable degradation) when the
        ``expand_url_pattern`` helper is unavailable.

        Short-circuits to ``[]`` when the circuit breaker is open.
        """
        now = time.monotonic()
        if self._is_breaker_open(now):
            _logger.warning(
                "terminology circuit breaker open; skipping expand() call "
                "(failures=%d, cooldown_remaining=%.1fs)",
                self._consecutive_failures,
                max(0.0, self._tripped_until - now),
            )
            return []

        # Preferred: apps.fhir_api.expand_url_pattern with retired codes
        # included (membership/expansion path — settled policy).
        try:
            from medterm4ds.apps.fhir_api import (  # type: ignore
                expand_url_pattern,
            )
        except ImportError:
            expand_url_pattern = None  # fall back to the facade below

        if expand_url_pattern is not None:
            try:
                expanded = expand_url_pattern(
                    self._engine, valueset_url, count=1000, include_retired=True
                )
                contains = (
                    expanded.get("expansion", {}).get("contains", [])
                    if isinstance(expanded, dict)
                    else []
                )
            except Exception as e:  # pragma: no cover - medterm4ds drift guard
                _logger.warning(
                    "in_process expand failed for %s: %s", valueset_url, e
                )
                self._on_call_failure()
                return []
            refs = []
            for item in contains:
                # FHIR-payload ``system`` values are canonical URLs;
                # _normalize_system passes them through unchanged.
                ref = self._to_coderef(
                    item.get("system"), item.get("code"), item.get("display")
                )
                if ref is not None:
                    refs.append(ref)
            self._on_call_success()
            return refs

        # Fallback: Terminology facade (no include_retired — acceptable
        # degradation on medterm builds without expand_url_pattern).
        if self._terminology is not None and hasattr(
            self._terminology, "expand_url"
        ):
            try:
                mt_refs = self._terminology.expand_url(valueset_url)
            except Exception as e:  # pragma: no cover - medterm4ds drift guard
                _logger.warning(
                    "in_process expand_url failed for %s: %s", valueset_url, e
                )
                self._on_call_failure()
                return []
            refs: list[CodeRef] = []
            for mt_ref in mt_refs or []:
                # medterm4ds CodeRef has (source, code). ``source`` is a
                # UMLS mnemonic (SNOMEDCT_US); _to_coderef runs it
                # through _normalize_system to expand to the FHIR
                # canonical URL (http://snomed.info/sct).
                ref = self._to_coderef(
                    getattr(mt_ref, "source", None),
                    getattr(mt_ref, "code", None),
                    getattr(mt_ref, "display", None),
                )
                if ref is not None:
                    refs.append(ref)
            self._on_call_success()
            return refs

        _logger.warning(
            "medterm4ds expand helpers unavailable; "
            "in_process.expand returns [] for %s",
            valueset_url,
        )
        self._on_call_failure()
        return []

    def expand_intensional(self, value_set: dict) -> list[CodeRef]:
        """Expand an intensional ValueSet in-process (MT-005).

        Preferred path: ``medterm4ds.apps.fhir_api.
        expand_intensional_value_set(engine, value_set, 1000,
        include_retired=True)`` — note ``count`` is POSITIONAL and the
        result is NOT truncated (depth-cap only). Returns
        ``{"system","code","display"}`` dicts converted via
        ``_to_coderef``. Retired codes included per the settled policy
        (expansion feeds membership). Fallback: facade
        ``Terminology.expand_intensional(value_set, count=1000)``
        (CodeRefs, no include_retired — acceptable degradation).

        Short-circuits to ``[]`` when the circuit breaker is open.
        """
        now = time.monotonic()
        if self._is_breaker_open(now):
            _logger.warning(
                "terminology circuit breaker open; skipping expand_intensional() call "
                "(failures=%d, cooldown_remaining=%.1fs)",
                self._consecutive_failures,
                max(0.0, self._tripped_until - now),
            )
            return []

        # Preferred: apps.fhir_api helper with retired codes included.
        try:
            from medterm4ds.apps.fhir_api import (  # type: ignore
                expand_intensional_value_set,
            )
        except ImportError:
            expand_intensional_value_set = None  # fall back to the facade

        if expand_intensional_value_set is not None:
            try:
                expanded, _depth_cap_hit = expand_intensional_value_set(
                    self._engine, value_set, 1000, include_retired=True
                )
            except Exception as e:  # pragma: no cover - medterm4ds drift guard
                _logger.warning(
                    "in_process expand_intensional failed for %s: %s",
                    value_set.get("url", "<intensional>"),
                    e,
                )
                self._on_call_failure()
                return []
            refs = []
            for item in expanded or []:
                ref = self._to_coderef(
                    item.get("system"), item.get("code"), item.get("display")
                )
                if ref is not None:
                    refs.append(ref)
            self._on_call_success()
            return refs

        # Fallback: Terminology facade (no include_retired — acceptable
        # degradation on medterm builds without the helper).
        if self._terminology is not None and hasattr(
            self._terminology, "expand_intensional"
        ):
            try:
                mt_refs = self._terminology.expand_intensional(
                    value_set, count=1000
                )
            except Exception as e:  # pragma: no cover - medterm4ds drift guard
                _logger.warning(
                    "in_process expand_intensional failed for %s: %s",
                    value_set.get("url", "<intensional>"),
                    e,
                )
                self._on_call_failure()
                return []
            refs = []
            for mt_ref in mt_refs or []:
                ref = self._to_coderef(
                    getattr(mt_ref, "source", None),
                    getattr(mt_ref, "code", None),
                    getattr(mt_ref, "display", None),
                )
                if ref is not None:
                    refs.append(ref)
            self._on_call_success()
            return refs

        _logger.warning(
            "expand_intensional is not supported by the installed "
            "medterm4ds; use HTTP mode (FHIR4DS_TERMINOLOGY_MODE=http) "
            "for intensional ValueSet expansion. Returning []."
        )
        return []

    def search_text(
        self,
        query: str,
        category: str,
        *,
        mode: str = "hybrid",
    ) -> list[SearchResult]:
        """Search terminology names via medterm4ds discovery service.

        Short-circuits to ``[]`` when the circuit breaker is open.
        """
        now = time.monotonic()
        if self._is_breaker_open(now):
            _logger.warning(
                "terminology circuit breaker open; skipping search_text() call "
                "(failures=%d, cooldown_remaining=%.1fs)",
                self._consecutive_failures,
                max(0.0, self._tripped_until - now),
            )
            return []

        # Imported lazily so module load stays cheap and isolated.
        # Re-imported on every call so tests that monkeypatch
        # medterm4ds.services.discovery.search_names take effect.
        from medterm4ds.services.discovery import (  # type: ignore
            search_names,
        )

        # Category maps to medterm4ds source filter (e.g. "condition" -> SNOMEDCT_US).
        sources = _category_to_sources(category)
        try:
            raw_results = search_names(
                query,
                engine=self._engine,
                sources=sources,
                limit=25,
            )
        except Exception as e:  # pragma: no cover - medterm4ds drift guard
            _logger.warning("in_process search_text failed for %r: %s", query, e)
            self._on_call_failure()
            return []

        results: list[SearchResult] = []
        for r in raw_results:
            code_obj = getattr(r, "code", None)
            system = getattr(code_obj, "source", None) if code_obj is not None else None
            ref = self._to_coderef(
                system,
                getattr(code_obj, "code", None),
                getattr(r, "name", None),
            )
            if ref is None:
                continue
            results.append(
                SearchResult(
                    system=ref.system,
                    code=ref.code,
                    display=ref.display,
                    score=float(getattr(r, "score", 0.0)),
                    match_grade=str(getattr(r, "match_grade", "ambiguous")),
                    search_mode=mode,
                    index_version=getattr(r, "index_version", None),
                )
            )
        self._on_call_success()
        return results

    def search_batch(
        self,
        queries: list[tuple[str, str]],
        *,
        mode: str = "hybrid",
    ) -> list[list[SearchResult]]:
        """Sequential per-query loop over ``search_text``.

        Note: the breaker is checked per-query inside ``search_text``.
        """
        return [self.search_text(q, cat, mode=mode) for q, cat in queries]

    # ------------------------------------------------------------------
    # Health probe
    # ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """Probe the underlying medterm4ds engine without going through HTTP.

        Returns ``True`` when the adapter has a usable engine, ``False``
        otherwise. Never raises — failures are caught and logged at
        ``WARNING``.

        For the in_process adapter the simplest stable probe is to
        confirm the engine is present and exposes the
        ``search_codes``/``search_names`` service entry points the
        protocol methods rely on. Catching "data not loaded" without
        false positives across medterm4ds versions is risky; instead
        we probe the surface we actually use.
        """
        try:
            engine = getattr(self, "_engine", None)
            if engine is None:
                _logger.warning(
                    "in_process terminology probe: engine not constructed"
                )
                return False
            # The protocol methods call search_names / expand_* against
            # this engine. If the engine advertises neither of the
            # common discovery surfaces, downstream calls will fail.
            if not (
                hasattr(engine, "search_codes")
                or hasattr(engine, "search_names")
                or hasattr(engine, "lookup_code")
            ):
                _logger.warning(
                    "in_process terminology probe: engine missing discovery surface"
                )
                return False
            return True
        except Exception as e:  # broad: probe must never raise
            _logger.warning(
                "in_process terminology probe failed: %s: %s",
                type(e).__name__,
                e,
            )
            return False


# ----------------------------------------------------------------------
# Category mapping
# ----------------------------------------------------------------------

# The category->source mapping now lives in its canonical home at
# :mod:`fhir4ds.cql.terminology.system_mappings` (shared with the HTTP
# adapter's $search ``system`` parameter, MT-002). Backward-compat
# aliases below keep existing internal references working.

_category_to_sources = category_to_source_mnemonics
_CATEGORY_TO_SOURCES: dict[str, tuple[str, ...]] = CATEGORY_TO_SOURCES
