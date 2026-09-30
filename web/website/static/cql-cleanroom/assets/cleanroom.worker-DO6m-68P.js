let g=null,S=null;async function h(){g||(S||(S=(async()=>{const{createDuckDBConnection:e}=await import("./duckdb-wasm-CE68u4tl.js"),{conn:t}=await e();await t.query(`
        CREATE TABLE IF NOT EXISTS resources (
          patient_ref VARCHAR,
          resourceType VARCHAR,
          id VARCHAR,
          resource JSON
        )
      `),g={conn:t}})().catch(e=>{throw S=null,e})),await S)}async function V(e){return await h(),g.conn.query(e)}function b(e,t){if(e==null)return null;const o=typeof e;if(o==="bigint")return t!==void 0&&t>0?Number(e)/Math.pow(10,t):Number(e);if(o==="number"||o==="boolean"||o==="string")return e;if(Array.isArray(e))return e.map(i=>b(i));if(o==="object"){if(typeof e.toArray=="function")return b(e.toArray());const i=String(e);if(/^-?\d+(?:\.\d+)?$/.test(i)){const n=Number(i);return t!==void 0&&t>0?n/Math.pow(10,t):n}const r={};for(const[n,a]of Object.entries(e))typeof a!="function"&&(r[n]=b(a));return r}return String(e)}function U(e){var r;const t=e.schema.fields.map(n=>n.name),o={};for(const n of e.schema.fields)o[n.name]=n.type.typeId===7?n.scale??((r=n.type)==null?void 0:r.scale)??0:void 0;const i=[];if(typeof e.toArray=="function"){for(const n of e.toArray()){const a={};for(const c of t)a[c]=b(n[c],o[c]);i.push(a)}return{columns:t,rows:i}}throw new Error("duckdb-wasm result exposes neither toArray nor columns")}async function J(e){await h();const t=Date.now();let o;try{o=await g.conn.query(e.sql)}catch(a){const c=a instanceof Error?a.message:String(a);return console.error("[executor] SQL failed:",c,"| sql length:",e.sql.length,"| head:",JSON.stringify(e.sql.slice(0,200)),"| tail:",JSON.stringify(e.sql.slice(-120))),JSON.stringify({schema:1,ok:!1,diagnostics:[{code:"evaluation_error",severity:"error",message:c,detail:"duckdb-wasm execution"}]})}const i={evaluate:Date.now()-t},{columns:r,rows:n}=U(o);if(e.capability==="evaluate_library"){const a={schema:1,ok:!0,patient_count:n.length,columns:r,rows:n,column_types:C(e.column_types,r,e.output_columns??null),timing_ms:{evaluate:i.evaluate}};return e.emit_sql&&(a.sql=e.sql),JSON.stringify(a)}if(e.capability==="run_tests")return JSON.stringify($(n,r,e));if(e.capability==="explain_patient")return JSON.stringify(B(n,r,e));throw new Error(`unknown execution capability: ${e.capability}`)}function C(e,t,o){const i={};for(const r of t){if(r==="patient_id")continue;const n=(o==null?void 0:o[r])??r;i[r]=e[n]??"Any"}return i}function P(e,t,o){const i=t.population??t.define??"";if(i in e)return e[i];for(const[r,n]of Object.entries(o??{}))if(n===i)return e[r];return null}function $(e,t,o){var l;const i=new Map;for(const s of e){const u=String(s.patient_id??"");i.set(u,s)}const r=[];let n=0;const a=((l=o.tests)==null?void 0:l.cases)??[];for(const s of a){const u=i.get(s.patient);if(!u){r.push({patient:s.patient,target:s.population??s.define??"",expected:s.expect,actual:null,reason:"unknown patient: not present in evaluation results"});continue}const d=P(u,s,o.output_columns??null);if(d==null){r.push({patient:s.patient,target:s.population??s.define??"",expected:s.expect,actual:null,reason:`unknown population/define column: '${s.population??s.define}'`});continue}const f=!!d;f!==s.expect?r.push({patient:s.patient,target:s.population??s.define??"",expected:s.expect,actual:f,reason:null}):n+=1}const c={};for(const s of t)s!=="patient_id"&&(c[s]=e.filter(u=>u[s]===!0).length);return{schema:1,ok:!0,passed:r.length===0,library:o.library??"",patients_evaluated:e.length,summary:c,tests:{total:a.length,passed:n,failed:r.length,failures:r},timing_ms:{}}}function T(e){if(!Array.isArray(e))return e;const[t,o,i,r,n,a]=e;return{target:t,attribute:o,value:i,operator:r,threshold:n,trace:Array.isArray(a)?a:[]}}function B(e,t,o){if(!e.length)return{schema:1,ok:!1,diagnostics:[{code:"not_found",severity:"error",message:`patient '${o.patient_id}' not present in evaluation results`}],patient_id:o.patient_id??"",populations:{},definitions:[]};const i=e[0],r={},n={};for(const a of t){if(a==="patient_id")continue;const c=i[a];if(typeof c=="boolean")r[a]=c;else if(c&&typeof c=="object"&&"result"in c){const l=c;r[a]=!!l.result,n[a]=Array.isArray(l.evidence)?l.evidence.map(T):[]}else if(Array.isArray(c)&&c.length===2){r[a]=!!c[0];const l=c[1];n[a]=Array.isArray(l)?l.map(T):[]}}return{schema:1,ok:!0,patient_id:o.patient_id??"",populations:r,definitions:Object.entries(n).map(([a,c])=>({column:a,result:r[a]??null,evidence:c}))}}var H=Object.freeze({__proto__:null,buildEvidenceEnvelope:B,buildVerifyEnvelope:$,caseValue:P,initDuckDB:h,jsonSafe:b,mapColumnTypes:C,namedEvidence:T,runRaw:V,runSqlOnDuckDB:J});const L="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";let p=null,O=!1,E=null;const v=[];function Q(){O=!0;for(const e of v)e();v.length=0}async function I(){O||await new Promise(e=>v.push(e))}self.onmessage=async e=>{const t=e.data;try{const o=await z(t);self.postMessage(o)}catch(o){self.postMessage({id:t.id,type:t.type,ok:!1,error:o instanceof Error?o.message:String(o)})}};async function z(e){switch(e.type){case"boot":return K();default:await I()}switch(e.type){case"parse_cql":return _(e,"parse_cql",{text:e.text,include_ast:e.include_ast===!0});case"compare_evidence":return _(e,"compare_evidence",{baseline:e.baseline,current:e.current,output_columns:e.output_columns??null});case"translate_cql":return _(e,"translate_cql",{libraries:e.libraries,main:e.main,audit_mode:e.audit_mode??"none",patient_ids:e.patient_ids??null});case"fhirpath_eval":return _(e,"fhirpath_eval",{path:e.path,resource:e.resource});case"validate_resource":return _(e,"validate_resource",{resource:e.resource});case"resource_schema":return _(e,"resource_schema",{resource_type:e.resource_type});case"resource_schema_tree":return _(e,"resource_schema_tree",{resource_type:e.resource_type,depth:e.depth??null});case"load_dataset":return _(e,"load_dataset",{dataset:e.dataset});case"measure_from_definitions":return _(e,"measure_from_definitions",{libraries:e.libraries,main:e.main,mapping:e.mapping??null,library_urls:e.library_urls??null});case"dependency_closure":return _(e,"dependency_closure",{libraries:e.libraries,main:e.main});case"measure_population_map":return _(e,"measure_population_map",{measure:e.measure});case"measure_report_from_rows":return _(e,"measure_report_from_rows",{measure:e.measure,rows:e.rows,columns:e.columns,period_start:e.period_start??null,period_end:e.period_end??null});case"rows_from_measure_reports":return _(e,"rows_from_measure_reports",{reports:e.reports,population_codes:e.population_codes??null});case"flatten_view":{const t=await G(e.view_definition);if(!t.ok)return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:t.diagnostics})};const o=await X(t.sql,e.resources);return{id:e.id,type:e.type,ok:!0,envelope:o}}case"evaluate_snippet":return await W(e);case"evaluate_library":case"run_tests":case"explain_patient":return await M(e)}}async function W(e){var d;const t=e.snippet.trim();if(!t)return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:[{code:"input_error",message:"snippet must be a non-empty string"}]})};const o=(((d=t.match(/^[A-Za-z]+/))==null?void 0:d[0])??"").toLowerCase(),i=new Set(["define","valueset","codesystem","code","parameter","context","using","include"]),r=o==="library",n=i.has(o);let a,c,l=0;if(r)a=t,c=void 0;else if(n){const f=/^\s*define\b/m.exec(e.main.text),N=(f?e.main.text.slice(0,f.index):e.main.text).split(`
`).filter(R=>{var j;const x=(((j=R.match(/^\s*([A-Za-z]+)/))==null?void 0:j[1])??"").toLowerCase();if(!i.has(x))return!0;if(x==="using")return!/^\s*using\b/m.test(t);const y=R.match(/"([^"]+)"|^\s*[A-Za-z]+\s+([A-Za-z][\w-]*)/),k=(y==null?void 0:y[1])??(y==null?void 0:y[2]);return k?!new RegExp(`\\b${x}\\s+"${k}"|\\b${x}\\s+${k}\\b`).test(t):!0}).join(`
`);l=(N.match(/\n/g)??[]).length,a=`${N}${t}
`,c=void 0}else l=(e.main.text.match(/\n/g)??[]).length+(e.main.text.endsWith(`
`)?1:2),a=`${e.main.text}
define "__snippet__":
  (${t})
`,c={snippet:"__snippet__"};const s={...e.main,text:a},u=await M({...e,type:"evaluate_library",main:s,output_columns:c,emit_sql:!0});try{const f=JSON.parse(u.envelope);if(f.cql=a,l>0)for(const A of f.diagnostics??[]){const m=A.location;m&&(m.start_line!=null&&m.start_line>=l&&(m.start_line=m.start_line-l),m.end_line!=null&&m.end_line>=l&&(m.end_line=m.end_line-l))}return{id:e.id,type:e.type,ok:!0,envelope:JSON.stringify(f)}}catch{return{id:e.id,type:e.type,ok:!0,envelope:u.envelope}}}async function _(e,t,o){var r;if(t==="load_dataset"){const n=o.dataset;await F(n);const a=((r=n.resources)==null?void 0:r.length)??0,c={};for(const s of n.resources??[]){const u=s.resourceType??"Unknown";c[u]=(c[u]??0)+1}const l=JSON.stringify({schema:1,ok:!0,resource_counts:c,total:a});return{id:e.id,type:t,ok:!0,envelope:l}}p.globals.set("_op_name",t),p.globals.set("__cleanroom_args",JSON.stringify(o));const i=p.runPython(`
import json
from fhir4ds import operations as _ops
from fhir4ds.operations import LibraryText

class _Envelope:
    """Minimal schema:1 carrier for adapter-composed results."""
    @staticmethod
    def ok(payload):
        class _R:
            def to_dict(self_inner):
                return {"schema": 1, "ok": True, **payload}
        return _R()

    @staticmethod
    def from_error(diag):
        class _R:
            def to_dict(self_inner):
                return {"schema": 1, "ok": False, "diagnostics": [diag.to_dict()]}
        return _R()

_args = json.loads(__cleanroom_args)




def _run(op, a):
    # Per-op signature adapters: operations signatures are NOT uniform
    # (parse_cql is positional text; translate takes LibraryText objects).
    if op == "parse_cql":
        if a.get("include_ast"):
            return _ops.parse_cql(a["text"], include_ast=True)
        return _ops.parse_cql(a["text"])
    if op == "compare_evidence":
        return _ops.compare_evidence(
            a["baseline"], a["current"], output_columns=a.get("output_columns")
        )
    if op == "translate_cql":
        libs = [LibraryText(name=l["name"], text=l["text"]) for l in a["libraries"]]
        main = LibraryText(name=a["main"]["name"], text=a["main"]["text"])
        pids = a.get("patient_ids")
        mode = a.get("audit_mode") or "none"
        if mode in ("population", "full"):
            return _ops.translate_cql(libs, main, audit_mode=mode, patient_ids=pids)
        return _ops.translate_cql(libs, main)
    if op == "fhirpath_eval":
        return _ops.fhirpath_eval(a["path"], a["resource"])
    if op == "validate_resource":
        return _ops.validate_resource(a["resource"])
    if op == "resource_schema":
        return _ops.resource_schema(a["resource_type"])
    if op == "resource_schema_tree":
        return _ops.resource_schema_tree(
            a["resource_type"], depth=a.get("depth")
        )
    if op == "measure_from_definitions":
        libs = [LibraryText(name=l["name"], text=l["text"]) for l in a["libraries"]]
        main = LibraryText(name=a["main"]["name"], text=a["main"]["text"])
        return _ops.measure_from_definitions(
            libs, main, mapping=a.get("mapping"), library_urls=a.get("library_urls")
        )
    if op == "dependency_closure":
        libs = [LibraryText(name=l["name"], text=l["text"]) for l in a["libraries"]]
        main = LibraryText(name=a["main"]["name"], text=a["main"]["text"])
        ordered, missing = _ops.dependency_closure(libs, main)
        return _Envelope.ok({
            "libraries": [{"name": l.name, "text": l.text} for l in ordered],
            "missing": missing,
        })
    if op == "measure_population_map":
        pairs, diag = _ops.measure_population_map(a["measure"])
        if diag is not None:
            return _Envelope.from_error(diag)
        return _Envelope.ok({"pairs": [{"code": c, "define": d} for c, d in pairs]})
    if op == "measure_report_from_rows":
        return _ops.measure_report_from_rows(
            a["measure"], a["rows"], a["columns"],
            period_start=a.get("period_start"),
            period_end=a.get("period_end"),
        )
    if op == "rows_from_measure_reports":
        return _ops.rows_from_measure_reports(
            a["reports"], population_codes=a.get("population_codes")
        )
    raise ValueError(f"unknown op: {op}")

result = _run(_op_name, _args)
json.dumps(result.to_dict())
`);return{id:e.id,type:t,ok:!0,envelope:i}}async function M(e){var l,s;const t=e.type==="explain_patient",o={libraries:e.libraries,main:e.main,audit_mode:t?"full":"population",patient_ids:t?[e.patient_id]:null,output_columns:e.output_columns??null,parameters:e.parameters??null};p.globals.set("__cleanroom_args",JSON.stringify(o)),p.globals.set("_op_name","translate_cql");const i=p.runPython(`
import json
from fhir4ds import operations as _ops
from fhir4ds.operations import LibraryText

_args = json.loads(__cleanroom_args)
_libs = [LibraryText(name=l["name"], text=l["text"]) for l in _args["libraries"]]
_main = LibraryText(name=_args["main"]["name"], text=_args["main"]["text"])
_pids = _args.get("patient_ids")
_mode = _args.get("audit_mode") or "population"
_oc = _args.get("output_columns")
_params = _args.get("parameters")
_r = _ops.translate_cql(_libs, _main, audit_mode=_mode, patient_ids=_pids, output_columns=_oc, parameters=_params)
json.dumps(_r.to_dict())
`),r=JSON.parse(i);if(!r.ok)return{id:e.id,type:e.type,ok:!0,envelope:i};const n=e.dataset;n&&((l=n.resources)!=null&&l.length||(s=n.valueset_resources)!=null&&s.length)&&await F(n);const a={capability:e.type,library:e.main.name,sql:r.sql,column_types:r.column_types,tests:e.type==="run_tests"?e.tests:null,patient_id:e.type==="explain_patient"?e.patient_id:null,output_columns:e.output_columns??null,emit_sql:e.type==="evaluate_library"&&e.emit_sql===!0},c=await J(a);return{id:e.id,type:e.type,ok:!0,envelope:c}}async function F(e){var o;const t=[];for(const i of e.resources??[]){const r=typeof i.resourceType=="string"?i.resourceType:null,n=typeof i.id=="string"?i.id:null;t.push({patient_ref:r==="Patient"?n:Z(i),resourceType:r??"",id:n,resource:JSON.stringify(i)})}if(await h(),t.length){const i=["DELETE FROM resources",`
      INSERT INTO resources (patient_ref, resourceType, id, resource)
      SELECT patient_ref, resourceType, id, resource FROM (
        SELECT * FROM (VALUES ${t.map(r=>`(${D(r.patient_ref)}, ${q(r.resourceType)}, ${D(r.id)}, ${q(String(r.resource))})`).join(", ")})
      ) AS t(patient_ref, resourceType, id, resource)
      `];for(const r of i)try{await w(r)}catch(n){throw console.error("[loadIntoDuckDB] statement failed:",String(n),"| sql:",JSON.stringify(r.slice(0,300))),n}}if((o=e.valueset_resources)!=null&&o.length){const{valuesetToRows:i,seedValuesetCache:r}=await import("./valuesetBridge-CYJsj6tG.js"),{rows:n,warnings:a}=i(e.valueset_resources);for(const c of a)console.warn("[valuesetBridge]",c);await r(n,w)}}function Z(e){const t=e.subject??e.patient;if(!t||typeof t!="object")return null;const o=t.reference;if(typeof o!="string")return null;const i=o.split("/").filter(Boolean);return i.length>=2&&i[i.length-2]==="Patient"?i[i.length-1]:null}function q(e){return e===null?"NULL":`'${e.replace(/'/g,"''")}'`}function D(e){return q(e)}async function w(e){return(await Promise.resolve().then(function(){return H})).runRaw(e)}async function G(e){await I(),p.globals.set("__vd_json",JSON.stringify(e));const t=p.runPython(`
