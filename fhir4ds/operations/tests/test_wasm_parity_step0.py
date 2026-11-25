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
from pathlib import Path

from fhir4ds.operations.tests.wasm_parity import contract, report, shipped_bundles, surfaces

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


def test_t7_shipped_wasm_bundles_are_one_known_set(wasm_ledger):
    """T7: every shipped copy matches the manifest, one core pin, provenance recorded."""
    observed = shipped_bundles.observe(shipped_bundles.load_manifest())
    violations = contract.evaluate_files(wasm_ledger, observed, today=date.today())
    report.write_files(observed, violations, wasm_ledger, today=date.today())
    assert not violations, report.failure_text("Step 0, T7 (shipped WASM bundles)", violations)

def test_t7_untracked_build_output_is_not_a_shipped_copy(tmp_path: Path) -> None:
    """A developer's gitignored build output must not register as drift.

    ``web/website/build/`` is gitignored docusaurus output that carries copies
    of the wasm bundles and cql-macros.ts. Walking it made every dev who had
    built the site see ~18 phantom WASM_COPY_DRIFT entries, so the scan is
    scoped to git-tracked files; this pins that scope.
    """
    repo = tmp_path / "repo"
    (repo / "web" / "app" / "dist").mkdir(parents=True)
    (repo / "web" / "website" / "build" / "assets").mkdir(parents=True)
    tracked = repo / "web" / "app" / "dist" / "cql.duckdb_extension.wasm"
    untracked = repo / "web" / "website" / "build" / "assets" / "cql.duckdb_extension.wasm"
    tracked.write_bytes(b"tracked")
    untracked.write_bytes(b"untracked")

    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "web/app/dist/cql.duckdb_extension.wasm"], cwd=repo, check=True)

    found = shipped_bundles._tracked_bundles(repo)

    assert tracked in found
    assert untracked not in found
