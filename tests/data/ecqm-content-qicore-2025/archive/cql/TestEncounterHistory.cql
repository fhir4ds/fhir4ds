library TestEncounterHistory

using QICore version '6.0.0'

include QICoreCommon

valueset "Diabetes": 'TBD'

context Patient

// Update the Patterns discussion to use this approach:
// https://github.com/cqframework/CQL-Formatting-and-Usage-Wiki/wiki/Authoring-Patterns-QICore-v6.0.0#encounters-with-a-condition
define "Encounters with a Diabetes Condition":
  [Encounter] CompletedEncounter
    where CompletedEncounter.reasonCode in "Diabetes"
      or exists (
        [ConditionEncounterDiagnosis: "Diabetes"] DiabetesCondition
          where CompletedEncounter.reasonReference.references(DiabetesCondition)
      )
