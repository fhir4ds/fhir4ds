# Scribe: v0.0.4 Evolution Summary

## Commit Message

```
fix(cql,fhirpath): harden C++ extensions for v0.0.4 spec conformance

10-iteration pressure test addressing 22 spec violations, undefined
behavior, and memory safety issues across CQL and FHIRPath DuckDB
extensions. All 686 SQL assertions passing (600 CQL + 86 FHIRPath).

CQL fixes:
- MonthsBetween/WeeksBetween: complete duration semantics (boundary math)
- CQLPrecision: return VARCHAR precision names per spec (breaking change)
- overlaps_before: respect closedness at boundary equality
- quantity arithmetic: normalize empty code to dimensionless "1";
  non-dimensionless multiply/divide returns NULL
- statistical_mode: return NULL for multi-modal distributions
- to_julian_day: use int64_t to prevent overflow
- predecessor_of: return NULL for year < 1

FHIRPath fixes:
- fhirpath_date: validate month (1-12) and day ranges with leap year
- fhirpath_number: enforce singleton (NULL for multi-item collections)
- fn_take/fn_skip/fn_truncate: overflow guard for double-to-int64 cast
- fn_dateArith: use int64_t + bounds check to prevent overflow/loops
- fn_iif: save/restore variables around criterion evaluation
- fn_aggregate/evalWhere/fn_all: variable scope isolation per iteration
- allTrue/allFalse/anyTrue/anyFalse: return empty for empty input
```
