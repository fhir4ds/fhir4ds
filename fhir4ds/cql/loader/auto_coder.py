"""AutoCoder — augments text-only CodeableConcepts with auto-coded Codings.

The AutoCoder runs a free-text CodeableConcept (e.g. ``Condition.code.text``)
through a Phase 1 :class:`TerminologyEndpoint`, takes the top-k ranked
:class:`SearchResult` matches, and writes them back as Codings on the
same CodeableConcept — each carrying the structured
:mod:`~fhir4ds.cql.loader.autocoding_extension` and
``userSelected=False``.

This is the engine that turns text-only EHR legacy data into the
addressable universe of ValueSet- and code-based CQL retrieves.

Reference: FDD ``docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE2_AUTOCODING.md``.

Zero-dependency guarantee (Phase 1 INV-1, preserved):
    Runtime imports are stdlib only (``hashlib``, ``json``, ``logging``,
    ``dataclasses``, ``math``, ``typing``). The
    :class:`TerminologyEndpoint` Protocol is imported only under
    ``TYPE_CHECKING`` — runtime duck-typing, no hard dependency on any
    Phase 1 adapter module. No ``httpx``, no ``medterm4ds``.

v1 limitations (per FDD §3f and §4.5):
    * ``BodyStructure.image`` is ``0..*`` (a list) in FHIR R4. The
      dotted-path walker treats ``image`` as a dict, so
      ``BodyStructure.image.site`` only resolves when the resource has a
      single image object. Multi-image BodyStructure is skipped
      silently (no exception). Phase 4 NER pipeline will introduce
      list-aware path resolution.
    * Free text longer than 200 characters is logged at DEBUG but not
      truncated — Phase 4 NER handles long-form text properly.

Safety guarantees (FDD §7 Invariants):
    * INV-9: :meth:`augment_resource` NEVER raises. All exceptions are
      caught, logged at WARNING, and the resource is returned unchanged.
    * INV-2: Original ``CodeableConcept.text`` is preserved unchanged.
    * INV-4: Resources with existing ``coding[]`` are NOT re-coded.
    * INV-6: Every auto-coded Coding has ``userSelected == False``.
    * INV-7: Cache hit determinism — same key returns byte-identical
      ``result_json``.
    * INV-8: Cache key pins ``index_version``; a version bump
      invalidates old rows.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .autocoding_extension import (
    AUTOCODING_EXTENSION_URL,
    build_autocoding_extension,
)
from .category import normalize_text, resolve_category

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from fhir4ds.cql.terminology.endpoint import TerminologyEndpoint
    from fhir4ds.cql.terminology.types import SearchResult

_logger = logging.getLogger(__name__)

#: Canonical engine name written into the autocoding extension. Only one
#: engine in v1 (medterm4ds); a separate field exists so downstream
#: consumers can route on engine in future releases.
_ENGINE_NAME = "medterm4ds"

#: Default dotted CodeableConcept paths per resource type. Covers the
#: common text-only EHR migration cases per FDD §3f.
DEFAULT_PATHS: dict[str, list[str]] = {
    "Condition":           ["code"],
    "Observation":         ["code"],
    "MedicationRequest":   ["medicationCodeableConcept"],
    "MedicationStatement": ["medicationCodeableConcept"],
    "Procedure":           ["code"],
    "Immunization":        ["vaccineCode"],
    "BodyStructure":       ["image.site"],
}

# Match-grade order: results at-or-above the configured threshold are
# kept (lower index = stronger match). Used by _keep_if_match_grade.
_MATCH_GRADE_ORDER: dict[str, int] = {
    "certain":    0,
    "probable":   1,
    "ambiguous":  2,
    "no-match":   3,
}


@dataclass(frozen=True)
class AutoCoderConfig:
    """Configuration for :class:`AutoCoder`.

    All fields have safe defaults — a freshly-constructed
    ``AutoCoderConfig()`` matches the strict-by-default posture
    documented in the master plan §4.

    Attributes:
        enabled: Master toggle. When ``False``, :meth:`augment_resource`
            is a no-op. Useful for runtime opt-out without removing the
            AutoCoder from the loader.
        search_mode: Ranking mode forwarded to
            :meth:`TerminologyEndpoint.search_batch`. One of
            ``lexical``/``hybrid``/``semantic``. Default ``hybrid``.
        min_match_grade: Threshold below which results are dropped.
            One of ``certain``/``probable``/``ambiguous``/``no-match``.
            Default ``certain`` (strict). Lowering to ``probable``
            multiplies recall at the cost of precision.
        top_k: Maximum number of Codings to append per CodeableConcept.
            Default ``3``. Thresholding happens BEFORE truncation, so a
            high-confidence search that returns 5 ``certain`` matches
            still writes only ``top_k`` Codings.
        engine_version: medterm4ds release version written into the
            extension's ``engine-version`` field. Default ``"0.0.1"``.
            Bump per release so Phase 5 staleness sweeps can detect
            pre-0.0.2 Codings.
        index_version: Optional explicit index version. When ``None``
            (default), the AutoCoder performs a one-shot probe-and-pin
            on the first batch (FDD §3c step 3) so the cache does not
            pollute if the underlying SapBERT/BM25 index rotates
            mid-run.
        codeable_paths: Per-resource-type list of dotted paths to
            CodeableConcept fields. Defaults to :data:`DEFAULT_PATHS`.
            Users override to add custom paths or remap existing ones.
        category_overrides: Per-resource-type category overrides. When
            a resource type appears here, the override takes precedence
            over :data:`RESOURCE_TYPE_TO_CATEGORY` (e.g. to remap
            ``Observation`` to ``vital``).
        batch_size: Number of resources processed per call to
            :meth:`AutoCoder.augment_resources`. Default ``1`` preserves
            the per-resource code path byte-for-byte. Larger values
            enable batch-aware cache lookups and (when ``workers > 1``)
            parallel augmentation. See the execution-strategy matrix in
            :doc:`FEATURE_BATCH_AUGMENTATION </plans/FEATURE_BATCH_AUGMENTATION.md>`.
        workers: Size of the multiprocessing pool used by
            :meth:`AutoCoder.augment_resources` when ``batch_size > 1``
            and the input size exceeds ``parallel_threshold``. Default
            ``1`` preserves today's single-process behavior. Bounded at
            runtime by ``os.cpu_count()``. Each worker loads its own
            medterm4ds engine (~5 GB for medspaCy + SapBERT); on a
            16 GB machine, ``workers=2`` is the practical max.
    """

    enabled: bool = True
    search_mode: str = "hybrid"
    min_match_grade: str = "certain"
    top_k: int = 3
    engine_version: str = "0.0.1"
    index_version: Optional[str] = None
    codeable_paths: dict[str, list[str]] = field(
        default_factory=lambda: dict(DEFAULT_PATHS)
    )
    category_overrides: dict[str, str] = field(default_factory=dict)
    batch_size: int = 1
    workers: int = 1


class AutoCoder:
    """Augment FHIR resources with auto-coded Codings.

    A single instance is bound to a DuckDB connection (for the cache
    table) and a Phase 1 :class:`TerminologyEndpoint` (for the search
    call). The cache table is created lazily in ``__init__``; if
    creation fails, augmentation is disabled and logged at WARNING.

    Example:
        >>> endpoint = HTTPTerminologyEndpoint("http://localhost:8001")
        >>> loader = FHIRDataLoader(con, auto_coder=AutoCoder(endpoint, con))
        >>> loader.load_ndjson("conditions.ndjson")
    """

    #: DuckDB cache table name. Constant — Phase 2 does not support
    #: customizing this. The table lives in the same connection as the
    #: ``resources`` table so one transactional scope covers both.
    CACHE_TABLE = "autocoding_cache"

    def __init__(
        self,
        endpoint: "TerminologyEndpoint",
        con: Any,
        *,
        config: Optional[AutoCoderConfig] = None,
    ) -> None:
        self._endpoint = endpoint
        self._con = con
        self._config = config if config is not None else AutoCoderConfig()

        # One-shot probe-and-pin state (FDD §3c step 3). Resolved on
        # first cache miss; never re-probed. ``None`` here means
        # "not yet resolved" (distinct from "resolved to None" which
        # would mean the endpoint reported no version).
        self._pinned_index_version: Optional[str] = None
        self._index_version_resolved = False

        # Cache-table readiness flag. If table creation fails (e.g. the
        # connection is a test stub without DDL support), augmentation
        # degrades to "always call the endpoint" (still correct, just
        # slower) — and we log WARNING.
        self._cache_enabled = False
        self._ensure_cache_table()

    def augment_resource(self, resource: dict) -> dict:
        """Augment ``resource`` in place with auto-coded Codings.

        INV-9 (never raises): all exceptions are caught, logged at
        WARNING, and the resource is returned unchanged. A single bad
        resource MUST NOT break the load pipeline.

        Mutates the input dict in place AND returns it (for ergonomic
        chaining). Original ``CodeableConcept.text`` is preserved
        unchanged (INV-2).

        Args:
            resource: A FHIR R4 resource dict.

        Returns:
            The same dict reference (mutated in place).
        """
        try:
            if not self._config.enabled:
                return resource
            self._augment_resource_inner(resource)
        except Exception as exc:  # noqa: BLE001 - INV-9: catch everything
            _logger.warning(
                "AutoCoder.augment_resource caught exception on %s/%s: %s; "
                "resource left unchanged.",
                resource.get("resourceType") if isinstance(resource, dict) else "<not-dict>",
                resource.get("id") if isinstance(resource, dict) else None,
                exc,
            )
        return resource

    def augment_resources(self, resources: list[dict]) -> None:
        """Batch-aware augmentation. Mutates each resource in place.

        Execution strategy is governed by ``self._config.batch_size``
        and ``self._config.workers``:

        - ``batch_size == 1``: delegates to :meth:`augment_resource`
          per resource (byte-identical to today's per-resource path).
        - ``batch_size > 1, workers == 1``: chunks the input by
          ``batch_size`` and loops synchronously, calling
          :meth:`augment_resource` per resource. Same code path as
          per-resource, just amortizes Python overhead.
        - ``batch_size > 1, workers > 1``: dispatches to
          :meth:`_augment_batch_parallel` which uses a
          :class:`multiprocessing.Pool` (Step 6 of the FDD). When the
          parallel path is unavailable or the input is too small, falls
          back to synchronous chunked mode.

        INV-9 is preserved through the batch boundary: a single bad
        resource does not break the batch.

        Args:
            resources: List of FHIR R4 resource dicts. Mutated in place.
        """
        if not resources:
            return
        batch_size = max(1, int(self._config.batch_size))
        workers = max(1, int(self._config.workers))
        if batch_size == 1 or workers == 1:
            for resource in resources:
                self.augment_resource(resource)
            return
        # batch_size > 1 AND workers > 1.
        #
        # FDD Step 6 (multiprocessing for AutoCoder) is deferred per
        # ``FEATURE_BATCH_AUGMENTATION.md`` §Step 6: "Lower priority
        # (Phase 2 is less CPU-bound than Phase 4). Skip if Step 5
        # surfaces problems that warrant deferring." Step 5 surfaced
        # the DuckDB-shared-connection hazard; we defer.
        #
        # The cross-resource parallel win for AutoCoder is captured by
        # Step 4's HTTP thread pool in ``search_batch`` (FDD §Step 4),
        # which runs concurrently inside each per-resource
        # ``augment_resource`` call. No separate AutoCoder-side pool
        # is needed in the common (HTTP endpoint) case. The in-process
        # endpoint case remains single-threaded per resource, but each
        # SapBERT call releases the GIL so a future thread pool could
        # still help — that's future work.
        #
        # For now: dispatch synchronously to preserve correctness.
        #
        # Audit QA-004: the NotImplementedError branch exists only to
        # distinguish "Step 6 deferred" (today) from "Step 6 broken"
        # (future). If Step 6 is ever implemented, drop this branch
        # and let real failures surface via the generic Exception catch.
        try:
            self._augment_batch_parallel(resources)
        except NotImplementedError:
            # Expected — the pool is deferred. Synchronous chunked mode.
            for resource in resources:
                self.augment_resource(resource)
        except Exception as exc:  # noqa: BLE001 - INV-9-style: never poison the batch
            _logger.warning(
                "AutoCoder.augment_resources parallel path failed (%s); "
                "falling back to synchronous mode.",
                exc,
            )
            for resource in resources:
                self.augment_resource(resource)

    # ── internals ───────────────────────────────────────────────────

    def _augment_batch_parallel(self, resources: list[dict]) -> None:
        """Parallel batch augmentation (FDD Step 6 — DEFERRED).

        The original plan called for a thread pool here. Step 5 surfaced
        a DuckDB-shared-connection hazard that applies equally to
        threads: DuckDB ``Connection`` objects cannot be safely shared
        across concurrent ``execute()`` calls (per DuckDB Python docs).
        Workers would need to call ``con.cursor()`` per thread, which
        would require non-trivial AutoCoder refactoring.

        Per FDD §Step 6: "Skip if Step 5 surfaces problems that warrant
        deferring." We defer. The cross-resource parallel win for
        AutoCoder is captured by Step 4's HTTP thread pool in
        :meth:`HTTPTerminologyEndpoint.search_batch`, which runs
        concurrently inside each per-resource ``augment_resource`` call.

        Raises ``NotImplementedError`` so :meth:`augment_resources`
        falls back to synchronous chunked mode.
        """
        raise NotImplementedError(
            "AutoCoder parallel batch deferred (see FDD §Step 6). Step 4's "
            "HTTP thread pool captures the cross-resource parallel win."
        )

    def _augment_resource_inner(self, resource: dict) -> None:
        if not isinstance(resource, dict):
            return

        resource_type = resource.get("resourceType")
        if not isinstance(resource_type, str):
            return  # loader will raise on this — not our job

        category = resolve_category(
            resource_type, self._config.category_overrides
        )
        if category is None:
            _logger.debug(
                "AutoCoder: no category for resourceType=%s; skipping.",
                resource_type,
            )
            return

        paths = self._config.codeable_paths.get(resource_type)
        if not paths:
            _logger.debug(
                "AutoCoder: no CodeableConcept paths for resourceType=%s; skipping.",
                resource_type,
            )
            return

        for dotted_path in paths:
            cc = self._walk_path(resource, dotted_path)
            if cc is None:
                continue
            if not isinstance(cc, dict):
                _logger.debug(
                    "AutoCoder: path %s on %s did not resolve to a dict; skipping.",
                    dotted_path, resource_type,
                )
                continue
            self._augment_codeable_concept(cc, category)

    def _augment_codeable_concept(self, cc: dict, category: str) -> None:
        """Augment a single CodeableConcept dict in place.

        Pre-conditions (verified by caller): ``cc`` is a dict, ``category``
        is a non-empty string.

        Guards (FDD INV-2/INV-3/INV-4):
            * Empty/missing/whitespace-only text → skip.
            * Existing ``coding[]`` → skip (no double-coding).
            * Search returns 0 results → no Codings appended, no cache
              write (the cache stores the FULL pre-filter result, so
              re-runs with a stricter threshold will still hit cache).
        """
        text = cc.get("text")
        if not isinstance(text, str) or not text.strip():
            return  # INV-3: resources without text are untouched.

        existing_coding = cc.get("coding")
        if isinstance(existing_coding, list) and existing_coding:
            # INV-4: existing manual coding → do NOT re-code.
            return

        if len(text) > 200:
            _logger.debug(
                "AutoCoder: text length %d exceeds 200 chars (%r); "
                "Phase 4 NER handles long-form text.",
                len(text), text[:50] + "…",
            )

        normalized = normalize_text(text)
        if not normalized:
            return  # whitespace-only edge case after normalization.

        text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        search_mode = self._config.search_mode
        index_version = self._resolve_index_version()

        results = self._lookup_or_search(
            text_hash=text_hash,
            category=category,
            search_mode=search_mode,
            index_version=index_version,
            query_text=text,
        )

        if not results:
            return  # nothing to write.

        # Apply threshold + top_k AFTER cache lookup. Cache stores the
        # FULL pre-filter result so threshold/top_k changes do not
        # invalidate cache entries (FDD §3c step 5 + design handoff §2.5).
        kept = self._filter_and_truncate(results)

        if not kept:
            return

        # Build Codings. Each Coding carries the autocoding extension
        # (INV-5) and userSelected=False (INV-6). Append to coding[].
        codings: list[dict] = []
        for result in kept:
            ext = build_autocoding_extension(
                engine=_ENGINE_NAME,
                engine_version=self._config.engine_version,
                search_mode=result.get("search_mode") or search_mode,
                score=result.get("score", 0.0),
                match_grade=result.get("match_grade", "ambiguous"),
                index_version=result.get("index_version") or index_version,
            )
            coding: dict[str, Any] = {
                "system": result.get("system"),
                "code": result.get("code"),
                "display": result.get("display"),
                "userSelected": False,
                "extension": [ext],
            }
            codings.append(coding)

        # cc.coding may be missing or None — initialize before extending.
        existing = cc.get("coding")
        if not isinstance(existing, list):
            existing = []
        existing.extend(codings)
        cc["coding"] = existing

    def _filter_and_truncate(
        self, results: list[dict]
    ) -> list[dict]:
        """Filter by min_match_grade, sort by score desc, take top_k."""
        threshold_rank = _MATCH_GRADE_ORDER.get(
            self._config.min_match_grade, 0
        )
        kept = [
            r for r in results
            if _MATCH_GRADE_ORDER.get(r.get("match_grade", "ambiguous"), 3)
            <= threshold_rank
        ]
        # Sort by score descending. Stable sort preserves search-engine
        # ordering for ties. Defensive: NaN scores (shouldn't happen
        # but engines can produce them) sort LAST under reverse=True
        # with a key function that treats NaN as -inf.
        def _score_key(r: dict) -> float:
            s = r.get("score", 0.0)
            try:
                sf = float(s)
            except (TypeError, ValueError):
                return float("-inf")
            return sf if math.isfinite(sf) else float("-inf")

        kept.sort(key=_score_key, reverse=True)
        return kept[: self._config.top_k]

    # ── cache plumbing ──────────────────────────────────────────────

    def _ensure_cache_table(self) -> None:
        """Create the DuckDB cache table if missing. Idempotent.

        On any failure, sets ``self._cache_enabled = False`` and logs
        WARNING. Augmentation still works (falls through to direct
        endpoint call on every miss), just slower.
        """
        if self._con is None:
            _logger.warning(
                "AutoCoder: no DuckDB connection provided; cache disabled."
            )
            return
        try:
            self._con.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.CACHE_TABLE} (
                    text_hash      VARCHAR,
                    category       VARCHAR,
                    search_mode    VARCHAR,
                    index_version  VARCHAR,
                    result_json    VARCHAR,
                    cached_at      TIMESTAMP,
                    PRIMARY KEY (text_hash, category, search_mode, index_version)
                )
                """
            )
            self._cache_enabled = True
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            _logger.warning(
                "AutoCoder: cache table creation failed (%s); cache disabled.",
                exc,
            )
            self._cache_enabled = False

    def _lookup_or_search(
        self,
        *,
        text_hash: str,
        category: str,
        search_mode: str,
        index_version: str,
        query_text: str,
    ) -> list[dict]:
        """Cache lookup → endpoint search → cache write.

        Returns the list of result dicts (full pre-filter set). The
        caller is responsible for thresholding + top_k truncation.
        """
        cached = self._cache_lookup(
            text_hash, category, search_mode, index_version
        )
        if cached is not None:
            return cached

        # Cache miss → call endpoint. Errors propagate to augment_resource
        # which catches them (INV-9). search_batch is the primary call
        # path (batch-friendly for future async work).
        try:
            raw = self._endpoint.search_batch(
                [(query_text, category)], mode=search_mode
            )
        except Exception as exc:  # noqa: BLE001 - INV-9 surfacing
            _logger.warning(
                "AutoCoder: endpoint.search_batch failed for "
                "(text=%r, category=%s): %s",
                query_text[:50], category, exc,
            )
            raise  # augment_resource will catch and leave resource unchanged.

        if not raw or len(raw) == 0:
            return []
        first = raw[0]
        if not isinstance(first, list):
            return []
        results = [self._result_to_dict(r) for r in first]

        # Cache write. Failures are non-fatal (next call re-searches).
        self._cache_write(
            text_hash=text_hash,
            category=category,
            search_mode=search_mode,
            index_version=index_version,
            results=results,
        )
        return results

    def _cache_lookup(
        self,
        text_hash: str,
        category: str,
        search_mode: str,
        index_version: str,
    ) -> Optional[list[dict]]:
        if not self._cache_enabled:
            return None
        try:
            row = self._con.execute(
                f"""
                SELECT result_json FROM {self.CACHE_TABLE}
                WHERE text_hash   = ?
                  AND category     = ?
                  AND search_mode  = ?
                  AND index_version = ?
                """,
                [text_hash, category, search_mode, index_version],
            ).fetchone()
        except Exception as exc:  # noqa: BLE001
            _logger.debug(
                "AutoCoder: cache lookup failed (%s); treating as miss.",
                exc,
            )
            return None
        if row is None or row[0] is None:
            return None
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError) as exc:
            _logger.debug(
                "AutoCoder: cache row JSON decode failed (%s); treating as miss.",
                exc,
            )
            return None
        if not isinstance(data, list):
            return None
        return data

    def _cache_write(
        self,
        *,
        text_hash: str,
        category: str,
        search_mode: str,
        index_version: str,
        results: list[dict],
    ) -> None:
        if not self._cache_enabled:
            return
        try:
            payload = json.dumps(results)
        except (TypeError, ValueError) as exc:
            _logger.warning(
                "AutoCoder: cache write skipped — result JSON encode failed (%s).",
                exc,
            )
            return
        try:
            # INSERT OR REPLACE — DuckDB supports this for PK tables.
            self._con.execute(
                f"""
                INSERT OR REPLACE INTO {self.CACHE_TABLE}
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [text_hash, category, search_mode, index_version, payload],
            )
        except Exception as exc:  # noqa: BLE001
            _logger.debug(
                "AutoCoder: cache write failed (%s); continuing without caching.",
                exc,
            )

    # ── index-version probe-and-pin ─────────────────────────────────

    def _resolve_index_version(self) -> str:
        """One-shot probe-and-pin of the endpoint's index_version.

        If the user configured an explicit ``index_version`` in the
        config, that wins. Otherwise, the first call resolves via a
        cheap ``search_text("diabetes", "condition", mode=...)`` probe
        and pins the result for the rest of the run.

        Returns ``"unknown"`` if the probe fails or the endpoint
        reports no version. (The cache key includes this string, so a
        later index refresh changes the key and forces fresh searches
        — INV-8.)
        """
        if self._config.index_version is not None:
            return self._config.index_version
        if self._index_version_resolved:
            return self._pinned_index_version or "unknown"

        try:
            results = self._endpoint.search_text(
                "diabetes", "condition", mode=self._config.search_mode
            )
            if results:
                version = getattr(results[0], "index_version", None)
                if isinstance(version, str) and version:
                    self._pinned_index_version = version
                elif isinstance(results[0], dict):
                    v = results[0].get("index_version")
                    if isinstance(v, str) and v:
                        self._pinned_index_version = v
        except Exception as exc:  # noqa: BLE001 - probe is best-effort
            _logger.debug(
                "AutoCoder: index-version probe failed (%s); pinning 'unknown'.",
                exc,
            )

        self._index_version_resolved = True
        return self._pinned_index_version or "unknown"

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _walk_path(resource: dict, dotted_path: str) -> Any:
        """Dotted-path walker. Returns ``None`` on any miss.

        Each segment is a dict key lookup. ``None`` at any level
        short-circuits. List-valued intermediates return ``None``
        (Phase 2 v1 limitation — see module docstring + FDD §3f).
        """
        current: Any = resource
        for segment in dotted_path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
            if current is None:
                return None
        return current

    @staticmethod
    def _result_to_dict(result: Any) -> dict:
        """Convert a SearchResult (dataclass or dict) to plain dict.

        The cache stores dicts (JSON-encodable). Both SearchResult
        instances and existing dicts pass through cleanly.
        """
        if isinstance(result, dict):
            return {
                "system": result.get("system"),
                "code": result.get("code"),
                "display": result.get("display"),
                "score": result.get("score", 0.0),
                "match_grade": result.get("match_grade", "ambiguous"),
                "search_mode": result.get("search_mode", "hybrid"),
                "index_version": result.get("index_version"),
            }
        if dataclasses.is_dataclass(result):
            d = dataclasses.asdict(result)
            return d
        # Unknown shape — best-effort passthrough.
        try:
            return dict(result)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            return {}
