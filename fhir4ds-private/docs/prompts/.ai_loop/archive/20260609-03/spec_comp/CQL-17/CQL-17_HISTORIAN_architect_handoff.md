# Architect Handoff - CQL-17 HISTORIAN

## Structural Health

Pass. The remediation is localized to the public CQL interval helper boundary where typed-null transport values are converted into user-visible `Start`/`End` results. It does not add measure, profile, fixture, or CQL-expression-specific branching. Python fallback, native-loaded registration, and no-Python/browser-style C++ now share the same point-type extrema contract.

## Golden Standard

Written to `.temp/architect/golden_standard.md`.

Key invariant: `__null__` may be used as an internal typed-null bound marker, but public `intervalStart` / `intervalEnd` must never expose it. Closed null bounds return CQL point-type extrema; open null bounds remain SQL NULL.

## Issue Summary

- `QA-001` HIGH `SPEC_VIOLATION`: verified and resolved. No new architecture findings.

## QA Quality

Adequate. The QA probe covered translated and direct helper surfaces across forced Python fallback, native-loaded registration, and no-Python C++; it also preserved the CQL-17 SKEPTIC distinction between null interval values and existing null-bound intervals. No `RETRY_QA` needed.

## Validation Reviewed

- `.temp/qa/cql17_historian_probe.py`: passed.
- `test_interval_part3_parity.py`: 3/3.
- Interval part 1/2/3 plus WASM/no-Python gates: 31/31.
- Official interval category: 412/412.
- Full conformance: 2822/2822.

## Recommended Fix Order

No remaining CQL-17 HISTORIAN issues. Continue to the next personality/chunk under the outer spec compliance orchestrator.
