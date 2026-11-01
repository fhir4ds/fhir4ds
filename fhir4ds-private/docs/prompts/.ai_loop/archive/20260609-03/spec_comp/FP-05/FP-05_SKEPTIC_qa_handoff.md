# QA Handoff - FP-05 SKEPTIC

## Scope

FHIRPath Normative Release section 5.3 Subsetting and 5.4 Combining:
`[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`,
`take(num)`, `intersect(other)`, `exclude(other)`, `union(other)`, and
`combine(other)`.

Spec source: https://hl7.org/fhirpath/N1/

## Spec Grounding

The section 5.3 signatures define exact function shapes: the indexer takes one
Integer index, `single()`, `first()`, `last()`, and `tail()` take no arguments,
and `skip(num)`/`take(num)` take one Integer argument. Section 5.4 defines
`union(other)` and `combine(other)` with exactly one collection argument.
`intersect(other)` and `exclude(other)` in section 5.3 also take exactly one
collection argument. Public `fhirpath_is_valid()` must reject malformed
signatures, and result UDFs should return empty/NULL through row resilience.

## Hypotheses Tested

1. Native no-argument subsetting functions may ignore unexpected arguments.
2. Native one-argument subsetting/combining functions may ignore extra
   arguments.
3. Native `fhirpath_is_valid()` may validate malformed `skip`/`take` on sparse
   Patient input because invalid count arguments are checked after empty-input
   short-circuiting.
4. Integer count/index arguments may accept Decimal-looking values.
5. Equality-based `union`/`intersect`/`exclude` may drift for duplicate JSON
   objects or compatible Quantity values.

## Result

Logged `QA-001` as a HIGH native C++ spec violation. Native C++ accepted
malformed section 5.3/5.4 calls that forced Python fallback rejected:

- `a.first(0)` returned `['zero']`, `fhirpath_is_valid=true`.
- `a.last(0)` returned `['two']`, `fhirpath_is_valid=true`.
- `a.tail(0)` returned `['one', 'two']`, `fhirpath_is_valid=true`.
- `a.skip(1, 2)` returned `['one', 'two']`, `fhirpath_is_valid=true`.
- `a.take(1, 2)` returned `['zero']`, `fhirpath_is_valid=true`.
- `a.combine(b, ints)`, `a.union(b, ints)`, `a.intersect(b, ints)`, and
  `a.exclude(b, ints)` ignored the second argument and returned data.
- Missing `skip`/`take`/combining arguments returned empty public results but
  still reported `fhirpath_is_valid=true` natively.
- `a.skip(1.0)`, `a.take(1.0)`, and multi-item count arguments returned empty
  public results but still reported `fhirpath_is_valid=true` natively on the
  sparse validation resource.

Probe artifact: `.temp/qa/fp05_skeptic_probe.py`.

## Validation Run

Focused probe only. Full validation is deferred to remediation after the fix.
