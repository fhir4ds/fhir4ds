-- Generated SQL for CMS68

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('0111c1a9-1590-40d6-8023-0e3bd45d493e',
                                '12626e98-67c8-4f3d-bac5-dbb5d57f58c8',
                                '14943c8d-1551-4449-b244-f3381a6f4e28',
                                '25938d1a-7785-4453-9574-01ccb82cb3e8',
                                '33c3042b-b935-456f-b22b-f3f55cf56cdc',
                                '37daa71d-a2a5-4807-8ee1-93417424ffee',
                                '3d42d9f8-0381-4562-94b7-314fcd27fae5',
                                '4ce081ec-bc42-44c6-bfbb-ad853903e3d1',
                                '60ad5deb-5c36-4ba3-bdee-9390f7ffdf6e',
                                '6bffc7ce-d4ac-42e2-9fd0-48b58e45d502',
                                '6f04cfd6-8557-4eff-84cb-9d3ed094dc4b',
                                '8b704351-4052-4207-8f69-e259ca15bf62',
                                '9ada2736-229a-40d4-b026-2bdec85c6d02',
                                'b6b76d56-4dd6-4394-98e3-97dbd3236675',
                                'd1f4cbfc-1f86-408b-a65d-50250a4dd148',
                                'db7bf97d-edaf-41c9-bf02-81a3f31db686',
                                'ebea0fbe-8ab4-43a2-8bfa-5117bb8d56a9',
                                'f254d721-854c-4b26-9d14-e6052c341501',
                                'f2e2e1c0-9e35-4592-9579-72a236cb2f56')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Encounter to Document Medications" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.600.1.1834')),
     "Procedure: Documentation of current medications (procedure)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://snomed.info/sct'' and code=''428191000124101'').exists()')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Procedure: Documentation of current medications (procedure) (procedurenotdone)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://snomed.info/sct'' and code=''428191000124101'').exists()')
     AND fhirpath_text(r.resource, 'status') = 'not-done'),
     "Coverage: Payer Type" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'type') AS "type"
   FROM resources r
   WHERE r.resourceType = 'Coverage'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591')),
     "SDE.SDE Ethnicity" AS
  (SELECT p.patient_id,
          list_transform(from_json(fhirpath(
                                              (SELECT _pd.resource
                                               FROM _patient_demographics AS _pd
                                               WHERE _pd.patient_id = p.patient_id
                                               LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity'').extension.where(url=''ombCategory'').valueCoding.code'), '["VARCHAR"]'), _lt_E -> json_object('codes', "Distinct"(list_concat([fhirpath_text(_lt_E, 'ombCategory')], fhirpath_text(_lt_E, 'detailed'))), 'display', fhirpath_text(_lt_E, 'text'))) AS RESOURCE
   FROM _patients AS p),
     "SDE.SDE Payer" AS
  (SELECT _inner.patient_id,
          _inner._resource_data AS RESOURCE
   FROM
     (SELECT patient_id,
             json_object('code', Payer.type, 'period', fhirpath_text(Payer.resource, 'period')) AS _resource_data
      FROM "Coverage: Payer Type" AS Payer) AS _inner),
     "SDE.SDE Race" AS
  (SELECT p.patient_id,
          list_transform(from_json(fhirpath(
                                              (SELECT _pd.resource
                                               FROM _patient_demographics AS _pd
                                               WHERE _pd.patient_id = p.patient_id
                                               LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-race'').extension.where(url=''ombCategory'').valueCoding.code'), '["VARCHAR"]'), _lt_R -> json_object('codes', CASE
                                                                                                                                                                                                                                                           WHEN fhirpath_text(_lt_R, 'ombCategory') IS NOT NULL
                                                                                                                                                                                                                                                                AND fhirpath_text(_lt_R, 'detailed') IS NOT NULL THEN "Distinct"(jsonConcat(fhirpath_text(_lt_R, 'ombCategory'), fhirpath_text(_lt_R, 'detailed')))
                                                                                                                                                                                                                                                           ELSE NULL
                                                                                                                                                                                                                                                       END, 'display', fhirpath_text(_lt_R, 'text'))) AS RESOURCE
   FROM _patients AS p),
     "SDE.SDE Sex" AS
  (SELECT p.patient_id,

     (SELECT CASE
                 WHEN fhirpath_text(
                                      (SELECT _pd.resource
                                       FROM _patient_demographics AS _pd
                                       WHERE _pd.patient_id = p.patient_id
                                       LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex'').valueCode') = '248153007' THEN 'http://snomed.info/sct|248153007'
                 WHEN fhirpath_text(
                                      (SELECT _pd.resource
                                       FROM _patient_demographics AS _pd
                                       WHERE _pd.patient_id = p.patient_id
                                       LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex'').valueCode') = '248152002' THEN 'http://snomed.info/sct|248152002'
                 ELSE NULL
             END) AS value
   FROM _patients AS p),
     "Qualifying Encounter During Day of Measurement Period" AS
  (SELECT *
   FROM "Encounter: Encounter to Document Medications" AS ValidEncounter
   WHERE ValidEncounter.status = 'finished'
     AND CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(ValidEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(ValidEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)),
     "Denominator Exceptions" AS
  (SELECT *
   FROM "Qualifying Encounter During Day of Measurement Period" AS QualifyingEncounter
   WHERE EXISTS
       (SELECT 1
        FROM "Procedure: Documentation of current medications (procedure) (procedurenotdone)" AS MedicationsNotDocumented
        WHERE intervalContains(fhirpath_text(QualifyingEncounter.resource, 'period'), fhirpath_text(MedicationsNotDocumented.resource, 'extension.where(url=''http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-recorded'').valueDateTime'))
          AND fhirpath_text(MedicationsNotDocumented.resource, 'status') = 'not-done'
          AND fhirpath_bool(MedicationsNotDocumented.resource, 'reasonCode.coding.where(system=''http://snomed.info/sct'' and code=''705016005'').exists()')
          AND MedicationsNotDocumented.patient_id = QualifyingEncounter.patient_id)),
     "Initial Population" AS
  (SELECT *
   FROM "Qualifying Encounter During Day of Measurement Period" AS QualifyingEncounter),
     "Denominator" AS
  (SELECT *
   FROM "Initial Population"),
     "Numerator" AS
  (SELECT *
   FROM "Qualifying Encounter During Day of Measurement Period" AS QualifyingEncounter
   WHERE EXISTS
       (SELECT 1
        FROM "Procedure: Documentation of current medications (procedure)" AS MedicationsDocumented
        WHERE intervalContains(fhirpath_text(QualifyingEncounter.resource, 'period'), intervalEnd(CASE
                                                                                                      WHEN fhirpath_text(MedicationsDocumented.resource, 'performed') IS NULL THEN NULL
                                                                                                      WHEN starts_with(LTRIM(fhirpath_text(MedicationsDocumented.resource, 'performed')), '{') THEN fhirpath_text(MedicationsDocumented.resource, 'performed')
                                                                                                      ELSE intervalFromBounds(fhirpath_text(MedicationsDocumented.resource, 'performed'), fhirpath_text(MedicationsDocumented.resource, 'performed'), TRUE, TRUE)
                                                                                                  END))
          AND fhirpath_text(MedicationsDocumented.resource, 'status') = 'completed'
          AND MedicationsDocumented.patient_id = QualifyingEncounter.patient_id)),
     "SDE Ethnicity" AS
  (SELECT *
   FROM "SDE.SDE Ethnicity"),
     "SDE Payer" AS
  (SELECT *
   FROM "SDE.SDE Payer"),
     "SDE Race" AS
  (SELECT *
   FROM "SDE.SDE Race"),
     "SDE Sex" AS
  (SELECT *
   FROM "SDE.SDE Sex")
SELECT p.patient_id,

  (SELECT COALESCE(LIST(json_extract_string("Initial Population".resource, '$.resourceType') || '/' || json_extract_string("Initial Population".resource, '$.id')), [])
   FROM "Initial Population"
   WHERE "Initial Population".patient_id = p.patient_id
     AND "Initial Population".resource IS NOT NULL) AS "Initial Population",

  (SELECT COALESCE(LIST(json_extract_string("Denominator".resource, '$.resourceType') || '/' || json_extract_string("Denominator".resource, '$.id')), [])
   FROM "Denominator"
   WHERE "Denominator".patient_id = p.patient_id
     AND "Denominator".resource IS NOT NULL) AS Denominator,

  (SELECT COALESCE(LIST(json_extract_string("Denominator Exceptions".resource, '$.resourceType') || '/' || json_extract_string("Denominator Exceptions".resource, '$.id')), [])
   FROM "Denominator Exceptions"
   WHERE "Denominator Exceptions".patient_id = p.patient_id
     AND "Denominator Exceptions".resource IS NOT NULL) AS "Denominator Exceptions",

  (SELECT COALESCE(LIST(json_extract_string("Numerator".resource, '$.resourceType') || '/' || json_extract_string("Numerator".resource, '$.id')), [])
   FROM "Numerator"
   WHERE "Numerator".patient_id = p.patient_id
     AND "Numerator".resource IS NOT NULL) AS Numerator
FROM _patients p
ORDER BY p.patient_id ASC
