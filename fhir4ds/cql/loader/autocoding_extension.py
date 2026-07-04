"""Builder/parser for the ``autocoding`` FHIR R4 extension.

Every Coding written by :class:`fhir4ds.cql.loader.auto_coder.AutoCoder`
carries this structured extension. The URL is canonical and stable
across releases; downstream consumers (Phase 5 staleness sweep) detect
auto-coded Codings by this URL.

Reference: FDD §3d, copied verbatim from master plan §2.

Extension shape (six sub-extensions, all always present — INV-5):

    {
        "url": "http://fhir4ds.org/fhir/StructureDefinition/autocoding",
        "extension": [
            {"url": "engine",          "valueString":  "medterm4ds"},
            {"url": "engine-version",  "valueString":  "<engine_version>"},
            {"url": "search-mode",     "valueCode":    "hybrid"},
            {"url": "score",           "valueDecimal": 0.87},
            {"url": "match-grade",     "valueCode":    "certain"},
            {"url": "index-version",   "valueString":  "2026AA-bm25-v3"}
        ]
    }

Zero-dependency guarantee: stdlib only (``math``, ``typing``).
"""

from __future__ import annotations

import math
from typing import Optional

#: Canonical URL for the autocoding extension. Stable across releases.
#: Downstream consumers detect auto-coded Codings by this URL.
AUTOCODING_EXTENSION_URL: str = (
    "http://fhir4ds.org/fhir/StructureDefinition/autocoding"
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


def build_autocoding_extension(
    *,
    engine: str,
    engine_version: str,
    search_mode: str,
    score: float,
    match_grade: str,
    index_version: Optional[str],
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
        match_grade: Match bucket (``certain``/``probable``/
            ``ambiguous``/``no-match``).
        index_version: Optional version tag of the terminology index.
            ``None`` is normalized to the literal string ``"unknown"``
            so the field always has a value (Phase 5 staleness sweeps
            rely on its presence).

    Returns:
        The FHIR R4 extension dict (URL + six sub-extensions in
        fixed field order — deterministic for byte-stable serialization).

    Raises:
        TypeError: If ``score`` cannot be coerced to a float.
        ValueError: If ``score`` is non-finite (NaN/inf/-inf).
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

    # Normalize None index_version to literal "unknown" so the field is
    # always present downstream (Phase 5 staleness sweep depends on it).
    index_version_value = index_version if index_version is not None else "unknown"

    return {
        "url": AUTOCODING_EXTENSION_URL,
        "extension": [
            {"url": URL_ENGINE,         "valueString":  engine},
            {"url": URL_ENGINE_VERSION, "valueString":  engine_version},
            {"url": URL_SEARCH_MODE,    "valueCode":    search_mode},
            {"url": URL_SCORE,          "valueDecimal": score_float},
            {"url": URL_MATCH_GRADE,    "valueCode":    match_grade},
            {"url": URL_INDEX_VERSION,  "valueString":  index_version_value},
        ],
    }


def parse_autocoding_extension(coding: dict) -> Optional[dict]:
    """Inverse of :func:`build_autocoding_extension`.

    Walks the Coding's ``extension[]`` looking for the autocoding
    extension. If found, returns the six sub-extension fields keyed by
    their URL suffix (``engine``, ``engine_version``, ``search_mode``,
    ``score``, ``match_grade``, ``index_version``). If absent, returns
    ``None``.

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
        if isinstance(ext, dict) and ext.get("url") == AUTOCODING_EXTENSION_URL:
            autocoding_root = ext
            break

    if autocoding_root is None:
        return None

    sub_extensions = autocoding_root.get("extension")
    if not isinstance(sub_extensions, list):
        return None

    # Sub-extension value types and their corresponding parse keys.
    # valueString → engine, engine_version, index_version.
    # valueCode   → search_mode, match_grade.
    # valueDecimal → score.
    expected = {
        URL_ENGINE:         ("valueString",  "engine"),
        URL_ENGINE_VERSION: ("valueString",  "engine_version"),
        URL_SEARCH_MODE:    ("valueCode",    "search_mode"),
        URL_SCORE:          ("valueDecimal", "score"),
        URL_MATCH_GRADE:    ("valueCode",    "match_grade"),
        URL_INDEX_VERSION:  ("valueString",  "index_version"),
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
