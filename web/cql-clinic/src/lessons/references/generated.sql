WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"MedicationRequest" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'MedicationRequest' AND (json_extract(r.resource, '$.meta.profile') IS NULL OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationnotrequested'))
),
"Active Request Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "MedicationRequest" AS R WHERE R.status = 'active' AND R.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"All Request Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(*) FROM "MedicationRequest" AS _agg_src WHERE _agg_src.patient_id = _pt.patient_id) AS value FROM _patients AS _pt
),
"On Ibuprofen" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "MedicationRequest" AS R WHERE R.status = 'active' AND fhirpath_text(resolve(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END), 'code.coding.code') = '5640' AND fhirpath_text(resolve(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END), 'code.coding.system') = 'http://www.nlm.nih.gov/research/umls/rxnorm' AND R.patient_id = _pt.patient_id)
),
"Reference String" AS (
SELECT _pt.patient_id, (SELECT fhirpath_text(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END, 'reference') FROM "MedicationRequest" AS R WHERE R.status = 'active' AND R.patient_id = _pt.patient_id ORDER BY json_extract_string(R.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"Referenced Med Id" AS (
SELECT _pt.patient_id, (SELECT LIST_EXTRACT(STR_SPLIT(fhirpath_text(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END, 'reference'), '/'), -1) FROM "MedicationRequest" AS R WHERE R.status = 'active' AND R.patient_id = _pt.patient_id ORDER BY json_extract_string(R.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"Resolved Med Code" AS (
SELECT _pt.patient_id, (SELECT fhirpath_text(CASE WHEN fhirpath_text(resolve(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END), 'code.coding.system') = 'http://www.nlm.nih.gov/research/umls/rxnorm' THEN fhirpath_text(resolve(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END), 'code.coding') ELSE NULL END, 'code') FROM "MedicationRequest" AS R WHERE R.status = 'active' AND R.patient_id = _pt.patient_id ORDER BY json_extract_string(R.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"Dangling Reference" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE TRY_CAST((SELECT sub.value FROM "Active Request Count" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) AS DOUBLE) > 0 AND (SELECT sub.resource FROM "Resolved Med Code" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) IS NULL
),
"Uses Medication Reference" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "MedicationRequest" AS R WHERE R.status = 'active' AND StartsWith(fhirpath_text(CASE WHEN fhirpath_text(R.resource, '(medication).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(R.resource, '(medication).type().name') AS VARCHAR)) = 'reference' THEN fhirpath_text(R.resource, 'medication') ELSE NULL END, 'reference'), 'Medication/') AND R.patient_id = _pt.patient_id)
)
SELECT _pt.patient_id, "Active Request Count".value AS "Active Request Count", "All Request Count".value AS "All Request Count", (SELECT CASE WHEN "On Ibuprofen".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "On Ibuprofen", "Reference String".resource AS "Reference String", "Referenced Med Id".resource AS "Referenced Med Id", "Resolved Med Code".resource AS "Resolved Med Code", (SELECT CASE WHEN "Dangling Reference".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Dangling Reference", (SELECT CASE WHEN "Uses Medication Reference".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Uses Medication Reference" FROM _patients _pt LEFT JOIN "Active Request Count" ON _pt.patient_id = "Active Request Count".patient_id LEFT JOIN "All Request Count" ON _pt.patient_id = "All Request Count".patient_id LEFT JOIN "On Ibuprofen" ON _pt.patient_id = "On Ibuprofen".patient_id LEFT JOIN "Reference String" ON _pt.patient_id = "Reference String".patient_id LEFT JOIN "Referenced Med Id" ON _pt.patient_id = "Referenced Med Id".patient_id LEFT JOIN "Resolved Med Code" ON _pt.patient_id = "Resolved Med Code".patient_id LEFT JOIN "Dangling Reference" ON _pt.patient_id = "Dangling Reference".patient_id LEFT JOIN "Uses Medication Reference" ON _pt.patient_id = "Uses Medication Reference".patient_id ORDER BY _pt.patient_id ASC