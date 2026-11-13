/*
@description: Common terminologies and functions used in FHIR-based CQL artifacts
*/
library FHIRCommon version '2.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1'

codesystem "LOINC": 'http://loinc.org'
codesystem "SNOMEDCT": 'http://snomed.info/sct'
codesystem "ICD10CM": 'http://hl7.org/fhir/sid/icd-10-cm'
codesystem "RoleCode": 'http://terminology.hl7.org/CodeSystem/v3-RoleCode'
codesystem "Diagnosis Role": 'http://terminology.hl7.org/CodeSystem/diagnosis-role'
codesystem "RequestIntent": 'http://hl7.org/fhir/request-intent'
codesystem "MedicationRequestCategory": 'http://terminology.hl7.org/CodeSystem/medicationrequest-category'
codesystem "ConditionClinicalStatusCodes": 'http://terminology.hl7.org/CodeSystem/condition-clinical'
codesystem "ConditionVerificationStatusCodes": 'http://terminology.hl7.org/CodeSystem/condition-ver-status'
codesystem "AllergyIntoleranceClinicalStatusCodes": 'http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical'
codesystem "AllergyIntoleranceVerificationStatusCodes": 'http://terminology.hl7.org/CodeSystem/allergyintolerance-verification'
codesystem "ConditionCategoryCodes": 'http://terminology.hl7.org/CodeSystem/condition-category'
codesystem "ObservationStatusCodes": 'http://hl7.org/fhir/observation-status'
codesystem "ObservationCategoryCodes": 'http://terminology.hl7.org/CodeSystem/observation-category'
codesystem "TaskCodeSystem": 'http://hl7.org/fhir/CodeSystem/task-code' 

code "Birthdate": '21112-8' from "LOINC" display 'Birth date'
code "Dead": '419099009' from "SNOMEDCT" display 'Dead'
code "ER": 'ER' from "RoleCode" display 'Emergency room'
code "ICU": 'ICU' from "RoleCode" display 'Intensive care unit'
code "Billing": 'billing' from "Diagnosis Role" display 'Billing'

// Condition Clinical Status Codes - Consider value sets for these
code "active": 'active' from "ConditionClinicalStatusCodes"
code "recurrence": 'recurrence' from "ConditionClinicalStatusCodes"
code "relapse": 'relapse' from "ConditionClinicalStatusCodes"
code "inactive": 'inactive' from "ConditionClinicalStatusCodes"
code "remission": 'remission' from "ConditionClinicalStatusCodes"
code "resolved": 'resolved' from "ConditionClinicalStatusCodes"

// Condition Verification Status Codes - Consider value sets for these
code "unconfirmed": 'unconfirmed' from ConditionVerificationStatusCodes
code "provisional": 'provisional' from ConditionVerificationStatusCodes
code "differential": 'differential' from ConditionVerificationStatusCodes
code "confirmed": 'confirmed' from ConditionVerificationStatusCodes
code "refuted": 'refuted' from ConditionVerificationStatusCodes
code "entered-in-error": 'entered-in-error' from ConditionVerificationStatusCodes

code "allergy-active": 'active' from "AllergyIntoleranceClinicalStatusCodes"
code "allergy-inactive": 'inactive' from "AllergyIntoleranceClinicalStatusCodes"
code "allergy-resolved": 'resolved' from "AllergyIntoleranceClinicalStatusCodes"

// Allergy/Intolerance Verification Status Codes - Consider value sets for these
code "allergy-unconfirmed": 'unconfirmed' from AllergyIntoleranceVerificationStatusCodes
code "allergy-confirmed": 'confirmed' from AllergyIntoleranceVerificationStatusCodes
code "allergy-refuted": 'refuted' from AllergyIntoleranceVerificationStatusCodes

// MedicationRequest Category Codes
code "Inpatient": 'inpatient' from "MedicationRequestCategory" display 'Inpatient'
code "Outpatient": 'outpatient' from "MedicationRequestCategory" display 'Outpatient'
code "Community": 'community' from "MedicationRequestCategory" display 'Community'
code "Discharge": 'discharge' from "MedicationRequestCategory" display 'Discharge'

