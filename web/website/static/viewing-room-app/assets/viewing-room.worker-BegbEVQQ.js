let _=null,p=null;async function y(t){_||(p||(p=(async()=>{const{createDuckDBConnection:e}=await import("./duckdb-wasm-CCZ60a6p.js"),{conn:o}=await e(t);_={conn:o}})().catch(e=>{throw p=null,e})),await p)}async function w(t){return await y(),_.conn.query(t)}function d(t,e){if(t==null)return null;const o=typeof t;if(o==="bigint")return e!==void 0&&e>0?Number(t)/Math.pow(10,e):Number(t);if(o==="number"||o==="boolean"||o==="string")return t;if(Array.isArray(t))return t.map(s=>d(s));if(o==="object"){if(typeof t.toArray=="function")return d(t.toArray());const s=String(t);if(/^-?\d+(?:\.\d+)?$/.test(s)){const c=Number(s);return e!==void 0&&e>0?c/Math.pow(10,e):c}const r={};for(const[c,f]of Object.entries(t))typeof f!="function"&&(r[c]=d(f));return r}return String(t)}async function S(t,e){var c,f;await y();const o=e.map(i=>`('${JSON.stringify(i).replace(/'/g,"''")}')`).join(", "),s=["CREATE OR REPLACE TEMP TABLE __vd_src (resource JSON)",o?`INSERT INTO __vd_src VALUES ${o}`:"INSERT INTO __vd_src SELECT NULL WHERE false"],r={schema:1,ok:!0};try{for(const n of s)await w(n);const i=await w(t),g=i.schema.fields.map(n=>n.name),h={};for(const n of i.schema.fields)h[n.name]=((c=n.type)==null?void 0:c.typeId)===7?n.scale??((f=n.type)==null?void 0:f.scale):void 0;const E=(await i.toArray()).map(n=>{const v={};for(const l of g)v[l]=d(n[l]===void 0?null:n[l],h[l]);return v});r.sql=t,r.columns=g,r.rows=JSON.parse(JSON.stringify(E))}catch(i){r.ok=!1,r.diagnostics=[{code:"evaluation_error",severity:"error",message:String(i instanceof Error?i.message:i)}]}return r}var N=Object.freeze({__proto__:null,initDuckDB:y,jsonSafe:d,runRaw:w,stageAndRunFlat:S});const b="https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";let a=null,m=!1;const u=[];function j(){m=!0;for(const t of u)t();u.length=0}async function k(){m||await new Promise(t=>u.push(t))}self.onmessage=async t=>{const e=t.data;try{const o=await D(e);self.postMessage(o)}catch(o){self.postMessage({id:e.id,type:e.type,ok:!1,error:o instanceof Error?o.message:String(o)})}};async function D(t){if(t.type==="boot")return R();await k();const e=await O(t.view_definition);if(!e.ok)return{id:t.id,type:t.type,ok:!0,envelope:JSON.stringify({schema:1,ok:!1,diagnostics:e.diagnostics})};const o=await S(e.sql,t.resources);return{id:t.id,type:t.type,ok:!0,envelope:JSON.stringify(o)}}async function O(t){await k(),a.globals.set("__vd_json",JSON.stringify(t));const e=a.runPython(`
import json
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator

try:
    vd = parse_view_definition(json.loads(__vd_json))
    gen = SQLGenerator(source_table="__vd_src")
    sql = gen.generate(vd)
    result = {"ok": True, "sql": sql}
except Exception as exc:
    from fhir4ds.operations.errors import diagnostic_from_exception
    diag = diagnostic_from_exception(exc, context="flatten_view")
    result = {"ok": False, "diagnostics": [diag.to_dict()]}
json.dumps(result)
`);return JSON.parse(e)}async function R(){if(m)return{id:0,type:"boot",ok:!0};const t=Date.now();try{const{loadPyodide:e}=await import(`${b}pyodide.mjs`);a=await e({indexURL:b}),await a.loadPackage(["micropip","duckdb","orjson","pyarrow"]);const o=new URL("./fhir4ds_v2-0.0.17-py3-none-any.whl?v=d7df06a1b48e",import.meta.url).href;a.globals.set("__wheel_url__",o),await a.runPythonAsync(`
import micropip, json

await micropip.install([
    "antlr4-python3-runtime>=4.10",
    "python-dateutil>=2.8",
])
await micropip.install(__wheel_url__, deps=False)
`),a.runPython(`
from fhir4ds.viewdef.parser import parse_view_definition
from fhir4ds.viewdef.generator import SQLGenerator
_vd = parse_view_definition({"resource": "Patient", "select": [{"column": [{"name": "id", "path": "id"}]}]})
_sql = SQLGenerator(source_table="__vd_src").generate(_vd)
assert "id" in _sql, "viewdef boot smoke failed"

import fhir4ds
__wheel_version__ = fhir4ds.__version__
`);const s=a.runPython("__wheel_version__"),{initDuckDB:r}=await Promise.resolve().then(function(){return N});return await r(),j(),{id:0,type:"boot",ok:!0,wheelVersion:s,bootMs:Date.now()-t}}catch(e){for(const o of u)o();return u.length=0,{id:0,type:"boot",ok:!1,error:e instanceof Error?e.message:String(e)}}}
