"""Tier-3 curation queue + embedding-proposer interface (AMUX-145).

The curation queue is the cascade's STOP: everything tier 2 could not
resolve lands in a deterministic JSONL report
(``<output_dir>/dedup_curation_queue.jsonl``) for human/terminology-team
review, sorted by ``(resource_type, patient_ref, lead rid)``.

The :class:`DedupCodeProposer` Protocol is a versioned, OPTIONAL,
default-off hook for the terminology stack: proposers may only ADD
entries to the queue as proposals — they can never affect merge
decisions. fhir4ds ships NO implementation and never imports
medterm4ds (dependency direction: the terminology stack registers one).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Protocol, Sequence, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - import isolation for typing only
    from .pipeline import DedupRecord

__all__ = [
    "CURATION_QUEUE_FILENAME",
    "DedupCodeProposer",
    "PROPOSER_INTERFACE_VERSION",
    "write_curation_queue",
]

CURATION_QUEUE_FILENAME = "dedup_curation_queue.jsonl"

#: Interface version for third-party DedupCodeProposer implementations.
#: Pinned by test; breaking changes bump this version.
PROPOSER_INTERFACE_VERSION = "1"


@runtime_checkable
class DedupCodeProposer(Protocol):
    """Versioned, optional, default-off. May only ADD curation-queue
    PROPOSALS; never affects merge decisions."""

    version: str

    def propose(self, records: Sequence["DedupRecord"]) -> Iterable[dict]:
        ...


def _entry_sort_key(entry: dict) -> tuple:
    lead = entry.get("rid") or sorted(entry.get("rids", []))[0]
    return (entry.get("resource_type", ""), entry.get("patient_ref") or "",
            lead)


def write_curation_queue(path: Path, entries: list[dict]) -> Path:
    """Write the deterministic JSONL curation queue.

    Non-proposal entries are sorted by
    ``(resource_type, patient_ref, lead rid)``; ``proposal`` entries are
    appended AFTER them (append-only doctrine), sorted among themselves.
    Every line is ``json.dumps(..., sort_keys=True)`` — no wall-clock, no
    RNG.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    main = sorted((e for e in entries if e.get("kind") != "proposal"),
                  key=_entry_sort_key)
    proposals = sorted((e for e in entries if e.get("kind") == "proposal"),
                       key=lambda e: json.dumps(e, sort_keys=True))
    with open(path, "w", encoding="utf-8") as handle:
        for entry in main + proposals:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return path
