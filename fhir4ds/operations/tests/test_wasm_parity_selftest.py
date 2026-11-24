"""Mutation tests of the ratchet: each way of silencing a gap must go red.

The gates are only useful if they cannot be quieted by accident. These tests
feed synthetic gaps to the ledger and the Tier A judge -- no DuckDB, no corpus.

Plan: FEATURE_WASM_PARITY_TEST_INFRA.md step 8 and section 6.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import count

import pytest

from fhir4ds.operations.tests.wasm_parity import contract, evaluators, ledger
from fhir4ds.operations.tests.wasm_parity.evaluators import CaseOutcome, SuiteResult

TODAY = date(2026, 11, 24)
_IDS = count()


def entry(kind, target, *, suite=None, days=10, **extra):
    """A valid ledger entry; ``days`` negative gives an already-expired one."""
    since = TODAY if days >= 0 else TODAY - timedelta(days=40, seconds=0)
    data = {
        "id": f"{kind.lower()}-{next(_IDS)}",
        "kind": kind,
        "target": target,
        "reason": "test",
        "owner": "test",
        "since": since.isoformat(),
        "expires": (TODAY + timedelta(days=days)).isoformat(),
        **extra,
    }
    if suite:
        data["suite"] = suite
    if kind == "WASM_ONLY_MACRO":
        data["approved_by"] = "tester"
    return ledger.Entry.from_dict(data)


def case(outcome, *, suspects=(), name="CqlX.xml::Case"):
    return CaseOutcome(name, outcome, "pass", "fail", "", tuple(suspects), tuple(suspects))


def result(*cases):
    return SuiteResult("cql", tuple(cases))


def codes(violations):
    return sorted(v.code for v in violations)


# ------------------------------------------------------------------ ledger


def test_reconcile_reports_unregistered_stale_and_expired():
    live = entry("MISSING_IN_BROWSER", "ported_long_ago")
    rec = ledger.reconcile([live], ["brand_new"], today=TODAY)
    assert rec.unregistered == ["brand_new"]
    assert rec.stale == ["ported_long_ago"]
    assert not rec.ok


def test_reconcile_accepts_a_live_registration():
    rec = ledger.reconcile([entry("MISSING_IN_BROWSER", ["a", "b"])], ["a", "b"], today=TODAY)
    assert rec.ok and set(rec.covered) == {"a", "b"}


def test_expired_registration_that_still_covers_a_gap_fails():
    stale_dated = entry("TS_BODY_DRIFT", "round", days=-1)
    rec = ledger.reconcile([stale_dated], ["round"], today=TODAY)
    assert rec.expired == {"round": stale_dated.id} and not rec.ok
    # the day before expiry it is still live
    assert ledger.reconcile([entry("TS_BODY_DRIFT", "round", days=0)], ["round"], today=TODAY).ok


@pytest.mark.parametrize(
    "mutation",
    [
        {"kind": "NOT_A_KIND"},
        {"approved_by": None},  # WASM_ONLY_MACRO needs an approver
        {"suite": "cql"},  # a name-level kind does not take a suite
        {"expires": "yesterday"},
    ],
)
def test_ledger_rejects_malformed_entries(mutation):
    data = entry("WASM_ONLY_MACRO", "coalesce").__dict__
    data = {**data, "since": TODAY.isoformat(), "expires": (TODAY + timedelta(days=30)).isoformat()}
    data.update(mutation)
    with pytest.raises(ledger.LedgerError):
        ledger.Entry.from_dict(data)


def test_case_kinds_need_a_suite_and_principle_kinds_expire_sooner():
    with pytest.raises(ledger.LedgerError):
        entry("PARITY_GAP", ["a"], suite=None)
    assert ledger.expiry_days("TS_BODY_DRIFT") == ledger.SHORT_EXPIRY_DAYS
    assert ledger.expiry_days("MISSING_IN_BROWSER") == ledger.DEFAULT_EXPIRY_DAYS
    assert ledger.expiry_days("DESKTOP_DEFECT") == ledger.SHORT_EXPIRY_DAYS


def test_shipped_ledger_is_valid():
    assert ledger.load(), "the ledger must carry the triaged baseline"


# ------------------------------------------------------------------ Tier A judge


def test_unregistered_gap_fails_with_a_ready_to_paste_entry():
    violations = evaluators.judge(result(case("PARITY_GAP")), [], today=TODAY)
    assert codes(violations) == ["UNREGISTERED_GAP"]
    proposal = violations[0].proposal
    assert proposal["kind"] == "PARITY_GAP" and proposal["suite"] == "cql"


def test_registered_gap_passes_and_stale_registration_fails():
    gap = result(case("PARITY_GAP"))
    registered = entry("PARITY_GAP", ["CqlX.xml::Case"], suite="cql")
    assert evaluators.judge(gap, [registered], today=TODAY) == []
    stale = evaluators.judge(result(), [registered], today=TODAY)
    assert codes(stale) == ["STALE_REGISTRATION"]


def test_expired_case_registration_does_not_cover_the_gap():
    expired = entry("PARITY_GAP", ["CqlX.xml::Case"], suite="cql", days=-1)
    assert codes(evaluators.judge(result(case("PARITY_GAP")), [expired], today=TODAY)) == [
        "EXPIRED_REGISTRATION"
    ]


def test_root_cause_name_registration_explains_a_wrong_result():
    gap = result(case("PARITY_GAP", suspects=["cqllistequaleq"]))
    ported = entry("MISSING_IN_BROWSER", "cqllistequaleq")
    assert evaluators.judge(gap, [ported], today=TODAY) == []
    expired = entry("MISSING_IN_BROWSER", "cqllistequaleq", days=-1)
    assert codes(evaluators.judge(gap, [expired], today=TODAY)) == [
        "EXPIRED_REGISTRATION",
        "UNREGISTERED_GAP",
    ]


def test_representation_registration_never_covers_a_wrong_result():
    """MACRO_VS_NATIVE accepts a type/serialisation difference, not a wrong value."""
    context = entry("MACRO_VS_NATIVE", "highboundary")
    diff = result(case("ENGINE_DIFF", suspects=["highboundary"]))
    assert evaluators.judge(diff, [context], today=TODAY) == []
    wrong = result(case("PARITY_GAP", suspects=["highboundary"]))
    assert codes(evaluators.judge(wrong, [context], today=TODAY)) == ["UNREGISTERED_GAP"]


def test_a_wrong_result_with_two_causes_needs_both_registered():
    gap = result(case("PARITY_GAP", suspects=["slice", "round"]))
    only_one = entry("MISSING_IN_BROWSER", "slice")
    assert codes(evaluators.judge(gap, [only_one], today=TODAY)) == ["UNREGISTERED_GAP"]
    both = [only_one, entry("TS_BODY_DRIFT", "round")]
    assert evaluators.judge(gap, both, today=TODAY) == []


def test_both_fail_is_a_desktop_defect_even_when_a_name_is_registered():
    desktop_defect = result(case("BOTH_FAIL", suspects=["round"]))
    registered_name = entry("TS_BODY_DRIFT", "round")
    violations = evaluators.judge(desktop_defect, [registered_name], today=TODAY)
    assert codes(violations) == ["UNREGISTERED_GAP"]
    fixed = entry("DESKTOP_DEFECT", ["CqlX.xml::Case"], suite="cql")
    assert evaluators.judge(desktop_defect, [registered_name, fixed], today=TODAY) == []


def test_translation_diff_cannot_be_registered():
    diff = result(CaseOutcome("CqlX.xml::T", "TRANSLATE_DIFF", "translated", "translated"))
    violation = evaluators.judge(diff, [], today=TODAY)[0]
    assert violation.code == "TRANSLATE_DIFF" and violation.proposal is None


def test_translation_errors_and_green_cases_are_not_gated():
    outcome = CaseOutcome("CqlX.xml::E", "TRANSLATE_ERROR", "translate: boom", "-")
    assert evaluators.judge(result(case("GREEN"), outcome), [], today=TODAY) == []


# ------------------------------------------------------------------ Step 0


def fake_contract(**overrides):
    base = dict(
        reference_statement_count=1,
        reference_registration_mismatch=(),
        desktop_names=frozenset({"a"}),
        browser_names=frozenset({"a"}),
        wasm_only_macros=(),
        body_drift={},
        desktop_only_uncovered=(),
        signature_drift={},
        macro_vs_native=(),
        app_copies=(("web/app/src/lib/cql-macros.ts", "identical"),),
    )
    return contract.Contract(**{**base, **overrides})


def test_contract_gates_demand_registration_per_kind():
    drift = fake_contract(
        wasm_only_macros=("coalesce",),
        body_drift={"round": ("a", "b")},
        desktop_only_uncovered=("slice",),
        app_copies=(("web/app/src/lib/cql-macros.ts", "differs"),),
    )
    violations = contract.evaluate(drift, [], today=TODAY)
    assert codes(violations) == ["UNREGISTERED_GAP"] * 4
    by_proposal = {v.proposal["kind"] for v in violations}
    assert by_proposal == {"WASM_ONLY_MACRO", "TS_BODY_DRIFT", "MISSING_IN_BROWSER", "BUNDLE_DRIFT"}
    entries = [
        entry("WASM_ONLY_MACRO", "coalesce"),
        entry("TS_BODY_DRIFT", "round"),
        entry("MISSING_IN_BROWSER", "slice"),
        entry("BUNDLE_DRIFT", "web/app/src/lib/cql-macros.ts"),
    ]
    assert contract.evaluate(drift, entries, today=TODAY) == []


def test_macro_vs_native_is_reported_but_not_required():
    native = fake_contract(macro_vs_native=("highboundary",))
    assert contract.evaluate(native, [], today=TODAY) == []
    stale = entry("MACRO_VS_NATIVE", "highboundary")
    assert codes(contract.evaluate(native, [stale], today=TODAY)) == []


def test_t1_t2_violations_name_the_problem():
    drifted = fake_contract(reference_registration_mismatch=("Ghost"))
    (violation,) = contract.check_reference(drifted)
    assert (violation.gate, violation.code) == ("T1", "REFERENCE_EXPORT_DRIFT")