// Diagnosis Role Codes
code "AD": 'AD' from "Diagnosis Role" display 'Admission diagnosis'
code "DD": 'DD' from "Diagnosis Role" display 'Discharge diagnosis'
code "CC": 'CC' from "Diagnosis Role" display 'Chief complaint'
code "CM": 'CM' from "Diagnosis Role" display 'Comorbidity diagnosis'
code "pre-op": 'pre-op' from "Diagnosis Role" display 'pre-op diagnosis'
code "post-op": 'post-op' from "Diagnosis Role" display 'post-op diagnosis'
code "billing": 'billing' from "Diagnosis Role" display 'billing diagnosis'

// Observation Status Codes
code "observation-registered": 'registered' from "ObservationStatusCodes" display 'Registered'
code "observation-preliminary": 'preliminary' from "ObservationStatusCodes" display 'Preliminary'
code "observation-final": 'final' from "ObservationStatusCodes" display 'Final'
code "observation-amended": 'amended' from "ObservationStatusCodes" display 'Amended'
code "observation-corrected": 'corrected' from "ObservationStatusCodes" display 'Corrected'
code "observation-cancelled": 'cancelled' from "ObservationStatusCodes" display 'Cancelled'
code "observation-entered-in-error": 'entered-in-error' from "ObservationStatusCodes" display 'Entered in Error'
code "observation-unknown": 'unknown' from "ObservationStatusCodes" display 'Unknown'

// Observation Category Codes
code "social-history": 'social-history' from "ObservationCategoryCodes" display 'Social History'
code "vital-signs": 'vital-signs' from "ObservationCategoryCodes" display 'Vital Signs'
code "imaging": 'imaging' from "ObservationCategoryCodes" display 'Imaging'
code "laboratory": 'laboratory' from "ObservationCategoryCodes" display 'Laboratory'
code "procedure": 'procedure' from "ObservationCategoryCodes" display 'Procedure'
code "survey": 'survey' from "ObservationCategoryCodes" display 'Survey'
code "exam": 'exam' from "ObservationCategoryCodes" display 'Exam'
code "therapy": 'therapy' from "ObservationCategoryCodes" display 'Therapy'
code "activity": 'activity' from "ObservationCategoryCodes" display 'Activity'

// Condition Category Codes
code "problem-list-item": 'problem-list-item' from "ConditionCategoryCodes" display 'Problem List Item'
code "encounter-diagnosis": 'encounter-diagnosis' from "ConditionCategoryCodes" display 'Encounter Diagnosis'

//Task codes
code "Fulfill": 'fulfill' from "TaskCodeSystem" display 'Fulfill'

context Patient

/*
@description: Normalizes a value that is a choice of timing-valued types to an equivalent interval
@comment: Normalizes a choice type of FHIR.dateTime, FHIR.Period, FHIR.Timing, FHIR.instance, FHIR.string, FHIR.Age, or FHIR.Range types
to an equivalent interval. This selection of choice types is a superset of the majority of choice types that are used as possible
representations for timing-valued elements in FHIR, allowing this function to be used across any resource.

The input can be provided as a dateTime, Period, Timing, instant, string, Age, or Range.
The intent of this function is to provide a clear and concise mechanism to treat single
elements that have multiple possible representations as intervals so that logic doesn't have to account
for the variability. More complex calculations (such as medication request period or dispense period
calculation) need specific guidance and consideration. That guidance may make use of this function, but
the focus of this function is on single element calculations where the semantics are unambiguous.
If the input is a dateTime, the result a DateTime Interval beginning and ending on that dateTime.
If the input is a Period, the result is a DateTime Interval.
If the input is a Timing, an error is raised indicating a single interval cannot be computed from a Timing.
If the input is an instant, the result is a DateTime Interval beginning and ending on that instant.
If the input is a string, an error is raised indicating a single interval cannot be computed from a string.
If the input is an Age, the result is a DateTime Interval beginning when the patient was the given Age,
and ending immediately prior to when the patient was the given Age plus one year.
If the input is a Range, the result is a DateTime Interval beginning when the patient was the Age given
by the low end of the Range, and ending immediately prior to when the patient was the Age given by the
high end of the Range plus one year.

NOTE: Due to the
complexity of determining a single interval from a Timing or String type, this function will throw a run-time exception if it is used
with a Timing or String.
*/
define fluent function toInterval(choice Choice<FHIR.dateTime, FHIR.Period, FHIR.Timing, FHIR.instant, FHIR.string, FHIR.Age, FHIR.Range>):
  case
    when choice is FHIR.dateTime then
      Interval[FHIRHelpers.ToDateTime(choice as FHIR.dateTime), FHIRHelpers.ToDateTime(choice as FHIR.dateTime)]
    when choice is FHIR.Period then
      FHIRHelpers.ToInterval(choice as FHIR.Period)
    when choice is FHIR.instant then
      Interval[FHIRHelpers.ToDateTime(choice as FHIR.instant), FHIRHelpers.ToDateTime(choice as FHIR.instant)]
    when choice is FHIR.Age then
      Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(choice as FHIR.Age),
        FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(choice as FHIR.Age) + 1 year)
    when choice is FHIR.Range then
      Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity((choice as FHIR.Range).low),
        FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity((choice as FHIR.Range).high) + 1 year)
    when choice is FHIR.Timing then
      Message(null as Interval<DateTime>, true, 'NOT_IMPLEMENTED', 'Error', 'Calculation of an interval from a Timing value is not supported')
    when choice is FHIR.string then
      Message(null as Interval<DateTime>, true, 'NOT_IMPLEMENTED', 'Error', 'Calculation of an interval from a String value is not supported')
    else
      null as Interval<DateTime>
  end

