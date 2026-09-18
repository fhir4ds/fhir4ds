library StringsConversions version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// One patient: Alice, female, born 1990-05-15.

define "Shout": Upper('hello')
// TODO: "Whisper" must lowercase 'WORLD'
// TODO: "Name Length" must count the characters in 'FHIR'
// TODO: "First Word" must slice 'FHIRPath' from index 0, length 4
// TODO: "Is Http" must test that 'http://hl7.org' starts with 'http'
// TODO: "Is Pdf" must test that 'report.pdf' ends with 'pdf'
// TODO: "Date Reformat" must replace dashes with slashes in '2024-03-01'
//   (ReplaceMatches takes a regex pattern)
// TODO: "First Segment" must split 'a,b,c' on commas and take the first
// TODO: "Joined" must combine {'a', 'b', 'c'} with '-' separator
// TODO: "B Position" must find the zero-based position of 'b' in 'abc'
// TODO: "Gender Shouted" must uppercase the patient's gender field
// TODO: "Int To String" must render 42 as a string
// TODO: "String To Integer" must parse '42' into an Integer
// TODO: "String To Decimal" must parse '3.5' into a Decimal
// TODO: "Integer Convertible" must check '42' converts to Integer
// TODO: "Not Integer Convertible" must check '3.5' — decimals never
//   integer-convert (no truncation)!
// TODO: "Birth Year String" must extract the patient's birth year and
//   render it as a string
