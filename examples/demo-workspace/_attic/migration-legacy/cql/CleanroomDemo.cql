library CleanroomDemo version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

define "Initial Population":
  Patient.gender = 'female'

define "Has Name":
  Patient.name.first().given.first() is not null
