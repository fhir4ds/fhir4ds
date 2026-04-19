library TestContext

using FHIR version '4.0.1'

//parameter "%context" FHIR.QuestionnaireResponse.Item
//parameter "%qitem" FHIR.Questionnaire.Item

context Patient

define TestContext: %context

//define TestListEntry: FHIR.Observation.Component { value: string { value: '123' } }
//define TestContext: List { entry: List { List.Entry { item: Reference { reference: { string: { value: 'Patient/123' } } } } } }