/*
@description: Given an interval, return true if the interval has a starting boundary specified
(i.e. the start of the interval is not null and not the minimum DateTime value)
*/
define fluent function hasStart(period Interval<DateTime>):
  not ( start of period is null
      or start of period = minimum DateTime
  )

/*
@description: Given an interval, returns true if the interval has an ending boundary specified
(i.e. the end of the interval is not null and not the maximum DateTime value)
*/
define fluent function hasEnd(period Interval<DateTime>):
  not (
    end of period is null
      or end of period = maximum DateTime
  )

/*
@description: Given an interval, returns the ending point if the interval has an ending boundary specified,
otherwise, returns the starting point
*/
define fluent function latest(choice Choice<FHIR.dateTime, FHIR.Period, FHIR.Age, FHIR.Range>):
  (choice.toInterval()) period
    return
      if (period.hasEnd()) then end of period
      else start of period

/*
@description: Given an interval, return the starting point if the interval has a starting boundary specified,
otherwise, return the ending point
*/
define fluent function earliest(choice Choice<FHIR.dateTime, FHIR.Period, FHIR.Age, FHIR.Range>):
  (choice.toInterval()) period
    return
      if (period.hasStart()) then start of period
      else end of period

/*
@description: Returns true if the given reference is to the given resource
@comment: Returns true if the `id` element of the given resource exactly equals the tail of the given reference.
NOTE: This function assumes resources from the same source server.
*/
define fluent function references(reference FHIR.Reference, resource FHIR.Resource):
  resource.id = Last(Split(reference.reference, '/'))  

/*
@description: Returns true if the given reference is to the given resourceId
@comment: Returns true if the `resourceId` parameter exactly equals the tail of the given reference.
NOTE: This function assumes resources from the same source server.
*/
define fluent function references(reference FHIR.Reference, resourceId String):
  resourceId = Last(Split(reference.reference, '/'))

/*
@description: Returns true if any of the given references are to the given resource
@comment: Returns true if the `id` element of the given resource exactly equals the tail of any of the given references.
NOTE: This function assumes resources from the same source server.
*/
define fluent function references(references List<FHIR.Reference>, resource FHIR.Resource):
  exists (references R where R.references(resource))
  
/*
@description: Returns true if any of the given references are to the given resourceId
@comment: Returns true if the `resourceId` parameter exactly equals the tail of any of the given references.
NOTE: This function assumes resources from the same source server.
*/
define fluent function references(references List<FHIR.Reference>, resourceId String):
  exists (references R where R.references(resourceId))

/*
@description: Returns true if the given code is in the given codeList
@comment: Returns true if the `code` is equivalent to any of the codes in the given `codeList`, false otherwise.
*/
define fluent function includesCode(codeList List<CodeableConcept>, code Concept):
  exists (codeList C where C ~ code)

/*
@description: Returns the canonical reference to the ValueSet referred to by the codeOptions extension, if present
@comment: This function is usable on any CodeableConcept, and looks for the [codeOptions](https://hl7.org/fhir/extensions/StructureDefinition-codeOptions.html)
extension, returning the canonical reference to the ValueSet identifying the set of possible codes for the activity.
@seealso: [Activity Extent](https://build.fhir.org/ig/HL7/cql-ig/patterns.html#activity-extent)
*/
define fluent function codeOptions(code CodeableConcept):
  (code.ext('http://hl7.org/fhir/StructureDefinition/codeOptions').value as canonical)

