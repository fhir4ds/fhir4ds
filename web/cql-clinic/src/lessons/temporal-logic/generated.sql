WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id, (SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1) AS patient_resource, CAST(fhirpath_date((SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1), 'birthDate') AS VARCHAR) AS birth_date FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Observation" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'effective') AS effective, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.start'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_start, COALESCE(json_extract_string(r.resource, '$.effectivePeriod.end'), json_extract_string(r.resource, '$.effectiveDateTime'), json_extract_string(r.resource, '$.effectiveDate'), json_extract_string(r.resource, '$.effectiveInstant')) AS effective_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Observation'
),
"Encounter" AS (
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_text(r.resource, 'period') AS period, json_extract_string(r.resource, '$.period.start') AS period_start, json_extract_string(r.resource, '$.period.end') AS period_end, fhirpath_text(r.resource, 'status') AS status FROM resources r WHERE r.resourceType = 'Encounter'
),
"Adjacent Or After" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE CAST(intervalStart(intervalFromBounds('2024-04-01', '2024-06-30', TRUE, TRUE)) AS TIMESTAMP) - INTERVAL '30 day' <= CAST(intervalStart(intervalFromBounds('2024-03-01', '2024-06-30', TRUE, TRUE)) AS TIMESTAMP) AND CAST(intervalStart(intervalFromBounds('2024-03-01', '2024-06-30', TRUE, TRUE)) AS TIMESTAMP) < CAST(intervalStart(intervalFromBounds('2024-04-01', '2024-06-30', TRUE, TRUE)) AS TIMESTAMP)
),
"Age In Months" AS (
SELECT _pt.patient_id, CalculateAgeInMonthsAt(CAST(_pt.birth_date AS VARCHAR), CAST('2024-03-12' AS VARCHAR)) AS resource FROM _patients AS _pt
),
"Age In Years" AS (
SELECT _pt.patient_id, CalculateAgeInYearsAt(CAST(_pt.birth_date AS VARCHAR), CAST('2024-03-12' AS VARCHAR)) AS resource FROM _patients AS _pt
),
"Birthday Month" AS (
SELECT _pt.patient_id, dateComponent(CAST(fhirpath_text(_pt.patient_resource, 'birthDate') AS VARCHAR), 'month') AS resource FROM _patients AS _pt
),
"Days Since Birth" AS (
SELECT _pt.patient_id, cqlDurationBetween(CAST(fhirpath_text(_pt.patient_resource, 'birthDate') AS VARCHAR), CAST('2024-03-12' AS VARCHAR), 'day') AS value FROM _patients AS _pt
),
"Enclosure Count" AS (
SELECT _pt.patient_id, (SELECT COUNT(_val) FROM (SELECT * AS _val FROM "Encounter" AS E WHERE intervalIncludes(intervalFromBounds('2024-01-01', '2024-06-30', TRUE, TRUE), E.period) AND E.patient_id = _pt.patient_id) AS _agg) AS value FROM _patients AS _pt
),
"First Obs In 2024" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END FROM "Observation" AS O WHERE intervalContains(intervalFromBounds('2024-01-01', '2024-06-30', TRUE, TRUE), CAST(CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END AS VARCHAR)) AND O.patient_id = _pt.patient_id ORDER BY json_extract_string(O.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"In Measurement Period" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE intervalContains(intervalFromBounds('2024-01-01', '2024-06-30', TRUE, TRUE), CAST('2024-03-01' AS VARCHAR))
),
"Latest Effective" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN fhirpath_text(O.resource, '(effective).type().name') IS NOT NULL AND LOWER(CAST(fhirpath_text(O.resource, '(effective).type().name') AS VARCHAR)) = 'datetime' THEN O.effective ELSE NULL END FROM "Observation" AS O WHERE O.patient_id = _pt.patient_id ORDER BY json_extract_string(O.resource, '$.id') ASC NULLS LAST LIMIT 1) AS resource FROM _patients AS _pt
),
"Measurement Period Width" AS (
SELECT _pt.patient_id, cqlDurationBetween(CAST(intervalStart(intervalFromBounds('2024-01-01', '2024-06-30', TRUE, TRUE)) AS VARCHAR), CAST(intervalEnd(intervalFromBounds('2024-01-01', '2024-06-30', TRUE, TRUE)) AS VARCHAR), 'day') AS value FROM _patients AS _pt
),
"Overlapping Intervals" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE COALESCE('2024-01-01', '0001-01-01') <= COALESCE('2024-06-30', '9999-12-31') AND COALESCE('2024-03-31', '9999-12-31') >= COALESCE('2024-03-01', '0001-01-01')
)
SELECT _pt.patient_id, (SELECT CASE WHEN "Adjacent Or After".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Adjacent Or After", "Age In Months".resource AS "Age In Months", "Age In Years".resource AS "Age In Years", "Birthday Month".resource AS "Birthday Month", "Days Since Birth".value AS "Days Since Birth", "Enclosure Count".value AS "Enclosure Count", "First Obs In 2024".resource AS "First Obs In 2024", (SELECT CASE WHEN "In Measurement Period".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "In Measurement Period", "Latest Effective".resource AS "Latest Effective", "Measurement Period Width".value AS "Measurement Period Width", (SELECT CASE WHEN "Overlapping Intervals".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Overlapping Intervals" FROM _patients _pt LEFT JOIN "Adjacent Or After" ON _pt.patient_id = "Adjacent Or After".patient_id LEFT JOIN "Age In Months" ON _pt.patient_id = "Age In Months".patient_id LEFT JOIN "Age In Years" ON _pt.patient_id = "Age In Years".patient_id LEFT JOIN "Birthday Month" ON _pt.patient_id = "Birthday Month".patient_id LEFT JOIN "Days Since Birth" ON _pt.patient_id = "Days Since Birth".patient_id LEFT JOIN "Enclosure Count" ON _pt.patient_id = "Enclosure Count".patient_id LEFT JOIN "First Obs In 2024" ON _pt.patient_id = "First Obs In 2024".patient_id LEFT JOIN "In Measurement Period" ON _pt.patient_id = "In Measurement Period".patient_id LEFT JOIN "Latest Effective" ON _pt.patient_id = "Latest Effective".patient_id LEFT JOIN "Measurement Period Width" ON _pt.patient_id = "Measurement Period Width".patient_id LEFT JOIN "Overlapping Intervals" ON _pt.patient_id = "Overlapping Intervals".patient_id ORDER BY _pt.patient_id ASC