-- Generated SQL for CMS157

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('18a871b4-b7d2-4fca-bd04-155b44965f4e',
                                '4bf7c1f5-8c25-4cd9-9ca8-d67e9f1283cb',
                                '6c1a8557-73be-4026-9ec6-f0699bfcbfda',
                                '91ebcd41-a1a5-45e0-95fd-e2a2799f4459',
                                'ba6d787f-d15f-4e22-8ee4-30c12d53aa37',
                                'bbdccaa6-f3a0-426d-8e77-eff43095cfc9',
                                'be20e6d8-f2f2-49d9-abc1-39e93ba36a1c',
                                'ea08cba3-e556-496e-8aab-3b1e6f58fda0',
                                'f0f73fe9-f8ae-4994-911f-1745e5efbce3',
                                'fe6ef07d-bff1-4e0e-9bf4-b0424a1d0ab4')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Audio Visual Telehealth Encounter" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.1444.5.215')),
     "Observation: Standardized Pain Assessment Tool" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1028')),
     "Encounter: Radiation Treatment Management" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1026')),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
     "Procedure: Chemotherapy Administration" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1027')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Condition: Cancer (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'abatementDateTime') AS abatement_date,
                   fhirpath_text(r.resource, 'onsetDateTime') AS onset_date,
                   fhirpath_text(r.resource, 'recordedDate') AS recorded_date
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1010')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
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
     "Chemotherapy Within 31 Days Prior and During Measurement Period" AS
  (SELECT *
   FROM "Procedure: Chemotherapy Administration" AS ChemoAdministration
   WHERE intervalIncludes(intervalFromBounds(CAST(dateSubtractQuantity(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), '{"value": 31.0, "unit": "day", "system": "http://unitsofmeasure.org"}') AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE), CASE
                                                                                                                                                                                                                                                                                                            WHEN fhirpath_text(ChemoAdministration.resource, 'performed') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                            WHEN starts_with(LTRIM(fhirpath_text(ChemoAdministration.resource, 'performed')), '{') THEN fhirpath_text(ChemoAdministration.resource, 'performed')
                                                                                                                                                                                                                                                                                                            ELSE intervalFromBounds(fhirpath_text(ChemoAdministration.resource, 'performed'), fhirpath_text(ChemoAdministration.resource, 'performed'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                        END)
     AND ChemoAdministration.status = 'completed'),
     "Face to Face or Telehealth Encounter with Ongoing Chemotherapy" AS
  (SELECT FaceToFaceOrTelehealthEncounter.patient_id,
          CAST(FaceToFaceOrTelehealthEncounter.resource AS VARCHAR) AS RESOURCE
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Encounter: Office Visit"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Audio Visual Telehealth Encounter") AS FaceToFaceOrTelehealthEncounter
   CROSS JOIN
     (SELECT *
      FROM "Chemotherapy Within 31 Days Prior and During Measurement Period") AS ChemoBeforeEncounter
   CROSS JOIN
     (SELECT *
      FROM "Chemotherapy Within 31 Days Prior and During Measurement Period") AS ChemoAfterEncounter
   CROSS JOIN "Condition: Cancer (qicore-condition-problems-health-concerns)" AS CancerDx
   WHERE intervalOverlaps(CASE
                              WHEN CancerDx.abatement_date IS NOT NULL THEN intervalFromBounds(COALESCE(CancerDx.onset_date, fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), CancerDx.recorded_date), CAST(CancerDx.abatement_date AS VARCHAR), TRUE, TRUE)
                              WHEN COALESCE(CancerDx.onset_date, fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), CancerDx.recorded_date) IS NOT NULL THEN CASE
                                                                                                                                                                     WHEN fhirpath_bool(CancerDx.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(CancerDx.onset_date, fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), CancerDx.recorded_date), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                     ELSE intervalFromBounds(COALESCE(CancerDx.onset_date, fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), CancerDx.recorded_date), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                 END
                              ELSE NULL
                          END, fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'period'))
     AND LEFT(REPLACE(CAST(STRFTIME(CAST(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP) - INTERVAL '30 day', '%Y-%m-%dT%H:%M:%S.%g') AS VARCHAR), ' ', 'T'), 10) <= CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                                                                                                                                                                                                                                                                          WHEN fhirpath_text(ChemoBeforeEncounter.resource, 'performed') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                          WHEN starts_with(LTRIM(fhirpath_text(ChemoBeforeEncounter.resource, 'performed')), '{') THEN fhirpath_text(ChemoBeforeEncounter.resource, 'performed')
                                                                                                                                                                                                                                                                                                                          ELSE intervalFromBounds(fhirpath_text(ChemoBeforeEncounter.resource, 'performed'), fhirpath_text(ChemoBeforeEncounter.resource, 'performed'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                      END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                  WHEN fhirpath_text(ChemoBeforeEncounter.resource, 'performed') IS NULL THEN NULL
                                                  WHEN starts_with(LTRIM(fhirpath_text(ChemoBeforeEncounter.resource, 'performed')), '{') THEN fhirpath_text(ChemoBeforeEncounter.resource, 'performed')
                                                  ELSE intervalFromBounds(fhirpath_text(ChemoBeforeEncounter.resource, 'performed'), fhirpath_text(ChemoBeforeEncounter.resource, 'performed'), TRUE, TRUE)
                                              END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= LEFT(REPLACE(CAST(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS VARCHAR), ' ', 'T'), 10)
     AND LEFT(REPLACE(CAST(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS VARCHAR), ' ', 'T'), 10) <= CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                                                                                                                                                                                                 WHEN fhirpath_text(ChemoAfterEncounter.resource, 'performed') IS NULL THEN NULL
                                                                                                                                                                                                                                                 WHEN starts_with(LTRIM(fhirpath_text(ChemoAfterEncounter.resource, 'performed')), '{') THEN fhirpath_text(ChemoAfterEncounter.resource, 'performed')
                                                                                                                                                                                                                                                 ELSE intervalFromBounds(fhirpath_text(ChemoAfterEncounter.resource, 'performed'), fhirpath_text(ChemoAfterEncounter.resource, 'performed'), TRUE, TRUE)
                                                                                                                                                                                                                                             END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
     AND CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                  WHEN fhirpath_text(ChemoAfterEncounter.resource, 'performed') IS NULL THEN NULL
                                                  WHEN starts_with(LTRIM(fhirpath_text(ChemoAfterEncounter.resource, 'performed')), '{') THEN fhirpath_text(ChemoAfterEncounter.resource, 'performed')
                                                  ELSE intervalFromBounds(fhirpath_text(ChemoAfterEncounter.resource, 'performed'), fhirpath_text(ChemoAfterEncounter.resource, 'performed'), TRUE, TRUE)
                                              END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= LEFT(REPLACE(CAST(STRFTIME(CAST(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP) + INTERVAL '30 day', '%Y-%m-%dT%H:%M:%S.%g') AS VARCHAR), ' ', 'T'), 10)
     AND NOT cqlSameAsP(CAST(CASE
                                 WHEN fhirpath_text(ChemoAfterEncounter.resource, 'performed') IS NULL THEN NULL
                                 WHEN starts_with(LTRIM(fhirpath_text(ChemoAfterEncounter.resource, 'performed')), '{') THEN fhirpath_text(ChemoAfterEncounter.resource, 'performed')
                                 ELSE intervalFromBounds(fhirpath_text(ChemoAfterEncounter.resource, 'performed'), fhirpath_text(ChemoAfterEncounter.resource, 'performed'), TRUE, TRUE)
                             END AS VARCHAR), CAST(CASE
                                                       WHEN fhirpath_text(ChemoBeforeEncounter.resource, 'performed') IS NULL THEN NULL
                                                       WHEN starts_with(LTRIM(fhirpath_text(ChemoBeforeEncounter.resource, 'performed')), '{') THEN fhirpath_text(ChemoBeforeEncounter.resource, 'performed')
                                                       ELSE intervalFromBounds(fhirpath_text(ChemoBeforeEncounter.resource, 'performed'), fhirpath_text(ChemoBeforeEncounter.resource, 'performed'), TRUE, TRUE)
                                                   END AS VARCHAR), 'day')
     AND intervalIncludes(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE), fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'period'))
     AND fhirpath_text(FaceToFaceOrTelehealthEncounter.resource, 'status') = 'finished'
     AND ChemoBeforeEncounter.patient_id = FaceToFaceOrTelehealthEncounter.patient_id
     AND ChemoAfterEncounter.patient_id = FaceToFaceOrTelehealthEncounter.patient_id
     AND CancerDx.patient_id = FaceToFaceOrTelehealthEncounter.patient_id),
     "Initial Population 1" AS
  (SELECT *
   FROM "Face to Face or Telehealth Encounter with Ongoing Chemotherapy"),
     "Denominator 1" AS
  (SELECT *
   FROM "Initial Population 1"),
     "Radiation Treatment Management During Measurement Period with Cancer Diagnosis" AS
  (SELECT *
   FROM "Encounter: Radiation Treatment Management" AS RadiationTreatmentManagement
   WHERE intervalIncludes(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE), fhirpath_text(RadiationTreatmentManagement.resource, 'period'))
     AND RadiationTreatmentManagement.status = 'finished'
     AND EXISTS
       (SELECT 1
        FROM "Condition: Cancer (qicore-condition-problems-health-concerns)" AS CancerDx
        WHERE (fhirpath_bool(CancerDx.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''active'').exists()')
               OR fhirpath_bool(CancerDx.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''recurrence'').exists()')
               OR fhirpath_bool(CancerDx.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''relapse'').exists()'))
          AND intervalOverlaps(CASE
                                   WHEN fhirpath_text(CancerDx.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(CancerDx.resource, 'onsetDateTime'), fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), fhirpath_text(CancerDx.resource, 'recordedDate')), fhirpath_text(CancerDx.resource, 'abatementDateTime'), TRUE, TRUE)
                                   WHEN COALESCE(fhirpath_text(CancerDx.resource, 'onsetDateTime'), fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), fhirpath_text(CancerDx.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                  WHEN fhirpath_bool(CancerDx.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(CancerDx.resource, 'onsetDateTime'), fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), fhirpath_text(CancerDx.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                  ELSE intervalFromBounds(COALESCE(fhirpath_text(CancerDx.resource, 'onsetDateTime'), fhirpath_text(CancerDx.resource, 'onsetPeriod.start'), fhirpath_text(CancerDx.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                              END
                                   ELSE NULL
                               END, fhirpath_text(RadiationTreatmentManagement.resource, 'period'))
          AND CancerDx.patient_id = RadiationTreatmentManagement.patient_id)),
     "Initial Population 2" AS
  (SELECT *
   FROM "Radiation Treatment Management During Measurement Period with Cancer Diagnosis"),
     "Denominator 2" AS
  (SELECT *
   FROM "Initial Population 2"),
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
     "Standard Pain Assessment with Result" AS
  (SELECT *
   FROM "Observation: Standardized Pain Assessment Tool" AS AssessedPain
   WHERE AssessedPain.value IS NOT NULL
     AND AssessedPain.status = 'final'),
     "Numerator 1" AS
  (SELECT *
   FROM "Face to Face or Telehealth Encounter with Ongoing Chemotherapy" AS FaceToFaceOrTelehealthEncounterWithChemo
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Standard Pain Assessment with Result") AS PainAssessed
        WHERE intervalIncludes(fhirpath_text(FaceToFaceOrTelehealthEncounterWithChemo.resource, 'period'), CASE
                                                                                                               WHEN fhirpath_text(PainAssessed.resource, 'effective') IS NULL THEN NULL
                                                                                                               WHEN starts_with(LTRIM(fhirpath_text(PainAssessed.resource, 'effective')), '{') THEN fhirpath_text(PainAssessed.resource, 'effective')
                                                                                                               ELSE intervalFromBounds(fhirpath_text(PainAssessed.resource, 'effective'), fhirpath_text(PainAssessed.resource, 'effective'), TRUE, TRUE)
                                                                                                           END)
          AND PainAssessed.patient_id = FaceToFaceOrTelehealthEncounterWithChemo.patient_id)),
     "Numerator 2" AS
  (SELECT *
   FROM "Radiation Treatment Management During Measurement Period with Cancer Diagnosis" AS RadiationManagementEncounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Standard Pain Assessment with Result") AS PainAssessed
        WHERE CASE
                  WHEN fhirpath_bool(RadiationManagementEncounter.resource, 'type.coding.where(system=''http://www.ama-assn.org/go/cpt'' and code=''77427'').exists()') THEN LEFT(REPLACE(CAST(STRFTIME(CAST(CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(RadiationManagementEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP) - INTERVAL '6 day', '%Y-%m-%dT%H:%M:%S.%g') AS VARCHAR), ' ', 'T'), 10) <= CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            WHEN fhirpath_text(PainAssessed.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            WHEN starts_with(LTRIM(fhirpath_text(PainAssessed.resource, 'effective')), '{') THEN fhirpath_text(PainAssessed.resource, 'effective')
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            ELSE intervalFromBounds(fhirpath_text(PainAssessed.resource, 'effective'), fhirpath_text(PainAssessed.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
                       AND CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                    WHEN fhirpath_text(PainAssessed.resource, 'effective') IS NULL THEN NULL
                                                                    WHEN starts_with(LTRIM(fhirpath_text(PainAssessed.resource, 'effective')), '{') THEN fhirpath_text(PainAssessed.resource, 'effective')
                                                                    ELSE intervalFromBounds(fhirpath_text(PainAssessed.resource, 'effective'), fhirpath_text(PainAssessed.resource, 'effective'), TRUE, TRUE)
                                                                END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(RadiationManagementEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
                  ELSE CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                                WHEN fhirpath_text(PainAssessed.resource, 'effective') IS NULL THEN NULL
                                                                WHEN starts_with(LTRIM(fhirpath_text(PainAssessed.resource, 'effective')), '{') THEN fhirpath_text(PainAssessed.resource, 'effective')
                                                                ELSE intervalFromBounds(fhirpath_text(PainAssessed.resource, 'effective'), fhirpath_text(PainAssessed.resource, 'effective'), TRUE, TRUE)
                                                            END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(RadiationManagementEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
                       AND CAST(LEFT(REPLACE(CAST(intervalEnd(CASE
                                                                  WHEN fhirpath_text(PainAssessed.resource, 'effective') IS NULL THEN NULL
                                                                  WHEN starts_with(LTRIM(fhirpath_text(PainAssessed.resource, 'effective')), '{') THEN fhirpath_text(PainAssessed.resource, 'effective')
                                                                  ELSE intervalFromBounds(fhirpath_text(PainAssessed.resource, 'effective'), fhirpath_text(PainAssessed.resource, 'effective'), TRUE, TRUE)
                                                              END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(RadiationManagementEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), LEFT(CAST('9999-12-31' AS VARCHAR), 10))
              END
          AND PainAssessed.patient_id = RadiationManagementEncounter.patient_id))
SELECT p.patient_id,

  (SELECT COALESCE(LIST("Initial Population 1".resource), [])
   FROM "Initial Population 1"
   WHERE "Initial Population 1".patient_id = p.patient_id
     AND "Initial Population 1".resource IS NOT NULL) AS "Initial Population 1",

  (SELECT COALESCE(LIST("Denominator 1".resource), [])
   FROM "Denominator 1"
   WHERE "Denominator 1".patient_id = p.patient_id
     AND "Denominator 1".resource IS NOT NULL) AS "Denominator 1",

  (SELECT COALESCE(LIST("Numerator 1".resource), [])
   FROM "Numerator 1"
   WHERE "Numerator 1".patient_id = p.patient_id
     AND "Numerator 1".resource IS NOT NULL) AS "Numerator 1",

  (SELECT COALESCE(LIST(json_extract_string("Initial Population 2".resource, '$.resourceType') || '/' || json_extract_string("Initial Population 2".resource, '$.id')), [])
   FROM "Initial Population 2"
   WHERE "Initial Population 2".patient_id = p.patient_id
     AND "Initial Population 2".resource IS NOT NULL) AS "Initial Population 2",

  (SELECT COALESCE(LIST(json_extract_string("Denominator 2".resource, '$.resourceType') || '/' || json_extract_string("Denominator 2".resource, '$.id')), [])
   FROM "Denominator 2"
   WHERE "Denominator 2".patient_id = p.patient_id
     AND "Denominator 2".resource IS NOT NULL) AS "Denominator 2",

  (SELECT COALESCE(LIST(json_extract_string("Numerator 2".resource, '$.resourceType') || '/' || json_extract_string("Numerator 2".resource, '$.id')), [])
   FROM "Numerator 2"
   WHERE "Numerator 2".patient_id = p.patient_id
     AND "Numerator 2".resource IS NOT NULL) AS "Numerator 2"
FROM _patients p
ORDER BY p.patient_id ASC
