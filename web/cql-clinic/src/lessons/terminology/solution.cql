library Terminology version '1.0.0'

using FHIR version '4.0.1'

include FHIRHelpers version '4.0.1' called FHIRHelpers

context Patient

codesystem "SNOMED": 'http://snomed.info/sct'
codesystem "ICD10CM": 'http://hl7.org/fhir/sid/icd-10-cm'

code "Diabetes SNOMED": '44054006' from "SNOMED" display 'Diabetes mellitus'
code "T2DM ICD": 'E11.9' from "ICD10CM" display 'Type 2 diabetes'

define "Has SNOMED Diabetes":
  exists([Condition] C where exists(C.code.coding cod where cod.code = "Diabetes SNOMED".code and cod.system = "Diabetes SNOMED".system))
define "Has ICD T2DM":
  exists([Condition] C where exists(C.code.coding cod where cod.code = "T2DM ICD".code and cod.system = "T2DM ICD".system))
define "SNOMED Condition Count":
  Count([Condition] C where exists(C.code.coding cod where cod.system = 'http://snomed.info/sct'))
define "ICD Condition Count":
  Count([Condition] C where exists(C.code.coding cod where cod.system = 'http://hl7.org/fhir/sid/icd-10-cm'))
define "First SNOMED Display":
  First([Condition] C where exists(C.code.coding cod where cod.system = 'http://snomed.info/sct') return First(C.code.coding).display)
define "Declared Code Display": "Diabetes SNOMED".display
define "Diabetes By Any System":
  exists([Condition] C where C.code.coding.code contains "Diabetes SNOMED".code)
define "Codings Per Condition":
  Count([Condition] C return Count(C.code.coding))
define "Has Hypertension":
  exists([Condition] C where exists(C.code.coding cod where cod.code = '38341003' and cod.system = 'http://snomed.info/sct'))