/*
@description: Returns the url portion of the given canonical reference (as a string)
@comment: This function returns the url portion of the given canonical reference (i.e. everything up to but not including the version pipe (`|`) and version).
If the canonical reference does not have a version, this function returns the canonical reference.
For example, given the canonical reference `http://example.org/ValueSet/ABC|123`, this function returns `http://example.org/ValueSet/ABC`.
*/
define fluent function url(canonical FHIR.canonical):
  Split(canonical, '|').first()

/*
@description: Returns the version portion of the given canonical reference (as a string)
@comment: This function returns the version portion of the given canonical reference (i.e. everything after the version pipe (`|`), if present).
If the canonical reference does not have a version, this function returns `null`.
For example, given the canonical reference `http://example.org/ValueSet/ABC|123`, this function returns `123`.
*/
define fluent function version(canonical FHIR.canonical):
  Split(canonical, '|').skip(1).first()

/*
@description: Returns any extensions defined on the given resource with the specified url
*/
define fluent function exts(domainResource DomainResource, url String):
  domainResource.extension E
    where E.url = url
    return E

/*
@description: Returns the single extension (if present) on the given resource with the specified url.
@comment: This function uses singleton from to ensure that a run-time exception is thrown if there
is more than one extension on the given resource with the specified url.
*/
define fluent function ext(domainResource DomainResource, url String):
  singleton from domainResource.exts(url)

/*
@description: Returns any extensions defined on the given element with the specified url.
*/
define fluent function exts(element Element, url String):
  element.extension E
    where E.url = url
    return E

/*
@description: Returns the single extension (if present) on the given element with the specified url.
@comment: This function uses singleton from to ensure that a run-time exception is thrown if there
is more than one extension on the given element with the specified url.
*/
define fluent function ext(element Element, url String):
  singleton from element.exts(url)

/*
@description: Returns any modifier extensions defined on the given resource with the specified url.
*/
define fluent function modifierExts(domainResource DomainResource, url String):
  domainResource.modifierExtension E
    where E.url = url
    return E

/*
@description: Returns the single modifier extension (if present) on the given resource with the specified url.
@comment: This function uses singleton from to ensure that a run-time exception is thrown if there
is more than one extension on the given resource with the specified url.
*/
define fluent function modifierExt(domainResource DomainResource, url String):
  singleton from domainResource.modifierExts(url)

/*
@description: Returns any modifier extensions defined on the given element with the specified url.
*/
define fluent function modifierExts(element BackboneElement, url String):
  element.modifierExtension E
    where E.url = url
    return E

/*
@description: Returns the single modifier extension (if present) on the given element with the specified url.
@comment: This function uses singleton from to ensure that a run-time exception is thrown if there
is more than one extension on the given element with the specified url.
*/
define fluent function modifierExt(element BackboneElement, url String):
  singleton from element.modifierExts(url)

/*
@description: Returns the birthTime of the patient, if present
@comment: This function returns the value of the birthTime extension, if present, null otherwise.
*/
define fluent function birthTime(patient Patient):
  patient.birthDate.ext('http://hl7.org/fhir/StructureDefinition/patient-birthTime').value as dateTime

/*
@description: Returns the birth date (and time if present) (as a DateTime)
@comment: This function returns the birthTime of the patient, if present, else the birthDate of the patient as a DateTime
*/
define fluent function birthDateTime(patient Patient):
  Coalesce(patient.birthTime().value, patient.birthDate.toDateTime())

/*
@description: Returns true if the given condition has the given category
*/
define fluent function hasCategory(condition FHIR.Condition, category Code):
  exists (condition.category C
    where C ~ category
  )

/*
@description: Returns true if the given condition is a problem list item.
*/
define fluent function isProblemListItem(condition FHIR.Condition):
  exists (condition.category C
    where C ~ "problem-list-item"
  )

/*
@description: Returns true if the given condition is an encounter diagnosis
*/
define fluent function isEncounterDiagnosis(condition FHIR.Condition):
  exists (condition.category C
    where C ~ "encounter-diagnosis"
  )