import json
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

try:
    vd = parse_view_definition(json.loads(__vd_json))
    gen = SQLGenerator(source_table="__cleanroom_flatten_src")
    sql = gen.generate(vd)
    result = {"ok": True, "sql": sql}
except Exception as exc:
    from fhir4ds.operations.errors import diagnostic_from_exception
    diag = diagnostic_from_exception(exc, context="flatten_view")
    result = {"ok": False, "diagnostics": [diag.to_dict()]}
json.dumps(result)
`);return JSON.parse(t)}async function X(e,t){await h();const o=t.map(n=>`('${JSON.stringify(n).replace(/'/g,"''")}')`).join(", "),i=["CREATE OR REPLACE TEMP TABLE __cleanroom_flatten_src (resource JSON)",o?`INSERT INTO __cleanroom_flatten_src VALUES ${o}`:"INSERT INTO __cleanroom_flatten_src SELECT NULL WHERE false"],r={schema:1,ok:!0};try{for(const s of i)await w(s);const n=await w(e),a=n.schema.fields.map(s=>s.name),l=(await n.toArray()).map(s=>{const u={};for(const d of a)u[d]=s[d]===void 0?null:s[d];return u});r.sql=e,r.columns=a,r.rows=JSON.parse(JSON.stringify(l))}catch(n){r.ok=!1,r.diagnostics=[{code:"evaluation_error",severity:"error",message:String(n instanceof Error?n.message:n)}]}finally{try{await w("DROP TABLE IF EXISTS __cleanroom_flatten_src")}catch{}}return JSON.stringify(r)}async function K(){if(O)return{id:0,type:"boot",ok:!0};E=null;const e=Date.now();try{const{loadPyodide:t}=await import(`${L}pyodide.mjs`);p=await t({indexURL:L}),await p.loadPackage(["micropip","duckdb","orjson","pyarrow"]);const o=new URL("./fhir4ds_v2-0.0.17-py3-none-any.whl?v=d7df06a1b48e",import.meta.url).href;p.globals.set("__wheel_url__",o),await p.runPythonAsync(`
import micropip, json

