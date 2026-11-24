"""The known-gap ledger (plan section 4.5): register or fix -- never ignore.

``known_gaps.json`` is tracked and reviewed in PRs. An entry carries ``id``,
``kind``, ``target`` (a function name, a file, or a list of case ids), ``reason``,
``owner``, ``since``, ``expires`` (ISO dates) and, for case kinds, the ``suite``.
The policy the gates enforce:

1. **Register or fix.** An unregistered gap fails the gate; the failure prints a
   ready-to-paste entry.
2. **Registration expires.** 90 days by default; 30 days for principle kinds
   (``WASM_ONLY_MACRO``, ``TS_BODY_DRIFT``) and for in-flight desktop defects.
   An expired entry that still covers a gap fails the gate.
3. **Stale registrations fail.** An entry whose gap no longer reproduces must be
   removed.
4. **The principle cannot be silenced.** ``WASM_ONLY_MACRO`` additionally needs
   ``approved_by`` (Joel 2026-11-24: no macros in WASM that do not exist on
   desktop).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

SCHEMA_VERSION = 1
LEDGER_PATH = Path(__file__).with_name("known_gaps.json")

DEFAULT_EXPIRY_DAYS = 90
SHORT_EXPIRY_DAYS = 30
SUITES = ("cql", "fhirpath", "viewdef", "omop")

# Name-level kinds: the target is one or more function/macro names.
NAME_KINDS = (
    "MISSING_IN_BROWSER",  # desktop macro/UDF with no browser counterpart
    "WASM_ONLY_MACRO",  # browser macro with no desktop macro (the principle)
    "TS_BODY_DRIFT",  # same-name macro, different body
    "SIGNATURE_DIFF",  # same-name function, different overload signatures
    "MACRO_VS_NATIVE",  # desktop macro, browser runs a same-name native function
)
# Case-level kinds: the target is a list of case ids and ``suite`` is required.
CASE_KINDS = (
    "PARITY_GAP",  # desktop matches the official expectation, browser does not
    "BROWSER_ONLY_PASS",  # browser matches, desktop does not
    "ENGINE_DIFF",  # both match, but raw value or declared type differs
    "DESKTOP_DEFECT",  # neither surface matches the official expectation
)
# File-level kinds: the target is a repo-relative path or bundle name.
FILE_KINDS = ("BUNDLE_DRIFT", "WASM_COPY_DRIFT", "STALE_WASM_BUNDLE", "PROVENANCE_UNKNOWN")
KINDS = NAME_KINDS + CASE_KINDS + FILE_KINDS

PRINCIPLE_KINDS = frozenset({"WASM_ONLY_MACRO", "TS_BODY_DRIFT"})
IN_FLIGHT_KINDS = frozenset({"DESKTOP_DEFECT"})


class LedgerError(ValueError):
    """The ledger file is malformed or violates the policy."""


@dataclass(frozen=True)
class Violation:
    """One reason a gate is red. ``proposal`` is a ready-to-paste ledger entry."""

    gate: str
    code: str
    message: str
    proposal: dict | None = None


def expiry_days(kind: str) -> int:
    if kind in PRINCIPLE_KINDS or kind in IN_FLIGHT_KINDS:
        return SHORT_EXPIRY_DAYS
    return DEFAULT_EXPIRY_DAYS


def _target_items(target: object) -> tuple[str, ...]:
    if isinstance(target, str) and target:
        items: tuple[str, ...] = (target,)
    elif (
        isinstance(target, list)
        and target
        and all(isinstance(item, str) and item for item in target)
    ):
        items = tuple(target)
    else:
        raise LedgerError(
            f"target must be a non-empty string or a list of non-empty strings, got {target!r}"
        )
    if len(set(items)) != len(items):
        raise LedgerError(f"duplicate target items: {sorted(items)}")
    return items


def _iso_date(value: object, where: str, field_name: str) -> date:
    if not isinstance(value, str):
        raise LedgerError(f"{where}: {field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"{where}: {field_name} is not an ISO date: {value!r}") from exc


@dataclass(frozen=True)
class Entry:
    id: str
    kind: str
    items: tuple[str, ...]
    reason: str
    owner: str
    since: date
    expires: date
    suite: str | None = None
    approved_by: str | None = None

    def expired(self, today: date) -> bool:
        return today > self.expires

    @classmethod
    def from_dict(cls, data: dict, where: str = "entry") -> Entry:
        if not isinstance(data, dict):
            raise LedgerError(f"{where}: an entry must be an object")
        for field_name in ("id", "kind", "target", "reason", "owner", "since", "expires"):
            if field_name not in data:
                raise LedgerError(f"{where}: missing required field {field_name!r}")
        entry_id, kind = data["id"], data["kind"]
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise LedgerError(f"{where}: id must be a non-empty string")
        if kind not in KINDS:
            raise LedgerError(f"{entry_id}: unknown kind {kind!r}; expected one of {sorted(KINDS)}")
        for field_name in ("reason", "owner"):
            if not isinstance(data[field_name], str) or not data[field_name].strip():
                raise LedgerError(f"{entry_id}: {field_name} must be a non-empty string")
        since = _iso_date(data["since"], entry_id, "since")
        expires = _iso_date(data["expires"], entry_id, "expires")
        if expires < since:
            raise LedgerError(f"{entry_id}: expires ({expires}) is before since ({since})")
        suite = data.get("suite")
        if kind in CASE_KINDS:
            if suite not in SUITES:
                raise LedgerError(f"{entry_id}: kind {kind} needs a suite in {SUITES}")
        elif suite is not None:
            raise LedgerError(f"{entry_id}: kind {kind} does not take a suite")
        approved_by = data.get("approved_by")
        if kind == "WASM_ONLY_MACRO":
            if not isinstance(approved_by, str) or not approved_by.strip():
                raise LedgerError(
                    f"{entry_id}: WASM_ONLY_MACRO is the no-wasm-only-macros principle "
                    "and needs a non-empty approved_by"
                )
        elif approved_by is not None:
            raise LedgerError(f"{entry_id}: approved_by only applies to WASM_ONLY_MACRO")
        return cls(
            entry_id,
            kind,
            _target_items(data["target"]),
            data["reason"],
            data["owner"],
            since,
            expires,
            suite,
            approved_by,
        )


def load(path: Path | None = None) -> list[Entry]:
    """Read and validate the ledger; returns entries in file order."""
    ledger_path = Path(path) if path is not None else LEDGER_PATH
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LedgerError(f"ledger not found: {ledger_path}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"{ledger_path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise LedgerError(f"{ledger_path}: expected an object with schema_version {SCHEMA_VERSION}")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise LedgerError(f"{ledger_path}: 'entries' must be a list")
    entries = [
        Entry.from_dict(item, f"{ledger_path.name} entries[{i}]")
        for i, item in enumerate(raw_entries)
    ]
    ids = [entry.id for entry in entries]
    if len(set(ids)) != len(ids):
        raise LedgerError(f"{ledger_path}: duplicate entry ids")
    return entries


@dataclass
class Reconciliation:
    """Result of matching observed gaps against the entries of one kind."""

    kind: str
    covered: dict[str, str] = field(default_factory=dict)  # item -> entry id
    expired: dict[str, str] = field(default_factory=dict)  # item -> expired entry id
    unregistered: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.expired or self.unregistered or self.stale)


def reconcile(entries: Iterable[Entry], observed: Iterable[str], *, today: date) -> Reconciliation:
    """Match one kind's entries against the gaps observed right now."""
    observed_set = set(observed)
    result = Reconciliation(kind="")
    for entry in entries:
        result.kind = entry.kind
        for item in entry.items:
            if item not in observed_set:
                result.stale.append(item)
            elif entry.expired(today):
                result.expired[item] = entry.id
            else:
                result.covered.setdefault(item, entry.id)
    result.unregistered = sorted(observed_set - result.covered.keys() - result.expired.keys())
    result.stale.sort()
    return result


def default_expiry(kind: str, since: date) -> date:
    return since + timedelta(days=expiry_days(kind))


def proposal(
    kind: str, target: object, *, suite: str | None = None, since: date | None = None
) -> dict:
    """A ready-to-paste entry skeleton. ``reason`` and ``owner`` must be filled in."""
    start = since or date.today()
    entry: dict = {
        "id": f"{kind.lower().replace('_', '-')}-<short-name>",
        "kind": kind,
        "target": target,
        "reason": "<why the gap is accepted and what removes it>",
        "owner": "<team or person>",
        "since": start.isoformat(),
        "expires": default_expiry(kind, start).isoformat(),
    }
    if suite is not None:
        entry["suite"] = suite
    if kind == "WASM_ONLY_MACRO":
        entry["approved_by"] = None
    return entry