/*
@description: Returns an interval representing the normalized Abatement of a given Condition resource.
@comment: @comment: If the abatement element of the Condition is represented as a DateTime, the result
is an interval beginning and ending on that DateTime.
If the abatement is represented as a Quantity, the quantity is expected to be a calendar-duration and is interpreted as the age of the patient. The
result is an interval from the date the patient turned that age to immediately before one year later.
If the abatement is represented as a Quantity Interval, the quantities are expected to be calendar-durations and are interpreted as an age range during
which the abatement occurred. The result is an interval from the date the patient turned the starting age of the quantity interval, and ending immediately
before one year later than the date the patient turned the ending age of the quantity interval.

NOTE: Due to the complexity of determining an interval from a String, this function will throw
a run-time exception if used with a Condition instance that has a String as the abatement value.
*/
define fluent function abatementInterval(condition Condition):
  if condition.abatement is FHIR.dateTime then
    Interval[FHIRHelpers.ToDateTime(condition.abatement as FHIR.dateTime), FHIRHelpers.ToDateTime(condition.abatement as FHIR.dateTime)]
  else if condition.abatement is FHIR.Period then
    FHIRHelpers.ToInterval(condition.abatement as FHIR.Period)
  else if condition.abatement is FHIR.string then
    Message(null as Interval<DateTime>, true, 'NOT_IMPLEMENTED', 'Error', 'Calculation of an interval from a String value is not supported')
  else if condition.abatement is FHIR.Age then
    Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(condition.abatement as FHIR.Age),
      FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(condition.abatement as FHIR.Age) + 1 year)
  else if condition.abatement is FHIR.Range then
    Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity((condition.abatement as FHIR.Range).low),
      FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity((condition.abatement as FHIR.Range).high) + 1 year)
  else if condition.abatement is FHIR.boolean then
    Interval[end of condition.onset.toInterval(), condition.recordedDate)
  else 
    null

/*
@description: Returns an interval representing the normalized prevalence period of a given Condition resource.
@comment: Uses the toInterval and toAbatementInterval functions to determine the widest potential interval from
onset to abatement as specified in the given Condition.
*/
define fluent function prevalenceInterval(condition Condition):
if condition.clinicalStatus ~ "active"
  or condition.clinicalStatus ~ "recurrence"
  or condition.clinicalStatus ~ "relapse" then
  Interval[start of condition.onset.toInterval(), end of condition.abatementInterval()]
else
  (end of condition.abatementInterval()) abatementDate
    return 
	  if abatementDate is null then
        Interval[start of condition.onset.toInterval(), abatementDate)
      else
        Interval[start of condition.onset.toInterval(), abatementDate]

/*
@description: Returns true if the given condition has a clinical status of active, recurrence, or relapse
*/
define fluent function isActive(condition FHIR.Condition):
  condition.clinicalStatus ~ "active"
    or condition.clinicalStatus ~ "recurrence"
    or condition.clinicalStatus ~ "relapse"

/*
@description: Returns conditions in the given list that have a clinical status of active, recurrence, or relapse
*/
define fluent function active(conditions List<FHIR.Condition>):
  conditions C
    where C.clinicalStatus ~ "active"
      or C.clinicalStatus ~ "recurrence"
      or C.clinicalStatus ~ "relapse"

/*
@description: Returns true if the given condition either has no verification status or has a verification status of confirmed, unconfirmed, provisional, or differential
*/
define fluent function isVerified(condition FHIR.Condition):
  condition.verificationStatus is not null implies
    (condition.verificationStatus ~ "confirmed"
      or condition.verificationStatus ~ "unconfirmed"
      or condition.verificationStatus ~ "provisional"
      or condition.verificationStatus ~ "differential"
    )

