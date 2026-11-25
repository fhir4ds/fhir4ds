"""Tier B: the real-browser audit (FEATURE_WASM_PARITY_TEST_INFRA.md §4.6).

Runs headless duckdb-wasm with the SHIPPED wasm extension bundles and the reference macros.
Skips when the web ``node_modules`` or chromium is absent (``FHIR4DS_WASM_NODE_MODULES`` may
point at another checkout); turns red under ``FHIR4DS_REQUIRE_WASM_REAL=1``.

This is the one gate that must run WITHOUT ``scripts/capped.sh``: chromium cannot start with a
capped virtual address space. It is light (a few short-lived browsers).
"""

from __future__ import annotations

import dataclasses
import os
from datetime import date

import pytest

from fhir4ds.operations.tests.wasm_parity import ledger, report, tier_b
from fhir4ds.operations.tests.wasm_parity.evaluators import SuiteResult, judge

FAMILIES = (
    "conversion",
    "list",
    "interval",
    "string",
    "logical",
    "fhirpath_udf",
    "audit_structs",
    "viewdef",
)
_RESULTS: dict[str, object] = {}


def _check(result, entries, gate="TIER_B") -> list[str]:
    violations = judge(result, entries, today=date.today(), gate=gate)
    return [f"[{v.code}] {v.message}" + (f"\n    proposal: {v.proposal}" if v.proposal else "") for v in violations]


@pytest.fixture(scope="session")
def real_facts(wasm_real, wasm_browser, wasm_contract):
    """B1/B2 facts and the contract with the exact (wasm) notion of natively provided."""
    x86_only, wasm_only = tier_b.staleness(wasm_real, wasm_browser)
    return {
        "x86_only": x86_only,
        "wasm_only": wasm_only,
        "macros": tier_b.macro_parity(wasm_real, wasm_browser),
        "versions": tier_b.versions(wasm_real, wasm_real.node_modules),
        "contract": dataclasses.replace(
            wasm_contract, stale_wasm_functions=tuple(sorted(x86_only))
        ),
    }


def test_b1_real_catalog_matches_the_simulation(real_facts, wasm_ledger):
    # macro bodies: a hard fact, nothing to register
    assert real_facts["macros"] == {
        "real_only": [],
        "sim_only": [],
        "body_diff": [],
    }
    # the exact staleness list is registered, or it is a finding
    entries = [e for e in wasm_ledger if e.kind == tier_b.STALE_KIND]
    rec = ledger.reconcile(entries, real_facts["x86_only"], today=date.today())
    problems = []
    for target in rec.unregistered:
        problems.append(f"{target!r}: {ledger.proposal(tier_b.STALE_KIND, target)}")
    problems += [f"expired: {t} ({e})" for t, e in sorted(rec.expired.items())]
    problems += [f"no longer missing, remove: {rec.stale}"] if rec.stale else []
    assert rec.ok, "\n".join(problems)


def test_b2_version_pins(real_facts):
    versions = real_facts["versions"]
    assert versions["engine"].lstrip("v") == versions["manifest_abi"], versions
    assert versions["installed_package"] == versions["manifest_package"], versions


@pytest.mark.parametrize("family", FAMILIES)
def test_b3_curated_family_matches_desktop(
    family, real_facts, wasm_desktop, wasm_real, wasm_ledger
):
    result = tier_b.run(
        wasm_desktop, wasm_real, real_facts["contract"], families=[family]
    )
    _RESULTS[family] = result
    assert result.cases, f"{family}: no case survived the availability filter"
    problems = _check(result, wasm_ledger)
    assert problems == [], f"{family}: {result.counts()}\n" + "\n".join(problems)


def test_b3_report(real_facts, wasm_desktop, wasm_real, wasm_ledger):
    """One report for every family: tests/output/wasm-parity/real.{json,md}.

    Self-sufficient: a family whose result is not cached yet is run here, so
    the report is complete when this test is selected alone, and the test
    skips together with the family tests when the real engine is unavailable.
    """
    for family in FAMILIES:
        if family not in _RESULTS:
            _RESULTS[family] = tier_b.run(
                wasm_desktop, wasm_real, real_facts["contract"], families=[family]
            )
    results = {family: _RESULTS[family] for family in FAMILIES}
    merged = SuiteResult(
        tier_b.SUITE,
        tuple(case for family in FAMILIES for case in results[family].cases),
        0,
        sum(results[family].elapsed for family in FAMILIES),
        "real",
    )
    violations = judge(merged, wasm_ledger, today=date.today(), gate="TIER_B")
    report.write_suite(merged, violations, wasm_ledger, today=date.today(), stem="real")


def test_b4_arrow_transport_envelope(wasm_desktop, wasm_real):
    records = tier_b.transport(wasm_desktop, wasm_real)
    # the text path is exact on both engines
    for record in records:
        assert record["desktop_error"] is None, record
        assert record["browser_error"] is None, record
        assert (record["browser_text"], record["browser_type"]) == (
            record["desktop_text"],
            record["desktop_type"],
        ), record
    # the Arrow path is pinned: a change here is a change in what every app displays
    for record in records:
        assert record["arrow"] == record["expected_arrow"], record
        assert record["arrow_error"] is None, record


@pytest.mark.skipif(
    os.environ.get(tier_b.FULL_CORPUS_ENV) != "1",
    reason=f"set {tier_b.FULL_CORPUS_ENV}=1 (scheduled job only) to run the whole CQL corpus "
    "on the real engine",
)
def test_b5_whole_cql_corpus_on_the_real_engine(real_facts, wasm_desktop, wasm_real, wasm_ledger):
    result = tier_b.full_corpus(wasm_desktop, wasm_real, real_facts["contract"])
    violations = judge(result, wasm_ledger, today=date.today(), gate="TIER_B")
    report.write_suite(result, violations, wasm_ledger, today=date.today(), stem="real_cql")
    problems = _check(result, wasm_ledger)
    assert problems == [], f"{result.counts()}\n" + "\n".join(problems)
