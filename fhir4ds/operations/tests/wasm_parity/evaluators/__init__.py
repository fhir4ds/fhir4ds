"""Tier A: official corpora evaluated on both surfaces (plan section 4.4).

Each evaluator reuses its official runner's own comparator, so "expected" is
decided by the same code the conformance gate runs. One ratchet test per suite
(decision D-2) asserts that every non-green case is registered in the ledger.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from ..ledger import CASE_KINDS, Entry, Violation, proposal, reconcile
from ..surfaces import emitted_names

GREEN = "GREEN"
PARITY_GAP = "PARITY_GAP"  # desktop matches the official expectation, browser does not
BROWSER_ONLY_PASS = "BROWSER_ONLY_PASS"  # browser matches, desktop does not
BOTH_FAIL = "BOTH_FAIL"  # neither surface matches the official expectation
ENGINE_DIFF = "ENGINE_DIFF"  # both match, but raw value or declared type differs
TRANSLATE_DIFF = "TRANSLATE_DIFF"  # SQL text depends on the translation connection
TRANSLATE_ERROR = "TRANSLATE_ERROR"  # engine-independent; reported, not gated

OUTCOMES = (
    GREEN,
    PARITY_GAP,
    BROWSER_ONLY_PASS,
    BOTH_FAIL,
    ENGINE_DIFF,
    TRANSLATE_DIFF,
    TRANSLATE_ERROR,
)
ATTRIBUTABLE_KINDS = (PARITY_GAP, ENGINE_DIFF, BROWSER_ONLY_PASS)
# Name-level kinds that explain a wrong RESULT: a case whose every flagged name
# is registered under one of these needs no case-level entry.
ROOT_CAUSE_KINDS = ("MISSING_IN_BROWSER", "WASM_ONLY_MACRO", "TS_BODY_DRIFT", "SIGNATURE_DIFF")
# Name-level kinds that explain a REPRESENTATION difference only (desktop wraps
# a Python UDF in a macro; the browser runs the native namesake). They cover
# ENGINE_DIFF; a wrong result always needs its own case-level entry.
CONTEXT_KINDS = ("MACRO_VS_NATIVE",)


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    outcome: str
    desktop: str  # official comparator verdict on the desktop surface
    browser: str  # ... on the browser contract
    detail: str = ""  # what differs, or why
    suspects: tuple[str, ...] = ()  # emitted names the contract flags
    missing: tuple[str, ...] = ()  # subset: names the browser contract lacks

    @property
    def green(self) -> bool:
        return self.outcome == GREEN


@dataclass(frozen=True)
class SuiteResult:
    suite: str
    cases: tuple[CaseOutcome, ...]
    gated: int = 0  # tests the official runner's own gating does not execute
    elapsed: float = 0.0

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = dict.fromkeys(OUTCOMES, 0)
        for case in self.cases:
            out[case.outcome] += 1
        return out


def suspects_for(sql: str, contract) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(flagged names the SQL emits, names the browser contract lacks).

    Attribution is a set difference on the SQL text, never error-text parsing.
    """
    emitted = emitted_names(sql)
    flagged = emitted & contract.flagged_names()
    missing = (emitted & contract.desktop_names) - contract.browser_names
    return tuple(sorted(flagged)), tuple(sorted(missing))


