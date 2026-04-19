-- Generated SQL for CMS124

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('05cbc93d-e748-4bca-b68d-3011ebf68e28',
                                '0e296f04-855b-42ad-aa20-295a719a96e5',
                                '1104f4a8-5328-4629-8b7f-77f7b2e62225',
                                '25727adc-4495-4e13-9dfc-8b9cb6bf17b9',
                                '27981b44-c26e-4bce-957c-f9e82f62f05d',
                                '321abfa0-2c0e-4885-8b5b-20208512e605',
                                '3aef97c8-9529-433c-95d3-ea01f188e156',
                                '3e21058f-64cc-4b0a-8c84-1122df974dae',
                                '4c40d1e6-3943-4a0e-a95c-6e6b845f0851',
                                '59ef157d-1417-4a8e-9193-06d9c66ba8e1',
                                '6005d1fd-e9f5-414d-88d6-23087b4f3e94',
                                '62bd7a1e-f946-435f-8898-39db9d870940',
                                '65a9a258-c453-484f-902c-743e678b44a4',
                                '679e022b-0ae1-414a-a2fa-f1af1d2eeef7',
                                '6ee7c92c-c8cd-4025-8002-ca1253ba830b',
                                '71b8882f-bb0f-4402-a4b7-adc60e2008a8',
                                '72af08cd-4f6d-4e7a-b3da-a7ebb2bd3887',
                                '7e41f717-097e-45a7-9a00-1e0ad852cb44',
                                '8723dbb4-f60f-488a-9da3-f02f04ea03bf',
                                '908f935e-43b9-4666-982a-f211d1cfcd50',
                                'ab346cb5-2c55-4171-93ea-aac9d266e6c7',
                                'b565dc44-4428-417d-bdf6-144e408ad815',
                                'b8c73916-4520-47e1-9456-a36cd1575693',
                                'c0d1f27d-249b-4d74-a493-a4796fb8e833',
                                'c5ea33df-060b-484a-b6c4-17c600559077',
                                'c6ec1681-b011-425a-a850-4e187e9fd927',
                                'cadbffa0-20b2-4c26-b202-75b9edfd0a07',
                                'd986061c-de3e-4d5d-95e7-f5ec93c5665c',
                                'dc5b8054-7432-4905-aaef-3acd6f3f75b9',
                                'dd04ce68-da5f-415e-b5e6-9f808a0edb6d',
                                'e0fdd5df-7671-417c-9eef-20873cd647d6',
                                'e8813151-9334-41d7-ab4b-1d597f08d4a9',
                                'e8e5b4c8-0e07-415f-a534-9143ecef5f10')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Virtual Encounter" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1089')),
     "Encounter: Preventive Care Services Initial Office Visit, 18 and Up" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1023')),
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
     "Encounter: Home Healthcare Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1016')),
     "Condition: Congenital or Acquired Absence of Cervix (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'abatementDateTime') AS abatement_date,
                   fhirpath_text(r.resource, 'onsetDateTime') AS onset_date,
                   fhirpath_text(r.resource, 'recordedDate') AS recorded_date,
                   fhirpath_text(r.resource, 'verificationStatus') AS verification_status
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.111.12.1016')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Observation: HPV Test" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'effectiveDateTime') AS effective_date,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.110.12.1059')),
     "Procedure: Hysterectomy with No Residual Cervix" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.198.12.1014')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Observation: Pap Test" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'effectiveDateTime') AS effective_date,
                   fhirpath_text(r.resource, 'status') AS status,
                   fhirpath_text(r.resource, 'value') AS value
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.108.12.1017')),
     "Condition: Congenital or Acquired Absence of Cervix (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'abatementDateTime') AS abatement_date,
                   fhirpath_text(r.resource, 'onsetDateTime') AS onset_date,
                   fhirpath_text(r.resource, 'recordedDate') AS recorded_date,
                   fhirpath_text(r.resource, 'verificationStatus') AS verification_status
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.111.12.1016')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Encounter: Preventive Care Services Established Office Visit, 18 and Up" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1025')),
     "Coverage: Payer Type" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'type') AS "type"
   FROM resources r
   WHERE r.resourceType = 'Coverage'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.114222.4.11.3591')),
     "Observation: Hospice care [Minimum Data Set]" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://loinc.org'' and code=''45755-6'').exists()')),
     "Encounter: Encounter Inpatient" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.666.5.307')),
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
     "ServiceRequest: Hospice Care Ambulatory" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'ServiceRequest'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.526.3.1584')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
     "Condition: Hospice Diagnosis (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1165')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Condition: Palliative Care Diagnosis (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1167')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Procedure: Palliative Care Intervention" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.198.12.1135')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Condition: Palliative Care Diagnosis (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.1167')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Palliative Care Encounter" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.101.12.1090')),
     "Observation: Functional Assessment of Chronic Illness Therapy - Palliative Care Questionnaire (FACIT-Pal)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND fhirpath_bool(r.resource, 'code.coding.where(system=''http://loinc.org'' and code=''71007-9'').exists()')),
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
     "PalliativeCare.Has Palliative Care in the Measurement Period" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Observation: Functional Assessment of Chronic Illness Therapy - Palliative Care Questionnaire (FACIT-Pal)"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                       'amended',
                                                       'corrected')) AS PalliativeAssessment
        WHERE PalliativeAssessment.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(PalliativeAssessment.resource, 'effective') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(PalliativeAssessment.resource, 'effective')), '{') THEN fhirpath_text(PalliativeAssessment.resource, 'effective')
                                     ELSE intervalFromBounds(fhirpath_text(PalliativeAssessment.resource, 'effective'), fhirpath_text(PalliativeAssessment.resource, 'effective'), TRUE, TRUE)
                                 END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(CASE
                                            WHEN fhirpath_text(PalliativeAssessment.resource, 'effective') IS NULL THEN NULL
                                            WHEN starts_with(LTRIM(fhirpath_text(PalliativeAssessment.resource, 'effective')), '{') THEN fhirpath_text(PalliativeAssessment.resource, 'effective')
                                            ELSE intervalFromBounds(fhirpath_text(PalliativeAssessment.resource, 'effective'), fhirpath_text(PalliativeAssessment.resource, 'effective'), TRUE, TRUE)
                                        END) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM
             (SELECT patient_id,
                     RESOURCE
              FROM "Condition: Palliative Care Diagnosis (qicore-condition-problems-health-concerns)"
              UNION SELECT patient_id,
                           RESOURCE
              FROM "Condition: Palliative Care Diagnosis (qicore-condition-encounter-diagnosis)") AS _union
           WHERE fhirpath_text(RESOURCE, 'verificationStatus') IS NULL
             OR fhirpath_text(RESOURCE, 'verificationStatus') IN ('confirmed',
                                                                  'unconfirmed',
                                                                  'provisional',
                                                                  'differential')) AS PalliativeDiagnosis
        WHERE PalliativeDiagnosis.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(PalliativeDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), fhirpath_text(PalliativeDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                     WHEN COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                     WHEN fhirpath_bool(PalliativeDiagnosis.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                     ELSE intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                 END
                                     ELSE NULL
                                 END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(CASE
                                            WHEN fhirpath_text(PalliativeDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), fhirpath_text(PalliativeDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                            WHEN COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                            WHEN fhirpath_bool(PalliativeDiagnosis.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                            ELSE intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                        END
                                            ELSE NULL
                                        END) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Encounter: Palliative Care Encounter"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS PalliativeEncounter
        WHERE PalliativeEncounter.patient_id = p.patient_id
          AND CAST(intervalStart(fhirpath_text(PalliativeEncounter.resource, 'period')) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(fhirpath_text(PalliativeEncounter.resource, 'period')) AS DATE), CAST('9999-12-31' AS DATE)) >= CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     OR EXISTS
       (SELECT *
        FROM
          (SELECT patient_id,
                  RESOURCE
           FROM "Procedure: Palliative Care Intervention"
           WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS PalliativeIntervention
        WHERE PalliativeIntervention.patient_id = p.patient_id
          AND CAST(intervalStart(CASE
                                     WHEN fhirpath_text(PalliativeIntervention.resource, 'performed') IS NULL THEN NULL
                                     WHEN starts_with(LTRIM(fhirpath_text(PalliativeIntervention.resource, 'performed')), '{') THEN fhirpath_text(PalliativeIntervention.resource, 'performed')
                                     ELSE intervalFromBounds(fhirpath_text(PalliativeIntervention.resource, 'performed'), fhirpath_text(PalliativeIntervention.resource, 'performed'), TRUE, TRUE)
                                 END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
          AND COALESCE(CAST(intervalEnd(CASE
                                            WHEN fhirpath_text(PalliativeIntervention.resource, 'performed') IS NULL THEN NULL
                                            WHEN starts_with(LTRIM(fhirpath_text(PalliativeIntervention.resource, 'performed')), '{') THEN fhirpath_text(PalliativeIntervention.resource, 'performed')
                                            ELSE intervalFromBounds(fhirpath_text(PalliativeIntervention.resource, 'performed'), fhirpath_text(PalliativeIntervention.resource, 'performed'), TRUE, TRUE)
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
     "Absence of Cervix" AS (
                               (SELECT *
                                FROM
                                  (SELECT patient_id,
                                          RESOURCE
                                   FROM "Procedure: Hysterectomy with No Residual Cervix"
                                   WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS NoCervixProcedure
                                WHERE CAST(intervalEnd(CASE
                                                           WHEN fhirpath_text(NoCervixProcedure.resource, 'performed') IS NULL THEN NULL
                                                           WHEN starts_with(LTRIM(fhirpath_text(NoCervixProcedure.resource, 'performed')), '{') THEN fhirpath_text(NoCervixProcedure.resource, 'performed')
                                                           ELSE intervalFromBounds(fhirpath_text(NoCervixProcedure.resource, 'performed'), fhirpath_text(NoCervixProcedure.resource, 'performed'), TRUE, TRUE)
                                                       END) AS DATE) <= CAST('2026-12-31T23:59:59.999' AS TIMESTAMP))
                             UNION
                               (SELECT *
                                FROM
                                  (SELECT patient_id,
                                          RESOURCE
                                   FROM
                                     (SELECT patient_id,
                                             RESOURCE
                                      FROM "Condition: Congenital or Acquired Absence of Cervix (qicore-condition-problems-health-concerns)"
                                      UNION SELECT patient_id,
                                                   RESOURCE
                                      FROM "Condition: Congenital or Acquired Absence of Cervix (qicore-condition-encounter-diagnosis)") AS _union
                                   WHERE fhirpath_text(RESOURCE, 'verificationStatus') IS NULL
                                     OR fhirpath_text(RESOURCE, 'verificationStatus') IN ('confirmed',
                                                                                          'unconfirmed',
                                                                                          'provisional',
                                                                                          'differential')) AS NoCervixDiagnosis
                                WHERE CAST(intervalStart(CASE
                                                             WHEN fhirpath_text(NoCervixDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(NoCervixDiagnosis.resource, 'onsetDateTime'), fhirpath_text(NoCervixDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(NoCervixDiagnosis.resource, 'recordedDate')), fhirpath_text(NoCervixDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                                             WHEN COALESCE(fhirpath_text(NoCervixDiagnosis.resource, 'onsetDateTime'), fhirpath_text(NoCervixDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(NoCervixDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                                       WHEN fhirpath_bool(NoCervixDiagnosis.resource, 'clinicalStatus.coding.where(code=''active'' or code=''recurrence'' or code=''relapse'').exists()') THEN intervalFromBounds(COALESCE(fhirpath_text(NoCervixDiagnosis.resource, 'onsetDateTime'), fhirpath_text(NoCervixDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(NoCervixDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                                       ELSE intervalFromBounds(COALESCE(fhirpath_text(NoCervixDiagnosis.resource, 'onsetDateTime'), fhirpath_text(NoCervixDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(NoCervixDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                                   END
                                                             ELSE NULL
                                                         END) AS DATE) <= CAST('2026-12-31T23:59:59.999' AS TIMESTAMP))),
     "Cervical Cytology Within 3 Years" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation: Pap Test"
      WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                  'amended',
                                                  'corrected')) AS CervicalCytology
   WHERE CAST(COALESCE(fhirpath_date(CervicalCytology.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(CervicalCytology.resource, 'effectivePeriod'))) AS DATE) >= CAST(dateSubtractQuantity(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), '{"value": 2.0, "unit": "year", "system": "http://unitsofmeasure.org"}') AS DATE)
     AND CAST(COALESCE(fhirpath_date(CervicalCytology.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(CervicalCytology.resource, 'effectivePeriod'))) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)
     AND fhirpath_text(CervicalCytology.resource, 'value') IS NOT NULL),
     "Denominator Exclusions" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Hospice.Has Hospice Services" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "Absence of Cervix" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "PalliativeCare.Has Palliative Care in the Measurement Period" AS sub
        WHERE sub.patient_id = p.patient_id)),
     "HPV Test Within 5 Years for Women Age 30 and Older" AS
  (SELECT *
   FROM
     (SELECT patient_id,
             RESOURCE
      FROM "Observation: HPV Test"
      WHERE fhirpath_text(RESOURCE, 'status') IN ('final',
                                                  'amended',
                                                  'corrected')) AS HPVTest
   WHERE EXTRACT(YEAR
                 FROM CAST(COALESCE(fhirpath_date(HPVTest.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(HPVTest.resource, 'effectivePeriod'))) AS DATE)) - EXTRACT(YEAR
                                                                                                                                                                               FROM
                                                                                                                                                                                 (SELECT _pd.birth_date
                                                                                                                                                                                  FROM _patient_demographics AS _pd
                                                                                                                                                                                  WHERE _pd.patient_id = HPVTest.patient_id
                                                                                                                                                                                  LIMIT 1)) - CASE
                                                                                                                                                                                                  WHEN EXTRACT(MONTH
                                                                                                                                                                                                               FROM CAST(COALESCE(fhirpath_date(HPVTest.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(HPVTest.resource, 'effectivePeriod'))) AS DATE)) < EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                                                             FROM
                                                                                                                                                                                                                                                                                                                                                                               (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                WHERE _pd.patient_id = HPVTest.patient_id
                                                                                                                                                                                                                                                                                                                                                                                LIMIT 1))
                                                                                                                                                                                                       OR EXTRACT(MONTH
                                                                                                                                                                                                                  FROM CAST(COALESCE(fhirpath_date(HPVTest.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(HPVTest.resource, 'effectivePeriod'))) AS DATE)) = EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                                                                FROM
                                                                                                                                                                                                                                                                                                                                                                                  (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                   FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                   WHERE _pd.patient_id = HPVTest.patient_id
                                                                                                                                                                                                                                                                                                                                                                                   LIMIT 1))
                                                                                                                                                                                                       AND EXTRACT(DAY
                                                                                                                                                                                                                   FROM CAST(COALESCE(fhirpath_date(HPVTest.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(HPVTest.resource, 'effectivePeriod'))) AS DATE)) < EXTRACT(DAY
                                                                                                                                                                                                                                                                                                                                                                                 FROM
                                                                                                                                                                                                                                                                                                                                                                                   (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                    FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                    WHERE _pd.patient_id = HPVTest.patient_id
                                                                                                                                                                                                                                                                                                                                                                                    LIMIT 1)) THEN 1
                                                                                                                                                                                                  ELSE 0
                                                                                                                                                                                              END >= 30
     AND CAST(COALESCE(fhirpath_date(HPVTest.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(HPVTest.resource, 'effectivePeriod'))) AS DATE) >= CAST(dateSubtractQuantity(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), '{"value": 4.0, "unit": "year", "system": "http://unitsofmeasure.org"}') AS DATE)
     AND CAST(COALESCE(fhirpath_date(HPVTest.resource, 'effectiveDateTime'), intervalEnd(fhirpath_text(HPVTest.resource, 'effectivePeriod'))) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)
     AND fhirpath_text(HPVTest.resource, 'value') IS NOT NULL),
     "Numerator" AS
  (SELECT p.patient_id
   FROM _patients AS p
   WHERE EXISTS
       (SELECT 1
        FROM "Cervical Cytology Within 3 Years" AS sub
        WHERE sub.patient_id = p.patient_id)
     OR EXISTS
       (SELECT 1
        FROM "HPV Test Within 5 Years for Women Age 30 and Older" AS sub
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
         FROM "Encounter: Preventive Care Services Established Office Visit, 18 and Up"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Preventive Care Services Initial Office Visit, 18 and Up"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Home Healthcare Services"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Telephone Visits"
         UNION SELECT patient_id,
                      RESOURCE
         FROM "Encounter: Virtual Encounter") AS _union
      WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS ValidEncounters
   WHERE CAST(intervalStart(fhirpath_text(ValidEncounters.resource, 'period')) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
     AND CAST(intervalEnd(fhirpath_text(ValidEncounters.resource, 'period')) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)),
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
                                                                                             END BETWEEN 24 AND 64
     AND fhirpath_text(
                         (SELECT _pd.resource
                          FROM _patient_demographics AS _pd
                          WHERE _pd.patient_id = p.patient_id
                          LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex'').valueCode') = '248152002'
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
