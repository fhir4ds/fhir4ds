"""Builder/parser for the ``autocoding`` FHIR R4 extension.

Every Coding written by :class:`fhir4ds.cql.loader.auto_coder.AutoCoder`
carries this structured extension. The URL is canonical and stable
across releases; downstream consumers (Phase 5 staleness sweep) detect
auto-coded Codings by this URL.

Reference: FDD §3d, copied verbatim from master plan §2.

Extension shape (v2, FHIR4-24 — eight sub-extensions; the last two are
optional and emitted only when the query text came from the coding[]
rather than ``code.text``):

    {
        "url": "https://fhir4ds.com/fhir/StructureDefinition/autocoding",
        "extension": [
            {"url": "engine",          "valueString":  "medterm4ds"},
            {"url": "engine-version",  "valueString":  "<engine_version>"},
            {"url": "search-mode",     "valueCode":    "hybrid"},
            {"url": "score",           "valueDecimal": 0.87},
            {"url": "match-grade",     "valueCode":    "certain"},
            {"url": "index-version",   "valueString":  "2026AA-bm25-v3"},
            {"url": "query-source",    "valueCode":    "code"},        # optional
            {"url": "query-system",    "valueString":  "mimic-medication-name"}  # optional
        ]
    }

``query-source`` records which precedence leg produced the query text
(``text`` | ``display`` | ``code``); ``query-system`` records the
NON-standard system URI that justified legs 2/3 (absent for the
``text`` leg and for code-less display entries). v1 rows (six fields,
no query provenance) still parse — the new fields read back as
``None``.

Zero-dependency guarantee: stdlib only (``math``, ``typing``).
"""

from __future__ import annotations

import math
from typing import Optional

#: Canonical URL for the autocoding extension. Stable across releases.
#: Downstream consumers detect auto-coded Codings by this URL.
#:
#: NOTE: this used to be ``http://fhir4ds.org/...``. The project does not own
#: fhir4ds.org (it does not resolve at all), so the canonical now points at the
#: owned domain. Codings emitted before the change still carry the legacy
#: spelling, so readers MUST accept both — see
#: :data:`AUTOCODING_EXTENSION_URLS`.
AUTOCODING_EXTENSION_URL: str = (
    "https://fhir4ds.com/fhir/StructureDefinition/autocoding"
)

#: Legacy (pre-0.0.23) spelling of the autocoding extension URL. Emitted data
#: may carry it; never emit it, always accept it.
AUTOCODING_EXTENSION_URL_LEGACY: str = (
    "http://fhir4ds.org/fhir/StructureDefinition/autocoding"
)

#: Every accepted spelling. Use for membership tests; emit
#: :data:`AUTOCODING_EXTENSION_URL` only.
AUTOCODING_EXTENSION_URLS: tuple[str, ...] = (
    AUTOCODING_EXTENSION_URL,
    AUTOCODING_EXTENSION_URL_LEGACY,
)

# Fixed sub-extension URL strings. The six URL constants below are
# deliberately part of the public API of this module so test code and
# downstream parsers can reference them without hardcoding strings.
URL_ENGINE = "engine"
URL_ENGINE_VERSION = "engine-version"
URL_SEARCH_MODE = "search-mode"
URL_SCORE = "score"
URL_MATCH_GRADE = "match-grade"
URL_INDEX_VERSION = "index-version"
URL_QUERY_SOURCE = "query-source"
URL_QUERY_SYSTEM = "query-system"

#: Accepted ``query-source`` values (FHIR4-24 precedence legs).
VALID_QUERY_SOURCES = frozenset({"text", "display", "code"})


