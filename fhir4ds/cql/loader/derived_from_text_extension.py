"""Builder/parser for the ``derived-from-text`` FHIR R4 extension.

Every Condition built by :class:`fhir4ds.cql.loader.notes_pipeline.NotesPipeline`
carries this structured extension on its top-level ``extension[]`` so
downstream consumers (Phase 5 staleness sweep, audit log, debugging UIs)
can recover the source resource, the dotted path, the exact text span,
and the matched substring that produced the Condition.

Reference: FDD ``docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md``
§3 (SCOPE REDUCTION block) — "Extension URL: ``http://fhir4ds.org/fhir/StructureDefinition/derived-from-text``".

Extension shape (five sub-extensions, all always present):

    {
        "url": "http://fhir4ds.org/fhir/StructureDefinition/derived-from-text",
        "extension": [
            {"url": "source-ref",   "valueString":   "Observation/abc"},
            {"url": "source-path",  "valueString":   "note[0].text"},
            {"url": "span-start",   "valueInteger":  42},
            {"url": "span-end",     "valueInteger":  57},
            {"url": "matched-text", "valueString":   "chest pain"}
        ]
    }

Zero-dependency guarantee (Phase 1 INV-1, preserved): stdlib only
(``typing``).
"""

from __future__ import annotations

from typing import Optional

#: Canonical URL for the derived-from-text extension. Stable across releases.
DERIVED_FROM_TEXT_EXTENSION_URL: str = (
    "http://fhir4ds.org/fhir/StructureDefinition/derived-from-text"
)

# Fixed sub-extension URL strings. Exposed as module constants so test
# code and downstream parsers can reference them without hardcoding.
URL_SOURCE_REF = "source-ref"
URL_SOURCE_PATH = "source-path"
URL_SPAN_START = "span-start"
URL_SPAN_END = "span-end"
URL_MATCHED_TEXT = "matched-text"


def build_derived_from_text_extension(
    *,
    source_ref: str,
    source_path: str,
    span_start: int,
    span_end: int,
    matched_text: str,
) -> dict:
    """Build the ``derived-from-text`` extension object.

    All five sub-extension fields are always present.

    Args:
        source_ref: ``"{ResourceType}/{id}"`` of the source resource
            (e.g. ``"Observation/abc-123"``).
        source_path: Dotted path within the source resource where the
            text was found (e.g. ``"note[0].text"``).
        span_start: Character offset (inclusive) of the match within
            the extracted note text. Coerced through ``int()`` so
            callers may pass numpy ints or Decimals without issue.
        span_end: Character offset (exclusive) of the match.
        matched_text: The actual substring that the NER pipeline
            matched to a code.

    Returns:
        The FHIR R4 extension dict (URL + five sub-extensions in
        fixed field order — deterministic for byte-stable serialization).

    Raises:
        TypeError: If ``span_start`` / ``span_end`` cannot be coerced
            to ``int``.
        ValueError: If ``span_start`` or ``span_end`` is negative.
    """
    start_int = int(span_start)  # may raise TypeError
    end_int = int(span_end)
    if start_int < 0 or end_int < 0:
        raise ValueError(
            f"derived-from-text span offsets must be non-negative; "
            f"got start={start_int!r}, end={end_int!r}."
        )

    return {
        "url": DERIVED_FROM_TEXT_EXTENSION_URL,
        "extension": [
            {"url": URL_SOURCE_REF,   "valueString":  str(source_ref)},
            {"url": URL_SOURCE_PATH,  "valueString":  str(source_path)},
            {"url": URL_SPAN_START,   "valueInteger": start_int},
            {"url": URL_SPAN_END,     "valueInteger": end_int},
            {"url": URL_MATCHED_TEXT, "valueString":  str(matched_text)},
        ],
    }


def parse_derived_from_text_extension(resource: dict) -> Optional[dict]:
    """Inverse of :func:`build_derived_from_text_extension`.

    Walks the Condition's top-level ``extension[]`` looking for the
    derived-from-text extension. If found, returns the five
    sub-extension fields keyed by their URL suffix (``source_ref``,
    ``source_path``, ``span_start``, ``span_end``, ``matched_text``).
    If absent, returns ``None``.

    Missing sub-extension fields are returned as ``None`` rather than
    raising — forward-compatible with future field additions.

    Args:
        resource: A FHIR R4 resource dict (with ``extension[]`` etc.).

    Returns:
        Dict of the five fields, or ``None`` if the resource does not
        carry the derived-from-text extension.
    """
    if not isinstance(resource, dict):
        return None

    extensions = resource.get("extension")
    if not isinstance(extensions, list):
        return None

    root: Optional[dict] = None
    for ext in extensions:
        if isinstance(ext, dict) and ext.get("url") == DERIVED_FROM_TEXT_EXTENSION_URL:
            root = ext
            break

    if root is None:
        return None

    sub_extensions = root.get("extension")
    if not isinstance(sub_extensions, list):
        return None

    expected = {
        URL_SOURCE_REF:   ("valueString",  "source_ref"),
        URL_SOURCE_PATH:  ("valueString",  "source_path"),
        URL_SPAN_START:   ("valueInteger", "span_start"),
        URL_SPAN_END:     ("valueInteger", "span_end"),
        URL_MATCHED_TEXT: ("valueString",  "matched_text"),
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


def is_derived_from_text(resource: dict) -> bool:
    """Return ``True`` iff ``resource`` carries the derived-from-text extension."""
    return parse_derived_from_text_extension(resource) is not None
