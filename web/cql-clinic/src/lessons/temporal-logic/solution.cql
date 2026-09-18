library TemporalLogic version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "Age In Years": AgeInYearsAt(@2024-03-12)
define "Age In Months": AgeInMonthsAt(@2024-03-12)
define "Days Since Birth": days between Patient.birthDate.value and @2024-03-12
define "Birthday Month": month from Patient.birthDate.value
define "First Obs In 2024":
  First([Observation] O where (O.effective as FHIR.dateTime) during Interval[@2024-01-01, @2024-06-30] return (O.effective as FHIR.dateTime).value)
define "Latest Effective": Last([Observation] O return (O.effective as FHIR.dateTime).value)
define "In Measurement Period": Interval[@2024-01-01, @2024-06-30] contains @2024-03-01
define "Enclosure Count": Count([Encounter] E where E.period during Interval[@2024-01-01, @2024-06-30])
define "Measurement Period Width": days between start of Interval[@2024-01-01, @2024-06-30] and end of Interval[@2024-01-01, @2024-06-30]
define "Overlapping Intervals": Interval[@2024-01-01, @2024-03-31] overlaps Interval[@2024-03-01, @2024-06-30]
define "Adjacent Or After": Interval[@2024-03-01, @2024-06-30] starts 30 days or less before start of Interval[@2024-04-01, @2024-06-30]
