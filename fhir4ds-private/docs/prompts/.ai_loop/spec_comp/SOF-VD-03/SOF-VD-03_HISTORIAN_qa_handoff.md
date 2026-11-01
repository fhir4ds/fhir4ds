# QA Handoff — SOF-VD-03 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 12-case single-lib battery, PARITY OK, values verified

row0 p1: ('p1','male','1','Chalmers','on','1974','John','Chalmers','2','male',0,'p1')
row1 p2: ('p2','female','1','Gray','off','1990','Kim','Gray','0','female',0,'p2')
row2 p3: ('p3',None,'0',None,'off',None,None,None,'0',None,0,'p3')

H: id order preserved; gender NULL for missing; name.count() '1'/'0' string;
first().family; iif over active; birthDate substring year. E: given.first();
name.family scalar; where(use='official').given.count() ('2' vs '0' — p2 has no
use); %resource.gender root-ref at select level; %rowIndex 0-based (deterministic
1-row-per-patient here); column.description retained (parse+generate accepted,
markdown doc field — not projected by design).

Evidence: .temp/qa/speccomp2/sofvd03_historian_explorer_probe1.py
