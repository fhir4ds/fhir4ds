-- Generated SQL for measure

WITH _vs_0(_vs_system, _vs_code) AS (VALUES ('http://loinc.org','10901-7'), ('http://loinc.org','10902-5'), ('http://loinc.org','11078-3'), ('http://loinc.org','11079-1'), ('http://loinc.org','11080-9'), ('http://loinc.org','11081-7'), ('http://loinc.org','11082-5'), ('http://loinc.org','12855-3'), ('http://loinc.org','12856-1'), ('http://loinc.org','12857-9'), ('http://loinc.org','12858-7'), ('http://loinc.org','12859-5'), ('http://loinc.org','12870-2'), ('http://loinc.org','12871-0'), ('http://loinc.org','12872-8'), ('http://loinc.org','12875-1'), ('http://loinc.org','12876-9'), ('http://loinc.org','12893-4'), ('http://loinc.org','12894-2'), ('http://loinc.org','12895-9'), ('http://loinc.org','13499-9'), ('http://loinc.org','13920-4'), ('http://loinc.org','14092-1'), ('http://loinc.org','14126-7'), ('http://loinc.org','16132-3'), ('http://loinc.org','16974-8'), ('http://loinc.org','16975-5'), ('http://loinc.org','16976-3'), ('http://loinc.org','16977-1'), ('http://loinc.org','16978-9'), ('http://loinc.org','16979-7'), ('http://loinc.org','18396-2'), ('http://loinc.org','19110-6'), ('http://loinc.org','21007-0'), ('http://loinc.org','21331-4'), ('http://loinc.org','21332-2'), ('http://loinc.org','21334-8'), ('http://loinc.org','21335-5'), ('http://loinc.org','21336-3'), ('http://loinc.org','21337-1'), ('http://loinc.org','21338-9'), ('http://loinc.org','21339-7'), ('http://loinc.org','21340-5'), ('http://loinc.org','22356-0'), ('http://loinc.org','22357-8'), ('http://loinc.org','22358-6'), ('http://loinc.org','24012-7'), ('http://loinc.org','28004-0'), ('http://loinc.org','28052-9'), ('http://loinc.org','29327-4'), ('http://loinc.org','29893-5'), ('http://loinc.org','30361-0'), ('http://loinc.org','31072-2'), ('http://loinc.org','31073-0'), ('http://loinc.org','31201-7'), ('http://loinc.org','31430-2'), ('http://loinc.org','32571-2'), ('http://loinc.org','32602-5'), ('http://loinc.org','32827-8'), ('http://loinc.org','32842-7'), ('http://loinc.org','33508-3'), ('http://loinc.org','33660-2'), ('http://loinc.org','33806-1'), ('http://loinc.org','33807-9'), ('http://loinc.org','33866-5'), ('http://loinc.org','34591-8'), ('http://loinc.org','34592-6'), ('http://loinc.org','35437-3'), ('http://loinc.org','35438-1'), ('http://loinc.org','35439-9'), ('http://loinc.org','35440-7'), ('http://loinc.org','35441-5'), ('http://loinc.org','35442-3'), ('http://loinc.org','35443-1'), ('http://loinc.org','35444-9'), ('http://loinc.org','35445-6'), ('http://loinc.org','35446-4'), ('http://loinc.org','35447-2'), ('http://loinc.org','35448-0'), ('http://loinc.org','35449-8'), ('http://loinc.org','35450-6'), ('http://loinc.org','35452-2'), ('http://loinc.org','35564-4'), ('http://loinc.org','35565-1'), ('http://loinc.org','40437-6'), ('http://loinc.org','40438-4'), ('http://loinc.org','40439-2'), ('http://loinc.org','40732-0'), ('http://loinc.org','40733-8'), ('http://loinc.org','41143-9'), ('http://loinc.org','41144-7'), ('http://loinc.org','41145-4'), ('http://loinc.org','41290-8'), ('http://loinc.org','42339-2'), ('http://loinc.org','42600-7'), ('http://loinc.org','42627-0'), ('http://loinc.org','42768-2'), ('http://loinc.org','43008-2'), ('http://loinc.org','43009-0'), ('http://loinc.org','43010-8'), ('http://loinc.org','43011-6'), ('http://loinc.org','43012-4'), ('http://loinc.org','43013-2'), ('http://loinc.org','43185-8'), ('http://loinc.org','43599-0'), ('http://loinc.org','44531-2'), ('http://loinc.org','44532-0'), ('http://loinc.org','44533-8'), ('http://loinc.org','44607-0'), ('http://loinc.org','44872-0'), ('http://loinc.org','44873-8'), ('http://loinc.org','45212-8'), ('http://loinc.org','47029-4'), ('http://loinc.org','48345-3'), ('http://loinc.org','48346-1'), ('http://loinc.org','49483-1'), ('http://loinc.org','49580-4'), ('http://loinc.org','49718-0'), ('http://loinc.org','49905-3'), ('http://loinc.org','49965-7'), ('http://loinc.org','51786-2'), ('http://loinc.org','5220-9'), ('http://loinc.org','5221-7'), ('http://loinc.org','5222-5'), ('http://loinc.org','5223-3'), ('http://loinc.org','5224-1'), ('http://loinc.org','5225-8'), ('http://loinc.org','53379-4'), ('http://loinc.org','53601-1'), ('http://loinc.org','54086-4'), ('http://loinc.org','56888-1'), ('http://loinc.org','57974-8'), ('http://loinc.org','57975-5'), ('http://loinc.org','57976-3'), ('http://loinc.org','57977-1'), ('http://loinc.org','57978-9'), ('http://loinc.org','58900-2'), ('http://loinc.org','62456-9'), ('http://loinc.org','68961-2'), ('http://loinc.org','69668-2'), ('http://loinc.org','73905-2'), ('http://loinc.org','73906-0'), ('http://loinc.org','75622-1'), ('http://loinc.org','75666-8'), ('http://loinc.org','77685-6'), ('http://loinc.org','7917-8'), ('http://loinc.org','7918-6'), ('http://loinc.org','7919-4'), ('http://loinc.org','80203-3'), ('http://loinc.org','80387-4'), ('http://loinc.org','81641-3'), ('http://loinc.org','83101-6'), ('http://loinc.org','85037-0'), ('http://loinc.org','85686-4'), ('http://loinc.org','86233-4'), ('http://loinc.org','86657-4'), ('http://loinc.org','89365-1'), ('http://loinc.org','89374-3'), ('http://loinc.org','9660-2'), ('http://loinc.org','9661-0'), ('http://loinc.org','9662-8'), ('http://loinc.org','9663-6'), ('http://loinc.org','9664-4'), ('http://loinc.org','9665-1'), ('http://loinc.org','9666-9'), ('http://loinc.org','9667-7'), ('http://loinc.org','9668-5'), ('http://loinc.org','9669-3'), ('http://loinc.org','9821-0')),
_vs_1(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','185349003'), ('http://snomed.info/sct','185463005'), ('http://snomed.info/sct','185464004'), ('http://snomed.info/sct','185465003'), ('http://snomed.info/sct','3391000175108'), ('http://snomed.info/sct','439740005'), ('http://www.ama-assn.org/go/cpt','99202'), ('http://www.ama-assn.org/go/cpt','99203'), ('http://www.ama-assn.org/go/cpt','99204'), ('http://www.ama-assn.org/go/cpt','99205'), ('http://www.ama-assn.org/go/cpt','99212'), ('http://www.ama-assn.org/go/cpt','99213'), ('http://www.ama-assn.org/go/cpt','99214'), ('http://www.ama-assn.org/go/cpt','99215')),
_vs_2(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','99381'), ('http://www.ama-assn.org/go/cpt','99382'), ('http://www.ama-assn.org/go/cpt','99383'), ('http://www.ama-assn.org/go/cpt','99384')),
_vs_3(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','99385'), ('http://www.ama-assn.org/go/cpt','99386'), ('http://www.ama-assn.org/go/cpt','99387')),
_vs_4(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','99391'), ('http://www.ama-assn.org/go/cpt','99392'), ('http://www.ama-assn.org/go/cpt','99393'), ('http://www.ama-assn.org/go/cpt','99394')),
_vs_5(_vs_system, _vs_code) AS (VALUES ('http://www.ama-assn.org/go/cpt','99395'), ('http://www.ama-assn.org/go/cpt','99396'), ('http://www.ama-assn.org/go/cpt','99397')),
_vs_6(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','10746341000119109'), ('http://snomed.info/sct','10755671000119100'), ('http://snomed.info/sct','111880001'), ('http://snomed.info/sct','1142045004'), ('http://snomed.info/sct','1142055000'), ('http://snomed.info/sct','1187000005'), ('http://snomed.info/sct','1187001009'), ('http://snomed.info/sct','1260096003'), ('http://snomed.info/sct','15928141000119107'), ('http://snomed.info/sct','165816005'), ('http://snomed.info/sct','186706006'), ('http://snomed.info/sct','186707002'), ('http://snomed.info/sct','186708007'), ('http://snomed.info/sct','230180003'), ('http://snomed.info/sct','230202002'), ('http://snomed.info/sct','230598008'), ('http://snomed.info/sct','235726002'), ('http://snomed.info/sct','236406007'), ('http://snomed.info/sct','240103002'), ('http://snomed.info/sct','276665006'), ('http://snomed.info/sct','276666007'), ('http://snomed.info/sct','281388009'), ('http://snomed.info/sct','315019000'), ('http://snomed.info/sct','397763006'), ('http://snomed.info/sct','398329009'), ('http://snomed.info/sct','402901009'), ('http://snomed.info/sct','405631006'), ('http://snomed.info/sct','406109008'), ('http://snomed.info/sct','40780007'), ('http://snomed.info/sct','414376003'), ('http://snomed.info/sct','414604009'), ('http://snomed.info/sct','416729007'), ('http://snomed.info/sct','420244003'), ('http://snomed.info/sct','420281004'), ('http://snomed.info/sct','420302007'), ('http://snomed.info/sct','420308006'), ('http://snomed.info/sct','420321004'), ('http://snomed.info/sct','420384005'), ('http://snomed.info/sct','420395004'), ('http://snomed.info/sct','420403001'), ('http://snomed.info/sct','420452002'), ('http://snomed.info/sct','420524008'), ('http://snomed.info/sct','420543008'), ('http://snomed.info/sct','420544002'), ('http://snomed.info/sct','420549007'), ('http://snomed.info/sct','420554003'), ('http://snomed.info/sct','420614009'), ('http://snomed.info/sct','420658009'), ('http://snomed.info/sct','420691000'), ('http://snomed.info/sct','420718004'), ('http://snomed.info/sct','420721002'), ('http://snomed.info/sct','420764009'), ('http://snomed.info/sct','420774007'), ('http://snomed.info/sct','420787001'), ('http://snomed.info/sct','420801006'), ('http://snomed.info/sct','420818005'), ('http://snomed.info/sct','420877009'), ('http://snomed.info/sct','420900006'), ('http://snomed.info/sct','420938005'), ('http://snomed.info/sct','420945005'), ('http://snomed.info/sct','421020000'), ('http://snomed.info/sct','421023003'), ('http://snomed.info/sct','421047005'), ('http://snomed.info/sct','421077004'), ('http://snomed.info/sct','421102007'), ('http://snomed.info/sct','421230000'), ('http://snomed.info/sct','421272004'), ('http://snomed.info/sct','421283008'), ('http://snomed.info/sct','421312009'), ('http://snomed.info/sct','421315006'), ('http://snomed.info/sct','421394009'), ('http://snomed.info/sct','421403008'), ('http://snomed.info/sct','421415007'), ('http://snomed.info/sct','421431004'), ('http://snomed.info/sct','421454008'), ('http://snomed.info/sct','421460008'), ('http://snomed.info/sct','421508002'), ('http://snomed.info/sct','421529006'), ('http://snomed.info/sct','421571007'), ('http://snomed.info/sct','421597001'), ('http://snomed.info/sct','421660003'), ('http://snomed.info/sct','421671002'), ('http://snomed.info/sct','421695000'), ('http://snomed.info/sct','421706001'), ('http://snomed.info/sct','421708000'), ('http://snomed.info/sct','421710003'), ('http://snomed.info/sct','421766003'), ('http://snomed.info/sct','421827003'), ('http://snomed.info/sct','421851008'), ('http://snomed.info/sct','421874007'), ('http://snomed.info/sct','421883002'), ('http://snomed.info/sct','421929001'), ('http://snomed.info/sct','421983003'), ('http://snomed.info/sct','421998001'), ('http://snomed.info/sct','422003001'), ('http://snomed.info/sct','422012004'), ('http://snomed.info/sct','422089004'), ('http://snomed.info/sct','422127002'), ('http://snomed.info/sct','422136003'), ('http://snomed.info/sct','422177004'), ('http://snomed.info/sct','422189002'), ('http://snomed.info/sct','422194002'), ('http://snomed.info/sct','422282000'), ('http://snomed.info/sct','422337001'), ('http://snomed.info/sct','432218001'), ('http://snomed.info/sct','442537007'), ('http://snomed.info/sct','442662004'), ('http://snomed.info/sct','445945000'), ('http://snomed.info/sct','48794007'), ('http://snomed.info/sct','52079000'), ('http://snomed.info/sct','62479008'), ('http://snomed.info/sct','697904001'), ('http://snomed.info/sct','697965002'), ('http://snomed.info/sct','699433000'), ('http://snomed.info/sct','700053002'), ('http://snomed.info/sct','713260006'), ('http://snomed.info/sct','713275003'), ('http://snomed.info/sct','713278001'), ('http://snomed.info/sct','713297001'), ('http://snomed.info/sct','713298006'), ('http://snomed.info/sct','713299003'), ('http://snomed.info/sct','713300006'), ('http://snomed.info/sct','713316008'), ('http://snomed.info/sct','713318009'), ('http://snomed.info/sct','713320007'), ('http://snomed.info/sct','713325002'), ('http://snomed.info/sct','713339002'), ('http://snomed.info/sct','713340000'), ('http://snomed.info/sct','713341001'), ('http://snomed.info/sct','713342008'), ('http://snomed.info/sct','713349004'), ('http://snomed.info/sct','713444005'), ('http://snomed.info/sct','713445006'), ('http://snomed.info/sct','713446007'), ('http://snomed.info/sct','713483007'), ('http://snomed.info/sct','713484001'), ('http://snomed.info/sct','713487008'), ('http://snomed.info/sct','713488003'), ('http://snomed.info/sct','713489006'), ('http://snomed.info/sct','713490002'), ('http://snomed.info/sct','713491003'), ('http://snomed.info/sct','713497004'), ('http://snomed.info/sct','713503007'), ('http://snomed.info/sct','713504001'), ('http://snomed.info/sct','713505000'), ('http://snomed.info/sct','713506004'), ('http://snomed.info/sct','713507008'), ('http://snomed.info/sct','713508003'), ('http://snomed.info/sct','713510001'), ('http://snomed.info/sct','713511002'), ('http://snomed.info/sct','713523008'), ('http://snomed.info/sct','713526000'), ('http://snomed.info/sct','713527009'), ('http://snomed.info/sct','713530002'), ('http://snomed.info/sct','713531003'), ('http://snomed.info/sct','713532005'), ('http://snomed.info/sct','713533000'), ('http://snomed.info/sct','713543002'), ('http://snomed.info/sct','713544008'), ('http://snomed.info/sct','713545009'), ('http://snomed.info/sct','713546005'), ('http://snomed.info/sct','713570009'), ('http://snomed.info/sct','713571008'), ('http://snomed.info/sct','713572001'), ('http://snomed.info/sct','713695001'), ('http://snomed.info/sct','713696000'), ('http://snomed.info/sct','713718006'), ('http://snomed.info/sct','713722001'), ('http://snomed.info/sct','713729005'), ('http://snomed.info/sct','713730000'), ('http://snomed.info/sct','713731001'), ('http://snomed.info/sct','713732008'), ('http://snomed.info/sct','713733003'), ('http://snomed.info/sct','713734009'), ('http://snomed.info/sct','713742005'), ('http://snomed.info/sct','713844000'), ('http://snomed.info/sct','713845004'), ('http://snomed.info/sct','713880000'), ('http://snomed.info/sct','713881001'), ('http://snomed.info/sct','713887002'), ('http://snomed.info/sct','713897006'), ('http://snomed.info/sct','713964006'), ('http://snomed.info/sct','713967004'), ('http://snomed.info/sct','714083007'), ('http://snomed.info/sct','714464009'), ('http://snomed.info/sct','719522009'), ('http://snomed.info/sct','721166000'), ('http://snomed.info/sct','722557007'), ('http://snomed.info/sct','733834006'), ('http://snomed.info/sct','733835007'), ('http://snomed.info/sct','735521001'), ('http://snomed.info/sct','735522008'), ('http://snomed.info/sct','735523003'), ('http://snomed.info/sct','735524009'), ('http://snomed.info/sct','735525005'), ('http://snomed.info/sct','735526006'), ('http://snomed.info/sct','735527002'), ('http://snomed.info/sct','735528007'), ('http://snomed.info/sct','771119002'), ('http://snomed.info/sct','771126002'), ('http://snomed.info/sct','771127006'), ('http://snomed.info/sct','79019005'), ('http://snomed.info/sct','80191000119101'), ('http://snomed.info/sct','81000119104'), ('http://snomed.info/sct','838338001'), ('http://snomed.info/sct','838377003'), ('http://snomed.info/sct','840442003'), ('http://snomed.info/sct','840498003'), ('http://snomed.info/sct','860871003'), ('http://snomed.info/sct','860872005'), ('http://snomed.info/sct','86406008'), ('http://snomed.info/sct','866044006'), ('http://snomed.info/sct','870271009'), ('http://snomed.info/sct','870328002'), ('http://snomed.info/sct','870344006'), ('http://snomed.info/sct','87117006'), ('http://snomed.info/sct','90681000119107'), ('http://snomed.info/sct','90691000119105'), ('http://snomed.info/sct','91947003'), ('http://snomed.info/sct','91948008'), ('http://hl7.org/fhir/sid/icd-10-cm','B20'), ('http://hl7.org/fhir/sid/icd-10-cm','B97.35'), ('http://hl7.org/fhir/sid/icd-10-cm','Z21')),
_vs_7(_vs_system, _vs_code) AS (VALUES ('http://snomed.info/sct','183452005'), ('http://snomed.info/sct','32485007'), ('http://snomed.info/sct','8715000')),
_vs_8(_vs_system, _vs_code) AS (VALUES ('https://nahdo.org/sopt','1'), ('https://nahdo.org/sopt','11'), ('https://nahdo.org/sopt','111'), ('https://nahdo.org/sopt','1111'), ('https://nahdo.org/sopt','1112'), ('https://nahdo.org/sopt','112'), ('https://nahdo.org/sopt','113'), ('https://nahdo.org/sopt','119'), ('https://nahdo.org/sopt','12'), ('https://nahdo.org/sopt','121'), ('https://nahdo.org/sopt','122'), ('https://nahdo.org/sopt','123'), ('https://nahdo.org/sopt','129'), ('https://nahdo.org/sopt','13'), ('https://nahdo.org/sopt','14'), ('https://nahdo.org/sopt','141'), ('https://nahdo.org/sopt','142'), ('https://nahdo.org/sopt','19'), ('https://nahdo.org/sopt','191'), ('https://nahdo.org/sopt','2'), ('https://nahdo.org/sopt','21'), ('https://nahdo.org/sopt','211'), ('https://nahdo.org/sopt','212'), ('https://nahdo.org/sopt','213'), ('https://nahdo.org/sopt','219'), ('https://nahdo.org/sopt','22'), ('https://nahdo.org/sopt','23'), ('https://nahdo.org/sopt','25'), ('https://nahdo.org/sopt','26'), ('https://nahdo.org/sopt','29'), ('https://nahdo.org/sopt','291'), ('https://nahdo.org/sopt','299'), ('https://nahdo.org/sopt','3'), ('https://nahdo.org/sopt','31'), ('https://nahdo.org/sopt','311'), ('https://nahdo.org/sopt','3111'), ('https://nahdo.org/sopt','3112'), ('https://nahdo.org/sopt','3113'), ('https://nahdo.org/sopt','3114'), ('https://nahdo.org/sopt','3115'), ('https://nahdo.org/sopt','3116'), ('https://nahdo.org/sopt','3119'), ('https://nahdo.org/sopt','312'), ('https://nahdo.org/sopt','3121'), ('https://nahdo.org/sopt','3122'), ('https://nahdo.org/sopt','3123'), ('https://nahdo.org/sopt','313'), ('https://nahdo.org/sopt','32'), ('https://nahdo.org/sopt','321'), ('https://nahdo.org/sopt','3211'), ('https://nahdo.org/sopt','3212'), ('https://nahdo.org/sopt','32121'), ('https://nahdo.org/sopt','32122'), ('https://nahdo.org/sopt','32123'), ('https://nahdo.org/sopt','32124'), ('https://nahdo.org/sopt','32125'), ('https://nahdo.org/sopt','32126'), ('https://nahdo.org/sopt','32127'), ('https://nahdo.org/sopt','32128'), ('https://nahdo.org/sopt','322'), ('https://nahdo.org/sopt','3221'), ('https://nahdo.org/sopt','3222'), ('https://nahdo.org/sopt','3223'), ('https://nahdo.org/sopt','3229'), ('https://nahdo.org/sopt','33'), ('https://nahdo.org/sopt','331'), ('https://nahdo.org/sopt','332'), ('https://nahdo.org/sopt','333'), ('https://nahdo.org/sopt','334'), ('https://nahdo.org/sopt','34'), ('https://nahdo.org/sopt','341'), ('https://nahdo.org/sopt','342'), ('https://nahdo.org/sopt','343'), ('https://nahdo.org/sopt','344'), ('https://nahdo.org/sopt','349'), ('https://nahdo.org/sopt','35'), ('https://nahdo.org/sopt','36'), ('https://nahdo.org/sopt','361'), ('https://nahdo.org/sopt','362'), ('https://nahdo.org/sopt','369'), ('https://nahdo.org/sopt','37'), ('https://nahdo.org/sopt','371'), ('https://nahdo.org/sopt','3711'), ('https://nahdo.org/sopt','3712'), ('https://nahdo.org/sopt','3713'), ('https://nahdo.org/sopt','372'), ('https://nahdo.org/sopt','379'), ('https://nahdo.org/sopt','38'), ('https://nahdo.org/sopt','381'), ('https://nahdo.org/sopt','3811'), ('https://nahdo.org/sopt','3812'), ('https://nahdo.org/sopt','3813'), ('https://nahdo.org/sopt','3819'), ('https://nahdo.org/sopt','382'), ('https://nahdo.org/sopt','389'), ('https://nahdo.org/sopt','39'), ('https://nahdo.org/sopt','391'), ('https://nahdo.org/sopt','4'), ('https://nahdo.org/sopt','41'), ('https://nahdo.org/sopt','42'), ('https://nahdo.org/sopt','43'), ('https://nahdo.org/sopt','44'), ('https://nahdo.org/sopt','5'), ('https://nahdo.org/sopt','51'), ('https://nahdo.org/sopt','511'), ('https://nahdo.org/sopt','512'), ('https://nahdo.org/sopt','513'), ('https://nahdo.org/sopt','514'), ('https://nahdo.org/sopt','515'), ('https://nahdo.org/sopt','516'), ('https://nahdo.org/sopt','517'), ('https://nahdo.org/sopt','519'), ('https://nahdo.org/sopt','52'), ('https://nahdo.org/sopt','521'), ('https://nahdo.org/sopt','522'), ('https://nahdo.org/sopt','523'), ('https://nahdo.org/sopt','524'), ('https://nahdo.org/sopt','529'), ('https://nahdo.org/sopt','53'), ('https://nahdo.org/sopt','54'), ('https://nahdo.org/sopt','55'), ('https://nahdo.org/sopt','56'), ('https://nahdo.org/sopt','561'), ('https://nahdo.org/sopt','562'), ('https://nahdo.org/sopt','59'), ('https://nahdo.org/sopt','6'), ('https://nahdo.org/sopt','61'), ('https://nahdo.org/sopt','611'), ('https://nahdo.org/sopt','612'), ('https://nahdo.org/sopt','613'), ('https://nahdo.org/sopt','614'), ('https://nahdo.org/sopt','619'), ('https://nahdo.org/sopt','62'), ('https://nahdo.org/sopt','621'), ('https://nahdo.org/sopt','622'), ('https://nahdo.org/sopt','623'), ('https://nahdo.org/sopt','629'), ('https://nahdo.org/sopt','7'), ('https://nahdo.org/sopt','71'), ('https://nahdo.org/sopt','72'), ('https://nahdo.org/sopt','73'), ('https://nahdo.org/sopt','79'), ('https://nahdo.org/sopt','8'), ('https://nahdo.org/sopt','81'), ('https://nahdo.org/sopt','82'), ('https://nahdo.org/sopt','821'), ('https://nahdo.org/sopt','822'), ('https://nahdo.org/sopt','823'), ('https://nahdo.org/sopt','83'), ('https://nahdo.org/sopt','84'), ('https://nahdo.org/sopt','85'), ('https://nahdo.org/sopt','89'), ('https://nahdo.org/sopt','9'), ('https://nahdo.org/sopt','91'), ('https://nahdo.org/sopt','92'), ('https://nahdo.org/sopt','93'), ('https://nahdo.org/sopt','94'), ('https://nahdo.org/sopt','95'), ('https://nahdo.org/sopt','951'), ('https://nahdo.org/sopt','953'), ('https://nahdo.org/sopt','954'), ('https://nahdo.org/sopt','959'), ('https://nahdo.org/sopt','96'), ('https://nahdo.org/sopt','97'), ('https://nahdo.org/sopt','98'), ('https://nahdo.org/sopt','99'), ('https://nahdo.org/sopt','9999')),
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
     "Condition: HIV (qicore-condition-encounter-diagnosis)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_6 ON _vs_6._vs_code = json_extract_string(_c, '$.code') AND (_vs_6._vs_system = '' OR _vs_6._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis')),
     "Encounter: Preventive Care Services - Established Office Visit, 18 and Up" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_5 ON _vs_5._vs_code = json_extract_string(_c, '$.code') AND (_vs_5._vs_system = '' OR _vs_5._vs_system = json_extract_string(_c, '$.system')))),
     "Observation: HIV 1 and 2 tests - Meaningful Use set" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Observation'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'), from_json(json_extract(r.resource::JSON, '$.code[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://loinc.org' AND json_extract_string(c, '$.code') = '75622-1')),
     "Encounter: Preventive Care Services-Initial Office Visit, 18 and Up" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_3 ON _vs_3._vs_code = json_extract_string(_c, '$.code') AND (_vs_3._vs_system = '' OR _vs_3._vs_system = json_extract_string(_c, '$.system')))),
     "Encounter: Office Visit" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_1 ON _vs_1._vs_code = json_extract_string(_c, '$.code') AND (_vs_1._vs_system = '' OR _vs_1._vs_system = json_extract_string(_c, '$.system')))),
     "Condition: HIV (qicore-condition-problems-health-concerns)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Condition'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_6 ON _vs_6._vs_code = json_extract_string(_c, '$.code') AND (_vs_6._vs_system = '' OR _vs_6._vs_system = json_extract_string(_c, '$.system')))
         AND list_contains(from_json(json_extract(r.resource, '$.meta.profile'), '["VARCHAR"]'), 'http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-problems-health-concerns')),
     "Encounter: Preventive Care, Established Office Visit, 0 to 17" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_4 ON _vs_4._vs_code = json_extract_string(_c, '$.code') AND (_vs_4._vs_system = '' OR _vs_4._vs_system = json_extract_string(_c, '$.system')))),
     "Observation: Human Immunodeficiency Virus (HIV) Laboratory Test Codes (Ab and Ag)" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Observation'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(r.resource::JSON, '$.code.coding'), '["JSON"]'),CAST([] AS JSON[]))) AS _c) _inv INNER JOIN _vs_0 ON _vs_0._vs_code = json_extract_string(_c, '$.code') AND (_vs_0._vs_system = '' OR _vs_0._vs_system = json_extract_string(_c, '$.system')))),
     "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_2 ON _vs_2._vs_code = json_extract_string(_c, '$.code') AND (_vs_2._vs_system = '' OR _vs_2._vs_system = json_extract_string(_c, '$.system')))),
     "Coverage: Payer Type" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource
     FROM resources r
     WHERE r.resourceType = 'Coverage'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_8 ON _vs_8._vs_code = json_extract_string(_c, '$.code') AND (_vs_8._vs_system = '' OR _vs_8._vs_system = json_extract_string(_c, '$.system')))),
     "Encounter: Encounter Inpatient" AS
    (SELECT DISTINCT r.patient_ref AS patient_id,
                     r.resource,
                     fhirpath_text(r.resource, 'status') AS status
     FROM resources r
     WHERE r.resourceType = 'Encounter'
         AND EXISTS (SELECT 1 FROM (SELECT unnest(flatten(COALESCE(list_transform(COALESCE(from_json(json_extract(r.resource::JSON, '$.type'), '["JSON"]'), CAST([] AS JSON[])), _cc -> COALESCE(from_json(json_extract(_cc, '$.coding'), '["JSON"]'), CAST([] AS JSON[]))), CAST([] AS JSON[][])))) AS _c) _inv INNER JOIN _vs_7 ON _vs_7._vs_code = json_extract_string(_c, '$.code') AND (_vs_7._vs_system = '' OR _vs_7._vs_system = json_extract_string(_c, '$.system')))),
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
    (SELECT p.patient_id
     FROM _patients AS p
     WHERE EXISTS
             (SELECT *
              FROM
                  (SELECT patient_id,
                          RESOURCE
                   FROM "Condition: HIV (qicore-condition-problems-health-concerns)"
                   UNION SELECT patient_id,
                                RESOURCE
                   FROM "Condition: HIV (qicore-condition-encounter-diagnosis)") AS HIVDiagnosis
              WHERE HIVDiagnosis.patient_id = p.patient_id
                  AND CAST(intervalStart(CASE
                                             WHEN fhirpath_text(HIVDiagnosis.resource, 'abatementDateTime') IS NOT NULL THEN intervalFromBounds(COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')), fhirpath_text(HIVDiagnosis.resource, 'abatementDateTime'), TRUE, TRUE)
                                             WHEN COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')) IS NOT NULL THEN CASE
                                                                                                                                                                                                                                                        WHEN EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(HIVDiagnosis.resource::JSON, '$.clinicalStatus.coding'), '["JSON"]'), from_json(json_extract(HIVDiagnosis.resource::JSON, '$.clinicalStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE (json_extract_string(c, '$.code') = 'active' OR json_extract_string(c, '$.code') = 'recurrence' OR json_extract_string(c, '$.code') = 'relapse')) THEN intervalFromBounds(COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, TRUE)
                                                                                                                                                                                                                                                        ELSE intervalFromBounds(COALESCE(fhirpath_text(HIVDiagnosis.resource, 'onsetDateTime'), fhirpath_text(HIVDiagnosis.resource, 'onsetPeriod.start'), fhirpath_text(HIVDiagnosis.resource, 'recordedDate')), CAST(NULL AS VARCHAR), TRUE, FALSE)
                                                                                                                                                                                                                                                    END
                                             ELSE NULL
                                         END) AS TIMESTAMP) < CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
                  AND NOT EXISTS (SELECT 1 FROM (SELECT unnest(COALESCE(from_json(json_extract(HIVDiagnosis.resource::JSON, '$.verificationStatus.coding'), '["JSON"]'), from_json(json_extract(HIVDiagnosis.resource::JSON, '$.verificationStatus[0].coding'), '["JSON"]'), CAST([] AS JSON[]))) AS c) _fbt WHERE json_extract_string(c, '$.system') = 'http://terminology.hl7.org/CodeSystem/condition-ver-status' AND json_extract_string(c, '$.code') = 'refuted'))),
     "Has HIV Test Performed" AS
    (SELECT p.patient_id
     FROM _patients AS p
     WHERE EXISTS
             (SELECT *
              FROM
                  (SELECT patient_id,
                          RESOURCE
                   FROM "Observation: Human Immunodeficiency Virus (HIV) Laboratory Test Codes (Ab and Ag)"
                   UNION SELECT patient_id,
                                RESOURCE
                   FROM "Observation: HIV 1 and 2 tests - Meaningful Use set") AS HIVTest
              WHERE HIVTest.patient_id = p.patient_id
                  AND fhirpath_text(HIVTest.resource, 'value') IS NOT NULL
                  AND EXTRACT(YEAR
                              FROM CAST(intervalStart(CASE
                                                          WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                          WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                          ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                      END) AS DATE)) - EXTRACT(YEAR
                                                                               FROM
                                                                                   (SELECT _pd.birth_date
                                                                                    FROM _patient_demographics AS _pd
                                                                                    WHERE _pd.patient_id = HIVTest.patient_id
                                                                                    LIMIT 1)) - CASE
                                                                                                    WHEN EXTRACT(MONTH
                                                                                                                 FROM CAST(intervalStart(CASE
                                                                                                                                             WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                                                                                             WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                                                                                             ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                                                                                         END) AS DATE)) < EXTRACT(MONTH
                                                                                                                                                                  FROM
                                                                                                                                                                      (SELECT _pd.birth_date
                                                                                                                                                                       FROM _patient_demographics AS _pd
                                                                                                                                                                       WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                       LIMIT 1))
                                                                                                         OR EXTRACT(MONTH
                                                                                                                    FROM CAST(intervalStart(CASE
                                                                                                                                                WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                                                                                                ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                                                                                            END) AS DATE)) = EXTRACT(MONTH
                                                                                                                                                                     FROM
                                                                                                                                                                         (SELECT _pd.birth_date
                                                                                                                                                                          FROM _patient_demographics AS _pd
                                                                                                                                                                          WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                          LIMIT 1))
                                                                                                         AND EXTRACT(DAY
                                                                                                                     FROM CAST(intervalStart(CASE
                                                                                                                                                 WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                                                                                                                                 WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                                                                                                                                 ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                                                                                                                             END) AS DATE)) < EXTRACT(DAY
                                                                                                                                                                      FROM
                                                                                                                                                                          (SELECT _pd.birth_date
                                                                                                                                                                           FROM _patient_demographics AS _pd
                                                                                                                                                                           WHERE _pd.patient_id = HIVTest.patient_id
                                                                                                                                                                           LIMIT 1)) THEN 1
                                                                                                    ELSE 0
                                                                                                END BETWEEN 15 AND 65
                  AND CAST(intervalStart(CASE
                                             WHEN fhirpath_text(HIVTest.resource, 'effective') IS NULL THEN NULL
                                             WHEN starts_with(LTRIM(fhirpath_text(HIVTest.resource, 'effective')), '{') THEN fhirpath_text(HIVTest.resource, 'effective')
                                             ELSE intervalFromBounds(fhirpath_text(HIVTest.resource, 'effective'), fhirpath_text(HIVTest.resource, 'effective'), TRUE, TRUE)
                                         END) AS TIMESTAMP) < CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)
                  AND (fhirpath_text(HIVTest.resource, 'status') = 'final'
                       OR fhirpath_text(HIVTest.resource, 'status') = 'amended'
                       OR fhirpath_text(HIVTest.resource, 'status') = 'corrected'))),
     "Numerator" AS
    (SELECT *
     FROM "Has HIV Test Performed"),
     "Patient Expired" AS
    (SELECT p.patient_id
     FROM _patients AS p
     WHERE CAST(fhirpath_text(
                                  (SELECT _pd.resource
                                   FROM _patient_demographics AS _pd
                                   WHERE _pd.patient_id = p.patient_id
                                   LIMIT 1), 'deceased') AS TIMESTAMP) <= CAST('2026-12-31T23:59:59.999' AS TIMESTAMP)),
     "Denominator Exceptions" AS
    (SELECT *
     FROM "Patient Expired"),
     "Qualifying Encounters" AS
    (SELECT *
     FROM
         (SELECT patient_id,
                 RESOURCE
          FROM "Encounter: Preventive Care Services, Initial Office Visit, 0 to 17"
          UNION SELECT patient_id,
                       RESOURCE
          FROM "Encounter: Preventive Care Services-Initial Office Visit, 18 and Up"
          UNION SELECT patient_id,
                       RESOURCE
          FROM "Encounter: Preventive Care, Established Office Visit, 0 to 17"
          UNION SELECT patient_id,
                       RESOURCE
          FROM "Encounter: Preventive Care Services - Established Office Visit, 18 and Up"
          UNION SELECT patient_id,
                       RESOURCE
          FROM "Encounter: Office Visit") AS Encounter
     WHERE CAST(intervalStart(fhirpath_text(Encounter.resource, 'period')) AS DATE) >= CAST(CAST('2026-01-01T00:00:00.000' AS TIMESTAMP) AS DATE)
         AND CAST(intervalEnd(fhirpath_text(Encounter.resource, 'period')) AS DATE) <= CAST(CAST('2026-12-31T23:59:59.999' AS TIMESTAMP) AS DATE)
         AND fhirpath_text(Encounter.resource, 'status') = 'finished'),
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
                                                                                                 END BETWEEN 15 AND 65
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

    "Denominator Exceptions".patient_id IS NOT NULL AS "Denominator Exceptions",

    "Numerator".patient_id IS NOT NULL AND "Initial Population".patient_id IS NOT NULL AND "Denominator Exclusions".patient_id IS NULL AS Numerator
FROM _patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Denominator Exclusions" ON p.patient_id = "Denominator Exclusions".patient_id
LEFT JOIN "Denominator Exceptions" ON p.patient_id = "Denominator Exceptions".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id ASC
