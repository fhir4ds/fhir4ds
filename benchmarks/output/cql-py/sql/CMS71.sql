-- Generated SQL for CMS71

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('0035424c-e3be-4dc2-919a-fd1c665893f6',
                                '017a2267-f463-47a6-8b8b-dc91465e0869',
                                '02ee41e8-26d8-4575-a999-32ee2204d745',
                                '0c90d2ea-5034-4465-8e4a-4d0d4e17cd5a',
                                '0daf2fdb-6abc-4b7c-9417-3972c4813295',
                                '0f3f1ce7-9c34-4082-a635-f09ddcf53ac1',
                                '0fc5a0c1-02c0-4427-87d8-2e58f4be7b07',
                                '12f5363d-fa3f-4a61-aad9-defc8583ca12',
                                '18912918-19e8-4d17-8160-71849eaede4b',
                                '1a19c21b-41f3-4376-9516-529ad9fb466f',
                                '1dbcccc2-895d-46a7-b28a-bf936fc7978a',
                                '1f5b2ed3-23d6-4ffc-be6b-852117f506be',
                                '24ffee3e-9b5b-491e-8490-006d306e5f8a',
                                '29fd4e9e-7f7c-4356-8d72-7eabc8060963',
                                '2c1e6f23-20a1-44c3-8c2a-0bec67c3d2f5',
                                '2d694619-fb6d-43e5-8f56-4eb95752c7a7',
                                '2ed389dd-10d2-49b1-966b-f8bada7df530',
                                '3023ca44-3a4f-4be3-931b-784e9c9c46e9',
                                '31d1dbd5-28cf-49d0-a38d-0c84497c8457',
                                '3b8d6a18-b4a3-4369-b33c-6a6daa6b5b4c',
                                '3ed947b5-9aba-4bed-aa72-f96b6f3f5082',
                                '4151585a-f621-4de5-91df-4e4227e2165e',
                                '43d04e08-768c-4e5e-a7eb-44219c5e94b1',
                                '4543f40b-6f71-47e7-8930-0340eede9145',
                                '4580e833-7432-4f02-8742-8beceaac18e8',
                                '52951a0c-ccd4-4e47-9133-16ff3984ef12',
                                '5370c25e-ca3c-4575-95c2-e23c783ff4c6',
                                '541c6790-5a21-41ca-8e4e-49da54a28b9b',
                                '56ae006d-ab1b-428d-8614-2ccd5d962650',
                                '5704cb0f-a88b-4df3-b3d3-5438d3de4f6d',
                                '595ebfd1-fe6a-4b4b-96a1-23a72f6a70da',
                                '5dd3cb00-eb9b-42ba-9af5-9cafa1475528',
                                '60216757-e9a7-4e33-90f4-d0b1212bdea9',
                                '63e42e45-fb2a-4a44-8354-79ea81b5d041',
                                '81386d2f-e6d7-4433-b477-314e658f8cfe',
                                '856d71be-a360-47b3-a038-5cb3037bf1f2',
                                '85774da1-da62-45f3-9bf8-12223f13d82a',
                                '8646b35e-68e3-4932-ae69-0bd7fb4e7a27',
                                '86d68293-66ae-425b-bc4a-9ce429f4621e',
                                '928c8cab-5c42-4b56-bdf4-72d402eb6a61',
                                '93ddd5ec-1cd5-4894-afbb-65826d86f41e',
                                '93e2d9e6-00b4-4dfc-a404-f0bd5e73fa7b',
                                '96b57130-dda8-481b-b96b-c0d48068384e',
                                '971fefaa-cfa2-4e36-80d6-319f748d4b5f',
                                '9a72ea26-595f-4442-8b00-fc52ed228aa6',
                                'a0d01348-6938-4d7b-8f26-d4643658de9e',
                                'a2365453-d868-4111-b1dc-aad2e81d55fd',
                                'a8856231-e110-4811-ac95-3f65c3d440fa',
                                'a998e27f-e0a9-475d-80e8-0e9344591294',
                                'acdea97f-8a2e-4aa3-b51f-768c5ad5ead8',
                                'ad014d1d-6043-4b40-9fd3-0abc1f308a04',
                                'aedf9576-e1ce-4777-8e3a-5089076b50f4',
                                'b1d0c606-661d-44e8-a25f-4e7ca8131f2a',
                                'b29204ac-96ce-4be0-90ad-ae8ecfa4f245',
                                'b3bcdbbc-3b69-4e22-b993-b04d87f225a8',
                                'bfa4b097-4c27-4046-a036-d97267e94113',
                                'c5eb810c-2abd-41ac-9838-81ab77532845',
                                'c640ff8f-5b2a-448e-85a2-e739af7a8dc4',
                                'c6b15880-138d-42cd-8350-8a16968c246b',
                                'c7da5140-b9ed-4122-a159-914963fe387f',
                                'cc42fc09-d5ed-4ac5-980e-f16279cf0499',
                                'ccfddeae-a86e-4e43-adca-2ceef716970e',
                                'cec2b099-7f6d-4260-a2f8-bc0ed0b9c3e5',
                                'd4ee0f25-8c45-4db4-8795-b7dbdbbc1ecd',
                                'd5991213-5237-4eb3-a6e9-61404f836d3b',
                                'd9dc15b7-bf03-4b72-8dd5-3e4db21f052d',
                                'dbe7efdb-fd75-4da4-a998-ae7e04051bd1',
                                'de03a32b-a1f7-461c-9853-00c2e5586e99',
                                'de0b5b09-c285-4e02-b82c-ad23eb00febf',
                                'e20b4e76-8523-43ab-abc2-a4f4137a84bb',
                                'e695d66d-1f4e-4b69-acad-0861f1222d44',
                                'e73134ce-ad08-430e-b85e-d61e2d28d709',
                                'e73d1055-c564-4663-9af0-d3ccabeb49c8',
                                'e75d7e1c-df18-487e-a8f0-0b140e120581',
                                'e8df70c5-74a8-4a26-871c-0301bcf9fd45',
                                'ed792352-3bb4-435d-896a-d221df866142',
                                'f07b7d1a-b0da-4d44-acc6-eb2a6dfa0da3',
                                'f0d3eb0e-a93c-4caf-8233-499a105906de',
                                'f0de258a-3358-4f1d-a91d-e1c57a2cb61a',
                                'f7838ae4-6846-4bc0-a1e9-2002d5f5b357',
                                'f916d085-e8dc-4e8d-97ae-07952c1062b9',
                                'fb49e13d-3b13-46ae-8862-59033137e1b8',
                                'fd13e14c-cd97-4e81-9a69-e638b0a1fa58')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS VARCHAR) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Condition: History of Atrial Ablation (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1110.76')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Task" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'intent') AS intent,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Task'),
     "Procedure: Atrial Ablation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.203')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Condition (qicore-condition-encounter-diagnosis)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Observation: History of Atrial Ablation" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Observation'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1110.76')),
     "Encounter: Observation Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1111.143')),
     "Condition (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Condition: History of Atrial Ablation (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1110.76')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Condition: Atrial Fibrillation or Flutter (qicore-condition-problems-health-concerns)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Condition'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.202')
     AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "MedicationRequest: Anticoagulant Therapy (medicationnotrequested)" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'intent') AS intent,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'MedicationRequest'
     AND in_valueset(r.resource, 'medication', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.200')
     AND fhirpath_bool(r.resource, 'doNotPerform')),
     "Encounter: Emergency Department Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.292')),
     "MedicationRequest: Anticoagulant Therapy" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'intent') AS intent,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'MedicationRequest'
     AND in_valueset(r.resource, 'medication', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.200')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationnotrequested'))),
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
     "ServiceRequest: Comfort Measures" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'intent') AS intent,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'ServiceRequest'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/1.3.6.1.4.1.33895.1.3.0.45')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
     "Procedure: Comfort Measures" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Procedure'
     AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/1.3.6.1.4.1.33895.1.3.0.45')
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Encounter: Nonelective Inpatient Encounter" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.424')),
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
     "TJC.Intervention Comfort Measures" AS (
                                               (SELECT patient_id,
                                                       RESOURCE
                                                FROM "ServiceRequest: Comfort Measures" AS SR
                                                WHERE array_contains(['active', 'completed', 'on-hold'], SR.status)
                                                  AND array_contains(['order', 'original-order', 'reflex-order', 'filler-order', 'instance-order'], SR.intent)
                                                  AND fhirpath_text(SR.resource, 'doNotPerform') IS NOT TRUE)
                                             UNION
                                               (SELECT patient_id,
                                                       RESOURCE
                                                FROM "Procedure: Comfort Measures" AS InterventionPerformed
                                                WHERE array_contains(['completed', 'in-progress'], InterventionPerformed.status))),
     "TJC.Non Elective Inpatient Encounter With Age" AS
  (SELECT *
   FROM "Encounter: Nonelective Inpatient Encounter" AS NonElectiveEncounter
   WHERE EXTRACT(YEAR
                 FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(NonElectiveEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) - EXTRACT(YEAR
                                                                                                                                                                                             FROM TRY_CAST(
                                                                                                                                                                                                             (SELECT _pd.birth_date
                                                                                                                                                                                                              FROM _patient_demographics AS _pd
                                                                                                                                                                                                              WHERE _pd.patient_id = NonElectiveEncounter.patient_id
                                                                                                                                                                                                              LIMIT 1) AS TIMESTAMP)) - CASE
                                                                                                                                                                                                                                            WHEN EXTRACT(MONTH
                                                                                                                                                                                                                                                         FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(NonElectiveEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) < EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                                                                                                                     FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                                                                                                                     (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                                                                                      FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                                                                                      WHERE _pd.patient_id = NonElectiveEncounter.patient_id
                                                                                                                                                                                                                                                                                                                                                                                                                                                      LIMIT 1) AS TIMESTAMP))
                                                                                                                                                                                                                                                 OR EXTRACT(MONTH
                                                                                                                                                                                                                                                            FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(NonElectiveEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) = EXTRACT(MONTH
                                                                                                                                                                                                                                                                                                                                                                                                                                        FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                                                                                                                        (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                                                                                         FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                                                                                         WHERE _pd.patient_id = NonElectiveEncounter.patient_id
                                                                                                                                                                                                                                                                                                                                                                                                                                                         LIMIT 1) AS TIMESTAMP))
                                                                                                                                                                                                                                                 AND EXTRACT(DAY
                                                                                                                                                                                                                                                             FROM TRY_CAST(CAST(LEFT(REPLACE(CAST(intervalStart(fhirpath_text(NonElectiveEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AS TIMESTAMP)) < EXTRACT(DAY
                                                                                                                                                                                                                                                                                                                                                                                                                                         FROM TRY_CAST(
                                                                                                                                                                                                                                                                                                                                                                                                                                                         (SELECT _pd.birth_date
                                                                                                                                                                                                                                                                                                                                                                                                                                                          FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                                                                                                                                                                                                                          WHERE _pd.patient_id = NonElectiveEncounter.patient_id
                                                                                                                                                                                                                                                                                                                                                                                                                                                          LIMIT 1) AS TIMESTAMP)) THEN 1
                                                                                                                                                                                                                                            ELSE 0
                                                                                                                                                                                                                                        END >= 18
     AND CAST(LEFT(REPLACE(CAST(intervalEnd(fhirpath_text(NonElectiveEncounter.resource, 'period')) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) BETWEEN CAST(LEFT(REPLACE(CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR) AND COALESCE(CAST(LEFT(REPLACE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR), CAST(LEFT(REPLACE(CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS VARCHAR), ' ', 'T'), 10) AS VARCHAR))),
     "TJC.Ischemic Stroke Encounter" AS
  (SELECT *
   FROM "TJC.Non Elective Inpatient Encounter With Age" AS NonElectiveEncounterWithAge
   WHERE EXISTS
       (SELECT '1'
        FROM
          (SELECT patient_ref AS patient_id,
                  RESOURCE
           FROM resources
           WHERE resourceType = 'Claim') AS _c
        WHERE _c.patient_id = NonElectiveEncounterWithAge.patient_id
          AND fhirpath_text(_c.resource, 'status') = 'active'
          AND fhirpath_text(_c.resource, 'use') = 'claim'
          AND claim_principal_diagnosis(_c.resource, fhirpath_text(NonElectiveEncounterWithAge.resource, 'id')) IS NOT NULL
          AND (in_valueset(claim_principal_diagnosis(_c.resource, fhirpath_text(NonElectiveEncounterWithAge.resource, 'id')), 'diagnosisCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.247')
               OR EXISTS
                 (SELECT '1'
                  FROM
                    (SELECT patient_ref AS patient_id,
                            RESOURCE
                     FROM resources
                     WHERE resourceType = 'Condition') AS _cond
                  WHERE _cond.patient_id = NonElectiveEncounterWithAge.patient_id
                    AND in_valueset(_cond.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.247')
                    AND fhirpath_text(claim_principal_diagnosis(_c.resource, fhirpath_text(NonElectiveEncounterWithAge.resource, 'id')), 'diagnosisReference.reference') LIKE '%/' || fhirpath_text(_cond.resource, 'id'))))),
     "TJC.Comfort Measures During Hospitalization" AS
  (SELECT *
   FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "TJC.Intervention Comfort Measures") AS ComfortMeasure
        WHERE intervalContains(intervalFromBounds(COALESCE(intervalStart(fhirpath_text(
                                                                                         (SELECT RESOURCE
                                                                                          FROM "Encounter: Emergency Department Visit" AS LastED
                                                                                          WHERE fhirpath_text(LastED.resource, 'status') = 'finished'
                                                                                            AND REPLACE(CAST(CAST(CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                              (SELECT RESOURCE
                                                                                                                                                               FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                               WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                 AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                                 AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                                                                                 AND LastObs.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                               ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                               LIMIT 1), 'period')), intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))) AS VARCHAR) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastED.resource, 'period'))
                                                                                            AND intervalEnd(fhirpath_text(LastED.resource, 'period')) <= CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                                                                     (SELECT RESOURCE
                                                                                                                                                                                                      FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                                                                      WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                                                        AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                                                                        AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                                                                                                                        AND LastObs.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                                                                      ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                                                                      LIMIT 1), 'period')), intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))) AS VARCHAR)
                                                                                            AND LastED.patient_id = IschemicStrokeEncounter.patient_id
                                                                                          ORDER BY intervalEnd(fhirpath_text(LastED.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastED.resource, '$.id') ASC NULLS LAST
                                                                                          LIMIT 1), 'period')), COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                       (SELECT RESOURCE
                                                                                                                                                        FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                        WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                          AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                          AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                                                                          AND LastObs.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                        ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                        LIMIT 1), 'period')), intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')))), CAST(intervalEnd(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS VARCHAR), TRUE, TRUE), CAST(COALESCE(intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                                                WHEN fhirpath_text(ComfortMeasure.resource, 'performed') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                                                WHEN starts_with(LTRIM(fhirpath_text(ComfortMeasure.resource, 'performed')), '{') THEN fhirpath_text(ComfortMeasure.resource, 'performed')
                                                                                                                                                                                                                                                                                                                                                                                                ELSE intervalFromBounds(fhirpath_text(ComfortMeasure.resource, 'performed'), fhirpath_text(ComfortMeasure.resource, 'performed'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                                            END), fhirpath_text(ComfortMeasure.resource, 'authoredOn')) AS VARCHAR))
          AND ComfortMeasure.patient_id = IschemicStrokeEncounter.patient_id)),
     "TJC.Encounter With Comfort Measures During Hospitalization" AS
  (SELECT *
   FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "TJC.Intervention Comfort Measures") AS ComfortMeasure
        WHERE intervalContains(intervalFromBounds(COALESCE(intervalStart(fhirpath_text(
                                                                                         (SELECT RESOURCE
                                                                                          FROM "Encounter: Emergency Department Visit" AS LastED
                                                                                          WHERE fhirpath_text(LastED.resource, 'status') = 'finished'
                                                                                            AND REPLACE(CAST(CAST(CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                              (SELECT RESOURCE
                                                                                                                                                               FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                               WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                 AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                                 AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                                                                                 AND LastObs.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                               ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                               LIMIT 1), 'period')), intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))) AS VARCHAR) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastED.resource, 'period'))
                                                                                            AND intervalEnd(fhirpath_text(LastED.resource, 'period')) <= CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                                                                     (SELECT RESOURCE
                                                                                                                                                                                                      FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                                                                      WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                                                        AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                                                                        AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                                                                                                                        AND LastObs.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                                                                      ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                                                                      LIMIT 1), 'period')), intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))) AS VARCHAR)
                                                                                            AND LastED.patient_id = IschemicStrokeEncounter.patient_id
                                                                                          ORDER BY intervalEnd(fhirpath_text(LastED.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastED.resource, '$.id') ASC NULLS LAST
                                                                                          LIMIT 1), 'period')), COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                       (SELECT RESOURCE
                                                                                                                                                        FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                        WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                          AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                          AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                                                                          AND LastObs.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                        ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                        LIMIT 1), 'period')), intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period')))), CAST(intervalEnd(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS VARCHAR), TRUE, TRUE), CAST(COALESCE(intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                                                WHEN fhirpath_text(ComfortMeasure.resource, 'performed') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                                                WHEN starts_with(LTRIM(fhirpath_text(ComfortMeasure.resource, 'performed')), '{') THEN fhirpath_text(ComfortMeasure.resource, 'performed')
                                                                                                                                                                                                                                                                                                                                                                                                ELSE intervalFromBounds(fhirpath_text(ComfortMeasure.resource, 'performed'), fhirpath_text(ComfortMeasure.resource, 'performed'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                                            END), fhirpath_text(ComfortMeasure.resource, 'authoredOn')) AS VARCHAR))
          AND ComfortMeasure.patient_id = IschemicStrokeEncounter.patient_id)),
     "TJC.Ischemic Stroke Encounters With Discharge Disposition" AS
  (SELECT *
   FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
   WHERE in_valueset(IschemicStrokeEncounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.87')
     OR in_valueset(IschemicStrokeEncounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.308')
     OR in_valueset(IschemicStrokeEncounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.309')
     OR in_valueset(IschemicStrokeEncounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.209')
     OR in_valueset(IschemicStrokeEncounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.207')),
     "Documented Reason For Not Giving Anticoagulant At Discharge" AS (
                                                                         (SELECT patient_id,
                                                                                 RESOURCE
                                                                          FROM "MedicationRequest: Anticoagulant Therapy (medicationnotrequested)" AS NoAnticoagulant
                                                                          WHERE (in_valueset(NoAnticoagulant.resource, 'reasonCode', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.473')
                                                                                 OR in_valueset(NoAnticoagulant.resource, 'reasonCode', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.93'))
                                                                            AND (fhirpath_bool(NoAnticoagulant.resource, 'category.coding.where(system=''http://terminology.hl7.org/CodeSystem/medicationrequest-category'' and code=''community'').exists()')
                                                                                 OR fhirpath_bool(NoAnticoagulant.resource, 'category.coding.where(system=''http://terminology.hl7.org/CodeSystem/medicationrequest-category'' and code=''discharge'').exists()'))
                                                                            AND array_contains(['active', 'completed'], NoAnticoagulant.status)
                                                                            AND array_contains(['order', 'original-order', 'reflex-order', 'filler-order', 'instance-order'], NoAnticoagulant.intent))
                                                                       UNION
                                                                         (SELECT patient_id,
                                                                                 RESOURCE
                                                                          FROM "MedicationRequest: Anticoagulant Therapy" AS MedReqAntiCoagulant
                                                                          WHERE EXISTS
                                                                              (SELECT 1
                                                                               FROM "Task" AS TaskReject
                                                                               WHERE fhirpath_text(MedReqAntiCoagulant.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(TaskReject.resource, 'focus.reference'), '/'), -1)
                                                                                 AND (in_valueset(TaskReject.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.473')
                                                                                      OR in_valueset(TaskReject.resource, 'statusReason', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.93'))
                                                                                 AND array_contains(['active', 'completed'], fhirpath_text(MedReqAntiCoagulant.resource, 'status'))
                                                                                 AND fhirpath_bool(TaskReject.resource, 'code.coding.where(system=''http://hl7.org/fhir/CodeSystem/task-code'' and code=''fulfill'').exists()')
                                                                                 AND TaskReject.patient_id = MedReqAntiCoagulant.patient_id))),
     "Encounter With A History Of Atrial Ablation" AS (
                                                         (SELECT patient_id,
                                                                 RESOURCE
                                                          FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
                                                          WHERE EXISTS
                                                              (SELECT *
                                                               FROM "Procedure: Atrial Ablation" AS AtrialAblationProcedure
                                                               WHERE fhirpath_text(AtrialAblationProcedure.resource, 'status') = 'completed'
                                                                 AND intervalStart(CASE
                                                                                       WHEN fhirpath_text(AtrialAblationProcedure.resource, 'performed') IS NULL THEN NULL
                                                                                       WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationProcedure.resource, 'performed')), '{') THEN fhirpath_text(AtrialAblationProcedure.resource, 'performed')
                                                                                       ELSE intervalFromBounds(fhirpath_text(AtrialAblationProcedure.resource, 'performed'), fhirpath_text(AtrialAblationProcedure.resource, 'performed'), TRUE, TRUE)
                                                                                   END) < intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                 AND AtrialAblationProcedure.patient_id = IschemicStrokeEncounter.patient_id))
                                                       UNION
                                                         (SELECT patient_id,
                                                                 RESOURCE
                                                          FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
                                                          WHERE EXISTS
                                                              (SELECT 1
                                                               FROM "Condition: History of Atrial Ablation (qicore-condition-problems-health-concerns)" AS AtrialAblationDiagnosis
                                                               WHERE (NOT (fhirpath_text(AtrialAblationDiagnosis.resource, 'verificationStatus') IS NOT NULL)
                                                                      OR NOT fhirpath_bool(AtrialAblationDiagnosis.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()')
                                                                      AND NOT fhirpath_bool(AtrialAblationDiagnosis.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''entered-in-error'').exists()'))
                                                                 AND intervalStart(CASE
                                                                                       WHEN fhirpath_text(AtrialAblationDiagnosis.resource, 'onset') IS NULL THEN NULL
                                                                                       WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationDiagnosis.resource, 'onset')), '{') THEN fhirpath_text(AtrialAblationDiagnosis.resource, 'onset')
                                                                                       ELSE intervalFromBounds(fhirpath_text(AtrialAblationDiagnosis.resource, 'onset'), fhirpath_text(AtrialAblationDiagnosis.resource, 'onset'), TRUE, TRUE)
                                                                                   END) < intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                 AND AtrialAblationDiagnosis.patient_id = IschemicStrokeEncounter.patient_id))
                                                       UNION
                                                         (SELECT patient_id,
                                                                 RESOURCE
                                                          FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
                                                          WHERE EXISTS
                                                              (SELECT 1
                                                               FROM "Observation: History of Atrial Ablation" AS AtrialAblationObservation
                                                               WHERE array_contains(['final', 'amended', 'corrected'], fhirpath_text(AtrialAblationObservation.resource, 'status'))
                                                                 AND cqlSameOrBefore(CAST(CASE
                                                                                              WHEN NOT (intervalStart(CASE
                                                                                                                          WHEN fhirpath_text(AtrialAblationObservation.resource, 'effective') IS NULL THEN NULL
                                                                                                                          WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationObservation.resource, 'effective')), '{') THEN fhirpath_text(AtrialAblationObservation.resource, 'effective')
                                                                                                                          ELSE intervalFromBounds(fhirpath_text(AtrialAblationObservation.resource, 'effective'), fhirpath_text(AtrialAblationObservation.resource, 'effective'), TRUE, TRUE)
                                                                                                                      END) IS NULL
                                                                                                        OR intervalStart(CASE
                                                                                                                             WHEN fhirpath_text(AtrialAblationObservation.resource, 'effective') IS NULL THEN NULL
                                                                                                                             WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationObservation.resource, 'effective')), '{') THEN fhirpath_text(AtrialAblationObservation.resource, 'effective')
                                                                                                                             ELSE intervalFromBounds(fhirpath_text(AtrialAblationObservation.resource, 'effective'), fhirpath_text(AtrialAblationObservation.resource, 'effective'), TRUE, TRUE)
                                                                                                                         END) = '0001-01-01 00:00:00') THEN intervalStart(CASE
                                                                                                                                                                              WHEN fhirpath_text(AtrialAblationObservation.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                              WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationObservation.resource, 'effective')), '{') THEN fhirpath_text(AtrialAblationObservation.resource, 'effective')
                                                                                                                                                                              ELSE intervalFromBounds(fhirpath_text(AtrialAblationObservation.resource, 'effective'), fhirpath_text(AtrialAblationObservation.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                          END)
                                                                                              ELSE intervalEnd(CASE
                                                                                                                   WHEN fhirpath_text(AtrialAblationObservation.resource, 'effective') IS NULL THEN NULL
                                                                                                                   WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationObservation.resource, 'effective')), '{') THEN fhirpath_text(AtrialAblationObservation.resource, 'effective')
                                                                                                                   ELSE intervalFromBounds(fhirpath_text(AtrialAblationObservation.resource, 'effective'), fhirpath_text(AtrialAblationObservation.resource, 'effective'), TRUE, TRUE)
                                                                                                               END)
                                                                                          END AS VARCHAR), CAST(intervalEnd(fhirpath_text(IschemicStrokeEncounter.resource, 'period')) AS VARCHAR))
                                                                 AND AtrialAblationObservation.patient_id = IschemicStrokeEncounter.patient_id))
                                                       UNION
                                                         (SELECT patient_id,
                                                                 RESOURCE
                                                          FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
                                                          WHERE EXISTS
                                                              (SELECT 1
                                                               FROM "Condition: History of Atrial Ablation (qicore-condition-encounter-diagnosis)" AS AtrialAblationEncDiagnosis
                                                               WHERE (NOT (fhirpath_text(AtrialAblationEncDiagnosis.resource, 'verificationStatus') IS NOT NULL)
                                                                      OR NOT fhirpath_bool(AtrialAblationEncDiagnosis.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()')
                                                                      AND NOT fhirpath_bool(AtrialAblationEncDiagnosis.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''entered-in-error'').exists()'))
                                                                 AND intervalStart(CASE
                                                                                       WHEN fhirpath_text(AtrialAblationEncDiagnosis.resource, 'onset') IS NULL THEN NULL
                                                                                       WHEN starts_with(LTRIM(fhirpath_text(AtrialAblationEncDiagnosis.resource, 'onset')), '{') THEN fhirpath_text(AtrialAblationEncDiagnosis.resource, 'onset')
                                                                                       ELSE intervalFromBounds(fhirpath_text(AtrialAblationEncDiagnosis.resource, 'onset'), fhirpath_text(AtrialAblationEncDiagnosis.resource, 'onset'), TRUE, TRUE)
                                                                                   END) < intervalStart(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                 AND AtrialAblationEncDiagnosis.patient_id = IschemicStrokeEncounter.patient_id))),
     "Encounter With Prior Or Present Diagnosis Of Atrial Fibrillation Or Flutter" AS (
                                                                                         (SELECT patient_id,
                                                                                                 RESOURCE
                                                                                          FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
                                                                                          WHERE EXISTS
                                                                                              (SELECT 1
                                                                                               FROM "Condition: Atrial Fibrillation or Flutter (qicore-condition-problems-health-concerns)" AS AtrialFibrillationFlutter
                                                                                               WHERE (NOT (fhirpath_text(AtrialFibrillationFlutter.resource, 'verificationStatus') IS NOT NULL)
                                                                                                      OR NOT fhirpath_bool(AtrialFibrillationFlutter.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''refuted'').exists()')
                                                                                                      AND NOT fhirpath_bool(AtrialFibrillationFlutter.resource, 'verificationStatus.coding.where(system=''http://terminology.hl7.org/CodeSystem/condition-ver-status'' and code=''entered-in-error'').exists()'))
                                                                                                 AND LEFT(CAST(intervalStart(CASE
                                                                                                                                 WHEN fhirpath_text(AtrialFibrillationFlutter.resource, 'onset') IS NULL THEN NULL
                                                                                                                                 WHEN starts_with(LTRIM(fhirpath_text(AtrialFibrillationFlutter.resource, 'onset')), '{') THEN fhirpath_text(AtrialFibrillationFlutter.resource, 'onset')
                                                                                                                                 ELSE intervalFromBounds(fhirpath_text(AtrialFibrillationFlutter.resource, 'onset'), fhirpath_text(AtrialFibrillationFlutter.resource, 'onset'), TRUE, TRUE)
                                                                                                                             END) AS VARCHAR), 10) <= intervalEnd(fhirpath_text(IschemicStrokeEncounter.resource, 'period'))
                                                                                                 AND AtrialFibrillationFlutter.patient_id = IschemicStrokeEncounter.patient_id))
                                                                                       UNION
                                                                                         (SELECT patient_id,
                                                                                                 RESOURCE
                                                                                          FROM "TJC.Ischemic Stroke Encounter" AS IschemicStrokeEncounter
                                                                                          WHERE EXISTS
                                                                                              (SELECT 1
                                                                                               FROM
                                                                                                 (SELECT unnest(from_json(fhirpath(IschemicStrokeEncounter.resource, 'reasonReference'), '["VARCHAR"]')) AS _lt_D) AS _lt_unnest
                                                                                               WHERE EXISTS
                                                                                                   (SELECT 1
                                                                                                    FROM
                                                                                                      (SELECT unnest(
                                                                                                                       (SELECT list(CASE
                                                                                                                                        WHEN
                                                                                                                                               (SELECT COUNT(*)
                                                                                                                                                FROM
                                                                                                                                                  (SELECT patient_id, RESOURCE
                                                                                                                                                   FROM "Condition (qicore-condition-encounter-diagnosis)"
                                                                                                                                                   UNION SELECT patient_id, RESOURCE
                                                                                                                                                   FROM "Condition (qicore-condition-problems-health-concerns)") AS C
                                                                                                                                                WHERE fhirpath_text(C.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_D, 'reference'), '/'), -1)
                                                                                                                                                  AND C.patient_id = IschemicStrokeEncounter.patient_id) = 1 THEN
                                                                                                                                               (SELECT RESOURCE
                                                                                                                                                FROM
                                                                                                                                                  (SELECT patient_id, RESOURCE
                                                                                                                                                   FROM "Condition (qicore-condition-encounter-diagnosis)"
                                                                                                                                                   UNION SELECT patient_id, RESOURCE
                                                                                                                                                   FROM "Condition (qicore-condition-problems-health-concerns)") AS C
                                                                                                                                                WHERE fhirpath_text(C.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_D, 'reference'), '/'), -1)
                                                                                                                                                  AND C.patient_id = IschemicStrokeEncounter.patient_id
                                                                                                                                                LIMIT 1)
                                                                                                                                        ELSE NULL
                                                                                                                                    END)
                                                                                                                        FROM
                                                                                                                          (SELECT unnest(from_json(fhirpath(IschemicStrokeEncounter.resource, 'reasonReference'), '["VARCHAR"]')) AS _lt_D) AS _lt_unnest)) AS _ivr) AS _ivt
                                                                                                    WHERE in_valueset(_ivr, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.202'))))),
     "Denominator" AS (
                         (SELECT patient_id,
                                 RESOURCE
                          FROM "Encounter With A History Of Atrial Ablation")
                       UNION
                         (SELECT patient_id,
                                 RESOURCE
                          FROM "Encounter With Prior Or Present Diagnosis Of Atrial Fibrillation Or Flutter")),
     "Denominator Exceptions" AS
  (SELECT *
   FROM "Denominator" AS Encounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Documented Reason For Not Giving Anticoagulant At Discharge") AS NoDischargeAnticoagulant
        WHERE intervalContains(fhirpath_text(Encounter.resource, 'period'), fhirpath_text(NoDischargeAnticoagulant.resource, 'authoredOn'))
          AND NoDischargeAnticoagulant.patient_id = Encounter.patient_id)),
     "Encounter With Comfort Measures During Hospitalization For Patients With Documented Atrial Fibrillation Or Flutter" AS
  (SELECT *
   FROM "Denominator" AS Encounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "TJC.Intervention Comfort Measures") AS ComfortMeasure
        WHERE intervalContains(intervalFromBounds(COALESCE(intervalStart(fhirpath_text(
                                                                                         (SELECT RESOURCE
                                                                                          FROM "Encounter: Emergency Department Visit" AS LastED
                                                                                          WHERE fhirpath_text(LastED.resource, 'status') = 'finished'
                                                                                            AND REPLACE(CAST(CAST(CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                              (SELECT RESOURCE
                                                                                                                                                               FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                               WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                 AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                                 AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(Encounter.resource, 'period'))
                                                                                                                                                                 AND LastObs.patient_id = Encounter.patient_id
                                                                                                                                                               ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                               LIMIT 1), 'period')), intervalStart(fhirpath_text(Encounter.resource, 'period'))) AS VARCHAR) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastED.resource, 'period'))
                                                                                            AND intervalEnd(fhirpath_text(LastED.resource, 'period')) <= CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                                                                     (SELECT RESOURCE
                                                                                                                                                                                                      FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                                                                      WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                                                        AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                                                                        AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(Encounter.resource, 'period'))
                                                                                                                                                                                                        AND LastObs.patient_id = Encounter.patient_id
                                                                                                                                                                                                      ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                                                                      LIMIT 1), 'period')), intervalStart(fhirpath_text(Encounter.resource, 'period'))) AS VARCHAR)
                                                                                            AND LastED.patient_id = Encounter.patient_id
                                                                                          ORDER BY intervalEnd(fhirpath_text(LastED.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastED.resource, '$.id') ASC NULLS LAST
                                                                                          LIMIT 1), 'period')), COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                       (SELECT RESOURCE
                                                                                                                                                        FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                        WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                          AND REPLACE(CAST(CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' AS VARCHAR), ' ', 'T') <= intervalEnd(fhirpath_text(LastObs.resource, 'period'))
                                                                                                                                                          AND intervalEnd(fhirpath_text(LastObs.resource, 'period')) <= intervalStart(fhirpath_text(Encounter.resource, 'period'))
                                                                                                                                                          AND LastObs.patient_id = Encounter.patient_id
                                                                                                                                                        ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                        LIMIT 1), 'period')), intervalStart(fhirpath_text(Encounter.resource, 'period')))), CAST(intervalEnd(fhirpath_text(Encounter.resource, 'period')) AS VARCHAR), TRUE, TRUE), CAST(COALESCE(intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                    WHEN fhirpath_text(ComfortMeasure.resource, 'performed') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                    WHEN starts_with(LTRIM(fhirpath_text(ComfortMeasure.resource, 'performed')), '{') THEN fhirpath_text(ComfortMeasure.resource, 'performed')
                                                                                                                                                                                                                                                                                                                                                                    ELSE intervalFromBounds(fhirpath_text(ComfortMeasure.resource, 'performed'), fhirpath_text(ComfortMeasure.resource, 'performed'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                END), fhirpath_text(ComfortMeasure.resource, 'authoredOn')) AS VARCHAR))
          AND ComfortMeasure.patient_id = Encounter.patient_id)),
     "Denominator Exclusions" AS (
                                    (SELECT patient_id,
                                            RESOURCE
                                     FROM "Denominator" AS Encounter
                                     WHERE fhirpath_text(Encounter.resource, 'status') = 'finished'
                                       AND (in_valueset(Encounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.87')
                                            OR in_valueset(Encounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.308')
                                            OR in_valueset(Encounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.309')
                                            OR in_valueset(Encounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.209')
                                            OR in_valueset(Encounter.resource, 'hospitalization.dischargeDisposition', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.207')))
                                  UNION
                                    (SELECT patient_id,
                                            RESOURCE
                                     FROM "Encounter With Comfort Measures During Hospitalization For Patients With Documented Atrial Fibrillation Or Flutter")),
     "Initial Population" AS
  (SELECT *
   FROM "TJC.Ischemic Stroke Encounter"),
     "Numerator" AS
  (SELECT *
   FROM "Denominator" AS Encounter
   WHERE EXISTS
       (SELECT 1
        FROM "MedicationRequest: Anticoagulant Therapy" AS DischargeAnticoagulant
        WHERE array_contains(['active', 'completed'], fhirpath_text(DischargeAnticoagulant.resource, 'status'))
          AND array_contains(['order', 'original-order', 'reflex-order', 'filler-order', 'instance-order'], fhirpath_text(DischargeAnticoagulant.resource, 'intent'))
          AND (fhirpath_bool(DischargeAnticoagulant.resource, 'category.coding.where(system=''http://terminology.hl7.org/CodeSystem/medicationrequest-category'' and code=''community'').exists()')
               OR fhirpath_bool(DischargeAnticoagulant.resource, 'category.coding.where(system=''http://terminology.hl7.org/CodeSystem/medicationrequest-category'' and code=''discharge'').exists()'))
          AND intervalContains(fhirpath_text(Encounter.resource, 'period'), fhirpath_text(DischargeAnticoagulant.resource, 'authoredOn'))
          AND NOT EXISTS
            (SELECT *
             FROM "Task" AS TaskReject
             WHERE fhirpath_text(DischargeAnticoagulant.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(TaskReject.resource, 'focus.reference'), '/'), -1)
               AND fhirpath_bool(TaskReject.resource, 'code.coding.where(system=''http://hl7.org/fhir/CodeSystem/task-code'' and code=''fulfill'').exists()')
               AND TaskReject.patient_id = DischargeAnticoagulant.patient_id)
          AND DischargeAnticoagulant.patient_id = Encounter.patient_id)),
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

  (SELECT COALESCE(LIST(json_extract_string("Initial Population".resource, '$.resourceType') || '/' || json_extract_string("Initial Population".resource, '$.id')), [])
   FROM "Initial Population"
   WHERE "Initial Population".patient_id = p.patient_id
     AND "Initial Population".resource IS NOT NULL) AS "Initial Population",

  (SELECT COALESCE(LIST(json_extract_string("Denominator".resource, '$.resourceType') || '/' || json_extract_string("Denominator".resource, '$.id')), [])
   FROM "Denominator"
   WHERE "Denominator".patient_id = p.patient_id
     AND "Denominator".resource IS NOT NULL) AS Denominator,

  (SELECT COALESCE(LIST(json_extract_string("Denominator Exclusions".resource, '$.resourceType') || '/' || json_extract_string("Denominator Exclusions".resource, '$.id')), [])
   FROM "Denominator Exclusions"
   WHERE "Denominator Exclusions".patient_id = p.patient_id
     AND "Denominator Exclusions".resource IS NOT NULL) AS "Denominator Exclusions",

  (SELECT COALESCE(LIST(json_extract_string("Denominator Exceptions".resource, '$.resourceType') || '/' || json_extract_string("Denominator Exceptions".resource, '$.id')), [])
   FROM "Denominator Exceptions"
   WHERE "Denominator Exceptions".patient_id = p.patient_id
     AND "Denominator Exceptions".resource IS NOT NULL) AS "Denominator Exceptions",

  (SELECT COALESCE(LIST(json_extract_string("Numerator".resource, '$.resourceType') || '/' || json_extract_string("Numerator".resource, '$.id')), [])
   FROM "Numerator"
   WHERE "Numerator".patient_id = p.patient_id
     AND "Numerator".resource IS NOT NULL) AS Numerator
FROM _patients p
ORDER BY p.patient_id ASC
