"""Content digests for measure results (FHIR4-110).

A long run that only reports pass/fail against an expectation cannot tell a wrong value from
a right one when nothing compares the output itself. A digest of the OUTPUT lets two runs of
the same tree be compared in seconds, and lets a swallowed fault or an ordering
nondeterminism show up as movement instead of as data.

Every measure gets two digests over the same cells:

- ``digest_exact`` keeps the order in which the run produced rows, columns and list elements.
- ``digest_normalised`` sorts rows by patient, columns by name and list elements by value, the
  way the corpus probes normalise CTE order.

So a run pair that differs only in ``digest_exact`` moved on ORDER (a list came back in
another order); a pair that differs in ``digest_normalised`` moved on CONTENT (a value, a
count, a membership). Content movement is the one a fault or a wrong-answer bug produces.

Nothing here retries, re-runs or repairs a measurement: it reports movement, that is all.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

SCHEMA_VERSION = 1

#: Hex characters kept per digest. 32 hex = 128 bits: collisions are not a practical concern
#: at ~10^7 cells, and the per-measure lines stay short enough to read in a gate log.
_DIGEST_HEX = 32

#: Movement classes, from "nothing to see" to "a value changed".
CLASSES = ("same", "order", "content", "missing")

_UNIT = "\x1f"  # field separator inside one hashed record
_RECORD = "\x1e"  # record separator


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_HEX]


def _is_missing(value: Any) -> bool:
    """SQL NULL as pandas carries it: None, NaN, NaT, pandas NA."""
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    # pandas.NaT / pandas.NA: no pandas import here, and `value != value` raises for NA.
    return type(value).__name__ in {"NaTType", "NAType"}


def _numpy_value(value: Any) -> Any:
    """Unwrap numpy: a scalar or 0-d array becomes its Python value, an array a list
    (``numpy.bool_`` is not a ``bool``, and a one-element array is still a list)."""
    ndim = getattr(value, "ndim", None)
    if isinstance(ndim, int) and not isinstance(value, (str, bytes, bytearray)):
        if ndim == 0:
            try:
                return value.item()
            except (TypeError, ValueError):
                return value
        if callable(getattr(value, "tolist", None)):
            return value.tolist()
    return value


def canonical(value: Any) -> Any:
    """A JSON-shaped, type-faithful copy of a result cell.

    A value that JSON cannot carry keeps its type in a one-key object (``{"__decimal__":
    "1.50"}``), so a Decimal never collapses into a float and a date into a string: a change
    of type between two runs is movement too.
    """
    value = _numpy_value(value)
    if _is_missing(value):
        return None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if value != value:
            return None
        if value in (float("inf"), float("-inf")):
            return {"__float__": "inf" if value > 0 else "-inf"}
        return value
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, time):
        return {"__time__": value.isoformat()}
    if isinstance(value, UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes__": bytes(value).hex()}
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted(canonical(item) for item in value)}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): canonical(value[key]) for key in sorted(value, key=str)}
    # Unknown type: its name and its repr without memory addresses, which change per run.
    text = repr(value)
    while "0x" in text:
        start = text.index("0x")
        end = start + 2
        while end < len(text) and text[end] in "0123456789abcdefABCDEF":
            end += 1
        text = text[:start] + text[end:]
    return {"__type__": f"{type(value).__module__}.{type(value).__qualname__}", "__repr__": text}


def _sorted_lists(value: Any) -> Any:
    if isinstance(value, list):
        return sorted((_sorted_lists(item) for item in value), key=_json)
    if isinstance(value, dict):
        return {key: _sorted_lists(value[key]) for key in value}
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(", ", ": "), ensure_ascii=False)


def _text(value: Any) -> str:
    """A cell as one line of text. Booleans and nulls use the spelling DuckDB's ``::VARCHAR``
    gives them (``true``, ``false``, ``None``), which is what the Tier C cell comparator
    expects; everything else is JSON, so ``"1"``, ``1`` and ``1.0`` stay three different cells."""
    if value is None:
        return "None"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return _json(value)


def cell_texts(value: Any) -> tuple[str, str]:
    """The cell as text, exact and order-normalised (``(exact, normalised)``).

    Booleans and nulls use the spelling DuckDB's ``::VARCHAR`` gives them (``true``,
    ``false``, ``None``), which is what the Tier C cell comparator expects; other values
    are JSON, so a string never passes for the number it spells.
    """
    exact = canonical(value)
    return _text(exact), _text(_sorted_lists(exact))


def measure_content(results: list[dict]) -> dict[str, Any]:
    """Digests of one measure's per-patient results.

    ``results`` is what the conformance runner hands the result writer: one dict per patient
    with a ``patient_id`` key. Returns patient and cell counts, the two measure digests and
    the same pair per column, so a moved measure names the define that moved without a second
    pass over the rows.
    """
    columns = list(dict.fromkeys(key for row in results for key in row))

    # Exact: every cell in the order the run produced it (rows, then columns, then lists).
    exact = hashlib.sha256()
    column_exact = {name: hashlib.sha256() for name in columns}
    rows_by_patient: dict[str, list[dict]] = {}
    for row in results:
        patient = cell_texts(row.get("patient_id"))[0]
        rows_by_patient.setdefault(patient, []).append(row)
        row_digest = hashlib.sha256()
        for name in columns:
            cell = _hash(cell_texts(row.get(name))[0]) + _UNIT
            row_digest.update(cell.encode("utf-8"))
            column_exact[name].update((cell + _RECORD).encode("utf-8"))
        exact.update((row_digest.hexdigest() + _RECORD).encode("utf-8"))

    # Normalised: (patient, occurrence, column) -> digest of the order-normalised cell. A
    # patient present in two rows keeps both rows; the occurrence is the row's rank among
    # that patient's rows, so it does not depend on the order the run produced them in.
    normal_cells: dict[tuple[str, int, str], str] = {}
    for patient, rows in rows_by_patient.items():
        ranked = sorted(
            rows, key=lambda row: [cell_texts(row.get(name))[1] for name in sorted(columns)]
        )
        for occurrence, row in enumerate(ranked):
            for name in columns:
                normal_cells[(patient, occurrence, name)] = _hash(cell_texts(row.get(name))[1])

    def column_normalised(name: str) -> str:
        digest = hashlib.sha256()
        for key in sorted(k for k in normal_cells if k[2] == name):
            digest.update((normal_cells[key] + _RECORD).encode("utf-8"))
        return digest.hexdigest()[:_DIGEST_HEX]

    normal = hashlib.sha256()
    for name in sorted(columns):
        normal.update((column_normalised(name) + _RECORD).encode("utf-8"))

    return {
        "patients": len(results),
        "cells": len(results) * len(columns),
        "columns": sorted(columns),
        "digest_exact": exact.hexdigest()[:_DIGEST_HEX],
        "digest_normalised": normal.hexdigest()[:_DIGEST_HEX],
        "by_column": {
            name: {
                "cells": len(results),
                "digest_exact": column_exact[name].hexdigest()[:_DIGEST_HEX],
                "digest_normalised": column_normalised(name),
            }
            for name in sorted(columns)
        },
    }


def suite_content(measures: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Digest of a whole run over ``{measure_id: measure_content(...)}``."""
    exact = hashlib.sha256()
    normal = hashlib.sha256()
    for measure_id in sorted(measures):
        exact.update((measure_id + _UNIT + measures[measure_id]["digest_exact"] + _RECORD).encode())
        normal.update(
            (measure_id + _UNIT + measures[measure_id]["digest_normalised"] + _RECORD).encode()
        )
    return {
        "measures": len(measures),
        "patients": sum(m["patients"] for m in measures.values()),
        "cells": sum(m["cells"] for m in measures.values()),
        "digest_exact": exact.hexdigest()[:_DIGEST_HEX],
        "digest_normalised": normal.hexdigest()[:_DIGEST_HEX],
    }


