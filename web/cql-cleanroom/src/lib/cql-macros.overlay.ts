// Hand-written browser bodies for desktop macros the generator cannot port yet.
//
// `cql-macros.ts` is GENERATED (fhir4ds/operations/tests/wasm_parity/macro_bundle.py) from
// the desktop catalog. This overlay is the only hand-written SQL left in the reference
// bundle, and Step 0 (test_wasm_parity_step0.py) keeps it honest:
//
//   * every name here is either a desktop macro the generator classes as `blocked` — its
//     desktop body needs a helper the browser lacks, so it is registered as
//     MISSING_IN_BROWSER in wasm_parity/known_gaps.json — or a browser-only macro Joel
//     approved (`Coalesce`, ledger `wasm-only-coalesce`). A body here is a known, expiring
//     gap, never a silent substitute;
//   * once the helper is ported the generator emits the desktop body and the statement here
//     must be deleted — Step 0 fails until it is.
//
// These bodies are NOT the desktop bodies: they are older or simplified spellings and behave
// differently (see the ledger entries). Add nothing here without a ledger entry.

export const HAND_WRITTEN_MACROS: string[] = [
  "CREATE MACRO IF NOT EXISTS \"Coalesce\"(a, b) AS COALESCE(a, b)",
];
