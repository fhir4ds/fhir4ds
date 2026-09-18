library Quantities version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "Dose Literal": 5 'mg'
define "Unit Aware Equality": 1 'g' = 1000 'mg'
define "Unit Aware Ordering": 180 'cm' < 2 'm'
define "Same Unit Sum": 5 'mg' + 5 'mg'
define "Cross Unit Sum": 1 'g' + 500 'mg'
define "Scalar Multiply": 5 'mg' * 2
define "Quantity As String": ToString(5 'mg')
define "Quantity Value": (5 'mg').value
define "Quantity Unit": (5 'mg').unit
define "Temperature Compare": 37 'Cel' > 30 'Cel'
define "Calendar Duration Compare": 1 year > 11 months
define "Dose In Range": 7.5 'mg' between 5 'mg' and 10 'mg'
