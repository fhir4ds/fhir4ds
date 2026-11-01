# Architect Handoff: CQL-12 HISTORIAN

## Structural Health

Healthy after remediation. The defect was a public helper-surface mismatch:
translated CQL already implemented three-argument `Substring`, but direct
DuckDB `Substring` exposed only the two-argument macro and hid the
length-limited behavior behind `SubstringLen`. The fix moved canonical
semantics back to the CQL-named helper and left `SubstringLen` as a thin
compatibility alias.

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with CQL-12 string invariants. The
relevant invariant is that public direct helpers must expose the same signatures
as the CQL Reference and stay parity-tested across forced Python fallback,
native-loaded registration, and no-Python/browser-style runtime paths.

## Audit Result

No new architectural findings. The change:
- Stays localized to `registerStringMacros`.
- Adds no resource, profile, measure, or fixture-specific logic.
- Preserves null propagation and 0-based indexing semantics.
- Keeps `SubstringLen` as a compatibility alias rather than a competing
  implementation.
- Adds direct runtime parity tests instead of relying only on translated CQL.

QA quality was sufficient. The HISTORIAN pass covered exact signatures,
official null/boundary semantics, Unicode character indexing, regex behavior,
invalid type guardrails from CQL-12 SKEPTIC, translated execution, and all
three DuckDB runtime surfaces. `RETRY_QA` is not set.

## Final Status

Issues by category:
- `SPEC_VIOLATION`: 1 found, 1 verified.

Recommended fix order: no further CQL-12 HISTORIAN fixes remain.
