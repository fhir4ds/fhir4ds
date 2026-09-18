library StringsConversions version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "Shout": Upper('hello')
define "Whisper": Lower('WORLD')
define "Name Length": Length('FHIR')
define "First Word": Substring('FHIRPath', 0, 4)
define "Is Http": StartsWith('http://hl7.org', 'http')
define "Is Pdf": EndsWith('report.pdf', 'pdf')
define "Date Reformat": ReplaceMatches('2024-03-01', '-', '/')
define "First Segment": First(Split('a,b,c', ','))
define "Joined": Combine({'a', 'b', 'c'}, '-')
define "B Position": PositionOf('b', 'abc')
define "Gender Shouted": Upper(Patient.gender)
define "Int To String": ToString(42)
define "String To Integer": ToInteger('42')
define "String To Decimal": ToDecimal('3.5')
define "Integer Convertible": ConvertsToInteger('42')
define "Not Integer Convertible": ConvertsToInteger('3.5')
define "Birth Year String": ToString(year from Patient.birthDate.value)
