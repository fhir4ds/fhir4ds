-- Generated SQL for CMS142

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('03b74242-d93e-438e-ac6a-f46b41548209',
                                '05f1e2a6-b317-42bb-827f-993ca3995f5b',
                                '0abeb5d4-0e98-4b8f-9745-2435306d9978',
                                '0b2799e8-0b28-4307-9fce-5441ee9950ae',
                                '15b275f0-8540-4c32-8ab6-29e535dcea64',
                                '164018dc-af9e-47b8-901f-70d00e101e43',
                                '28492651-41c3-4e9e-a68f-9b7836e3eca9',
                                '2dd72971-2da8-4365-8147-106425cf4a6f',
                                '356705b1-d6dd-44fd-916e-209c55981b0a',
                                '3783189c-3c29-4687-9f89-c3306c6d28fd',
                                '380d6e3a-1fc1-474c-a8f3-8e6ba4f0dd42',
                                '3835c33d-b335-44d7-a7b6-c8a0d5420290',
                                '3df53f41-2dd3-4f7c-9745-0566541661c4',
                                '3eba9b35-c636-42be-b34d-d4efacf3cbd2',
                                '41ae0086-ac99-4a31-9546-21b054bbf7d8',
                                '54e602f1-ae48-421f-ac5f-417538ae401e',
                                '5df18a61-3644-4004-b66f-84530f643a74',
                                '6aef5a18-59bd-4a47-80bc-2bd44636e41f',
                                '70727b4f-7bb8-4782-8462-f7fe286aed50',
                                '73734a3e-0dc8-44ce-a5a2-070b1ab48aaf',
                                '9a9e1543-79a1-47a0-a3dd-5ac008bbea65',
                                '9bdcc79c-f0b7-438e-9e2b-3f6a4350caf6',
                                'afe0cb42-4b07-4874-8ea2-46e9ecc94787',
                                'b85440e4-b902-49cd-b3d6-363ba7a99bce',
                                'bc456bd5-d133-48dd-bbfc-228fa3f22c9a',
                                'c90e9816-b69c-423c-827c-475f63f1ef7d',
                                'ccee7cc2-a83f-4b0b-8cda-43099234b75d',
                                'd9840e8c-3359-42c2-b354-4b236c3c1b15',
                                'dea40dde-9674-4a89-987f-0617a78a5e94',
                                'eb6c9df0-6dc7-4940-8785-0863f01b6e42',
                                'f4b75f60-a150-404c-b139-e85b84b04bfe',
                                'fa93e3b9-fe40-4a1c-be89-536969a54f2c')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Ophthalmological Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1285')),
     "Condition: Diabetic Retinopathy (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.327')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Communication: Macular edema absent (situation) (communicationnotdone)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Communication'
     AND in_valueset(r.resource, 'category', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.2.1391')
     AND fhirpath_text(r.resource, 'status') = 'not-done'),
     "Communication: Macular Edema Findings Present" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Communication'
     AND in_valueset(r.resource, 'category', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1320')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-communicationnotdone'))),
     "Encounter: Care Services in Long-Term Residential Facility" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1014')),
     "Communication: Level of Severity of Retinopathy Findings (communicationnotdone)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Communication'
     AND in_valueset(r.resource, 'category', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1283')
     AND fhirpath_text(r.resource, 'status') = 'not-done'),
     "Communication: Macular Edema Findings Present (communicationnotdone)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Communication'
     AND in_valueset(r.resource, 'category', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1320')
     AND fhirpath_text(r.resource, 'status') = 'not-done'),
     "Encounter: Outpatient Consultation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1008')),
     "Communication: Level of Severity of Retinopathy Findings" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Communication'
     AND in_valueset(r.resource, 'category', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1283')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-communicationnotdone'))),
     "Observation: Macular Exam" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1251')),
     "Communication: Macular edema absent (situation)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Communication'
     AND in_valueset(r.resource, 'category', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.2.1391')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-communicationnotdone'))),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
     "Condition: Diabetic Retinopathy (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.327')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Encounter: Nursing Facility Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1012')),
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
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Encounter: Office Visit"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Ophthalmological Services"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Outpatient Consultation"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Care Services in Long-Term Residential Facility"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Nursing Facility Visit") AS QualifyingEncounter
   WHERE CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(QualifyingEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(QualifyingEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND fhirpath_text(QualifyingEncounter.resource, 'status') = 'finished'
     AND NOT fhirpath_bool(QualifyingEncounter.resource, 'class.where(system=''http://terminology.hl7.org/CodeSystem/v3-ActCode'' and code=''VR'').exists()')),
     "Diabetic Retinopathy Encounter" AS
  (SELECT *
   FROM "Qualifying Encounter During Day of Measurement Period" AS ValidQualifyingEncounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Condition: Diabetic Retinopathy (qicore-condition-problems-health-concerns)"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Condition: Diabetic Retinopathy (qicore-condition-encounter-diagnosis)") AS DiabeticRetinopathy
        WHERE CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                       WHEN fhirpath_text(DiabeticRetinopathy.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')), fhirpath_text(DiabeticRetinopathy.resource, 'abatementDateTime'), TRUE, TRUE)
                                                       WHEN COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                                       WHEN fhirpath_bool(DiabeticRetinopathy.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                                       ELSE intervalFromBounds(COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                                   END
                                                       ELSE NULL
                                                   END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(ValidQualifyingEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), LEFT(CAST('9999-12-31' AS VARCHAR), 10))
          AND COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(CASE
                                                              WHEN fhirpath_text(DiabeticRetinopathy.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')), fhirpath_text(DiabeticRetinopathy.resource, 'abatementDateTime'), TRUE, TRUE)
                                                              WHEN COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                                              WHEN fhirpath_bool(DiabeticRetinopathy.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                                              ELSE intervalFromBounds(COALESCE(fhirpath_text(DiabeticRetinopathy.resource, 'onsetDateTime'), fhirpath_text(DiabeticRetinopathy.resource, 'onsetPeriod.start'), fhirpath_text(DiabeticRetinopathy.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                                          END
                                                              ELSE NULL
                                                          END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), LEFT(CAST('9999-12-31' AS VARCHAR), 10)) >= CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(ValidQualifyingEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND (fhirpath_bool(DiabeticRetinopathy.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''active'').exists()')
               OR fhirpath_bool(DiabeticRetinopathy.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''recurrence'').exists()')
               OR fhirpath_bool(DiabeticRetinopathy.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''relapse'').exists()'))
          AND NOT (fhirpath_bool(DiabeticRetinopathy.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''unconfirmed'').exists()')
                   OR fhirpath_bool(DiabeticRetinopathy.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()')
                   OR fhirpath_bool(DiabeticRetinopathy.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''entered-in-error'').exists()'))
          AND DiabeticRetinopathy.patient_id = ValidQualifyingEncounter.patient_id)),
     "Initial Population" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXTRACT(YEAR
                 FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) - EXTRACT(YEAR
                                                                                                                                                                    FROM TRY_CAST(
                                                                                                                                                                                    (SELECT _pd.birth_date
                                                                                                                                                                                     FROM _patient_demographics AS _pd
                                                                                                                                                                                     WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                     LIMIT 1) AS TIMESTAMP)) - CASE
                                                                                                                                                                                                                   WHEN EXTRACT(MONTH
                                                                                                                                                                                                                                FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                                                                   FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                                                                   (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                                    FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                                    WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                                                                                                                                                                                                                                    LIMIT 1) AS TIMESTAMP))
                                                                                                                                                                                                                        OR EXTRACT(MONTH
                                                                                                                                                                                                                                   FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                                                                      FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                                                                      (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                                       FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                                       WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                                                                                                                                                                                                                                       LIMIT 1) AS TIMESTAMP))
                                                                                                                                                                                                                        AND EXTRACT(DAY
                                                                                                                                                                                                                                    FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                                                                                                                                                                                                                                       FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                                                                       (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                                        FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                                        WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                                                                                                                                                                                                                                        LIMIT 1) AS TIMESTAMP)) THEN 1
                                                                                                                                                                                                                   ELSE 0
                                                                                                                                                                                                               END >= 18
     AND EXISTS
       (SELECT 1
        FROM "Diabetic Retinopathy Encounter" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Level of Severity of Retinopathy Findings Communicated" AS
  (SELECT *
   FROM "Communication: Level of Severity of Retinopathy Findings" AS LevelOfSeverityCommunicated
   WHERE fhirpath_text(LevelOfSeverityCommunicated.resource, 'status') = 'completed'
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE cqlAfter(CAST(fhirpath_text(LevelOfSeverityCommunicated.resource, 'sent') AS VARCHAR), CAST(intervalStart(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period')) AS VARCHAR))
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(LevelOfSeverityCommunicated.resource, 'sent') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(LevelOfSeverityCommunicated.resource, 'sent') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND EncounterDiabeticRetinopathy.patient_id = LevelOfSeverityCommunicated.patient_id)),
     "Macular Edema Absence Communicated" AS
  (SELECT *
   FROM "Communication: Macular edema absent (situation)" AS MacularEdemaAbsentCommunicated
   WHERE fhirpath_text(MacularEdemaAbsentCommunicated.resource, 'status') = 'completed'
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE cqlAfter(CAST(fhirpath_text(MacularEdemaAbsentCommunicated.resource, 'sent') AS VARCHAR), CAST(intervalStart(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period')) AS VARCHAR))
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(MacularEdemaAbsentCommunicated.resource, 'sent') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(MacularEdemaAbsentCommunicated.resource, 'sent') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND EncounterDiabeticRetinopathy.patient_id = MacularEdemaAbsentCommunicated.patient_id)),
     "Macular Edema Presence Communicated" AS
  (SELECT *
   FROM "Communication: Macular Edema Findings Present" AS MacularEdemaPresentCommunicated
   WHERE fhirpath_text(MacularEdemaPresentCommunicated.resource, 'status') = 'completed'
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE cqlAfter(CAST(fhirpath_text(MacularEdemaPresentCommunicated.resource, 'sent') AS VARCHAR), CAST(intervalStart(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period')) AS VARCHAR))
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(MacularEdemaPresentCommunicated.resource, 'sent') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(MacularEdemaPresentCommunicated.resource, 'sent') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND EncounterDiabeticRetinopathy.patient_id = MacularEdemaPresentCommunicated.patient_id)),
     "Macular Exam Performed" AS
  (SELECT *
   FROM "Observation: Macular Exam" AS MacularExam
   WHERE MacularExam.value IS NOT NULL
     AND array_contains(['final', 'amended', 'corrected', 'preliminary'], MacularExam.status)
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE intervalIncludes(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period'), CASE
                                                                                                   WHEN fhirpath_text(MacularExam.resource, 'effective') IS NULL THEN NULL
                                                                                                   WHEN starts_with(LTRIM(fhirpath_text(MacularExam.resource, 'effective')), '{') THEN fhirpath_text(MacularExam.resource, 'effective')
                                                                                                   ELSE intervalFromBounds(fhirpath_text(MacularExam.resource, 'effective'), fhirpath_text(MacularExam.resource, 'effective'), TRUE, TRUE)
                                                                                               END)
          AND EncounterDiabeticRetinopathy.patient_id = MacularExam.patient_id)),
     "Denominator" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Initial Population" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND EXISTS
       (SELECT 1
        FROM "Macular Exam Performed" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Medical or Patient Reason for Not Communicating Absence of Macular Edema" AS
  (SELECT *
   FROM "Communication: Macular edema absent (situation) (communicationnotdone)" AS MacularEdemaAbsentNotCommunicated
   WHERE (in_valueset(MacularEdemaAbsentNotCommunicated.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1007')
          OR in_valueset(MacularEdemaAbsentNotCommunicated.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1008'))
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE intervalContains(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period'), fhirpath_text(MacularEdemaAbsentNotCommunicated.resource, 'sent'))
          AND EncounterDiabeticRetinopathy.patient_id = MacularEdemaAbsentNotCommunicated.patient_id)),
     "Medical or Patient Reason for Not Communicating Level of Severity of Retinopathy" AS
  (SELECT *
   FROM "Communication: Level of Severity of Retinopathy Findings (communicationnotdone)" AS LevelOfSeverityNotCommunicated
   WHERE (in_valueset(LevelOfSeverityNotCommunicated.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1007')
          OR in_valueset(LevelOfSeverityNotCommunicated.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1008'))
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE intervalContains(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period'), fhirpath_text(LevelOfSeverityNotCommunicated.resource, 'sent'))
          AND EncounterDiabeticRetinopathy.patient_id = LevelOfSeverityNotCommunicated.patient_id)),
     "Medical or Patient Reason for Not Communicating Presence of Macular Edema" AS
  (SELECT *
   FROM "Communication: Macular Edema Findings Present (communicationnotdone)" AS MacularEdemaPresentNotCommunicated
   WHERE (in_valueset(MacularEdemaPresentNotCommunicated.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1007')
          OR in_valueset(MacularEdemaPresentNotCommunicated.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1008'))
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Diabetic Retinopathy Encounter") AS EncounterDiabeticRetinopathy
        WHERE intervalContains(fhirpath_text(EncounterDiabeticRetinopathy.resource, 'period'), fhirpath_text(MacularEdemaPresentNotCommunicated.resource, 'sent'))
          AND EncounterDiabeticRetinopathy.patient_id = MacularEdemaPresentNotCommunicated.patient_id)),
     "Denominator Exceptions" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Medical or Patient Reason for Not Communicating Level of Severity of Retinopathy" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "Medical or Patient Reason for Not Communicating Absence of Macular Edema" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "Medical or Patient Reason for Not Communicating Presence of Macular Edema" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Numerator" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Level of Severity of Retinopathy Findings Communicated" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND (EXISTS
            (SELECT 1
             FROM "Macular Edema Absence Communicated" AS sub
             WHERE sub.patient_id = p.patient_id)
          OR EXISTS
            (SELECT 1
             FROM "Macular Edema Presence Communicated" AS sub
             WHERE sub.patient_id = p.patient_id))),
     "Results of Dilated Macular or Fundus Exam Communicated" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Level of Severity of Retinopathy Findings Communicated" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND (EXISTS
            (SELECT 1
             FROM "Macular Edema Absence Communicated" AS sub
             WHERE sub.patient_id = p.patient_id)
          OR EXISTS
            (SELECT 1
             FROM "Macular Edema Presence Communicated" AS sub
             WHERE sub.patient_id = p.patient_id))),
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
              WHEN "Denominator Exceptions".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS "Denominator Exceptions",

  (SELECT CASE
              WHEN "Numerator".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS Numerator
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Denominator Exceptions" ON p.patient_id = "Denominator Exceptions".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id ASC
