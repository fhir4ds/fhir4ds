library TestMedicationUnion

using QICore version '6.0.0'

include FHIRHelpers version '4.4.000'

context Patient

define Test:
  (
    [MedicationAdministrationNotDone] M
        return {
            id: M.id,
            statusReason: M.statusReason,
            authoredOn: M.recorded
        }
  )
  union (
    [MedicationNotRequested] M
        return {
            id: M.id,
            statusReason: M.reasonCode,
            authoredOn: M.authoredOn
        }
  )
  union (
    from 
      [MedicationRequest] M,
      [TaskRejected] T
    return {
        id: M.id,
        statusReason: { T.statusReason },
        authoredOn: M.authoredOn
    }
  )