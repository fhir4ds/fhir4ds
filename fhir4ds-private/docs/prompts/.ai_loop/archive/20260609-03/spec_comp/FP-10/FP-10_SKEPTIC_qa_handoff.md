# QA Handoff - FP-10 SKEPTIC

Spec focus: FHIRPath Normative Release §5.6.6-§5.6.12 string transforms:
`upper()`, `lower()`, `replace(pattern, substitution)`, `matches(regex)`,
`replaceMatches(regex, substitution)`, `length()`, and `toChars()`.

Spec source checked directly: https://hl7.org/fhirpath/N1/ lines around
§5.6. The relevant contract says these functions operate on singleton String
collections, signal an error for multi-item or non-String input, and have the
signatures shown in their headings.

SKEPTIC source predictions before testing:

1. Native C++ dispatch has no exact arity guard for FP-10 transforms, so extra
   arguments may be ignored.
2. Native `replace`/`matches`/`replaceMatches` may evaluate dynamic arguments
   against the source String instead of the outer resource focus.
3. Fallback `length()` may still read the first item instead of enforcing a
   singleton String.
4. `fhirpath_is_valid()` may report true when sparse validation data makes the
   transform input empty before argument type or regex safety is checked.

Fresh probe:

`python3 .temp/qa/fp10_skeptic_probe.py > .temp/qa/fp10_skeptic_probe.log`

Result: 39 cases, 19 failures before remediation. The failures were grouped
into `QA-001` through `QA-004` in `evolution.json`.

Key evidence:

- `s.upper(1)`, `s.replace('a','b','c')`, `s.matches('a','b')`,
  `s.replaceMatches('a','b','c')`, `s.length(1)`, and `s.toChars(1)` returned
  native data and `fhirpath_is_valid=true` despite invalid signatures.
- `s.replace(pattern, sub)` and `s.matches(regex)` differed between native C++
  and forced Python fallback because native argument focus was wrong.
- Forced Python fallback returned the length of the first item for
  `arr.length()` where `arr` contained two strings.
- Unsafe regex patterns such as `(a+)+` remained `fhirpath_is_valid=true` when
  validation reached an empty source path before checking the regex literal.

Recommended fix:

- Add exact FP-10 arity checks in native `evalFunction`.
- Evaluate ordinary FP-10 transform arguments against the outer invocation
  focus for sourced calls.
- Validate FP-10 argument cardinality/type and regex safety before input-empty
  short-circuiting where the argument itself is concrete.
- Make fallback `length()` use the same singleton String helper as other
  transform functions.
- Extend fallback static validation for FP-10 arity, literal argument types,
  literal unions, and dangerous regex literals.
