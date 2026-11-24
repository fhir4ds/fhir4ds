"""Tier A: official corpora agree on desktop and on the browser contract.

One ratchet test per suite (decision D-2). Each suite reuses its official
runner's comparator, so "expected" is decided by the same code the conformance
gate runs. Every non-green case must be registered in ``known_gaps.json``
(fix, or register with a reason and an owner). Reports are written to
``tests/output/wasm-parity/<suite>.{json,md}``.

Plan: FEATURE_WASM_PARITY_TEST_INFRA.md section 4.4.
"""

from __future__ import annotations

from datetime import date

import pytest

from fhir4ds.operations.tests.wasm_parity import evaluators, report
from fhir4ds.operations.tests.wasm_parity.evaluators import cql
from fhir4ds.operations.tests.wasm_parity.reference_bundle import (
    EnvironmentInputMissing,
    required,
)

SUITES = {cql.SUITE: cql}


@pytest.mark.parametrize("suite", sorted(SUITES))
def test_corpus_parity(suite, wasm_desktop, wasm_browser, wasm_contract, wasm_ledger):
    module = SUITES[suite]
    try:
        result = module.run(wasm_desktop, wasm_browser, wasm_contract)
    except EnvironmentInputMissing as exc:
        if required():
            raise
        pytest.skip(str(exc))
    violations = evaluators.judge(result, wasm_ledger, today=date.today())
    report.write_suite(result, violations, wasm_ledger, today=date.today())
    assert not violations, report.failure_text(
        f"Tier A ({suite} corpus, desktop vs browser contract)", violations
    )