def _live_name_entries(
    entries: list[Entry], today: date
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    """(root-cause name -> live entry id, context name -> live entry id, expired names)."""
    root: dict[str, str] = {}
    context: dict[str, str] = {}
    expired: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        if entry.kind in ROOT_CAUSE_KINDS:
            target = root
        elif entry.kind in CONTEXT_KINDS:
            target = context
        else:
            continue
        for item in entry.items:
            if entry.expired(today):
                expired[item].append(entry.id)
            else:
                target.setdefault(item, entry.id)
    return root, context, expired


def judge(result: SuiteResult, entries: list[Entry], *, today: date) -> list[Violation]:
    """Apply the triage policy to one suite's outcomes."""
    root_live, context_live, expired_names = _live_name_entries(entries, today)
    of_kind: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        if entry.kind in CASE_KINDS and entry.suite == result.suite:
            of_kind[entry.kind].append(entry)

    violations: list[Violation] = []
    for kind in ATTRIBUTABLE_KINDS:
        case_ids: list[str] = []
        for case in result.cases:
            if case.outcome != kind:
                continue
            if case.suspects:
                stale = {
                    name: expired_ids
                    for name in case.suspects
                    if name not in root_live
                    and name not in context_live
                    and (expired_ids := expired_names.get(name))
                }
                for name, entry_ids in sorted(stale.items()):
                    violations.append(
                        Violation(
                            "TIER_A",
                            "EXPIRED_REGISTRATION",
                            f"{result.suite} {case.case_id}: name-level gap {name!r} is only "
                            f"covered by expired registration {entry_ids}",
                        )
                    )
                if all(name in root_live for name in case.suspects):
                    continue  # a registered root cause explains the wrong result
                if kind == ENGINE_DIFF and all(
                    name in root_live or name in context_live for name in case.suspects
                ):
                    continue  # a registered representation difference
            case_ids.append(case.case_id)
        rec = reconcile(of_kind[kind], case_ids, today=today)
        for item, entry_id in sorted(rec.expired.items()):
            violations.append(
                Violation(
                    "TIER_A",
                    "EXPIRED_REGISTRATION",
                    f"{result.suite} {kind}: entry {entry_id!r} expired but still covers "
                    f"{item!r}; fix the gap or re-register with a reason",
                )
            )
        if rec.stale:
            violations.append(
                Violation(
                    "TIER_A",
                    "STALE_REGISTRATION",
                    f"{result.suite} {kind}: registered cases no longer reproduce — remove "
                    f"them from known_gaps.json: {rec.stale}",
                )
            )
        if rec.unregistered:
            violations.append(
                Violation(
                    "TIER_A",
                    "UNREGISTERED_GAP",
                    f"{result.suite} {kind}: {len(rec.unregistered)} unregistered case(s): "
                    f"{rec.unregistered}",
                    proposal=proposal(
                        kind,
                        rec.unregistered if len(rec.unregistered) > 1 else rec.unregistered[0],
                        suite=result.suite,
                    ),
                )
            )

    both_fail = tuple(case.case_id for case in result.cases if case.outcome == BOTH_FAIL)
    rec = reconcile(of_kind["DESKTOP_DEFECT"], both_fail, today=today)
    for item, entry_id in sorted(rec.expired.items()):
        violations.append(
            Violation(
                "TIER_A",
                "EXPIRED_REGISTRATION",
                f"{result.suite} BOTH_FAIL: desktop defect entry {entry_id!r} expired but "
                f"{item!r} still fails on both surfaces",
            )
        )
    if rec.stale:
        violations.append(
            Violation(
                "TIER_A",
                "STALE_REGISTRATION",
                f"{result.suite} DESKTOP_DEFECT: registered desktop defects no longer "
                f"reproduce — remove them: {rec.stale}",
            )
        )
    if rec.unregistered:
        violations.append(
            Violation(
                "TIER_A",
                "UNREGISTERED_GAP",
                f"{result.suite} BOTH_FAIL: {len(rec.unregistered)} desktop defect(s) fail "
                f"on both surfaces and are unregistered: {rec.unregistered}",
                proposal=proposal("DESKTOP_DEFECT", list(both_fail), suite=result.suite),
            )
        )
    for case in result.cases:
        if case.outcome == TRANSLATE_DIFF:
            violations.append(
                Violation(
                    "TIER_A",
                    "TRANSLATE_DIFF",
                    f"{result.suite} {case.case_id}: translated SQL depends on the "
                    f"translation connection ({case.detail}); must be zero and cannot be "
                    "registered",
                )
            )
    return violations
