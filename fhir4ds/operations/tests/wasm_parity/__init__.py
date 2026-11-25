"""WASM parity test infrastructure (AMUX-175 / CONDU-2).

Plan: ``fhir4ds-private/docs/architecture/plans/FEATURE_WASM_PARITY_TEST_INFRA.md``.

* ``reference_bundle`` -- Step 0: the browser macro statements, read as ground truth.
* ``surfaces`` -- the desktop surface and the simulated browser contract (section 4.1).
* ``contract`` -- Step 0 contract gates T1-T7 (section 4.3).
* ``ledger`` -- ``known_gaps.json``: every accepted gap with a kind, reason, owner,
  expiry (section 4.5).
* ``evaluators`` -- Tier A: official corpora evaluated on both surfaces (section 4.4).
* ``report`` -- the per-run gap report under ``tests/output/wasm-parity/``.
"""

from .ledger import (
    CASE_KINDS,
    KINDS,
    LEDGER_PATH,
    NAME_KINDS,
    Entry,
    LedgerError,
    Reconciliation,
    Violation,
    load,
    reconcile,
)
from .reference_bundle import (
    EnvironmentInputMissing,
    ReferenceBundle,
    app_macro_files,
    load_reference_bundle,
)

__all__ = [
    "CASE_KINDS",
    "EnvironmentInputMissing",
    "Entry",
    "KINDS",
    "LEDGER_PATH",
    "NAME_KINDS",
    "LedgerError",
    "Reconciliation",
    "Violation",
    "ReferenceBundle",
    "app_macro_files",
    "load",
    "load_reference_bundle",
    "reconcile",
]
