-- Generated SQL for CMS143

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('003b7002-84ee-4303-8030-8bc113f15e7e',
                                '006665cc-fce7-4e0a-9c13-b394fb41aee2',
                                '0e80afcd-6020-4d72-a5fd-d6db3f1f1a05',
                                '13d6df48-7288-49e6-9ad4-aa230744746b',
                                '1821adaa-fc62-4a94-9ebc-388ef6ced017',
                                '1ea6ee4a-bfb0-44ec-8a94-5f0035c81c9e',
                                '20d535da-db77-47c2-bc50-d36ed8a29270',
                                '2b101fed-53d1-44c8-b11a-792edd52228d',
                                '2cca67ad-d05c-4bd2-aa74-d5ba553b9afc',
                                '2e8da2d1-f38b-4c84-af43-51378f5af1c5',
                                '37d4f1ee-3f65-4f68-ac6c-685cc093eaf1',
                                '3cd86896-d4cb-4396-b4ad-96d3675b74e1',
                                '4163cf16-fe03-4cb3-aa8e-1be30b80bd22',
                                '4ca8189d-0064-457f-af42-9a02e5d0cc97',
                                '523eeca6-d45d-4326-a397-627bea696810',
                                '5275f17e-d213-4c1f-8d5c-9022276fdf8a',
                                '68109c29-0e38-4fb1-b994-846311eb3079',
                                '7263b5ad-e3fe-45af-8775-b827ecfd1c93',
                                '8352db6f-c4c7-4eb1-8264-ea3db86f1c6e',
                                '901324d3-abcb-44c1-97af-7fb226ea1985',
                                '9394a368-dd04-495b-a810-ee4e9a32e8a0',
                                '999429c0-38b9-4932-9f33-3c03a111eefa',
                                '9d5d6b94-a5a2-4544-be69-831ea5359943',
                                'b73f2b5d-98a4-4742-b2d6-979bd3e075a8',
                                'e180c0c4-8263-401a-923d-b1426bf07636',
                                'e216b280-8e64-4b45-97dc-98011f39205a',
                                'e2c1a11c-c85b-4ce9-a24e-4ce7f783a09b',
                                'e320fffc-78f7-4fb3-9cce-cc3608809c53',
                                'e4efaf8d-368e-4aff-9b5c-bbc074489b67',
                                'e8c4626d-c2e1-45df-b073-031784e03f55',
                                'f72cdb4b-8664-425b-a6ec-53480aa155de')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Nursing Facility Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1012')),
     "Observation: Optic Disc Exam for Structural Abnormalities" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1334')),
     "Observation: Cup to Disc Ratio (observationcancelled)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1333')),
     "Observation: Optic Disc Exam for Structural Abnormalities (observationcancelled)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1334')),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
     "Observation: Cup to Disc Ratio" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1333')),
     "Condition: Primary Open-Angle Glaucoma (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.326')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Ophthalmological Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1285')),
     "Encounter: Outpatient Consultation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1008')),
     "Encounter: Care Services in Long-Term Residential Facility" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1014')),
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
     "Qualifying Encounter During Measurement Period" AS
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
      FROM "Encounter: Nursing Facility Visit"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Encounter: Care Services in Long-Term Residential Facility") AS QualifyingEncounter
   WHERE intervalIncludes(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE), fhirpath_text(QualifyingEncounter.resource, 'period'))
     AND fhirpath_text(QualifyingEncounter.resource, 'status') = 'finished'
     AND NOT fhirpath_bool(QualifyingEncounter.resource, 'class.where(system=''http://terminology.hl7.org/CodeSystem/v3-ActCode'' and code=''VR'').exists()')),
     "Primary Open Angle Glaucoma Encounter" AS
  (SELECT *
   FROM "Qualifying Encounter During Measurement Period" AS ValidQualifyingEncounter
   WHERE EXISTS
       (SELECT 1
        FROM "Condition: Primary Open-Angle Glaucoma (qicore-condition-problems-health-concerns)" AS PrimaryOpenAngleGlaucoma
        WHERE intervalOverlaps(CASE
                                   WHEN fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetDateTime'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetPeriod.start'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'recordedDate')), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'abatementDateTime'), TRUE, TRUE)
                                   WHEN COALESCE(fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetDateTime'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetPeriod.start'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                                  WHEN fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetDateTime'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetPeriod.start'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                                  ELSE intervalFromBounds(COALESCE(fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetDateTime'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'onsetPeriod.start'), fhirpath_text(PrimaryOpenAngleGlaucoma.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                              END
                                   ELSE NULL
                               END, fhirpath_text(ValidQualifyingEncounter.resource, 'period'))
          AND (fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''active'').exists()')
               OR fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''recurrence'').exists()')
               OR fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'clinicalStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-clinical'' and code=''relapse'').exists()'))
          AND NOT (fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''unconfirmed'').exists()')
                   OR fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()')
                   OR fhirpath_bool(PrimaryOpenAngleGlaucoma.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''entered-in-error'').exists()'))
          AND PrimaryOpenAngleGlaucoma.patient_id = ValidQualifyingEncounter.patient_id)),
     "Cup to Disc Ratio Performed with Result" AS
  (SELECT *
   FROM "Observation: Cup to Disc Ratio" AS CupToDiscExamPerformed
   WHERE CupToDiscExamPerformed.value IS NOT NULL
     AND array_contains(['final', 'amended', 'corrected'], CupToDiscExamPerformed.status)
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Primary Open Angle Glaucoma Encounter") AS EncounterWithPOAG
        WHERE CAST(LEFT(REPLACE(CAST(intervalStart(CASE
                                                       WHEN fhirpath_text(CupToDiscExamPerformed.resource, 'effective') IS NULL THEN NULL
                                                       WHEN starts_with(LTRIM(fhirpath_text(CupToDiscExamPerformed.resource, 'effective')), '{') THEN fhirpath_text(CupToDiscExamPerformed.resource, 'effective')
                                                       ELSE intervalFromBounds(fhirpath_text(CupToDiscExamPerformed.resource, 'effective'), fhirpath_text(CupToDiscExamPerformed.resource, 'effective'), TRUE, TRUE)
                                                   END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(EncounterWithPOAG.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(intervalEnd(CASE
                                                     WHEN fhirpath_text(CupToDiscExamPerformed.resource, 'effective') IS NULL THEN NULL
                                                     WHEN starts_with(LTRIM(fhirpath_text(CupToDiscExamPerformed.resource, 'effective')), '{') THEN fhirpath_text(CupToDiscExamPerformed.resource, 'effective')
                                                     ELSE intervalFromBounds(fhirpath_text(CupToDiscExamPerformed.resource, 'effective'), fhirpath_text(CupToDiscExamPerformed.resource, 'effective'), TRUE, TRUE)
                                                 END) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(EncounterWithPOAG.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), LEFT(CAST('9999-12-31' AS VARCHAR), 10))
          AND EncounterWithPOAG.patient_id = CupToDiscExamPerformed.patient_id)),
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
        FROM "Primary Open Angle Glaucoma Encounter" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Denominator" AS
  (SELECT *
   FROM "Initial Population"),
     "Medical Reason for Not Performing Cup to Disc Ratio" AS
  (SELECT *
   FROM "Observation: Cup to Disc Ratio (observationcancelled)" AS CupToDiscExamNotPerformed
   WHERE in_valueset(CupToDiscExamNotPerformed.resource, 'extension.where(url=''http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneReason'').valueCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1007')
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Primary Open Angle Glaucoma Encounter") AS EncounterWithPOAG
        WHERE CAST(LEFT(REPLACE(CAST(fhirpath_text(CupToDiscExamNotPerformed.resource, 'issued') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(EncounterWithPOAG.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(CupToDiscExamNotPerformed.resource, 'issued') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(EncounterWithPOAG.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), LEFT(CAST('9999-12-31' AS VARCHAR), 10))
          AND EncounterWithPOAG.patient_id = CupToDiscExamNotPerformed.patient_id)),
     "Medical Reason for Not Performing Optic Disc Exam" AS
  (SELECT *
   FROM "Observation: Optic Disc Exam for Structural Abnormalities (observationcancelled)" AS OpticDiscExamNotPerformed
   WHERE in_valueset(OpticDiscExamNotPerformed.resource, 'extension.where(url=''http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-notDoneReason'').valueCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1007')
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Primary Open Angle Glaucoma Encounter") AS EncounterWithPOAG
        WHERE CAST(LEFT(REPLACE(CAST(fhirpath_text(OpticDiscExamNotPerformed.resource, 'issued') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) >= CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(EncounterWithPOAG.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR)
          AND CAST(LEFT(REPLACE(CAST(fhirpath_text(OpticDiscExamNotPerformed.resource, 'issued') AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) <= COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(EncounterWithPOAG.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), LEFT(CAST('9999-12-31' AS VARCHAR), 10))
          AND EncounterWithPOAG.patient_id = OpticDiscExamNotPerformed.patient_id)),
     "Denominator Exceptions" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Medical Reason for Not Performing Cup to Disc Ratio" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "Medical Reason for Not Performing Optic Disc Exam" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Optic Disc Exam Performed with Result" AS
  (SELECT *
   FROM "Observation: Optic Disc Exam for Structural Abnormalities" AS OpticDiscExamPerformed
   WHERE OpticDiscExamPerformed.value IS NOT NULL
     AND array_contains(['final', 'amended', 'corrected'], OpticDiscExamPerformed.status)
     AND EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Primary Open Angle Glaucoma Encounter") AS EncounterWithPOAG
        WHERE intervalIncludes(fhirpath_text(EncounterWithPOAG.resource, 'period'), CASE
                                                                                        WHEN fhirpath_text(OpticDiscExamPerformed.resource, 'effective') IS NULL THEN NULL
                                                                                        WHEN starts_with(LTRIM(fhirpath_text(OpticDiscExamPerformed.resource, 'effective')), '{') THEN fhirpath_text(OpticDiscExamPerformed.resource, 'effective')
                                                                                        ELSE intervalFromBounds(fhirpath_text(OpticDiscExamPerformed.resource, 'effective'), fhirpath_text(OpticDiscExamPerformed.resource, 'effective'), TRUE, TRUE)
                                                                                    END)
          AND EncounterWithPOAG.patient_id = OpticDiscExamPerformed.patient_id)),
     "Numerator" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Cup to Disc Ratio Performed with Result" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND EXISTS
       (SELECT 1
        FROM "Optic Disc Exam Performed with Result" AS sub
        WHERE sub.patient_id = p.patient_id)),
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
