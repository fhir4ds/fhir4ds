WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id, (SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1) AS patient_resource, CAST(fhirpath_date((SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1), 'birthDate') AS VARCHAR) AS birth_date FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Condition" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource FROM resources r WHERE r.resourceType = 'Condition'
),
"Encounter" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'period') AS period, json_extract_string(r.resource, '$.period.start') AS period_start, json_extract_string(r.resource, '$.period.end') AS period_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Encounter'
),
"Observation" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'effective') AS effective, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.start'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_start, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.end'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Observation'
),
"Has Diabetes" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Condition" AS C WHERE fhirpath_text(C.resource, 'code.coding.code') = '44054006' AND fhirpath_text(C.resource, 'code.coding.system') = 'http://snomed.info/sct' AND C.patient_id = _pt.patient_id)
),
"Measurement Period" AS (
SELECT _pt.patient_id, intervalFromBounds('2024-01-01', '2024-12-31', TRUE, TRUE) AS value FROM _patients AS _pt
),
"Age At Start" AS (
SELECT _pt.patient_id, CalculateAgeInYearsAt(CAST(_pt.birth_date AS VARCHAR), CAST(intervalStart((SELECT sub.value FROM "Measurement Period" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1)) AS VARCHAR)) AS resource FROM _patients AS _pt
),
"Had Office Visit" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Encounter" AS E WHERE fhirpath_text(E.resource, 'class.code') = 'AMB' AND intervalIncludes((SELECT sub.value FROM "Measurement Period" AS sub WHERE sub.patient_id = E.patient_id LIMIT 1), E.period) AND E.patient_id = _pt.patient_id)
),
"Has Recent A1c" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'code.coding.code') = '4548-4' AND fhirpath_text(O.resource, 'code.coding.system') = 'http://loinc.org' AND intervalContains((SELECT sub.value FROM "Measurement Period" AS sub WHERE sub.patient_id = O.patient_id LIMIT 1), CAST(CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END AS VARCHAR)) AND O.patient_id = _pt.patient_id)
),
"In Hospice" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Encounter" AS E WHERE fhirpath_text(E.resource, 'class.code') = 'HH' AND intervalIncludes((SELECT sub.value FROM "Measurement Period" AS sub WHERE sub.patient_id = E.patient_id LIMIT 1), E.period) AND E.patient_id = _pt.patient_id)
),
"Initial Population" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Has Diabetes" AS sub WHERE sub.patient_id = _pt.patient_id) AND CASE WHEN (SELECT sub.resource FROM "Age At Start" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) IS NULL OR 18 IS NULL OR 75 IS NULL THEN NULL ELSE TRY_CAST((SELECT sub.resource FROM "Age At Start" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) AS DOUBLE) >= 18 AND TRY_CAST((SELECT sub.resource FROM "Age At Start" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) AS DOUBLE) <= 75 END
),
"Denominator" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Initial Population" AS sub WHERE sub.patient_id = _pt.patient_id) AND EXISTS (SELECT 1 FROM "Had Office Visit" AS sub WHERE sub.patient_id = _pt.patient_id)
),
"Denominator Exclusion" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Denominator" AS sub WHERE sub.patient_id = _pt.patient_id) AND EXISTS (SELECT 1 FROM "In Hospice" AS sub WHERE sub.patient_id = _pt.patient_id)
),
"Numerator" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Denominator" AS sub WHERE sub.patient_id = _pt.patient_id) AND NOT EXISTS (SELECT 1 FROM "Denominator Exclusion" AS sub WHERE sub.patient_id = _pt.patient_id) AND EXISTS (SELECT 1 FROM "Has Recent A1c" AS sub WHERE sub.patient_id = _pt.patient_id)
)
SELECT _pt.patient_id, (SELECT CASE WHEN "Has Diabetes".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Has Diabetes", "Measurement Period".value AS "Measurement Period", "Age At Start".resource AS "Age At Start", (SELECT CASE WHEN "Had Office Visit".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Had Office Visit", (SELECT CASE WHEN "Has Recent A1c".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Has Recent A1c", (SELECT CASE WHEN "In Hospice".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "In Hospice", (SELECT CASE WHEN "Initial Population".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Initial Population", (SELECT CASE WHEN "Denominator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS Denominator, (SELECT CASE WHEN "Denominator Exclusion".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Denominator Exclusion", (SELECT CASE WHEN "Numerator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS Numerator FROM _patients _pt LEFT JOIN "Has Diabetes" ON _pt.patient_id = "Has Diabetes".patient_id LEFT JOIN "Measurement Period" ON _pt.patient_id = "Measurement Period".patient_id LEFT JOIN "Age At Start" ON _pt.patient_id = "Age At Start".patient_id LEFT JOIN "Had Office Visit" ON _pt.patient_id = "Had Office Visit".patient_id LEFT JOIN "Has Recent A1c" ON _pt.patient_id = "Has Recent A1c".patient_id LEFT JOIN "In Hospice" ON _pt.patient_id = "In Hospice".patient_id LEFT JOIN "Initial Population" ON _pt.patient_id = "Initial Population".patient_id LEFT JOIN "Denominator" ON _pt.patient_id = "Denominator".patient_id LEFT JOIN "Denominator Exclusion" ON _pt.patient_id = "Denominator Exclusion".patient_id LEFT JOIN "Numerator" ON _pt.patient_id = "Numerator".patient_id ORDER BY _pt.patient_id ASC