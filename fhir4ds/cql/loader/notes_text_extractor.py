"""Walker that extracts ``(path, text, source_ref)`` tuples from FHIR notes.

Phase 4 of the medterm4ds integration. The notes-pipeline layer (see
:mod:`fhir4ds.cql.loader.notes_pipeline`) calls :func:`extract_note_texts`
to collect every text-bearing field configured for a given resource type,
then hands each text to ``medterm4ds.extract`` for concept extraction.

Reference: FDD §3 (SCOPE REDUCTION block at top of
``docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md``).

Dotted-path grammar supported (subset of FHIRPath sufficient for the
note-bearing fields enumerated in FDD §3):

    ``.``                — nested key descent (e.g. ``hospitalization.dischargeDisposition.text``)
    ``[N]``              — list index (e.g. ``finding[0].basis``)
    ``[]``               — wildcard: iterate every element of the list

The final resolved value is treated as text:

    * ``str``           — used directly.
    * Path ending in ``.data`` — base64-decoded (per FHIR ``base64Binary``);
      :class:`ValueError` on bad padding is swallowed (an empty list element
      is emitted instead, see ``_decode_base64``).
    * Non-string scalars (int, float, bool) — coerced via ``str()``.
    * ``None`` / missing — skipped silently.

Zero-dependency guarantee (Phase 1 INV-1, preserved): stdlib only
(``base64``, ``binascii``, ``dataclasses``, ``logging``, ``typing``).
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

__all__ = [
    "DEFAULT_NOTE_PATHS",
    "NoteText",
    "extract_note_texts",
]

_logger = logging.getLogger(__name__)


#: Default per-resource-type note paths (FDD §3, master plan §2).
#: Keys are FHIR R4 resource types; values are dotted-path expressions
#: supported by :func:`extract_note_texts`. Callers may override this
#: default by passing ``note_paths=`` to :class:`NotesPipelineConfig`.
DEFAULT_NOTE_PATHS: dict[str, list[str]] = {
    "DocumentReference":   ["content[].attachment.data"],
    "ClinicalImpression":  ["summary", "finding[].basis"],
    "Encounter":           ["reason[].valueString", "hospitalization.dischargeDisposition.text"],
    "Observation":         ["note[].text"],
    "AllergyIntolerance":  ["reaction[].description"],
    "MedicationRequest":   ["note[].text"],
    "DiagnosticReport":    ["presentedForm[].data"],
    "CarePlan":            ["note[].text"],
}


#: Splits a dotted path into segments. Handles ``[N]`` and ``[]`` indexing.
#: Examples:
#:   "hospitalization.dischargeDisposition.text" -> ["hospitalization", "dischargeDisposition", "text"]
#:   "content[].attachment.data"                 -> ["content[]", "attachment", "data"]
#:   "finding[0].basis"                          -> ["finding[0]", "basis"]
_SEGMENT_RE = re.compile(r"""
    (?:
        [^.[]+           # bare key (everything up to . or [)
        (?:\[\d*\])*     # zero-or-more index/wildcard brackets at this segment
    )
""", re.VERBOSE)


@dataclass(frozen=True)
class NoteText:
    """A single text fragment extracted from a FHIR resource.

    Attributes:
        path: Dotted path used to reach this text (e.g.
            ``"content[0].attachment.data"``). Includes resolved indices
            so downstream provenance is unambiguous.
        text: Decoded text content (str). Never None.
        source_ref: ``"{ResourceType}/{id}"`` of the source resource.
            Empty string when the source resource has no ``id`` field.
    """

    path: str
    text: str
    source_ref: str


def _split_path(path: str) -> list[str]:
    """Split a dotted path into segments, preserving bracket suffixes.

    Examples:
        ``"a.b.c"`` -> ``["a", "b", "c"]``
        ``"a[].b[0].c"`` -> ``["a[]", "b[0]", "c"]``
    """
    segments: list[str] = []
    pos = 0
    n = len(path)
    while pos < n:
        m = _SEGMENT_RE.match(path, pos)
        if not m or m.end() == pos:
            # Empty segment or stray character — advance defensively.
            pos += 1
            continue
        segments.append(m.group(0))
        pos = m.end()
        # Skip the '.' separator if present.
        if pos < n and path[pos] == ".":
            pos += 1
    return segments


def _decode_base64(value: str, path: str, source_ref: str) -> str:
    """base64-decode ``value`` (FHIR ``base64Binary``).

    Returns the decoded text. On decode failure (bad padding, non-base64
    alphabet), logs a WARNING and returns an empty string — the caller
    treats an empty string as a skip, so a single corrupt attachment
    does not abort extraction of other fields (INV-3 / FDD §7).
    """
    if not isinstance(value, str) or not value:
        return ""
    raw = value.strip()
    # FHIR permits whitespace inside base64Binary; strip before decoding.
    compact = "".join(raw.split())
    try:
        # validate=True rejects non-alphabet characters (e.g. "!!") rather
        # than silently dropping them, so genuinely malformed payloads are
        # logged and skipped instead of producing mojibake that downstream
        # NER would waste cycles on.
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        _logger.warning(
            "Failed to base64-decode %s on %s: %s — skipping field.",
            path, source_ref or "<unknown>", exc,
        )
        return ""
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        # Binary payload — decode with replacement so we don't crash the
        # load. The NER pipeline will simply find no concepts in mojibake.
        _logger.debug(
            "base64-decoded payload at %s on %s was not valid UTF-8; "
            "decoding with replacement.",
            path, source_ref,
        )
        return decoded.decode("utf-8", errors="replace")


def _walk(
    current: Any,
    segments: Sequence[str],
    path_so_far: str,
    decoded_base64: bool,
    source_ref: str,
    out: list[NoteText],
) -> None:
    """Recursive walker that emits :class:`NoteText` rows on terminal segments."""
    if not segments:
        # Terminal — emit if current is a usable scalar.
        if current is None:
            return
        if decoded_base64:
            text = _decode_base64(current, path_so_far, source_ref) if isinstance(current, str) else ""
            if text:
                out.append(NoteText(path=path_so_far, text=text, source_ref=source_ref))
            return
        if isinstance(current, str):
            if current:
                out.append(NoteText(path=path_so_far, text=current, source_ref=source_ref))
            return
        if isinstance(current, (int, float, bool)):
            out.append(NoteText(path=path_so_far, text=str(current), source_ref=source_ref))
            return
        # dict / list at terminal with no further segments — skip silently.
        return

    seg = segments[0]
    rest = segments[1:]

    # Parse index/wildcard suffixes at the end of this segment.
    # Examples: "finding[]" / "finding[0]" / "content[]" / "dischargeDisposition"
    m = re.match(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<brackets>(?:\[\d*\])*)$", seg)
    if not m:
        _logger.debug("Skipping unrecognized path segment %r in %s", seg, path_so_far)
        return
    key = m.group("key")
    brackets = m.group("brackets")

    if not isinstance(current, dict):
        return
    if key not in current:
        return
    child = current[key]

    # If no brackets, child descends directly.
    if not brackets:
        new_path = f"{path_so_far}.{key}" if path_so_far else key
        _walk(child, rest, new_path, decoded_base64, source_ref, out)
        return

    # One or more bracket suffixes. We only support one level per segment
    # in practice (the spec uses at most a single [] per step), but we
    # iterate the bracket groups in order to be robust.
    indices: list[str] = re.findall(r"\[(\d*)\]", brackets)
    cur = child
    new_path = f"{path_so_far}.{key}" if path_so_far else key
    for idx_str in indices:
        if not isinstance(cur, list):
            # Can't descend further through a non-list.
            return
        if idx_str == "":
            # Wildcard — fan out across all elements, then continue with
            # any remaining segments/brackets applied to each.
            for i, item in enumerate(cur):
                item_path = f"{new_path}[{i}]"
                _walk_bracket_chain(item, indices[1:], rest, item_path, decoded_base64, source_ref, out)
            return
        else:
            idx = int(idx_str)
            if idx < 0 or idx >= len(cur):
                return  # Out-of-bounds index — skip silently.
            cur = cur[idx]
            new_path = f"{new_path}[{idx}]"
    # All bracket indices consumed — continue with rest.
    _walk(cur, rest, new_path, decoded_base64, source_ref, out)


def _walk_bracket_chain(
    current: Any,
    remaining_indices: Sequence[str],
    remaining_segments: Sequence[str],
    path_so_far: str,
    decoded_base64: bool,
    source_ref: str,
    out: list[NoteText],
) -> None:
    """Apply any remaining bracket indices on the same segment, then walk rest.

    Called after a wildcard ``[]`` resolves to a single element; the
    element may still need further bracket indices (e.g. ``a[][0]``)
    before the next dotted segment is processed. In practice this is
    rare but supported for symmetry with the indexed branch.
    """
    if not remaining_indices:
        _walk(current, remaining_segments, path_so_far, decoded_base64, source_ref, out)
        return
    cur = current
    new_path = path_so_far
    for idx_str in remaining_indices:
        if not isinstance(cur, list):
            return
        if idx_str == "":
            for i, item in enumerate(cur):
                _walk_bracket_chain(item, [], remaining_segments, f"{new_path}[{i}]", decoded_base64, source_ref, out)
            return
        idx = int(idx_str)
        if idx < 0 or idx >= len(cur):
            return
        cur = cur[idx]
        new_path = f"{new_path}[{idx}]"
    _walk(cur, remaining_segments, new_path, decoded_base64, source_ref, out)


def extract_note_texts(
    resource: dict,
    note_paths: dict[str, list[str]] | None = None,
) -> list[NoteText]:
    """Extract ``(path, text, source_ref)`` triples from a FHIR resource.

    Args:
        resource: A FHIR R4 resource dict. Must have a ``resourceType``.
        note_paths: Optional per-resource-type path map. When ``None``,
            :data:`DEFAULT_NOTE_PATHS` is used. Keys absent from the map
            produce an empty list (not an error).

    Returns:
        List of :class:`NoteText` triples, in deterministic order
        (paths iterated in declared order, wildcards in source order).

    Raises:
        TypeError: If ``resource`` is not a dict.
    """
    if not isinstance(resource, dict):
        raise TypeError(f"Expected dict, got {type(resource).__name__}")
    resource_type = resource.get("resourceType")
    if not isinstance(resource_type, str) or not resource_type:
        return []
    resource_id = resource.get("id")
    source_ref = f"{resource_type}/{resource_id}" if resource_id else ""

    paths_map = note_paths if note_paths is not None else DEFAULT_NOTE_PATHS
    configured = paths_map.get(resource_type)
    if not configured:
        return []

    out: list[NoteText] = []
    for dotted in configured:
        if not isinstance(dotted, str) or not dotted:
            continue
        segments = _split_path(dotted)
        if not segments:
            continue
        # FDD: paths ending in ``.data`` are base64-encoded payloads.
        decoded_base64 = segments[-1] == "data"
        _walk(resource, segments, "", decoded_base64, source_ref, out)
    return out
