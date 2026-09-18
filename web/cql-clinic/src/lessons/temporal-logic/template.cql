library TemporalLogic version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// This lesson is all about WHEN: ages, durations, and intervals.
// Fixture patients: Alice Johnson (born 1985-03-12) and Bob Smith (born 1972-07-23).
// All dates are fixed, so every result is deterministic.

define "Age In Years": AgeInYearsAt(@2024-03-12)
// TODO: "Age In Months" must be Alice's age in whole months at @2024-03-12
// TODO: "Days Since Birth" must count elapsed days from the patient's birthDate to @2024-03-12
//   (hint: Patient.birthDate.value gives the Date; days between A and B)
// TODO: "Birthday Month" must extract the month number from the birthDate
// TODO: "First Obs In 2024" must return the earliest Observation effective date
//   in the first half of 2024 (during Interval[@2024-01-01, @2024-06-30])
//   (hint: cast the choice type — O.effective as FHIR.dateTime)
// TODO: "Latest Effective" must return the chronologically last Observation effective date
// TODO: "In Measurement Period" must be true: does Interval[@2024-01-01, @2024-06-30] contain @2024-03-01?
// TODO: "Enclosure Count" must count Encounters whose ENTIRE period falls in the
//   first half of 2024 (one of Alice's three encounters extends past June 30)
// TODO: "Measurement Period Width" must be the elapsed days from start to end of
//   Interval[@2024-01-01, @2024-06-30] (2024 is a leap year)
// TODO: "Overlapping Intervals" must be true: Interval[@2024-01-01, @2024-03-31]
//   overlaps Interval[@2024-03-01, @2024-06-30]
// TODO: "Adjacent Or After" — is it true that Interval[@2024-03-01, @2024-06-30]
//   starts 30 days or less before start of Interval[@2024-04-01, @2024-06-30]?
