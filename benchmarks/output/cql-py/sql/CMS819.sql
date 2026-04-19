-- Generated SQL for CMS819

WITH _patients AS
  (SELECT DISTINCT _outer.patient_ref AS patient_id
   FROM resources AS _outer
   WHERE _outer.patient_ref IS NOT NULL
     AND EXISTS
       (SELECT 1
        FROM resources AS _pt
        WHERE _pt.resourceType = 'Patient'
          AND _pt.id = _outer.patient_ref)
     AND _outer.patient_ref IN ('06d7810a-dcc6-4f6d-ab28-2a0843449475',
                                '11589117-d7b3-48d2-ac4e-b2dedd2dda37',
                                '1994e69a-472b-4e32-80c1-5c692f36acce',
                                '1de546d8-e39f-4d9f-b606-d3be3a24b3be',
                                '2adae583-4f70-4492-add5-c56cd38f5843',
                                '31b40acc-ca5f-4d1d-bd83-4b1a14eb822e',
                                '47e2c410-9c00-4f05-96b4-b925e0c158b1',
                                '6127705f-6f70-4134-9c87-1129389bea42',
                                '67f1ba74-5f3c-4729-9085-69bc55f49225',
                                '6d76c342-ac9f-4c46-b224-f39b8216d30e',
                                '73b0c1fe-874b-4982-8cb2-3c30520441de',
                                '8fc93696-e9a6-46a3-b8e9-7c7929e8ad36',
                                '93064568-a739-403d-853f-a3150bd8f752',
                                '9e1276d8-5574-424a-b093-0bd89b45019e',
                                'b88740a3-5143-4b36-ae0d-75a6b95db7e2',
                                'bdd17c60-c755-4150-8137-fa3884903970',
                                'bef27397-e972-46e8-8e92-b8d4fd7985dc',
                                'cf4e9832-fad4-4041-9c6b-e7605bf0b3a0')),
     _patient_demographics AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   CAST(fhirpath_date(r.resource, 'birthDate') AS DATE) AS birth_date
   FROM resources r
   WHERE r.resourceType = 'Patient'),
     "Encounter: Encounter Inpatient" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource,
                   fhirpath_text(r.resource, 'status') AS status
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.666.5.307')),
     "Encounter: Observation Services" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1111.143')),
     "Location" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Location'),
     "MedicationAdministration: Opioids, All" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'MedicationAdministration'
     AND (in_valueset(r.resource, 'medicationCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1196.226')
          OR EXISTS
            (SELECT '1'
             FROM resources AS m
             WHERE m.resourceType = 'Medication'
               AND LIST_EXTRACT(STR_SPLIT(fhirpath_text(r.resource, 'medicationReference.reference'), '/'), -1) = fhirpath_text(m.resource, 'id')
               AND in_valueset(m.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1196.226')))
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationadministrationnotdone'))),
     "Encounter: Emergency Department Visit" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'Encounter'
     AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.117.1.7.1.292')),
     "MedicationAdministration: Opioid Antagonist" AS
  (SELECT DISTINCT r.patient_ref AS patient_id,
                   r.resource
   FROM resources r
   WHERE r.resourceType = 'MedicationAdministration'
     AND (in_valueset(r.resource, 'medicationCodeableConcept', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1248.119')
          OR EXISTS
            (SELECT '1'
             FROM resources AS m
             WHERE m.resourceType = 'Medication'
               AND LIST_EXTRACT(STR_SPLIT(fhirpath_text(r.resource, 'medicationReference.reference'), '/'), -1) = fhirpath_text(m.resource, 'id')
               AND in_valueset(m.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1248.119')))
     AND (fhirpath_text(r.resource, 'status') IS NULL
          OR fhirpath_text(r.resource, 'status') != 'not-done')
     AND (json_extract(r.resource, '$.meta.profile') IS NULL
          OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-medicationadministrationnotdone'))),
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
     AND CAST(intervalEnd(fhirpath_text(EncounterInpatient.resource, 'period')) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))),
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
     "Non Enteral Opioid Antagonist Administration" AS
  (SELECT *
   FROM "MedicationAdministration: Opioid Antagonist" AS AntagonistGiven
   WHERE fhirpath_text(AntagonistGiven.resource, 'status') = 'completed'),
     "Opioid Administration" AS
  (SELECT *
   FROM "MedicationAdministration: Opioids, All" AS Opioids
   WHERE fhirpath_text(Opioids.resource, 'status') = 'completed'),
     "Qualifying Encounter" AS
  (SELECT *
   FROM "Encounter: Encounter Inpatient" AS InpatientEncounter
   WHERE EXTRACT(YEAR
                 FROM CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS DATE)) - EXTRACT(YEAR
                                                                                                                   FROM
                                                                                                                     (SELECT _pd.birth_date
                                                                                                                      FROM _patient_demographics AS _pd
                                                                                                                      WHERE _pd.patient_id = InpatientEncounter.patient_id
                                                                                                                      LIMIT 1)) - CASE
                                                                                                                                      WHEN EXTRACT(MONTH
                                                                                                                                                   FROM CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS DATE)) < EXTRACT(MONTH
                                                                                                                                                                                                                                                     FROM
                                                                                                                                                                                                                                                       (SELECT _pd.birth_date
                                                                                                                                                                                                                                                        FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                        WHERE _pd.patient_id = InpatientEncounter.patient_id
                                                                                                                                                                                                                                                        LIMIT 1))
                                                                                                                                           OR EXTRACT(MONTH
                                                                                                                                                      FROM CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS DATE)) = EXTRACT(MONTH
                                                                                                                                                                                                                                                        FROM
                                                                                                                                                                                                                                                          (SELECT _pd.birth_date
                                                                                                                                                                                                                                                           FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                           WHERE _pd.patient_id = InpatientEncounter.patient_id
                                                                                                                                                                                                                                                           LIMIT 1))
                                                                                                                                           AND EXTRACT(DAY
                                                                                                                                                       FROM CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS DATE)) < EXTRACT(DAY
                                                                                                                                                                                                                                                         FROM
                                                                                                                                                                                                                                                           (SELECT _pd.birth_date
                                                                                                                                                                                                                                                            FROM _patient_demographics AS _pd
                                                                                                                                                                                                                                                            WHERE _pd.patient_id = InpatientEncounter.patient_id
                                                                                                                                                                                                                                                            LIMIT 1)) THEN 1
                                                                                                                                      ELSE 0
                                                                                                                                  END >= 18
     AND CAST(intervalEnd(fhirpath_text(InpatientEncounter.resource, 'period')) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
     AND InpatientEncounter.status = 'finished'),
     "Encounter With Opioid Administration Outside Of Operating Room" AS
  (SELECT *
   FROM "Qualifying Encounter" AS InpatientEncounter
   WHERE EXISTS
       (SELECT 1
        FROM
          (SELECT *
           FROM "Opioid Administration") AS OpioidGiven
        WHERE intervalContains(intervalFromBounds(COALESCE(intervalStart(fhirpath_text(
                                                                                         (SELECT RESOURCE
                                                                                          FROM "Encounter: Emergency Department Visit" AS LastED
                                                                                          WHERE fhirpath_text(LastED.resource, 'status') = 'finished'
                                                                                            AND CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                            (SELECT RESOURCE
                                                                                                                                             FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                             WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                               AND CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                               AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS TIMESTAMP)
                                                                                                                                               AND LastObs.patient_id = InpatientEncounter.patient_id
                                                                                                                                             ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                             LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientEncounter.resource, 'period'))) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastED.resource, 'period')) AS TIMESTAMP)
                                                                                            AND CAST(intervalEnd(fhirpath_text(LastED.resource, 'period')) AS TIMESTAMP) <= CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                                                                                        (SELECT RESOURCE
                                                                                                                                                                                                                         FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                                                                                         WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                                                                           AND CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                           AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                           AND LastObs.patient_id = InpatientEncounter.patient_id
                                                                                                                                                                                                                         ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                                                                                         LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientEncounter.resource, 'period'))) AS TIMESTAMP)
                                                                                            AND LastED.patient_id = InpatientEncounter.patient_id
                                                                                          ORDER BY intervalEnd(fhirpath_text(LastED.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastED.resource, '$.id') ASC NULLS LAST
                                                                                          LIMIT 1), 'period')), COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                       (SELECT RESOURCE
                                                                                                                                                        FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                        WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                          AND CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                          AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                          AND LastObs.patient_id = InpatientEncounter.patient_id
                                                                                                                                                        ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                        LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientEncounter.resource, 'period')))), CAST(intervalEnd(fhirpath_text(InpatientEncounter.resource, 'period')) AS VARCHAR), TRUE, TRUE), intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                        WHEN fhirpath_text(OpioidGiven.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                        WHEN starts_with(LTRIM(fhirpath_text(OpioidGiven.resource, 'effective')), '{') THEN fhirpath_text(OpioidGiven.resource, 'effective')
                                                                                                                                                                                                                                                                                                                                                                        ELSE intervalFromBounds(fhirpath_text(OpioidGiven.resource, 'effective'), fhirpath_text(OpioidGiven.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                    END))
          AND NOT EXISTS
            (SELECT 1
             FROM
               (SELECT unnest(from_json(fhirpath(InpatientEncounter.resource, 'location'), '["VARCHAR"]')) AS _lt_EncounterLocation) AS _lt_unnest
             WHERE in_valueset(CASE
                                   WHEN
                                          (SELECT COUNT(*)
                                           FROM "Location" AS L
                                           WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_EncounterLocation, 'location.reference'), '/'), -1)
                                             AND L.patient_id = OpioidGiven.patient_id) = 1 THEN
                                          (SELECT RESOURCE
                                           FROM "Location" AS L
                                           WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_EncounterLocation, 'location.reference'), '/'), -1)
                                             AND L.patient_id = OpioidGiven.patient_id
                                           LIMIT 1)
                                   ELSE NULL
                               END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1248.141')
               AND intervalContains(fhirpath_text(_lt_EncounterLocation, 'period'), intervalStart(CASE
                                                                                                      WHEN fhirpath_text(OpioidGiven.resource, 'effective') IS NULL THEN NULL
                                                                                                      WHEN starts_with(LTRIM(fhirpath_text(OpioidGiven.resource, 'effective')), '{') THEN fhirpath_text(OpioidGiven.resource, 'effective')
                                                                                                      ELSE intervalFromBounds(fhirpath_text(OpioidGiven.resource, 'effective'), fhirpath_text(OpioidGiven.resource, 'effective'), TRUE, TRUE)
                                                                                                  END)))
          AND OpioidGiven.patient_id = InpatientEncounter.patient_id)),
     "Initial Population" AS
  (SELECT *
   FROM "Encounter With Opioid Administration Outside Of Operating Room"),
     "Denominator" AS
  (SELECT *
   FROM "Initial Population"),
     "Encounter With NonOperating Room Opioid And Antagonist Administration" AS
  (SELECT NonEnteralOpioidAntagonistGiven.patient_id,
          CAST(InpatientHospitalization.resource AS VARCHAR) AS RESOURCE
   FROM "Non Enteral Opioid Antagonist Administration" AS NonEnteralOpioidAntagonistGiven
   CROSS JOIN
     (SELECT *
      FROM "Opioid Administration") AS OpioidGiven
   CROSS JOIN
     (SELECT *
      FROM "Denominator") AS InpatientHospitalization
   WHERE NOT EXISTS
       (SELECT 1
        FROM
          (SELECT unnest(from_json(fhirpath(InpatientHospitalization.resource, 'location'), '["VARCHAR"]')) AS _lt_EncounterLocation) AS _lt_unnest
        WHERE in_valueset(CASE
                              WHEN
                                     (SELECT COUNT(*)
                                      FROM "Location" AS L
                                      WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_EncounterLocation, 'location.reference'), '/'), -1)
                                        AND L.patient_id = InpatientHospitalization.patient_id) = 1 THEN
                                     (SELECT RESOURCE
                                      FROM "Location" AS L
                                      WHERE fhirpath_text(L.resource, 'id') = LIST_EXTRACT(STR_SPLIT(fhirpath_text(_lt_EncounterLocation, 'location.reference'), '/'), -1)
                                        AND L.patient_id = InpatientHospitalization.patient_id
                                      LIMIT 1)
                              ELSE NULL
                          END, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1248.141')
          AND intervalContains(fhirpath_text(_lt_EncounterLocation, 'period'), intervalStart(CASE
                                                                                                 WHEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective') IS NULL THEN NULL
                                                                                                 WHEN starts_with(LTRIM(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')), '{') THEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')
                                                                                                 ELSE intervalFromBounds(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), TRUE, TRUE)
                                                                                             END)))
     AND intervalContains(intervalFromBounds(COALESCE(intervalStart(fhirpath_text(
                                                                                    (SELECT RESOURCE
                                                                                     FROM "Encounter: Emergency Department Visit" AS LastED
                                                                                     WHERE fhirpath_text(LastED.resource, 'status') = 'finished'
                                                                                       AND CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                       (SELECT RESOURCE
                                                                                                                                        FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                        WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                          AND CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                          AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP)
                                                                                                                                          AND LastObs.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                                                                        ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                        LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period'))) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastED.resource, 'period')) AS TIMESTAMP)
                                                                                       AND CAST(intervalEnd(fhirpath_text(LastED.resource, 'period')) AS TIMESTAMP) <= CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                                                                                   (SELECT RESOURCE
                                                                                                                                                                                                                    FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                                                                                    WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                                                                      AND CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                      AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                      AND LastObs.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                                                                                                                                                    ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                                                                                    LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period'))) AS TIMESTAMP)
                                                                                       AND LastED.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                     ORDER BY intervalEnd(fhirpath_text(LastED.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastED.resource, '$.id') ASC NULLS LAST
                                                                                     LIMIT 1), 'period')), COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                  (SELECT RESOURCE
                                                                                                                                                   FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                   WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                     AND CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                     AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                     AND LastObs.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                                                                                   ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                   LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')))), CAST(intervalEnd(fhirpath_text(InpatientHospitalization.resource, 'period')) AS VARCHAR), TRUE, TRUE), intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                               WHEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                               WHEN starts_with(LTRIM(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')), '{') THEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')
                                                                                                                                                                                                                                                                                                                                                                               ELSE intervalFromBounds(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                           END))
     AND intervalContains(intervalFromBounds(COALESCE(intervalStart(fhirpath_text(
                                                                                    (SELECT RESOURCE
                                                                                     FROM "Encounter: Emergency Department Visit" AS LastED
                                                                                     WHERE fhirpath_text(LastED.resource, 'status') = 'finished'
                                                                                       AND CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                       (SELECT RESOURCE
                                                                                                                                        FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                        WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                          AND CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                          AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP)
                                                                                                                                          AND LastObs.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                                                                        ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                        LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period'))) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastED.resource, 'period')) AS TIMESTAMP)
                                                                                       AND CAST(intervalEnd(fhirpath_text(LastED.resource, 'period')) AS TIMESTAMP) <= CAST(COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                                                                                   (SELECT RESOURCE
                                                                                                                                                                                                                    FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                                                                                    WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                                                                                      AND CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                      AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                                                                                      AND LastObs.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                                                                                                                                                    ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                                                                                    LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period'))) AS TIMESTAMP)
                                                                                       AND LastED.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                     ORDER BY intervalEnd(fhirpath_text(LastED.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastED.resource, '$.id') ASC NULLS LAST
                                                                                     LIMIT 1), 'period')), COALESCE(intervalStart(fhirpath_text(
                                                                                                                                                  (SELECT RESOURCE
                                                                                                                                                   FROM "Encounter: Observation Services" AS LastObs
                                                                                                                                                   WHERE fhirpath_text(LastObs.resource, 'status') = 'finished'
                                                                                                                                                     AND CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP) - INTERVAL '1 hour' <= CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                     AND CAST(intervalEnd(fhirpath_text(LastObs.resource, 'period')) AS TIMESTAMP) <= CAST(intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')) AS TIMESTAMP)
                                                                                                                                                     AND LastObs.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
                                                                                                                                                   ORDER BY intervalEnd(fhirpath_text(LastObs.resource, 'period')) DESC NULLS FIRST, json_extract_string(LastObs.resource, '$.id') ASC NULLS LAST
                                                                                                                                                   LIMIT 1), 'period')), intervalStart(fhirpath_text(InpatientHospitalization.resource, 'period')))), CAST(intervalEnd(fhirpath_text(InpatientHospitalization.resource, 'period')) AS VARCHAR), TRUE, TRUE), intervalStart(CASE
                                                                                                                                                                                                                                                                                                                                                                               WHEN fhirpath_text(OpioidGiven.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                                                                                                                                                                                                                                               WHEN starts_with(LTRIM(fhirpath_text(OpioidGiven.resource, 'effective')), '{') THEN fhirpath_text(OpioidGiven.resource, 'effective')
                                                                                                                                                                                                                                                                                                                                                                               ELSE intervalFromBounds(fhirpath_text(OpioidGiven.resource, 'effective'), fhirpath_text(OpioidGiven.resource, 'effective'), TRUE, TRUE)
                                                                                                                                                                                                                                                                                                                                                                           END))
     AND CAST(intervalStart(CASE
                                WHEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective') IS NULL THEN NULL
                                WHEN starts_with(LTRIM(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')), '{') THEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')
                                ELSE intervalFromBounds(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), TRUE, TRUE)
                            END) AS TIMESTAMP) - INTERVAL '12 hour' <= CAST(intervalEnd(CASE
                                                                                            WHEN fhirpath_text(OpioidGiven.resource, 'effective') IS NULL THEN NULL
                                                                                            WHEN starts_with(LTRIM(fhirpath_text(OpioidGiven.resource, 'effective')), '{') THEN fhirpath_text(OpioidGiven.resource, 'effective')
                                                                                            ELSE intervalFromBounds(fhirpath_text(OpioidGiven.resource, 'effective'), fhirpath_text(OpioidGiven.resource, 'effective'), TRUE, TRUE)
                                                                                        END) AS TIMESTAMP)
     AND CAST(intervalEnd(CASE
                              WHEN fhirpath_text(OpioidGiven.resource, 'effective') IS NULL THEN NULL
                              WHEN starts_with(LTRIM(fhirpath_text(OpioidGiven.resource, 'effective')), '{') THEN fhirpath_text(OpioidGiven.resource, 'effective')
                              ELSE intervalFromBounds(fhirpath_text(OpioidGiven.resource, 'effective'), fhirpath_text(OpioidGiven.resource, 'effective'), TRUE, TRUE)
                          END) AS TIMESTAMP) < CAST(intervalStart(CASE
                                                                      WHEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective') IS NULL THEN NULL
                                                                      WHEN starts_with(LTRIM(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')), '{') THEN fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective')
                                                                      ELSE intervalFromBounds(fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), fhirpath_text(NonEnteralOpioidAntagonistGiven.resource, 'effective'), TRUE, TRUE)
                                                                  END) AS TIMESTAMP)
     AND in_valueset(NonEnteralOpioidAntagonistGiven.resource, 'dosage.route', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113762.1.4.1248.187')
     AND OpioidGiven.patient_id = NonEnteralOpioidAntagonistGiven.patient_id
     AND InpatientHospitalization.patient_id = NonEnteralOpioidAntagonistGiven.patient_id),
     "Numerator" AS
  (SELECT *
   FROM "Encounter With NonOperating Room Opioid And Antagonist Administration"),
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

  (SELECT COALESCE(LIST("Numerator".resource), [])
   FROM "Numerator"
   WHERE "Numerator".patient_id = p.patient_id
     AND "Numerator".resource IS NOT NULL) AS Numerator
FROM _patients p
ORDER BY p.patient_id ASC
