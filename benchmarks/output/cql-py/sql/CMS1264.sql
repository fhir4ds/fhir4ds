-- Generated SQL for CMS1264

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('01959faf-5ea5-41cb-b960-b74da18cca85',
                                '040dc7b1-27f9-43a3-82c9-b1a514db3071',
                                '11703274-1218-440d-bb98-08502a794179',
                                '16cffb87-15ea-48b7-bd68-f211f48d6f19',
                                '1f8035de-4255-434e-a32f-b97039ec57ff',
                                '21b841f6-b863-4c1d-8798-41c527b04a92',
                                '2c2a7958-4d1a-4142-9360-8045067a1c5b',
                                '2fc54731-4fd9-4884-aba5-9a8385111375',
                                '3302c6ff-8767-4be7-9c81-f1d98351b247',
                                '35fd427f-1233-4f3c-b8b3-9e400755da8f',
                                '404c928b-a752-4792-91c4-8a1fd0656759',
                                '42be9d46-4c2f-4493-8299-d33dcbb7170e',
                                '4c95d881-2e7e-4e81-bb4c-b1ae680ff286',
                                '50270eff-f1ed-4cb3-b22b-467d89937c3a',
                                '540b665b-e89c-466a-9ef8-758b3883a37c',
                                '5ae9589c-1301-45a0-af30-ac7b679b649f',
                                '5fb0b78c-ffd3-47c3-91a3-252bc4a70177',
                                '6252a858-2362-4c63-8d7d-6db0b7ac9299',
                                '63cea3d6-d2e0-4736-a035-87633ca960bd',
                                '666528ac-0d94-4b09-8e6c-c5930b7dd17c',
                                '66803f75-5dc5-43fb-9844-f18d765a64ec',
                                '74855a5c-bb3b-438a-9eb9-7fdc1994d06d',
                                '78cbc6ac-f30d-404b-b539-6b903c7cfeba',
                                '7bcd79b7-7898-437d-b563-cfb9068df210',
                                '7bee402e-2687-4813-9b39-37d723663d18',
                                '7dd19e80-23c6-4e31-86a9-bb833cfc676b',
                                '7fbb7e37-228b-4b3b-8974-871a3e798720',
                                '7fd4f9cd-8fbb-4935-9bfd-959c538166b2',
                                '8e43bc64-4242-494d-b47f-fdbbd3372bbe',
                                '9098f676-4f4e-402c-80e3-331aabb6d414',
                                '9b5e4d84-366b-4082-8409-b7e18e0a3c45',
                                '9bac5045-01af-4350-b54f-63ab17f3ba9f',
                                '9ec1a135-fb47-4c1c-8f6b-98afab15274e',
                                '9f77830b-ff7c-4060-bf38-295b215ab56d',
                                'a11dce52-c6b3-46e5-bc01-8994b0c8f471',
                                'a3dd602c-cd84-4e7a-aa37-eae4b15fdf4e',
                                'a42d4cc2-24ca-4637-889f-276bcdd1e7cf',
                                'ae6b86ec-3d29-4e35-88dc-57f997814f47',
                                'b312fbc9-083f-4832-8d7c-d3e64df4145b',
                                'c3284314-fe9b-408a-9b26-a21830f84432',
                                'cc00e728-de5f-4df8-abcb-1e610496be66',
                                'cc01e29c-7ebb-4876-b63a-29de550c62f9',
                                'cee26b56-54cf-444e-8944-6edfbd6d2b93',
                                'd3a7a6b7-bbbc-4c08-bd8c-ce1e1cbdc8a8',
                                'd5fe6f9c-6036-4004-9993-290f3a2be34a',
                                'd8832769-c838-4f1b-9c1e-fa4ed3a3efb9',
                                'dac89c3d-536e-4dca-9871-570a0bcd8d16',
                                'dad5b672-1e5b-437c-91fe-1f69b5d58c70',
                                'dfd5dc6b-3299-4e4f-ae02-45f251e1f75b',
                                'e982ec87-76b0-4fe2-b437-ac0503cf2159',
                                'eabe386d-5bca-4fdd-acb0-8228b4df83c0',
                                'ed5fa616-8b70-4016-b40d-6f87983e2776',
                                'ee13a2d8-61d9-4d2f-8f13-1423bd271950')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "ServiceRequest: Decision to Transfer" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'authoredOn') AS authored_date,
                   fhirpath_text(r.resource, 'intent') AS intent,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'ServiceRequest'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.286')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
     "Encounter: Triage" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.279')),
     "Location" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Location'),
     "Encounter: Emergency Department Evaluation and Management Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1010')),
     "Encounter: Observation Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1111.143')),
     "Encounter: Encounter Inpatient" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.666.5.307')),
     "Coverage: Payer Type" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'type') AS "type"
   FROM resources r
   WHERE r.resourceType = 'Coverage'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591')),
     "CQMCommon.Inpatient Encounter" AS
  (SELECT *
   FROM "Encounter: Encounter Inpatient" AS EncounterInpatient
   WHERE EncounterInpatient.status = 'finished'
     AND CAST(intervalEnd(fhirpath_text(EncounterInpatient.resource, 'period')) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))),
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
     "ED Evaluation and Management" AS
  (SELECT *
   FROM "Encounter: Emergency Department Evaluation and Management Visit" AS EDEvalManagementVisit
   WHERE CAST(intervalEnd(fhirpath_text(EDEvalManagementVisit.resource, 'period')) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     AND EDEvalManagementVisit.status = 'finished'),
     "ED Triage" AS
  (SELECT *
   FROM "Encounter: Triage" AS EDTriage
   WHERE CAST(intervalEnd(fhirpath_text(EDTriage.resource, 'period')) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2027-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2027-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     AND array_contains(['finished', 'triaged'], EDTriage.status)),
     "ED Triage Excluding Those Prior To ED Encounters" AS
  (SELECT *
   FROM "ED Triage" AS EDTriageinMP
   WHERE NOT EXISTS
       (SELECT *
        FROM "ED Evaluation and Management" AS EDEvalManagementinMP
        WHERE (intervalOverlapsBefore(fhirpath_text(EDTriageinMP.resource, 'period'), fhirpath_text(EDEvalManagementinMP.resource, 'period'))
               OR intervalIncludes(fhirpath_text(EDEvalManagementinMP.resource, 'period'), fhirpath_text(EDTriageinMP.resource, 'period'))
               OR intervalIncludes(fhirpath_text(EDTriageinMP.resource, 'period'), fhirpath_text(EDEvalManagementinMP.resource, 'period'))
               OR CAST(intervalStart(fhirpath_text(EDEvalManagementinMP.resource, 'period')) AS TIMESTAMP) - INTERVAL '120 minute' <= CAST(intervalEnd(fhirpath_text(EDTriageinMP.resource, 'period')) AS TIMESTAMP)
               AND CAST(intervalEnd(fhirpath_text(EDTriageinMP.resource, 'period')) AS TIMESTAMP) < CAST(intervalStart(fhirpath_text(EDEvalManagementinMP.resource, 'period')) AS TIMESTAMP))
          AND EDEvalManagementinMP.patient_id = EDTriageinMP.patient_id)),
     "Initial Population" AS (
                                (SELECT patient_id,
                                        RESOURCE
                                 FROM "ED Evaluation and Management")
                              UNION
                                (SELECT patient_id,
                                        RESOURCE
                                 FROM "ED Triage Excluding Those Prior To ED Encounters")),
     "Denominator" AS
  (SELECT *
   FROM "Initial Population"),
     "ED Arrival Left Without Being Seen" AS
  (SELECT *
   FROM "Denominator" AS EDEncounter
   WHERE fhirpath_bool(EDEncounter.resource, 'hospitalization.dischargeDisposition.coding.where(system=''http://snomed.info/sct'' and code=''21541000119102'').exists()')),
     "ED Encounter or Triage of Patients 18 Years and Older" AS
  (SELECT *
   FROM "Denominator" AS EDEncounter
   WHERE EXTRACT(YEAR
                 FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) - EXTRACT(YEAR
                                                                                                            FROM
                                                                                                              (SELECT _pd.birth_date
                                                                                                               FROM _patient_demographics AS _pd
                                                                                                               WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                               LIMIT 1)) - CASE
                                                                                                                               WHEN EXTRACT(MONTH
                                                                                                                                            FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) < EXTRACT(MONTH
                                                                                                                                                                                                                                       FROM
                                                                                                                                                                                                                                         (SELECT _pd.birth_date
                                                                                                                                                                                                                                          FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                          WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                          LIMIT 1))
                                                                                                                                    OR EXTRACT(MONTH
                                                                                                                                               FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) = EXTRACT(MONTH
                                                                                                                                                                                                                                          FROM
                                                                                                                                                                                                                                            (SELECT _pd.birth_date
                                                                                                                                                                                                                                             FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                             WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                             LIMIT 1))
                                                                                                                                    AND EXTRACT(DAY
                                                                                                                                                FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) < EXTRACT(DAY
                                                                                                                                                                                                                                           FROM
                                                                                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                              WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                              LIMIT 1)) THEN 1
                                                                                                                               ELSE 0
                                                                                                                           END >= 18),
     "Adult With Mental Health Diagnosis" AS
  (SELECT *
   FROM "ED Encounter or Triage of Patients 18 Years and Older" AS AdultEDEncounters
   WHERE EXISTS
       (SELECT '1'
        FROM
          (SELECT patient_ref AS patient_id,
                  RESOURCE
           FROM resources
           WHERE resourceType = 'Claim') AS _c
        WHERE _c.patient_id = AdultEDEncounters.patient_id
          AND fhirpath_text(_c.resource, 'status') = 'active'
          AND fhirpath_text(_c.resource, 'use') = 'claim'
          AND claim_principal_diagnosis(_c.resource, fhirpath_text(AdultEDEncounters.resource, 'id')) IS NOT NULL
          AND (in_valueset(claim_principal_diagnosis(_c.resource, fhirpath_text(AdultEDEncounters.resource, 'id')), 'diagnosisCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
               OR EXISTS
                 (SELECT '1'
                  FROM
                    (SELECT patient_ref AS patient_id,
                            RESOURCE
                     FROM resources
                     WHERE resourceType = 'Condition') AS _cond
                  WHERE _cond.patient_id = AdultEDEncounters.patient_id
                    AND in_valueset(_cond.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
                    AND fhirpath_text(claim_principal_diagnosis(_c.resource, fhirpath_text(AdultEDEncounters.resource, 'id')), 'diagnosisReference.reference') LIKE '%/' || fhirpath_text(_cond.resource, 'id'))))),
     "Adult With No Mental Health Diagnosis" AS
  (SELECT *
   FROM "ED Encounter or Triage of Patients 18 Years and Older" AS AdultEDEncounters
   WHERE NOT EXISTS
       (SELECT '1'
        FROM
          (SELECT patient_ref AS patient_id,
                  RESOURCE
           FROM resources
           WHERE resourceType = 'Claim') AS _c
        WHERE _c.patient_id = AdultEDEncounters.patient_id
          AND fhirpath_text(_c.resource, 'status') = 'active'
          AND fhirpath_text(_c.resource, 'use') = 'claim'
          AND claim_principal_diagnosis(_c.resource, fhirpath_text(AdultEDEncounters.resource, 'id')) IS NOT NULL
          AND (in_valueset(claim_principal_diagnosis(_c.resource, fhirpath_text(AdultEDEncounters.resource, 'id')), 'diagnosisCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
               OR EXISTS
                 (SELECT '1'
                  FROM
                    (SELECT patient_ref AS patient_id,
                            RESOURCE
                     FROM resources
                     WHERE resourceType = 'Condition') AS _cond
                  WHERE _cond.patient_id = AdultEDEncounters.patient_id
                    AND in_valueset(_cond.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
                    AND fhirpath_text(claim_principal_diagnosis(_c.resource, fhirpath_text(AdultEDEncounters.resource, 'id')), 'diagnosisReference.reference') LIKE '%/' || fhirpath_text(_cond.resource, 'id'))))),
     "ED Encounter or Triage of Patients Less Than 18 Years" AS
  (SELECT *
   FROM "Denominator" AS EDEncounter
   WHERE EXTRACT(YEAR
                 FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) - EXTRACT(YEAR
                                                                                                            FROM
                                                                                                              (SELECT _pd.birth_date
                                                                                                               FROM _patient_demographics AS _pd
                                                                                                               WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                               LIMIT 1)) - CASE
                                                                                                                               WHEN EXTRACT(MONTH
                                                                                                                                            FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) < EXTRACT(MONTH
                                                                                                                                                                                                                                       FROM
                                                                                                                                                                                                                                         (SELECT _pd.birth_date
                                                                                                                                                                                                                                          FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                          WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                          LIMIT 1))
                                                                                                                                    OR EXTRACT(MONTH
                                                                                                                                               FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) = EXTRACT(MONTH
                                                                                                                                                                                                                                          FROM
                                                                                                                                                                                                                                            (SELECT _pd.birth_date
                                                                                                                                                                                                                                             FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                             WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                             LIMIT 1))
                                                                                                                                    AND EXTRACT(DAY
                                                                                                                                                FROM CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE)) < EXTRACT(DAY
                                                                                                                                                                                                                                           FROM
                                                                                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                              WHERE _pd.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                              LIMIT 1)) THEN 1
                                                                                                                               ELSE 0
                                                                                                                           END < 18),
     "ED Observation Status" AS
  (SELECT *
   FROM "Encounter: Observation Services" AS EDObsEncounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Denominator") AS EDStay
        WHERE intervalIncludes(fhirpath_text(EDStay.resource, 'period'), fhirpath_text(EDObsEncounter.resource, 'period'))
          AND fhirpath_text(EDObsEncounter.resource, 'status') = 'finished'
          AND EDStay.patient_id = EDObsEncounter.patient_id)),
     "ED Triage Before Evaluation Management" AS
  (SELECT *
   FROM "ED Triage" AS EDTriageinMP
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Denominator") AS EDEncounter
        WHERE (intervalOverlapsBefore(fhirpath_text(EDTriageinMP.resource, 'period'), fhirpath_text(EDEncounter.resource, 'period'))
               OR intervalIncludes(fhirpath_text(EDEncounter.resource, 'period'), fhirpath_text(EDTriageinMP.resource, 'period'))
               OR intervalIncludes(fhirpath_text(EDTriageinMP.resource, 'period'), fhirpath_text(EDEncounter.resource, 'period'))
               OR CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '120 minute' <= CAST(intervalEnd(fhirpath_text(EDTriageinMP.resource, 'period')) AS TIMESTAMP)
               AND CAST(intervalEnd(fhirpath_text(EDTriageinMP.resource, 'period')) AS TIMESTAMP) < CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP))
          AND EDEncounter.patient_id = EDTriageinMP.patient_id)),
     "ED Triage and Evaluation Management" AS (
                                                 (SELECT patient_id,
                                                         RESOURCE
                                                  FROM "Denominator")
                                               UNION
                                                 (SELECT patient_id,
                                                         RESOURCE
                                                  FROM "ED Triage Before Evaluation Management")),
     "Boarded Time Greater Than 240 Minutes" AS
  (SELECT *
   FROM "Denominator" AS EDEncounter
   WHERE CAST(
                (SELECT fhirpath_text(TransferOrder.resource, 'authoredOn')
                 FROM "ServiceRequest: Decision to Transfer" AS TransferOrder
                 WHERE intervalContains(fhirpath_text(EDEncounter.resource, 'period'), fhirpath_text(TransferOrder.resource, 'authoredOn'))
                   AND fhirpath_text(TransferOrder.resource, 'intent') = 'order'
                   AND array_contains(['active', 'completed'], fhirpath_text(TransferOrder.resource, 'status'))
                   AND TransferOrder.patient_id = EDEncounter.patient_id
                 ORDER BY fhirpath_text(TransferOrder.resource, 'authoredOn') DESC NULLS FIRST, json_extract_string(TransferOrder.resource, '$.id') ASC NULLS LAST
                 LIMIT 1) AS TIMESTAMP) <= CAST(list_extract(list_sort(
                                                                         (SELECT list(intervalEnd(fhirpath_text(_lt_Location, 'period')))
                                                                          FROM
                                                                            (SELECT unnest(from_json(fhirpath(_bb_Location.resource, 'location'), '["VARCHAR"]')) AS _lt_Location
                                                                             FROM "ED Triage and Evaluation Management" AS _bb_Location
                                                                             WHERE _bb_Location.patient_id = EDEncounter.patient_id) AS _bb_unnest
                                                                          WHERE in_valueset(CASE
                                                                                                WHEN
                                                                                                       (SELECT COUNT(*)
                                                                                                        FROM "Location" AS L
                                                                                                        WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                                                          AND L.patient_id = EDEncounter.patient_id) = 1 THEN
                                                                                                       (SELECT RESOURCE
                                                                                                        FROM "Location" AS L
                                                                                                        WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                                                          AND L.patient_id = EDEncounter.patient_id
                                                                                                        LIMIT 1)
                                                                                                ELSE NULL
                                                                                            END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.284')
                                                                            AND intervalEnd(fhirpath_text(_lt_Location, 'period')) IS NOT NULL
                                                                            AND (CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '120 minute' <= CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP)
                                                                                 AND CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP) < CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP)
                                                                                 OR intervalOverlapsBefore(fhirpath_text(_lt_Location, 'period'), fhirpath_text(EDEncounter.resource, 'period'))
                                                                                 OR intervalOverlapsBefore(fhirpath_text(EDEncounter.resource, 'period'), fhirpath_text(_lt_Location, 'period'))
                                                                                 OR CAST(intervalStart(fhirpath_text(_lt_Location, 'period')) AS DATE) = CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE))), 'asc'), -1) AS TIMESTAMP) - INTERVAL '241 minute'),
     "Boarded Time Greater Than 240 Minutes and No Observation Stay" AS
  (SELECT *
   FROM "Boarded Time Greater Than 240 Minutes" AS Boarding
   WHERE NOT EXISTS
       (SELECT *
        FROM "ED Observation Status" AS EDO
        WHERE intervalIncludes(fhirpath_text(Boarding.resource, 'period'), fhirpath_text(EDO.resource, 'period'))
          AND EDO.patient_id = Boarding.patient_id)),
     "ED Length of Stay Greater Than 480 Minutes" AS
  (SELECT *
   FROM "Denominator" AS EDEncounter
   WHERE CAST(list_extract(list_sort(
                                       (SELECT list(intervalStart(fhirpath_text(_lt_Location, 'period')))
                                        FROM
                                          (SELECT unnest(from_json(fhirpath(_bb_Location.resource, 'location'), '["VARCHAR"]')) AS _lt_Location
                                           FROM "ED Triage and Evaluation Management" AS _bb_Location
                                           WHERE _bb_Location.patient_id = EDEncounter.patient_id) AS _bb_unnest
                                        WHERE in_valueset(CASE
                                                              WHEN
                                                                     (SELECT COUNT(*)
                                                                      FROM "Location" AS L
                                                                      WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                        AND L.patient_id = EDEncounter.patient_id) = 1 THEN
                                                                     (SELECT RESOURCE
                                                                      FROM "Location" AS L
                                                                      WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                        AND L.patient_id = EDEncounter.patient_id
                                                                      LIMIT 1)
                                                              ELSE NULL
                                                          END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.284')
                                          AND intervalStart(fhirpath_text(_lt_Location, 'period')) IS NOT NULL
                                          AND (CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '120 minute' <= CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP)
                                               AND CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP) < CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP)
                                               OR intervalOverlapsBefore(fhirpath_text(_lt_Location, 'period'), fhirpath_text(EDEncounter.resource, 'period'))
                                               OR intervalOverlapsBefore(fhirpath_text(EDEncounter.resource, 'period'), fhirpath_text(_lt_Location, 'period'))
                                               OR CAST(intervalStart(fhirpath_text(_lt_Location, 'period')) AS DATE) = CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE))), 'asc'), -1) AS TIMESTAMP) <= CAST(list_extract(list_sort(
                                                                                                                                                                                                                                                                (SELECT list(intervalEnd(fhirpath_text(_lt_Location, 'period')))
                                                                                                                                                                                                                                                                 FROM
                                                                                                                                                                                                                                                                   (SELECT unnest(from_json(fhirpath(_bb_Location.resource, 'location'), '["VARCHAR"]')) AS _lt_Location
                                                                                                                                                                                                                                                                    FROM "ED Triage and Evaluation Management" AS _bb_Location
                                                                                                                                                                                                                                                                    WHERE _bb_Location.patient_id = EDEncounter.patient_id) AS _bb_unnest
                                                                                                                                                                                                                                                                 WHERE in_valueset(CASE
                                                                                                                                                                                                                                                                                       WHEN
                                                                                                                                                                                                                                                                                              (SELECT COUNT(*)
                                                                                                                                                                                                                                                                                               FROM "Location" AS L
                                                                                                                                                                                                                                                                                               WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                                                                                                                                                                                                                                                 AND L.patient_id = EDEncounter.patient_id) = 1 THEN
                                                                                                                                                                                                                                                                                              (SELECT RESOURCE
                                                                                                                                                                                                                                                                                               FROM "Location" AS L
                                                                                                                                                                                                                                                                                               WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                                                                                                                                                                                                                                                 AND L.patient_id = EDEncounter.patient_id
                                                                                                                                                                                                                                                                                               LIMIT 1)
                                                                                                                                                                                                                                                                                       ELSE NULL
                                                                                                                                                                                                                                                                                   END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.284')
                                                                                                                                                                                                                                                                   AND intervalEnd(fhirpath_text(_lt_Location, 'period')) IS NOT NULL
                                                                                                                                                                                                                                                                   AND (CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '120 minute' <= CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                                                                        AND CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP) < CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                                                                        OR intervalOverlapsBefore(fhirpath_text(_lt_Location, 'period'), fhirpath_text(EDEncounter.resource, 'period'))
                                                                                                                                                                                                                                                                        OR intervalOverlapsBefore(fhirpath_text(EDEncounter.resource, 'period'), fhirpath_text(_lt_Location, 'period'))
                                                                                                                                                                                                                                                                        OR CAST(intervalStart(fhirpath_text(_lt_Location, 'period')) AS DATE) = CAST(intervalStart(fhirpath_text(EDEncounter.resource, 'period')) AS DATE))), 'asc'), -1) AS TIMESTAMP) - INTERVAL '481 minute'),
     "ED Length of Stay Greater Than 480 Minutes and No Observation Stay" AS
  (SELECT *
   FROM "ED Length of Stay Greater Than 480 Minutes" AS EDStay
   WHERE NOT EXISTS
       (SELECT *
        FROM "ED Observation Status" AS EDObs
        WHERE intervalIncludes(fhirpath_text(EDStay.resource, 'period'), fhirpath_text(EDObs.resource, 'period'))
          AND EDObs.patient_id = EDStay.patient_id)),
     "Pediatric With Mental Health Diagnosis" AS
  (SELECT *
   FROM "ED Encounter or Triage of Patients Less Than 18 Years" AS PediatricEDEncounters
   WHERE EXISTS
       (SELECT '1'
        FROM
          (SELECT patient_ref AS patient_id,
                  RESOURCE
           FROM resources
           WHERE resourceType = 'Claim') AS _c
        WHERE _c.patient_id = PediatricEDEncounters.patient_id
          AND fhirpath_text(_c.resource, 'status') = 'active'
          AND fhirpath_text(_c.resource, 'use') = 'claim'
          AND claim_principal_diagnosis(_c.resource, fhirpath_text(PediatricEDEncounters.resource, 'id')) IS NOT NULL
          AND (in_valueset(claim_principal_diagnosis(_c.resource, fhirpath_text(PediatricEDEncounters.resource, 'id')), 'diagnosisCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
               OR EXISTS
                 (SELECT '1'
                  FROM
                    (SELECT patient_ref AS patient_id,
                            RESOURCE
                     FROM resources
                     WHERE resourceType = 'Condition') AS _cond
                  WHERE _cond.patient_id = PediatricEDEncounters.patient_id
                    AND in_valueset(_cond.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
                    AND fhirpath_text(claim_principal_diagnosis(_c.resource, fhirpath_text(PediatricEDEncounters.resource, 'id')), 'diagnosisReference.reference') LIKE '%/' || fhirpath_text(_cond.resource, 'id'))))),
     "Pediatric With No Mental Health Diagnosis" AS
  (SELECT *
   FROM "ED Encounter or Triage of Patients Less Than 18 Years" AS PediatricEDEncounters
   WHERE NOT EXISTS
       (SELECT '1'
        FROM
          (SELECT patient_ref AS patient_id,
                  RESOURCE
           FROM resources
           WHERE resourceType = 'Claim') AS _c
        WHERE _c.patient_id = PediatricEDEncounters.patient_id
          AND fhirpath_text(_c.resource, 'status') = 'active'
          AND fhirpath_text(_c.resource, 'use') = 'claim'
          AND claim_principal_diagnosis(_c.resource, fhirpath_text(PediatricEDEncounters.resource, 'id')) IS NOT NULL
          AND (in_valueset(claim_principal_diagnosis(_c.resource, fhirpath_text(PediatricEDEncounters.resource, 'id')), 'diagnosisCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
               OR EXISTS
                 (SELECT '1'
                  FROM
                    (SELECT patient_ref AS patient_id,
                            RESOURCE
                     FROM resources
                     WHERE resourceType = 'Condition') AS _cond
                  WHERE _cond.patient_id = PediatricEDEncounters.patient_id
                    AND in_valueset(_cond.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.285')
                    AND fhirpath_text(claim_principal_diagnosis(_c.resource, fhirpath_text(PediatricEDEncounters.resource, 'id')), 'diagnosisReference.reference') LIKE '%/' || fhirpath_text(_cond.resource, 'id'))))),
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
   FROM "SDE.SDE Sex"),
     "Stratification 1" AS
  (SELECT *
   FROM "Pediatric With No Mental Health Diagnosis"),
     "Stratification 2" AS
  (SELECT *
   FROM "Adult With No Mental Health Diagnosis"),
     "Stratification 3" AS
  (SELECT *
   FROM "Pediatric With Mental Health Diagnosis"),
     "Stratification 4" AS
  (SELECT *
   FROM "Adult With Mental Health Diagnosis"),
     "Time to Treatment Room Greater Than 60 Minutes" AS
  (SELECT *
   FROM "ED Evaluation and Management" AS EDEvalManagementinMP
   WHERE CAST(list_extract(list_sort(
                                       (SELECT list(intervalStart(fhirpath_text(_lt_Location, 'period')))
                                        FROM
                                          (SELECT unnest(from_json(fhirpath(_bb_Location.resource, 'location'), '["VARCHAR"]')) AS _lt_Location
                                           FROM "ED Triage and Evaluation Management" AS _bb_Location
                                           WHERE _bb_Location.patient_id = EDEvalManagementinMP.patient_id) AS _bb_unnest
                                        WHERE in_valueset(CASE
                                                              WHEN
                                                                     (SELECT COUNT(*)
                                                                      FROM "Location" AS L
                                                                      WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                        AND L.patient_id = EDEvalManagementinMP.patient_id) = 1 THEN
                                                                     (SELECT RESOURCE
                                                                      FROM "Location" AS L
                                                                      WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                        AND L.patient_id = EDEvalManagementinMP.patient_id
                                                                      LIMIT 1)
                                                              ELSE NULL
                                                          END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.284')
                                          AND intervalStart(fhirpath_text(_lt_Location, 'period')) IS NOT NULL
                                          AND (CAST(intervalStart(fhirpath_text(EDEvalManagementinMP.resource, 'period')) AS TIMESTAMP) - INTERVAL '120 minute' <= CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP)
                                               AND CAST(intervalEnd(fhirpath_text(_lt_Location, 'period')) AS TIMESTAMP) < CAST(intervalStart(fhirpath_text(EDEvalManagementinMP.resource, 'period')) AS TIMESTAMP)
                                               OR intervalOverlapsBefore(fhirpath_text(_lt_Location, 'period'), fhirpath_text(EDEvalManagementinMP.resource, 'period'))
                                               OR intervalOverlapsBefore(fhirpath_text(EDEvalManagementinMP.resource, 'period'), fhirpath_text(_lt_Location, 'period'))
                                               OR CAST(intervalStart(fhirpath_text(_lt_Location, 'period')) AS DATE) = CAST(intervalStart(fhirpath_text(EDEvalManagementinMP.resource, 'period')) AS DATE))), 'asc'), -1) AS TIMESTAMP) <= CAST(list_extract(list_sort(
                                                                                                                                                                                                                                                                         (SELECT list(intervalStart(fhirpath_text(_lt_Location, 'period')))
                                                                                                                                                                                                                                                                          FROM
                                                                                                                                                                                                                                                                            (SELECT unnest(from_json(fhirpath(EDEvalManagementinMP.resource, 'location'), '["VARCHAR"]')) AS _lt_Location) AS _lt_unnest
                                                                                                                                                                                                                                                                          WHERE in_valueset(CASE
                                                                                                                                                                                                                                                                                                WHEN
                                                                                                                                                                                                                                                                                                       (SELECT COUNT(*)
                                                                                                                                                                                                                                                                                                        FROM "Location" AS L
                                                                                                                                                                                                                                                                                                        WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                                                                                                                                                                                                                                                          AND L.patient_id = EDEvalManagementinMP.patient_id) = 1 THEN
                                                                                                                                                                                                                                                                                                       (SELECT RESOURCE
                                                                                                                                                                                                                                                                                                        FROM "Location" AS L
                                                                                                                                                                                                                                                                                                        WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_Location, 'location.reference'), '/'), -1)
                                                                                                                                                                                                                                                                                                          AND L.patient_id = EDEvalManagementinMP.patient_id
                                                                                                                                                                                                                                                                                                        LIMIT 1)
                                                                                                                                                                                                                                                                                                ELSE NULL
                                                                                                                                                                                                                                                                                            END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1046.278')
                                                                                                                                                                                                                                                                            AND intervalStart(fhirpath_text(_lt_Location, 'period')) IS NOT NULL), 'asc'), 1) AS TIMESTAMP) - INTERVAL '61 minute'),
     "Numerator" AS (
                       (SELECT patient_id,
                               RESOURCE
                        FROM "Time to Treatment Room Greater Than 60 Minutes")
                     UNION
                       (SELECT patient_id,
                               RESOURCE
                        FROM "ED Arrival Left Without Being Seen")
                     UNION
                       (SELECT patient_id,
                               RESOURCE
                        FROM "Boarded Time Greater Than 240 Minutes and No Observation Stay")
                     UNION
                       (SELECT patient_id,
                               RESOURCE
                        FROM "ED Length of Stay Greater Than 480 Minutes and No Observation Stay"))
SELECT p.patient_id,

  (SELECT COALESCE(LIST(json_extract_string("Initial Population".resource, '$.resourceType') || '/' || json_extract_string("Initial Population".resource, '$.id')), [])
   FROM "Initial Population"
   WHERE "Initial Population".patient_id = p.patient_id
     AND "Initial Population".resource IS NOT NULL) AS "Initial Population",

  (SELECT COALESCE(LIST(json_extract_string("Denominator".resource, '$.resourceType') || '/' || json_extract_string("Denominator".resource, '$.id')), [])
   FROM "Denominator"
   WHERE "Denominator".patient_id = p.patient_id
     AND "Denominator".resource IS NOT NULL) AS Denominator,

  (SELECT COALESCE(LIST(json_extract_string("Numerator".resource, '$.resourceType') || '/' || json_extract_string("Numerator".resource, '$.id')), [])
   FROM "Numerator"
   WHERE "Numerator".patient_id = p.patient_id
     AND "Numerator".resource IS NOT NULL) AS Numerator
FROM _patients p
ORDER BY p.patient_id ASC
