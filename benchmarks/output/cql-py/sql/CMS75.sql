-- Generated SQL for CMS75

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('02b613cd-c4f0-431d-8799-2ed39b11785f',
                                '043f64b7-dd25-42ea-9785-0bdcbe64b27a',
                                '0af30a0b-0bdd-4868-976e-0eafa69c60db',
                                '1f4e0855-2a5a-4076-8086-10a14e61c298',
                                '26549e84-fbf3-43dc-8971-2f3baaf508d7',
                                '303676f7-30b4-4324-8ab3-8d5ab7e92102',
                                '326c7237-c7a4-4e1b-bd1d-ba518dc942dd',
                                '3e98ff8c-6d30-4a34-aabe-579419dd834f',
                                '6ddffc8d-02e7-44ce-a766-e67ae088db62',
                                '8b91c8d5-4fed-4be7-b930-ba922a502c05',
                                '8ed53f97-fe74-47f6-bf94-d3e85e70e1dd',
                                'a1d949ba-b8dd-453d-8565-f168e027b329',
                                'a42cd354-1966-45d5-aec2-2d42225e6911',
                                'b532c8f5-b38a-4337-8661-7b744e271a9c',
                                'bed5f054-2f38-4b02-998f-e7e64012cfb9',
                                'c17b4f9b-4821-4152-aac5-cafb99b3470c',
                                'd1b991a9-34a5-4926-8b52-694e5bc41bae',
                                'e72e9b43-d488-41d1-835d-9222337639b2',
                                'ebb4d1e8-32af-4811-adc5-f84a7318c5b8',
                                'f076026e-a9df-4c3c-acc9-8c3af6845543')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Clinical Oral Evaluation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.125.12.1003')),
     "Condition: Dental Caries (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.125.12.1004')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Condition: Dental Caries (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.125.12.1004')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Coverage: Payer Type" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'type') AS "type"
   FROM resources r
   WHERE r.resourceType = 'Coverage'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591')),
     "ServiceRequest: Hospice Care Ambulatory" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'ServiceRequest'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1584')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
     "Condition: Hospice Diagnosis (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1165')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Encounter: Hospice Encounter" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1003')),
     "Encounter: Encounter Inpatient" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.666.5.307')),
     "Procedure: Hospice Care Ambulatory" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1584')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Condition: Hospice Diagnosis (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1165')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Observation: Hospice care [Minimum Data Set]" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://loinc.org'' and code=''45755-6'').exists()')),
     "Hospice.Has Hospice Services" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Encounter: Encounter Inpatient"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS InpatientEncounter
        WHERE InpatientEncounter.patient_id = p.patient_id
          AND (fhirpath_bool(InpatientEncounter.resource, 'hospitalization.dischargeDisposition.coding.where(system=''http://snomed.info/sct'' and code=''428361000124107'').exists()')
               OR fhirpath_bool(InpatientEncounter.resource, 'hospitalization.dischargeDisposition.coding.where(system=''http://snomed.info/sct'' and code=''428371000124100'').exists()'))
          AND CAST(intervalEnd(fhirpath_text(InpatientEncounter.resource, 'period')) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE)))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Encounter: Hospice Encounter"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS HospiceEncounter
        WHERE HospiceEncounter.patient_id = p.patient_id
          AND CAST(intervalStart(fhirpath_text(HospiceEncounter.resource, 'period')) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(fhirpath_text(HospiceEncounter.resource, 'period')) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Observation: Hospice care [Minimum Data Set]"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                       'amended',
                                                       'corrected')) AS HospiceAssessment
        WHERE HospiceAssessment.patient_id = p.patient_id
          AND fhirpath_bool(HospiceAssessment.resource, 'value.coding.where(system=''http://snomed.info/sct'' and code=''373066001'').exists()')
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(HospiceAssessment.resource, 'effective') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(HospiceAssessment.resource, 'effective')), '{') THEN fhirpath_text(HospiceAssessment.resource, 'effective')
                                     ELSE intervalFromBounds(fhirpath_text(HospiceAssessment.resource, 'effective'), fhirpath_text(HospiceAssessment.resource, 'effective'), TRUE, TRUE)
                                 END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(CASE
                                            WHEN fhirpath_text(HospiceAssessment.resource, 'effective') IS NULL THEN NULL
                                            WHEN starts_with(LTRIM(fhirpath_text(HospiceAssessment.resource, 'effective')), '{') THEN fhirpath_text(HospiceAssessment.resource, 'effective')
                                            ELSE intervalFromBounds(fhirpath_text(HospiceAssessment.resource, 'effective'), fhirpath_text(HospiceAssessment.resource, 'effective'), TRUE, TRUE)
                                        END) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "ServiceRequest: Hospice Care Ambulatory"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('active',
                                                       'completed')
             AND fhirpath_text(RESOURCE, 'intent') IN ('order',
                                                       'original-order',
                                                       'reflex-order',
                                                       'filler-order',
                                                       'instance-order')) AS HospiceOrder
        WHERE HospiceOrder.patient_id = p.patient_id
          AND CAST(fhirpath_text(HospiceOrder.resource, 'authoredOn') AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
          AND CAST(fhirpath_text(HospiceOrder.resource, 'authoredOn') AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Procedure: Hospice Care Ambulatory"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS HospicePerformed
        WHERE HospicePerformed.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(HospicePerformed.resource, 'performed') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(HospicePerformed.resource, 'performed')), '{') THEN fhirpath_text(HospicePerformed.resource, 'performed')
                                     ELSE intervalFromBounds(fhirpath_text(HospicePerformed.resource, 'performed'), fhirpath_text(HospicePerformed.resource, 'performed'), TRUE, TRUE)
                                 END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(CASE
                                            WHEN fhirpath_text(HospicePerformed.resource, 'performed') IS NULL THEN NULL
                                            WHEN starts_with(LTRIM(fhirpath_text(HospicePerformed.resource, 'performed')), '{') THEN fhirpath_text(HospicePerformed.resource, 'performed')
                                            ELSE intervalFromBounds(fhirpath_text(HospicePerformed.resource, 'performed'), fhirpath_text(HospicePerformed.resource, 'performed'), TRUE, TRUE)
                                        END) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM
             (SELECT patient_id,
                     RESOURCE
              FROM "Condition: Hospice Diagnosis (qicore-condition-problems-health-concerns)"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Condition: Hospice Diagnosis (qicore-condition-encounter-diagnosis)") AS _union
           WHERE fhirpath_text(RESOURCE, 'verificationStatus') IS NULL
             OR fhirpath_text(RESOURCE, 'verificationStatus') IN ('confirmed',
                                                                  'unconfirmed',
                                                                  'provisional',
                                                                  'differential')) AS HospiceCareDiagnosis
        WHERE HospiceCareDiagnosis.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(HospiceCareDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), fhirpath_text(HospiceCareDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                     WHEN COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                        WHEN fhirpath_bool(HospiceCareDiagnosis.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                        ELSE intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                    END
                                     ELSE NULL
                                 END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(CASE
                                            WHEN fhirpath_text(HospiceCareDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), fhirpath_text(HospiceCareDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                            WHEN COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                               WHEN fhirpath_bool(HospiceCareDiagnosis.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                               ELSE intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                           END
                                            ELSE NULL
                                        END) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))),
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
  (SELECT *
   FROM "Hospice.Has Hospice Services"),
     "Numerator" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Condition: Dental Caries (qicore-condition-problems-health-concerns)"
           UNION SELECT patient_id,
                        RESOURCE
           FROM "Condition: Dental Caries (qicore-condition-encounter-diagnosis)") AS DentalCaries
        WHERE DentalCaries.patient_id = p.patient_id
          AND intervalOverlaps(CASE
                                   WHEN fhirpath_text(DentalCaries.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(DentalCaries.resource, 'onsetDateTime'), fhirpath_text(DentalCaries.resource, 'onsetPeriod.start'), fhirpath_text(DentalCaries.resource, 'recordedDate')), fhirpath_text(DentalCaries.resource, 'abatementDateTime'), TRUE, TRUE)
                                   WHEN COALESCE(fhirpath_text(DentalCaries.resource, 'onsetDateTime'), fhirpath_text(DentalCaries.resource, 'onsetPeriod.start'), fhirpath_text(DentalCaries.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                              WHEN fhirpath_bool(DentalCaries.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(DentalCaries.resource, 'onsetDateTime'), fhirpath_text(DentalCaries.resource, 'onsetPeriod.start'), fhirpath_text(DentalCaries.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                              ELSE intervalFromBounds(COALESCE(fhirpath_text(DentalCaries.resource, 'onsetDateTime'), fhirpath_text(DentalCaries.resource, 'onsetPeriod.start'), fhirpath_text(DentalCaries.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                          END
                                   ELSE NULL
                               END, intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)))),
     "Qualifying Encounters" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Encounter: Clinical Oral Evaluation"
      WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS ValidEncounter
   WHERE CAST(intervalStart(CASE
                                WHEN fhirpath_text(ValidEncounter.resource, 'period') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(ValidEncounter.resource, 'period')), '{') THEN fhirpath_text(ValidEncounter.resource, 'period')
                                ELSE intervalFromBounds(fhirpath_text(ValidEncounter.resource, 'period'), fhirpath_text(ValidEncounter.resource, 'period'), TRUE, TRUE)
                            END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
     AND CAST(intervalEnd(CASE
                              WHEN fhirpath_text(ValidEncounter.resource, 'period') IS NULL THEN NULL
                              WHEN starts_with(LTRIM(fhirpath_text(ValidEncounter.resource, 'period')), '{') THEN fhirpath_text(ValidEncounter.resource, 'period')
                              ELSE intervalFromBounds(fhirpath_text(ValidEncounter.resource, 'period'), fhirpath_text(ValidEncounter.resource, 'period'), TRUE, TRUE)
                          END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)),
     "Initial Population" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXTRACT(YEAR
                 FROM CAST('2026-01-01T00:00:00.000' AS TIMESTAMP)) - EXTRACT(YEAR
                                                                              FROM
                                                                                (SELECT _pd.birth_date
                                                                                 FROM _patient_demographics AS _pd
                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                 LIMIT 1)) - CASE
                                                                                                 WHEN EXTRACT(MONTH
                                                                                                              FROM CAST('2026-01-01T00:00:00.000' AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                           FROM
                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                              WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                              LIMIT 1))
                                                                                                      OR EXTRACT(MONTH
                                                                                                                 FROM CAST('2026-01-01T00:00:00.000' AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                              FROM
                                                                                                                                                                                (SELECT _pd.birth_date
                                                                                                                                                                                 FROM _patient_demographics AS _pd
                                                                                                                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                 LIMIT 1))
                                                                                                      AND EXTRACT(DAY
                                                                                                                  FROM CAST('2026-01-01T00:00:00.000' AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                               FROM
                                                                                                                                                                                 (SELECT _pd.birth_date
                                                                                                                                                                                  FROM _patient_demographics AS _pd
                                                                                                                                                                                  WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                  LIMIT 1)) THEN 1
                                                                                                 ELSE 0
                                                                                             END BETWEEN 1 AND 20
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
              WHEN "Numerator".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS Numerator
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Denominator Exclusions" ON p.patient_id = "Denominator Exclusions".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id ASC
