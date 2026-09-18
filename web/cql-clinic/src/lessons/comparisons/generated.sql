WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Absolute Value" AS (
SELECT _pt.patient_id, TRY(system.abs(-5)) AS value FROM _patients AS _pt
),
"Age Category" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN 25 >= 18 THEN 'Adult' ELSE 'Minor' END) AS value FROM _patients AS _pt
),
"Date Difference" AS (
SELECT _pt.patient_id, cqlDifferenceBetween(CAST('2023-01-01' AS VARCHAR), CAST('2023-01-31' AS VARCHAR), 'day') AS value FROM _patients AS _pt
),
"Date Range" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE dateComponent(CAST('2024-06-15' AS VARCHAR), 'year') = 2024
),
"Equality" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE 'ABC' = 'ABC'
),
"Equivalence" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE CASE WHEN 'ABC' IS NULL AND 'abc' IS NULL THEN TRUE WHEN 'ABC' IS NULL OR 'abc' IS NULL THEN FALSE ELSE trim(regexp_replace(lower('ABC'), '\s+', ' ', 'g')) = trim(regexp_replace(lower('abc'), '\s+', ' ', 'g')) END
),
"Forced Precedence" AS (
SELECT _pt.patient_id, TRY((2 + 3) * 4) AS value FROM _patients AS _pt
),
"Grade Category" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN 85 >= 90 THEN 'A' WHEN 85 >= 80 THEN 'B' WHEN 85 >= 70 THEN 'C' ELSE 'F' END) AS resource FROM _patients AS _pt
),
"Power" AS (
SELECT _pt.patient_id, TRY_CAST(mathPower(CAST(2 AS VARCHAR), CAST(3 AS VARCHAR)) AS INTEGER) AS value FROM _patients AS _pt
),
"Precedence Test" AS (
SELECT _pt.patient_id, TRY(2 + 3 * 4) AS value FROM _patients AS _pt
),
"Square Root" AS (
SELECT _pt.patient_id, SQRT(16) AS resource FROM _patients AS _pt
)
SELECT _pt.patient_id, "Absolute Value".value AS "Absolute Value", "Age Category".value AS "Age Category", "Date Difference".value AS "Date Difference", (SELECT CASE WHEN "Date Range".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Date Range", (SELECT CASE WHEN "Equality".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS Equality, (SELECT CASE WHEN "Equivalence".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS Equivalence, "Forced Precedence".value AS "Forced Precedence", "Grade Category".resource AS "Grade Category", "Power".value AS Power, "Precedence Test".value AS "Precedence Test", "Square Root".resource AS "Square Root" FROM _patients _pt LEFT JOIN "Absolute Value" ON _pt.patient_id = "Absolute Value".patient_id LEFT JOIN "Age Category" ON _pt.patient_id = "Age Category".patient_id LEFT JOIN "Date Difference" ON _pt.patient_id = "Date Difference".patient_id LEFT JOIN "Date Range" ON _pt.patient_id = "Date Range".patient_id LEFT JOIN "Equality" ON _pt.patient_id = "Equality".patient_id LEFT JOIN "Equivalence" ON _pt.patient_id = "Equivalence".patient_id LEFT JOIN "Forced Precedence" ON _pt.patient_id = "Forced Precedence".patient_id LEFT JOIN "Grade Category" ON _pt.patient_id = "Grade Category".patient_id LEFT JOIN "Power" ON _pt.patient_id = "Power".patient_id LEFT JOIN "Precedence Test" ON _pt.patient_id = "Precedence Test".patient_id LEFT JOIN "Square Root" ON _pt.patient_id = "Square Root".patient_id ORDER BY _pt.patient_id ASC