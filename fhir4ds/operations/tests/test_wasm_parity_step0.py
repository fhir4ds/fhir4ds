"""Step 0: the browser contract is pinned and every gap is registered.

T1  the reference bundle parses and matches its own ``REGISTERED_MACRO_NAMES``
T2  the simulated browser surface is exactly bare + bundles + reference statements
T3  no wasm-only macros (the principle: no macros in WASM that desktop lacks)
T4  same-name macros carry the same body
T5  every desktop macro is in the reference or natively provided
T6  every app's ``cql-macros.ts`` is byte-identical to the reference

Plan: FEATURE_WASM_PARITY_TEST_INFRA.md section 4.3. A gap may be accepted only
by a ledger entry with a reason, an owner and an expiry (section 4.5). The
report is written to ``tests/output/wasm-parity/step0.{json,md}``.
"""

from __future__ import annotations

from datetime import date

from fhir4ds.operations.tests.wasm_parity import contract, report, surfaces

GATE = "Step 0 (browser contract vs desktop)"


def test_t1_t2_reference_and_simulator_are_faithful(wasm_reference, wasm_contract):
    """T1 + T2 hold with no registered exception."""
    violations = contract.check_reference(wasm_contract) + contract.check_simulator(wasm_reference)
    assert not violations, report.failure_text(GATE, violations)
    assert wasm_contract.reference_statement_count == len(wasm_reference.statements) > 0


def test_t3_t6_contract_gaps_are_registered(wasm_reference, wasm_contract, wasm_ledger):
    """T3-T6: every contract gap has a live ledger entry; none is stale or expired."""
    violations = contract.evaluate(wasm_contract, wasm_ledger, today=date.today())
    report.write_contract(
        wasm_contract,
        surfaces.simulator_fidelity(wasm_reference),
        violations,
        wasm_ledger,
        today=date.today(),
    )
    assert not violations, report.failure_text(GATE, violations)
