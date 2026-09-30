library Status version '1.13.000'

using QICore version '6.0.0'

include FHIRHelpers version '4.4.000' called FHIRHelpers

codesystem "ObservationCategoryCodes": 'http://terminology.hl7.org/CodeSystem/observation-category'

code "exam": 'exam' from "ObservationCategoryCodes" display 'exam'
code "imaging": 'imaging' from "ObservationCategoryCodes" display 'imaging'

context Patient

//This library contains functions used to constrain FHIR resource elements for measures authored by NCQA, based on QICore 6.0.0 resources including IG and authoring patterns. The functions may appear similar to some QICoreCommon functions but differ in that they have constraints that are relevant for measures authored by NCQA.

//Assessment, Performed
define fluent function isAssessmentPerformed(Obs List<ObservationScreeningAssessment>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }

//Device, Order - Personal Use Devices
define fluent function isDeviceOrder(DeviceRequest List<DeviceRequest>):
  DeviceRequest D
    where D.status in { 'active', 'completed' }
      and D.intent = 'order'

//Diagnostic Study, Order
define fluent function isDiagnosticStudyOrder(ServiceRequest List<ServiceRequest>):
  ServiceRequest S
    where S.status in { 'active', 'completed' }
      and S.intent = 'order'
      
//Intervention, Order
define fluent function isInterventionOrder(ServiceRequest List<ServiceRequest>):
  ServiceRequest S
    where S.status in { 'active', 'completed' }
      and S.intent = 'order'    

//Laboratory Test, Order
define fluent function isLaboratoryTestOrder(ServiceRequest List<ServiceRequest>):
  ServiceRequest S
    where S.status in { 'active', 'completed' }
      and S.intent = 'order'        

//Diagnostic Study, Performed
define fluent function isDiagnosticStudyPerformed(Obs List<ObservationClinicalResult>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }
        and exists ( O.category ObservationCategory
        where ( ObservationCategory ) ~ "imaging"
    )
    
//Encounter, Performed
//General usage unless required otherwise by measure intent (e.g., follow-up encounters)
define fluent function isEncounterPerformed(Enc List<Encounter>):
  Enc E
    where E.status in {'finished', 'arrived', 'triaged', 'in-progress', 'onleave'}

//Immunization, Administered
define fluent function isImmunizationAdministered(Immunization List<Immunization>):
  Immunization I
    where I.status ~ 'completed'

//Intervention, Performed
define fluent function isInterventionPerformed(Proc List<Procedure>):
  Proc P
    where P.status ~ 'completed'

//Procedure, Performed
define fluent function isProcedurePerformed(Proc List<Procedure>):
  Proc P
    where P.status ~ 'completed'

//Laboratory Test, Performed
define fluent function isLaboratoryTestPerformed(Obs List<LaboratoryResultObservation>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }

//Medication, Active
define fluent function isMedicationActive(MedicationRequest List<MedicationRequest>):
  MedicationRequest M
    where M.status = 'active'
      and M.intent = 'order'

//Medication, Dispensed
define fluent function isMedicationDispensed(Med List<MedicationDispense>):
  Med M
    where M.status in { 'completed', 'in-progress', 'on-hold' }

//Medication, Order
define fluent function isMedicationOrder(MedicationRequest List<MedicationRequest>):
  MedicationRequest M
    where M.status in { 'active', 'completed' }
      and M.intent = 'order'

//Physical Exam, Performed
define fluent function isPhysicalExamPerformed(Obs List<ObservationClinicalResult>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }
      and exists ( O.category ObservationCategory
          where ( ObservationCategory ) ~ "exam"
      )

//Observation Vital Signs
define fluent function isObservationBP(Obs List<USCoreBloodPressureProfile>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }
      
define fluent function isObservationBodyHeight(Obs List<USCoreBodyHeightProfile>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }
      
define fluent function isObservationBodyWeight(Obs List<USCoreBodyWeightProfile>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }
      
define fluent function isObservationBMI(Obs List<USCoreBMIProfile>):
  Obs O
    where O.status in { 'final', 'amended', 'corrected' }
    
//Observation Smoking Status
define fluent function isObservationSmokingStatus(Obs List<USCoreSmokingStatusProfile>):
  Obs O
    where O.status = 'final' 

//Symptom
define fluent function isSymptom(Obs List<SimpleObservation>):
  Obs O
    where O.status in { 'preliminary', 'final', 'amended', 'corrected' }