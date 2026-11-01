# QA Handoff - CQL-16 SKEPTIC

## Scope

SPEC COMPLIANCE CHUNK CQL-16: CQL interval operators part 2. Fresh SKEPTIC run from current state, covering Included In precision, Intersect, Meets/Meets Before/Meets After, Not Equal, Not Equivalent, On Or After/Before, Overlaps/Overlaps Before/Overlaps After, translated CQL, forced Python fallback, native-loaded registration, and no-Python C++ extension.

Translator architecture AGENTS file was not present at `docs/architecture/translator/AGENTS.md`; root AGENTS, `extensions/cql/AGENTS.md`, `GLOBAL_RULES.md`, and current durable knowledge were used.

## Spec Anchor

Official CQL Reference v1.5.3 Appendix B says interval `intersect` returns the overlapping portion of both intervals, or null if they do not overlap. The same reference defines `overlaps before` and `overlaps after` as overlaps plus Start/End boundary ordering; Date/DateTime/Time precision comparisons are performed at the specified precision where present, and existing CQL comparison semantics preserve unknown temporal/Quantity comparisons as null rather than false.

Reference checked: https://cql.hl7.org/09-b-cqlreference.html

## Hypotheses Tested

1. `intervalIntersect` may choose raw endpoints rather than effective Start/End boundaries for half-open intervals.
2. `overlaps before/after` may collapse an unknown overlap result to false.
3. Quantity interval ordering may diverge between Python fallback and no-Python C++ when units are incompatible.
4. `meets before/after`, `on or after`, and `on or before` may mishandle open endpoints if they do not use effective boundaries.
5. Interval `!=` and `!~` may diverge for typed null intervals.

## Evidence

Probe file: `.temp/qa/cql16_skeptic_probe.py`

Command:

```bash
python3 .temp/qa/cql16_skeptic_probe.py
```

Result: failed as expected with two HIGH findings.

## Findings

`QA-001` HIGH: `intervalIntersect` ignores effective open endpoints in forced Python/native-loaded paths.

Reproducer: `Interval[1, 5) intersect Interval[5, 7]`

Expected: `null`, because the first interval excludes 5 and there is no overlapping point.

Actual: forced Python and native-loaded return `{"low":"5","high":"5","lowClosed":true,"highClosed":true}`. no-Python C++ returns null. Translated CQL `IntersectOpenDisjoint` reproduces the bad Python/native result.

`QA-002` HIGH: `overlaps before/after` collapses unknown overlap to false and has Quantity parity drift.

Reproducers:

```sql
SELECT intervalOverlapsBefore(intervalFromBounds('2014','2014',true,true), intervalFromBounds('2014-06-01','2014-06-02',true,true));
SELECT intervalOverlapsAfter(intervalFromBounds('2014-06-01','2014-06-02',true,true), intervalFromBounds('2014','2014',true,true));
SELECT intervalOverlapsBefore(intervalFromBounds('{"value":1,"unit":"g"}', '{"value":3,"unit":"g"}', true, true), intervalFromBounds('{"value":1,"unit":"cm"}', '{"value":2,"unit":"cm"}', true, true));
```

Expected: SQL NULL for unknown partial-temporal overlap and incompatible Quantity ordering.

Actual: partial-temporal `overlaps before/after` return false across all three surfaces. Incompatible Quantity `overlaps before/after` return false in forced Python/native-loaded and NULL in no-Python C++, so semantics and parity both fail. Translated CQL reproduces the same failures.

## Passing Coverage

The probe also covered passing CQL-16 boundaries for included-in precision, finite/unbounded intersection, open-bound meets before/after, effective-bound on-or-after/on-or-before, `!~` over null intervals, and `!=` over null intervals.

## Handoff

Set `evolution.json.phase` to `FIX` with `QA-001` and `QA-002` open.
