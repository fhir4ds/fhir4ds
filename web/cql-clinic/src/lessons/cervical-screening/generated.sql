WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id, (SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1) AS patient_resource, CAST(fhirpath_date((SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1), 'birthDate') AS VARCHAR) AS birth_date FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Encounter" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'period') AS period, json_extract_string(r.resource, '$.period.start') AS period_start, json_extract_string(r.resource, '$.period.end') AS period_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Encounter'
),
"Observation" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'effective') AS effective, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.start'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_start, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.end'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Observation'
),
"Procedure" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'performed') AS performed, COALESCE(json_extract_string(r.resource, '$.performedPeriod.start'), json_extract_string(r.resource, '$.performedDateTime'), json_extract_string(r.resource, '$.performedDate'), json_extract_string(r.resource, '$.performedInstant')) AS performed_start, COALESCE(json_extract_string(r.resource, '$.performedPeriod.end'), json_extract_string(r.resource, '$.performedDateTime'), json_extract_string(r.resource, '$.performedDate'), json_extract_string(r.resource, '$.performedInstant')) AS performed_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Procedure' AND (fhirpath_text(r.resource, 'status') IS NULL OR fhirpath_text(r.resource, 'status') != 'not-done') AND (json_extract(r.resource, '$.meta.profile') IS NULL OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))
),
"Cytology Lookback" AS (
SELECT _pt.patient_id, intervalFromBounds('2022-01-01', '2024-12-31', TRUE, TRUE) AS value FROM _patients AS _pt
),
"HPV Lookback" AS (
SELECT _pt.patient_id, intervalFromBounds('2020-01-01', '2024-12-31', TRUE, TRUE) AS value FROM _patients AS _pt
),
"Had Hysterectomy" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Procedure" AS P WHERE fhirpath_text(P.resource, 'code.coding.code') = '116140006' AND fhirpath_text(P.resource, 'code.coding.system') = 'http://snomed.info/sct' AND P.patient_id = _pt.patient_id)
),
"Had Recent Cytology" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'code.coding.code') = '10524-7' AND fhirpath_text(O.resource, 'code.coding.system') = 'http://loinc.org' AND intervalContains((SELECT sub.value FROM "Cytology Lookback" AS sub WHERE sub.patient_id = O.patient_id LIMIT 1), CAST(CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END AS VARCHAR)) AND O.patient_id = _pt.patient_id)
),
"Had Recent HPV" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Observation" AS O WHERE fhirpath_text(O.resource, 'code.coding.code') = '21440-3' AND fhirpath_text(O.resource, 'code.coding.system') = 'http://loinc.org' AND intervalContains((SELECT sub.value FROM "HPV Lookback" AS sub WHERE sub.patient_id = O.patient_id LIMIT 1), CAST(CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END AS VARCHAR)) AND O.patient_id = _pt.patient_id)
),
"Is Female" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE fhirpath_text(_pt.patient_resource, 'gender') = 'female'
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
"In Hospice" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT * FROM "Encounter" AS E WHERE fhirpath_text(E.resource, 'class.code') = 'HH' AND intervalIncludes((SELECT sub.value FROM "Measurement Period" AS sub WHERE sub.patient_id = E.patient_id LIMIT 1), E.period) AND E.patient_id = _pt.patient_id)
),
"Initial Population" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Is Female" AS sub WHERE sub.patient_id = _pt.patient_id) AND CASE WHEN (SELECT sub.resource FROM "Age At Start" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) IS NULL OR 23 IS NULL OR 64 IS NULL THEN NULL ELSE TRY_CAST((SELECT sub.resource FROM "Age At Start" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) AS DOUBLE) >= 23 AND TRY_CAST((SELECT sub.resource FROM "Age At Start" AS sub WHERE sub.patient_id = _pt.patient_id LIMIT 1) AS DOUBLE) <= 64 END AND EXISTS (SELECT 1 FROM "Had Office Visit" AS sub WHERE sub.patient_id = _pt.patient_id)
),
"Denominator" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Initial Population" AS sub WHERE sub.patient_id = _pt.patient_id)
),
"Denominator Exclusion" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Denominator" AS sub WHERE sub.patient_id = _pt.patient_id) AND (EXISTS (SELECT 1 FROM "Had Hysterectomy" AS sub WHERE sub.patient_id = _pt.patient_id) OR EXISTS (SELECT 1 FROM "In Hospice" AS sub WHERE sub.patient_id = _pt.patient_id))
),
"Numerator" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE EXISTS (SELECT 1 FROM "Denominator" AS sub WHERE sub.patient_id = _pt.patient_id) AND NOT EXISTS (SELECT 1 FROM "Denominator Exclusion" AS sub WHERE sub.patient_id = _pt.patient_id) AND (EXISTS (SELECT 1 FROM "Had Recent Cytology" AS sub WHERE sub.patient_id = _pt.patient_id) OR EXISTS (SELECT 1 FROM "Had Recent HPV" AS sub WHERE sub.patient_id = _pt.patient_id))
)
SELECT _pt.patient_id, "Cytology Lookback".value AS "Cytology Lookback", "HPV Lookback".value AS "HPV Lookback", (SELECT CASE WHEN "Had Hysterectomy".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Had Hysterectomy", (SELECT CASE WHEN "Had Recent Cytology".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Had Recent Cytology", (SELECT CASE WHEN "Had Recent HPV".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Had Recent HPV", (SELECT CASE WHEN "Is Female".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Is Female", "Measurement Period".value AS "Measurement Period", "Age At Start".resource AS "Age At Start", (SELECT CASE WHEN "Had Office Visit".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Had Office Visit", (SELECT CASE WHEN "In Hospice".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "In Hospice", (SELECT CASE WHEN "Initial Population".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Initial Population", (SELECT CASE WHEN "Denominator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS Denominator, (SELECT CASE WHEN "Denominator Exclusion".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Denominator Exclusion", (SELECT CASE WHEN "Numerator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS Numerator FROM _patients _pt LEFT JOIN "Cytology Lookback" ON _pt.patient_id = "Cytology Lookback".patient_id LEFT JOIN "HPV Lookback" ON _pt.patient_id = "HPV Lookback".patient_id LEFT JOIN "Had Hysterectomy" ON _pt.patient_id = "Had Hysterectomy".patient_id LEFT JOIN "Had Recent Cytology" ON _pt.patient_id = "Had Recent Cytology".patient_id LEFT JOIN "Had Recent HPV" ON _pt.patient_id = "Had Recent HPV".patient_id LEFT JOIN "Is Female" ON _pt.patient_id = "Is Female".patient_id LEFT JOIN "Measurement Period" ON _pt.patient_id = "Measurement Period".patient_id LEFT JOIN "Age At Start" ON _pt.patient_id = "Age At Start".patient_id LEFT JOIN "Had Office Visit" ON _pt.patient_id = "Had Office Visit".patient_id LEFT JOIN "In Hospice" ON _pt.patient_id = "In Hospice".patient_id LEFT JOIN "Initial Population" ON _pt.patient_id = "Initial Population".patient_id LEFT JOIN "Denominator" ON _pt.patient_id = "Denominator".patient_id LEFT JOIN "Denominator Exclusion" ON _pt.patient_id = "Denominator Exclusion".patient_id LEFT JOIN "Numerator" ON _pt.patient_id = "Numerator".patient_id ORDER BY _pt.patient_id ASC