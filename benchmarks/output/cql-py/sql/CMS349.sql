-- Generated SQL for CMS349

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('010e7c7c-3767-4d0c-8b1d-935c1e451ad0',
                                '050401cc-5f7b-432a-8194-11702adede21',
                                '0dd2c81f-19b8-495b-acdf-196a2207b376',
                                '15d4c0f3-e862-4b06-9ed0-7a572b901aba',
                                '161e8e14-fea4-47c4-b752-b90e047697ea',
                                '18ad99cd-c0b1-48c9-ab0b-bb3ab66e1c18',
                                '198a8ffe-cd3f-45f7-931b-897796c67247',
                                '1d082b9c-26b3-4f59-b7f9-6f206c594506',
                                '1d47538d-c090-48eb-8d0b-0ed7e86ebbfd',
                                '243bc4d8-841e-4760-a65b-13013bf5204c',
                                '2f132a6c-2ec6-4553-9d90-d3e7dc19de26',
                                '35a14482-f089-4578-81ef-52dfebf9e77d',
                                '40677ab0-38af-4fe1-8cc0-bcd41c14d37d',
                                '41abc473-f005-4664-aa67-773f9b2f77e7',
                                '5e4b8bcc-7354-4513-8c9e-61c59bf7c2fc',
                                '64e863bc-02b5-46cc-8c27-57df7cebfcaf',
                                '720428de-44f9-48d8-86c9-262b6bd5fa46',
                                '74e4451c-12d0-4e5b-8f99-c9410766c3c4',
                                '7b9a4d0a-7465-45ac-932a-0aca2de75a3c',
                                '8a599e2b-f25b-4912-8369-cda93caaf351',
                                '8b1bcbaa-01df-486d-b243-9399e7515074',
                                '8bc5cedd-f265-49c4-be8e-d6a0a12b3752',
                                '90346970-2f5c-43aa-81ab-30e4f5d74830',
                                '9b6c9156-c4b5-46a1-8d47-d2d4998f44d3',
                                'a05a0ed5-b57d-4ce6-adc8-b4b9ec0403ae',
                                'af6febab-8963-49ea-86e4-72345024dc0b',
                                'b46e3e19-548e-481a-93a1-57973055ffad',
                                'b8161404-686d-4ce4-b291-e7a02ffe7b7e',
                                'bd10b739-a303-497c-8b23-e673bee363f5',
                                'df21795c-3269-4d4c-9173-0089d65a75d5',
                                'e2c3ca6d-c054-4245-b59c-12f83919cfaa',
                                'e48db8cc-afd4-47ea-846c-ee4f3794e5ea',
                                'e98529d7-5196-4523-bbc9-cbf48b5525d1',
                                'f24d0ae4-0daf-4f7e-85c8-679360f29219',
                                'f5a4440e-ff86-4d9a-807c-26dc21daad46',
                                'ffb7a0c4-fcef-46ff-9593-f3cebe574e21')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Preventive Care, Established Office Visit, 0 to 17" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1024')),
     "Condition: HIV (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.120.12.1003')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Observation: Human Immunodeficiency Virus (HIV) Laboratory Test Codes (Ab and Ag)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1056.50')),
     "Encounter: Preventive Care Services - Established Office Visit, 18 and Up" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1025')),
     "Condition: HIV (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.120.12.1003')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
     "Observation: HIV 1 and 2 tests - Meaningful Use set" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://loinc.org'' and code=''75622-1'').exists()')),
     "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1022')),
     "Encounter: Preventive Care Services-Initial Office Visit, 18 and Up" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1023')),
     "Coverage: Payer Type" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'type') AS "type"
   FROM resources r
   WHERE r.resourceType = 'Coverage'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591')),
     "Encounter: Encounter Inpatient" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.666.5.307')),
     "CQMCommon.Inpatient Encounter" AS
  (SELECT *
   FROM "Encounter: Encounter Inpatient" AS EncounterInpatient
   WHERE EncounterInpatient.status = 'finished'
     AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(EncounterInpatient.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) BETWEEN CAST(LEFT(REPLACE(CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AND COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), CAST(LEFT(REPLACE(CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))),
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
     "Denominator Exclusions" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Condition: HIV (qicore-condition-problems-health-concerns)"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Condition: HIV (qicore-condition-encounter-diagnosis)") AS HIVDiagnosis
        WHERE HIVDiagnosis.patient_id = p.patient_id
          AND intervalStart(CASE
                                WHEN fhirpath_text(HIVDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')), fhirpath_text(HIVDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                WHEN COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                           WHEN fhirpath_bool(HIVDiagnosis.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                           ELSE intervalFromBounds(COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                       END
                                ELSE NULL
                            END) < CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND NOT fhirpath_bool(HIVDiagnosis.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()'))),
     "Has HIV Test Performed" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Observation: Human Immunodeficiency Virus (HIV) Laboratory Test Codes (Ab and Ag)"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Observation: HIV 1 and 2 tests - Meaningful Use set") AS HIVTest
        WHERE HIVTest.patient_id = p.patient_id
          AND fhirpath_text(HIVTest.resource, 'value') IS NOT NULL
          AND EXTRACT(YEAR
                      FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                             WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                             WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                             ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                         END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) - EXTRACT(YEAR
                                                                                                                                               FROM TRY_CAST(
                                                                                                                                                               (SELECT _pd.birth_date
                                                                                                                                                                FROM _patient_demographics AS _pd
                                                                                                                                                                WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                LIMIT 1) AS TIMESTAMP)) - CASE
                                                                                                                                                                                              WHEN EXTRACT(MONTH
                                                                                                                                                                                                           FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                                                                                                                                                                                                                  WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                  WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                                                                                                                                                                                                                  ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                              END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                    FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                    (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                     FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                     WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                                                                                                                                                                                                     LIMIT 1) AS TIMESTAMP))
                                                                                                                                                                                                   OR EXTRACT(MONTH
                                                                                                                                                                                                              FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                                                                                                                                                                                                                     WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                     WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                                                                                                                                                                                                                     ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                                 END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                       FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                       (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                        FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                        WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                                                                                                                                                                                                        LIMIT 1) AS TIMESTAMP))
                                                                                                                                                                                                   AND EXTRACT(DAY
                                                                                                                                                                                                               FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                                                                                                                                                                                                                      WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                      WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                                                                                                                                                                                                                      ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                                  END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                                                                                                                                                                                        FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                        (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                         FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                         WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                                                                                                                                                                                                         LIMIT 1) AS TIMESTAMP)) THEN 1
                                                                                                                                                                                              ELSE 0
                                                                                                                                                                                          END BETWEEN 15 AND 65
          AND intervalStart(CASE
                                WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                            END) < CAST('2026-12-31T23:59:59.999' AS VARCHAR)
          AND (fhirpath_text(HIVTest.resource, 'status') = 'final'
               OR fhirpath_text(HIVTest.resource, 'status') = 'amended'
               OR fhirpath_text(HIVTest.resource, 'status') = 'corrected'))),
     "Numerator" AS
  (SELECT *
   FROM "Has HIV Test Performed"),
     "Patient Expired" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE cqlSameOrBefore(CAST(fhirpath_text(
                                              (SELECT _pd.resource
                                               FROM _patient_demographics AS _pd
                                               WHERE _pd.patient_id = p.patient_id
                                               LIMIT 1), 'deceased') AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR))),
     "Denominator Exceptions" AS
  (SELECT *
   FROM "Patient Expired"),
     "Qualifying Encounters" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Preventive Care Services-Initial Office Visit, 18 and Up"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Preventive Care, Established Office Visit, 0 to 17"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Preventive Care Services - Established Office Visit, 18 and Up"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Office Visit") AS Encounter
   WHERE CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND fhirpath_text(Encounter.resource, 'status') = 'finished'),
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
                                                                                                                                                                                                               END BETWEEN 15 AND 65
     AND EXISTS
       (SELECT 1
        FROM "Qualifying Encounters" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Denominator" AS
  (SELECT *
   FROM "Initial Population"),
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
              WHEN "Denominator Exclusions".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS "Denominator Exclusions",

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
LEFT JOIN "Denominator Exclusions" ON p.patient_id = "Denominator Exclusions".patient_id
LEFT JOIN "Denominator Exceptions" ON p.patient_id = "Denominator Exceptions".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id ASC
