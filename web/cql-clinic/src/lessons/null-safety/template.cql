library NullSafety version '1.0.0'

context Patient

// CQL uses SQL-style three-valued logic: null means UNKNOWN, not false.
// The fixture patient has NO deathDate and NO telecom (absent fields),
// which makes them null — perfect for exploring null behavior.

define "Deceased Is Null": Patient.deceased is null
// TODO: "Explicit Null Is Null" — what does the literal null is null produce?
// TODO: "Null Not Equal" must use != to compare null with 'x'
//   (surprise: the answer is not true!)
// TODO: "Null And False" must evaluate null and false
// TODO: "Null Or True" must evaluate null or true
// TODO: "Null Not Propagates" must evaluate not null
// TODO: "Coalesce First NonNull" must return 'found me' from a list with nulls
// TODO: "Missing Field Is Null" must test that Patient.telecom is absent
// TODO: "Coalesce Field Default" must produce 'still alive' by coalescing
//   the patient's (absent) deceased value
// TODO: "Count Ignores Null" must count {null, 'a', null, 'b'} (nulls skipped!)
// TODO: "IsNull Vs IsTrue" must be an if/then/else: when (Patient.deceased
//   is null) is true, return 'no death date', else 'has death date'
