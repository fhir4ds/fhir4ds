WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id, (SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1) AS patient_resource, CAST(fhirpath_date((SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1), 'birthDate') AS VARCHAR) AS birth_date FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"B Position" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN strpos('abc', 'b') = 0 THEN -1 ELSE strpos('abc', 'b') - 1 END) AS resource FROM _patients AS _pt
),
"Birth Year String" AS (
SELECT _pt.patient_id, ToString(dateComponent(CAST(fhirpath_text(_pt.patient_resource, 'birthDate') AS VARCHAR), 'year')) AS value FROM _patients AS _pt
),
"Date Reformat" AS (
SELECT _pt.patient_id, ReplaceMatches('2024-03-01', '-', '/') AS resource FROM _patients AS _pt
),
"First Segment" AS (
SELECT _pt.patient_id, LIST_EXTRACT(STR_SPLIT('a,b,c', ','), 1) AS resource FROM _patients AS _pt
),
"First Word" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN 0 < 0 OR 0 >= system.length('FHIRPath') OR 4 < 0 THEN NULL ELSE system.substring('FHIRPath', 0 + 1, 4) END) AS resource FROM _patients AS _pt
),
"Gender Shouted" AS (
SELECT _pt.patient_id, UPPER(fhirpath_text(_pt.patient_resource, 'gender')) AS resource FROM _patients AS _pt
),
"Int To String" AS (
SELECT _pt.patient_id, ToString(42) AS value FROM _patients AS _pt
),
"Integer Convertible" AS (
SELECT _pt.patient_id, ConvertsToInteger('42') AS resource FROM _patients AS _pt
),
"Is Http" AS (
SELECT _pt.patient_id, StartsWith('http://hl7.org', 'http') AS resource FROM _patients AS _pt
),
"Is Pdf" AS (
SELECT _pt.patient_id, EndsWith('report.pdf', 'pdf') AS resource FROM _patients AS _pt
),
"Joined" AS (
SELECT _pt.patient_id, CombineSep(['a', 'b', 'c'], '-') AS resource FROM _patients AS _pt
),
"Name Length" AS (
SELECT _pt.patient_id, LENGTH('FHIR') AS resource FROM _patients AS _pt
),
"Not Integer Convertible" AS (
SELECT _pt.patient_id, ConvertsToInteger('3.5') AS resource FROM _patients AS _pt
),
"Shout" AS (
SELECT _pt.patient_id, UPPER('hello') AS resource FROM _patients AS _pt
),
"String To Decimal" AS (
SELECT _pt.patient_id, ToDecimal('3.5') AS value FROM _patients AS _pt
),
"String To Integer" AS (
SELECT _pt.patient_id, ToInteger('42') AS value FROM _patients AS _pt
),
"Whisper" AS (
SELECT _pt.patient_id, LOWER('WORLD') AS resource FROM _patients AS _pt
)
SELECT _pt.patient_id, "B Position".resource AS "B Position", "Birth Year String".value AS "Birth Year String", "Date Reformat".resource AS "Date Reformat", "First Segment".resource AS "First Segment", "First Word".resource AS "First Word", "Gender Shouted".resource AS "Gender Shouted", "Int To String".value AS "Int To String", "Integer Convertible".resource AS "Integer Convertible", "Is Http".resource AS "Is Http", "Is Pdf".resource AS "Is Pdf", "Joined".resource AS Joined, "Name Length".resource AS "Name Length", "Not Integer Convertible".resource AS "Not Integer Convertible", "Shout".resource AS Shout, "String To Decimal".value AS "String To Decimal", "String To Integer".value AS "String To Integer", "Whisper".resource AS Whisper FROM _patients _pt LEFT JOIN "B Position" ON _pt.patient_id = "B Position".patient_id LEFT JOIN "Birth Year String" ON _pt.patient_id = "Birth Year String".patient_id LEFT JOIN "Date Reformat" ON _pt.patient_id = "Date Reformat".patient_id LEFT JOIN "First Segment" ON _pt.patient_id = "First Segment".patient_id LEFT JOIN "First Word" ON _pt.patient_id = "First Word".patient_id LEFT JOIN "Gender Shouted" ON _pt.patient_id = "Gender Shouted".patient_id LEFT JOIN "Int To String" ON _pt.patient_id = "Int To String".patient_id LEFT JOIN "Integer Convertible" ON _pt.patient_id = "Integer Convertible".patient_id LEFT JOIN "Is Http" ON _pt.patient_id = "Is Http".patient_id LEFT JOIN "Is Pdf" ON _pt.patient_id = "Is Pdf".patient_id LEFT JOIN "Joined" ON _pt.patient_id = "Joined".patient_id LEFT JOIN "Name Length" ON _pt.patient_id = "Name Length".patient_id LEFT JOIN "Not Integer Convertible" ON _pt.patient_id = "Not Integer Convertible".patient_id LEFT JOIN "Shout" ON _pt.patient_id = "Shout".patient_id LEFT JOIN "String To Decimal" ON _pt.patient_id = "String To Decimal".patient_id LEFT JOIN "String To Integer" ON _pt.patient_id = "String To Integer".patient_id LEFT JOIN "Whisper" ON _pt.patient_id = "Whisper".patient_id ORDER BY _pt.patient_id ASC