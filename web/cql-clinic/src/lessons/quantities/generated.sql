WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Calendar Duration Compare" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE quantity_compare(parse_quantity('{"value": 1, "unit": "year", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 11, "unit": "month", "system": "http://unitsofmeasure.org"}'), '>')
),
"Cross Unit Sum" AS (
SELECT _pt.patient_id, quantity_add(parse_quantity('{"value": 1, "unit": "g", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 500, "unit": "mg", "system": "http://unitsofmeasure.org"}')) AS value FROM _patients AS _pt
),
"Dose In Range" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN parse_quantity('{"value": 7.5, "unit": "mg", "system": "http://unitsofmeasure.org"}') IS NULL OR parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}') IS NULL OR parse_quantity('{"value": 10, "unit": "mg", "system": "http://unitsofmeasure.org"}') IS NULL THEN NULL ELSE quantity_compare(parse_quantity('{"value": 7.5, "unit": "mg", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}'), '>=') AND quantity_compare(parse_quantity('{"value": 7.5, "unit": "mg", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 10, "unit": "mg", "system": "http://unitsofmeasure.org"}'), '<=') END) AS resource FROM _patients AS _pt
),
"Dose Literal" AS (
SELECT _pt.patient_id, parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}') AS value FROM _patients AS _pt
),
"Quantity As String" AS (
SELECT _pt.patient_id, QuantityToString(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}')) AS value FROM _patients AS _pt
),
"Quantity Unit" AS (
SELECT _pt.patient_id, from_json(fhirpath(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}'), 'unit'), '["VARCHAR"]') AS value FROM _patients AS _pt
),
"Quantity Value" AS (
SELECT _pt.patient_id, from_json(fhirpath(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}'), 'value'), '["VARCHAR"]') AS value FROM _patients AS _pt
),
"Same Unit Sum" AS (
SELECT _pt.patient_id, quantity_add(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}')) AS value FROM _patients AS _pt
),
"Scalar Multiply" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN quantity_value(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}')) IS NULL OR 2 IS NULL THEN NULL ELSE parse_quantity(CAST(json_object('value', quantity_value(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}')) * 2, 'unit', quantity_unit(parse_quantity('{"value": 5, "unit": "mg", "system": "http://unitsofmeasure.org"}')), 'system', 'http://unitsofmeasure.org') AS VARCHAR)) END) AS value FROM _patients AS _pt
),
"Temperature Compare" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE quantity_compare(parse_quantity('{"value": 37, "unit": "Cel", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 30, "unit": "Cel", "system": "http://unitsofmeasure.org"}'), '>')
),
"Unit Aware Equality" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE quantity_compare(parse_quantity('{"value": 1, "unit": "g", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 1000, "unit": "mg", "system": "http://unitsofmeasure.org"}'), '==')
),
"Unit Aware Ordering" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE quantity_compare(parse_quantity('{"value": 180, "unit": "cm", "system": "http://unitsofmeasure.org"}'), parse_quantity('{"value": 2, "unit": "m", "system": "http://unitsofmeasure.org"}'), '<')
)
SELECT _pt.patient_id, (SELECT CASE WHEN "Calendar Duration Compare".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Calendar Duration Compare", "Cross Unit Sum".value AS "Cross Unit Sum", "Dose In Range".resource AS "Dose In Range", "Dose Literal".value AS "Dose Literal", "Quantity As String".value AS "Quantity As String", "Quantity Unit".value AS "Quantity Unit", "Quantity Value".value AS "Quantity Value", "Same Unit Sum".value AS "Same Unit Sum", "Scalar Multiply".value AS "Scalar Multiply", (SELECT CASE WHEN "Temperature Compare".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Temperature Compare", (SELECT CASE WHEN "Unit Aware Equality".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Unit Aware Equality", (SELECT CASE WHEN "Unit Aware Ordering".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Unit Aware Ordering" FROM _patients _pt LEFT JOIN "Calendar Duration Compare" ON _pt.patient_id = "Calendar Duration Compare".patient_id LEFT JOIN "Cross Unit Sum" ON _pt.patient_id = "Cross Unit Sum".patient_id LEFT JOIN "Dose In Range" ON _pt.patient_id = "Dose In Range".patient_id LEFT JOIN "Dose Literal" ON _pt.patient_id = "Dose Literal".patient_id LEFT JOIN "Quantity As String" ON _pt.patient_id = "Quantity As String".patient_id LEFT JOIN "Quantity Unit" ON _pt.patient_id = "Quantity Unit".patient_id LEFT JOIN "Quantity Value" ON _pt.patient_id = "Quantity Value".patient_id LEFT JOIN "Same Unit Sum" ON _pt.patient_id = "Same Unit Sum".patient_id LEFT JOIN "Scalar Multiply" ON _pt.patient_id = "Scalar Multiply".patient_id LEFT JOIN "Temperature Compare" ON _pt.patient_id = "Temperature Compare".patient_id LEFT JOIN "Unit Aware Equality" ON _pt.patient_id = "Unit Aware Equality".patient_id LEFT JOIN "Unit Aware Ordering" ON _pt.patient_id = "Unit Aware Ordering".patient_id ORDER BY _pt.patient_id ASC