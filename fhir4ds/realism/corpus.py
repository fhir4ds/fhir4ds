"""FHIR corpus loading for the realism harness (AMUX-150 follow-on).

Corpus-agnostic loader with first-class support for the MIMIC-IV-FHIR
demo layout (``fhir/`` directory of NDJSON files, one resource type per
file, e.g. ``Patient.ndjson``, ``Observation.ndjson``) and FHIR Bundle
JSON files (a directory of Bundle documents, or a single ``.json`` /
``.jsonl`` file). Everything is returned as a plain ``list[dict]`` of
FHIR resources — the shape the matching index, the dedup pipeline, and
the PIQI views consume.

Determinism: loaders sort output by ``(resourceType, id)`` and never
depend on filesystem ordering.

Tolerance policy (the demo corpus's quirks):

- Bundle ``entry`` items without a ``resource`` are skipped (link /
  request / response entries).
- Nested Bundles inside entries are flattened one level (the MIMIC demo
  ships inner collection bundles in some files).
- Blank NDJSON lines are skipped.
- ``.gz``-compressed NDJSON/JSON files (the MIMIC demo ships
  ``MimicPatient.ndjson.gz``) are transparently decompressed.
- Non-JSON / non-FHIR files in a directory are skipped when at least one
  parseable FHIR payload exists; a directory with NO parseable FHIR
  content raises ``ValueError`` (a typo'd path must fail loudly, not
  silently produce an empty corpus).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Iterator, Optional, Union

__all__ = [
    "load_corpus",
    "load_ndjson_dir",
    "load_bundle_file",
    "bundle_entries",
    "iter_ndjson_resources",
    "is_fhir_resource",
]

#: File suffixes treated as NDJSON regardless of case (MIMIC ships
#: ``Patient.ndjson``; some mirrors use ``.json`` lines — a ``.json``
#: file is tried as a single JSON document first, then as JSONL).
_NDJSON_SUFFIXES = {".ndjson", ".jsonl"}
_JSON_SUFFIXES = {".json"}


def is_fhir_resource(obj: object) -> bool:
    """A minimal FHIR-resource shape check: dict with a string resourceType."""
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("resourceType"), str)
        and bool(obj["resourceType"])
    )


def iter_ndjson_resources(text: str) -> Iterator[dict]:
    """Yield resources from NDJSON text; blank lines skipped."""
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = _loads(line, f"NDJSON line {lineno}")
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"malformed JSON on NDJSON line {lineno}: {exc}") from exc
        if not is_fhir_resource(obj):
            raise ValueError(
                f"NDJSON line {lineno} is not a FHIR resource "
                f"(no string 'resourceType'): "
                f"{str(line)[:120]!r}")
        yield obj


def _read_text(path: Path) -> str:
    """Read a text payload, transparently gunzipping ``.gz`` files.

    Raises ``ValueError`` naming the file for corrupt gzip payloads and
    undecodable bytes — a raw ``BadGzipFile``/``UnicodeDecodeError``
    without attribution gives the caller no way to tell which file in a
    corpus directory is broken.
    """
    try:
        if path.suffix.lower() == ".gz":
            data = gzip.decompress(path.read_bytes())
        else:
            data = path.read_bytes()
        return data.decode("utf-8-sig")
    except (ValueError, OSError, EOFError) as exc:
        # BadGzipFile subclasses OSError; UnicodeDecodeError subclasses
        # ValueError; a TRUNCATED gzip payload raises EOFError (QA-D6E-002)
        # which subclasses neither. All are re-raised with file
        # attribution.
        raise ValueError(f"{path.name}: cannot read corpus file ({exc})") from exc


def _loads(text: str, name: str):
    """``json.loads`` with the QA-D6E-001 guard: pathologically deep
    nesting raises the parser's raw ``RecursionError`` — re-raise it as
    an attributed ``ValueError`` like every other malformed-file signal."""
    try:
        return json.loads(text)
    except RecursionError as exc:
        raise ValueError(
            f"{name}: JSON nesting too deep to parse") from exc


def _is_data_file(name: str) -> bool:
    lowered = name.lower()
    for suffix in _NDJSON_SUFFIXES | _JSON_SUFFIXES:
        if lowered.endswith(suffix) or lowered.endswith(suffix + ".gz"):
            return True
    return False


def _stripped_suffix(path: Path) -> str:
    """Suffix with any .gz removed: ``X.ndjson.gz`` -> ``.ndjson``."""
    name = path.name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    return "." + name.rsplit(".", 1)[-1] if "." in name else ""


def bundle_entries(bundle: dict) -> Iterator[dict]:
    """Yield resources from a Bundle dict, flattening nested bundles.

    Entries without a ``resource`` are skipped (quirk tolerance). The
    walk is ITERATIVE (explicit entry-iterator stack, document-order
    DFS): the recursive form raised a raw ``RecursionError`` on deeply
    nested bundle chains (QA-D6E-001).
    """
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise ValueError(
            "expected a FHIR Bundle (resourceType == 'Bundle'), got "
            + repr(bundle.get("resourceType") if isinstance(bundle, dict)
                   else type(bundle).__name__))
    stack: list[Iterator[dict]] = [iter(bundle.get("entry") or [])]
    while stack:
        try:
            entry = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource")
        if not is_fhir_resource(resource):
            continue
        if resource["resourceType"] == "Bundle":
            stack.append(iter(resource.get("entry") or []))
        else:
            yield resource


def _extend_flattening(resources: list[dict], objs: Iterator[dict]) -> None:
    """Append resources, flattening Bundle objects into their entries.

    Single-document Bundles are flattened by ``load_bundle_file`` /
    ``load_ndjson_dir``; a Bundle arriving on a JSONL/NDJSON *stream*
    must be flattened the same way, otherwise its entries are invisible
    to every downstream consumer (matching / dedup / PIQI views key on
    the clinical resourceType, never ``Bundle``).
    """
    for obj in objs:
        if obj.get("resourceType") == "Bundle":
            resources.extend(bundle_entries(obj))
        else:
            resources.append(obj)


def load_bundle_file(path: Union[str, Path]) -> list[dict]:
    """Load one Bundle JSON file (``.json``) or JSONL bundle stream."""
    path = Path(path)
    text = _read_text(path)
    if _stripped_suffix(path) in _NDJSON_SUFFIXES:
        resources: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = _loads(line, str(path))
            if not is_fhir_resource(obj):
                raise ValueError(
                    f"{path}: JSONL line is not a FHIR resource")
            _extend_flattening(resources, [obj])
        return _sorted(resources)
    try:
        obj = _loads(text, str(path))
    except json.JSONDecodeError:
        # A .json file may hold a JSONL stream of resources/Bundles
        # (the same fallback the directory loader documents); the raw
        # "Extra data" error leaks the JSON parser's internals.
        resources = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                line_obj = _loads(line, str(path))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}: neither a single JSON document nor a "
                    f"JSONL resource stream ({exc})") from exc
            if not is_fhir_resource(line_obj):
                raise ValueError(
                    f"{path}: JSONL line is not a FHIR resource")
            _extend_flattening(resources, [line_obj])
        if not resources:
            raise ValueError(f"{path}: file is not a FHIR resource/Bundle")
        return _sorted(resources)
    if not is_fhir_resource(obj):
        raise ValueError(f"{path}: file is not a FHIR resource/Bundle")
    if obj["resourceType"] == "Bundle":
        return _sorted(bundle_entries(obj))
    return _sorted([obj])


def load_ndjson_dir(path: Union[str, Path]) -> list[dict]:
    """Load a MIMIC-layout directory: one resource type per NDJSON file."""
    path = Path(path)
    resources: list[dict] = []
    files = sorted(
        p for p in path.iterdir()
        if p.is_file() and _is_data_file(p.name)
    )
    failures: list[str] = []
    for file in files:
        text = _read_text(file)
        if _stripped_suffix(file) in _JSON_SUFFIXES:
            # Try single-document JSON first (Bundle or resource), then
            # fall back to JSONL lines (some mirrors stream bundles).
            try:
                obj = _loads(text, file.name)
            except json.JSONDecodeError:
                obj = None
            if obj is not None and is_fhir_resource(obj):
                if obj["resourceType"] == "Bundle":
                    resources.extend(bundle_entries(obj))
                else:
                    resources.append(obj)
                continue
            if obj is not None and isinstance(obj, list):
                # A bare JSON array of resources (entry.resource export).
                for item in obj:
                    if is_fhir_resource(item):
                        _extend_flattening(resources, [item])
                    elif isinstance(item, dict) and is_fhir_resource(
                            item.get("resource")):
                        _extend_flattening(resources, [item["resource"]])
                continue
        try:
            _extend_flattening(resources, iter_ndjson_resources(text))
        except ValueError as exc:
            failures.append(f"{file.name}: {exc}")
    if not resources:
        detail = ("; ".join(failures[:3]) + "…") if failures else "no data files"
        raise ValueError(
            f"no FHIR resources parsed from {path} ({detail})")
    return _sorted(resources)


def _sorted(resources: list[dict]) -> list[dict]:
    # Keys are str()-coerced: is_fhir_resource only pins ``resourceType``
    # to a string; ``id`` may be any JSON value (invalid FHIR but valid
    # JSON) and a mixed-type key would crash the sort with a raw
    # TypeError. Tolerance-first: load it, order deterministically.
    return sorted(resources, key=lambda r: (str(r.get("resourceType", "")),
                                            str(r.get("id", ""))))


def load_corpus(path: Union[str, Path]) -> list[dict]:
    """Load a corpus from a directory (NDJSON layout or Bundle dir) or a
    single file (NDJSON / Bundle JSON). See module docstring."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"corpus path does not exist: {path}")
    if path.is_dir():
        return load_ndjson_dir(path)
    if path.is_file():
        return load_bundle_file(path)
    raise ValueError(f"corpus path is neither file nor directory: {path}")