def build_autocoding_extension(
    *,
    engine: str,
    engine_version: str,
    search_mode: str,
    score: float,
    match_grade: str,
    index_version: Optional[str],
    query_source: Optional[str] = None,
    query_system: Optional[str] = None,
) -> dict:
    """Build the autocoding extension object.

    All six sub-extension fields are always present (INV-5).

    Args:
        engine: Engine name (constant ``"medterm4ds"`` in v1).
        engine_version: medterm4ds release version string.
        search_mode: Ranking strategy used (``lexical``/``hybrid``/
            ``semantic``).
        score: Relevance score from the underlying ranking engine.
            MUST be a finite float — ``NaN``, ``+inf``, and ``-inf``
            are rejected with :class:`ValueError` because
            ``json.dumps(allow_nan=False)`` would later refuse them
            during resource serialization (see
            :func:`fhir4ds.cql.loader.fhir_loader._serialize_resource`).
        match_grade: Match bucket from medterm4ds 0.0.9's authoritative
            vocabulary (``certain``/``exact``/``probable``/``possible``/
            ``broader``; ``ambiguous``/``no-match`` survive only as
            legacy cache-row aliases).
        index_version: Optional version tag of the terminology index.
            ``None`` is normalized to the literal string ``"unknown"``
            so the field always has a value (Phase 5 staleness sweeps
            rely on its presence).
        query_source: FHIR4-24 provenance — which precedence leg
            produced the query text (``text``/``display``/``code``).
            ``None`` (default) omits the sub-extension (v1 shape).
        query_system: FHIR4-24 provenance — the NON-standard system
            URI that justified the display/code legs. ``None`` (default)
            omits the sub-extension.

    Returns:
        The FHIR R4 extension dict (URL + sub-extensions in fixed
        field order — deterministic for byte-stable serialization).

    Raises:
        TypeError: If ``score`` cannot be coerced to a float.
        ValueError: If ``score`` is non-finite (NaN/inf/-inf), or
            ``query_source`` is not one of ``text``/``display``/``code``.
    """
    # Coerce score through float() so callers may pass a Decimal/int.
    # This is the boundary where JSON-unsafe values are caught — the
    # downstream serializer also has allow_nan=False but raising here
    # gives a clearer, earlier error pointing at the offending field.
    score_float = float(score)  # may raise TypeError
    if not math.isfinite(score_float):
        raise ValueError(
            f"autocoding extension score must be a finite float; "
            f"got {score!r} (NaN/Infinity are not JSON-serializable "
            f"with allow_nan=False)."
        )
    if query_source is not None and query_source not in VALID_QUERY_SOURCES:
        raise ValueError(
            f"autocoding extension query_source must be one of "
            f"{sorted(VALID_QUERY_SOURCES)} or None, got {query_source!r}."
        )

    # Normalize None index_version to literal "unknown" so the field is
    # always present downstream (Phase 5 staleness sweep depends on it).
    index_version_value = index_version if index_version is not None else "unknown"

    sub_extensions: list[dict] = [
        {"url": URL_ENGINE,         "valueString":  engine},
        {"url": URL_ENGINE_VERSION, "valueString":  engine_version},
        {"url": URL_SEARCH_MODE,    "valueCode":    search_mode},
        {"url": URL_SCORE,          "valueDecimal": score_float},
        {"url": URL_MATCH_GRADE,    "valueCode":    match_grade},
        {"url": URL_INDEX_VERSION,  "valueString":  index_version_value},
    ]
    if query_source is not None:
        sub_extensions.append({"url": URL_QUERY_SOURCE, "valueCode": query_source})
    if query_system is not None:
        sub_extensions.append({"url": URL_QUERY_SYSTEM, "valueString": query_system})

    return {
        "url": AUTOCODING_EXTENSION_URL,
        "extension": sub_extensions,
    }


def parse_autocoding_extension(coding: dict) -> Optional[dict]:
    """Inverse of :func:`build_autocoding_extension`.

    Walks the Coding's ``extension[]`` looking for the autocoding
    extension. If found, returns the sub-extension fields keyed by
    their URL suffix (``engine``, ``engine_version``, ``search_mode``,
    ``score``, ``match_grade``, ``index_version``, ``query_source``,
    ``query_system``). If absent, returns ``None``.

    Missing sub-extension fields are returned as ``None`` rather than
    raising — this is the right behavior for forward compatibility
    (Phase 5+ may add fields; downstream code should tolerate their
    absence).

    Args:
        coding: A FHIR R4 Coding dict (with ``system``, ``code``,
            ``extension``, etc.).

    Returns:
        Dict of the six fields, or ``None`` if the coding does not
        carry the autocoding extension.
    """
    if not isinstance(coding, dict):
        return None

    extensions = coding.get("extension")
    if not isinstance(extensions, list):
        return None

    autocoding_root: Optional[dict] = None
    for ext in extensions:
        if isinstance(ext, dict) and ext.get("url") in AUTOCODING_EXTENSION_URLS:
            autocoding_root = ext
            break

    if autocoding_root is None:
        return None

    sub_extensions = autocoding_root.get("extension")
    if not isinstance(sub_extensions, list):
        return None

    # Sub-extension value types and their corresponding parse keys.
    # valueString → engine, engine_version, index_version, query_system.
    # valueCode   → search_mode, match_grade, query_source.
    # valueDecimal → score.
    expected = {
        URL_ENGINE:         ("valueString",  "engine"),
        URL_ENGINE_VERSION: ("valueString",  "engine_version"),
        URL_SEARCH_MODE:    ("valueCode",    "search_mode"),
        URL_SCORE:          ("valueDecimal", "score"),
        URL_MATCH_GRADE:    ("valueCode",    "match_grade"),
        URL_INDEX_VERSION:  ("valueString",  "index_version"),
        URL_QUERY_SOURCE:   ("valueCode",    "query_source"),
        URL_QUERY_SYSTEM:   ("valueString",  "query_system"),
    }

    parsed: dict[str, object] = {key: None for _, (_, key) in expected.items()}
    for sub in sub_extensions:
        if not isinstance(sub, dict):
            continue
        url = sub.get("url")
        if url in expected:
            value_key, field_name = expected[url]
            parsed[field_name] = sub.get(value_key)
    return parsed


def is_autocoded(coding: dict) -> bool:
    """Return ``True`` iff ``coding`` carries the autocoding extension.

    Convenience predicate over :func:`parse_autocoding_extension`.
    """
    return parse_autocoding_extension(coding) is not None