/*
@description: Returns conditions in the given list that either have no verification status or have a verification status of confirmed, unconfirmed, provisional, or differential
*/
define fluent function verified(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus is not null implies
      (C.verificationStatus ~ "confirmed"
        or C.verificationStatus ~ "unconfirmed"
        or C.verificationStatus ~ "provisional"
        or C.verificationStatus ~ "differential"
      )

/*
@description: Returns true if the given condition has a verification status of unconfirmed
*/
define fluent function isUnconfirmed(condition FHIR.Condition):
  condition.verificationStatus ~ "unconfirmed"

/*
@description: Returns conditions in the given list that have a verification status of unconfirmed
*/
define fluent function unconfirmed(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus ~ "unconfirmed"

/*
@description: Returns true if the given condition has a verification status of provisional
*/
define fluent function isProvisional(condition FHIR.Condition):
  condition.verificationStatus ~ "provisional"

/*
@description: Returns conditions in the given list that have a verification status of provisional
*/
define fluent function provisional(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus ~ "provisional"

/*
@description: Returns true if the given condition has a verification status of differential
*/
define fluent function isDifferential(condition FHIR.Condition):
  condition.verificationStatus ~ "differential"

/*
@description: Returns conditions in the given list that have a verification status of differential
*/
define fluent function differential(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus ~ "differential"

/*
@description: Returns true if the given condition has a verification status of confirmed
*/
define fluent function isConfirmed(condition FHIR.Condition):
  condition.verificationStatus ~ "confirmed"

/*
@description: Returns conditions in the given list that have a verification status of confirmed
*/
define fluent function confirmed(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus ~ "confirmed"

/*
@description: Returns true if the given condition has a verification status of refuted
*/
define fluent function isRefuted(condition FHIR.Condition):
  condition.verificationStatus ~ "refuted"

/*
@description: Returns conditions in the given list that have a verification status of refuted
*/
define fluent function refuted(conditions List<FHIR.Condition>):
  conditions C
    where C.verificationStatus ~ "refuted"

/*
@description: Returns the abatement of the given AllergyIntolerance, if present
*/
define fluent function abatement(allergyIntolerance AllergyIntolerance):
  allergyIntolerance.ext('http://hl7.org/fhir/StructureDefinition/allergyintolerance-abatement').value
    as Choice<dateTime, Age, Period, Range, string>

/*
@description: Returns the resolutionAge of the given AllergyIntolerance, if present
*/
define fluent function resolutionAge(allergyIntolerance AllergyIntolerance):
  allergyIntolerance.ext('http://hl7.org/fhir/StructureDefinition/allergyintolerance-resolutionAge').value
    as Age

/*
@description: Returns an interval representing the normalized abatement of a given AllergyIntolerance resource.
@comment: This function uses the abatement extension, if present, otherwise the resolutionAge.
If the abatement of the AllergyIntolerance is a DateTime, the result is an interval beginning and ending on that DateTime.
If the abatement is a Period, the result is the Period converted to an Interval of DateTime.
If the abatement is an Age, the result is an interval from the date the patient turned that age to immediately before one year later.
If the abatement is a Range, the quantities are expected to be calendar-durations and are interpreted as an age range during
which the abatement occurred. The result is an interval from the date the patient turned the starting age of the quantity interval, and ending immediately
before one year later than the date the patient turned the ending age of the quantity interval.
If the resolutionAge is present, the result is an interval from the date the patient turned that age to immediately before one year later.

NOTE: Due to the complexity of determining an interval from a String, this function will throw
a run-time exception if used with a Condition instance that has a String as the abatement value.
*/
define fluent function abatementInterval(allergyIntolerance AllergyIntolerance):
  allergyIntolerance A
    let 
      abatement: A.abatement(),
      resolutionAge: A.resolutionAge()
    return
      if abatement is FHIR.dateTime then
        Interval[FHIRHelpers.ToDateTime(abatement as FHIR.dateTime), FHIRHelpers.ToDateTime(abatement as FHIR.dateTime)]
      else if abatement is FHIR.Period then
        FHIRHelpers.ToInterval(abatement as FHIR.Period)
      else if abatement is FHIR.string then
        Message(null as Interval<DateTime>, true, 'NOT_IMPLEMENTED', 'Error', 'Calculation of an interval from a String value is not supported')
      else if abatement is FHIR.Age then
        Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(abatement as FHIR.Age),
          FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(abatement as FHIR.Age) + 1 year)
      else if abatement is FHIR.Range then
        Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity((abatement as FHIR.Range).low),
          FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity((abatement as FHIR.Range).high) + 1 year)
      else if abatement is FHIR.boolean then
        Interval[end of A.onset.toInterval(), A.recordedDate)
      else if resolutionAge is not null then
        Interval[FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(resolutionAge),
          FHIRHelpers.ToDate(Patient.birthDate) + FHIRHelpers.ToQuantity(resolutionAge) + 1 year)
      else 
        null

/*
@description: Returns an interval representing the normalized prevalence period of a given Condition resource.
@comment: Uses the toInterval and toAbatementInterval functions to determine the widest potential interval from
onset to abatement as specified in the given Condition.
*/
define fluent function prevalenceInterval(allergyIntolerance AllergyIntolerance):
if allergyIntolerance.clinicalStatus ~ "allergy-active" then
  Interval[start of allergyIntolerance.onset.toInterval(), end of allergyIntolerance.abatementInterval()]
else
  (end of allergyIntolerance.abatementInterval()) abatementDate
    return 
      if abatementDate is null then
        Interval[start of allergyIntolerance.onset.toInterval(), abatementDate)
      else
        Interval[start of allergyIntolerance.onset.toInterval(), abatementDate]

/*
@description: Returns true if the given allergy has a clinical status of active
*/
define fluent function isActive(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.clinicalStatus ~ "allergy-active"

/*
@description: Returns allergies in the given list that have a clinical status of active
*/
define fluent function active(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.clinicalStatus ~ "allergy-active"

/*
@description: Returns true if the given condition has a clinical status of inactive
*/
define fluent function isInactive(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.clinicalStatus ~ "allergy-inactive"

/*
@description: Returns allergies in the given list that have a clinical status of inactive
*/
define fluent function inactive(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.clinicalStatus ~ "allergy-inactive"

/*
@description: Returns true if the given condition has a clinical status of resolved
*/
define fluent function isResolved(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.clinicalStatus ~ "allergy-resolved"

/*
@description: Returns allergies in the given list that have a clinical status of resolved
*/
define fluent function resolved(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.clinicalStatus ~ "allergy-resolved"

/*
@description: Returns true if the given condition either has no verification status or has a verification status of confirmed, unconfirmed, provisional, or differential
*/
define fluent function isVerified(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.verificationStatus is not null implies
    (allergyIntolerance.verificationStatus ~ "allergy-confirmed"
      or allergyIntolerance.verificationStatus ~ "allergy-unconfirmed"
    )

/*
@description: Returns conditions in the given list that either have no verification status or have a verification status of confirmed, unconfirmed, provisional, or differential
*/
define fluent function verified(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.verificationStatus is not null implies
      (A.verificationStatus ~ "allergy-confirmed"
        or A.verificationStatus ~ "allergy-unconfirmed"
      )

/*
@description: Returns true if the given condition has a verification status of confirmed
*/
define fluent function isConfirmed(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.verificationStatus ~ "allergy-confirmed"

/*
@description: Returns allergies in the given list that have a verification status of confirmed
*/
define fluent function confirmed(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.verificationStatus ~ "allergy-confirmed"

/*
@description: Returns true if the given condition has a verification status of unconfirmed
*/
define fluent function isUnconfirmed(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.verificationStatus ~ "allergy-unconfirmed"

/*
@description: Returns allergies in the given list that have a verification status of unconfirmed
*/
define fluent function unconfirmed(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.verificationStatus ~ "allergy-unconfirmed"

/*
@description: Returns true if the given condition has a verification status of refuted
*/
define fluent function isRefuted(allergyIntolerance FHIR.AllergyIntolerance):
  allergyIntolerance.verificationStatus ~ "allergy-refuted"

/*
@description: Returns allergies in the given list that have a verification status of refuted
*/
define fluent function refuted(allergyIntolerances List<FHIR.AllergyIntolerance>):
  allergyIntolerances A
    where A.verificationStatus ~ "allergy-refuted"

/*
@description: Returns true if the given observation has the given category
*/
define fluent function hasCategory(observation FHIR.Observation, category Code):
  exists (observation.category C
    where C ~ category
  )

/*
@description: Returns true if the given observation is a social history observation
*/
define fluent function isSocialHistory(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "social-history"
  )

/*
@description: Returns true if the given observation is a vital sign
*/
define fluent function isVitalSign(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "vital-signs"
  )

/*
@description: Returns true if the given observation is an imaging observation
*/
define fluent function isImaging(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "imaging"
  )

/*
@description: Returns true if the given observation is a laboratory observation
*/
define fluent function isLaboratory(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "laboratory"
  )

/*
@description: Returns true if the given observation is a procedure observation
*/
define fluent function isProcedure(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "procedure"
  )

/*
@description: Returns true if the given observation is a survey observation
*/
define fluent function isSurvey(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "survey"
  )

/*
@description: Returns true if the given observation is an exam observation
*/
define fluent function isExam(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "exam"
  )

/*
@description: Returns true if the given observation is a therapy observation
*/
define fluent function isTherapy(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "therapy"
  )

/*
@description: Returns true if the given observation is an activity observation
*/
define fluent function isActivity(observation FHIR.Observation):
  exists (observation.category C
    where C ~ "activity"
  )

/*
@description: Returns true if the given observation has status final, amended, or corrected
*/
define fluent function isResulted(observation FHIR.Observation):
  observation.status ~ "observation-final".code
    or observation.status ~ "observation-amended".code
    or observation.status ~ "observation-corrected".code

/*
@description: Returns observations in the given list with a status of final, amended, or corrected
*/
define fluent function resulted(observations List<FHIR.Observation>):
  observations observation
    where observation.status ~ "observation-final".code
      or observation.status ~ "observation-amended".code
      or observation.status ~ "observation-corrected".code

/*
@description: Returns true if the given observation has a status of final
*/
define fluent function isFinal(observation FHIR.Observation):
  observation.status ~ "observation-final".code

/*
@description: Returns observations in the given list with a status of final
*/
define fluent function final(observations List<FHIR.Observation>):
  observations observation
    where observation.status ~ "observation-final".code

/*
@description: Returns true if the given observation has a status of amended
*/
define fluent function isAmended(observation FHIR.Observation):
  observation.status ~ "observation-amended".code

/*
@description: Returns observations in the given list with a status of amended
*/
define fluent function amended(observations List<FHIR.Observation>):
  observations observation
    where observation.status ~ "observation-amended".code

/*
@description: Returns true if the given observation has a status of corrected
*/
define fluent function isCorrected(observation FHIR.Observation):
  observation.status ~ "observation-corrected".code

/*
@description: Returns observations in the given list with a status of corrected
*/
define fluent function corrected(observations List<FHIR.Observation>):
  observations observation
    where observation.status ~ "observation-corrected".code

/*
@description: Returns true if the given MedicationRequest has a category of Community
*/
define fluent function isCommunity(medicationRequest MedicationRequest):
  exists (medicationRequest.category C
    where C ~ Community
  )

/*
@description: Returns true if the given MedicationRequest has a category of Discharge
*/
define fluent function isDischarge(medicationRequest MedicationRequest):
  exists (medicationRequest.category C
    where C ~ Discharge
  )

/*
@description: Returns true if the given MedicationRequest has the given category
*/
define fluent function hasCategory(medicationRequest MedicationRequest, category Code):
  exists (medicationRequest.category C
    where C ~ category
  )

/*
@description: Returns the most recent Condition by recordedDate
*/
define fluent function mostRecent(conditions List<Condition>):
  Last(
    conditions C
      sort by recordedDate.value
  )

/*
@description: Returns the most recent Observation by issued
*/
define fluent function mostRecent(observations List<FHIR.Observation>):
  Last(
    observations O
      sort by issued.value
  )

/*
@description: Returns the most recent Procedure by the start of performed.toInterval()
*/
define fluent function mostRecent(procedures List<FHIR.Procedure>):
  Last(
    procedures P
      sort by start of performed.toInterval()
  )

/*
@description: Returns the most recent MedicationRequest by authoredOn
*/
define fluent function mostRecent(medicationRequests List<"MedicationRequest">):
  Last(
    medicationRequests MR
      sort by authoredOn.value
  )

/*
@description: Returns the most recent ServiceRequest by authoredOn
*/
define fluent function mostRecent(serviceRequests List<FHIR.ServiceRequest>):
  Last(
    serviceRequests SR
      sort by authoredOn.value
  )

/*
@description: Creates a list of integers from 1 to how many days are in the interval. Note, this wont create an index for
the final day if it is less than 24 hours. This also includes the first 24 hour period.
*/
define fluent function toDayNumbers(period Interval<DateTime>):
  ( expand { Interval[1, duration in days between start of period and end of period]} ) DayNumber
    return end of DayNumber

/*
@description: Creates a list of 24 hour long intervals in an interval paired with the index (1 indexed) to which 24 hour interval it is.
Note that the result will include intervals that are closed at the beginning and open at the end
*/
define fluent function daysInPeriod(period Interval<DateTime>):
  ( period.toDayNumbers() ) DayIndex
    let 
      startPeriod: start of period + (24 hours * (DayIndex - 1)),
      endPeriod: 
        if (hours between startPeriod and end of period < 24) then 
          startPeriod
        else 
          start of period + (24 hours * DayIndex)
    return Tuple {
      dayIndex: DayIndex,
      dayPeriod: Interval[startPeriod, endPeriod)
    }
