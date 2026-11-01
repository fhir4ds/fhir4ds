# QA Handoff: CQL-10 HISTORIAN

## Scope

CQL arithmetic operators Part 1: `Abs`, `Add`, `Ceiling`, `Divide`, `Floor`, `Exp`, `HighBoundary`, `Log`, `Ln`, and `LowBoundary`.

This HISTORIAN run started from the active source and official XML fixtures. It did not consult archived workflow output. Coverage focused on official boundary/date-time history, direct public helper behavior, native C++/browser surface behavior, forced Python fallback behavior, and regression risk around already-passing conformance.

## Findings

`QA-CQL10-HISTORIAN-001` found that public `HighBoundary`/`LowBoundary` helper calls over time strings with `Z` or signed offsets produced malformed strings in the Python fallback and needed matching native C++ behavior for the C++-only surface. The fix preserves the suffix while filling missing time components. Static CQL `@T...Z/+/-` literals remain invalid per the official XML and are rejected by the translator.

`QA-CQL10-HISTORIAN-002` found that forced Python fallback boundary helpers treated numeric strings as temporal text. Decimal boundary strings now match native C++, while four-digit year-only date strings still retain date precision behavior required by official `HighBoundary(@2014, 6)` / `LowBoundary(@2014, 6)` cases.

## Verification

- `python3 conformance/scripts/run_cql.py` passed `1706/1706`.
- `python3 conformance/scripts/run_all.py` passed overall `2822/2822`.
- `python3 -m pytest fhir4ds -q` passed `7171 passed, 5 skipped, 9 warnings`.
- Native C++ CQL unit target passed `638 assertions`.
- Focused parity/C++ surface pytest passed `15/15`.
