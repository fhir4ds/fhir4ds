# QA Handoff - FP-10 HISTORIAN

## Scope

FHIRPath Normative Release §5.6.6-§5.6.12 string transform functions:
`upper()`, `lower()`, `replace(pattern, substitution)`, `matches(regex)`,
`replaceMatches(regex, substitution)`, `length()`, and `toChars()`.

Spec source: https://hl7.org/fhirpath/N1/ lines 1282-1411. The relevant
contract is singleton String input; empty collection/argument propagation where
specified; exact arity; Unicode-capable string behavior; and regex functions
that use a regular expression argument.

## Fresh Probe

Created `.temp/qa/fp10_historian_probe.py` with 51 cases run in isolated native
C++ and forced Python fallback subprocesses. Coverage included ASCII and UTF-8
case conversion, code-point length/chars, literal `replace` versus regex
`replaceMatches`, capture substitution, dynamic sibling-field arguments,
empty collection propagation, singleton/multi-item input errors, invalid arity,
non-String arguments, malformed regex syntax, ReDoS patterns, and overlong
regex guards.

Initial result: 13 probe failures, representing 3 unique issues after removing
wrapper expectation noise around `fhirpath_bool(length()==1)`.

## Issues

- `QA-001` HIGH: malformed regex syntax is not validated consistently.
  `s.matches('[invalid')` leaves native `fhirpath_is_valid=true` and causes the
  forced Python fallback SQL UDF to raise `InvalidInputException`.
- `QA-002` MEDIUM: native `upper()`/`lower()` miss common Latin Extended-A case
  pairs such as `č/Č`, `ž/Ž`, and `š/Š`.
- `QA-003` MEDIUM: forced Python fallback `replace()` treats a singleton empty
  input string with a non-matching pattern as empty collection instead of
  returning the original empty string.

## Artifacts

- Probe: `.temp/qa/fp10_historian_probe.py`
- Current failing command: `python3 .temp/qa/fp10_historian_probe.py`

