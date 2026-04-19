/*
@update: JSR 2025-01-23 ->
Updated library to account for USCDI requirements.
*/
library SupplementalDataElements version '4.0.000'

using QICore version '6.0.0'

include FHIRHelpers version '4.4.000' called FHIRHelpers

codesystem "AdministrativeGender": 'http://terminology.hl7.org/CodeSystem/v3-AdministrativeGender'
codesystem "SNOMEDCT": 'http://snomed.info/sct'
codesystem "DataAbsentReason": 'http://terminology.hl7.org/CodeSystem/data-absent-reason'

valueset "Ethnicity": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.837'
valueset "ONC Administrative Sex": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1'
valueset "Sex": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1240.3'
valueset "Patient Sex For Quality Measurement": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1021.120'
valueset "Payer Type": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591'
valueset "Race": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.836'

code "M": 'M' from "AdministrativeGender" display 'Male'
code "F": 'F' from "AdministrativeGender" display 'Female'

code "Patient sex unknown": '184115007' from SNOMEDCT display 'Patient sex unknown (finding)'
code "Female": '248152002' from SNOMEDCT display 'Female (finding)'
code "Male": '248153007' from SNOMEDCT display 'Male (finding)'

code "Asked But Declined": 'asked-declined' from DataAbsentReason

context Patient

define "SDE Ethnicity":
  Patient.ethnicity E
    return Tuple {
      codes: { E.ombCategory } union E.detailed,
      display: E.text
    }

define "SDE Payer":
  [Coverage: type in "Payer Type"] Payer
    return {
      code: Payer.type,
      period: Payer.period
    }

define "SDE Race":
  Patient.race R
    return Tuple {
      codes: R.ombCategory union R.detailed,
      display: R.text
    }

define "SDE Sex":
  case
    when Patient.sex = '184115007' then "Patient sex unknown"
    when Patient.sex = '248152002' then "Female"
    when Patient.sex = '248153007' then "Male"
    when Patient.sex = 'asked-declined' then "Asked But Declined"
    when Patient.gender = 'male' then "M"
    when Patient.gender = 'female' then "F"
    else null
  end