-- Generated SQL for CMS149

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('0405033f-c6a4-4619-93da-14c9c5613d7b',
                                '04c67cc9-bf23-4f31-988c-8bac7e96f938',
                                '051c9480-438e-48d5-b91f-5f8f980b1f8b',
                                '1312a23d-9987-425c-b842-ce97792fa49c',
                                '2eb467fd-9453-4652-bb38-18d1ab636aca',
                                '38fba18c-6026-4777-b99b-75996d5968e3',
                                '49997661-cfa3-4554-9d30-18dbb589d95c',
                                '598ab62f-bb5f-4947-b299-97aa8c50aef2',
                                '67e19058-917d-43f8-98d3-d16730fc7d32',
                                '6bd80fce-8086-46d6-a95f-bf70f0a016ca',
                                '7698942f-4fca-43dd-8457-6b80cd517566',
                                '805ca8cb-ad65-4edb-88c1-19aeec7461f2',
                                '83ef16cb-ad8a-4ce0-a8c8-c0ff7346d83c',
                                '8a93582d-baef-491c-a253-b43762a90ef6',
                                '8f570399-4bd9-4c38-aa3d-e526d987109b',
                                '9356623d-fe48-4da2-8def-54fb9e97177c',
                                '980e3550-6c75-4c4d-a64d-0657107e7cec',
                                '99f28510-d75f-48d3-9f36-69739bc27419',
                                '9c546150-9e90-4743-989a-39fe2b0a5a5b',
                                '9e1ffb55-7663-4cd5-a2bf-6f29fccbc70e',
                                'a3867482-15a8-42fd-8d78-dff5db0d40f4',
                                'a7318ea6-4b51-4c32-aeb5-60668c1b1114',
                                'a7935229-6eb1-45c1-ad08-4fcba8ebbde6',
                                'a8c0ccf4-e672-4c1f-9f33-fbf4464a5fe5',
                                'bff8345c-0962-455c-afd7-a1b26bfc50e2',
                                'c0e64f12-0d43-4bff-bd50-aae46844e6b6',
                                'de56e9db-49b7-4f1a-a1ae-2649b1bb52b9',
                                'e00c927a-f454-4611-97b2-e3e2bdfed182',
                                'e1e5ecba-2f9f-41c6-9bd2-2a1bc26a0273',
                                'e9a609ba-0f93-4d33-965e-4bca590af192',
                                'f2613ad5-c498-4205-98b4-e9d8ae0b53ad',
                                'fd115ded-69a6-4766-bdd9-d6364347401e')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Psych Visit Psychotherapy" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1496')),
     "Observation: Cognitive Assessment" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1332')),
     "Encounter: Care Services in Long Term Residential Facility" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1014')),
     "Encounter: Behavioral or Neuropsych Assessment" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1023')),
     "Encounter: Home Healthcare Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1016')),
     "Encounter: Patient Provider Interaction" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1012')),
     "Encounter: Outpatient Consultation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1008')),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
     "Observation: Cognitive Assessment (observationcancelled)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1332')),
     "Encounter: Occupational Therapy Evaluation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1011')),
     "Condition: Dementia & Mental Degenerations (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1005')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Nursing Facility Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1012')),
     "Observation: Standardized Tools for Assessment of Cognition" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1006')),
     "Observation: Standardized Tools for Assessment of Cognition (observationcancelled)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1006')),
     "Encounter: Psych Visit Diagnostic Evaluation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1492')),
     "Condition: Dementia & Mental Degenerations (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1005')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
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
     "Encounter to Assess Cognition" AS
  (SELECT patient_id,
          RESOURCE
   FROM "Encounter: Psych Visit Diagnostic Evaluation"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Nursing Facility Visit"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Care Services in Long Term Residential Facility"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Home Healthcare Services"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Psych Visit Psychotherapy"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Behavioral or Neuropsych Assessment"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Occupational Therapy Evaluation"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Office Visit"
   UNION SELECT patient_id,
                RESOURCE
   FROM "Encounter: Outpatient Consultation"),
     "Dementia Encounter During Measurement Period" AS
  (SELECT *
   FROM "Encounter to Assess Cognition" AS EncounterAssessCognition
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Condition: Dementia & Mental Degenerations (qicore-condition-problems-health-concerns)"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Condition: Dementia & Mental Degenerations (qicore-condition-encounter-diagnosis)") AS Dementia
        WHERE intervalIncludes(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE), fhirpath_text(EncounterAssessCognition.resource, 'period'))
          AND intervalOverlaps(CASE
                                   WHEN fhirpath_text(Dementia.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(Dementia.resource, 'onsetDateTime'), fhirpath_text(Dementia.resource, 'onsetPeriod.start'), fhirpath_text(Dementia.resource, 'recordedDate')), fhirpath_text(Dementia.resource, 'abatementDateTime'), TRUE, TRUE)
                                   WHEN COALESCE(fhirpath_text(Dementia.resource, 'onsetDateTime'), fhirpath_text(Dementia.resource, 'onsetPeriod.start'), fhirpath_text(Dementia.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                  WHEN fhirpath_bool(Dementia.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(Dementia.resource, 'onsetDateTime'), fhirpath_text(Dementia.resource, 'onsetPeriod.start'), fhirpath_text(Dementia.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                  ELSE intervalFromBounds(COALESCE(fhirpath_text(Dementia.resource, 'onsetDateTime'), fhirpath_text(Dementia.resource, 'onsetPeriod.start'), fhirpath_text(Dementia.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                              END
                                   ELSE NULL
                               END, fhirpath_text(EncounterAssessCognition.resource, 'period'))
          AND (fhirpath_bool(Dementia.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''active'').exists()')
               OR fhirpath_bool(Dementia.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''recurrence'').exists()')
               OR fhirpath_bool(Dementia.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''relapse'').exists()'))
          AND NOT (fhirpath_bool(Dementia.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''unconfirmed'').exists()')
                   OR fhirpath_bool(Dementia.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()')
                   OR fhirpath_bool(Dementia.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''entered-in-error'').exists()'))
          AND Dementia.patient_id = EncounterAssessCognition.patient_id)),
     "Assessment of Cognition Using Standardized Tools or Alternate Methods" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation: Standardized Tools for Assessment of Cognition"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Observation: Cognitive Assessment") AS CognitiveAssessment
   WHERE fhirpath_text(CognitiveAssessment.resource, 'value') IS NOT NULL
     AND array_contains(['final', 'amended', 'corrected', 'preliminary'], fhirpath_text(CognitiveAssessment.resource, 'status'))
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Dementia Encounter During Measurement Period") AS EncounterDementia
        WHERE CAST(CAST(intervalEnd(fhirpath_text(EncounterDementia.resource, 'period')) AS DATE) - INTERVAL '12 month' AS DATE) <= CAST(intervalStart(CASE
                                                                                                                                                           WHEN fhirpath_text(CognitiveAssessment.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                           WHEN starts_with(LTRIM(fhirpath_text(CognitiveAssessment.resource, 'effective')), '{') THEN fhirpath_text(CognitiveAssessment.resource, 'effective')
                                                                                                                                                           ELSE intervalFromBounds(fhirpath_text(CognitiveAssessment.resource, 'effective'), fhirpath_text(CognitiveAssessment.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                       END) AS DATE)
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(CognitiveAssessment.resource, 'effective') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(CognitiveAssessment.resource, 'effective')), '{') THEN fhirpath_text(CognitiveAssessment.resource, 'effective')
                                     ELSE intervalFromBounds(fhirpath_text(CognitiveAssessment.resource, 'effective'), fhirpath_text(CognitiveAssessment.resource, 'effective'), TRUE, TRUE)
                                 END) AS DATE) <= CAST(CAST(intervalEnd(fhirpath_text(EncounterDementia.resource, 'period')) AS DATE) AS DATE)
          AND EncounterDementia.patient_id = CognitiveAssessment.patient_id)),
     "Numerator" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Assessment of Cognition Using Standardized Tools or Alternate Methods" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Patient Reason for Not Performing Assessment of Cognition Using Standardized Tools or Alternate Methods" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation: Standardized Tools for Assessment of Cognition (observationcancelled)"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Observation: Cognitive Assessment (observationcancelled)") AS NoCognitiveAssessment
   WHERE in_valueset(NoCognitiveAssessment.resource, 'extension.where(url=''http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneReason'').valueCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1008')
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Dementia Encounter During Measurement Period") AS EncounterDementia
        WHERE CAST(fhirpath_text(NoCognitiveAssessment.resource, 'issued') AS DATE) >= CAST(intervalStart(fhirpath_text(EncounterDementia.resource, 'period')) AS DATE)
          AND CAST(fhirpath_text(NoCognitiveAssessment.resource, 'issued') AS DATE) <= COALESCE(CAST(intervalEnd(fhirpath_text(EncounterDementia.resource, 'period')) AS DATE), CAST('9999-12-31' AS DATE))
          AND EncounterDementia.patient_id = NoCognitiveAssessment.patient_id)),
     "Denominator Exceptions" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Patient Reason for Not Performing Assessment of Cognition Using Standardized Tools or Alternate Methods" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Qualifying Encounter During Measurement Period" AS
  (SELECT *
   FROM
     (
        (SELECT patient_id,
                RESOURCE
         FROM "Encounter to Assess Cognition")
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Patient Provider Interaction") AS ValidEncounter
   WHERE intervalIncludes(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE), fhirpath_text(ValidEncounter.resource, 'period'))
     AND fhirpath_text(ValidEncounter.resource, 'status') = 'finished'),
     "Initial Population" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Dementia Encounter During Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND
       (SELECT COUNT(*)
        FROM "Qualifying Encounter During Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id) >= 2),
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
