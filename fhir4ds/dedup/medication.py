"""Bounded same-corpus medication Reference resolver (AMUX-150 chunk A).

Resolves ``medication[x] = medicationReference`` on MedicationRequest /
MedicationDispense / MedicationAdministration to a Medication resource's
codings, strictly within the input corpus:

1. **Contained first**: ``#<id>`` fragments resolve against the SAME
   resource's ``contained`` list (the dominant real-world pattern).
2. **Corpus second**: ``Medication/<id>`` relative references (and
   absolute URLs whose anchored tail matches ``Medication/<id>``,
   ``_history``-stripped — the loader's anchored-tail doctrine) resolve
   against a :class:`MedicationIndex` built once from the input resource
   list.
3. **Unresolved**: no usable coding — the record can never union
   (singleton) and lands in the tier-3 curation queue with kind
   ``unresolved_medication_reference``.

No external terminology, no cross-dataset dereferencing, no recursion (a
Medication referencing a Medication is not valid FHIR and is not
followed). Deterministic by construction: the index is a pure function of
the input list, and duplicate Medication ids resolve to the
lexicographically smallest resource (mirroring union-find tie-breaking).
"""

from __future__ import annotations

import json
import re
from typing import Optional

__all__ = [
    "MedicationIndex",
    "LazyMedicationIndex",
    "resolve_medication_reference",
]

# Anchored tail doctrine (loader/_patient_ref): the Medication/<id> segment
# must be the FINAL path segment after _history stripping.
_MEDICATION_REF_RE = re.compile(r"(?:^|/)Medication/([A-Za-z0-9\-.]{1,64})$")
_HISTORY_RE = re.compile(r"/_history/[A-Za-z0-9\-.]+$")


class MedicationIndex:
    """id -> Medication resource, built once from the input resource list.

    Duplicate Medication ids resolve to the lexicographically smallest
    resource (deterministic tie-break on ``json.dumps(sort_keys=True)``).
    """

    def __init__(self, medications: dict[str, dict]) -> None:
        self._by_id = dict(medications)

    @classmethod
    def from_resources(cls, resources: list) -> "MedicationIndex":
        by_id: dict[str, dict] = {}
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            if resource.get("resourceType") != "Medication":
                continue
            mid = resource.get("id")
            if not isinstance(mid, str) or not mid:
                continue
            existing = by_id.get(mid)
            if existing is None or json.dumps(
                    resource, sort_keys=True) < json.dumps(
                    existing, sort_keys=True):
                by_id[mid] = resource
        return cls(by_id)

    def lookup(self, mid: str) -> Optional[dict]:
        return self._by_id.get(mid)

    def __len__(self) -> int:
        return len(self._by_id)


class LazyMedicationIndex:
    """Builds the same-corpus MedicationIndex on first ``resolve`` call.

    A corpus without medication references never pays the build (the
    resolver is only consulted for medication[x]-reference records).
    """

    def __init__(self, resources: list) -> None:
        self._resources = resources
        self._index: Optional[MedicationIndex] = None

    @property
    def built(self) -> bool:
        return self._index is not None

    def resolve(self, resource: dict) -> Optional[dict]:
        if self._index is None:
            self._index = MedicationIndex.from_resources(self._resources)
        return resolve_medication_reference(resource, self._index)


def resolve_medication_reference(resource: dict,
                                 index: MedicationIndex) -> Optional[dict]:
    """Resolve one resource's ``medicationReference`` (contained first,
    then corpus). Returns the referenced Medication resource or None.

    Never raises on malformed input: a missing/non-string reference
    string, an unknown contained id, or a dangling corpus reference all
    resolve to None (the caller's unresolved path).
    """
    reference_field = resource.get("medicationReference")
    if not isinstance(reference_field, dict):
        return None
    reference = reference_field.get("reference")
    if not isinstance(reference, str) or not reference:
        return None
    # 1. Contained #<id> fragments (dominant pattern) — same resource.
    if reference.startswith("#"):
        fragment = reference[1:]
        for contained in resource.get("contained") or []:
            if isinstance(contained, dict) \
                    and contained.get("resourceType") == "Medication" \
                    and contained.get("id") == fragment:
                return contained
        return None
    # 2. Corpus Medication/<id> (anchored tail, _history-stripped).
    cleaned = _HISTORY_RE.sub("", reference)
    match = _MEDICATION_REF_RE.search(cleaned)
    if match is None:
        return None
    return index.lookup(match.group(1))
