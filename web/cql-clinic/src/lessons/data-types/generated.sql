WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Boolean And" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE TRUE AND FALSE
),
"Boolean Or" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE TRUE OR FALSE
),
"Coalesce Example" AS (
SELECT _pt.patient_id, COALESCE(NULL, 'Default Value') AS resource FROM _patients AS _pt
),
"Date Arithmetic" AS (
SELECT _pt.patient_id, dateAddQuantity(CAST(CAST(CURRENT_DATE AS VARCHAR) AS VARCHAR), '{"value": 30, "unit": "day", "system": "http://unitsofmeasure.org"}') AS value FROM _patients AS _pt
),
"Decimal Division" AS (
SELECT _pt.patient_id, cqlDivide(CAST(10.0 AS VARCHAR), CAST(3.0 AS VARCHAR)) AS value FROM _patients AS _pt
),
"Height" AS (
SELECT _pt.patient_id, parse_quantity('{"value": 175, "unit": "cm", "system": "http://unitsofmeasure.org"}') AS value FROM _patients AS _pt
),
"Integer Math" AS (
SELECT _pt.patient_id, TRY(10 + 5 * 2) AS value FROM _patients AS _pt
),
"Null Comparison" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE NULL IS NULL
),
"String Comparison" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE 'CQL' = 'CQL'
),
"String Concatenation" AS (
SELECT _pt.patient_id, 'Hello' || ' World' AS resource FROM _patients AS _pt
),
"Today" AS (
SELECT _pt.patient_id, CAST(CURRENT_DATE AS VARCHAR) AS value FROM _patients AS _pt
),
"Weight" AS (
SELECT _pt.patient_id, parse_quantity('{"value": 70, "unit": "kg", "system": "http://unitsofmeasure.org"}') AS value FROM _patients AS _pt
)
SELECT _pt.patient_id, (SELECT CASE WHEN "Boolean And".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Boolean And", (SELECT CASE WHEN "Boolean Or".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Boolean Or", "Coalesce Example".resource AS "Coalesce Example", "Date Arithmetic".value AS "Date Arithmetic", "Decimal Division".value AS "Decimal Division", "Height".value AS Height, "Integer Math".value AS "Integer Math", (SELECT CASE WHEN "Null Comparison".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Null Comparison", (SELECT CASE WHEN "String Comparison".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "String Comparison", "String Concatenation".resource AS "String Concatenation", "Today".value AS Today, "Weight".value AS Weight FROM _patients _pt LEFT JOIN "Boolean And" ON _pt.patient_id = "Boolean And".patient_id LEFT JOIN "Boolean Or" ON _pt.patient_id = "Boolean Or".patient_id LEFT JOIN "Coalesce Example" ON _pt.patient_id = "Coalesce Example".patient_id LEFT JOIN "Date Arithmetic" ON _pt.patient_id = "Date Arithmetic".patient_id LEFT JOIN "Decimal Division" ON _pt.patient_id = "Decimal Division".patient_id LEFT JOIN "Height" ON _pt.patient_id = "Height".patient_id LEFT JOIN "Integer Math" ON _pt.patient_id = "Integer Math".patient_id LEFT JOIN "Null Comparison" ON _pt.patient_id = "Null Comparison".patient_id LEFT JOIN "String Comparison" ON _pt.patient_id = "String Comparison".patient_id LEFT JOIN "String Concatenation" ON _pt.patient_id = "String Concatenation".patient_id LEFT JOIN "Today" ON _pt.patient_id = "Today".patient_id LEFT JOIN "Weight" ON _pt.patient_id = "Weight".patient_id ORDER BY _pt.patient_id ASC