# QA Handoff — SOF-VD-10 SKEPTIC (validation rules)

## Verdict: CLEAN — 31/31 fresh cases (flagged=0 after 3 adjudications)

Verified: sql-name regex ^[A-Za-z][A-Za-z0-9_]*$ on ViewDefinition.name /
constant.name / column.name (leading underscore/digit, hyphen, unicode-first,
space, dot, $, empty -> ParseError; 1-char/255-char/digits-inside OK);
at-most-one-of forEach/forEachOrNull/repeat (all pairs + all-three ->
ParseError); required fields (resource, select, column.path, column.name,
constant.name, constant.value[x], where.path -> ParseError when missing);
resource binding (BogusType/lowercase/rejected, Observation OK);
fhirVersion ARRAY binding (['4.0']/['4.0.1'] OK, ['9.9.9'] rejected,
STRING form rejected as wrong type, absent optional).

Adjudications: fhirVersion is 0..* ARRAY per this spec version + official
fixtures (basic.json uses ["5.0.0","4.0.1","3.0.2"]) — my scalar-form wants
corrected; absent = optional (parsed OK).

Evidence: .temp/qa/speccomp2/sofvd10_skeptic_probe1.py
