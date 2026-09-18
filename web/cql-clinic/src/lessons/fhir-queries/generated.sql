WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id, (SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1) AS patient_resource, CAST(fhirpath_date((SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1), 'birthDate') AS VARCHAR) AS birth_date FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Observation" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, COALESCE(fhirpath_text(r.resource, 'category.coding.code'), fhirpath_text(r.resource, 'code.coding.code')) AS code, fhirpath_text(r.resource, 'effective') AS effective, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.start'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_start, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.end'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_end, fhirpath_text(r.resource, 'status') AS status, fhirpath_text(r.resource, 'valueQuantity.value') AS value_quantity FROM resources r WHERE r.resourceType = 'Observation'
),
"MedicationRequest" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'intent') AS intent, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'MedicationRequest' AND (json_extract(r.resource, '$.meta.profile') IS NULL OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationnotrequested'))
),
"Condition" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource FROM resources r WHERE r.resourceType = 'Condition'
),
"Active Med Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "MedicationRequest" AS MR WHERE MR.status = 'active' AND MR.intent = 'order' AND MR.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"Full Name" AS (
SELECT _pt.patient_id, fhirpath_text(fhirpath_text(_pt.patient_resource, 'name'), 'given') || ' ' || fhirpath_text(fhirpath_text(_pt.patient_resource, 'name'), 'family') AS resource FROM _patients AS _pt
),
"Has Diabetes" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.code') = '44054006' AND C.patient_id = _pt.patient_id)
),
"Is Male" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE fhirpath_text(_pt.patient_resource, 'gender') = 'male'
),
"Lab Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'category.coding.code') = 'laboratory' AND O.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"Observation Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(*) FROM "Observation" AS _agg_src WHERE _agg_src.patient_id = _pt.patient_id) AS value FROM _patients AS _pt
),
"Systolic BP" AS (
SELECT _pt.patient_id, (SELECT O.value_quantity FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'code.coding.code') = '8480-6' AND O.patient_id = _pt.patient_id ORDER BY json_extract_string(O.resource, '$.id') ASC NULLS LAST LIMIT 1) AS value FROM _patients AS _pt
)
SELECT _pt.patient_id, "Active Med Count".value AS "Active Med Count", "Full Name".resource AS "Full Name", (SELECT CASE WHEN "Has Diabetes".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Has Diabetes", (SELECT CASE WHEN "Is Male".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Is Male", "Lab Count".value AS "Lab Count", "Observation Count".value AS "Observation Count", "Systolic BP".value AS "Systolic BP" FROM _patients _pt LEFT JOIN "Active Med Count" ON _pt.patient_id = "Active Med Count".patient_id LEFT JOIN "Full Name" ON _pt.patient_id = "Full Name".patient_id LEFT JOIN "Has Diabetes" ON _pt.patient_id = "Has Diabetes".patient_id LEFT JOIN "Is Male" ON _pt.patient_id = "Is Male".patient_id LEFT JOIN "Lab Count" ON _pt.patient_id = "Lab Count".patient_id LEFT JOIN "Observation Count" ON _pt.patient_id = "Observation Count".patient_id LEFT JOIN "Systolic BP" ON _pt.patient_id = "Systolic BP".patient_id ORDER BY _pt.patient_id ASC