def classify(first: dict[str, Any] | None, second: dict[str, Any] | None) -> str:
    """How two digests of the same thing (measure or column) relate."""
    if first is None or second is None:
        return "missing"
    if first["digest_exact"] == second["digest_exact"]:
        return "same"
    if first["digest_normalised"] == second["digest_normalised"]:
        return "order"
    return "content"


def compare_records(
    first: dict[str, dict[str, Any]], second: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Compare two ``{measure_id: measure_content}`` records, measure by measure.

    The result names every measure that is not ``same`` and, for each, the columns that
    moved; ``moved`` counts them so a caller can fail on any movement.
    """
    measures: dict[str, dict[str, Any]] = {}
    for measure_id in sorted(set(first) | set(second)):
        before, after = first.get(measure_id), second.get(measure_id)
        kind = classify(before, after)
        entry: dict[str, Any] = {"class": kind}
        if kind != "same" and before is not None and after is not None:
            columns = sorted(set(before["by_column"]) | set(after["by_column"]))
            entry["moved_columns"] = [
                name
                for name in columns
                if classify(before["by_column"].get(name), after["by_column"].get(name)) != "same"
            ]
        measures[measure_id] = entry
    counts = Counter(entry["class"] for entry in measures.values())
    return {
        "compared": len(measures),
        "moved": len(measures) - counts["same"],
        "counts": {kind: counts.get(kind, 0) for kind in CLASSES},
        "measures": measures,
    }


def text_rows(results: list[dict]) -> dict[str, Any]:
    """The results as the text rows the Tier C cell comparator takes (exact order).

    The patient id comes first and unquoted: the comparator keys its rows by the first
    column and prints it in every example.
    """
    columns = list(dict.fromkeys(key for row in results for key in row))
    columns = ["patient_id"] + [name for name in columns if name != "patient_id"]

    def cell(row: dict, name: str) -> str:
        value = row.get(name)
        if name == "patient_id" and isinstance(value, str):
            return value
        return cell_texts(value)[0]

    return {"columns": columns, "rows": [[cell(row, name) for name in columns] for row in results]}


def write_digest_file(path: Path, measures: dict[str, dict[str, Any]], suite: str | None = None) -> None:
    """Write ``content_digests.json``: the suite digest and one record per measure."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "suite": suite,
        "digest": suite_content(measures),
        "measures": measures,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_record(path: Path) -> dict[str, Any]:
    """The digest record of one run: ``{"suite", "digest", "measures"}``.

    ``path`` is a ``content_digests.json``, or a gate report such as ``dqm_report.json``
    (which carries the same digests per measure). Raises ``ValueError`` naming the file
    when it holds no digests.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path} is not a digest record: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a digest record: not a JSON object")

    if "schema_version" in payload:
        if payload["schema_version"] != SCHEMA_VERSION:
            raise ValueError(
                f"{path} has digest schema {payload['schema_version']}; "
                f"this tree reads {SCHEMA_VERSION}"
            )
        return {
            "suite": payload.get("suite"),
            "digest": payload.get("digest"),
            "measures": payload.get("measures"),
        }

    summary = payload.get("_summary") or {}
    measures = {
        measure_id: measure["content"]
        for measure_id, measure in payload.items()
        if isinstance(measure, dict) and "digest_normalised" in (measure.get("content") or {})
    }
    if not measures:
        raise ValueError(f"{path} carries no content digests (written before FHIR4-110?)")
    return {
        "suite": summary.get("suite"),
        "digest": summary.get("content_digest"),
        "measures": measures,
    }
