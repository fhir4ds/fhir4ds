-- Generated SQL for measure

WITH _vs_0(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','183919006'), ('http://snomed.info/sct','183920000'), ('http://snomed.info/sct','183921001'), ('http://snomed.info/sct','305336008'), ('http://snomed.info/sct','305911006'), ('http://snomed.info/sct','385765002'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9473'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9474'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9475'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9476'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9477'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9478'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9479'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5003'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5004'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5005'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5006'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5007'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5008'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','Q5010'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','S9126'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2042'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2043'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2044'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2045'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','T2046')),
_vs_1(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','185349003'), ('http://snomed.info/sct','185463005'), ('http://snomed.info/sct','185464004'), ('http://snomed.info/sct','185465003'), ('http://snomed.info/sct','3391000175108'), ('http://snomed.info/sct','439740005'), ('http://www.ama-assn.org/go/cpt','99202'), ('http://www.ama-assn.org/go/cpt','99203'), ('http://www.ama-assn.org/go/cpt','99204'), ('http://www.ama-assn.org/go/cpt','99205'), ('http://www.ama-assn.org/go/cpt','99212'), ('http://www.ama-assn.org/go/cpt','99213'), ('http://www.ama-assn.org/go/cpt','99214'), ('http://www.ama-assn.org/go/cpt','99215')),
_vs_2(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','185460008'), ('http://snomed.info/sct','185462000'), ('http://snomed.info/sct','185466002'), ('http://snomed.info/sct','185467006'), ('http://snomed.info/sct','185468001'), ('http://snomed.info/sct','185470005'), ('http://snomed.info/sct','225929007'), ('http://snomed.info/sct','315205008'), ('http://snomed.info/sct','439708006'), ('http://snomed.info/sct','698704008'), ('http://snomed.info/sct','704126008'), ('http://www.ama-assn.org/go/cpt','99341'), ('http://www.ama-assn.org/go/cpt','99342'), ('http://www.ama-assn.org/go/cpt','99344'), ('http://www.ama-assn.org/go/cpt','99345'), ('http://www.ama-assn.org/go/cpt','99347'), ('http://www.ama-assn.org/go/cpt','99348'), ('http://www.ama-assn.org/go/cpt','99349'), ('http://www.ama-assn.org/go/cpt','99350')),
_vs_3(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','99385'), ('http://www.ama-assn.org/go/cpt','99386'), ('http://www.ama-assn.org/go/cpt','99387')),
_vs_4(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','99395'), ('http://www.ama-assn.org/go/cpt','99396'), ('http://www.ama-assn.org/go/cpt','99397')),
_vs_5(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','98966'), ('http://www.ama-assn.org/go/cpt','98967'), ('http://www.ama-assn.org/go/cpt','98968'), ('http://www.ama-assn.org/go/cpt','99441'), ('http://www.ama-assn.org/go/cpt','99442'), ('http://www.ama-assn.org/go/cpt','99443'), ('http://snomed.info/sct','185317003'), ('http://snomed.info/sct','314849005'), ('http://snomed.info/sct','386472008'), ('http://snomed.info/sct','386473003'), ('http://snomed.info/sct','401267002')),
_vs_6(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','98970'), ('http://www.ama-assn.org/go/cpt','98971'), ('http://www.ama-assn.org/go/cpt','98972'), ('http://www.ama-assn.org/go/cpt','98980'), ('http://www.ama-assn.org/go/cpt','98981'), ('http://www.ama-assn.org/go/cpt','99421'), ('http://www.ama-assn.org/go/cpt','99422'), ('http://www.ama-assn.org/go/cpt','99423'), ('http://www.ama-assn.org/go/cpt','99457'), ('http://www.ama-assn.org/go/cpt','99458'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G0071'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G2010'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G2012'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G2250'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G2251'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G2252')),
_vs_7(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','305284002'), ('http://snomed.info/sct','305381007'), ('http://snomed.info/sct','305686008'), ('http://snomed.info/sct','305824005'), ('http://snomed.info/sct','441874000'), ('http://snomed.info/sct','4901000124101'), ('http://snomed.info/sct','713281006'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G9054')),
_vs_8(_vs_system, _vs_code) AS (VALUES ('http://loinc.org','10524-7'), ('http://loinc.org','18500-9'), ('http://loinc.org','19762-4'), ('http://loinc.org','19764-0'), ('http://loinc.org','19765-7'), ('http://loinc.org','19766-5'), ('http://loinc.org','19774-9'), ('http://loinc.org','33717-0'), ('http://loinc.org','47527-7'), ('http://loinc.org','47528-5')),
_vs_9(_vs_system, _vs_code) AS (VALUES ('http://loinc.org','21440-3'), ('http://loinc.org','30167-1'), ('http://loinc.org','38372-9'), ('http://loinc.org','59263-4'), ('http://loinc.org','59264-2'), ('http://loinc.org','59420-0'), ('http://loinc.org','69002-4'), ('http://loinc.org','71431-1'), ('http://loinc.org','75694-0'), ('http://loinc.org','77379-6'), ('http://loinc.org','77399-4'), ('http://loinc.org','77400-0'), ('http://loinc.org','82354-2'), ('http://loinc.org','82456-5'), ('http://loinc.org','82675-0'), ('http://loinc.org','95539-3')),
_vs_10(_vs_system, _vs_code) AS (VALUES ('http://hl7.org/fhir/sid/icd-10-cm','Q51.5'), ('http://hl7.org/fhir/sid/icd-10-cm','Z90.710'), ('http://hl7.org/fhir/sid/icd-10-cm','Z90.712'), ('http://snomed.info/sct','10738891000119107'), ('http://snomed.info/sct','248911005'), ('http://snomed.info/sct','37687000'), ('http://snomed.info/sct','428078001'), ('http://snomed.info/sct','429290001'), ('http://snomed.info/sct','429763009'), ('http://snomed.info/sct','473171009'), ('http://snomed.info/sct','723171001')),
_vs_11(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','170935008'), ('http://snomed.info/sct','170936009'), ('http://snomed.info/sct','305911006')),
_vs_12(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','305686008'), ('http://snomed.info/sct','305824005'), ('http://snomed.info/sct','441874000'), ('http://hl7.org/fhir/sid/icd-10-cm','Z51.5')),
_vs_13(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','58293'), ('http://www.ama-assn.org/go/cpt','59135'), ('http://www.ama-assn.org/go/cpt','57530'), ('http://www.ama-assn.org/go/cpt','57531'), ('http://www.ama-assn.org/go/cpt','57540'), ('http://www.ama-assn.org/go/cpt','57545'), ('http://www.ama-assn.org/go/cpt','57550'), ('http://www.ama-assn.org/go/cpt','57555'), ('http://www.ama-assn.org/go/cpt','57556'), ('http://www.ama-assn.org/go/cpt','58150'), ('http://www.ama-assn.org/go/cpt','58152'), ('http://www.ama-assn.org/go/cpt','58200'), ('http://www.ama-assn.org/go/cpt','58210'), ('http://www.ama-assn.org/go/cpt','58240'), ('http://www.ama-assn.org/go/cpt','58260'), ('http://www.ama-assn.org/go/cpt','58262'), ('http://www.ama-assn.org/go/cpt','58263'), ('http://www.ama-assn.org/go/cpt','58267'), ('http://www.ama-assn.org/go/cpt','58270'), ('http://www.ama-assn.org/go/cpt','58275'), ('http://www.ama-assn.org/go/cpt','58280'), ('http://www.ama-assn.org/go/cpt','58285'), ('http://www.ama-assn.org/go/cpt','58290'), ('http://www.ama-assn.org/go/cpt','58291'), ('http://www.ama-assn.org/go/cpt','58292'), ('http://www.ama-assn.org/go/cpt','58294'), ('http://www.ama-assn.org/go/cpt','58548'), ('http://www.ama-assn.org/go/cpt','58550'), ('http://www.ama-assn.org/go/cpt','58552'), ('http://www.ama-assn.org/go/cpt','58553'), ('http://www.ama-assn.org/go/cpt','58554'), ('http://www.ama-assn.org/go/cpt','58570'), ('http://www.ama-assn.org/go/cpt','58571'), ('http://www.ama-assn.org/go/cpt','58572'), ('http://www.ama-assn.org/go/cpt','58573'), ('http://www.ama-assn.org/go/cpt','58575'), ('http://www.ama-assn.org/go/cpt','58951'), ('http://www.ama-assn.org/go/cpt','58953'), ('http://www.ama-assn.org/go/cpt','58954'), ('http://www.ama-assn.org/go/cpt','58956'), ('http://www.cms.gov/Medicare/Coding/ICD10','0UTC0ZZ'), ('http://www.cms.gov/Medicare/Coding/ICD10','0UTC4ZZ'), ('http://www.cms.gov/Medicare/Coding/ICD10','0UTC7ZZ'), ('http://www.cms.gov/Medicare/Coding/ICD10','0UTC8ZZ'), ('http://snomed.info/sct','116140006'), ('http://snomed.info/sct','116142003'), ('http://snomed.info/sct','116143008'), ('http://snomed.info/sct','116144002'), ('http://snomed.info/sct','1163275000'), ('http://snomed.info/sct','176697007'), ('http://snomed.info/sct','236888001'), ('http://snomed.info/sct','236891001'), ('http://snomed.info/sct','24293001'), ('http://snomed.info/sct','287924009'), ('http://snomed.info/sct','307771009'), ('http://snomed.info/sct','35955002'), ('http://snomed.info/sct','361222003'), ('http://snomed.info/sct','361223008'), ('http://snomed.info/sct','387626007'), ('http://snomed.info/sct','414575003'), ('http://snomed.info/sct','41566006'), ('http://snomed.info/sct','440383008'), ('http://snomed.info/sct','446446002'), ('http://snomed.info/sct','446679008'), ('http://snomed.info/sct','46226009'), ('http://snomed.info/sct','708877008'), ('http://snomed.info/sct','708878003'), ('http://snomed.info/sct','739671004'), ('http://snomed.info/sct','739672006'), ('http://snomed.info/sct','739673001'), ('http://snomed.info/sct','739674007'), ('http://snomed.info/sct','740514001'), ('http://snomed.info/sct','740515000'), ('http://snomed.info/sct','767610009'), ('http://snomed.info/sct','767611008'), ('http://snomed.info/sct','767612001'), ('http://snomed.info/sct','82418001'), ('http://snomed.info/sct','86477000'), ('http://snomed.info/sct','88144003')),
_vs_14(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','103735009'), ('http://snomed.info/sct','105402000'), ('http://snomed.info/sct','1841000124106'), ('http://snomed.info/sct','395669003'), ('http://snomed.info/sct','395670002'), ('http://snomed.info/sct','395694002'), ('http://snomed.info/sct','395695001'), ('http://snomed.info/sct','433181000124107'), ('http://snomed.info/sct','443761007')),
_vs_15(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','170935008'), ('http://snomed.info/sct','170936009'), ('http://snomed.info/sct','385763009'), ('http://www.ama-assn.org/go/cpt','99377'), ('http://www.ama-assn.org/go/cpt','99378'), ('http://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets','G0182')),
_vs_16(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','183452005'), ('http://snomed.info/sct','32485007'), ('http://snomed.info/sct','8715000')),
_vs_17(_vs_system, _vs_code) AS (VALUES ('https://nahdo.org/sopt','1'), ('https://nahdo.org/sopt','11'), ('https://nahdo.org/sopt','111'), ('https://nahdo.org/sopt','1111'), ('https://nahdo.org/sopt','1112'), ('https://nahdo.org/sopt','112'), ('https://nahdo.org/sopt','113'), ('https://nahdo.org/sopt','119'), ('https://nahdo.org/sopt','12'), ('https://nahdo.org/sopt','121'), ('https://nahdo.org/sopt','122'), ('https://nahdo.org/sopt','123'), ('https://nahdo.org/sopt','129'), ('https://nahdo.org/sopt','13'), ('https://nahdo.org/sopt','14'), ('https://nahdo.org/sopt','141'), ('https://nahdo.org/sopt','142'), ('https://nahdo.org/sopt','19'), ('https://nahdo.org/sopt','191'), ('https://nahdo.org/sopt','2'), ('https://nahdo.org/sopt','21'), ('https://nahdo.org/sopt','211'), ('https://nahdo.org/sopt','212'), ('https://nahdo.org/sopt','213'), ('https://nahdo.org/sopt','219'), ('https://nahdo.org/sopt','22'), ('https://nahdo.org/sopt','23'), ('https://nahdo.org/sopt','25'), ('https://nahdo.org/sopt','26'), ('https://nahdo.org/sopt','29'), ('https://nahdo.org/sopt','291'), ('https://nahdo.org/sopt','299'), ('https://nahdo.org/sopt','3'), ('https://nahdo.org/sopt','31'), ('https://nahdo.org/sopt','311'), ('https://nahdo.org/sopt','3111'), ('https://nahdo.org/sopt','3112'), ('https://nahdo.org/sopt','3113'), ('https://nahdo.org/sopt','3114'), ('https://nahdo.org/sopt','3115'), ('https://nahdo.org/sopt','3116'), ('https://nahdo.org/sopt','3119'), ('https://nahdo.org/sopt','312'), ('https://nahdo.org/sopt','3121'), ('https://nahdo.org/sopt','3122'), ('https://nahdo.org/sopt','3123'), ('https://nahdo.org/sopt','313'), ('https://nahdo.org/sopt','32'), ('https://nahdo.org/sopt','321'), ('https://nahdo.org/sopt','3211'), ('https://nahdo.org/sopt','3212'), ('https://nahdo.org/sopt','32121'), ('https://nahdo.org/sopt','32122'), ('https://nahdo.org/sopt','32123'), ('https://nahdo.org/sopt','32124'), ('https://nahdo.org/sopt','32125'), ('https://nahdo.org/sopt','32126'), ('https://nahdo.org/sopt','32127'), ('https://nahdo.org/sopt','32128'), ('https://nahdo.org/sopt','322'), ('https://nahdo.org/sopt','3221'), ('https://nahdo.org/sopt','3222'), ('https://nahdo.org/sopt','3223'), ('https://nahdo.org/sopt','3229'), ('https://nahdo.org/sopt','33'), ('https://nahdo.org/sopt','331'), ('https://nahdo.org/sopt','332'), ('https://nahdo.org/sopt','333'), ('https://nahdo.org/sopt','334'), ('https://nahdo.org/sopt','34'), ('https://nahdo.org/sopt','341'), ('https://nahdo.org/sopt','342'), ('https://nahdo.org/sopt','343'), ('https://nahdo.org/sopt','344'), ('https://nahdo.org/sopt','349'), ('https://nahdo.org/sopt','35'), ('https://nahdo.org/sopt','36'), ('https://nahdo.org/sopt','361'), ('https://nahdo.org/sopt','362'), ('https://nahdo.org/sopt','369'), ('https://nahdo.org/sopt','37'), ('https://nahdo.org/sopt','371'), ('https://nahdo.org/sopt','3711'), ('https://nahdo.org/sopt','3712'), ('https://nahdo.org/sopt','3713'), ('https://nahdo.org/sopt','372'), ('https://nahdo.org/sopt','379'), ('https://nahdo.org/sopt','38'), ('https://nahdo.org/sopt','381'), ('https://nahdo.org/sopt','3811'), ('https://nahdo.org/sopt','3812'), ('https://nahdo.org/sopt','3813'), ('https://nahdo.org/sopt','3819'), ('https://nahdo.org/sopt','382'), ('https://nahdo.org/sopt','389'), ('https://nahdo.org/sopt','39'), ('https://nahdo.org/sopt','391'), ('https://nahdo.org/sopt','4'), ('https://nahdo.org/sopt','41'), ('https://nahdo.org/sopt','42'), ('https://nahdo.org/sopt','43'), ('https://nahdo.org/sopt','44'), ('https://nahdo.org/sopt','5'), ('https://nahdo.org/sopt','51'), ('https://nahdo.org/sopt','511'), ('https://nahdo.org/sopt','512'), ('https://nahdo.org/sopt','513'), ('https://nahdo.org/sopt','514'), ('https://nahdo.org/sopt','515'), ('https://nahdo.org/sopt','516'), ('https://nahdo.org/sopt','517'), ('https://nahdo.org/sopt','519'), ('https://nahdo.org/sopt','52'), ('https://nahdo.org/sopt','521'), ('https://nahdo.org/sopt','522'), ('https://nahdo.org/sopt','523'), ('https://nahdo.org/sopt','524'), ('https://nahdo.org/sopt','529'), ('https://nahdo.org/sopt','53'), ('https://nahdo.org/sopt','54'), ('https://nahdo.org/sopt','55'), ('https://nahdo.org/sopt','56'), ('https://nahdo.org/sopt','561'), ('https://nahdo.org/sopt','562'), ('https://nahdo.org/sopt','59'), ('https://nahdo.org/sopt','6'), ('https://nahdo.org/sopt','61'), ('https://nahdo.org/sopt','611'), ('https://nahdo.org/sopt','612'), ('https://nahdo.org/sopt','613'), ('https://nahdo.org/sopt','614'), ('https://nahdo.org/sopt','619'), ('https://nahdo.org/sopt','62'), ('https://nahdo.org/sopt','621'), ('https://nahdo.org/sopt','622'), ('https://nahdo.org/sopt','623'), ('https://nahdo.org/sopt','629'), ('https://nahdo.org/sopt','7'), ('https://nahdo.org/sopt','71'), ('https://nahdo.org/sopt','72'), ('https://nahdo.org/sopt','73'), ('https://nahdo.org/sopt','79'), ('https://nahdo.org/sopt','8'), ('https://nahdo.org/sopt','81'), ('https://nahdo.org/sopt','82'), ('https://nahdo.org/sopt','821'), ('https://nahdo.org/sopt','822'), ('https://nahdo.org/sopt','823'), ('https://nahdo.org/sopt','83'), ('https://nahdo.org/sopt','84'), ('https://nahdo.org/sopt','85'), ('https://nahdo.org/sopt','89'), ('https://nahdo.org/sopt','9'), ('https://nahdo.org/sopt','91'), ('https://nahdo.org/sopt','92'), ('https://nahdo.org/sopt','93'), ('https://nahdo.org/sopt','94'), ('https://nahdo.org/sopt','95'), ('https://nahdo.org/sopt','951'), ('https://nahdo.org/sopt','953'), ('https://nahdo.org/sopt','954'), ('https://nahdo.org/sopt','959'), ('https://nahdo.org/sopt','96'), ('https://nahdo.org/sopt','97'), ('https://nahdo.org/sopt','98'), ('https://nahdo.org/sopt','99'), ('https://nahdo.org/sopt','9999')),
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
     "Encounter: Preventive Care Services Established Office Visit, 18 and Up" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_4 ON _vs_4._vs_code = json_extract_string(_c, '$.code') AND (_vs_4._vs_system = '' OR _vs_4._vs_system = json_extract_string(_c, '$.system')))),
     "Encounter: Preventive Care Services Initial Office Visit, 18 and Up" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_3 ON _vs_3._vs_code = json_extract_string(_c, '$.code') AND (_vs_3._vs_system = '' OR _vs_3._vs_system = json_extract_string(_c, '$.system')))),
     "Condition: Congenital or Acquired Absence of Cervix (qicore-condition-problems-health-concerns)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_date(r.resource, 'abatementDateTime') AS abatement_date,
                     fhirpath_date(r.resource, 'onsetDateTime') AS onset_date,
                     fhirpath_date(r.resource, 'recordedDate') AS recorded_date,
                     fhirpath_text(r.resource, 'verificationStatus') AS verification_status
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_10 ON _vs_10._vs_code = json_extract_string(_c, '$.code') AND (_vs_10._vs_system = '' OR _vs_10._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Condition: Congenital or Acquired Absence of Cervix (qicore-condition-encounter-diagnosis)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_date(r.resource, 'abatementDateTime') AS abatement_date,
                     fhirpath_date(r.resource, 'onsetDateTime') AS onset_date,
                     fhirpath_date(r.resource, 'recordedDate') AS recorded_date,
                     fhirpath_text(r.resource, 'verificationStatus') AS verification_status
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_10 ON _vs_10._vs_code = json_extract_string(_c, '$.code') AND (_vs_10._vs_system = '' OR _vs_10._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Encounter: Home Healthcare Services" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_2 ON _vs_2._vs_code = json_extract_string(_c, '$.code') AND (_vs_2._vs_system = '' OR _vs_2._vs_system = json_extract_string(_c, '$.system')))),
     "Procedure: Hysterectomy with No Residual Cervix" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Procedure'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_13 ON _vs_13._vs_code = json_extract_string(_c, '$.code') AND (_vs_13._vs_system = '' OR _vs_13._vs_system = json_extract_string(_c, '$.system')))
         AND (fhirpath_text(r.resource, 'status') IS NULL
              OR fhirpath_text(r.resource, 'status') != 'not-done')
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Encounter: Office Visit" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_1 ON _vs_1._vs_code = json_extract_string(_c, '$.code') AND (_vs_1._vs_system = '' OR _vs_1._vs_system = json_extract_string(_c, '$.system')))),
     "Observation: Pap Test" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_date(r.resource, 'effectiveDateTime') AS effective_date,
                     fhirpath_text(r.resource, 'status') AS status,
                     fhirpath_text(r.resource, 'value') AS value
     FROM resources r
     WHERE r.resourceType = 'Observation'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_8 ON _vs_8._vs_code = json_extract_string(_c, '$.code') AND (_vs_8._vs_system = '' OR _vs_8._vs_system = json_extract_string(_c, '$.system')))),
     "Observation: HPV Test" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_date(r.resource, 'effectiveDateTime') AS effective_date,
                     fhirpath_text(r.resource, 'status') AS status,
                     fhirpath_text(r.resource, 'value') AS value
     FROM resources r
     WHERE r.resourceType = 'Observation'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_9 ON _vs_9._vs_code = json_extract_string(_c, '$.code') AND (_vs_9._vs_system = '' OR _vs_9._vs_system = json_extract_string(_c, '$.system')))),
     "Encounter: Virtual Encounter" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_6 ON _vs_6._vs_code = json_extract_string(_c, '$.code') AND (_vs_6._vs_system = '' OR _vs_6._vs_system = json_extract_string(_c, '$.system')))),
     "Encounter: Telephone Visits" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_5 ON _vs_5._vs_code = json_extract_string(_c, '$.code') AND (_vs_5._vs_system = '' OR _vs_5._vs_system = json_extract_string(_c, '$.system')))),
     "Coverage: Payer Type" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Coverage'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_17 ON _vs_17._vs_code = json_extract_string(_c, '$.code') AND (_vs_17._vs_system = '' OR _vs_17._vs_system = json_extract_string(_c, '$.system')))),
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
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_16 ON _vs_16._vs_code = json_extract_string(_c, '$.code') AND (_vs_16._vs_system = '' OR _vs_16._vs_system = json_extract_string(_c, '$.system')))),
     "Procedure: Hospice Care Ambulatory" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Procedure'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_15 ON _vs_15._vs_code = json_extract_string(_c, '$.code') AND (_vs_15._vs_system = '' OR _vs_15._vs_system = json_extract_string(_c, '$.system')))
         AND (fhirpath_text(r.resource, 'status') IS NULL
              OR fhirpath_text(r.resource, 'status') != 'not-done')
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Condition: Hospice Diagnosis (qicore-condition-problems-health-concerns)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_11 ON _vs_11._vs_code = json_extract_string(_c, '$.code') AND (_vs_11._vs_system = '' OR _vs_11._vs_system = json_extract_string(_c, '$.system')))
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
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_11 ON _vs_11._vs_code = json_extract_string(_c, '$.code') AND (_vs_11._vs_system = '' OR _vs_11._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "ServiceRequest: Hospice Care Ambulatory" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'ServiceRequest'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_15 ON _vs_15._vs_code = json_extract_string(_c, '$.code') AND (_vs_15._vs_system = '' OR _vs_15._vs_system = json_extract_string(_c, '$.system')))
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-servicenotrequested'))),
     "Procedure: Palliative Care Intervention" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Procedure'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_14 ON _vs_14._vs_code = json_extract_string(_c, '$.code') AND (_vs_14._vs_system = '' OR _vs_14._vs_system = json_extract_string(_c, '$.system')))
         AND (fhirpath_text(r.resource, 'status') IS NULL
              OR fhirpath_text(r.resource, 'status') != 'not-done')
         AND (json_extract(r.resource, '$.meta.profile') IS NULL
              OR NOT list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-procedurenotdone'))),
     "Observation: Functional Assessment of Chronic Illness Therapy - Palliative Care Questionnaire (FACIT-Pal)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Observation'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'), from_json(json_extract(r.resource::JSON, '$.code[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://loinc.org' AND json_extract_string(c, '$.code') = '71007-9')),
     "Encounter: Palliative Care Encounter" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_7 ON _vs_7._vs_code = json_extract_string(_c, '$.code') AND (_vs_7._vs_system = '' OR _vs_7._vs_system = json_extract_string(_c, '$.system')))),
     "Condition: Palliative Care Diagnosis (qicore-condition-problems-health-concerns)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_12 ON _vs_12._vs_code = json_extract_string(_c, '$.code') AND (_vs_12._vs_system = '' OR _vs_12._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Condition: Palliative Care Diagnosis (qicore-condition-encounter-diagnosis)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_12 ON _vs_12._vs_code = json_extract_string(_c, '$.code') AND (_vs_12._vs_system = '' OR _vs_12._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
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
                                                                                                                                                                                                                                                                             WHEN EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(PalliativeDiagnosis.resource::JSON, '$.clinicalStatus.coding'), '["JSON"]'), from_json(json_extract(PalliativeDiagnosis.resource::JSON, '$.clinicalStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE (json_extract_string(c, '$.code') = 'active' OR json_extract_string(c, '$.code') = 'recurrence' OR json_extract_string(c, '$.code') = 'relapse')) THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                                             ELSE intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                                         END
                                             ELSE NULL
                                         END) AS DATE) <= COALESCE(CAST(intervalEnd(intervalFromBounds(CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS VARCHAR), CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS VARCHAR), TRUE, TRUE)) AS DATE), CAST('9999-12-31' AS DATE))
                  AND COALESCE(CAST(intervalEnd(CASE
                                                    WHEN fhirpath_text(PalliativeDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), fhirpath_text(PalliativeDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                                    WHEN COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                                                    WHEN EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(PalliativeDiagnosis.resource::JSON, '$.clinicalStatus.coding'), '["JSON"]'), from_json(json_extract(PalliativeDiagnosis.resource::JSON, '$.clinicalStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE (json_extract_string(c, '$.code') = 'active' OR json_extract_string(c, '$.code') = 'recurrence' OR json_extract_string(c, '$.code') = 'relapse')) THEN intervalFromBounds(COALESCE(fhirpath_text(PalliativeDiagnosis.resource, 'onsetDateTime'), fhirpath_text(PalliativeDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(PalliativeDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
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
                                                                                                                                                                                                                                                                                         WHEN EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(NoCervixDiagnosis.resource::JSON, '$.clinicalStatus.coding'), '["JSON"]'), from_json(json_extract(NoCervixDiagnosis.resource::JSON, '$.clinicalStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE (json_extract_string(c, '$.code') = 'active' OR json_extract_string(c, '$.code') = 'recurrence' OR json_extract_string(c, '$.code') = 'relapse')) THEN intervalFromBounds(COALESCE(fhirpath_text(NoCervixDiagnosis.resource, 'onsetDateTime'), fhirpath_text(NoCervixDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(NoCervixDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
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
         AND (SELECT json_extract_string(e, '$.valueCode') FROM (SELECT unnest(COALESCE(from_json(json_extract((SELECT _pd.resource
                                FROM _patient_demographics AS _pd
                                WHERE _pd.patient_id = p.patient_id
                                LIMIT 1)::JSON, '$.extension'), '["JSON"]'), CAST([] AS JSON[]))) AS e) _ext_t WHERE json_extract_string(e, '$.url') = 'http://hl7.org/fhir/us/core/StructureDefinition/us-core-sex' LIMIT 1) = '248152002'
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
