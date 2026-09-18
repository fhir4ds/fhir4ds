WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Condition" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource FROM resources r WHERE r.resourceType = 'Condition'
),
"Observation" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'effective') AS effective, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.start'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_start, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.end'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_end, fhirpath_text(r.resource, 'status') AS status, fhirpath_text(r.resource, 'valueQuantity.value') AS value_quantity FROM resources r WHERE r.resourceType = 'Observation'
),
"Avg Value" AS (
SELECT _pt.patient_id, (SELECT AVG(TRY_CAST(_val AS DOUBLE)) FROM (SELECT O.value_quantity AS _val FROM "Observation" AS O WHERE O.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"BP With Let" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Observation" AS O WHERE CQLListContainsEq(from_json(fhirpath(O.resource, 'code.coding.code'), '["VARCHAR"]'), '8480-6') AND O.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"Distinct Statuses" AS (
SELECT _pt.patient_id, (SELECT COUNT(DISTINCT _val) FROM (SELECT O.status AS _val FROM "Observation" AS O WHERE O.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"Earliest Obs Id" AS (
SELECT _pt.patient_id, (SELECT fhirpath_text(O.resource, 'id') FROM "Observation" AS O WHERE O.patient_id = _pt.patient_id ORDER BY CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END ASC NULLS LAST, json_extract_string(O.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"Final Obs Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Observation" AS O WHERE O.status = 'final' AND O.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"First Tuple" AS (
SELECT _pt.patient_id, (SELECT json_object('id', fhirpath_text(O.resource, 'id'), 'status', O.status) FROM "Observation" AS O WHERE O.patient_id = _pt.patient_id ORDER BY json_extract_string(O.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"High Final Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Observation" AS O WHERE O.status = 'final' AND TRY_CAST(cql_quantity_value(O.value_quantity) AS DOUBLE) > 100 AND O.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"Max Value" AS (
SELECT _pt.patient_id, (SELECT MAX(_val) FROM (SELECT O.value_quantity AS _val FROM "Observation" AS O WHERE O.value_quantity IS NOT NULL AND O.patient_id = _pt.patient_id) AS _agg) AS resource FROM _patients AS _pt
),
"Singleton Value" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN TRY_CAST((SELECT COUNT(*) FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'id') = 'obs-2' AND O.patient_id = _pt.patient_id) AS DOUBLE) = 1 THEN (SELECT O.value_quantity FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'id') = 'obs-2' AND O.patient_id = _pt.patient_id LIMIT 1) ELSE NULL END) AS value FROM _patients AS _pt
),
"Union Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(*) FROM (SELECT patient_id, resource FROM "Observation" UNION ALL SELECT patient_id, resource FROM "Condition") AS _agg_src WHERE _agg_src.patient_id = _pt.patient_id) AS value FROM _patients AS _pt
)
SELECT _pt.patient_id, "Avg Value".value AS "Avg Value", "BP With Let".value AS "BP With Let", "Distinct Statuses".value AS "Distinct Statuses", "Earliest Obs Id".resource AS "Earliest Obs Id", "Final Obs Count".value AS "Final Obs Count", "First Tuple".resource AS "First Tuple", "High Final Count".value AS "High Final Count", "Max Value".resource AS "Max Value", "Singleton Value".value AS "Singleton Value", "Union Count".value AS "Union Count" FROM _patients _pt LEFT JOIN "Avg Value" ON _pt.patient_id = "Avg Value".patient_id LEFT JOIN "BP With Let" ON _pt.patient_id = "BP With Let".patient_id LEFT JOIN "Distinct Statuses" ON _pt.patient_id = "Distinct Statuses".patient_id LEFT JOIN "Earliest Obs Id" ON _pt.patient_id = "Earliest Obs Id".patient_id LEFT JOIN "Final Obs Count" ON _pt.patient_id = "Final Obs Count".patient_id LEFT JOIN "First Tuple" ON _pt.patient_id = "First Tuple".patient_id LEFT JOIN "High Final Count" ON _pt.patient_id = "High Final Count".patient_id LEFT JOIN "Max Value" ON _pt.patient_id = "Max Value".patient_id LEFT JOIN "Singleton Value" ON _pt.patient_id = "Singleton Value".patient_id LEFT JOIN "Union Count" ON _pt.patient_id = "Union Count".patient_id ORDER BY _pt.patient_id ASC