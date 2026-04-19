-- Generated SQL for CMS155

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('1e0720b0-0782-4455-a355-8c1ecec3c653',
                                '259f8551-1cea-44f5-ae9e-e3f083d9f48f',
                                '362bc370-9fa5-4806-9cd3-378c484fa873',
                                '4304f97a-e2bb-4cda-93fa-ab510a136403',
                                '4a9211fc-d757-47ae-8bc0-0803c43a6728',
                                '598662b8-30c9-4f9b-a2d1-d91bea113d77',
                                'a0c68789-2a1b-4bc4-b6a4-d8f6b154d8ac',
                                'bd9b9e02-ce12-43cb-af1c-25298c891e62',
                                'dbb639f6-f7b7-41c8-bc30-84e5574c08cd',
                                'dfabce9a-f0fe-4095-a948-074d3aa8ccc7')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Preventive Care, Established Office Visit, 0 to 17" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1024')),
     "Procedure: Counseling for Physical Activity" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.118.12.1035')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Observation (us-core-bmi)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'),
     "Condition: Pregnancy (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'abatementDateTime') AS abatement_date,
                   fhirpath_text(r.resource, 'onsetDateTime') AS onset_date,
                   fhirpath_text(r.resource, 'recordedDate') AS recorded_date
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.378')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Preventive Care Services Group Counseling" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1027')),
     "Encounter: Preventive Care Services Individual Counseling" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1026')),
     "Observation (us-core-body-weight)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'),
     "Condition: Pregnancy (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'abatementDateTime') AS abatement_date,
                   fhirpath_text(r.resource, 'onsetDateTime') AS onset_date,
                   fhirpath_text(r.resource, 'recordedDate') AS recorded_date
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.378')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Observation (us-core-body-height)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'),
     "Encounter: Home Healthcare Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1016')),
     "Encounter: Telephone Visits" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1080')),
     "Encounter: Office Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1001')),
     "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1022')),
     "Procedure: Counseling for Nutrition" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.195.12.1003')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
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
     "BMI Percentile in Measurement Period" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation (us-core-bmi)"
      WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                  'amended',
                                                  'corrected')) AS BMIPercentile
   WHERE CAST(intervalStart(CASE
                                WHEN fhirpath_text(BMIPercentile.resource, 'effective') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(BMIPercentile.resource, 'effective')), '{') THEN fhirpath_text(BMIPercentile.resource, 'effective')
                                ELSE intervalFromBounds(fhirpath_text(BMIPercentile.resource, 'effective'), fhirpath_text(BMIPercentile.resource, 'effective'), TRUE, TRUE)
                            END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
     AND CAST(intervalEnd(CASE
                              WHEN fhirpath_text(BMIPercentile.resource, 'effective') IS NULL THEN NULL
                              WHEN starts_with(LTRIM(fhirpath_text(BMIPercentile.resource, 'effective')), '{') THEN fhirpath_text(BMIPercentile.resource, 'effective')
                              ELSE intervalFromBounds(fhirpath_text(BMIPercentile.resource, 'effective'), fhirpath_text(BMIPercentile.resource, 'effective'), TRUE, TRUE)
                          END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)
     AND fhirpath_text(BMIPercentile.resource, 'value') IS NOT NULL),
     "Height in Measurement Period" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation (us-core-body-height)"
      WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                  'amended',
                                                  'corrected')) AS Height
   WHERE CAST(intervalStart(CASE
                                WHEN fhirpath_text(Height.resource, 'effective') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(Height.resource, 'effective')), '{') THEN fhirpath_text(Height.resource, 'effective')
                                ELSE intervalFromBounds(fhirpath_text(Height.resource, 'effective'), fhirpath_text(Height.resource, 'effective'), TRUE, TRUE)
                            END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
     AND CAST(intervalEnd(CASE
                              WHEN fhirpath_text(Height.resource, 'effective') IS NULL THEN NULL
                              WHEN starts_with(LTRIM(fhirpath_text(Height.resource, 'effective')), '{') THEN fhirpath_text(Height.resource, 'effective')
                              ELSE intervalFromBounds(fhirpath_text(Height.resource, 'effective'), fhirpath_text(Height.resource, 'effective'), TRUE, TRUE)
                          END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)
     AND fhirpath_text(Height.resource, 'value') IS NOT NULL),
     "Numerator 2" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Procedure: Counseling for Nutrition"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS NutritionCounseling
        WHERE NutritionCounseling.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(NutritionCounseling.resource, 'performed') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(NutritionCounseling.resource, 'performed')), '{') THEN fhirpath_text(NutritionCounseling.resource, 'performed')
                                     ELSE intervalFromBounds(fhirpath_text(NutritionCounseling.resource, 'performed'), fhirpath_text(NutritionCounseling.resource, 'performed'), TRUE, TRUE)
                                 END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
          AND CAST(intervalEnd(CASE
                                   WHEN fhirpath_text(NutritionCounseling.resource, 'performed') IS NULL THEN NULL
                                   WHEN starts_with(LTRIM(fhirpath_text(NutritionCounseling.resource, 'performed')), '{') THEN fhirpath_text(NutritionCounseling.resource, 'performed')
                                   ELSE intervalFromBounds(fhirpath_text(NutritionCounseling.resource, 'performed'), fhirpath_text(NutritionCounseling.resource, 'performed'), TRUE, TRUE)
                               END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE))),
     "Numerator 3" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Procedure: Counseling for Physical Activity"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS ActivityCounseling
        WHERE ActivityCounseling.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(ActivityCounseling.resource, 'performed') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(ActivityCounseling.resource, 'performed')), '{') THEN fhirpath_text(ActivityCounseling.resource, 'performed')
                                     ELSE intervalFromBounds(fhirpath_text(ActivityCounseling.resource, 'performed'), fhirpath_text(ActivityCounseling.resource, 'performed'), TRUE, TRUE)
                                 END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
          AND CAST(intervalEnd(CASE
                                   WHEN fhirpath_text(ActivityCounseling.resource, 'performed') IS NULL THEN NULL
                                   WHEN starts_with(LTRIM(fhirpath_text(ActivityCounseling.resource, 'performed')), '{') THEN fhirpath_text(ActivityCounseling.resource, 'performed')
                                   ELSE intervalFromBounds(fhirpath_text(ActivityCounseling.resource, 'performed'), fhirpath_text(ActivityCounseling.resource, 'performed'), TRUE, TRUE)
                               END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE))),
     "Pregnancy Diagnosis Which Overlaps Measurement Period" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Condition: Pregnancy (qicore-condition-problems-health-concerns)"
      UNION SELECT patient_id,
                   RESOURCE
      FROM "Condition: Pregnancy (qicore-condition-encounter-diagnosis)") AS PregnancyDiag
   WHERE intervalOverlaps(CASE
                              WHEN fhirpath_text(PregnancyDiag.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(PregnancyDiag.resource, 'onsetDateTime'), fhirpath_text(PregnancyDiag.resource, 'onsetPeriod.start'), fhirpath_text(PregnancyDiag.resource, 'recordedDate')), fhirpath_text(PregnancyDiag.resource, 'abatementDateTime'), TRUE, TRUE)
                              WHEN COALESCE(fhirpath_text(PregnancyDiag.resource, 'onsetDateTime'), fhirpath_text(PregnancyDiag.resource, 'onsetPeriod.start'), fhirpath_text(PregnancyDiag.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                            WHEN fhirpath_bool(PregnancyDiag.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(PregnancyDiag.resource, 'onsetDateTime'), fhirpath_text(PregnancyDiag.resource, 'onsetPeriod.start'), fhirpath_text(PregnancyDiag.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                            ELSE intervalFromBounds(COALESCE(fhirpath_text(PregnancyDiag.resource, 'onsetDateTime'), fhirpath_text(PregnancyDiag.resource, 'onsetPeriod.start'), fhirpath_text(PregnancyDiag.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                        END
                              ELSE NULL
                          END, intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE))),
     "Denominator Exclusions" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Hospice.Has Hospice Services" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "Pregnancy Diagnosis Which Overlaps Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "Qualifying Encounters" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM
        (SELECT patient_id,
                RESOURCE
         FROM "Encounter: Office Visit"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Preventive Care Services Individual Counseling"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Preventive Care, Established Office Visit, 0 to 17"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Preventive Care Services Group Counseling"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Home Healthcare Services"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Telephone Visits") AS _union
      WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS ValidEncounters
   WHERE CAST(intervalStart(CASE
                                WHEN fhirpath_text(ValidEncounters.resource, 'period') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(ValidEncounters.resource, 'period')), '{') THEN fhirpath_text(ValidEncounters.resource, 'period')
                                ELSE intervalFromBounds(fhirpath_text(ValidEncounters.resource, 'period'), fhirpath_text(ValidEncounters.resource, 'period'), TRUE, TRUE)
                            END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
     AND CAST(intervalEnd(CASE
                              WHEN fhirpath_text(ValidEncounters.resource, 'period') IS NULL THEN NULL
                              WHEN starts_with(LTRIM(fhirpath_text(ValidEncounters.resource, 'period')), '{') THEN fhirpath_text(ValidEncounters.resource, 'period')
                              ELSE intervalFromBounds(fhirpath_text(ValidEncounters.resource, 'period'), fhirpath_text(ValidEncounters.resource, 'period'), TRUE, TRUE)
                          END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)),
     "Initial Population" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXTRACT(YEAR
                 FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) - EXTRACT(YEAR
                                                                              FROM
                                                                                (SELECT _pd.birth_date
                                                                                 FROM _patient_demographics AS _pd
                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                 LIMIT 1)) - CASE
                                                                                                 WHEN EXTRACT(MONTH
                                                                                                              FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                           FROM
                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                              WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                              LIMIT 1))
                                                                                                      OR EXTRACT(MONTH
                                                                                                                 FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                              FROM
                                                                                                                                                                                (SELECT _pd.birth_date
                                                                                                                                                                                 FROM _patient_demographics AS _pd
                                                                                                                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                 LIMIT 1))
                                                                                                      AND EXTRACT(DAY
                                                                                                                  FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                               FROM
                                                                                                                                                                                 (SELECT _pd.birth_date
                                                                                                                                                                                  FROM _patient_demographics AS _pd
                                                                                                                                                                                  WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                  LIMIT 1)) THEN 1
                                                                                                 ELSE 0
                                                                                             END BETWEEN 3 AND 17
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
   FROM "SDE.SDE Sex"),
     "Stratification 1" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXTRACT(YEAR
                 FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) - EXTRACT(YEAR
                                                                              FROM
                                                                                (SELECT _pd.birth_date
                                                                                 FROM _patient_demographics AS _pd
                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                 LIMIT 1)) - CASE
                                                                                                 WHEN EXTRACT(MONTH
                                                                                                              FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                           FROM
                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                              WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                              LIMIT 1))
                                                                                                      OR EXTRACT(MONTH
                                                                                                                 FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                              FROM
                                                                                                                                                                                (SELECT _pd.birth_date
                                                                                                                                                                                 FROM _patient_demographics AS _pd
                                                                                                                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                 LIMIT 1))
                                                                                                      AND EXTRACT(DAY
                                                                                                                  FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                               FROM
                                                                                                                                                                                 (SELECT _pd.birth_date
                                                                                                                                                                                  FROM _patient_demographics AS _pd
                                                                                                                                                                                  WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                  LIMIT 1)) THEN 1
                                                                                                 ELSE 0
                                                                                             END BETWEEN 3 AND 11),
     "Stratification 2" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXTRACT(YEAR
                 FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) - EXTRACT(YEAR
                                                                              FROM
                                                                                (SELECT _pd.birth_date
                                                                                 FROM _patient_demographics AS _pd
                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                 LIMIT 1)) - CASE
                                                                                                 WHEN EXTRACT(MONTH
                                                                                                              FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                           FROM
                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                              WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                              LIMIT 1))
                                                                                                      OR EXTRACT(MONTH
                                                                                                                 FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                              FROM
                                                                                                                                                                                (SELECT _pd.birth_date
                                                                                                                                                                                 FROM _patient_demographics AS _pd
                                                                                                                                                                                 WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                 LIMIT 1))
                                                                                                      AND EXTRACT(DAY
                                                                                                                  FROM CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                               FROM
                                                                                                                                                                                 (SELECT _pd.birth_date
                                                                                                                                                                                  FROM _patient_demographics AS _pd
                                                                                                                                                                                  WHERE _pd.patient_id = p.patient_id
                                                                                                                                                                                  LIMIT 1)) THEN 1
                                                                                                 ELSE 0
                                                                                             END BETWEEN 12 AND 17),
     "Weight in Measurement Period" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation (us-core-body-weight)"
      WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                  'amended',
                                                  'corrected')) AS Weight
   WHERE CAST(intervalStart(CASE
                                WHEN fhirpath_text(Weight.resource, 'effective') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(Weight.resource, 'effective')), '{') THEN fhirpath_text(Weight.resource, 'effective')
                                ELSE intervalFromBounds(fhirpath_text(Weight.resource, 'effective'), fhirpath_text(Weight.resource, 'effective'), TRUE, TRUE)
                            END) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
     AND CAST(intervalEnd(CASE
                              WHEN fhirpath_text(Weight.resource, 'effective') IS NULL THEN NULL
                              WHEN starts_with(LTRIM(fhirpath_text(Weight.resource, 'effective')), '{') THEN fhirpath_text(Weight.resource, 'effective')
                              ELSE intervalFromBounds(fhirpath_text(Weight.resource, 'effective'), fhirpath_text(Weight.resource, 'effective'), TRUE, TRUE)
                          END) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)
     AND fhirpath_text(Weight.resource, 'value') IS NOT NULL),
     "Numerator 1" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "BMI Percentile in Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND EXISTS
       (SELECT 1
        FROM "Height in Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id)
     AND EXISTS
       (SELECT 1
        FROM "Weight in Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id))
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
              WHEN "Numerator 1".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS "Numerator 1",

  (SELECT CASE
              WHEN "Numerator 2".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS "Numerator 2",

  (SELECT CASE
              WHEN "Numerator 3".patient_id IS NOT NULL THEN TRUE
              ELSE FALSE
          END) AS "Numerator 3"
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Denominator Exclusions" ON p.patient_id = "Denominator Exclusions".patient_id
LEFT JOIN "Numerator 1" ON p.patient_id = "Numerator 1".patient_id
LEFT JOIN "Numerator 2" ON p.patient_id = "Numerator 2".patient_id
LEFT JOIN "Numerator 3" ON p.patient_id = "Numerator 3".patient_id
ORDER BY p.patient_id ASC
