-- Generated SQL for measure

WITH _vs_0(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','183919006'), ('http://snomed.info/sct','183920000'), ('http://snomed.info/sct','183921001'), ('http://snomed.info/sct','305336008'), ('http://snomed.info/sct','305911006'), ('http://snomed.info/sct','385765002'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9473'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9474'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9475'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9476'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9477'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9478'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9479'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5003'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5004'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5005'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5006'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5007'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5008'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5010'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','S9126'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2042'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2043'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2044'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2045'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2046')),
_vs_1(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','170935008'), ('http://snomed.info/sct','170936009'), ('http://snomed.info/sct','305911006')),
_vs_2(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','234723000'), ('http://snomed.info/sct','313042009'), ('http://snomed.info/sct','35889000'), ('http://snomed.info/sct','70468009'), ('http://www.ada.org/cdt','D1206'), ('http://www.ada.org/cdt','D1208')),
_vs_3(_vs_system, _vs_code) AS (VALUES ('http://www.ada.org/cdt','D0120'), ('http://www.ada.org/cdt','D0140'), ('http://www.ada.org/cdt','D0145'), ('http://www.ada.org/cdt','D0150'), ('http://www.ada.org/cdt','D0160'), ('http://www.ada.org/cdt','D0170'), ('http://www.ada.org/cdt','D0180')),
_vs_4(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','170935008'), ('http://snomed.info/sct','170936009'), ('http://snomed.info/sct','385763009'), ('http://www.ama-assn.org/go/cpt','99377'), ('http://www.ama-assn.org/go/cpt','99378'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G0182')),
_vs_5(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','183452005'), ('http://snomed.info/sct','32485007'), ('http://snomed.info/sct','8715000')),
_vs_6(_vs_system, _vs_code) AS (VALUES ('https://nahdo.org/sopt','1'), ('https://nahdo.org/sopt','11'), ('https://nahdo.org/sopt','111'), ('https://nahdo.org/sopt','1111'), ('https://nahdo.org/sopt','1112'), ('https://nahdo.org/sopt','112'), ('https://nahdo.org/sopt','113'), ('https://nahdo.org/sopt','119'), ('https://nahdo.org/sopt','12'), ('https://nahdo.org/sopt','121'), ('https://nahdo.org/sopt','122'), ('https://nahdo.org/sopt','123'), ('https://nahdo.org/sopt','129'), ('https://nahdo.org/sopt','13'), ('https://nahdo.org/sopt','14'), ('https://nahdo.org/sopt','141'), ('https://nahdo.org/sopt','142'), ('https://nahdo.org/sopt','19'), ('https://nahdo.org/sopt','191'), ('https://nahdo.org/sopt','2'), ('https://nahdo.org/sopt','21'), ('https://nahdo.org/sopt','211'), ('https://nahdo.org/sopt','212'), ('https://nahdo.org/sopt','213'), ('https://nahdo.org/sopt','219'), ('https://nahdo.org/sopt','22'), ('https://nahdo.org/sopt','23'), ('https://nahdo.org/sopt','25'), ('https://nahdo.org/sopt','26'), ('https://nahdo.org/sopt','29'), ('https://nahdo.org/sopt','291'), ('https://nahdo.org/sopt','299'), ('https://nahdo.org/sopt','3'), ('https://nahdo.org/sopt','31'), ('https://nahdo.org/sopt','311'), ('https://nahdo.org/sopt','3111'), ('https://nahdo.org/sopt','3112'), ('https://nahdo.org/sopt','3113'), ('https://nahdo.org/sopt','3114'), ('https://nahdo.org/sopt','3115'), ('https://nahdo.org/sopt','3116'), ('https://nahdo.org/sopt','3119'), ('https://nahdo.org/sopt','312'), ('https://nahdo.org/sopt','3121'), ('https://nahdo.org/sopt','3122'), ('https://nahdo.org/sopt','3123'), ('https://nahdo.org/sopt','313'), ('https://nahdo.org/sopt','32'), ('https://nahdo.org/sopt','321'), ('https://nahdo.org/sopt','3211'), ('https://nahdo.org/sopt','3212'), ('https://nahdo.org/sopt','32121'), ('https://nahdo.org/sopt','32122'), ('https://nahdo.org/sopt','32123'), ('https://nahdo.org/sopt','32124'), ('https://nahdo.org/sopt','32125'), ('https://nahdo.org/sopt','32126'), ('https://nahdo.org/sopt','32127'), ('https://nahdo.org/sopt','32128'), ('https://nahdo.org/sopt','322'), ('https://nahdo.org/sopt','3221'), ('https://nahdo.org/sopt','3222'), ('https://nahdo.org/sopt','3223'), ('https://nahdo.org/sopt','3229'), ('https://nahdo.org/sopt','33'), ('https://nahdo.org/sopt','331'), ('https://nahdo.org/sopt','332'), ('https://nahdo.org/sopt','333'), ('https://nahdo.org/sopt','334'), ('https://nahdo.org/sopt','34'), ('https://nahdo.org/sopt','341'), ('https://nahdo.org/sopt','342'), ('https://nahdo.org/sopt','343'), ('https://nahdo.org/sopt','344'), ('https://nahdo.org/sopt','349'), ('https://nahdo.org/sopt','35'), ('https://nahdo.org/sopt','36'), ('https://nahdo.org/sopt','361'), ('https://nahdo.org/sopt','362'), ('https://nahdo.org/sopt','369'), ('https://nahdo.org/sopt','37'), ('https://nahdo.org/sopt','371'), ('https://nahdo.org/sopt','3711'), ('https://nahdo.org/sopt','3712'), ('https://nahdo.org/sopt','3713'), ('https://nahdo.org/sopt','372'), ('https://nahdo.org/sopt','379'), ('https://nahdo.org/sopt','38'), ('https://nahdo.org/sopt','381'), ('https://nahdo.org/sopt','3811'), ('https://nahdo.org/sopt','3812'), ('https://nahdo.org/sopt','3813'), ('https://nahdo.org/sopt','3819'), ('https://nahdo.org/sopt','382'), ('https://nahdo.org/sopt','389'), ('https://nahdo.org/sopt','39'), ('https://nahdo.org/sopt','391'), ('https://nahdo.org/sopt','4'), ('https://nahdo.org/sopt','41'), ('https://nahdo.org/sopt','42'), ('https://nahdo.org/sopt','43'), ('https://nahdo.org/sopt','44'), ('https://nahdo.org/sopt','5'), ('https://nahdo.org/sopt','51'), ('https://nahdo.org/sopt','511'), ('https://nahdo.org/sopt','512'), ('https://nahdo.org/sopt','513'), ('https://nahdo.org/sopt','514'), ('https://nahdo.org/sopt','515'), ('https://nahdo.org/sopt','516'), ('https://nahdo.org/sopt','517'), ('https://nahdo.org/sopt','519'), ('https://nahdo.org/sopt','52'), ('https://nahdo.org/sopt','521'), ('https://nahdo.org/sopt','522'), ('https://nahdo.org/sopt','523'), ('https://nahdo.org/sopt','524'), ('https://nahdo.org/sopt','529'), ('https://nahdo.org/sopt','53'), ('https://nahdo.org/sopt','54'), ('https://nahdo.org/sopt','55'), ('https://nahdo.org/sopt','56'), ('https://nahdo.org/sopt','561'), ('https://nahdo.org/sopt','562'), ('https://nahdo.org/sopt','59'), ('https://nahdo.org/sopt','6'), ('https://nahdo.org/sopt','61'), ('https://nahdo.org/sopt','611'), ('https://nahdo.org/sopt','612'), ('https://nahdo.org/sopt','613'), ('https://nahdo.org/sopt','614'), ('https://nahdo.org/sopt','619'), ('https://nahdo.org/sopt','62'), ('https://nahdo.org/sopt','621'), ('https://nahdo.org/sopt','622'), ('https://nahdo.org/sopt','623'), ('https://nahdo.org/sopt','629'), ('https://nahdo.org/sopt','7'), ('https://nahdo.org/sopt','71'), ('https://nahdo.org/sopt','72'), ('https://nahdo.org/sopt','73'), ('https://nahdo.org/sopt','79'), ('https://nahdo.org/sopt','8'), ('https://nahdo.org/sopt','81'), ('https://nahdo.org/sopt','82'), ('https://nahdo.org/sopt','821'), ('https://nahdo.org/sopt','822'), ('https://nahdo.org/sopt','823'), ('https://nahdo.org/sopt','83'), ('https://nahdo.org/sopt','84'), ('https://nahdo.org/sopt','85'), ('https://nahdo.org/sopt','89'), ('https://nahdo.org/sopt','9'), ('https://nahdo.org/sopt','91'), ('https://nahdo.org/sopt','92'), ('https://nahdo.org/sopt','93'), ('https://nahdo.org/sopt','94'), ('https://nahdo.org/sopt','95'), ('https://nahdo.org/sopt','951'), ('https://nahdo.org/sopt','953'), ('https://nahdo.org/sopt','954'), ('https://nahdo.org/sopt','959'), ('https://nahdo.org/sopt','96'), ('https://nahdo.org/sopt','97'), ('https://nahdo.org/sopt','98'), ('https://nahdo.org/sopt','99'), ('https://nahdo.org/sopt','9999')),
_patients AS
    (SELECT DISTINCT patient_ref AS patient_id
     FROM resources
     WHERE patient_ref IS NOT NULL),
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
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_3 ON _vs_3._vs_code = json_extract_string(_c, '$.code') AND (_vs_3._vs_system = '' OR _vs_3._vs_system = json_extract_string(_c, '$.system')))),
     "Procedure: Fluoride Varnish Application for Children" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Procedure'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_2 ON _vs_2._vs_code = json_extract_string(_c, '$.code') AND (_vs_2._vs_system = '' OR _vs_2._vs_system = json_extract_string(_c, '$.system')))
         AND (fhirpath_text(r.resource, 'status') IS NULL
              OR fhirpath_text(r.resource, 'status') != 'not-done')
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Coverage: Payer Type" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Coverage'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_6 ON _vs_6._vs_code = json_extract_string(_c, '$.code') AND (_vs_6._vs_system = '' OR _vs_6._vs_system = json_extract_string(_c, '$.system')))),
     "Observation: Hospice care [Minimum Data Set]" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Observation'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'), from_json(json_extract(r.resource::JSON, '$.code[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://loinc.org' AND json_extract_string(c, '$.code') = '45755-6')),
     "Encounter: Encounter Inpatient" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_5 ON _vs_5._vs_code = json_extract_string(_c, '$.code') AND (_vs_5._vs_system = '' OR _vs_5._vs_system = json_extract_string(_c, '$.system')))),
     "Procedure: Hospice Care Ambulatory" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Procedure'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_4 ON _vs_4._vs_code = json_extract_string(_c, '$.code') AND (_vs_4._vs_system = '' OR _vs_4._vs_system = json_extract_string(_c, '$.system')))
         AND (fhirpath_text(r.resource, 'status') IS NULL
              OR fhirpath_text(r.resource, 'status') != 'not-done')
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Condition: Hospice Diagnosis (qicore-condition-problems-health-concerns)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_1 ON _vs_1._vs_code = json_extract_string(_c, '$.code') AND (_vs_1._vs_system = '' OR _vs_1._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Hospice Encounter" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_0 ON _vs_0._vs_code = json_extract_string(_c, '$.code') AND (_vs_0._vs_system = '' OR _vs_0._vs_system = json_extract_string(_c, '$.system')))),
     "Condition: Hospice Diagnosis (qicore-condition-encounter-diagnosis)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_1 ON _vs_1._vs_code = json_extract_string(_c, '$.code') AND (_vs_1._vs_system = '' OR _vs_1._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "ServiceRequest: Hospice Care Ambulatory" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'ServiceRequest'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_4 ON _vs_4._vs_code = json_extract_string(_c, '$.code') AND (_vs_4._vs_system = '' OR _vs_4._vs_system = json_extract_string(_c, '$.system')))
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
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
                  AND (EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(InpatientEncounter.resource::JSON, '$.hospitalization.dischargeDisposition.coding'), '["JSON"]'), from_json(json_extract(InpatientEncounter.resource::JSON, '$.hospitalization[0].dischargeDisposition.coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://snomed.info/sct' AND json_extract_string(c, '$.code') = '428361000124107')
                       OR EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(InpatientEncounter.resource::JSON, '$.hospitalization.dischargeDisposition.coding'), '["JSON"]'), from_json(json_extract(InpatientEncounter.resource::JSON, '$.hospitalization[0].dischargeDisposition.coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://snomed.info/sct' AND json_extract_string(c, '$.code') = '428371000124100'))
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
                  AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(HospiceAssessment.resource::JSON, '$.valueCodeableConcept.coding'), '["JSON"]'), from_json(json_extract(HospiceAssessment.resource::JSON, '$.value.coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://snomed.info/sct' AND json_extract_string(c, '$.code') = '373066001')
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
                                                                                                                                                                                                                                                                                WHEN EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(HospiceCareDiagnosis.resource::JSON, '$.clinicalStatus.coding'), '["JSON"]'), from_json(json_extract(HospiceCareDiagnosis.resource::JSON, '$.clinicalStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE (json_extract_string(c, '$.code') = 'active' OR json_extract_string(c, '$.code') = 'recurrence' OR json_extract_string(c, '$.code') = 'relapse')) THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                                ELSE intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                            END
                                             ELSE NULL
                                         END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
                  AND COALESCE(CAST(intervalEnd(CASE
                                                    WHEN fhirpath_text(HospiceCareDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), fhirpath_text(HospiceCareDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                                    WHEN COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                                       WHEN EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(HospiceCareDiagnosis.resource::JSON, '$.clinicalStatus.coding'), '["JSON"]'), from_json(json_extract(HospiceCareDiagnosis.resource::JSON, '$.clinicalStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE (json_extract_string(c, '$.code') = 'active' OR json_extract_string(c, '$.code') = 'recurrence' OR json_extract_string(c, '$.code') = 'relapse')) THEN intervalFromBounds(COALESCE(fhirpath_text(HospiceCareDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HospiceCareDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HospiceCareDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
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
                                                   LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity'').extension.where(url=''ombCategory'').valueCoding.code'), '["VARCHAR"]'), _lt_E -> to_json(struct_pack(codes := jsonConcat([fhirpath_text(_lt_E, 'ombCategory')], fhirpath_text(_lt_E, 'detailed')), display := fhirpath_text(_lt_E, 'text')))) AS RESOURCE
     FROM _patients AS p),
     "SDE.SDE Payer" AS
    (SELECT _inner.patient_id,
            _inner._resource_data AS RESOURCE
     FROM
         (SELECT patient_id,
                 to_json(struct_pack(code := fhirpath_text(Payer.resource, 'type'), period := fhirpath_text(Payer.resource, 'period'))) AS _resource_data
          FROM "Coverage: Payer Type" AS Payer) AS _inner),
     "SDE.SDE Race" AS
    (SELECT p.patient_id,
            list_transform(from_json(fhirpath(
                                                  (SELECT _pd.resource
                                                   FROM _patient_demographics AS _pd
                                                   WHERE _pd.patient_id = p.patient_id
                                                   LIMIT 1), 'extension.where(url=''http://hl7.org/fhir/us/core/StructureDefinition/us-core-race'').extension.where(url=''ombCategory'').valueCoding.code'), '["VARCHAR"]'), _lt_R -> to_json(struct_pack(codes := jsonConcat(fhirpath_text(_lt_R, 'ombCategory'), fhirpath_text(_lt_R, 'detailed')), display := fhirpath_text(_lt_R, 'text')))) AS RESOURCE
     FROM _patients AS p),
     "SDE.SDE Sex" AS
    (SELECT p.patient_id,

         (SELECT CASE
                     WHEN (SELECT json_extract_string(e, '$.valueCode') FROM (SELECT unnest(COALESCE(from_json(json_extract((SELECT _pd.resource
                                             FROM _patient_demographics AS _pd
                                             WHERE _pd.patient_id = p.patient_id
                                             LIMIT 1)::JSON, '$.extension'), '["JSON"]'), CAST([] AS JSON[]))) AS e) _ext_t WHERE json_extract_string(e, '$.url') = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex' LIMIT 1) = '248153007' THEN 'http://snomed.info/sct|248153007'
                     WHEN (SELECT json_extract_string(e, '$.valueCode') FROM (SELECT unnest(COALESCE(from_json(json_extract((SELECT _pd.resource
                                             FROM _patient_demographics AS _pd
                                             WHERE _pd.patient_id = p.patient_id
                                             LIMIT 1)::JSON, '$.extension'), '["JSON"]'), CAST([] AS JSON[]))) AS e) _ext_t WHERE json_extract_string(e, '$.url') = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex' LIMIT 1) = '248152002' THEN 'http://snomed.info/sct|248152002'
                     ELSE NULL
                 END) AS value
     FROM _patients AS p),
     "Denominator Exclusions" AS
    (SELECT *
     FROM "Hospice.Has Hospice Services"),
     "Numerator" AS
    (SELECT p.patient_id
     FROM _patients AS p
     WHERE
             (SELECT COUNT(_val)
              FROM
                  (SELECT DISTINCT intervalEnd(CASE
                                                   WHEN fhirpath_text(FluorideApplication.resource, 'performed') IS NULL THEN NULL
                                                   WHEN starts_with(LTRIM(fhirpath_text(FluorideApplication.resource, 'performed')), '{') THEN fhirpath_text(FluorideApplication.resource, 'performed')
                                                   ELSE intervalFromBounds(fhirpath_text(FluorideApplication.resource, 'performed'), fhirpath_text(FluorideApplication.resource, 'performed'), TRUE, TRUE)
                                               END) AS _val
                   FROM
                       (SELECT patient_id,
                               RESOURCE
                        FROM "Procedure: Fluoride Varnish Application for Children"
                        WHERE fhirpath_text(RESOURCE, 'status') IN ('completed')) AS FluorideApplication
                   WHERE CAST(intervalEnd(CASE
                                              WHEN fhirpath_text(FluorideApplication.resource, 'performed') IS NULL THEN NULL
                                              WHEN starts_with(LTRIM(fhirpath_text(FluorideApplication.resource, 'performed')), '{') THEN fhirpath_text(FluorideApplication.resource, 'performed')
                                              ELSE intervalFromBounds(fhirpath_text(FluorideApplication.resource, 'performed'), fhirpath_text(FluorideApplication.resource, 'performed'), TRUE, TRUE)
                                          END) AS DATE) BETWEEN CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE) AND COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST(intervalStart(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE))
                       AND FluorideApplication.patient_id = p.patient_id) AS _agg) >= 2),
     "Qualifying Encounters" AS
    (SELECT *
     FROM
         (SELECT patient_id,
                 RESOURCE
          FROM "Encounter: Clinical Oral Evaluation"
          WHERE fhirpath_text(RESOURCE, 'status') IN ('finished')) AS ValidEncounter
     WHERE CAST(intervalStart(fhirpath_text(ValidEncounter.resource, 'period')) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
         AND CAST(intervalEnd(fhirpath_text(ValidEncounter.resource, 'period')) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)),
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
     FROM "SDE.SDE Sex"),
     "Stratification 1" AS
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
                                                                                                 END BETWEEN 1 AND 5),
     "Stratification 2" AS
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
                                                                                                 END BETWEEN 6 AND 12),
     "Stratification 3" AS
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
                                                                                                 END BETWEEN 13 AND 20)
SELECT p.patient_id,

    "Initial Population".patient_id IS NOT NULL AS "Initial Population",

    "Denominator".patient_id IS NOT NULL AND "Initial Population".patient_id IS NOT NULL AS Denominator,

    "Denominator Exclusions".patient_id IS NOT NULL AS "Denominator Exclusions",

    "Numerator".patient_id IS NOT NULL AND "Initial Population".patient_id IS NOT NULL AND "Denominator Exclusions".patient_id IS NULL AS Numerator
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Denominator Exclusions" ON p.patient_id = "Denominator Exclusions".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id ASC
