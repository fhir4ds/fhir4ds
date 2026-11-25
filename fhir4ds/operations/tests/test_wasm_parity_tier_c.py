"""Tier C: real measure population SQL on real duckdb-wasm.

Per PR a curated set of measures goes through the gate; ``FHIR4DS_WASM_TIER_C_SUITE=<suite>`` runs
every measure of a suite (the scheduled job). Skips when the DQM fixtures, the web ``node_modules``
or chromium are absent; red under ``FHIR4DS_REQUIRE_WASM_PARITY=1`` and
``FHIR4DS_REQUIRE_WASM_REAL=1``. Like Tier B it must run WITHOUT ``scripts/capped.sh`` (chromium
cannot start with a capped address space); the desktop translation of each measure runs in its own
child process.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from fhir4ds.operations.tests.wasm_parity import ledger, report, tier_c
from fhir4ds.operations.tests.wasm_parity.reference_bundle import EnvironmentInputMissing, required

SUITE = "qi-core-2025"


def _require(suite: str) -> None:
    try:
        tier_c.fixture_dir(suite)
    except EnvironmentInputMissing as exc:
        if required():
            raise
        pytest.skip(str(exc))


def _outcome(real, work, measure_id: str, suite: str) -> tier_c.Outcome:
    try:
        dump = tier_c.dump_for(work, measure_id, suite)
    except tier_c.TranslateError as exc:
        return tier_c.Outcome(measure_id, suite, "TRANSLATE_ERROR", str(exc)[:400])
    return tier_c.run_measure(real, dump)


_SEEN: dict[str, list[tier_c.Outcome]] = {}
DUMP_CACHE_ENV = "FHIR4DS_WASM_TIER_C_DUMP_CACHE"  # local convenience for re-runs


def _work(tmp_path_factory):
    """Where measure dumps are cached. Translation is the slow part of a suite run, so a local
    re-run may point at an earlier directory; a translator change must invalidate it."""
    cached = os.environ.get(DUMP_CACHE_ENV, "").strip()
    return Path(cached) if cached else tmp_path_factory.getbasetemp() / "tier-c"


def _check(outcomes: list[tier_c.Outcome], entries, suite: str, *, stem: str) -> None:
    violations = tier_c.judge(outcomes, entries, today=date.today(), suite=suite)
    seen = _SEEN.setdefault(stem, [])  # the report carries every measure judged so far
    seen.extend(o for o in outcomes if o.measure not in {x.measure for x in seen})
    tier_c.write_report(seen, violations, report.OUTPUT_DIR / f"{stem}.json")
    assert not violations, report.failure_text(f"Tier C ({suite})", violations)


@pytest.mark.parametrize("measure_id", tier_c.CURATED)
def test_curated_measure_matches_desktop_on_the_real_engine(measure_id, wasm_real, wasm_ledger, tmp_path_factory):
    _require(tier_c.CURATED_SUITE)
    outcome = _outcome(wasm_real, _work(tmp_path_factory), measure_id, tier_c.CURATED_SUITE)
    _check([outcome], wasm_ledger, tier_c.CURATED_SUITE, stem="tier_c")


def test_whole_suite_on_the_real_engine(wasm_real, wasm_ledger, tmp_path_factory):
    suite = os.environ.get(tier_c.SUITE_ENV, "").strip().lower()
    if not suite:
        pytest.skip(f"opt-in: set {tier_c.SUITE_ENV}=<suite> to run every measure of a suite")
    _require(suite)
    work = _work(tmp_path_factory)
    outcomes = [_outcome(wasm_real, work, m, suite) for m in tier_c.measure_ids(suite)]
    _check(outcomes, wasm_ledger, suite, stem=f"tier_c_{suite}")


def _entry(items: tuple[str, ...], suite: str = SUITE):
    return ledger.Entry(
        id="tierc-test",
        kind="PARITY_GAP",
        items=items,
        reason="known real-only defect",
        owner="test",
        since=date(2026, 11, 24),
        expires=date(2026, 12, 24),
        suite=suite,
        surface="real",
    )


class TestComparison:
    def test_another_order_and_another_instant_spelling_are_not_gaps(self):
        cols = ["patient_id", "IP", "T0", "E"]
        desktop = [["p1", "true", "2025-10-01 08:00:00+00:00", "[a, b]"], ["p2", "false", "None", "None"]]
        wasm = [["p1", "true", "2025-10-01T08:00:00.000Z", "[b, a]"], ["p2", "false", "None", "None"]]
        diffs, same = tier_c.compare(cols, desktop, wasm)
        assert same
        assert diffs["T0"]["kind"] == "instant"
        assert diffs["E"]["kind"] == "order"

    def test_a_boolean_difference_and_a_new_patient_are_gaps(self):
        diffs, same = tier_c.compare(
            ["id", "IP"], [["p1", "true"], ["p2", "false"]], [["p1", "false"], ["p2", "false"], ["p3", "true"]]
        )
        assert not same
        assert diffs["IP"]["kind"] == "boolean"
        assert diffs["id"]["kind"] == "patients"

    def test_a_real_value_difference_is_a_gap(self):
        diffs, same = tier_c.compare(
            ["id", "T0"], [["p1", "2025-10-01 08:00:00+00:00"]], [["p1", "2025-10-02T08:00:00.000Z"]]
        )
        assert same
        assert diffs["T0"]["kind"] == "value"

    def test_the_same_instant_inside_json_text_is_not_a_gap(self):
        desktop = [["p1", '{"low": "2025-05-01T00:00:00.000+00:00", "high": "2026-04-30T23:59:59.000+00:00"}']]
        wasm = [["p1", '{"low": "2025-05-01T00:00:00.000Z", "high": "2026-04-30T23:59:59.000Z"}']]
        diffs, same = tier_c.compare(["id", "Intake Period"], desktop, wasm)
        assert same
        assert diffs["Intake Period"]["kind"] == "instant"

    def test_another_offset_for_another_instant_stays_a_gap(self):
        desktop = [["p1", "2025-10-01 08:00:00+00:00"]]
        wasm = [["p1", "2025-10-01T09:00:00.000Z"]]
        diffs, _ = tier_c.compare(["id", "T0"], desktop, wasm)
        assert diffs["T0"]["kind"] == "value"

    def test_identical_rows_have_no_differences(self):
        assert tier_c.compare(["id", "IP"], [["p1", "true"]], [["p1", "true"]]) == ({}, True)


class TestJudge:
    def test_an_unregistered_gap_fails_with_a_ready_proposal(self):
        outcome = tier_c.Outcome("CMS75", SUITE, "PARITY_GAP")
        violations = tier_c.judge([outcome], [], today=date(2026, 11, 25), suite=SUITE)
        assert [v.code for v in violations] == ["UNREGISTERED"]
        assert violations[0].proposal["target"] == "CMS75"
        assert violations[0].proposal["suite"] == SUITE
        assert violations[0].proposal["surface"] == "real"

    def test_a_registered_gap_passes_until_it_expires(self):
        outcome = tier_c.Outcome("CMS75", SUITE, "PARITY_GAP")
        entry = _entry(["CMS75"])
        assert tier_c.judge([outcome], [entry], today=date(2026, 11, 25), suite=SUITE) == []
        later = tier_c.judge([outcome], [entry], today=date(2026, 12, 25), suite=SUITE)
        assert [v.code for v in later] == ["EXPIRED_REGISTRATION"]

    def test_a_fixed_measure_makes_its_registration_stale(self):
        outcome = tier_c.Outcome("CMS75", SUITE, "IDENTICAL")
        violations = tier_c.judge([outcome], [_entry(["CMS75"])], today=date(2026, 11, 25), suite=SUITE)
        assert [v.code for v in violations] == ["STALE_REGISTRATION"]

    def test_an_engine_error_is_a_gap_inside_its_own_suite_only(self):
        outcome = tier_c.Outcome("CMS56", SUITE, "ERROR", "More than one row returned by a subquery")
        elsewhere = _entry(["CMS56"], suite="cql")
        violations = tier_c.judge([outcome], [elsewhere], today=date(2026, 11, 25), suite=SUITE)
        assert [v.code for v in violations] == ["UNREGISTERED"]
        assert tier_c.judge([outcome], [_entry(["CMS56"])], today=date(2026, 11, 25), suite=SUITE) == []

    def test_a_measure_this_run_did_not_evaluate_is_neither_required_nor_stale(self):
        outcomes = [tier_c.Outcome("CMS68", SUITE, "IDENTICAL")]
        entry = _entry(["CMS75", "CMS832"])
        assert tier_c.judge(outcomes, [entry], today=date(2026, 11, 25), suite=SUITE) == []

    def test_a_failed_desktop_translation_is_not_registrable(self):
        outcome = tier_c.Outcome("CMS2", SUITE, "TRANSLATE_ERROR", "boom")
        violations = tier_c.judge([outcome], [_entry(["CMS2"])], today=date(2026, 11, 25), suite=SUITE)
        assert [v.code for v in violations] == ["TRANSLATE_ERROR", "STALE_REGISTRATION"]
