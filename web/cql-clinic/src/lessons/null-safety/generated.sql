WITH _patients AS (
SELECT DISTINCT _outer.patient_ref AS patient_id, (SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1) AS patient_resource, CAST(fhirpath_date((SELECT _pt_resource.resource FROM resources AS _pt_resource WHERE _pt_resource.resourceType = 'Patient' AND _pt_resource.id = _outer.patient_ref LIMIT 1), 'birthDate') AS VARCHAR) AS birth_date FROM resources AS _outer WHERE _outer.patient_ref IS NOT NULL AND EXISTS (SELECT 1 FROM resources AS _pt WHERE _pt.resourceType = 'Patient' AND _pt.id = _outer.patient_ref)
),
"Coalesce Field Default" AS (
SELECT _pt.patient_id, COALESCE(fhirpath_text(_pt.patient_resource, 'deceased.value'), 'still alive') AS resource FROM _patients AS _pt
),
"Coalesce First NonNull" AS (
SELECT _pt.patient_id, COALESCE(NULL, NULL, 'found me') AS resource FROM _patients AS _pt
),
"Count Ignores Null" AS (
SELECT _pt.patient_id, len(list_filter([NULL, 'a', NULL, 'b'], _v -> _v IS NOT NULL)) AS value FROM _patients AS _pt
),
"Deceased Is Null" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE fhirpath_text(_pt.patient_resource, 'deceased') IS NULL
),
"Explicit Null Is Null" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE NULL IS NULL
),
"IsNull Vs IsTrue" AS (
SELECT _pt.patient_id, (SELECT CASE WHEN IsTrue(fhirpath_text(_pt.patient_resource, 'deceased') IS NULL) THEN 'no death date' ELSE 'has death date' END) AS value FROM _patients AS _pt
),
"Missing Field Is Null" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE fhirpath_text(_pt.patient_resource, 'telecom') IS NULL
),
"Null And False" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE NULL AND FALSE
),
"Null Not Equal" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE NULL != 'x'
),
"Null Not Propagates" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE NOT NULL
),
"Null Or True" AS (
SELECT _pt.patient_id FROM _patients AS _pt WHERE NULL OR TRUE
)
SELECT _pt.patient_id, "Coalesce Field Default".resource AS "Coalesce Field Default", "Coalesce First NonNull".resource AS "Coalesce First NonNull", "Count Ignores Null".value AS "Count Ignores Null", (SELECT CASE WHEN "Deceased Is Null".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Deceased Is Null", (SELECT CASE WHEN "Explicit Null Is Null".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Explicit Null Is Null", "IsNull Vs IsTrue".value AS "IsNull Vs IsTrue", (SELECT CASE WHEN "Missing Field Is Null".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Missing Field Is Null", (SELECT CASE WHEN "Null And False".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Null And False", (SELECT CASE WHEN "Null Not Equal".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Null Not Equal", (SELECT CASE WHEN "Null Not Propagates".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Null Not Propagates", (SELECT CASE WHEN "Null Or True".patient_id IS NOT NULL THEN TRUE ELSE FALSE END) AS "Null Or True" FROM _patients _pt LEFT JOIN "Coalesce Field Default" ON _pt.patient_id = "Coalesce Field Default".patient_id LEFT JOIN "Coalesce First NonNull" ON _pt.patient_id = "Coalesce First NonNull".patient_id LEFT JOIN "Count Ignores Null" ON _pt.patient_id = "Count Ignores Null".patient_id LEFT JOIN "Deceased Is Null" ON _pt.patient_id = "Deceased Is Null".patient_id LEFT JOIN "Explicit Null Is Null" ON _pt.patient_id = "Explicit Null Is Null".patient_id LEFT JOIN "IsNull Vs IsTrue" ON _pt.patient_id = "IsNull Vs IsTrue".patient_id LEFT JOIN "Missing Field Is Null" ON _pt.patient_id = "Missing Field Is Null".patient_id LEFT JOIN "Null And False" ON _pt.patient_id = "Null And False".patient_id LEFT JOIN "Null Not Equal" ON _pt.patient_id = "Null Not Equal".patient_id LEFT JOIN "Null Not Propagates" ON _pt.patient_id = "Null Not Propagates".patient_id LEFT JOIN "Null Or True" ON _pt.patient_id = "Null Or True".patient_id ORDER BY _pt.patient_id ASC