await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])
await micropip.install(__wheel_url__, deps=False)
`),p.runPython(`
# Boot resource assertions (S16): bundled .cql includes AND on-demand SD
# JSONs must resolve in MEMFS or later capabilities crash at first use.
from importlib import resources as _res
for _name in ("FHIRHelpers", "QICoreCommon", "Status"):
    _p = _res.files("fhir4ds.cql.resources.cql").joinpath(_name + ".cql")
    assert _p is not None and _p.is_file(), f"bundled CQL missing: {_name}"

from fhir4ds.cql.paths import get_resource_path as _grp
_sd_dir = _grp("fhir", "r4")
for _rt in ("Patient", "Observation", "Condition", "Encounter", "Procedure",
            "MedicationRequest", "ServiceRequest", "DeviceRequest",
            "CommunicationRequest", "Coverage"):
    _f = _sd_dir / (_rt + ".json")
    assert _f.is_file(), f"StructureDefinition missing in wheel: {_rt}"

import fhir4ds
__wheel_version__ = fhir4ds.__version__
`);const i=p.runPython("__wheel_version__");return p.runPython(`
from fhir4ds import operations as _ops
_v = _ops.validate_resource({"resourceType": "Patient", "id": "boot-check"})
assert _v.valid is True, "validate_resource boot smoke failed"
_s = _ops.resource_schema("Patient")
assert _s.ok and any(f["name"] == "gender" for f in _s.fields), \\
    "resource_schema boot smoke failed"
_t = _ops.resource_schema_tree("Observation")
assert _t.ok and any(c["name"] == "valueQuantity" for c in _t.root["children"]), \\
    "resource_schema_tree boot smoke failed"
`),await h(),Q(),{id:0,type:"boot",ok:!0,wheelVersion:i,bootMs:Date.now()-e}}catch(t){E=t instanceof Error?t.message:String(t);for(const o of v)o();return v.length=0,{id:0,type:"boot",ok:!1,error:E}}}
