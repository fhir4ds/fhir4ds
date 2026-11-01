# QA Handoff: CQL-14 HISTORIAN

## Scope

Chunk CQL-14, Date/Time Operators Part 2:
`Now()`, `Today()`, `TimeOfDay()`, precision-aware same/on-or-before/on-or-after
operators, Date/DateTime/Time minus Quantity, and `Time(...)` construction.

Spec source: CQL Reference v1.5.3 Appendix B, Date and Time Operators
(`https://cql.hl7.org/09-b-cqlreference.html#datetime-operators-3`).

`docs/architecture/translator/AGENTS.md` is not present in this checkout; QA
used root `AGENTS.md`, `extensions/cql/AGENTS.md`, `GLOBAL_RULES.md`,
`GLOBAL_KNOWLEDGE.md`, and `PROC_VALIDATION.md`.

## Fresh Probe

Created `.temp/qa/cql14_historian_probe.py`.

The probe checks:
- current-clock helper shape for `dateTimeNow`, `dateTimeToday`, and
  `dateTimeTimeOfDay` across forced Python fallback, native-loaded, and
  no-Python C++ registrations where available.
- timezone-normalized and uncertainty-aware `dateTimeSame*` / `cqlSame*`
  precision comparisons, including invalid precision returning SQL NULL.
- Date/DateTime/Time minus Quantity behavior, malformed Quantity rejection,
  fractional day/week truncation, and midnight wraparound.
- translated CQL for `Now() = Now()`, `TimeOfDay() = TimeOfDay()`,
  uncertain precision comparisons, DateTime subtraction, one-argument
  `Time(hour)`, `time from <DateTime>`, and trailing-null `Time(...)`
  constructor components.

## Finding

`QA-001` HIGH, OPEN:
Translated `Time(...)` constructors reject trailing null components that the
official Time constructor rule treats as unspecified precision. Expected:
`Time(12, null)` -> `T12`, `Time(12, 30, null)` -> `T12:30`,
`Time(12, 30, 0, null)` -> `T12:30:00`; actual translated execution returned
SQL NULL at `Time(12, null)`.

The invalid gap case `Time(12, null, 0)` should continue returning SQL NULL.

