-- Generated SQL for CMS50

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('03556842-5a83-41e6-8f43-5801d151336b',
                                '075f9e36-6a87-47ac-952e-aeb295f184d9',
                                '0fbfcffb-d7b0-4956-b860-22bac50ca7ea',
                                '12c82f74-5184-450f-9de1-ea211f3bf47a',
                                '25b1e840-7e85-4140-9c1b-773d4daa6dee',
                                '2feec6c6-7250-4391-a4ee-0d5006cc70bc',
                                '3041ca48-5558-4fa4-829f-c3d6129bdd54',
                                '37605377-59e5-4f97-b12f-797753056b96',
                                '3c747b52-446b-4107-aff5-a6121d5e9ffc',
                                '3e48a3fd-0416-470f-a3c5-3635f18f2913',
                                '408f74fc-488e-4d0e-8d4b-cd3f17955b31',
                                '445106a4-1531-4830-8726-4ea6c1d27484',
                                '6138f86b-449c-4828-9b62-fe2bed4157b1',
                                '648157ed-8a6e-43b5-9481-9498848ae5ea',
                                '65d214fa-db56-4076-9ecc-485c31229b0f',
                                '849d31ab-b698-4cb4-99eb-fc3ad8aceda9',
                                '854f73d5-2461-4c12-b214-c4a3ceecfe36',
                                '8e1e9821-1176-4dd0-a361-1931cbc5029e',
                                '929d656d-006c-46c3-81c5-6ca1c82146d2',
                                '9b46ce43-4c9e-4112-8d8d-89c01cef28b0',
                                'a4eb4933-e343-4e4b-b4bd-f582c42979be',
                                'b1788e29-83a4-4a89-a488-6d0a861f13cd',
                                'b20c7bc3-8545-4807-8212-5fb687463efc',
                                'bf87bf51-99d7-4765-a19a-f68c9fcf6a2e',
                                'c1493a4a-56c3-40ba-b209-edca6d9a0b9d',
                                'c1b6ce43-8310-4776-8103-1e0d6bc08fc6',
                                'cf289d58-f8a0-4f58-a62d-39fc1762318a',
                                'd9a98a4c-9208-4370-b07c-1c5c63fd09b6',
                                'dc409230-77aa-4b66-bc1d-84e421089367',
                                'e25e1d4a-6240-4bd6-8d8a-2773e7a920b6',
                                'e2a4f358-87f1-4fe1-b4e1-27969993d361',
                                'f117390a-55f1-49b7-920a-c64d1934c89c',
                                'f2634662-4c9c-4963-b3f4-f90c3794bcc3')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Ophthalmological Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1285')),
     "Encounter: Preventive Care, Established Office Visit, 0 to 17" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1024')),
     "Encounter" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'),
     "Encounter: Preventive Care Services Established Office Visit, 18 and Up" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1025')),
     "Procedure: Health behavior assessment, or re-assessment (ie, health-focused clinical interview, behavioral observations, clinical decision making)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96156'').exists()')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Procedure: Psychological or neuropsychological test administration and scoring by physician or other qualified health care professional, two or more tests, any method; first 30 minutes" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96136'').exists()')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Encounter: Behavioral/Neuropsych Assessment" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1023')),
     "Procedure: Behavioral/Neuropsych Assessment" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1023')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Procedure: Psych Visit Diagnostic Evaluation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1492')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1022')),
     "Procedure: Psychotherapy for crisis; first 60 minutes" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''90839'').exists()')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Procedure: Psychological or neuropsychological test administration and scoring by technician, two or more tests, any method; first 30 minutes" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96138'').exists()')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Encounter: Preventive Care Services Initial Office Visit, 18 and Up" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1023')),
     "Task: Consultant Report" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Task'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.121.12.1006')),
     "Procedure: Developmental test administration (including assessment of fine and/or gross motor, language, cognitive level, social, memory and/or executive functions by standardized developmental instruments when performed), by physician or other qualified health care professional, with interpretation and report; first hour" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96112'').exists()')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "ServiceRequest: Referral" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'authoredOn') AS authored_date,
                   fhirpath_text(r.resource, 'intent') AS intent,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'ServiceRequest'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1046')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
     "Encounter: Psych Visit Diagnostic Evaluation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1492')),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
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
     "First Referral during First 10 Months of Measurement Period" AS
  (SELECT p.patient_id,

     (SELECT json_object('ID', fhirpath_text(ReferralOrder.resource, 'id'), 'AuthorDate', ReferralOrder.authored_date)
      FROM "ServiceRequest: Referral" AS ReferralOrder
      WHERE array_contains(['active', 'completed'], ReferralOrder.status)
        AND ReferralOrder.intent = 'order'
        AND CAST(LEFT(REPLACE(CAST(fhirpath_text(ReferralOrder.resource, 'authoredOn') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
        AND CAST(LEFT(REPLACE(CAST(fhirpath_text(ReferralOrder.resource, 'authoredOn') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(printf('%04d-%02d-%02d', CASE
                                                                                                                                                                                      WHEN LENGTH(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T')) >= 4 THEN CAST(SUBSTR(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 1, 4) AS INTEGER)
                                                                                                                                                                                      ELSE NULL
                                                                                                                                                                                  END, 10, 31) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
        AND ReferralOrder.patient_id = p.patient_id
      ORDER BY fhirpath_text(ReferralOrder.resource, 'authoredOn') ASC NULLS LAST, json_extract_string(ReferralOrder.resource, '$.id') ASC NULLS LAST
      LIMIT 1) AS RESOURCE
   FROM _patients AS p),
     "Has Encounter during Measurement Period" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Encounter: Office Visit"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Ophthalmological Services"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care Services Established Office Visit, 18 and Up"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care Services Initial Office Visit, 18 and Up"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care, Established Office Visit, 0 to 17") AS ValidEncounter
        WHERE ValidEncounter.patient_id = p.patient_id
          AND fhirpath_text(ValidEncounter.resource, 'status') = 'finished'
          AND CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                       WHEN fhirpath_text(ValidEncounter.resource, 'period') IS NULL THEN NULL
                                                       WHEN starts_with(LTRIM(fhirpath_text(ValidEncounter.resource, 'period')), '{') THEN fhirpath_text(ValidEncounter.resource, 'period')
                                                       ELSE intervalFromBounds(fhirpath_text(ValidEncounter.resource, 'period'), fhirpath_text(ValidEncounter.resource, 'period'), TRUE, TRUE)
                                                   END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(intervalEnd(CASE
                                                     WHEN fhirpath_text(ValidEncounter.resource, 'period') IS NULL THEN NULL
                                                     WHEN starts_with(LTRIM(fhirpath_text(ValidEncounter.resource, 'period')), '{') THEN fhirpath_text(ValidEncounter.resource, 'period')
                                                     ELSE intervalFromBounds(fhirpath_text(ValidEncounter.resource, 'period'), fhirpath_text(ValidEncounter.resource, 'period'), TRUE, TRUE)
                                                 END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))),
     "Has Encounter from DRCs during Measurement Period" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT *
           FROM "Encounter" AS EncDRC
           WHERE fhirpath_bool(EncDRC.resource, 'type.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96136'').exists()')
             OR fhirpath_bool(EncDRC.resource, 'type.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96138'').exists()')
             OR fhirpath_bool(EncDRC.resource, 'type.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''90839'').exists()')
             OR fhirpath_bool(EncDRC.resource, 'type.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96112'').exists()')
             OR fhirpath_bool(EncDRC.resource, 'type.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''96156'').exists()')) AS Encounter
        WHERE Encounter.patient_id = p.patient_id
          AND fhirpath_text(Encounter.resource, 'status') = 'finished'
          AND CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))),
     "Has Encounter from Valuesets during Measurement Period" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Encounter: Behavioral/Neuropsych Assessment"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Office Visit"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Ophthalmological Services"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care Services Established Office Visit, 18 and Up"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care Services Initial Office Visit, 18 and Up"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Preventive Care, Established Office Visit, 0 to 17"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Encounter: Psych Visit Diagnostic Evaluation") AS Encounter
        WHERE Encounter.patient_id = p.patient_id
          AND fhirpath_text(Encounter.resource, 'status') = 'finished'
          AND CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))),
     "Has Intervention during Measurement Period" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM
             (SELECT patient_id,
                     RESOURCE
              FROM "Procedure: Behavioral/Neuropsych Assessment"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Procedure: Health behavior assessment, or re-assessment (ie, health-focused clinical interview, behavioral observations, clinical decision making)"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Procedure: Psychological or neuropsychological test administration and scoring by physician or other qualified health care professional, two or more tests, any method; first 30 minutes"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Procedure: Psychological or neuropsychological test administration and scoring by technician, two or more tests, any method; first 30 minutes"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Procedure: Psychotherapy for crisis; first 60 minutes"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Procedure: Psych Visit Diagnostic Evaluation"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Procedure: Developmental test administration (including assessment of fine and/or gross motor, language, cognitive level, social, memory and/or executive functions by standardized developmental instruments when performed), by physician or other qualified health care professional, with interpretation and report; first hour") AS _union
           WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS ValidIntervention
        WHERE ValidIntervention.patient_id = p.patient_id
          AND CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                       WHEN fhirpath_text(ValidIntervention.resource, 'performed') IS NULL THEN NULL
                                                       WHEN starts_with(LTRIM(fhirpath_text(ValidIntervention.resource, 'performed')), '{') THEN fhirpath_text(ValidIntervention.resource, 'performed')
                                                       ELSE intervalFromBounds(fhirpath_text(ValidIntervention.resource, 'performed'), fhirpath_text(ValidIntervention.resource, 'performed'), TRUE, TRUE)
                                                   END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(intervalEnd(CASE
                                                     WHEN fhirpath_text(ValidIntervention.resource, 'performed') IS NULL THEN NULL
                                                     WHEN starts_with(LTRIM(fhirpath_text(ValidIntervention.resource, 'performed')), '{') THEN fhirpath_text(ValidIntervention.resource, 'performed')
                                                     ELSE intervalFromBounds(fhirpath_text(ValidIntervention.resource, 'performed'), fhirpath_text(ValidIntervention.resource, 'performed'), TRUE, TRUE)
                                                 END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))),
     "Initial Population" AS
  (SELECT p.patient_id
   FROM _patients AS p
   LEFT JOIN "First Referral during First 10 Months of Measurement Period" AS j1 ON j1.patient_id = p.patient_id
   WHERE (EXISTS
            (SELECT 1
             FROM "Has Encounter during Measurement Period" AS sub
             WHERE sub.patient_id = p.patient_id)
          OR EXISTS
            (SELECT 1
             FROM "Has Intervention during Measurement Period" AS sub
             WHERE sub.patient_id = p.patient_id))
     AND j1.resource IS NOT NULL),
     "Denominator" AS
  (SELECT *
   FROM "Initial Population"),
     "Referring Clinician Receives Consultant Report to Close Referral Loop" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM "Task: Consultant Report" AS ConsultantReportObtained
        WHERE ConsultantReportObtained.patient_id = p.patient_id
          AND EXISTS
            (SELECT 1
             FROM
               (SELECT *
                FROM "First Referral during First 10 Months of Measurement Period") AS FirstReferral
             WHERE json_extract_string(FirstReferral.resource, '$.ID') IN list_transform(from_json(fhirpath(ConsultantReportObtained.resource, 'basedOn'), '["VARCHAR"]'), _lt_Task -> LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Task, 'reference'), '/'), -1))
               AND CAST(intervalEnd(fhirpath_text(ConsultantReportObtained.resource, 'executionPeriod')) AS VARCHAR) > CAST(json_extract_string(FirstReferral.resource, '$.AuthorDate') AS VARCHAR)
               AND fhirpath_text(ConsultantReportObtained.resource, 'status') = 'completed'
               AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(ConsultantReportObtained.resource, 'executionPeriod')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) BETWEEN CAST(LEFT(REPLACE(CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AND COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), CAST(LEFT(REPLACE(CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))
               AND FirstReferral.patient_id = ConsultantReportObtained.patient_id))),
     "Numerator" AS
  (SELECT *
   FROM "Referring Clinician Receives Consultant Report to Close Referral Loop"),
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

  (SELECT CASE
              WHEN "Initial Population".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS "Initial Population",

  (SELECT CASE
              WHEN "Denominator".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS Denominator,

  (SELECT CASE
              WHEN "Numerator".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS Numerator
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id ASC
