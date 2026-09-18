WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Condition" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource FROM resources r WHERE r.resourceType = 'Condition'
),
"Codings Per Condition" AS (
SELECT _pt.patient_id, len(list_filter(COALESCE((SELECT list(_val) FROM (SELECT array_length(fhirpath(C.resource, 'code.coding')) AS _val FROM "Condition" AS C WHERE C.patient_id = _pt.patient_id) AS _agg), []), _v -> _v IS NOT NULL)) AS value FROM _patients AS _pt
),
"Declared Code Display" AS (
SELECT _pt.patient_id, 'Diabetes mellitus' AS resource FROM _patients AS _pt
),
"Diabetes By Any System" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Condition" AS C WHERE CQLListContainsEq(from_json(fhirpath(C.resource, 'code.coding.code'), '["VARCHAR"]'), '44054006') AND C.patient_id = _pt.patient_id)
),
"First SNOMED Display" AS (
SELECT _pt.patient_id, (SELECT fhirpath_text(LIST_EXTRACT(from_json(fhirpath(C.resource, 'code.coding'), '["VARCHAR"]'), 1), 'display') FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.system') = 'http://snomed.info/sct' AND C.patient_id = _pt.patient_id ORDER BY json_extract_string(C.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"Has Hypertension" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.code') = '38341003' AND fhirpath_text(C.resource, 'code.coding.system') = 'http://snomed.info/sct' AND C.patient_id = _pt.patient_id)
),
"Has ICD T2DM" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.code') = 'E11.9' AND fhirpath_text(C.resource, 'code.coding.system') = 'http://hl7.org/fhir/sid/icd-10-cm' AND C.patient_id = _pt.patient_id)
),
"Has SNOMED Diabetes" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.code') = '44054006' AND fhirpath_text(C.resource, 'code.coding.system') = 'http://snomed.info/sct' AND C.patient_id = _pt.patient_id)
),
"ICD Condition Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.system') = 'http://hl7.org/fhir/sid/icd-10-cm' AND C.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"SNOMED Condition Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.system') = 'http://snomed.info/sct' AND C.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
)
SELECT _pt.patient_id, "Codings Per Condition".value AS "Codings Per Condition", "Declared Code Display".resource AS "Declared Code Display", (SELECT CASE WHEN "Diabetes By Any System".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Diabetes By Any System", "First SNOMED Display".resource AS "First SNOMED Display", (SELECT CASE WHEN "Has Hypertension".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Has Hypertension", (SELECT CASE WHEN "Has ICD T2DM".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Has ICD T2DM", (SELECT CASE WHEN "Has SNOMED Diabetes".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Has SNOMED Diabetes", "ICD Condition Count".value AS "ICD Condition Count", "SNOMED Condition Count".value AS "SNOMED Condition Count" FROM _patients _pt LEFT JOIN "Codings Per Condition" ON _pt.patient_id = "Codings Per Condition".patient_id LEFT JOIN "Declared Code Display" ON _pt.patient_id = "Declared Code Display".patient_id LEFT JOIN "Diabetes By Any System" ON _pt.patient_id = "Diabetes By Any System".patient_id LEFT JOIN "First SNOMED Display" ON _pt.patient_id = "First SNOMED Display".patient_id LEFT JOIN "Has Hypertension" ON _pt.patient_id = "Has Hypertension".patient_id LEFT JOIN "Has ICD T2DM" ON _pt.patient_id = "Has ICD T2DM".patient_id LEFT JOIN "Has SNOMED Diabetes" ON _pt.patient_id = "Has SNOMED Diabetes".patient_id LEFT JOIN "ICD Condition Count" ON _pt.patient_id = "ICD Condition Count".patient_id LEFT JOIN "SNOMED Condition Count" ON _pt.patient_id = "SNOMED Condition Count".patient_id ORDER BY _pt.patient_id ASC