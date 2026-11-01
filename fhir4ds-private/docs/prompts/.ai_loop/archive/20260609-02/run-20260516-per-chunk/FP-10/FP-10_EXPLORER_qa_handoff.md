# QA Handoff - FP-10 EXPLORER

## Scope

FHIRPath N1 §5.6.6-§5.6.12 String Manipulation (Transform): `upper()`, `lower()`, `replace(pattern, substitution)`, `matches(regex)`, `replaceMatches(regex, substitution)`, `length()`, and `toChars()`.

## Spec Basis

Verified against https://hl7.org/fhirpath/N1/ §5.6. The section requires singleton String input for string functions; non-String or multi-item input signals an error to the calling environment. `matches()` must be case-sensitive, single-line/DOTALL, and allow Unicode characters. `replaceMatches()` replaces each regex match and may use regex capture groups. `length()` and `toChars()` operate on characters, not UTF-8 bytes.

## Exploration

Created `.temp/qa/fp10_explorer_probe.py` to compare public DuckDB outputs across the native C++ extension and a forced Python fallback connection. The probe stressed Unicode code points, multi-code-point grapheme sequences, empty pattern replacement, regex `.` on non-ASCII strings, invalid regex patterns, null/missing values, non-String values, and multi-item fields.

## Findings

1. `QA-001` HIGH: Native `matches()`/`replaceMatches()` apply regex `.` byte-wise for non-ASCII UTF-8. Examples:
   - `accent.matches('.')`: native `false`, Python fallback `true` for `é`.
   - `emoji.matches('.')`: native `false`, Python fallback `true` for `😀`.
   - `accent.replaceMatches('.', 'x')`: native `xx`, fallback `x`.
   - `emoji.replaceMatches('.', 'x')`: native `xxxx`, fallback `x`.

2. `QA-002` MEDIUM: Bundled native extension is stale for Unicode case mapping already present in source:
   - `sharp.upper().length()` on `Straße`: native `6`, fallback `7`.
   - `greek.lower().upper()` on `Σςσ`: native `ΣϢΣ`, fallback `ΣΣΣ`.

## Non-Issues Verified

Empty input, null fields, non-String fields, multi-item fields, empty argument collections, empty pattern `replace()`, DOTALL newline matching, and capture-group `$1`/`$2` replacement behaved as expected or matched forced fallback.
