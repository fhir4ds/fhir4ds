library CleanroomDemo version '1.1.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

valueset "Demo Mammography": 'http://example.org/demo/mammography'

context Patient

define "Initial Population":
  Patient.gender = 'female'

define "Has Name":
  Patient.name.first().given.first() is not null

// S26 (item 10): one define using a workspace VALUESER (local file under
// ValueSet/) — retrieve membership flows through the workspace
// terminology the kernel loads (same path the CMS example workspaces
// use; p1 carries a LOINC mammography Observation).
define "Has Screening Mammogram":
  exists([Observation: "Demo Mammography"])
