"""Notes-pipeline orchestrator: free-text → derived FHIR Conditions.

Phase 4 of the medterm4ds integration. The pipeline extracts text from
configured note paths on a FHIR resource, calls
``medterm4ds.extract(text, format="codes", ...)`` for each fragment, and
wraps every affirmed concept in a synthetic Condition resource carrying:

* Phase 2's autocoding extension (engine="medterm4ds-ner") on the Coding.
* Phase 4's derived-from-text extension on the Condition (source-ref,
  source-path, span offsets, matched-text) for audit/debug.

Reference: FDD §3 (SCOPE REDUCTION block) at the top of
``docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md``.

Invariants (FDD §7):

* INV-1 / Phase 1: ``import fhir4ds`` must succeed without medterm4ds.
  ``medterm4ds`` is imported lazily inside :meth:`_ensure_medterm4ds`;
  nothing at module top references it.
* INV-3 (loader safety): :meth:`extract_conditions` NEVER raises —
  every exception is caught, logged WARNING, and an empty list is
  returned. A single bad resource cannot break the batch load.
* INV-4 (no Condition-on-Condition derivation): when the source
  resource_type is ``"Condition"`` the pipeline returns ``[]`` so
  batch loads cannot enter an infinite loop.
* INV-6 (deterministic ids): the derived Condition id is a sha256 hash
  of ``(source_ref, span_start, span_end, system, code)`` truncated to
  32 chars, so re-running the pipeline on the same source yields
  byte-identical Conditions. ``system`` is the post-normalization FHIR
  canonical URL so two concepts from different code systems at the same
  span don't collide (REV-005).
* INV-7 (system URL normalization): medterm4ds returns source mnemonics
  (``"SNOMEDCT_US"``); fhir4ds MUST expand them to canonical FHIR URLs.
  This is delegated to Phase 1's mnemonic map in
  :mod:`fhir4ds.cql.terminology.in_process_adapter` plus
  :class:`SystemResolver` for OID / SNOMED module normalization.

Zero-dep guarantee: at import time, only stdlib + fhir4ds-internal
modules are referenced. ``medterm4ds`` is imported inside
:meth:`_ensure_medterm4ds` on first use.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .autocoding_extension import build_autocoding_extension
from .derived_from_text_extension import build_derived_from_text_extension
from .notes_text_extractor import DEFAULT_NOTE_PATHS, NoteText, extract_note_texts

__all__ = [
    "NotesPipeline",
    "NotesPipelineConfig",
    "DEFAULT_NOTE_PATHS",
]

_logger = logging.getLogger(__name__)

#: Engine label written into Phase 2's autocoding extension. Distinct
#: from the Phase 2 default (``"medterm4ds"``) so downstream consumers
#: can tell Codings produced by the NER pipeline apart from Codings
#: produced by the text-CodeableConcept auto-coder.
_ENGINE_NAME = "medterm4ds-ner"

#: Deterministic-id salt bucket. The literal prefix keeps Phase 4 ids
#: out of the same hash space as any future fhir4ds synthesizer.
_ID_SALT = "fhir4ds-phase4-derived-condition"

#: Type alias for the per-resource return shape: one derived Condition
#: per dict, a list of them per source resource.
DerivedConditions = list[dict]

#: Empirical per-worker memory budget for medspaCy + SapBERT
#: (audit QA-005). Used by :meth:`NotesPipeline._extract_batch_parallel`
#: to emit a WARNING when ``workers * budget`` exceeds available
#: virtual memory. Not a hard gate — the user explicitly opts into
#: ``workers`` and may have pre-warmed medspaCy or be on a machine
#: with swap. Override by lowering ``workers``.
WORKER_MEMORY_BUDGET_BYTES = 5 * (1024 ** 3)

# ----------------------------------------------------------------------
# Multiprocessing worker globals (Step 5)
#
# Workers MUST be module-level functions and MUST NOT close over ``self``
# (which would pickle the parent's DuckDB connection — fork-unsafe).
# Configuration travels via these module globals, populated by the Pool
# initializer. They are process-local: each worker process gets its own
# copy after ``spawn`` or ``fork``.
# ----------------------------------------------------------------------

#: Per-worker extract kwargs (frozen at pool-init time). Set by
#: ``_init_worker``. Read by ``_worker_extract_fragments``.
_WORKER_EXTRACT_KWARGS: dict = {}


@dataclass(frozen=True)
class NotesPipelineConfig:
    """Configuration for :class:`NotesPipeline`.

    All fields have safe defaults that match the FDD SCOPE REDUCTION
    block. A freshly-constructed ``NotesPipelineConfig()`` runs the
    full pipeline in strict-by-default posture: only affirmed concepts
    at-or-above ``"certain"`` match grade generate Conditions.

    Attributes:
        note_paths: Per-resource-type dotted-path map. Defaults to
            :data:`DEFAULT_NOTE_PATHS`.
        categories: Optional medterm4ds category filter (``["condition",
            "medication", ...]``). ``None`` = all categories.
        mode: Search mode (``"lexical"``/``"semantic"``/``"hybrid"``).
            ``None`` lets medterm4ds pick its default (hybrid).
        min_grade: Minimum match grade to keep (``"certain"``/``"probable"``
            /``"possible"``). Default ``"certain"``.
        include_negated: When ``True``, also emit Conditions for negated
            concepts (status == ``"negated"``). Default ``False``.
        include_uncertain: When ``True``, also emit Conditions for
            uncertain concepts. Default ``False``.
        include_historical: When ``True``, also emit Conditions for
            historical concepts. Default ``False``.
        verification_status: Default ``verificationStatus.coding[0].code``
            on derived Conditions. Default ``"unconfirmed"``.
        clinical_status: Default ``clinicalStatus.coding[0].code`` on
            derived Conditions. Default ``"active"``.
        batch_size: Number of resources processed per call to
            :meth:`extract_conditions_batch`. Default ``1`` preserves
            today's per-resource code path byte-for-byte. Larger values
            enable batch-aware chunking and (when ``workers > 1``)
            parallel extraction via :class:`multiprocessing.Pool`.
        workers: Size of the multiprocessing pool used when
            ``batch_size > 1`` and ``len(resources) >=
            parallel_threshold``. Default ``1`` preserves single-process
            behavior. Each worker loads its own medterm4ds engine
            (~5 GB for medspaCy + SapBERT); on a 16 GB machine,
            ``workers=2`` is the practical max. On Windows,
            ``multiprocessing`` uses ``spawn`` (not ``fork``) — workers
            re-import ``medterm4ds`` from scratch. User code calling
            :class:`NotesPipeline` from a script MUST guard the entry
            point with ``if __name__ == "__main__":`` to avoid recursive
            worker imports on Windows.
        parallel_threshold: Minimum input size required before the
            multiprocessing pool is used. Below this threshold the
            pipeline uses synchronous mode regardless of ``workers`` —
            the cold medspaCy warm-up cost (~30s per worker) outweighs
            the per-text savings for small batches. Default ``200``,
            tuned for cold-start; users with pre-warmed medspaCy may
            lower it to ``0``. An INFO log line is emitted when the
            threshold fires AND ``workers > 1`` (when ``workers == 1``
            the user has explicitly chosen sync mode, so no diagnostic
            is needed).
    """

    note_paths: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_NOTE_PATHS))
    categories: Optional[list[str]] = None
    mode: Optional[str] = None
    min_grade: Optional[str] = "certain"
    include_negated: bool = False
    include_uncertain: bool = False
    include_historical: bool = False
    verification_status: str = "unconfirmed"
    clinical_status: str = "active"
    batch_size: int = 1
    workers: int = 1
    parallel_threshold: int = 200

    def __post_init__(self) -> None:
        """Validate non-negative performance knobs at construction.

        Per GLOBAL_RULES "No Silent Fallbacks": the runtime ``max(1, ...)``
        clamp in :meth:`NotesPipeline.extract_conditions_batch` would
        otherwise discard user intent silently. The dataclass is frozen,
        so a misconfigured value cannot be fixed post-construction — the
        caller MUST be told at construction time. Raises ``ValueError``
        for any non-positive ``workers`` or ``batch_size`` so the user
        sees the misconfiguration immediately.
        """
        if not isinstance(self.workers, int) or self.workers < 1:
            raise ValueError(
                f"NotesPipelineConfig.workers must be a positive int (>=1), "
                f"got {self.workers!r}"
            )
        if not isinstance(self.batch_size, int) or self.batch_size < 1:
            raise ValueError(
                f"NotesPipelineConfig.batch_size must be a positive int (>=1), "
                f"got {self.batch_size!r}"
            )
        if not isinstance(self.parallel_threshold, int) or self.parallel_threshold < 0:
            raise ValueError(
                f"NotesPipelineConfig.parallel_threshold must be a non-negative int, "
                f"got {self.parallel_threshold!r}"
            )


class NotesPipeline:
    """Orchestrates free-text → derived Condition extraction.

    The pipeline is constructed cheaply (no medterm4ds import). The
    first call to :meth:`extract_conditions` triggers a lazy load of
    ``medterm4ds.extract`` via :meth:`_ensure_medterm4ds`.

    Example::

        from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

        pipeline = NotesPipeline(NotesPipelineConfig())
        derived = pipeline.extract_conditions(observation_resource)
        # derived: list[dict] of Condition resources
    """

    def __init__(self, config: Optional[NotesPipelineConfig] = None) -> None:
        self._config = config if config is not None else NotesPipelineConfig()
        # Lazy: ``_extract_fn`` is populated by ``_ensure_medterm4ds()``
        # on the first call to ``extract_conditions``. Stays ``None``
        # until then so module import never touches medterm4ds.
        self._extract_fn: Any = None
        self._medterm4ds_index_version: Optional[str] = None
        # REV-006: cached medterm4ds engine version string. Populated on
        # first call to :meth:`_medterm4ds_engine_version` so a batch load
        # over thousands of notes only triggers one
        # ``importlib.metadata.version`` lookup.
        self._medterm4ds_engine_version_cached: Optional[str] = None

    # ------------------------------------------------------------------
    # Lazy medterm4ds loading
    # ------------------------------------------------------------------

    def _ensure_medterm4ds(self) -> None:
        """Lazily import ``medterm4ds.extract`` on first use.

        Raises ImportError with an install hint if medterm4ds is not
        available. The exception escapes :meth:`extract_conditions`'s
        try/except only on the very first call — subsequent calls
        short-circuit on the cached ``self._extract_fn``.
        """
        if self._extract_fn is not None:
            return
        try:
            import medterm4ds  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised when extra missing
            raise ImportError(
                "medterm4ds is required for NotesPipeline. Install with: "
                "pip install 'fhir4ds-v2[ner]'  (which pulls medterm4ds[extraction])"
            ) from exc
        self._extract_fn = medterm4ds.extract
        # Best-effort index-version probe. medterm4ds MAY expose
        # ``__index_version__`` or ``get_index_version()``; if neither
        # is present, the autocoding extension falls back to "unknown".
        version: Optional[str] = getattr(medterm4ds, "__index_version__", None)
        if version is None:
            getter = getattr(medterm4ds, "get_index_version", None)
            if callable(getter):
                try:
                    version = getter()
                except Exception:  # pragma: no cover - defensive
                    version = None
        self._medterm4ds_index_version = version if isinstance(version, str) else None

    def _medterm4ds_engine_version(self) -> str:
        """Return the installed medterm4ds version, cached per-instance.

        REV-006: previously this was a module-level function called once
        per derived Condition (each Condition triggered an
        ``importlib.metadata.version("medterm4ds")`` lookup). At scale
        (10k notes) that is 10k+ identical lookups. Now the value is
        resolved on first use and cached on the pipeline instance.
        """
        if self._medterm4ds_engine_version_cached is None:
            self._medterm4ds_engine_version_cached = _fetch_medterm4ds_engine_version()
        return self._medterm4ds_engine_version_cached

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_conditions(self, resource: dict) -> list[dict]:
        """Extract Conditions from a single FHIR resource's note text.

        NEVER raises. All exceptions are caught, logged at WARNING, and
        an empty list is returned (INV-3).

        Args:
            resource: A FHIR R4 resource dict.

        Returns:
            List of derived Condition dicts (possibly empty). The
            source resource is unchanged.
        """
        try:
            if not isinstance(resource, dict):
                _logger.warning(
                    "NotesPipeline.extract_conditions expected dict, got %s — skipping.",
                    type(resource).__name__,
                )
                return []

            # INV-4: never derive Conditions from Conditions. Prevents
            # infinite loops in batch loads where derived resources get
            # re-fed into the pipeline.
            if resource.get("resourceType") == "Condition":
                return []

            try:
                self._ensure_medterm4ds()
            except ImportError as exc:
                # medterm4ds missing — log once and bail. We do NOT
                # re-raise (INV-3) so a misconfigured pipeline degrades
                # to a no-op rather than poisoning the loader batch.
                _logger.warning("NotesPipeline disabled: %s", exc)
                self._extract_fn = _DISABLED_SENTINEL
                return []

            if self._extract_fn is _DISABLED_SENTINEL:
                return []

            fragments = extract_note_texts(resource, self._config.note_paths)
            if not fragments:
                return []

            conditions: list[dict] = []
            for fragment in fragments:
                try:
                    concepts = self._call_medterm4ds(fragment.text)
                except Exception as exc:  # pragma: no cover - defensive
                    _logger.warning(
                        "medterm4ds.extract raised on %s path=%s: %s — skipping fragment.",
                        fragment.source_ref, fragment.path, exc,
                    )
                    continue
                for concept in concepts:
                    try:
                        cond = self._build_condition(concept, fragment, resource)
                    except Exception as exc:  # pragma: no cover - defensive
                        _logger.warning(
                            "Failed to build derived Condition from %s path=%s code=%r: %s",
                            fragment.source_ref, fragment.path,
                            _safe_getattr(concept, "code"), exc,
                        )
                        continue
                    if cond is not None:
                        conditions.append(cond)
            return conditions
        except Exception as exc:
            # INV-3: NEVER raise from extract_conditions. Single bad
            # resource must not break the load.
            _logger.warning(
                "NotesPipeline.extract_conditions failed on resource %r: %s",
                resource.get("resourceType") if isinstance(resource, dict) else type(resource).__name__,
                exc,
            )
            return []

    def extract_conditions_batch(
        self, resources: list[dict]
    ) -> list[DerivedConditions]:
        """Batch-aware extraction. Returns one list of derived Conditions
        per input resource, preserving input order.

        Execution strategy is governed by ``self._config.batch_size``,
        ``self._config.workers``, and ``self._config.parallel_threshold``:

        - ``batch_size == 1`` or ``workers == 1``: chunks the input by
          ``batch_size`` and loops synchronously, calling
          :meth:`extract_conditions` per chunk. Byte-identical to
          today's per-resource path.
        - ``batch_size > 1`` and ``workers > 1`` and
          ``len(resources) >= parallel_threshold``: dispatches to
          :meth:`_extract_batch_parallel` which uses a
          :class:`multiprocessing.Pool`. Falls back to synchronous
          chunked mode on any failure.

        INV-3 / INV-A4 preserved through the batch boundary: a single
        bad resource does not break the batch.

        Example::

            >>> batch = pipeline.extract_conditions_batch([r1, r2, r3])
            >>> len(batch) == 3
            >>> batch[0]  # list of Conditions derived from r1
            [{'resourceType': 'Condition', 'id': '...', ...}, ...]

        Args:
            resources: List of FHIR R4 resource dicts.

        Returns:
            One list of derived Condition dicts per input resource.
            Outer length always equals ``len(resources)``; inner
            length may be zero.
        """
        if not isinstance(resources, list):
            raise TypeError(
                f"Expected list of FHIR resource dicts, got {type(resources).__name__}"
            )
        if not resources:
            return []
        batch_size = max(1, int(self._config.batch_size))
        workers = max(1, int(self._config.workers))
        threshold = max(0, int(self._config.parallel_threshold))
        if batch_size == 1 or workers == 1 or len(resources) < threshold:
            if workers > 1 and len(resources) < threshold:
                _logger.info(
                    "NotesPipeline.extract_conditions_batch: len=%d < "
                    "parallel_threshold=%d; using synchronous mode.",
                    len(resources), threshold,
                )
            results: list[DerivedConditions] = []
            for i in range(0, len(resources), batch_size):
                chunk = resources[i : i + batch_size]
                for resource in chunk:
                    results.append(self.extract_conditions(resource))
            return results
        # Parallel path
        try:
            return self._extract_batch_parallel(resources)
        except Exception as exc:
            _logger.warning(
                "NotesPipeline.extract_conditions_batch parallel path failed "
                "(%s); falling back to synchronous mode.",
                exc,
            )
            return [
                self.extract_conditions(r) for r in resources
            ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_kwargs(self) -> dict:
        """Build the medterm4ds.extract kwargs dict from the config.

        Centralized so :meth:`_call_medterm4ds` (sync) and the Pool
        initializer (parallel) build the identical kwargs.
        """
        kwargs: dict[str, Any] = {"format": "codes"}
        if self._config.categories is not None:
            kwargs["categories"] = list(self._config.categories)
        if self._config.mode is not None:
            kwargs["mode"] = self._config.mode
        if self._config.min_grade is not None:
            kwargs["min_grade"] = self._config.min_grade
        kwargs["include_negated"] = self._config.include_negated
        kwargs["include_uncertain"] = self._config.include_uncertain
        kwargs["include_historical"] = self._config.include_historical
        return kwargs

    def _extract_batch_parallel(
        self, resources: list[dict]
    ) -> list[DerivedConditions]:
        """Parallel extraction via :class:`multiprocessing.Pool`.

        Step 5 of the FDD. Workers are module-level functions
        (:func:`_init_worker`, :func:`_worker_extract_fragments`);
        they read configuration from module globals populated by the
        Pool initializer. Workers convert medterm4ds concepts to plain
        dicts at the process boundary (defensive picklability) and
        group them per-fragment so the parent can rebuild Conditions
        with full fragment context.

        On any failure, raises so :meth:`extract_conditions_batch` can
        fall back to synchronous mode.
        """
        if not resources:
            return []
        import os
        # Bounded worker count. ``os.cpu_count()`` returns None on
        # exotic platforms; fall back to 1.
        cpu = os.cpu_count() or 1
        actual_workers = max(1, min(int(self._config.workers), cpu))

        # Optional memory-pressure warning (INV-A8). ``psutil`` is NOT
        # a fhir4ds dependency; the warning is best-effort.
        try:
            import psutil  # type: ignore[import-not-found]
            available = psutil.virtual_memory().available
            if actual_workers * WORKER_MEMORY_BUDGET_BYTES > available:
                _logger.warning(
                    "NotesPipeline parallel mode: workers=%d × ~5GB exceeds "
                    "available virtual memory %d bytes; consider lowering "
                    "workers or pre-warming medspaCy.",
                    actual_workers, available,
                )
        except ImportError:
            pass  # psutil is optional — silent skip.

        # Pre-compute text fragments in the parent. Workers receive the
        # already-extracted fragments so they don't have to import the
        # fhir4ds text extractor (cleaner process boundary, smaller
        # pickled payload).
        payloads: list[tuple[dict, list]] = []
        for resource in resources:
            if not isinstance(resource, dict):
                payloads.append((resource, []))
                continue
            # INV-4 mirrored: never derive Conditions from Conditions.
            if resource.get("resourceType") == "Condition":
                payloads.append((resource, []))
                continue
            try:
                fragments = extract_note_texts(resource, self._config.note_paths)
            except Exception as exc:  # pragma: no cover - defensive
                _logger.warning(
                    "extract_note_texts raised on %r: %s; treating as 0 fragments.",
                    resource.get("resourceType") if isinstance(resource, dict) else None,
                    exc,
                )
                fragments = []
            payloads.append((resource, fragments))

        # Build kwargs once (centralized in :meth:`_extract_kwargs`).
        extract_kwargs = self._extract_kwargs()

        # Dispatch via multiprocessing.Pool. ``spawn`` (Windows) and
        # ``fork`` (POSIX) both work because workers are module-level
        # functions with no closure over ``self``.
        from multiprocessing import Pool
        with Pool(
            actual_workers,
            initializer=_init_worker,
            initargs=(extract_kwargs,),
        ) as pool:
            chunksize = max(1, len(payloads) // (actual_workers * 4))
            worker_results = pool.map(
                _worker_extract_fragments, payloads, chunksize=chunksize,
            )

        # Build derived Conditions in the PARENT process. This keeps
        # ``_build_condition`` (which reads ``self._config``) on the
        # right side of the process boundary — workers never reference
        # ``self``. The deterministic id (INV-6) is computed in the
        # parent so the hash is identical to the sync path.
        results: list[DerivedConditions] = []
        for (resource, fragments), fragment_concepts in zip(payloads, worker_results):
            conditions: list[dict] = []
            # fragment_concepts is list[list[dict]] — outer per fragment,
            # inner per concept. ``zip(fragments, fragment_concepts)``
            # is safe because workers preserve outer length.
            for fragment, concepts in zip(fragments, fragment_concepts):
                for concept in concepts or []:
                    cond = self._build_condition(concept, fragment, resource)
                    if cond is not None:
                        conditions.append(cond)
            results.append(conditions)
        return results

    def _call_medterm4ds(self, text: str) -> list[Any]:
        """Invoke the cached ``medterm4ds.extract`` with pipeline kwargs.

        Delegates to :meth:`_extract_kwargs` so the sync and parallel
        paths build identical kwargs (audit QA-002).
        """
        return self._extract_fn(text, **self._extract_kwargs())

    def _build_condition(
        self,
        concept: Any,
        fragment: NoteText,
        source_resource: dict,
    ) -> Optional[dict]:
        """Wrap a single medterm4ds concept into a FHIR Condition dict.

        Returns ``None`` when the concept's status is filtered out by
        the pipeline config (negated/uncertain/historical exclusion).
        """
        status = _safe_getattr(concept, "status") or "affirmed"
        if status != "affirmed":
            # Configured include_* flags already steered medterm4ds; if a
            # non-affirmed concept still made it through, the user opted
            # in via the matching flag. Otherwise skip.
            if status == "negated" and not self._config.include_negated:
                return None
            if status == "uncertain" and not self._config.include_uncertain:
                return None
            if status == "historical" and not self._config.include_historical:
                return None

        code = _safe_getattr(concept, "code")
        if not code:
            return None

        system = _normalize_system(_safe_getattr(concept, "source"))
        display = _safe_getattr(concept, "display")
        confidence = _safe_getattr(concept, "confidence") or 0.0
        match_grade = _safe_getattr(concept, "match_grade") or "possible"
        matched_text = _safe_getattr(concept, "matched_text") or ""
        span_start = _safe_getattr(concept, "span_start") or 0
        span_end = _safe_getattr(concept, "span_end") or 0

        # Phase 2 autocoding extension on the Coding — engine is
        # ``"medterm4ds-ner"`` so downstream consumers can distinguish
        # NER-derived Codings from text-CodeableConcept auto-codes.
        autocoding = build_autocoding_extension(
            engine=_ENGINE_NAME,
            engine_version=self._medterm4ds_engine_version(),
            search_mode=self._config.mode if self._config.mode is not None else "hybrid",
            score=float(confidence),
            match_grade=str(match_grade),
            index_version=self._medterm4ds_index_version,
        )
        coding: dict[str, Any] = {
            "system": system,
            "code": str(code),
            "userSelected": False,
            "extension": [autocoding],
        }
        if display:
            coding["display"] = str(display)
        codeable_concept: dict[str, Any] = {"coding": [coding]}
        if display:
            codeable_concept["text"] = str(display)

        # Phase 4 derived-from-text extension on the Condition — audit
        # /debug provenance (source resource + path + span + text).
        derived_ext = build_derived_from_text_extension(
            source_ref=fragment.source_ref,
            source_path=fragment.path,
            span_start=int(span_start),
            span_end=int(span_end),
            matched_text=str(matched_text),
        )

        # Deterministic Condition id (INV-6): sha256 of
        # (salt, source_ref, span_start, span_end, system, code),
        # truncated. REV-005: ``system`` (the post-normalization FHIR
        # canonical URL) is included in the digest so two concepts from
        # different code systems at the same span on the same source
        # don't collide and silently get dropped by loader id-dedup.
        digest_input = "␟".join([
            _ID_SALT,
            fragment.source_ref,
            str(span_start),
            str(span_end),
            str(system) if system is not None else "",
            str(code),
        ])
        digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
        condition_id = digest[:32]

        condition: dict[str, Any] = {
            "resourceType": "Condition",
            "id": condition_id,
            "extension": [derived_ext],
            "code": codeable_concept,
            "verificationStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                    "code": self._config.verification_status,
                }]
            },
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": self._config.clinical_status,
                }]
            },
        }

        # Subject provenance: copy from source resource if present.
        subject = source_resource.get("subject") if isinstance(source_resource, dict) else None
        if isinstance(subject, dict) and subject.get("reference"):
            condition["subject"] = {"reference": subject["reference"]}

        # Evidence: point back at the source resource.
        if fragment.source_ref:
            condition["evidence"] = [{
                "code": [codeable_concept],
                "detail": [{"reference": fragment.source_ref}],
            }]

        return condition


# ----------------------------------------------------------------------
# Module-private helpers
# ----------------------------------------------------------------------


def _safe_getattr(obj: Any, name: str) -> Any:
    """``getattr`` that also supports dict-like concept objects.

    medterm4ds ``ExtractedConcept`` is a dataclass (attribute access),
    but the pipeline tolerates a plain dict so unit tests can mock it
    with the cheapest possible fixture.
    """
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


# ----------------------------------------------------------------------
# Multiprocessing worker functions (Step 5)
#
# These are module-level functions — NOT methods. They MUST NOT close
# over ``self`` (which would pickle the parent's DuckDB connection —
# fork-unsafe). Configuration is delivered via the Pool initializer
# into module globals (``_WORKER_ENGINE``, ``_WORKER_EXTRACT_KWARGS``).
# ----------------------------------------------------------------------


def _init_worker(extract_kwargs: dict) -> None:
    """Pool initializer: import medterm4ds and pre-warm the NLP pipeline.

    Runs once per worker process. Sets the module global
    ``_WORKER_EXTRACT_KWARGS`` so subsequent calls to
    :func:`_worker_extract_fragments` can read them without closing
    over the parent's state.

    Note: ``medterm4ds.connect()`` returns a :class:`Terminology` object
    for code lookup (ancestors, descendants, mapping) — it does NOT
    expose ``extract()``. The NER extraction entry point is the
    module-level :func:`medterm4ds.extract` function. We import the
    module and pin a reference to its ``extract`` callable; the first
    call triggers the lazy load of GLiNER + medspaCy + BM25 + SapBERT +
    FAISS (~30s cold, ~0s warm), then subsequent calls reuse the
    cached pipeline.
    """
    global _WORKER_EXTRACT_KWARGS
    try:
        import medterm4ds  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise ImportError(
            "medterm4ds is required for parallel NotesPipeline. Install with: "
            "pip install 'fhir4ds-v2[ner]'  (which pulls medterm4ds[extraction])"
        ) from exc
    # Pin the module-level extract function. ``connect()`` is the
    # terminology-lookup API (returns Terminology without .extract);
    # we want the NER extraction API.
    global _WORKER_EXTRACT_FN
    _WORKER_EXTRACT_FN = medterm4ds.extract
    _WORKER_EXTRACT_KWARGS = dict(extract_kwargs)


#: Per-worker extract function (set by ``_init_worker``). Module-level
#: :func:`medterm4ds.extract`; not the ``Terminology`` object from
#: :func:`medterm4ds.connect`.
_WORKER_EXTRACT_FN: Any = None


def _worker_extract_fragments(
    payload: tuple[dict, list],
) -> list[list[dict]]:
    """Worker function: extract concepts for one resource, grouped by fragment.

    Args:
        payload: ``(resource, fragments)`` tuple where ``fragments`` is
            the pre-computed list of :class:`NoteText` entries from the
            parent (avoids re-running the text extractor in workers).

    Returns:
        Per-fragment list of concept **dicts** (post-boundary
        conversion). Outer length always equals ``len(fragments)``;
        inner length may be zero. medterm4ds's ``ExtractedConcept``
        dataclass is converted to plain dicts here so the result is
        unconditionally picklable. Never raises — worker failures
        return an empty outer list so a single bad resource cannot
        poison the batch.
    """
    if _WORKER_EXTRACT_FN is None:
        return []
    _resource, fragments = payload
    out: list[list[dict]] = []
    for fragment in fragments:
        try:
            concepts = _WORKER_EXTRACT_FN(fragment.text, **_WORKER_EXTRACT_KWARGS)
        except Exception:  # pragma: no cover - defensive
            out.append([])
            continue
        fragment_out: list[dict] = []
        for concept in concepts or []:
            if isinstance(concept, dict):
                fragment_out.append(concept)
            else:
                # Convert dataclass-like to dict at the process boundary
                fragment_out.append({
                    "code": _safe_getattr(concept, "code"),
                    "display": _safe_getattr(concept, "display"),
                    "source": _safe_getattr(concept, "source"),
                    "confidence": _safe_getattr(concept, "confidence"),
                    "match_grade": _safe_getattr(concept, "match_grade"),
                    "matched_text": _safe_getattr(concept, "matched_text"),
                    "span_start": _safe_getattr(concept, "span_start"),
                    "span_end": _safe_getattr(concept, "span_end"),
                    "status": _safe_getattr(concept, "status"),
                })
        out.append(fragment_out)
    return out


def _normalize_system(source: Any) -> Optional[str]:
    """Expand a medterm4ds source mnemonic to its FHIR canonical URL.

    Two-pass normalization (mirrors
    :meth:`InProcessTerminologyEndpoint._normalize_system`):

    1. If ``source`` is a UMLS mnemonic (``SNOMEDCT_US``, ``RXNORM``,
       ``LNC``, ...), expand it via the shared mnemonic map.
    2. Flow through :class:`SystemResolver` so OID and SNOMED module
       URLs also reduce to canonical form.

    Unknown values pass through unchanged (defensive).

    REV-007: the mnemonic map is now imported from the public
    :mod:`fhir4ds.cql.terminology.system_mappings` module (no underscore
    private import) so refactors of ``in_process_adapter`` cannot break
    pipeline system normalization silently.
    """
    if source is None:
        return None
    s = str(source)
    # Import the mnemonic map lazily so this module remains importable
    # even if the terminology package is partially refactored. Falls
    # back to an empty map (which leaves the input unchanged after
    # SystemResolver normalization) — worst case is no expansion, not
    # an import error.
    try:
        from fhir4ds.cql.terminology.system_mappings import (
            SOURCE_MNEMONIC_TO_URL,
        )
    except ImportError:  # pragma: no cover - defensive
        SOURCE_MNEMONIC_TO_URL = {}
    mapped = SOURCE_MNEMONIC_TO_URL.get(s, s)
    try:
        from fhir4ds.cql.duckdb.udf.system_resolver import SystemResolver
        return SystemResolver.normalize(mapped)
    except ImportError:  # pragma: no cover - defensive
        return mapped


def _fetch_medterm4ds_engine_version() -> str:
    """Resolve the installed medterm4ds version (one lookup per call).

    Used to seed the per-instance cache in
    :meth:`NotesPipeline._medterm4ds_engine_version`. Kept as a
    module-private helper so the cache and the actual lookup are
    testable independently.
    """
    try:
        from importlib.metadata import version  # py3.10+
        try:
            return version("medterm4ds")
        except Exception:  # pragma: no cover - package not installed
            return "unknown"
    except ImportError:  # pragma: no cover
        return "unknown"


#: Sentinel cached into ``self._extract_fn`` when medterm4ds is missing
#: so we don't retry the ImportError on every subsequent call. Kept as
#: a module-private to dodge a circular ``self`` reference.
_DISABLED_SENTINEL = object()
