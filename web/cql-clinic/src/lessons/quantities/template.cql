library Quantities version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

// Quantities carry their units everywhere: number, space, quoted UCUM unit.

define "Dose Literal": 5 'mg'
// TODO: "Unit Aware Equality" must prove 1 'g' equals 1000 'mg'
// TODO: "Unit Aware Ordering" must prove 180 'cm' is less than 2 'm'
// TODO: "Same Unit Sum" must add 5 'mg' + 5 'mg'
// TODO: "Cross Unit Sum" must add 1 'g' + 500 'mg' (watch the result unit!)
// TODO: "Scalar Multiply" must compute 5 'mg' times 2
// TODO: "Quantity As String" must render 5 'mg' via ToString
// TODO: "Quantity Value" must project the numeric value of (5 'mg')
// TODO: "Quantity Unit" must project the unit of (5 'mg')
// TODO: "Temperature Compare" must prove 37 'Cel' > 30 'Cel'
//   (Celsius uses the UCUM code Cel)
// TODO: "Calendar Duration Compare" must prove 1 year > 11 months
// TODO: "Dose In Range" must test 7.5 'mg' between 5 'mg' and 10 'mg'
